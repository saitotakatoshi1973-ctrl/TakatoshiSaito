# batch-inbox.md — フォルダ一括wiki化スキル

## 概要

指定フォルダのファイルを `processed-sources.yaml` と照合し、
未処理・内容更新・部分失敗のファイルだけを `_inbox/` にコピーして wiki 化します。
処理済みチェックにより、同じファイルを二重処理しません。

---

## 起動方法

誤発動防止のため、呼びかけには必ず **「wiki」** を含めてください。

| 呼びかけ例 | recursive | wiki_filter | 説明 |
|-----------|-----------|-------------|------|
| `「03_CX推進/01_戦略/ をwikiバッチ処理して」` | false | false | 直下のみ・全件 |
| `「05_会議・経営/経営会議/ をwiki一括化して」` | false | false | 直下のみ・全件 |
| `「03_CX推進/ をサブフォルダも含めてwikiバッチ処理して」` | true | false | 再帰・全件 |
| `「01_IT/ をサブフォルダも含めてwikiバッチ処理して。wiki化価値があるものだけ対象にして」` | true | true | 再帰・LLM事前スクリーニング |
| `「wiki batch 09_InformationOrganization/ --recursive --filter」` | true | true | 再帰・LLM事前スクリーニング |

> ⚠️ 「バッチ処理して」「一括化して」など **「wiki」を含まない呼びかけは本スキルを起動しない**。

### 入力パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `target_dir` | ✅ | — | 00personal 相対パス または 絶対パス |
| `recursive` | — | `false` | サブフォルダも再帰的に処理するか |
| `file_types` | — | `pptx,xlsx,pdf,md,txt` | 対象拡張子（カンマ区切り） |
| `max_files` | — | `10` | 1回の処理上限件数（未処理+再処理の合計） |
| `wiki_filter` | — | `false` | LLM事前スクリーニングで低価値ファイルを除外するか |
| `wiki_score_threshold` | — | `6` | wiki_filter 有効時の採用スコア下限（0〜10） |
| `wiki_detail_level` | — | `"summary"` | wikiの詳細度。`"summary"`（箇条書き中心・短め）/ `"full"`（全テンプレート・詳細） |
| `batch_auto_classify` | — | `true` | `true` = 信頼度 < 6 でも自動進行しレビューリストに記録。`false` = 従来通りユーザー確認で停止 |

---

## 共通設定

```python
import os
import re
import yaml
import hashlib
import shutil
import ctypes
import time
from datetime import date

PERSONAL_ROOT  = r"C:\Users\takatoshi-saito\OneDrive\00personal"
KB_ROOT        = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"
INBOX_DIR      = os.path.join(KB_ROOT, "_inbox")
PROCESSED_PATH = os.path.join(KB_ROOT, "_system", "processed-sources.yaml")

# 除外フォルダパターン（personal-rules.md の searchable=false ルールに準拠）
EXCLUDE_PATTERN = re.compile(
    r"(^old$|^旧_|_nomal$|_仕掛$|_archive$|^アーカイブ$)",
    re.IGNORECASE
)
DEFAULT_FILE_TYPES = {"pptx", "xlsx", "pdf", "md", "txt"}


def is_cloud_only(path: str) -> bool:
    """
    OneDrive Files-on-Demand のクラウド専用ファイルかどうかを判定する。
    ローカルにダウンロードされていないファイルは True を返す。
    Windows 以外の環境では常に False を返す。
    """
    try:
        FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000  # クラウド専用（要求時取得）
        FILE_ATTRIBUTE_OFFLINE               = 0x1000   # オフライン（未ダウンロード）
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
            return False
        return bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_OFFLINE))
    except Exception:
        return False  # 判定失敗時は処理対象として扱う


def hydrate_cloud_file(path: str, timeout: int = 300, wait: int = 5) -> bool:
    """
    OneDrive クラウド専用ファイルをローカルにダウンロードする。
    ファイルを少量読み込むことで Files-on-Demand の取得を開始し、
    クラウド専用属性が外れるまで待機する。
    成功: True / 失敗: False
    """
    if not is_cloud_only(path):
        return True

    try:
        with open(path, "rb") as f:
            f.read(1)  # OneDrive のダウンロードを開始する
    except Exception:
        return False

    start = time.time()
    while time.time() - start < timeout:
        if not is_cloud_only(path):
            return True
        time.sleep(wait)

    return not is_cloud_only(path)
```

---

## バッチ実行前の一括読み込み（クレジット削減）

バッチ処理を開始する前に、以下のファイルを **1回だけ** 読み込む。
処理ループ内では再読み込みしない。

```python
# ── サブスキル（1回だけ読んでメモリに保持）──
# Read: wiki-agent/skills/convert-binary.md
# Read: wiki-agent/skills/analyze.md
# Read: wiki-agent/skills/place-wiki.md
# ※ write-wiki.md は batch_write_wiki=True のため呼び出し不要（analyze.md が統合実行）

# ── 分類ルール（全ファイル共通）──
# Read: KnowledgeBase/_system/SCHEMA.md               ← full版（1回だけ読む）
# Read: KnowledgeBase/_system/learning/classification-hints.md

# ── ② スリム SCHEMA を動的生成（SCHEMA.md 読み込み直後に実行）──
# slim_schema = generate_slim_schema(schema_content)
# → analyze.md の STEP 4 では full SCHEMA.md の代わりに slim_schema を参照
# → SCHEMA.md が更新されても次回バッチ時に自動追従（別ファイル管理不要）
```

> **重要**: これらを `Skill()` ツールで呼び出さないこと。
> `Skill()` は呼ぶたびにスキルファイル全文をコンテキストに注入するため、
> バッチ処理でファイル数分だけクレジットを消費する。
> 代わりに `Read` ツールで1回読み込み、以降はメモリ上の内容を再利用する。

---

## スリム SCHEMA 動的生成（② クレジット削減）

