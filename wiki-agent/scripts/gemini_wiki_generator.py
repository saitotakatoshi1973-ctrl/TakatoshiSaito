"""
gemini_wiki_generator.py
========================
Excel / PPTX / PDF ファイルを Gemini 2.5 Flash API で wiki Markdown に変換するスクリプト。

【スタンドアロンモード】ファイルを指定して直接wiki生成・保存
    python gemini_wiki_generator.py <ファイルパス> [--dest <保存先>] [--dry-run]

【スキル統合モード（--body-only）】write-wiki.md から呼び出し、本文のみ stdout に出力
    python gemini_wiki_generator.py <ファイルパス> --body-only
        [--wiki-type strategy] [--title "タイトル"]
        [--scope kyorindo] [--domain cx] [--tags "CX,戦略"]
        [--converted-text "事前抽出テキスト"]

例:
    python gemini_wiki_generator.py "C:/Users/.../資料.xlsx"
    python gemini_wiki_generator.py "C:/Users/.../資料.pptx" --dest kyorindo/it-systems/
    python gemini_wiki_generator.py "C:/Users/.../資料.pdf" --dry-run
    python gemini_wiki_generator.py "C:/Users/.../資料.pptx" --body-only --wiki-type strategy --title "CX戦略"
"""

import argparse
import hashlib
import os
import re
import sys
import textwrap
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── 定数 ────────────────────────────────────────────────
PERSONAL_ROOT  = Path(r"C:\Users\takatoshi-saito\OneDrive\00personal")
KB_ROOT        = PERSONAL_ROOT / "KnowledgeBase"
PROCESSED_PATH = KB_ROOT / "_system" / "processed-sources.yaml"
DOTENV_PATH    = PERSONAL_ROOT / "ClaudeCodeFolder" / ".env"

TODAY = date.today().isoformat()


# ── .env 読み込み ────────────────────────────────────────
load_dotenv(DOTENV_PATH)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY が設定されていません。.env ファイルを確認してください。")
    sys.exit(1)


# ── Gemini クライアント初期化 ────────────────────────────
from google import genai
CLIENT = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"


# ════════════════════════════════════════════════════════
# テキスト抽出
# ════════════════════════════════════════════════════════

def extract_text(file_path: Path) -> str:
    """拡張子に応じてテキストを抽出する"""
    ext = file_path.suffix.lower()

    if ext == ".xlsx":
        return _extract_excel(file_path)
    elif ext == ".pptx":
        return _extract_pptx(file_path)
    elif ext == ".pdf":
        return _extract_pdf(file_path)
    else:
        raise ValueError(f"未対応の形式: {ext}")


