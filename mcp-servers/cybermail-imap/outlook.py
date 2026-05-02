#!/usr/bin/env python3
"""
Outlook COM 操作モジュール
pywin32 を使ってローカルの Outlook アプリからメールを取得する。
読み取り専用（フェーズ1）。書き込み操作はフェーズ2で追加予定。
"""

import json
import re
from datetime import datetime
from typing import Optional


def _get_outlook():
    """起動中の Outlook Application オブジェクトを取得する。
    Outlook が起動していない場合は RuntimeError を送出する。
    """
    try:
        import pythoncom
        import win32com.client
        # スレッド内から呼ぶ場合に必要な COM 初期化
        pythoncom.CoInitialize()
        # GetActiveObject: すでに起動中の Outlook に接続（新規起動しない）
        return win32com.client.GetActiveObject("Outlook.Application")
    except Exception as e:
        raise RuntimeError(
            "Outlook に接続できません。Outlook を起動してからもう一度お試しください。\n"
            f"詳細: {e}"
        )


def _get_namespace():
    """MAPI NameSpace を取得する"""
    outlook = _get_outlook()
    ns = outlook.GetNamespace("MAPI")
    # プロファイルを明示的にログオン（必要な場合）
    try:
        ns.Logon()
    except Exception:
        pass
    return ns


# ---- 日付変換 ----