SCHEMA.md を読み込んだ直後に `generate_slim_schema()` を呼び出す。
full SCHEMA.md（~2200トークン）の代わりに slim 版（~900トークン）を
analyze.md STEP 4 に渡すことで、1ファイルあたりの分類コストを約60%削減する。
SCHEMA.md が更新されれば次回バッチ時に自動追従するため、別ファイル管理は不要。

```python
import re
from datetime import date

def generate_slim_schema(schema_content: str) -> str:
    """
    SCHEMA.md のコードブロック内 ASCII ツリーを解析し、
    「フルパス : 説明1行」の一覧を動的生成する。

    入力: SCHEMA.md の全文
    出力: フォルダパス一覧 + vendor/research 境界ルール（~900トークン程度）

    解析対象:
      - 「KnowledgeBase/」で始まるブロック → トップカテゴリ一覧
      - 各カテゴリ名で始まるブロック（kyorindo/ など）→ サブカテゴリ一覧
    """
    result = [
        f"# KnowledgeBase フォルダパス一覧（SCHEMA.md から {date.today()} 自動生成）",
        "",
    ]

    # コードブロック（```...```）を全て抽出
    blocks = re.findall(r'```\n?(.*?)```', schema_content, re.DOTALL)

    for block in blocks:
        lines = block.strip().split('\n')
        if not lines:
            continue
        first = lines[0].strip()

        # ── パターン A: KnowledgeBase/ ブロック（トップカテゴリ一覧）──
        if first == 'KnowledgeBase/':
            for line in lines[1:]:
                m = re.match(
                    r'^[├└]──\s+([a-zA-Z0-9_-]+/)\s*(?:#\s*(.+))?$',
                    line.strip()
                )
                if m and m.group(2):
                    result.append(f"{m.group(1):<50} {m.group(2).strip()}")
            result.append("")
            continue

        # ── パターン B: カテゴリブロック（kyorindo/ など）──
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*/$', first):
            continue   # _system/ など対象外

        top = first.rstrip('/')
        path_stack: list[tuple[str, int]] = [(top, 0)]

        for line in lines[1:]:
            # ├── または └── で始まるフォルダ行（/ で終わる）を抽出
            m = re.match(
                r'^((?:│   |    )*)[├└]──\s+([a-zA-Z0-9_.{}\-]+/)\s*(?:#\s*(.+))?',
                line
            )
            if not m:
                continue

            indent_s    = m.group(1)           # 例: "│   │   "
            folder_name = m.group(2).rstrip('/')
            comment     = (m.group(3) or "").strip()
            depth       = len(indent_s) // 4 + 1  # 4文字/レベル

            # path_stack を現在の深さに合わせてトリム
            path_stack = [(p, d) for p, d in path_stack if d < depth]
            path_stack.append((folder_name, depth))

            full_path = '/'.join(p for p, d in path_stack) + '/'

            if comment:
                result.append(f"{full_path:<50} {comment}")
            # コメントなしはパス構築用にスタックに保持するが出力はしない

    # vendor / research 境界ルール（SCHEMA.md セクション4を要約）
    result.extend([
        "",
        "## vendor / research 境界ルール",
        "- ベンダー名で検索しそう（契約・見積・打ち合わせ記録）→ vendor/{vendor-name}/",
        "- テーマ・技術名・講義内容で検索しそう → research/ または ai-dx/",
    ])

    return '\n'.join(result)


# バッチ開始時に1回だけ実行:
# schema_content = open(SCHEMA_PATH, encoding='utf-8').read()
# slim_schema    = generate_slim_schema(schema_content)
```

---

## STEP 1: フォルダをスキャンする

```python
def scan_target_dir(
    target_dir: str,
    recursive: bool,
    file_types: set[str],
) -> dict:
    """
    target_dir を走査して対象ファイルのリストを返す。
    - 除外パターンに合致するフォルダはスキップ。
    - OneDrive クラウド専用ファイル（未ダウンロード）は cloud_only に分類。
    - 最終更新日時の古い順で返す。

    戻り値: {
        "local":      list[str],  # ローカルにあるファイル（処理対象）
        "cloud_only": list[str],  # クラウド専用。後続でファイル名から対象判定する
    }
    """
    local      = []
    cloud_only = []

    if recursive:
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if not EXCLUDE_PATTERN.match(d)]
            for fname in files:
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in file_types:
                    full = os.path.join(root, fname)
                    if is_cloud_only(full):
                        cloud_only.append(full)
                    else:
                        local.append(full)
    else:
        for entry in os.scandir(target_dir):
            if entry.is_file():
                ext = entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
                if ext in file_types:
                    if is_cloud_only(entry.path):
                        cloud_only.append(entry.path)
                    else:
                        local.append(entry.path)

    # 最終更新日時の古い順（先に作成されたものを優先処理）
    local.sort(key=lambda p: os.path.getmtime(p))
    return {"local": local, "cloud_only": cloud_only}
```

---

## STEP 1.5: クラウド専用ファイルをファイル名で事前判定・ダウンロードする

`scan_target_dir()` で `cloud_only` に分類されたファイルは、本文を読めないため、
**ファイル名・フォルダパスだけ**で wiki 化対象かを判定する。

対象と判定したファイルだけを OneDrive からローカルへダウンロードし、
成功したものは通常の `local` ファイルと同じ処理フローに合流させる。

### LLM へのクラウド専用ファイル判定指示

```
以下は OneDrive 上には存在するが、まだローカルにダウンロードされていないファイル一覧です。
ファイル名とフォルダパスのみから、それぞれの「wikiナレッジとしての価値」を 0〜10 で評価してください。

【評価基準】
高評価（7〜10）:
  - 状況・一覧・台数・導入状況などの管理資料
  - 戦略・方針・設計・仕様を記した資料
  - 業界動向・競合情報・調査レポート
  - 会議記録・進捗サマリー
  - 現在も参照価値がある技術情報（構成図・アーキテクチャ等）
  - 見積書・相見積、発注書、納品書など調達履歴として価値がある資料

低評価（0〜4）:
  - 古い機器マニュアル・製品PDF単体
  - スキャン画像・申請書・テンプレート・POP
  - ファイル名から内容が明らかに低価値、または用途不明なもの

【ファイル一覧】
{cloud_only_files をパスとともに列挙}

【出力形式（YAML）】
- path: "ファイル絶対パス"
  score: 8
  decision: "download"   # download | skip
  reason: "（1行で理由）"
```