def _extract_excel(file_path: Path) -> str:
    """Excel ファイルからテキストを抽出する"""
    import openpyxl
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        lines.append(f"## シート: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            # 空行はスキップ
            if any(c.strip() for c in cells):
                lines.append("\t".join(cells))
    wb.close()
    return "\n".join(lines)


def _extract_pptx(file_path: Path) -> str:
    """PPTX ファイルからテキストを抽出する"""
    from pptx import Presentation
    prs = Presentation(file_path)
    lines = []
    for i, slide in enumerate(prs.slides, 1):
        slide_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        slide_texts.append(text)
        if slide_texts:
            lines.append(f"## スライド {i}")
            lines.extend(slide_texts)
    return "\n".join(lines)


def _extract_pdf(file_path: Path) -> str:
    """PDF ファイルからテキストを抽出する"""
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    lines = []
    for i, page in enumerate(doc, 1):
        text = page.get_text().strip()
        if text:
            lines.append(f"## ページ {i}")
            lines.append(text)
    doc.close()
    return "\n".join(lines)


# ════════════════════════════════════════════════════════
# Gemini API でwiki生成
# ════════════════════════════════════════════════════════

# ── wiki_type 別テンプレート ─────────────────────────────
WIKI_TYPE_TEMPLATES = {
    "strategy": """\
## 背景・目的
（元資料から読み取れる背景や目的を2〜4文で記述）

## 主要内容
（ロードマップ・施策・方針を箇条書きまたはフェーズ別に整理）

## 重要ポイント
（意思決定に影響する数値・KPI・優先事項を箇条書き）

## 関連リンク
（分類先フォルダ内の関連ファイルがあればパスを記述、なければ空）""",

    "organization": """\
## 概要
（組織・企業の基本情報）

## 組織構成
（部署・チーム・人員構成を箇条書きまたは表で整理）

## 役割・担当
（主要ポストと担当業務）

## 変更履歴
（直近の組織変更があれば記録）""",

    "issue": """\
## 課題一覧

| # | 課題 | 優先度 | 担当 |
|---|------|--------|------|
| 1 | ...  | 高     | ...  |

## 背景・原因
（課題の発生背景や根本原因）

## 対応方針
（解決に向けた方向性・アプローチ）""",

    "progress": """\
## 日時・参加者
- 日時: YYYY-MM-DD HH:MM
- 参加者: （氏名・部署）

## 議題
（議題を箇条書き）

## 決定事項
（決定内容を箇条書き）

## 次回アクション

| 担当 | 内容 | 期限 |
|------|------|------|""",

    "reference": """\
## 出典情報
- 媒体/著者:
- 公開日:

## 要点サマリー
（3〜5文で主要な主張・結論を要約）

## 詳細メモ
（重要な数値・固有名詞・ファクトを箇条書き）

## 自社への示唆
（杏林堂やプロジェクトに関連する示唆があれば記述）""",

    "task": """\
## タスク一覧

| # | タスク | 優先度 | 担当 | 期限 | 状態 |
|---|--------|--------|------|------|------|

## 背景・目的
（このタスクリストの目的）""",

    "log": """\
## 日時
YYYY-MM-DD

## 内容
（議論や作業の概要）

## 判断理由
（なぜその判断をしたか）

## 次のステップ
（続きのアクション）""",

    "benchmark": """\
## 比較軸
（何を比較するかの定義）

## 比較テーブル

| 企業/項目 | 指標1 | 指標2 | 指標3 |
|----------|-------|-------|-------|

## 考察
（比較から読み取れる示唆・杏林堂の立ち位置）""",

    "research": """\
## 出典
- 主催/著者:
- 日時/公開日:
- 形式: セミナー | レポート | 論文

## 概要
（2〜3文でテーマと主旨を説明）

## 重要な知見
（箇条書きで重要な発見・主張を列挙）

## 自社への示唆
（実務・プロジェクトへの応用可能性）""",
}

# ── スタンドアロン用プロンプト（Front-matter込み） ───────────
WIKI_PROMPT_TEMPLATE = textwrap.dedent("""\
    あなたは社内ナレッジベースのwikiライターです。
    以下のビジネス文書のテキストを読み、社内wiki用のMarkdownファイルを生成してください。

    ## 出力形式

    必ず以下のYAML front-matterから始めてください：

    ---
    title: "（文書のタイトル）"
    wiki_type: "（meeting_notes / reference / strategy / specification / report / manual のいずれか）"
    source: "{source_path}"
    source_date: "（文書の作成日・更新日。YYYYMMDD形式。不明なら空文字）"
    created: "{today}"
    status: active
    tags: [（関連タグをカンマ区切りで）]
    ---

    ## 本文の書き方

    - 文書の内容を日本語で整理してください
    - 重要な数値・日付・固有名詞は必ず含めてください
    - テーブル形式で整理できる情報はMarkdownテーブルにしてください
    - 見出し（##）で構造化してください
    - 最後に「## 関連情報」セクションを追加してください（関連が推測できる場合）

    ## 文書テキスト

    ファイル名: {file_name}
    フォルダパス: {folder_path}

    {content}
""")

# ── スキル統合用プロンプト（本文のみ・Front-matterなし） ───────
WIKI_BODY_PROMPT_TEMPLATE = textwrap.dedent("""\
    あなたは社内ナレッジベースのwikiライターです。
    以下のビジネス文書のテキストを読み、wiki記事の本文を日本語で執筆してください。

    ## 分類情報（システムが事前に決定済み）

    wiki_type : {wiki_type}
    タイトル  : {title}
    保存先    : {destination}
    スコープ  : {scope}
    ドメイン  : {domain}
    タグ      : {tags}

    ## 出力セクション構成（wiki_typeに対応するテンプレート）

    {template}

    ## 執筆ルール

    - Front-matter（---で囲まれたYAMLブロック）は出力しない
    - テンプレートのセクション構成を必ず守る
    - 元資料にない内容は推測して書かない
    - 元資料に情報が不足するセクションは「（情報なし）」と記載する
    - 固有名詞・数値・日付は元資料のものを正確に使う
    - 文体は「である調」で統一する
    - 分量: 300〜800文字（summaryモード時は150〜300文字）

    ## 文書テキスト

    ファイル名: {file_name}
    フォルダパス: {folder_path}

    {content}
""")


def generate_wiki(file_path: Path, content: str) -> str:
    """【スタンドアロン用】Front-matter込みのwiki Markdownを生成する"""
    source_path = to_personal_relative(file_path)
    prompt = WIKI_PROMPT_TEMPLATE.format(
        source_path=source_path,
        today=TODAY,
        file_name=file_path.name,
        folder_path=str(file_path.parent),
        content=content[:50000],
    )
    print("🤖 Gemini API に送信中...")
    response = CLIENT.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return response.text


def generate_wiki_body(
    file_path: Path,
    content: str,
    wiki_type: str = "reference",
    title: str = "",
    destination: str = "",
    scope: str = "",
    domain: str = "",
    tags: list[str] | None = None,
) -> str:
    """【スキル統合用】本文のみ（Front-matterなし）を生成して返す。
    analyze.md の分類結果を受け取り、wiki_type に対応するテンプレートで執筆する。
    write-wiki.md から --body-only モードで呼び出される。
    """
    template = WIKI_TYPE_TEMPLATES.get(wiki_type, WIKI_TYPE_TEMPLATES["reference"])
    prompt = WIKI_BODY_PROMPT_TEMPLATE.format(
        wiki_type=wiki_type,
        title=title or file_path.stem,
        destination=destination,
        scope=scope,
        domain=domain,
        tags=", ".join(tags or []),
        template=template,
        file_name=file_path.name,
        folder_path=str(file_path.parent),
        content=content[:50000],
    )
    response = CLIENT.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return response.text


# ════════════════════════════════════════════════════════
# wiki ファイル保存
# ════════════════════════════════════════════════════════

def suggest_wiki_filename(file_path: Path) -> str:
    """ファイル名からwikiファイル名を推定する（英小文字・アンダースコア）"""
    stem = file_path.stem
    # 日付パターンを保持しつつ、日本語・記号を除去
    stem = re.sub(r"[^\w\s\-]", "_", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_").lower()
    # ASCII以外を除去
    stem = re.sub(r"[^\x00-\x7F]", "", stem).strip("_")
    if not stem:
        stem = "wiki_" + hashlib.md5(file_path.name.encode()).hexdigest()[:8]
    return stem + ".md"


def save_wiki(wiki_content: str, dest_dir: Path, filename: str) -> Path:
    """wiki Markdown をファイルに保存する"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    wiki_path = dest_dir / filename

    # 同名ファイルが存在する場合は _v2, _v3 を付与
    if wiki_path.exists():
        base = wiki_path.stem
        i = 2
        while wiki_path.exists():
            wiki_path = dest_dir / f"{base}_v{i}.md"
            i += 1

    wiki_path.write_text(wiki_content, encoding="utf-8")
    return wiki_path


# ════════════════════════════════════════════════════════
# processed-sources.yaml 更新
# ════════════════════════════════════════════════════════

def compute_md5(file_path: Path) -> str:
    """ファイルの MD5 ハッシュを計算する"""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def to_personal_relative(abs_path: Path) -> str:
    """絶対パスを 00personal 相対パス（スラッシュ区切り）に変換する"""
    return abs_path.relative_to(PERSONAL_ROOT).as_posix()


def to_kb_relative(abs_path: Path) -> str:
    """絶対パスを KnowledgeBase 相対パス（スラッシュ区切り）に変換する"""
    return abs_path.relative_to(KB_ROOT).as_posix()


def update_processed_sources(source_path: Path, wiki_path: Path) -> None:
    """processed-sources.yaml に新しいレコードを追記する"""
    record = {
        "source_path": to_personal_relative(source_path),
        "wiki_path": to_kb_relative(wiki_path),
        "file_hash": compute_md5(source_path),
        "processed_date": TODAY,
        "index_registered": True,
        "binary_moved": "skipped",
        "source_deleted": False,
    }

    # 既存の YAML を読み込む
    if PROCESSED_PATH.exists():
        existing = PROCESSED_PATH.read_text(encoding="utf-8")
    else:
        existing = ""

    # YAML形式でレコードを追記
    new_record = yaml.dump(
        [record],
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    # リスト形式の先頭 "- " を維持しつつ追記
    with open(PROCESSED_PATH, "a", encoding="utf-8") as f:
        f.write("\n" + new_record)

    print(f"📋 processed-sources.yaml を更新しました")


# ════════════════════════════════════════════════════════
# メイン処理
# ════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Gemini API を使って wiki Markdown を生成する")
    parser.add_argument("file_path", help="処理対象ファイルのパス（xlsx/pptx/pdf）")
    # スタンドアロン用
    parser.add_argument("--dest",    default=None,  help="wiki保存先（KnowledgeBase相対パス）例: kyorindo/it-systems/")
    parser.add_argument("--dry-run", action="store_true", help="ファイル保存・YAML更新をせず出力のみ確認")
    # スキル統合用（--body-only）
    parser.add_argument("--body-only",      action="store_true", help="本文のみ stdout に出力（write-wiki.md統合用）")
    parser.add_argument("--wiki-type",      default="reference", help="wiki_type（analyze.mdの分類結果）")
    parser.add_argument("--title",          default="",          help="タイトル候補（analyze.mdの分類結果）")
    parser.add_argument("--scope",          default="",          help="スコープ（kyorindo等）")
    parser.add_argument("--domain",         default="",          help="ドメイン（cx/it-systems等）")
    parser.add_argument("--tags",           default="",          help="タグ（カンマ区切り）")
    parser.add_argument("--converted-text", default="",          help="事前抽出済みテキスト（省略時はファイルから抽出）")
    args = parser.parse_args()

    file_path = Path(args.file_path).resolve()

    # ── バリデーション ────────────────────────────────────
    if not file_path.exists():
        print(f"❌ ファイルが見つかりません: {file_path}", file=sys.stderr)
        sys.exit(1)

    ext = file_path.suffix.lower()
    if ext not in (".xlsx", ".pptx", ".pdf"):
        print(f"❌ 未対応の形式です（xlsx/pptx/pdf のみ対応）: {ext}", file=sys.stderr)
        sys.exit(1)

    # ── テキスト抽出 ─────────────────────────────────────
    if args.converted_text:
        # 事前抽出済みテキストを使用（convert-binary.md の結果を再利用）
        content = args.converted_text
        if not args.body_only:
            print(f"📄 事前抽出テキストを使用: {len(content):,} 文字")
    else:
        if not args.body_only:
            print(f"📄 テキスト抽出中: {file_path.name}")
        try:
            content = extract_text(file_path)
        except Exception as e:
            print(f"❌ テキスト抽出失敗: {e}", file=sys.stderr)
            sys.exit(1)

        if not content.strip():
            content = f"ファイル名: {file_path.name}\nフォルダ: {file_path.parent.name}"
            if not args.body_only:
                print("⚠️  テキスト抽出不可。ファイル名から内容を推定します。")

        if not args.body_only:
            print(f"   抽出文字数: {len(content):,} 文字")

    # ════════════════════════════════════════════════════
    # --body-only モード（write-wiki.md スキル統合用）
    # Front-matterなし・本文のみを stdout に出力して終了
    # ════════════════════════════════════════════════════
    if args.body_only:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        try:
            body = generate_wiki_body(
                file_path=file_path,
                content=content,
                wiki_type=args.wiki_type,
                title=args.title,
                destination=args.dest or "",
                scope=args.scope,
                domain=args.domain,
                tags=tags,
            )
        except Exception as e:
            print(f"❌ Gemini API エラー: {e}", file=sys.stderr)
            sys.exit(1)
        # 本文のみを stdout に出力（write-wiki.md が受け取る）
        sys.stdout.reconfigure(encoding="utf-8")
        print(body)
        return

    # ════════════════════════════════════════════════════
    # スタンドアロンモード（通常 / dry-run）
    # ════════════════════════════════════════════════════
    try:
        wiki_content = generate_wiki(file_path, content)
    except Exception as e:
        print(f"❌ Gemini API エラー: {e}")
        sys.exit(1)

    # ── dry-run モード ───────────────────────────────────
    if args.dry_run:
        print("\n" + "═" * 60)
        print("【DRY-RUN】生成されたwiki内容（保存はしません）:")
        print("═" * 60)
        print(wiki_content)
        return

    # ── 保存先の決定 ─────────────────────────────────────
    if args.dest:
        dest_dir = KB_ROOT / args.dest.strip("/")
    else:
        # デフォルト: KnowledgeBase/_inbox_gemini/ に保存（手動で移動）
        dest_dir = KB_ROOT / "_inbox_gemini"
        print(f"⚠️  --dest 未指定のため {dest_dir} に保存します")

    filename = suggest_wiki_filename(file_path)

    # ── ファイル保存 ─────────────────────────────────────
    wiki_path = save_wiki(wiki_content, dest_dir, filename)
    print(f"✅ wiki保存完了: {wiki_path}")

    # ── processed-sources.yaml 更新 ─────────────────────
    try:
        update_processed_sources(file_path, wiki_path)
    except Exception as e:
        print(f"⚠️  YAML更新失敗（手動で追記してください）: {e}")

    print("\n🎉 完了!")
    print(f"   ソース : {to_personal_relative(file_path)}")
    print(f"   wiki   : {to_kb_relative(wiki_path)}")


if __name__ == "__main__":
    main()
