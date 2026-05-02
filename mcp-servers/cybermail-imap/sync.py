#!/usr/bin/env python3
"""
Cybermail Web API 差分同期スクリプト（UserPromptSubmit フック用）

クールダウン時間（デフォルト60分）以内に同期済みの場合はスキップする。
新着メールがある場合のみ標準出力に JSON で出力し、Claude のコンテキストに注入される。

社内LANでIMAPポートがブロックされている場合でも、HTTPS(443)経由で動作する。
"""

import html
import http.cookiejar
import json
import os
import re
import sqlite3
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime


# ---- 添付ファイル名抽出（server.py と同等）----

def _extract_attachments(html_body: str) -> list[str]:
    """Cybermail HTML レスポンスから添付ファイル名を抽出する"""
    seen: set[str] = set()
    result: list[str] = []

    def _add(name: str) -> None:
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)

    # パターン1: att_download リンクのテキストをファイル名として取得
    for m in re.finditer(r'<a[^>]+cmd=att_download[^>]*>([^<]+)</a>', html_body, re.I):
        _add(html.unescape(m.group(1)))

    # パターン2: att_download URL の fname / filename パラメータ
    for m in re.finditer(r'cmd=att_download[^"\']*[&;](?:fname|filename)=([^&"\'<>\s]+)', html_body, re.I):
        _add(urllib.parse.unquote(m.group(1)))

    # パターン3: JavaScript の rgAttInfo 配列（Cybermail 独自形式）
    for block in re.findall(r'rgAttInfo\s*=\s*\[(.*?)\]', html_body, re.DOTALL):
        for name in re.findall(r"'([^']+\.[A-Za-z0-9]{1,10})'", block):
            _add(html.unescape(name))

    # パターン4: Content-Disposition 的な記述
    for m in re.finditer(r'filename=["\']([^"\'<>\s]+)["\']', html_body, re.I):
        _add(html.unescape(m.group(1)))

    return result

_dir = os.path.dirname(os.path.abspath(__file__))


# ---- 日付パース（server.py と同等）----