### クラウド専用ファイルの処理

```python
def screen_cloud_files_by_name(
    cloud_files: list[str],
    score_threshold: int = 6,
    batch_size: int = 30,
) -> dict:
    """
    クラウド専用ファイルをファイル名・フォルダパスのみで評価する。

    戻り値: {
        "download_targets": list[dict],  # ダウンロード対象（score >= threshold）
        "skipped": list[dict],           # 低スコアのためスキップ
    }
    """
    download_targets = []
    skipped = []

    for i in range(0, len(cloud_files), batch_size):
        batch = cloud_files[i:i + batch_size]
        scores = llm_score_cloud_file_names(batch)

        for item in scores:
            if item["score"] >= score_threshold and item.get("decision") == "download":
                download_targets.append(item)
            else:
                skipped.append(item)

    return {"download_targets": download_targets, "skipped": skipped}


def hydrate_selected_cloud_files(download_targets: list[dict]) -> dict:
    """
    判定済みのクラウド専用ファイルをローカルにダウンロードする。

    戻り値: {
        "downloaded": list[str],  # ローカル化成功。通常処理へ合流
        "failed": list[dict],     # ダウンロード失敗
    }
    """
    downloaded = []
    failed = []

    for item in download_targets:
        path = item["path"]
        ok = hydrate_cloud_file(path)
        if ok:
            downloaded.append(path)
        else:
            failed.append({
                "path": path,
                "score": item.get("score"),
                "reason": item.get("reason", "ダウンロード失敗"),
            })

    return {"downloaded": downloaded, "failed": failed}
```

### クラウド専用ファイルの扱い

| 判定 | 処理 |
|------|------|
| score >= threshold かつ decision: download | OneDriveからローカルにダウンロードし、成功したら通常処理へ合流 |
| score < threshold または decision: skip | wiki化対象外としてスキップ |
| ダウンロード失敗 | エラーではなく `cloud_download_failed` として結果に記録し、次回再処理可能にする |

---

## STEP 1.6: wiki化価値をスクリーニングする（wiki_filter=true 時のみ）

`wiki_filter=true` の場合、まずルールベースで除外し、残ったファイルのみ LLM スコアリングを行う。
これにより LLM 呼び出し回数を削減できる。

### 1.6-A: ルールベース事前フィルタ（LLM 不要・即時判定）

```python
import re

# 明らかに低価値なファイルをLLMを使わずに除外するパターン
EXCLUDE_NAME_PATTERNS = [
    re.compile(r'^img[-_]\w+\.(pdf|png|jpg|jpeg)', re.IGNORECASE),  # スキャン画像PDF
    re.compile(r'^~\$'),                                              # Officeテンポラリ
    re.compile(r'テンプレート|template', re.IGNORECASE),              # テンプレート類
    re.compile(r'特売\s*POP|pop素材', re.IGNORECASE),                 # POPデザイン
    re.compile(r'^ReadMe', re.IGNORECASE),                            # README
    re.compile(r'サイズ見本|見本帳'),                                  # 見本類
    re.compile(r'申請書[\s_]*(様式|フォーム)'),                        # 申請書フォーム
]

def rule_based_filter(files: list[str]) -> dict:
    """
    ファイル名パターンマッチングで即時除外する（LLM不要）。
    戻り値: { "passed": list[str], "excluded": list[dict] }
    """
    passed   = []
    excluded = []

    for f in files:
        fname = os.path.basename(f)
        matched = next(
            (p.pattern for p in EXCLUDE_NAME_PATTERNS if p.search(fname)),
            None
        )
        if matched:
            excluded.append({"path": f, "reason": f"ルールベース除外: {matched}"})
        else:
            passed.append(f)

    return {"passed": passed, "excluded": excluded}
```

ルールベースフィルタ後、残ったファイルのみ LLM スコアリングへ進む。

### 1.6-B: LLM スコアリング（wiki_filter=true かつルールで残ったファイルのみ）

`wiki_filter=true` の場合、ファイル名とフォルダパスをもとに LLM が wiki 化価値を
0〜10 でスコアリングし、`wiki_score_threshold`（デフォルト6）未満のファイルを除外する。

### LLM へのスコアリング指示

```
以下のファイル一覧について、それぞれの「wikiナレッジとしての価値」を 0〜10 で評価してください。
ファイル名とフォルダパスのみから判断します。

【評価基準】
高評価（7〜10）:
  - 状況・一覧・台数・導入状況などの管理資料
  - 戦略・方針・設計・仕様を記した資料
  - 業界動向・競合情報・調査レポート
  - 会議記録・進捗サマリー
  - 現在も参照価値がある技術情報（構成図・アーキテクチャ等）
  - 見積書・相見積（ベンダー比較・価格情報として価値あり）
  - 発注書・納品書（調達履歴として価値あり）

中評価（5〜6）:
  - セットアップ手順書・運用マニュアル（現行機器・現行システムのもの）
  - 比較的新しい（3年以内）の情報資料

低評価（0〜4）:
  - 古い機器のマニュアル・仕様書（製品マニュアルPDF単体）
  - スキャンした申請書・承認書類（内容が読み取れないもの）
  - 特売POP・フォームテンプレート・サイズ見本
  - 設定値のみの技術PDFで文脈がないもの
  - ファイル名から内容が明らかに低価値（img-xxxxxx.pdf 等）

【ファイル一覧】
{files をパスとともに列挙}

【出力形式（YAML）】
- path: "ファイル絶対パス"
  score: 8
  reason: "（1行で理由）"
```

### スクリーニング処理

