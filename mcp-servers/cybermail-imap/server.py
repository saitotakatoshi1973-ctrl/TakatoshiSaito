#!/usr/bin/env python3
"""
Cybermail Web MCP Server
CybermailウェブメールAPI（HTTPS）経由でメールを取得・分析するMCPサーバー。
社内LAN環境でIMAPポート(993)がブロックされていてもHTTPS(443)で動作する。
"""

import asyncio
import html
import http.cookiejar
import json
import os
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, List, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

# .env ファイル読み込み
_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_dir, ".env"))

# 設定
WEB_HOST = os.getenv("CYBERMAIL_HOST", "tsuruha.cybermail.jp")
WEB_USER = os.getenv("CYBERMAIL_USER", "")
WEB_PASS = os.getenv("CYBERMAIL_PASS", "")
KB_PATH  = os.getenv(
    "CYBERMAIL_KB_PATH",
    os.path.join(_dir, "kb", "emails.db"),
)
BASE_URL = f"https://{WEB_HOST}"


# ======== CybermailSession ========

class CybermailSession:
    """Cybermailウェブメール HTTPS セッション管理"""

    def __init__(self):
        self.crumb: str = ""
        self._ssl_ctx = ssl.create_default_context()
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=self._ssl_ctx),
        )

    # ---------- 内部リクエストヘルパー ----------

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

    # ---------- 公開メソッド ----------

    def login(self) -> bool:
        """ログインしてセッションcrumbを取得する"""
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
        """フォルダ一覧を取得する"""
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

    def get_email_list(self, mbox: str, max_count: int = 500) -> list[dict]:
        """指定フォルダのメール一覧を取得する（最新 max_count 件）"""
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
        # rgRec 形式: [0, 'MSG_ID', uid_num, "subject", ["nick", "addr"], 'date', 'size', ...]
        pattern = (
            r'\[0,\s*\'([^\']+)\',\s*(\d+),\s*"([^"]*)",\s*'
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
        # メタ情報抽出
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

        # HTMLから本文テキストを抽出
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


# ======== 日付パース ========

def _parse_full_date(sz_date: str, date_str: str) -> str:
    """メール日時を YYYY-MM-DD HH:MM 形式に変換する。
    szDate（年付き）を優先し、取得できない場合は date_str から年を補完する。
    """
    # --- szDate から解析（年付き完全日時）---
    if sz_date:
        # パターン1: YYYY/MM/DD HH:MM:SS または YYYY-MM-DD HH:MM
        m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})', sz_date)
        if m:
            y, mo, d, h, mi = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d} {int(h):02d}:{mi}"
        # パターン2: RFC 2822 形式 "Thu, 01 May 2026 10:30:00 +0900"
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                  "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2})', sz_date)
        if m:
            d, mon, y, h, mi = m.groups()
            mo = months.get(mon, 1)
            return f"{y}-{mo:02d}-{int(d):02d} {h}:{mi}"

    # --- date_str から年を補完（MM/DD HH:MM 形式）---
    if date_str:
        m = re.search(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', date_str)
        if m:
            mo, d, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            today = datetime.now()
            year  = today.year
            # 月が今月より先の場合は昨年と判断
            if mo > today.month or (mo == today.month and d > today.day):
                year -= 1
            return f"{year}-{mo:02d}-{d:02d} {h:02d}:{mi}"

    return date_str or ""


# ======== 添付ファイル名抽出 ========

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
    # 例: <a href="...cmd=att_download...">report.pdf</a>
    for m in re.finditer(r'<a[^>]+cmd=att_download[^>]*>([^<]+)</a>', html_body, re.I):
        _add(html.unescape(m.group(1)))

    # パターン2: att_download URL の fname / filename パラメータ
    # 例: cmd=att_download&...&fname=report.pdf
    for m in re.finditer(r'cmd=att_download[^"\']*[&;](?:fname|filename)=([^&"\'<>\s]+)', html_body, re.I):
        _add(urllib.parse.unquote(m.group(1)))

    # パターン3: JavaScript の rgAttInfo 配列（Cybermail 独自形式）
    # 例: rgAttInfo = [['report.pdf', ...], ...]
    for block in re.findall(r'rgAttInfo\s*=\s*\[(.*?)\]', html_body, re.DOTALL):
        for name in re.findall(r"'([^']+\.[A-Za-z0-9]{1,10})'", block):
            _add(html.unescape(name))

    # パターン4: Content-Disposition 的な記述（テキスト部分）
    # 例: filename="report.pdf"
    for m in re.finditer(r'filename=["\']([^"\'<>\s]+)["\']', html_body, re.I):
        _add(html.unescape(m.group(1)))

    return result


# ======== データベース ========

def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
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

    # マイグレーション: カラム追加
    cols = [row[1] for row in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "attachments" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN attachments TEXT")
    if "source" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN source TEXT DEFAULT 'cybermail'")
        conn.execute("UPDATE emails SET source = 'cybermail' WHERE source IS NULL")

    conn.commit()
    return conn


def _sync_folder_web(
    session: CybermailSession,
    mbox: str,
    mbox_name: str,
    db: sqlite3.Connection,
    max_per_folder: int,
) -> int:
    """1フォルダを差分同期する。追加件数を返す"""
    try:
        email_list = session.get_email_list(mbox, max_per_folder)
        if not email_list:
            db.execute(
                "INSERT OR REPLACE INTO folders (mbox, name, synced_at) VALUES (?,?,?)",
                (mbox, mbox_name, datetime.now().isoformat()),
            )
            db.commit()
            return 0

        # DB に存在しない msg_id だけ取得
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
            except Exception:
                # 本文取得失敗時はヘッダーだけ保存（年補完のみ試みる）
                fallback_date = _parse_full_date("", meta["date_str"])
                db.execute(
                    """INSERT OR IGNORE INTO emails
                       (msg_id, folder, from_addr, to_addr, subject, date, body_text, attachments, synced_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        meta["msg_id"],
                        mbox,
                        meta["from_addr"][:200],
                        "",
                        meta["subject"][:500],
                        fallback_date or meta["date_str"],
                        "",
                        None,
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


# ======== Lifespan ========

@asynccontextmanager
async def app_lifespan(server):
    conn = init_db(KB_PATH)
    yield {"db": conn}
    conn.close()


mcp = FastMCP("cybermail_mcp", lifespan=app_lifespan)


# ======== Pydantic Input Models ========

class SyncInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    folders: Optional[List[str]] = Field(
        default=None,
        description="同期するフォルダのmboxキー（@, @.01 など）。省略時は全フォルダ",
    )
    max_per_folder: Optional[int] = Field(
        default=200, ge=1, le=2000,
        description="フォルダあたりの最大取得件数（デフォルト: 200）",
    )


class ListEmailsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    folder: Optional[str] = Field(default=None, description="フォルダmbox（省略時は全フォルダ）")
    limit: Optional[int]  = Field(default=20, ge=1, le=200, description="取得件数（最大200）")
    offset: Optional[int] = Field(default=0, ge=0, description="スキップ件数（ページング）")
    from_addr: Optional[str] = Field(default=None, description="送信者フィルタ（部分一致）")
    date_from: Optional[str] = Field(default=None, description="開始日 YYYY-MM-DD")
    date_to:   Optional[str] = Field(default=None, description="終了日 YYYY-MM-DD")


class GetEmailInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    email_id:     int  = Field(..., ge=1, description="メールのDB ID（cybermail_list_emails で確認）")
    include_html: bool = Field(default=False, description="未使用（互換性のため残存）")


class SearchEmailsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    query: str           = Field(..., min_length=1, max_length=500, description="検索キーワード")
    limit: Optional[int] = Field(default=20, ge=1, le=100, description="取得件数（最大100）")


# ======== Tools ========

@mcp.tool(
    name="cybermail_sync",
    annotations={
        "title": "Cybermailメール同期",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def cybermail_sync(params: SyncInput, ctx: Context) -> str:
    """ウェブメールAPIからメールを取得し、ローカル知識ベース（SQLite）を差分更新する。

    初回は全件取得、2回目以降は DB に未登録のメールのみ追加する。
    フォルダ未指定の場合は全フォルダを対象とする。
    """
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    loop = asyncio.get_event_loop()

    try:
        await ctx.report_progress(0.0, "Cybermailにログイン中...")
        session = CybermailSession()
        ok = await loop.run_in_executor(None, session.login)
        if not ok:
            return "Error: ログインに失敗しました。認証情報を確認してください。"

        # フォルダ一覧取得
        # ゴミ箱・下書き・迷惑メール・アーカイブは同期対象外（送信BOXは含める）
        SKIP_FOLDERS = {"@.trash", "@.draft", "@.spam", "@.06"}

        all_folders = await loop.run_in_executor(None, session.get_folders)
        if params.folders:
            target = [f for f in all_folders if f["mbox"] in params.folders and f["mbox"] not in SKIP_FOLDERS]
        else:
            target = [f for f in all_folders if f["mbox"] not in SKIP_FOLDERS]

        total_added = 0
        details: list[str] = []

        for i, fld in enumerate(target):
            progress = (i + 1) / len(target) * 0.95
            await ctx.report_progress(progress, f"同期中: {fld['name']} ({fld['mbox']})")
            added = await loop.run_in_executor(
                None,
                _sync_folder_web,
                session,
                fld["mbox"],
                fld["name"],
                db,
                params.max_per_folder,
            )
            total_added += added
            if added > 0:
                details.append(f"  {fld['name']} ({fld['mbox']}): +{added}件")

        await loop.run_in_executor(None, session.logout)
        await ctx.report_progress(1.0, "同期完了")

        result = (
            f"## 同期完了\n\n"
            f"- 対象フォルダ: {len(target)}個\n"
            f"- 新規追加: {total_added}件\n"
        )
        if details:
            result += "\n### 詳細\n" + "\n".join(details)
        return result

    except Exception as e:
        return f"Error: 予期しないエラー - {type(e).__name__}: {e}"


@mcp.tool(
    name="cybermail_list_folders",
    annotations={
        "title": "フォルダ一覧取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cybermail_list_folders(ctx: Context) -> str:
    """知識ベースに同期済みのフォルダ一覧とメール件数を返す。"""
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    rows = db.execute("""
        SELECT f.mbox, f.name, f.synced_at, COUNT(e.id) AS cnt
        FROM folders f
        LEFT JOIN emails e ON e.folder = f.mbox
        GROUP BY f.mbox
        ORDER BY f.mbox
    """).fetchall()

    if not rows:
        return "知識ベースにフォルダがありません。`cybermail_sync` を実行してください。"

    lines = ["## 同期済みフォルダ一覧\n"]
    for mbox, name, synced_at, cnt in rows:
        synced = synced_at[:19] if synced_at else "未同期"
        lines.append(f"- **{name}** (`{mbox}`): {cnt}件（最終同期: {synced}）")
    return "\n".join(lines)


@mcp.tool(
    name="cybermail_list_emails",
    annotations={
        "title": "メール一覧取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cybermail_list_emails(params: ListEmailsInput, ctx: Context) -> str:
    """知識ベースからメール一覧を取得する。フォルダ・送信者・日付でフィルタリング可能。"""
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]

    conditions: list[str] = []
    args: list[Any] = []

    if params.folder:
        conditions.append("folder = ?")
        args.append(params.folder)
    if params.from_addr:
        conditions.append("from_addr LIKE ?")
        args.append(f"%{params.from_addr}%")
    if params.date_from:
        conditions.append("date >= ?")
        args.append(params.date_from)
    if params.date_to:
        conditions.append("date <= ?")
        args.append(f"{params.date_to}T23:59:59")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = db.execute(f"SELECT COUNT(*) FROM emails {where}", args).fetchone()[0]
    rows = db.execute(
        f"""SELECT id, folder, from_addr, subject, date, attachments
            FROM emails {where}
            ORDER BY date DESC
            LIMIT ? OFFSET ?""",
        args + [params.limit, params.offset],
    ).fetchall()

    if not rows:
        return "該当するメールがありません。"

    shown_from = params.offset + 1
    shown_to   = params.offset + len(rows)
    lines = [f"## メール一覧 ({shown_from}〜{shown_to} / 全{total}件)\n"]

    for row_id, folder, from_addr, subject, date, attachments in rows:
        dt = (date or "")[:16] or "----"
        # 添付ファイルアイコンと件数
        att_label = ""
        if attachments:
            try:
                att_list = json.loads(attachments)
                if att_list:
                    att_label = f" 📎{len(att_list)}"
            except Exception:
                pass
        lines.append(
            f"**[{row_id}]** {dt} | {folder} | {(from_addr or '')[:30]} | {(subject or '')[:60]}{att_label}"
        )

    if total > shown_to:
        lines.append(f"\n*次のページ: offset={params.offset + params.limit}*")

    return "\n".join(lines)


@mcp.tool(
    name="cybermail_get_email",
    annotations={
        "title": "メール詳細取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cybermail_get_email(params: GetEmailInput, ctx: Context) -> str:
    """指定 ID のメール詳細（ヘッダー・本文）を取得する。"""
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    row = db.execute(
        "SELECT id, folder, from_addr, to_addr, subject, date, body_text, attachments FROM emails WHERE id = ?",
        (params.email_id,),
    ).fetchone()

    if not row:
        return f"Error: ID {params.email_id} のメールが見つかりません。"

    row_id, folder, from_addr, to_addr, subject, date, body_text, attachments = row

    # 添付ファイル名を解析
    att_names: list[str] = []
    if attachments:
        try:
            att_names = json.loads(attachments)
        except Exception:
            pass

    lines = [
        f"## メール詳細 [ID: {row_id}]",
        "",
        f"**フォルダ**: {folder}",
        f"**日時**: {date}",
        f"**From**: {from_addr}",
        f"**To**: {to_addr}",
        f"**件名**: {subject}",
    ]

    if att_names:
        lines.append(f"**添付ファイル**: {', '.join(att_names)}")
    else:
        lines.append("**添付ファイル**: なし")

    lines += [
        "",
        "---",
        "",
        "### 本文",
        "",
        body_text or "（本文なし）",
    ]
    return "\n".join(lines)


@mcp.tool(
    name="cybermail_search_emails",
    annotations={
        "title": "メール全文検索",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cybermail_search_emails(params: SearchEmailsInput, ctx: Context) -> str:
    """件名・本文・送信者を横断してキーワード検索する。"""
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    pat = f"%{params.query}%"
    rows = db.execute(
        """SELECT id, folder, from_addr, subject, date, body_text
           FROM emails
           WHERE subject LIKE ? OR body_text LIKE ? OR from_addr LIKE ?
           ORDER BY date DESC
           LIMIT ?""",
        (pat, pat, pat, params.limit),
    ).fetchall()

    if not rows:
        return f"「{params.query}」に一致するメールが見つかりません。"

    lines = [f"## 検索結果: 「{params.query}」({len(rows)}件)\n"]
    for row_id, folder, from_addr, subject, date, body_text in rows:
        dt = (date or "")[:16] or "----"
        lines.append(f"**[{row_id}]** {dt} | {(from_addr or '')[:25]} | {subject}")
        if body_text:
            idx = body_text.lower().find(params.query.lower())
            if idx >= 0:
                s = max(0, idx - 50)
                e = min(len(body_text), idx + len(params.query) + 50)
                excerpt = body_text[s:e].replace("\n", " ").strip()
                lines.append(f"  *...{excerpt}...*")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="cybermail_get_stats",
    annotations={
        "title": "知識ベース統計情報",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cybermail_get_stats(ctx: Context) -> str:
    """知識ベースの統計情報を返す（総件数・期間・送信者TOP5など）。"""
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]

    total        = db.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    folder_count = db.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
    date_range   = db.execute("SELECT MIN(date), MAX(date) FROM emails").fetchone()
    top_senders  = db.execute(
        """SELECT from_addr, COUNT(*) AS cnt FROM emails
           GROUP BY from_addr ORDER BY cnt DESC LIMIT 5"""
    ).fetchall()
    last_sync = db.execute("SELECT MAX(synced_at) FROM folders").fetchone()[0]

    lines = [
        "## 知識ベース統計",
        "",
        f"- **総メール数**: {total}件",
        f"- **フォルダ数**: {folder_count}個",
        f"- **期間**: {(date_range[0] or '')[:10]} 〜 {(date_range[1] or '')[:10]}",
        f"- **最終同期**: {(last_sync or '')[:19]}",
        "",
        "### 送信者 TOP5",
    ]
    for addr, cnt in top_senders:
        lines.append(f"- {addr}: {cnt}件")

    return "\n".join(lines)


# ======== Outlook OWA Tools ========

class OutlookListFoldersInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    refresh: Optional[bool] = Field(
        default=False,
        description="True にするとフォルダ一覧を再取得してキャッシュを更新する",
    )


class OutlookListEmailsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    folder_path: str           = Field(..., description="フォルダパス（例: 受信トレイ）。outlook_list_folders で確認")
    limit:       Optional[int] = Field(default=30, ge=1, le=200, description="取得件数")
    offset:      Optional[int] = Field(default=0,  ge=0,          description="スキップ件数（ページング）")
    from_filter: Optional[str] = Field(default=None, description="差出人フィルタ（部分一致）")
    date_from:   Optional[str] = Field(default=None, description="開始日 YYYY-MM-DD")
    date_to:     Optional[str] = Field(default=None, description="終了日 YYYY-MM-DD")


class OutlookGetEmailInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    message_id: str = Field(..., description="メールID（outlook_list_emails の id フィールド）")


class OutlookSyncInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    folder_path:    str            = Field(..., description="同期するフォルダパス（例: 受信トレイ）")
    max_per_folder: Optional[int]  = Field(default=200, ge=1, le=2000, description="最大取得件数")
    recursive:      Optional[bool] = Field(default=False, description="サブフォルダも再帰同期するか")


@mcp.tool(
    name="outlook_auth",
    annotations={
        "title": "Outlook 認証（ブラウザ自動起動）",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def outlook_auth(ctx: Context) -> str:
    """Playwright で Chromium を起動し、OWA セッショントークンを取得する。

    手順:
    1. Chromium ウィンドウが自動で開く
    2. HENNGE でログイン（初回のみ。2回目以降はセッションが残っていれば自動）
    3. OWA の受信トレイが表示されたら自動でトークンをキャプチャして完了
    """
    import owa
    loop = asyncio.get_event_loop()

    # すでにトークンが有効な場合はスキップ
    existing = await loop.run_in_executor(None, owa.get_token)
    if existing:
        return "✅ すでに認証済みです。トークンは有効期限内です。"

    try:
        await ctx.report_progress(0.1, "Chromium を起動中...")
        token = await loop.run_in_executor(None, owa.get_token_via_browser)
        await ctx.report_progress(0.9, "フォルダキャッシュを更新中...")

        # フォルダキャッシュも更新
        await loop.run_in_executor(None, owa.refresh_folder_cache, token)

        await ctx.report_progress(1.0, "認証完了")
        return (
            "## Outlook 認証完了 ✅\n\n"
            "トークンを取得しました。フォルダキャッシュを更新しました。\n"
            "以降は `outlook_list_folders` や `outlook_sync` を使用できます。\n\n"
            "※ トークン有効期限：約55分（期限切れ後は再度 `outlook_auth` を実行）"
        )
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="outlook_list_folders",
    annotations={
        "title": "Outlookフォルダ一覧取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def outlook_list_folders(params: OutlookListFoldersInput, ctx: Context) -> str:
    """Outlook の全フォルダを一覧表示する。件数・未読数を含む。
    refresh=True でサーバーから最新データを取得してキャッシュを更新する。
    """
    import owa
    loop = asyncio.get_event_loop()

    token = await loop.run_in_executor(None, owa.get_token)
    if not token:
        return (
            "Error: 未認証です。まず `outlook_auth` を実行してください。"
        )

    try:
        await ctx.report_progress(0.0, "フォルダ一覧を取得中...")

        if params.refresh or not os.path.exists(owa.FOLDER_CACHE_PATH):
            folders = await loop.run_in_executor(None, owa.refresh_folder_cache, token)
        else:
            with open(owa.FOLDER_CACHE_PATH, encoding="utf-8") as f:
                folders = json.load(f)

        await ctx.report_progress(1.0, "取得完了")

        if not folders:
            return "フォルダが見つかりません。"

        lines = [f"## Outlook フォルダ一覧（{len(folders)}個）\n"]
        for fld in folders:
            depth  = fld["path"].count("/")
            indent = "  " * depth
            name   = fld["path"].split("/")[-1]
            unread = fld.get("unread", 0)
            count  = fld.get("count", 0)
            unread_str = f" 未読:{unread}" if unread > 0 else ""
            lines.append(f"{indent}- **{name}** ({count}件{unread_str})  `{fld['path']}`")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="outlook_list_emails",
    annotations={
        "title": "Outlookメール一覧取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def outlook_list_emails(params: OutlookListEmailsInput, ctx: Context) -> str:
    """Outlook の指定フォルダのメール一覧を取得する（新着順）。"""
    import owa
    loop = asyncio.get_event_loop()

    token = await loop.run_in_executor(None, owa.get_token)
    if not token:
        return "Error: 未認証です。まず `outlook_auth` を実行してください。"

    folder_id = await loop.run_in_executor(None, owa.get_folder_id_by_path, params.folder_path)
    if not folder_id:
        return (
            f"Error: フォルダ「{params.folder_path}」が見つかりません。\n"
            "`outlook_list_folders` でフォルダ一覧を確認してください。"
        )

    try:
        emails, total = await loop.run_in_executor(
            None,
            owa.get_emails_in_folder,
            token, folder_id,
            params.limit, params.offset,
            params.from_filter, params.date_from, params.date_to,
        )

        if not emails:
            return f"「{params.folder_path}」に該当するメールがありません。"

        shown_from = params.offset + 1
        shown_to   = params.offset + len(emails)
        lines = [f"## {params.folder_path} ({shown_from}〜{shown_to} / 全{total}件)\n"]

        for m in emails:
            att = " 📎" if m["has_attachments"] else ""
            lines.append(
                f"**{m['date']}** | {m['from_addr'][:30]} | {m['subject'][:60]}{att}"
            )
            lines.append(f"  id: `{m['id']}`")

        if total > shown_to:
            lines.append(f"\n*次のページ: offset={params.offset + params.limit}*")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="outlook_get_email",
    annotations={
        "title": "Outlookメール詳細取得",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def outlook_get_email(params: OutlookGetEmailInput, ctx: Context) -> str:
    """Outlook のメール詳細（本文・添付ファイル名）を取得する。"""
    import owa
    loop = asyncio.get_event_loop()

    token = await loop.run_in_executor(None, owa.get_token)
    if not token:
        return "Error: 未認証です。まず `outlook_auth` を実行してください。"

    try:
        mail = await loop.run_in_executor(None, owa.get_email_detail, token, params.message_id)

        att_str = ", ".join(mail["attachments"]) if mail["attachments"] else "なし"
        lines = [
            "## メール詳細",
            "",
            f"**日時**: {mail['date']}",
            f"**From**: {mail['from_name']} <{mail['from_addr']}>",
            f"**To**: {mail['to_addr']}",
            f"**件名**: {mail['subject']}",
            f"**添付**: {att_str}",
            "",
            "---",
            "",
            "### 本文",
            "",
            mail["body"] or "（本文なし）",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@mcp.tool(
    name="outlook_sync",
    annotations={
        "title": "Outlookメール同期（DBへ保存）",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def outlook_sync(params: OutlookSyncInput, ctx: Context) -> str:
    """Outlook の指定フォルダのメールを SQLite DB に差分同期する。"""
    import owa
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    loop = asyncio.get_event_loop()

    token = await loop.run_in_executor(None, owa.get_token)
    if not token:
        return "Error: 未認証です。まず `outlook_auth` を実行してください。"

    try:
        await ctx.report_progress(0.0, "フォルダ情報を取得中...")

        # フォルダキャッシュを確認
        if not os.path.exists(owa.FOLDER_CACHE_PATH):
            await loop.run_in_executor(None, owa.refresh_folder_cache, token)

        with open(owa.FOLDER_CACHE_PATH, encoding="utf-8") as f:
            all_folders = json.load(f)

        # 対象フォルダを特定
        if params.recursive:
            targets = [
                fld for fld in all_folders
                if fld["path"] == params.folder_path
                or fld["path"].startswith(params.folder_path + "/")
            ]
        else:
            targets = [
                fld for fld in all_folders
                if fld["path"] == params.folder_path
            ]

        if not targets:
            return (
                f"Error: フォルダ「{params.folder_path}」が見つかりません。\n"
                "`outlook_list_folders` でフォルダ一覧を確認してください。"
            )

        total_added = 0
        details: list[str] = []

        for i, fld in enumerate(targets):
            progress = (i + 1) / len(targets) * 0.95
            await ctx.report_progress(progress, f"同期中: {fld['path']}")
            added = await loop.run_in_executor(
                None,
                owa.sync_folder_to_db,
                token, fld["id"], fld["path"], db, params.max_per_folder,
            )
            total_added += added
            if added > 0:
                details.append(f"  {fld['path']}: +{added}件")

        await ctx.report_progress(1.0, "同期完了")

        result = (
            f"## Outlook 同期完了\n\n"
            f"- 対象フォルダ: {len(targets)}個\n"
            f"- 新規追加: {total_added}件\n"
        )
        if details:
            result += "\n### 詳細\n" + "\n".join(details)
        return result

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


class BackfillInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    batch_size: Optional[int] = Field(
        default=50, ge=1, le=500,
        description="一度に処理する件数（デフォルト: 50）",
    )


@mcp.tool(
    name="cybermail_backfill_attachments",
    annotations={
        "title": "添付ファイル名バックフィル（既存レコード一括更新）",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def cybermail_backfill_attachments(params: BackfillInput, ctx: Context) -> str:
    """attachments が NULL の既存メールに対して添付ファイル名を遡及取得・更新する。
    今後の新着メールは通常の同期で自動的に取得されるため、このツールは初回のみ使用する。
    """
    db: sqlite3.Connection = ctx.request_context.lifespan_state["db"]
    loop = asyncio.get_event_loop()

    # attachments が NULL のレコードを取得（date も同時に更新するため date カラムも取得）
    targets = db.execute(
        "SELECT id, folder, msg_id, date FROM emails WHERE attachments IS NULL ORDER BY id"
    ).fetchall()

    total = len(targets)
    if total == 0:
        return "添付ファイル名が未取得のメールはありません。すでに最新の状態です。"

    try:
        await ctx.report_progress(0.0, f"Cybermailにログイン中... (対象: {total}件)")
        session = CybermailSession()
        ok = await loop.run_in_executor(None, session.login)
        if not ok:
            return "Error: ログインに失敗しました。認証情報を確認してください。"

        updated = 0
        skipped = 0

        for i, (row_id, folder, msg_id, old_date) in enumerate(targets):
            progress = (i + 1) / total
            if i % 10 == 0:
                await ctx.report_progress(progress, f"処理中: {i+1}/{total}件")

            try:
                _, _, _, att_list, full_date = await loop.run_in_executor(
                    None, session.get_email_body, folder, msg_id, old_date or ""
                )
                attachments = json.dumps(att_list, ensure_ascii=False) if att_list else "[]"
                new_date    = full_date or old_date
                db.execute(
                    "UPDATE emails SET attachments = ?, date = ? WHERE id = ?",
                    (attachments, new_date, row_id),
                )
                updated += 1
            except Exception:
                skipped += 1

            # batch_size ごとにコミット
            if (i + 1) % params.batch_size == 0:
                db.commit()

        db.commit()
        await loop.run_in_executor(None, session.logout)
        await ctx.report_progress(1.0, "バックフィル完了")

        # 添付ありの件数を集計
        with_att = db.execute(
            "SELECT COUNT(*) FROM emails WHERE attachments IS NOT NULL AND attachments != '[]'"
        ).fetchone()[0]

        return (
            f"## 添付ファイル名バックフィル完了\n\n"
            f"- 対象: {total}件\n"
            f"- 更新成功: {updated}件\n"
            f"- スキップ（取得失敗）: {skipped}件\n"
            f"- 添付ファイルあり: {with_att}件\n\n"
            "次回以降の新着メールは通常の同期で自動的に取得されます。"
        )

    except Exception as e:
        return f"Error: 予期しないエラー - {type(e).__name__}: {e}"


if __name__ == "__main__":
    mcp.run()