def _parse_full_date(sz_date: str, date_str: str) -> str:
    """メール日時を YYYY-MM-DD HH:MM 形式に変換する。
    szDate（年付き）を優先し、取得できない場合は date_str から年を補完する。
    """
    if sz_date:
        m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})', sz_date)
        if m:
            y, mo, d, h, mi = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d} {int(h):02d}:{mi}"
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                  "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2})', sz_date)
        if m:
            d, mon, y, h, mi = m.groups()
            mo = months.get(mon, 1)
            return f"{y}-{mo:02d}-{int(d):02d} {h}:{mi}"

    if date_str:
        m = re.search(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', date_str)
        if m:
            mo, d, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            today = datetime.now()
            year  = today.year
            if mo > today.month or (mo == today.month and d > today.day):
                year -= 1
            return f"{year}-{mo:02d}-{d:02d} {h:02d}:{mi}"

    return date_str or ""


# ---- .env を手動読み込み（python-dotenv 未インストール環境でも動作）----

def _load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_env(os.path.join(_dir, ".env"))

WEB_HOST      = os.getenv("CYBERMAIL_HOST", "tsuruha.cybermail.jp")
WEB_USER      = os.getenv("CYBERMAIL_USER", "")
WEB_PASS      = os.getenv("CYBERMAIL_PASS", "")
KB_PATH       = os.getenv("CYBERMAIL_KB_PATH", os.path.join(_dir, "kb", "emails.db"))
COOLDOWN_MIN  = int(os.getenv("CYBERMAIL_SYNC_COOLDOWN_MINUTES", "60"))
COOLDOWN_FILE = os.path.join(_dir, "kb", ".last_sync")
BASE_URL      = f"https://{WEB_HOST}"
MAX_PER_FOLDER = 200  # フック実行時は軽量に


# ---- クールダウン管理 ----

def _is_in_cooldown() -> bool:
    """前回同期からクールダウン時間内かどうか確認する"""
    if not os.path.exists(COOLDOWN_FILE):
        return False
    try:
        with open(COOLDOWN_FILE) as f:
            last = datetime.fromisoformat(f.read().strip())
        elapsed_min = (datetime.now() - last).total_seconds() / 60
        return elapsed_min < COOLDOWN_MIN
    except Exception:
        return False


def _update_cooldown() -> None:
    os.makedirs(os.path.dirname(COOLDOWN_FILE), exist_ok=True)
    with open(COOLDOWN_FILE, "w") as f:
        f.write(datetime.now().isoformat())


# ---- データベース ----

def _init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            mbox       TEXT PRIMARY KEY,
            name       TEXT,
            synced_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id      TEXT,
            folder      TEXT,
            from_addr   TEXT,
            to_addr     TEXT,
            subject     TEXT,
            date        TEXT,
            body_text   TEXT,
            attachments TEXT,
            synced_at   TEXT,
            UNIQUE(msg_id, folder)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_date   ON emails(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_from   ON emails(from_addr)")

    # 既存 DB に attachments カラムがない場合は追加（マイグレーション）
    cols = [row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "attachments" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN attachments TEXT")

    conn.commit()
    return conn


# ---- Cybermail HTTPS セッション（server.py の CybermailSession と同等）----

class _Session:
    def __init__(self):
        self.crumb: str = ""
        ssl_ctx = ssl.create_default_context()
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=ssl_ctx),
        )

    def _get(self, path: str, params: dict | None = None) -> str:
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        r = self._opener.open(req, timeout=30)
        return r.read().decode("utf-8", errors="replace")

    def _post(self, path: str, data: dict) -> str:
        url = f"{BASE_URL}{path}"
        encoded = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": f"{BASE_URL}/cgi-bin/login?index=1&lang=jp",
            },
        )
        r = self._opener.open(req, timeout=30)
        return r.read().decode("utf-8", errors="replace")

    def login(self) -> bool:
        self._get("/cgi-bin/login?index=1&lang=jp")
        body = self._post(
            "/cgi-bin/login",
            {
                "USERID": WEB_USER,
                "PASSWD": WEB_PASS,
                "lang": "jp",
                "CLIENT_TOKEN": "",
                "CHALLENGE": "",
            },
        )
        m = re.search(r"crumb:\s*(\d+)", body)
        if not m:
            return False
        self.crumb = m.group(1)
        return True

    def get_folders(self) -> list[dict]:
        body = self._get(
            "/cgi-bin/msg_list",
            {"cmd": "show_list", "templ": "ajax", "mbox": "@", "msg_show": "1", "m": self.crumb},
        )
        folders: list[dict] = []
        raw = re.search(r"rgFolderInfo:\s*\[(.*?)\n\],", body, re.DOTALL)
        if raw:
            for mbox, name in re.findall(r"\['([^']+)',\s*'[^']*',\s*'([^']*)'", raw.group(1)):
                name_clean = re.sub(r"&#x[0-9A-Fa-f]+;", "", name).strip()
                if mbox:
                    folders.append({"mbox": mbox, "name": name_clean or mbox})
        return folders

    def get_email_list(self, mbox: str, max_count: int = 200) -> list[dict]:
        body = self._get(
            "/cgi-bin/msg_list",
            {
                "cmd": "show_list",
                "templ": "ajax",
                "mbox": mbox,
                "msg_show": str(max_count),
                "m": self.crumb,
            },
        )
        emails: list[dict] = []
        pattern = (
            r'\[0,\s*\'([A-Z0-9_]+)\',\s*(\d+),\s*"([^"]*)",\s*'
            r'\["([^"]*)",\s*"([^"]*)"\],\s*\'([^\']*)\''
        )
        for m in re.finditer(pattern, body):
            emails.append(
                {
                    "msg_id":    m.group(1),
                    "subject":   html.unescape(m.group(3)),
                    "from_nick": html.unescape(m.group(4)),
                    "from_addr": m.group(5),
                    "date_str":  m.group(6),
                }
            )
        return emails

    def get_email_body(self, mbox: str, msg_id: str, date_str: str = "") -> tuple[str, str, str, list[str], str]:
        """メール本文を取得する。戻り値: (テキスト本文, 差出人, 宛先, 添付ファイル名リスト, 完全日時)"""
        body = self._get(
            "/cgi-bin/msg_read",
            {
                "cmd":    "mail_all",
                "templ":  "dualbody",
                "thm":    "1",
                "m":      self.crumb,
                "mbox":   mbox,
                "msgid":  msg_id,
                "notify": "0",  # 開封通知を送信しない
                "type":   "0",
                "reload": "1",
                "crumb":  self.crumb,
            },
        )
        from_m = re.search(r'szFrom="([^"]*)"', body)
        to_m   = re.search(r'szTo="([^"]*)"',   body)
        date_m = re.search(r'szDate="([^"]*)"', body)

        from_full = html.unescape(from_m.group(1)) if from_m else ""
        to_full   = html.unescape(to_m.group(1))   if to_m   else ""
        sz_date   = html.unescape(date_m.group(1)) if date_m else ""

        # 年付き完全日時に変換
        full_date = _parse_full_date(sz_date, date_str)

        # 添付ファイル名を抽出
        attachments = _extract_attachments(body)

        body_start = body.find("<body")
        content = body[body_start:] if body_start >= 0 else body
        content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.I)
        content = re.sub(r"<style[^>]*>.*?</style>",   "", content, flags=re.DOTALL | re.I)
        text = re.sub(r"<[^>]+>", "", content)
        text = (
            text.replace("&nbsp;", " ")
                .replace("&lt;",   "<")
                .replace("&gt;",   ">")
                .replace("&amp;",  "&")
                .replace("&quot;", '"')
                .replace("&#39;",  "'")
        )
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text).strip()
        return text, from_full, to_full, attachments, full_date

    def logout(self):
        try:
            self._get("/cgi-bin/end", {"m": self.crumb})
        except Exception:
            pass