```python
def pre_screen_wiki_value(
    files: list[str],
    score_threshold: int = 6,
    batch_size: int = 30,
) -> dict:
    """
    ① ルールベースで即時除外 → ② 残りを LLM スコアリング の2段階で処理する。
    LLM トークン節約のため batch_size 件ずつ分割して処理する。

    戻り値: {
        "passed":   list[str],   # 採用ファイル（rule通過 + score >= threshold）
        "filtered": list[dict]   # 除外ファイル（rule除外 + LLM低スコア）
    }
    """
    # ① ルールベース事前フィルタ（LLM不要）
    rule_result = rule_based_filter(files)
    filtered    = rule_result["excluded"]   # ルールで除外済み
    candidates  = rule_result["passed"]     # LLMスコアリング対象

    passed = []

    # ② LLMスコアリング（ルールを通過したファイルのみ）
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        scores = llm_score_wiki_value(batch)   # 上記プロンプトで呼び出し

        for item in scores:
            if item["score"] >= score_threshold:
                passed.append(item["path"])
            else:
                filtered.append(item)

    return {"passed": passed, "filtered": filtered}
```

### スクリーニング結果の表示

```
🔍 wiki_filter スクリーニング結果

スキャン: 72件 → ローカル: 68件 / ☁️クラウド専用: 4件
         クラウド判定: ダウンロード対象2件 / スキップ2件
         ダウンロード成功: 2件 / 失敗0件
         採用: 10件 / 除外: 60件（うちキャッシュ済みスキップ: 45件）③

【採用（score ≥ 6）】
  ✅ KP-20プリンタの状況説明資料2018.xlsx         [score: 8] 状況管理資料
  ✅ ラベルプリンタ導入状況資料 2017.xlsx          [score: 7] 導入状況一覧
  ✅ iPhone台数.xlsx                              [score: 8] 台数管理資料
  ✅ TV会議システム5拠点202003.pdf                 [score: 7] システム構成情報
  ✅ KP-30_データ変換の流れ.pptx                  [score: 8] 技術仕様・フロー説明
  ✅ レジロール各店発注実績_20240703-20250328.xlsx  [score: 6] 実績データ（直近）
  ✅ WebEX面会設定方法.pdf                        [score: 6] 現行システム手順書
  ✅ TV会議システム2拠点.pdf                      [score: 6] システム構成情報
  ☁️→✅ 重要システム構成図_2024.pdf                [score: 8] クラウドから取得

【除外（score < 6）の主な理由】
  ❌ 古いBHT操作マニュアル（5件）: 旧機器PDF
  ❌ 特売POP_PDF（6件）: テンプレートPDF
  ❌ img-xxxxxx.pdf 等（内容不明スキャンPDF）
  ...

採用した 8 件で処理を進めますか？
```

---

## STEP 2: processed-sources.yaml と照合する

```python
def compute_file_hash(file_path: str) -> str:
    """
    ファイルの MD5 ハッシュを返す。
    OneDrive Files-on-Demand でクラウド専用のファイルは読み取り失敗の可能性があるため、
    失敗時は空文字列を返す（未処理扱いで続行）。
    """
    try:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def load_processed_sources() -> dict[str, dict]:
    """
    processed-sources.yaml を読み込み、
    source_path をキーとする辞書を返す。
    ファイルが存在しない場合は空辞書を返す。
    """
    if not os.path.exists(PROCESSED_PATH):
        return {}
    try:
        with open(PROCESSED_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        # リスト形式（コメントのみの場合 [] が返る）
        if isinstance(data, list):
            return {r["source_path"]: r for r in data if r and r.get("source_path")}
        return {}
    except Exception:
        return {}


def to_personal_relative(abs_path: str) -> str:
    """絶対パスを 00personal/ 相対パスに変換する（スラッシュ区切り）"""
    return os.path.relpath(abs_path, PERSONAL_ROOT).replace("\\", "/")


def filter_files(files: list[str]) -> dict:
    """
    processed-sources.yaml と照合して以下に分類する:
      new     : 未記録            → 処理対象
      updated : ハッシュ変化       → 再処理対象（wikiを上書き更新）
      partial : 部分失敗           → 再処理対象
      done    : 完全成功済み       → スキップ

    partial 判定条件:
      - index_registered が False
      - binary_moved が False（"skipped" は正常終了なので除外）
    """
    processed = load_processed_sources()
    result = {"new": [], "updated": [], "partial": [], "done": [], "cached_texts": {}}

    for abs_path in files:
        rel_path = to_personal_relative(abs_path)
        record   = processed.get(rel_path)

        if record is None:
            result["new"].append(abs_path)
            continue

        current_hash = compute_file_hash(abs_path)
        stored_hash  = record.get("file_hash", "")

        if stored_hash and current_hash and current_hash != stored_hash:
            # ファイル内容が変化 → 再処理（wikiを最新内容で上書き）
            result["updated"].append(abs_path)
        elif (
            not record.get("index_registered", False)
            or record.get("binary_moved") is False
        ):
            # 部分失敗 → 再処理
            result["partial"].append(abs_path)
            # ① ハッシュ一致 = ファイル内容は同じ → 変換テキストキャッシュを再利用
            if record.get("extracted_text"):
                result["cached_texts"][abs_path] = record["extracted_text"]
        else:
            # 完全成功済み → スキップ
            result["done"].append(abs_path)

    return result
```

---

## STEP 2.5: 削除されたソースファイルを検出する

指定フォルダに関連する `processed-sources.yaml` のレコードのうち、
現在のスキャン結果に存在しないものを「削除済み」として検出する。
`source_deleted: true` 設定済みのレコードはスキップ（既知の削除）。

```python
def detect_deleted_sources(target_dir: str, current_files: list[str]) -> list[dict]:
    """
    target_dir 配下のレコードのうち、現在のスキャン結果に存在しないものを返す。
    """
    target_rel     = to_personal_relative(target_dir).rstrip("/")
    processed      = load_processed_sources()
    current_rel_set = {to_personal_relative(f) for f in current_files}

    deleted = []
    for source_path, record in processed.items():
        # target_dir 配下のレコードのみ対象
        if not source_path.startswith(target_rel + "/"):
            continue
        # 既知の削除はスキップ
        if record.get("source_deleted", False):
            continue
        if source_path not in current_rel_set:
            deleted.append(record)

    return deleted
```