def _format_date(pytime) -> str:
    """PyTime オブジェクトを YYYY-MM-DD HH:MM 形式の文字列に変換する"""
    if pytime is None:
        return ""
    try:
        # win32com の PyTime は str() で変換可能
        s = str(pytime)
        # 形式: "2026/05/01 10:30:00" or "05/01/26 10:30:00" など環境依存
        # datetime にパースして統一形式に変換
        for fmt in (
            "%m/%d/%Y %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(s.strip(), fmt)
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                continue
        return s[:16]
    except Exception:
        return ""


# ---- フォルダ操作 ----

def _folder_path(folder) -> str:
    """フォルダの完全パスを '/' 区切りで返す（ルートは除く）"""
    parts = []
    current = folder
    # ルートストアの直下まで遡る
    while True:
        try:
            parent = current.Parent
            # Parent が Namespace や Store レベルになったら終了
            if not hasattr(parent, "Parent") or parent.Class not in (2, 15):
                break
            parts.append(current.Name)
            current = parent
        except Exception:
            break
    parts.append(current.Name)
    parts.reverse()
    return "/".join(parts)


def get_all_folders(include_stats: bool = True) -> list[dict]:
    """
    全フォルダを再帰的に取得してリストで返す。

    戻り値:
        [{"path": "受信トレイ", "entry_id": "...", "count": 10, "last_date": "2026-05-01"}, ...]
    """
    ns = _get_namespace()
    results: list[dict] = []

    def _traverse(folder, parent_path: str = ""):
        name = folder.Name
        path = f"{parent_path}/{name}" if parent_path else name
        entry_id = ""
        try:
            entry_id = folder.EntryID
        except Exception:
            pass

        count = 0
        last_date = ""
        if include_stats:
            try:
                items = folder.Items
                count = items.Count
                if count > 0:
                    # 最新メールの日付を取得（受信日時でソート）
                    try:
                        items.Sort("[ReceivedTime]", True)
                        last_item = items.GetFirst()
                        if last_item and hasattr(last_item, "ReceivedTime"):
                            last_date = _format_date(last_item.ReceivedTime)[:10]
                    except Exception:
                        pass
            except Exception:
                pass

        results.append({
            "path":      path,
            "entry_id":  entry_id,
            "count":     count,
            "last_date": last_date,
        })

        # サブフォルダを再帰処理
        try:
            for sub in folder.Folders:
                _traverse(sub, path)
        except Exception:
            pass

    # ns.Folders はアカウント（ストア）のルートフォルダ一覧
    # 例: "saito-t@kyorindo.co.jp"、"パブリックフォルダ" など
    for account_folder in ns.Folders:
        try:
            for folder in account_folder.Folders:
                _traverse(folder)
        except Exception:
            pass

    return results


def get_folder_by_path(path: str):
    """パス文字列からフォルダオブジェクトを取得する"""
    ns = _get_namespace()
    parts = path.split("/")

    def _find(folder, remaining: list[str]):
        if not remaining:
            return folder
        target = remaining[0]
        for sub in folder.Folders:
            if sub.Name == target:
                return _find(sub, remaining[1:])
        return None

    # 全アカウントフォルダから検索
    for account_folder in ns.Folders:
        try:
            result = _find(account_folder, parts)
            if result:
                return result
        except Exception:
            pass

    return None


# ---- メール一覧取得 ----

def get_emails_in_folder(
    folder_path: str,
    limit: int = 50,
    offset: int = 0,
    from_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[list[dict], int]:
    """
    指定フォルダのメール一覧を取得する。

    戻り値: (メールリスト, 総件数)
    """
    folder = get_folder_by_path(folder_path)
    if folder is None:
        raise ValueError(f"フォルダが見つかりません: {folder_path}")

    items = folder.Items
    items.Sort("[ReceivedTime]", True)  # 新着順

    emails: list[dict] = []
    total = 0
    skipped = 0

    for i in range(1, items.Count + 1):
        try:
            item = items[i]
            # メールアイテム以外（会議出席依頼など）はスキップ
            if not hasattr(item, "Subject"):
                continue

            # フィルタ適用
            sender = ""
            try:
                sender = getattr(item, "SenderEmailAddress", "") or ""
            except Exception:
                pass

            recv_date = ""
            try:
                recv_date = _format_date(item.ReceivedTime)
            except Exception:
                pass

            if from_filter and from_filter.lower() not in sender.lower():
                continue
            if date_from and recv_date[:10] < date_from:
                continue
            if date_to and recv_date[:10] > date_to:
                continue

            total += 1

            if skipped < offset:
                skipped += 1
                continue
            if len(emails) >= limit:
                continue

            # 添付ファイル名
            att_names: list[str] = []
            try:
                for j in range(1, item.Attachments.Count + 1):
                    att = item.Attachments.Item(j)
                    att_names.append(att.FileName)
            except Exception:
                pass

            emails.append({
                "entry_id":    item.EntryID,
                "subject":     getattr(item, "Subject", "") or "",
                "from_addr":   sender,
                "from_name":   getattr(item, "SenderName", "") or "",
                "date":        recv_date,
                "attachments": att_names,
                "folder_path": folder_path,
            })
        except Exception:
            continue

    return emails, total


# ---- メール詳細取得 ----

def get_email_by_entry_id(entry_id: str) -> Optional[dict]:
    """EntryID からメール詳細を取得する"""
    ns = _get_namespace()
    try:
        item = ns.GetItemFromID(entry_id)
        if item is None:
            return None

        # 宛先
        to_addrs: list[str] = []
        try:
            for j in range(1, item.Recipients.Count + 1):
                r = item.Recipients.Item(j)
                to_addrs.append(getattr(r, "Address", r.Name) or r.Name)
        except Exception:
            pass

        # 添付ファイル名
        att_names: list[str] = []
        try:
            for j in range(1, item.Attachments.Count + 1):
                att = item.Attachments.Item(j)
                att_names.append(att.FileName)
        except Exception:
            pass

        # 本文（プレーンテキスト優先）
        body = ""
        try:
            body = item.Body or ""
        except Exception:
            pass

        return {
            "entry_id":    entry_id,
            "subject":     getattr(item, "Subject", "") or "",
            "from_addr":   getattr(item, "SenderEmailAddress", "") or "",
            "from_name":   getattr(item, "SenderName", "") or "",
            "to_addr":     "; ".join(to_addrs),
            "date":        _format_date(getattr(item, "ReceivedTime", None)),
            "body":        body[:50000],
            "attachments": att_names,
        }
    except Exception as e:
        raise RuntimeError(f"メール取得エラー: {e}")


# ---- DB 同期用 ----

def sync_folder_to_db(
    folder_path: str,
    db,
    max_count: int = 200,
) -> int:
    """
    指定フォルダのメールを SQLite DB に差分同期する。
    戻り値: 追加件数
    """
    folder = get_folder_by_path(folder_path)
    if folder is None:
        return 0

    items = folder.Items
    items.Sort("[ReceivedTime]", True)

    # DB に存在する entry_id を取得
    existing = {
        row[0]
        for row in db.execute(
            "SELECT msg_id FROM emails WHERE folder = ? AND source = 'outlook'",
            (folder_path,)
        ).fetchall()
    }

    added = 0
    count = min(items.Count, max_count)

    for i in range(1, count + 1):
        try:
            item = items[i]
            if not hasattr(item, "Subject"):
                continue

            entry_id = item.EntryID
            if entry_id in existing:
                continue

            # 日付
            date = _format_date(getattr(item, "ReceivedTime", None))

            # 差出人
            from_addr = getattr(item, "SenderEmailAddress", "") or ""
            from_name = getattr(item, "SenderName", "") or ""
            from_full = f"{from_name} <{from_addr}>" if from_name and from_addr else (from_name or from_addr)

            # 宛先
            to_addrs: list[str] = []
            try:
                for j in range(1, item.Recipients.Count + 1):
                    r = item.Recipients.Item(j)
                    to_addrs.append(getattr(r, "Address", r.Name) or r.Name)
            except Exception:
                pass

            # 添付ファイル名
            att_names: list[str] = []
            try:
                for j in range(1, item.Attachments.Count + 1):
                    att = item.Attachments.Item(j)
                    att_names.append(att.FileName)
            except Exception:
                pass

            # 本文
            body = ""
            try:
                body = (item.Body or "")[:50000]
            except Exception:
                pass

            db.execute(
                """INSERT OR IGNORE INTO emails
                   (msg_id, folder, from_addr, to_addr, subject, date,
                    body_text, attachments, source, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry_id,
                    folder_path,
                    from_full[:200],
                    ("; ".join(to_addrs))[:200],
                    (getattr(item, "Subject", "") or "")[:500],
                    date,
                    body,
                    json.dumps(att_names, ensure_ascii=False) if att_names else "[]",
                    "outlook",
                    datetime.now().isoformat(),
                ),
            )
            added += 1

        except Exception:
            continue

    db.commit()
    return added
