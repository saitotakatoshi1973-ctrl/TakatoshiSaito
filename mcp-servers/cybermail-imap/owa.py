#!/usr/bin/env python3
"""
Outlook メールアクセスモジュール
Claude in Chrome 拡張機能 + fetch 傍受でトークンを取得し、
Exchange REST API v2.0 でメールを読み書きする。

OWA のトークンは audience=https://outlook.office.com のため、
Graph API ではなく Exchange REST API を使用する。
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Optional

import requests as req

# ---------- 設定 ----------
_dir = os.path.dirname(os.path.abspath(__file__))

# キャッシュパス
TOKEN_CACHE_PATH   = os.path.join(_dir, "owa_token_cache.json")
FOLDER_CACHE_PATH  = os.path.join(_dir, "owa_folders_cache.json")

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Exchange REST API ベース（audience: https://outlook.office.com）
OWA_BASE = "https://outlook.office.com/api/v2.0/me"

# トークン有効期限のマージン（実際の期限より早めに期限切れとみなす）
TOKEN_MARGIN_SEC = 5 * 60  # 5分


# ======== トークンキャッシュ ========

def get_token() -> Optional[str]:
    """キャッシュ済みアクセストークンを返す。期限切れまたは未認証の場合は None。"""
    if not os.path.exists(TOKEN_CACHE_PATH):
        return None
    try:
        with open(TOKEN_CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
        expires_at = cache.get("expires_at", 0)
        if time.time() < expires_at - TOKEN_MARGIN_SEC:
            return cache.get("access_token")
    except Exception:
        pass
    return None


def _save_token(token: str, expires_in_sec: int = 3300) -> None:
    """アクセストークンをキャッシュファイルに保存する"""
    cache = {
        "access_token": token,
        "expires_at":   time.time() + expires_in_sec,
        "source":       "browser",
    }
    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def clear_token_cache() -> None:
    """トークンキャッシュを削除する（再認証が必要になる）"""
    if os.path.exists(TOKEN_CACHE_PATH):
        os.remove(TOKEN_CACHE_PATH)


# ======== ブラウザ認証（owa_browser_helper.py 経由） ========

def get_token_via_browser() -> str:
    """owa_browser_helper.py を独立プロセスで起動し、
    トークンファイルが生成されるまで待機する。"""
    import subprocess
    import sys

    helper = os.path.join(_dir, "owa_browser_helper.py")

    # 既存のキャッシュを削除
    if os.path.exists(TOKEN_CACHE_PATH):
        os.remove(TOKEN_CACHE_PATH)

    # cmd /c start で Windows GUI セッションとして起動
    subprocess.Popen(
        f'cmd /c start "" "{sys.executable}" "{helper}"',
        shell=True,
    )

    # トークンファイルが生成されるまで最大 6 分ポーリング
    deadline = time.time() + 360
    while time.time() < deadline:
        token = get_token()
        if token:
            return token
        time.sleep(2)

    raise RuntimeError(
        "タイムアウト（6分）: トークンを取得できませんでした。\n"
        "・Chrome で OWA を開き、受信トレイを表示してください\n"
        "・再度 outlook_auth を実行してください"
    )


# ======== Exchange REST API ========

def _api_get(token: str, path: str, params: Optional[dict] = None) -> dict:
    """Exchange REST API v2.0 に GET リクエストを送る"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "User-Agent":    "CybermailMCP/1.0",
    }
    url  = f"{OWA_BASE}{path}"
    resp = req.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _parse_owa_date(dt_str: str) -> str:
    """OWA の日時文字列（ISO 8601）を 'YYYY-MM-DD HH:MM' に変換する"""
    if not dt_str:
        return ""
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", dt_str)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}"
    except Exception:
        pass
    return dt_str[:16]


# ======== フォルダ操作 ========

def _collect_folders(token: str, parent_id: Optional[str], parent_path: str, result: list) -> None:
    """フォルダを再帰的に収集する"""
    if parent_id:
        path = f"/MailFolders/{parent_id}/ChildFolders"
    else:
        path = "/MailFolders"

    params = {
        "$top":    100,
        "$select": "Id,DisplayName,TotalItemCount,UnreadItemCount",
    }
    try:
        data = _api_get(token, path, params)
    except Exception:
        return

    for folder in data.get("value", []):
        name = folder.get("DisplayName", "")
        fp   = f"{parent_path}/{name}" if parent_path else name
        result.append({
            "id":     folder.get("Id", ""),
            "path":   fp,
            "count":  folder.get("TotalItemCount", 0),
            "unread": folder.get("UnreadItemCount", 0),
        })
        _collect_folders(token, folder["Id"], fp, result)


def get_all_folders(token: str) -> list[dict]:
    """全メールフォルダを再帰的に取得する"""
    result: list[dict] = []
    _collect_folders(token, None, "", result)
    return result