削除が検出された場合、**処理開始前に**ユーザーへ確認する：

```
⚠️ 削除されたソースファイルが見つかりました（{N}件）

  {i}. {source_path}
       → wiki: {wiki_path}

これらのwikiをどうしますか？
  A. wikiを削除する（change_log に記録）
  B. status: outdated に更新して残す（推奨）
  C. 何もしない（次回も同じ警告が出ます）
A / B / C で回答してください:
```

| 選択 | wikiファイル | processed-sources.yaml |
|------|------------|------------------------|
| A. 削除 | ファイルを削除、index から除去 | レコードを削除 |
| B. outdated更新 | Front-matterの `status: outdated` に変更 | `source_deleted: true` を追記 |
| C. 何もしない | そのまま | `source_deleted: true` を追記（次回警告なし） |

---

## STEP 3: 処理予定をユーザーに提示・確認する

```python
def show_preview(
    target_dir: str,
    filtered: dict,
    max_files: int,
    screen_result: dict | None = None,
) -> list[str]:
    """
    処理予定ファイルを表示してユーザーの確認を取る。
    screen_result が渡された場合はスクリーニング統計も表示する。
    確認後、処理対象の絶対パスリストを返す。
    空リストはキャンセル。
    """
    # new / updated / partial を合わせて max_files 件まで
    to_process = (
        filtered["new"] + filtered["updated"] + filtered["partial"]
    )[:max_files]

    # スクリーニング統計（wiki_filter=True 時のみ表示）
    filter_line = ""
    if screen_result is not None:
        total_scanned = len(screen_result["passed"]) + len(screen_result["filtered"])
        filter_line = (
            f"🔍 スクリーニング      :"
            f" {total_scanned}件 → 採用{len(screen_result['passed'])}件"
            f" / 除外{len(screen_result['filtered'])}件\n"
        )

    print(f"""
📂 バッチ処理の準備ができました

対象フォルダ: {to_personal_relative(target_dir)}
────────────────────────────────
{filter_line}🆕 未処理（新規）     : {len(filtered["new"])}件
🔄 内容更新（再処理）  : {len(filtered["updated"])}件
⚠️  部分失敗（再処理）  : {len(filtered["partial"])}件
✅ 処理済み（スキップ） : {len(filtered["done"])}件
────────────────────────────────
今回処理する         : {len(to_process)}件（max_files={max_files}）

【処理予定ファイル】""")

    for i, f in enumerate(to_process, 1):
        label = ""
        if f in filtered["updated"]:
            label = "（内容更新）"
        elif f in filtered["partial"]:
            label = "（再処理）"
        print(f"  {i}. {os.path.basename(f)} {label}")

    if not to_process:
        print("\n処理対象ファイルはありません。")
        return []

    print(f"""
進めますか？
  1. 進める
  2. 上限を変更する（現在: {max_files}件）
  3. キャンセル""")

    # ユーザーの回答に応じて to_process を返す（LLM がユーザー返答を読んで判定）
    return to_process
```

---

## STEP 4〜6: 処理実行

