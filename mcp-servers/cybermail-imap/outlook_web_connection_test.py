#!/usr/bin/env python3
"""
新しいOutlook / Outlook on the web 接続テスト。

DBには書き込まず、PlaywrightでOutlook Webを開いてメール画面が
表示できるかだけを確認する。

接続方式の経緯:
- Microsoft Graph Device Code Flow は tenant_id を特定できず失敗した。
- Outlook COM は新しいOutlookがCOM/MAPIを公開しないため失敗した。
- このため、ログイン済みのOutlook WebをPlaywrightで開く方式を採用した。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def find_local_browser() -> str | None:
    """PCにインストール済みのEdge/Chromeを探す。"""
    for path in LOCAL_BROWSER_CANDIDATES:
        if path.exists():
            return str(path)
    return None


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlook Web 接続テスト")
    parser.add_argument("--url", default=OUTLOOK_URL, help="接続先URL")
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="ブラウザプロファイル保存先",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=180,
        help="手動ログイン待ち時間",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="画面を表示せずに実行する。初回ログイン時は非推奨",
    )
    parser.add_argument(
        "--browser-exe",
        default=None,
        help="Edge/Chromeの実行ファイルパス。省略時は自動検出",
    )
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser_exe = args.browser_exe or find_local_browser()

    print("=== Outlook Web 接続テスト ===")
    print("DBには書き込みません。")
    print(f"URL: {args.url}")
    print(f"Profile: {profile_dir}")
    print(f"Browser: {browser_exe or 'Playwright bundled Chromium'}")
    print("")

    with sync_playwright() as p:
        launch_options = {
            "user_data_dir": str(profile_dir),
            "headless": args.headless,
            "viewport": {"width": 1400, "height": 900},
            "locale": "ja-JP",
        }
        if browser_exe:
            launch_options["executable_path"] = browser_exe

        browser = p.chromium.launch_persistent_context(
            **launch_options,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            print("ブラウザを開きました。ログイン画面が出た場合は手動でログインしてください。")
            print(f"最大 {args.timeout_sec} 秒待機します。")

            ok = wait_for_mail_ui(page, args.timeout_sec * 1000)
            current_url = page.url
            title = page.title()

            print("")
            print("=== 判定 ===")
            print(f"title: {title}")
            print(f"url: {current_url}")
            if ok:
                print("Result: OK - Outlook Webのメール画面を確認できました。")
                return 0

            print("Result: NG - メール画面を確認できませんでした。", file=sys.stderr)
            print("ログイン未完了、追加認証、または画面文言の違いの可能性があります。", file=sys.stderr)
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
