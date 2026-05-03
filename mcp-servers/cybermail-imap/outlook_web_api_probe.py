#!/usr/bin/env python3
"""
Outlook Web API プローブ。

DBには書き込まず、Outlook Webの通信からBearer tokenを検出し、
利用可能な読み取りAPIでフォルダ一覧と受信トレイのメール一覧を取得する。

接続方式の経緯:
- Microsoft Graph Device Code Flow は tenant_id を特定できず失敗した。
- Outlook COM は新しいOutlookがCOM/MAPIを公開しないため失敗した。
- Outlook Web接続は成功したため、通信中のBearer tokenを使う方式を検証する。
- Graph tokenは検出できたがAPI呼び出しは403だったため、Outlook REST APIを使う。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_PROFILE_DIR = Path(__file__).with_name("outlook_web_profile")
OUTLOOK_URL = "https://outlook.office.com/mail/"
LOCAL_BROWSER_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]
TARGET_HOSTS = (
    "outlook.office.com",
    "graph.microsoft.com",
    "substrate.office.com",
)
EXCLUDED_FOLDER_WORDS = (
    "archive",
    "アーカイブ",
    "deleted",
    "削除",
    "trash",
    "ゴミ箱",
    "junk",
    "迷惑",
    "spam",
    "draft",
    "下書き",
    "rss",
    "sync issues",
    "同期の失敗",
    "recoverable",
    "検出された項目",
    "conversation history",
    "会話の履歴",
    "reminders",
    "再通知設定済み",
    "outbox",
    "送信トレイ",
)


@dataclass
class CapturedToken:
    token: str
    host: str
    aud: str
    exp: int | None


def find_local_browser() -> str | None:
    """PCにインストール済みのEdge/Chromeを探す。"""
    for path in LOCAL_BROWSER_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """JWTのpayloadを検証なしでデコードする。"""
    try:
        part = token.split(".")[1]
        padded = part + "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def get_header(headers: dict[str, str], name: str) -> str:
    """Playwrightのヘッダーdictから大文字小文字を無視して値を取る。"""
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return ""


def wait_for_mail_ui(page, timeout_ms: int) -> bool:
    """Outlook WebのメールUIらしい要素が出るまで待つ。"""
    selectors = [
        '[aria-label*="メール"]',
        '[aria-label*="Mail"]',
        '[aria-label*="受信"]',
        '[aria-label*="Inbox"]',
        'text=受信トレイ',
        'text=Inbox',
        'text=新規メール',
        'text=New mail',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.wait_for(timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def graph_get(token: str, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Graph APIへGETする。"""
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": 'IdType="ImmutableId"',
        },
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def exchange_get(token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Outlook REST APIへGETする。"""
    resp = requests.get(
        f"https://outlook.office.com/api/v2.0/me{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "OutlookWebApiProbe/1.0",
        },
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def is_excluded_folder(name: str) -> bool:
    """同期除外候補かどうかを簡易判定する。"""
    lower_name = name.lower()
    return any(word in lower_name for word in EXCLUDED_FOLDER_WORDS)


def print_folder_plan(folders: list[dict[str, Any]], provider: str) -> None:
    """フォルダ選別結果を表示する。"""
    total_count = len(folders)
    excluded = []
    targets = []

    for folder in folders:
        path = folder.get("Path") or folder.get("path") or folder.get("DisplayName") or folder.get("displayName") or ""
        if is_excluded_folder(path):
            excluded.append(folder)
        else:
            targets.append(folder)

    safe_print("")
    safe_print(f"=== フォルダ選別結果 ({provider}) ===")
    safe_print(f"全フォルダ数: {total_count}")
    safe_print(f"同期対象フォルダ数: {len(targets)}")
    safe_print(f"除外フォルダ数: {len(excluded)}")

    safe_print("")
    safe_print("=== 除外フォルダ ===")
    for folder in excluded:
        path = folder.get("Path") or folder.get("path") or folder.get("DisplayName") or folder.get("displayName") or ""
        count = folder.get("TotalItemCount", folder.get("totalItemCount", 0))
        unread = folder.get("UnreadItemCount", folder.get("unreadItemCount", 0))
        safe_print(f"- {path} / total={count} unread={unread}")


def safe_text(value: Any) -> str:
    """Windowsコンソールで表示できない文字を置換する。"""
    text = "" if value is None else str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def safe_print(text: str = "") -> None:
    """表示不能文字でプローブが止まらないように出力する。"""
    print(safe_text(text))


def collect_graph_folders(token: str, parent_id: str | None = None, parent_path: str = "") -> list[dict[str, Any]]:
    """Graphでメールフォルダを再帰取得する。"""
    if parent_id:
        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{parent_id}/childFolders"
    else:
        url = "https://graph.microsoft.com/v1.0/me/mailFolders"

    folders = graph_get(
        token,
        url,
        {
            "$top": 100,
            "$select": "id,displayName,totalItemCount,unreadItemCount,childFolderCount",
        },
    ).get("value", [])

    results: list[dict[str, Any]] = []
    for folder in folders:
        name = folder.get("displayName", "")
        path = f"{parent_path}/{name}" if parent_path else name
        folder["path"] = path
        results.append(folder)
        if folder.get("childFolderCount", 0):
            results.extend(collect_graph_folders(token, folder.get("id"), path))
    return results


def collect_exchange_folders(token: str, parent_id: str | None = None, parent_path: str = "") -> list[dict[str, Any]]:
    """Outlook REST APIでメールフォルダを再帰取得する。"""
    path = f"/MailFolders/{parent_id}/ChildFolders" if parent_id else "/MailFolders"
    folders = exchange_get(
        token,
        path,
        {
            "$top": 100,
            "$select": "Id,DisplayName,TotalItemCount,UnreadItemCount,ChildFolderCount",
        },
    ).get("value", [])

    results: list[dict[str, Any]] = []
    for folder in folders:
        name = folder.get("DisplayName", "")
        folder_path = f"{parent_path}/{name}" if parent_path else name
        folder["Path"] = folder_path
        results.append(folder)
        if folder.get("ChildFolderCount", 0):
            results.extend(collect_exchange_folders(token, folder.get("Id"), folder_path))
    return results


def probe_graph(token: str) -> bool:
    """Graphでフォルダ一覧と受信トレイメール一覧を試す。"""
    safe_print("")
    safe_print("=== Graph API Probe ===")
    folders = collect_graph_folders(token)
    print_folder_plan(folders, "Graph")

    safe_print(f"フォルダ取得: {len(folders)}件")
    inbox_id = None
    for folder in folders:
        name = folder.get("displayName", "")
        path = folder.get("path", name)
        mark = "除外候補" if is_excluded_folder(path) else "対象候補"
        safe_print(
            f"- [{mark}] {path} / total={folder.get('totalItemCount', 0)} "
            f"unread={folder.get('unreadItemCount', 0)}"
        )
        if name.lower() in {"inbox", "受信トレイ", "受信box", "受信箱"}:
            inbox_id = folder.get("id")

    if not inbox_id and folders:
        safe_print("受信トレイを自動検出できませんでした。メール一覧取得はスキップします。")
        return True

    messages = graph_get(
        token,
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{inbox_id}/messages",
        {
            "$top": 10,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,hasAttachments",
        },
    ).get("value", [])

    safe_print("")
    safe_print(f"受信トレイ メール一覧: {len(messages)}件")
    for msg in messages:
        from_info = (msg.get("from") or {}).get("emailAddress") or {}
        safe_print(
            f"- {msg.get('receivedDateTime', '')[:16]} | "
            f"{from_info.get('name', '')} <{from_info.get('address', '')}> | "
            f"{msg.get('subject', '')}"
        )
    return True


def probe_exchange(token: str) -> bool:
    """Outlook REST APIでフォルダ一覧と受信トレイメール一覧を試す。"""
    safe_print("")
    safe_print("=== Outlook REST API Probe ===")
    folders = collect_exchange_folders(token)
    print_folder_plan(folders, "Outlook REST")

    safe_print(f"フォルダ取得: {len(folders)}件")
    inbox_id = None
    for folder in folders:
        name = folder.get("DisplayName", "")
        path = folder.get("Path", name)
        mark = "除外候補" if is_excluded_folder(path) else "対象候補"
        safe_print(
            f"- [{mark}] {path} / total={folder.get('TotalItemCount', 0)} "
            f"unread={folder.get('UnreadItemCount', 0)}"
        )
        if name.lower() in {"inbox", "受信トレイ", "受信box", "受信箱"}:
            inbox_id = folder.get("Id")

    if not inbox_id and folders:
        safe_print("受信トレイを自動検出できませんでした。メール一覧取得はスキップします。")
        return True

    messages = exchange_get(
        token,
        f"/MailFolders/{inbox_id}/Messages",
        {
            "$top": 10,
            "$orderby": "ReceivedDateTime desc",
            "$select": "Id,Subject,From,ReceivedDateTime,HasAttachments",
        },
    ).get("value", [])

    safe_print("")
    safe_print(f"受信トレイ メール一覧: {len(messages)}件")
    for msg in messages:
        from_info = ((msg.get("From") or {}).get("EmailAddress") or {})
        safe_print(
            f"- {msg.get('ReceivedDateTime', '')[:16]} | "
            f"{from_info.get('Name', '')} <{from_info.get('Address', '')}> | "
            f"{msg.get('Subject', '')}"
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlook Web API プローブ")
    parser.add_argument("--url", default=OUTLOOK_URL, help="接続先URL")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="ブラウザプロファイル保存先")
    parser.add_argument("--timeout-sec", type=int, default=180, help="トークン検出待ち時間")
    parser.add_argument("--browser-exe", default=None, help="Edge/Chromeの実行ファイルパス")
    parser.add_argument("--headless", action="store_true", help="画面を表示せずに実行する")
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser_exe = args.browser_exe or find_local_browser()

    print("=== Outlook Web API プローブ ===")
    print("DBには書き込みません。トークンもファイル保存しません。")
    print(f"URL: {args.url}")
    print(f"Profile: {profile_dir}")
    print(f"Browser: {browser_exe or 'Playwright bundled Chromium'}")
    print("")

    captured: dict[str, CapturedToken] = {}

    def on_request(request) -> None:
        try:
            host = request.url.split("/")[2].lower()
            if not any(target in host for target in TARGET_HOSTS):
                return
            auth = get_header(request.headers, "authorization")
            if not auth.startswith("Bearer "):
                return
            token = auth[7:]
            if token in captured:
                return
            payload = decode_jwt_payload(token)
            aud = str(payload.get("aud", ""))
            exp = payload.get("exp")
            captured[token] = CapturedToken(token=token, host=host, aud=aud, exp=exp if isinstance(exp, int) else None)
            print(f"token検出: host={host} aud={aud or '-'} len={len(token)}")
        except Exception:
            return

    with sync_playwright() as p:
        launch_options = {
            "user_data_dir": str(profile_dir),
            "headless": args.headless,
            "viewport": {"width": 1400, "height": 900},
            "locale": "ja-JP",
        }
        if browser_exe:
            launch_options["executable_path"] = browser_exe

        browser = p.chromium.launch_persistent_context(**launch_options)
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.on("request", on_request)

        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            print("Outlook Webを開きました。ログイン画面が出た場合は手動でログインしてください。")
            print("トークンが検出されない場合は、メールを1通クリックしてください。")

            wait_for_mail_ui(page, min(args.timeout_sec, 60) * 1000)
            deadline = time.time() + args.timeout_sec
            while time.time() < deadline and not captured:
                page.wait_for_timeout(1000)

            if not captured:
                print("Error: Bearer tokenを検出できませんでした。", file=sys.stderr)
                return 1
        finally:
            browser.close()

    tokens = list(captured.values())
    print("")
    print("=== 検出トークン ===")
    for i, item in enumerate(tokens, start=1):
        exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.exp)) if item.exp else "-"
        print(f"{i}. host={item.host} aud={item.aud or '-'} exp={exp_str}")

    errors: list[str] = []
    for item in tokens:
        try:
            if "graph.microsoft.com" in item.host or item.aud in {"00000003-0000-0000-c000-000000000000", "https://graph.microsoft.com"}:
                if probe_graph(item.token):
                    print("")
                    print("Result: OK - Graph APIでフォルダ/メール一覧を取得できました。")
                    return 0
        except Exception as e:
            errors.append(f"Graph API失敗: {type(e).__name__}: {e}")

        try:
            if "outlook.office.com" in item.host or "outlook.office.com" in item.aud:
                if probe_exchange(item.token):
                    print("")
                    print("Result: OK - Outlook REST APIでフォルダ/メール一覧を取得できました。")
                    return 0
        except Exception as e:
            errors.append(f"Outlook REST API失敗: {type(e).__name__}: {e}")

    print("")
    print("Result: NG - 検出トークンでフォルダ/メール一覧を取得できませんでした。", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