```python
def run_batch(
    to_process: list[str],
    filtered: dict,
    wiki_detail_level:   str       = "summary",
    batch_auto_classify: bool      = True,
    slim_schema:         str|None  = None,    # ② 動的生成スリムSCHEMA
) -> dict:
    """
    to_process の各ファイルを wiki 化する。1ファイルずつ直列で処理する。

    クレジット削減のため batch_mode=True を place-wiki に渡し、
    _overview.md 更新・change_log 追記・index-builder 呼び出しを
    処理ループ内では行わず、後で flush_batch_post_processing() にまとめる。

    batch_auto_classify=True の場合、信頼度 < 6 のファイルも自動進行し
    auto_classified_list に記録する（バッチ後にまとめてレビュー可能）。
    """
    auto_classified = []   # 低信頼度で自動進行したファイルのリスト
    cached_texts = filtered.get("cached_texts", {})  # ① 変換テキストキャッシュ（partial再処理時に再利用）
    results      = []
    skipped      = []
    errors       = []
    # バッチ末尾で一括処理する後処理キュー
    deferred_overviews   = set()   # 更新が必要なフォルダパス（重複排除）
    deferred_changelog   = []      # change_log エントリ（文字列リスト）
    deferred_wiki_paths  = []      # index-builder に渡す wiki パス
    deferred_ps_records  = []      # processed-sources.yaml レコード（一括書き込み用）

    for abs_path in to_process:
        rel_path  = to_personal_relative(abs_path)
        fname     = os.path.basename(abs_path)
        file_hash = compute_file_hash(abs_path)

        # STEP 4: _inbox/ にコピー（原本は 00personal/ に残したまま）
        inbox_copy = _resolve_collision(os.path.join(INBOX_DIR, fname))
        try:
            shutil.copy2(abs_path, inbox_copy)
        except Exception as e:
            errors.append({"file": rel_path, "step": "copy", "error": str(e)})
            continue

        # STEP 5: パイプラインを呼び出す
        # batch_mode=True により place-wiki は overview/changelog/index を
        # 即時実行せず deferred_* リストに積んで返す
        pipeline_input = {
            "file_path":              inbox_copy,
            "original_personal_path": rel_path,
            "file_hash":              file_hash,
            "skip_route_binary":      True,
            "batch_mode":             True,          # ← 後処理を遅延させる
            "wiki_detail_level":      wiki_detail_level,   # ← summary / full
            "batch_auto_classify":    batch_auto_classify, # ← 低信頼度自動進行
            "cached_text":            cached_texts.get(abs_path),  # ① キャッシュヒット時は変換スキップ
            "batch_write_wiki":       True,          # ① analyze + write-wiki を1回のLLM呼び出しに統合
            "slim_schema":            slim_schema,   # ② 動的生成スリムSCHEMA（analyze STEP 4 で使用）
        }
        # ── パイプライン実行順序（batch_write_wiki=True 時）──
        # 1. convert-binary.md  → テキスト抽出（cached_text があればスキップ）
        # 2. analyze.md         → 分類判定 ＋ wiki本文を同時生成（STEP 6 統合モード）
        #    ↳ write-wiki.md の呼び出しはスキップ（analyze.md が wiki_content を出力済み）
        # 3. place-wiki.md      → analyze 統合出力の wiki_content を受け取って配置
        #
        # pipeline_result に期待するフィールド:
        #   status / wiki_path / processed_record / auto_classified / confidence_score / destination
        #   extracted_text: convert-binary の出力テキスト（キャッシュ用・3000文字まで）← ①

        pipeline_result = run_inbox_pipeline(pipeline_input)
        # ↑ convert-binary → analyze → write-wiki → place-wiki（batch_mode）の順に実行

        # STEP 6: _inbox/ のコピーを削除
        try:
            if os.path.exists(inbox_copy):
                os.remove(inbox_copy)
        except Exception:
            pass

        # 低信頼度で自動進行した場合はリストに記録
        if pipeline_result.get("auto_classified"):
            auto_classified.append({
                "file":        rel_path,
                "destination": pipeline_result.get("destination", ""),
                "confidence":  pipeline_result.get("confidence_score", 0),
            })

        # 結果を記録
        if pipeline_result.get("status") == "skip":
            skipped.append({
                "file":   rel_path,
                "reason": pipeline_result.get("reason", "ユーザーがスキップを選択"),
            })
        elif pipeline_result.get("status") == "error":
            errors.append({
                "file":  rel_path,
                "step":  "pipeline",
                "error": pipeline_result.get("reason", "不明なエラー"),
            })
        else:
            wiki_path = pipeline_result.get("wiki_path", "")
            label = "（更新）" if abs_path in filtered.get("updated", []) else ""
            results.append({"file": rel_path, "wiki_path": wiki_path, "label": label})

            # 後処理キューに積む
            dest_dir = os.path.dirname(
                os.path.join(KB_ROOT, wiki_path)
            )
            deferred_overviews.add(dest_dir)
            deferred_changelog.append(
                f"[追加] {wiki_path}" + ("（更新）" if label else "")
            )
            deferred_wiki_paths.append(
                os.path.join(KB_ROOT, wiki_path)
            )
            # processed-sources.yaml レコードもバッファに積む（一括書き込み用）
            if "processed_record" in pipeline_result:
                record = pipeline_result["processed_record"]
                # ① 変換テキストをキャッシュとして保存（3000文字まで）
                # 次回 partial 再処理時に convert-binary をスキップできる
                if "extracted_text" not in record and pipeline_result.get("extracted_text"):
                    record["extracted_text"] = pipeline_result["extracted_text"][:3000]
                deferred_ps_records.append(record)

    return {
        "auto_classified_list": auto_classified,  # バッチ完了後レビュー用
        "status":               "success" if not errors else "partial",
        "processed":            len(results),
        "skipped":              len(skipped),
        "errors":               len(errors),
        "results":              results,
        "skipped_list":         skipped,
        "error_list":           errors,
        # 後処理キュー（flush_batch_post_processing() へ渡す）
        "deferred_overviews":   list(deferred_overviews),
        "deferred_changelog":   deferred_changelog,
        "deferred_wiki_paths":  deferred_wiki_paths,
        "deferred_ps_records":  deferred_ps_records,
    }


def flush_batch_post_processing(
    deferred_overviews:  list[str],
    deferred_changelog:  list[str],
    deferred_wiki_paths: list[str],
    deferred_ps_records: list[dict] | None = None,
) -> dict:
    """
    run_batch() が収集した後処理を一括で実行する。

    ① _overview.md の更新: 影響フォルダごとに1回だけ update-overview.md を呼ぶ
    ② change_log への一括追記: 全エントリを1回のファイル書き込みで追記
    ③ index-builder の一括実行: 全 wiki パスを渡して1回だけ呼ぶ

    これにより、ファイルごとに3回発生していた後処理がまとめて3〜4回になる。
    （processed-sources.yaml 含めると4回）
    """
    flush_errors = []

    # ① _overview.md 一括更新（影響フォルダ数分だけ、append モードで LLM不要）
    for dest_dir in deferred_overviews:
        overview_path = os.path.join(dest_dir, "_overview.md")
        if os.path.exists(overview_path):
            try:
                # そのフォルダに追加された wiki ファイルだけを渡す（差分追記）
                new_files_for_dir = [
                    {
                        "filename": os.path.basename(p),
                        "title":    os.path.basename(p).replace(".md", ""),
                        "status":   "current",
                        "updated":  date.today().strftime("%Y-%m-%d"),
                    }
                    for p in deferred_wiki_paths
                    if os.path.dirname(p) == dest_dir
                ]
                update_overview_run(
                    target_dir = os.path.relpath(dest_dir, KB_ROOT).replace("\\", "/"),
                    mode       = "append",        # LLM不要の差分追記モード
                    new_files  = new_files_for_dir,
                )
            except Exception as e:
                flush_errors.append({"step": "overview", "dir": dest_dir, "error": str(e)})

    # ② change_log 一括追記（1回のファイル書き込み）
    if deferred_changelog:
        try:
            today    = date.today()
            log_path = os.path.join(
                KB_ROOT, "_system",
                f"change_log_{today.strftime('%Y-%m')}.md"
            )
            if not os.path.exists(log_path):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(f"# KnowledgeBase 変更履歴 {today.strftime('%Y年%m月')}\n\n")
            with open(log_path, "a", encoding="utf-8") as f:
                for entry in deferred_changelog:
                    f.write(f"- {today.strftime('%Y-%m-%d')} {entry}\n")
        except Exception as e:
            flush_errors.append({"step": "changelog", "error": str(e)})

    # ③ index-builder 一括実行（全 wiki パスをまとめて渡す）
    if deferred_wiki_paths:
        try:
            index_builder_run(mode="batch_add", file_paths=deferred_wiki_paths)
        except Exception as e:
            flush_errors.append({"step": "index_builder", "error": str(e)})

    # ④ processed-sources.yaml 一括書き込み（O(n²) → O(1) に削減）
    if deferred_ps_records:
        try:
            upsert_all_processed_records(deferred_ps_records)
        except Exception as e:
            flush_errors.append({"step": "processed_sources", "error": str(e)})

    return {
        "status": "success" if not flush_errors else "partial",
        "errors": flush_errors,
    }


def upsert_all_processed_records(records: list[dict]) -> None:
    """
    processed-sources.yaml を1回だけ読み込み、バッファの全レコードを
    upsert して1回だけ書き込む。バッチ処理時の O(n²) I/O を O(1) に削減。
    """
    existing = []
    if os.path.exists(PROCESSED_PATH):
        try:
            with open(PROCESSED_PATH, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or []
        except Exception:
            existing = []

    # source_path をキーにして upsert
    existing_map = {r["source_path"]: i for i, r in enumerate(existing) if r.get("source_path")}
    for rec in records:
        sp = rec.get("source_path")
        if sp and sp in existing_map:
            existing[existing_map[sp]] = rec   # 上書き
        else:
            existing.append(rec)               # 追加

    for attempt in range(3):
        try:
            with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(5)
            else:
                raise RuntimeError("processed-sources.yaml への一括書き込みに失敗しました")


def load_filter_rejection_cache() -> dict[str, str]:
    """
    wiki_filter で過去にスキップ判定されたファイルを {rel_path: file_hash} で返す。
    ハッシュが一致する場合のみキャッシュ有効（ファイル更新時は再スコアリング）。
    """
    processed = load_processed_sources()
    return {
        sp: record.get("file_hash", "")
        for sp, record in processed.items()
        if record.get("wiki_filter_result") == "skip"
    }


def save_filter_rejections(filtered_items: list[dict]) -> None:
    """
    wiki_filter で新たに除外判定したファイルを processed-sources.yaml にキャッシュとして記録する。
    次回バッチ時、ハッシュが一致するファイルは LLM スコアリングをスキップできる。

    filtered_items: pre_screen_wiki_value の "filtered" リスト
    ルールベース除外（score フィールドなし）はスキップする。
    """
    today   = date.today().strftime("%Y-%m-%d")
    records = []
    for item in filtered_items:
        if "score" not in item:
            continue   # ルールベース除外はキャッシュ不要（次回もルールで除外される）
        path = item.get("path", "")
        if not path:
            continue
        rel_path  = to_personal_relative(path)
        file_hash = compute_file_hash(path)
        records.append({
            "source_path":        rel_path,
            "file_hash":          file_hash,
            "wiki_filter_result": "skip",
            "wiki_filter_score":  item.get("score", 0),
            "wiki_filter_date":   today,
            "wiki_path":          None,
            "index_registered":   False,
            "binary_moved":       "skipped",
        })
    if records:
        upsert_all_processed_records(records)


def _resolve_collision(dest_path: str) -> str:
    """同名ファイルが _inbox/ に存在する場合 _v2/_v3 を付与する"""
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(dest_path)
    version = 2
    while os.path.exists(f"{base}_v{version}{ext}"):
        version += 1
    return f"{base}_v{version}{ext}"
```