def refresh_folder_cache(token: str) -> list[dict]:
    """フォルダ一覧を取得してキャッシュファイルに保存する"""
    folders = get_all_folders(token)
    with open(FOLDER_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(folders, f, ensure_ascii=False, indent=2)
    return folders


def get_folder_id_by_path(path: str) -> Optional[str]:
    """フォルダパスからIDを取得する（キャッシュ参照）"""
    if not os.path.exists(FOLDER_CACHE_PATH):
        return None
    with open(FOLDER_CACHE_PATH, encoding="utf-8") as f:
        folders = json.load(f)
    for folder in folders:
        if folder["path"].lower() == path.lower():
            return folder["id"]
    return None


# ======== メール操作 ========

def get_emails_in_folder(
    token:       str,
    folder_id:   str,
    limit:       int = 50,
    skip:        int = 0,
    from_filter: Optional[str] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
) -> tuple[list[dict], int]:
    """指定フォルダのメール一覧を取得する。戻り値: (メールリスト, 総件数)"""
    params: dict = {
        "$top":     limit,
        "$skip":    skip,
        "$orderby": "ReceivedDateTime desc",
        "$select":  "Id,Subject,From,ReceivedDateTime,HasAttachments",
    }

    # フィルタ条件（Exchange REST API OData 形式）
    filters: list[str] = []
    if date_from:
        filters.append(f"ReceivedDateTime ge {date_from}T00:00:00Z")
    if date_to:
        filters.append(f"ReceivedDateTime le {date_to}T23:59:59Z")
    if from_filter:
        safe = from_filter.replace("'", "''")
        filters.append(f"contains(From/EmailAddress/Address,'{safe}')")
    if filters:
        params["$filter"] = " and ".join(filters)

    data  = _api_get(token, f"/MailFolders/{folder_id}/Messages", params)
    total = data.get("@odata.count", 0) or len(data.get("value", []))

    emails: list[dict] = []
    for msg in data.get("value", []):
        from_info = msg.get("From", {}).get("EmailAddress", {})
        emails.append({
            "id":              msg.get("Id", ""),
            "subject":         msg.get("Subject", ""),
            "from_addr":       from_info.get("Address", ""),
            "from_name":       from_info.get("Name", ""),
            "date":            _parse_owa_date(msg.get("ReceivedDateTime", "")),
            "has_attachments": msg.get("HasAttachments", False),
        })

    return emails, total


def get_email_detail(token: str, message_id: str) -> dict:
    """メール詳細（本文・添付ファイル名）を取得する"""
    msg = _api_get(token, f"/Messages/{message_id}", {
        "$select": "Id,Subject,From,ToRecipients,ReceivedDateTime,Body,HasAttachments",
        "$expand": "Attachments($select=Name,ContentType,Size)",
    })

    from_info = msg.get("From", {}).get("EmailAddress", {})
    to_list   = [
        r.get("EmailAddress", {}).get("Address", "")
        for r in msg.get("ToRecipients", [])
    ]

    # HTML 本文をプレーンテキストに変換
    body_content = msg.get("Body", {}).get("Content", "")
    body_type    = msg.get("Body", {}).get("ContentType", "text")
    if body_type == "HTML":
        body_content = re.sub(r"<script[^>]*>.*?</script>", "", body_content, flags=re.DOTALL | re.I)
        body_content = re.sub(r"<style[^>]*>.*?</style>",   "", body_content, flags=re.DOTALL | re.I)
        body_content = re.sub(r"<[^>]+>", "", body_content)
        body_content = (
            body_content
            .replace("&nbsp;", " ")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&amp;",  "&")
            .replace("&quot;", '"')
            .replace("&#39;",  "'")
        )
        body_content = re.sub(r"\n\s*\n\s*\n", "\n\n", body_content).strip()

    # 添付ファイル名取得
    att_names: list[str] = []
    if msg.get("HasAttachments"):
        expanded = msg.get("Attachments", [])
        if expanded:
            att_names = [a.get("Name", "") for a in expanded if a.get("Name")]
        else:
            try:
                att_data  = _api_get(token, f"/Messages/{message_id}/Attachments",
                                     {"$select": "Name,ContentType,Size"})
                att_names = [a.get("Name", "") for a in att_data.get("value", [])]
            except Exception:
                pass

    return {
        "id":          message_id,
        "subject":     msg.get("Subject", ""),
        "from_addr":   from_info.get("Address", ""),
        "from_name":   from_info.get("Name", ""),
        "to_addr":     "; ".join(to_list),
        "date":        _parse_owa_date(msg.get("ReceivedDateTime", "")),
        "body":        body_content[:50000],
        "attachments": att_names,
    }


# ======== DB 同期 ========

def sync_folder_to_db(
    token:       str,
    folder_id:   str,
    folder_path: str,
    db,
    max_count:   int = 200,
) -> int:
    """指定フォルダのメールを SQLite DB に差分同期する。追加件数を返す。"""
    existing = {
        row[0]
        for row in db.execute(
            "SELECT msg_id FROM emails WHERE folder = ? AND source = 'outlook'",
            (folder_path,),
        ).fetchall()
    }

    added     = 0
    skip      = 0
    page_size = 50

    while added < max_count:
        fetch = min(page_size, max_count - added)
        emails, total = get_emails_in_folder(token, folder_id, limit=fetch, skip=skip)
        if not emails:
            break

        for mail in emails:
            if mail["id"] in existing:
                skip += 1
                continue

            try:
                detail    = get_email_detail(token, mail["id"])
                body      = detail["body"]
                att_names = detail["attachments"]
                to_addr   = detail["to_addr"]
            except Exception:
                body      = ""
                att_names = []
                to_addr   = ""

            from_full = (
                f"{mail['from_name']} <{mail['from_addr']}>"
                if mail["from_name"] and mail["from_addr"]
                else mail["from_addr"]
            )

            db.execute(
                """INSERT OR IGNORE INTO emails
                   (msg_id, folder, from_addr, to_addr, subject, date,
                    body_text, attachments, source, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    mail["id"],
                    folder_path,
                    from_full[:200],
                    to_addr[:200],
                    mail["subject"][:500],
                    mail["date"],
                    body,
                    json.dumps(att_names, ensure_ascii=False) if att_names else "[]",
                    "outlook",
                    datetime.now().isoformat(),
                ),
            )
            added += 1

        skip += len(emails)
        if skip >= total:
            break

    db.commit()
    return added