# ---- フォルダ差分同期 ----

def _sync_folder(session: _Session, mbox: str, mbox_name: str, db: sqlite3.Connection) -> int:
    """1フォルダを差分同期する。追加件数を返す"""
    try:
        email_list = session.get_email_list(mbox, MAX_PER_FOLDER)
        if not email_list:
            db.execute(
                "INSERT OR REPLACE INTO folders (mbox, name, synced_at) VALUES (?,?,?)",
                (mbox, mbox_name, datetime.now().isoformat()),
            )
            db.commit()
            return 0

        existing = {
            row[0]
            for row in db.execute(
                "SELECT msg_id FROM emails WHERE folder = ?", (mbox,)
            ).fetchall()
        }
        new_emails = [e for e in email_list if e["msg_id"] not in existing]

        added = 0
        for meta in new_emails:
            try:
                body_text, from_full, to_full, att_list, full_date = session.get_email_body(
                    mbox, meta["msg_id"], meta["date_str"]
                )
                from_addr   = from_full or meta["from_addr"]
                attachments = json.dumps(att_list, ensure_ascii=False) if att_list else None
                date        = full_date or meta["date_str"]
            except Exception:
                body_text   = ""
                from_addr   = meta["from_addr"]
                to_full     = ""
                attachments = None
                date        = _parse_full_date("", meta["date_str"]) or meta["date_str"]

            db.execute(
                """INSERT OR IGNORE INTO emails
                   (msg_id, folder, from_addr, to_addr, subject, date, body_text, attachments, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    meta["msg_id"],
                    mbox,
                    from_addr[:200],
                    to_full[:200],
                    meta["subject"][:500],
                    date,
                    body_text[:50000],
                    attachments,
                    datetime.now().isoformat(),
                ),
            )
            added += 1

        db.execute(
            "INSERT OR REPLACE INTO folders (mbox, name, synced_at) VALUES (?,?,?)",
            (mbox, mbox_name, datetime.now().isoformat()),
        )
        db.commit()
        return added

    except Exception:
        return 0


# ---- メイン ----

def main() -> None:
    if _is_in_cooldown():
        # クールダウン中はサイレントに終了（Claude への出力なし）
        sys.exit(0)

    if not WEB_USER or not WEB_PASS:
        sys.exit(0)

    try:
        session = _Session()
        if not session.login():
            sys.exit(0)

        all_folders = session.get_folders()
        db = _init_db(KB_PATH)

        # ゴミ箱・下書き・迷惑メール・アーカイブは同期対象外（送信BOXは含める）
        SKIP_FOLDERS = {"@.trash", "@.draft", "@.spam", "@.06"}

        total_added = 0
        folder_results: dict[str, int] = {}

        for fld in all_folders:
            if fld["mbox"] in SKIP_FOLDERS:
                continue
            added = _sync_folder(session, fld["mbox"], fld["name"], db)
            if added > 0:
                folder_results[fld["name"]] = added
                total_added += added

        session.logout()
        db.close()
        _update_cooldown()

        # 新着ありの場合のみ Claude のコンテキストに注入
        if total_added > 0:
            output = {
                "cybermail_sync": {
                    "status": "updated",
                    "new_emails": total_added,
                    "folders": folder_results,
                    "synced_at": datetime.now().isoformat(),
                    "message": (
                        f"Cybermailに新着メールが{total_added}件あります。"
                        "詳細は `cybermail_list_emails` ツールで確認できます。"
                    ),
                }
            }
            sys.stdout.buffer.write(
                json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8")
            )
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()

    except Exception:
        # エラーはサイレント（フックの失敗で Claude の起動を妨げない）
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