---

## STEP 7: 完了レポートを出力する

```
✅ バッチ処理完了

対象フォルダ: 03_CX推進/01_戦略/
────────────────────────────
クラウド専用:  4件
  - ダウンロード対象: 2件
  - ダウンロード成功: 2件
  - スキップ: 2件
  - 失敗: 0件
処理成功:      7件
内容更新:      1件（wiki を上書き更新）
スキップ:      1件（ユーザーが分類確認でスキップ）
エラー:        1件
────────────────────────────
【処理済みファイル】
  ✅ CX戦略2026_v3.pptx → kyorindo/cx/strategy/CX戦略2026_20260502.md
  🔄 ロードマップ_20260416.pptx → kyorindo/cx/strategy/CX_roadmap_20260416.md（更新）
  ...

【スキップ】
  ⏭️ CX方針メモ.txt → ユーザーがスキップを選択

【エラー（手動確認）】
  ❌ 旧_CX方針.pptx → convert-binary 失敗（パスワード保護の可能性）

【低信頼度で自動分類（要レビュー）】
  ⚠️ 体制図220826.pptx → kyorindo/organization/ [信頼度: 4]
  → 誤っている場合は手動で移動してください

次回「wikiバッチ処理して」で同じフォルダを指定すると、未処理・更新されたファイルのみ対象になります。
処理状態: KnowledgeBase/_system/processed-sources.yaml
```

> `auto_classified_list` が空の場合、「低信頼度で自動分類」セクションは表示しない。

---

## メイン実行フロー

```python
def run(
    target_dir: str,
    recursive: bool      = False,
    file_types: set[str] = DEFAULT_FILE_TYPES,
    max_files: int        = 20,              # ← 10→20（⑨の変更）
    wiki_filter: bool     = False,
    wiki_score_threshold: int = 6,
    wiki_detail_level: str    = "summary",   # ← ⑤で追加
    batch_auto_classify: bool = True,        # ← ⑦で追加
) -> dict:
    # 絶対パスに正規化
    if not os.path.isabs(target_dir):
        target_dir = os.path.join(PERSONAL_ROOT, target_dir)

    if not os.path.isdir(target_dir):
        return {"status": "error", "message": f"フォルダが見つかりません: {target_dir}"}

    # ② スリム SCHEMA を動的生成（バッチ開始時に1回だけ）
    # SCHEMA.md を読み込み → フォルダパス一覧を抽出 → slim_schema として保持
    # analyze.md STEP 4 では full SCHEMA.md の代わりにこれを参照する
    SCHEMA_PATH = os.path.join(KB_ROOT, "_system", "SCHEMA.md")
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_content = f.read()
        slim_schema = generate_slim_schema(schema_content)
    except Exception:
        slim_schema = None   # 生成失敗時は analyze.md が full SCHEMA.md を参照

    # STEP 1: スキャン（クラウド専用ファイルは後続で事前判定）
    scan_result = scan_target_dir(target_dir, recursive, file_types)
    all_files   = scan_result["local"]        # ローカルにあるファイル
    cloud_files = scan_result["cloud_only"]   # ☁️ クラウド専用ファイル

    cloud_result = {"download_targets": [], "skipped": []}
    hydrate_result = {"downloaded": [], "failed": []}

    # STEP 1.5: クラウド専用ファイルはファイル名・パスだけで対象判定し、
    # 対象であればローカルにダウンロードして通常処理へ合流させる
    if cloud_files:
        cloud_result = screen_cloud_files_by_name(
            cloud_files,
            score_threshold=wiki_score_threshold,
        )
        hydrate_result = hydrate_selected_cloud_files(cloud_result["download_targets"])
        all_files += hydrate_result["downloaded"]

        print(
            f"☁️ クラウド専用: {len(cloud_files)}件 / "
            f"ダウンロード対象: {len(cloud_result['download_targets'])}件 / "
            f"成功: {len(hydrate_result['downloaded'])}件 / "
            f"失敗: {len(hydrate_result['failed'])}件 / "
            f"スキップ: {len(cloud_result['skipped'])}件"
        )

    # STEP 1.6: wiki_filter=True の場合は LLM スクリーニング
    screen_result = None
    if wiki_filter and all_files:
        # ③ スクリーニング結果キャッシュ: 前回スキップ済みファイルをLLM呼び出し前に除外
        rejection_cache = load_filter_rejection_cache()
        uncached_files  = []
        pre_cached_skip = []
        for f in all_files:
            rel       = to_personal_relative(f)
            cached_h  = rejection_cache.get(rel)
            if cached_h and cached_h == compute_file_hash(f):
                # ハッシュ一致 → 前回と同じファイル。LLMスコアリング不要
                pre_cached_skip.append({"path": f, "reason": "キャッシュ済み除外（前回スキップ）"})
            else:
                uncached_files.append(f)

        screen_result = pre_screen_wiki_value(uncached_files, wiki_score_threshold)

        # キャッシュ済みスキップを filtered に合算して表示統計に反映
        screen_result["filtered"].extend(pre_cached_skip)
        all_files = screen_result["passed"]   # 採用ファイルのみ以降の処理へ

        # 今回新たにLLMがスキップ判定したファイルをキャッシュに保存（次回再スコアリング不要）
        newly_rejected = [item for item in screen_result["filtered"] if "score" in item]
        if newly_rejected:
            save_filter_rejections(newly_rejected)

    # STEP 2.5: 削除検出 → ユーザー確認
    deleted = detect_deleted_sources(target_dir, all_files)
    if deleted:
        handle_deleted_sources(deleted)   # ユーザーに A/B/C を確認して処理

    # STEP 2: 未処理フィルタ
    filtered = filter_files(all_files)

    # STEP 3: プレビュー・確認（スクリーニング結果も合わせて表示）
    to_process = show_preview(target_dir, filtered, max_files, screen_result)
    if not to_process:
        return {"status": "cancelled", "message": "処理をキャンセルしました"}

    # STEP 4〜6: 処理実行（batch_mode=True で後処理を遅延）
    result = run_batch(
        to_process,
        filtered,
        wiki_detail_level    = wiki_detail_level,
        batch_auto_classify  = batch_auto_classify,
        slim_schema          = slim_schema,          # ② 動的生成スリムSCHEMA
    )
    result["cloud_files"] = len(cloud_files)
    result["cloud_download_targets"] = len(cloud_result["download_targets"])
    result["cloud_downloaded"] = len(hydrate_result["downloaded"])
    result["cloud_download_failed"] = hydrate_result["failed"]
    result["cloud_skipped"] = cloud_result["skipped"]

    # STEP 後処理: overview/changelog/index を一括実行（クレジット削減）
    flush_result = flush_batch_post_processing(
        deferred_overviews  = result.pop("deferred_overviews",  []),
        deferred_changelog  = result.pop("deferred_changelog",  []),
        deferred_wiki_paths = result.pop("deferred_wiki_paths", []),
        deferred_ps_records = result.pop("deferred_ps_records", []),
    )
    if flush_result["errors"]:
        result["error_list"].extend(flush_result["errors"])
        result["errors"] += len(flush_result["errors"])
        result["status"] = "partial"

    return result
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| フォルダが存在しない | エラーを返してスキップ |
| OneDriveクラウド専用ファイル（未ダウンロード） | STEP 1.5 でファイル名・パスから対象判定。対象ならダウンロードして通常処理へ合流、低スコアならスキップ |
| クラウド専用ファイルのダウンロード失敗 | `cloud_download_failed` に記録してスキップ。次回再処理可能 |
| ハッシュ計算失敗（その他 I/O エラー） | 空文字として未処理扱いで続行 |
| _inbox/ へのコピー失敗 | エラーリストに記録してスキップ |
| パイプライン処理失敗 | エラーリストに記録。_inbox コピーは削除 |
| processed-sources.yaml 読み込み失敗 | 空辞書として続行（全ファイルを新規扱い）|
| processed-sources.yaml 書き込み失敗 | 5秒×3回リトライ → 失敗時は警告のみ |

---

## 呼び出し先スキル

```
batch-inbox.md（ユーザー起動）
    ├─ _inbox/ にコピー
    └─→ convert-binary.md       （テキスト抽出）
        └─→ analyze.md          （分類判定）
            └─→ write-wiki.md   （wiki生成）
                └─→ place-wiki.md（後処理 / skip_route_binary=True）
                        ├─→ update-overview.md
                        ├─→ change_log に記録
                        ├─→ index-builder.md（add）
                        └─→ processed-sources.yaml に記録
```
