# write-wiki.md — wiki記事執筆スキル（Claude モード / フォールバック）

## 概要

> ⚠️ **このスキルは フォールバック専用です。**
> 通常の wiki 化パイプラインでは `gemini_wiki_generator.py` が分類・本文生成を担います。
> 本スキルが呼ばれるのは以下のケースのみです：
> - Gemini API が失敗した場合（自動フォールバック）
> - 「Claudeモードで」と明示指定された場合（`use_gemini=false`）
> - 既存資料の後追いwiki化を手動で行う場合

`analyze.md` の分類結果YAMLと変換テキストを受け取り、
Claude が KnowledgeBase wiki 用の Markdown ファイルを生成・保存します。

---

## 入力

`analyze.md` STEP 6 が出力した以下のYAML（またはそれに相当する情報）：

```yaml
file_name: "xxx.pptx"
file_type: "pptx"
wiki_destination: "kyorindo/cx/strategy/"   # KnowledgeBase/ 配下の相対パス
personal_destination: null
title_suggestion: "CX推進ロードマップ v4"
wiki_type: "strategy"
scope: "kyorindo"
domain: "cx"
tags: ["CX", "ロードマップ", "2026"]
source: "agent"                             # agent | web | internal_doc | manual | seminar
source_url: ""
classification_confidence: 9
classification_method: "llm_scoring"
converted_text: "（convert-binary.md が変換したテキスト）"
detail_level: "summary"   # "summary"（バッチ時デフォルト）/ "full"（詳細執筆）
# ── Gemini モード用（オプション） ──
use_gemini: true               # デフォルトON。false にすると Claude で生成
source_file_abs_path: ""       # 元ファイルの絶対パス（use_gemini=true 時に使用）
```

---

## STEP 1: ファイル名を決定する

### 1-1: ファイル名の生成

```python
import os
import re
from datetime import date

def generate_filename(title_suggestion: str, wiki_destination: str) -> str:
    """
    {title_suggestion}_{YYYYMMDD}.md を生成する。
    タイトルに使えない文字はアンダースコアに置換。
    """
    today = date.today().strftime("%Y%m%d")
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title_suggestion).strip()
    filename = f"{safe_title}_{today}.md"
    return filename
```

### 1-2: 衝突チェックと自動リネーム

```python
def resolve_filename(wiki_destination: str, filename: str, kb_root: str) -> str:
    """
    ファイル名が既存ファイルと衝突する場合、_v2/_v3 を自動付与する。
    kb_root: KnowledgeBase/ の絶対パス
    """
    dest_dir = os.path.join(kb_root, wiki_destination)
    stem, ext = os.path.splitext(filename)  # stem="CX_roadmap_20260501", ext=".md"

    candidate = filename
    version = 2
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{stem}_v{version}{ext}"
        version += 1
    return candidate
```

---

## STEP 2: Front-matter を生成する

SCHEMA.md で定義された Front-matter を入力YAMLから組み立てる。

```python
from datetime import date

def build_frontmatter(input_yaml: dict, title: str) -> str:
    today = date.today().strftime("%Y-%m-%d")
    tags_str = "\n".join([f'  - "{t}"' for t in input_yaml.get("tags", [])])
    related_str = "[]"

    fm = f"""---
wiki_type: {input_yaml["wiki_type"]}
title: "{title}"
aliases: []
created: {today}
updated: {today}
source: {input_yaml.get("source", "agent")}
source_url: "{input_yaml.get("source_url", "")}"
tags:
{tags_str}
scope: {input_yaml["scope"]}
domain: {input_yaml["domain"]}
status: current
related: {related_str}
---"""
    return fm
```

---

## STEP 3-G: Gemini API で本文を生成する（use_gemini=true の場合のみ）

`use_gemini: true` かつ `source_file_abs_path` が指定されている場合に実行する。
成功すれば STEP 4 へ進む。失敗した場合は自動的に STEP 3（Claude執筆）にフォールバックする。

```python
import subprocess
import sys

GEMINI_SCRIPT = r"C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder\wiki-agent\scripts\gemini_wiki_generator.py"

def call_gemini_body(
    source_file_abs_path: str,
    wiki_type:    str,
    title:        str,
    destination:  str,
    scope:        str,
    domain:       str,
    tags:         list[str],
    converted_text: str = "",
) -> dict:
    """
    gemini_wiki_generator.py を --body-only モードで呼び出す。
    戻り値: {"status": "success", "body": str} または {"status": "error", "reason": str}
    """
    cmd = [
        sys.executable, GEMINI_SCRIPT,
        source_file_abs_path,
        "--body-only",
        "--wiki-type",  wiki_type,
        "--title",      title,
        "--dest",       destination,
        "--scope",      scope,
        "--domain",     domain,
        "--tags",       ",".join(tags),
    ]
    # convert-binary.md の抽出結果がある場合は渡して再抽出を省略
    if converted_text:
        cmd += ["--converted-text", converted_text[:30000]]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if result.returncode != 0:
            return {"status": "error", "reason": result.stderr.strip()}
        body = result.stdout.strip()
        if not body:
            return {"status": "error", "reason": "Gemini から空の本文が返されました"}
        return {"status": "success", "body": body}
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "Gemini API タイムアウト（120秒）"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
```

### 実行フロー

```python
body = None
generation_method = "claude"   # ログ記録用

if use_gemini and source_file_abs_path:
    print("🤖 Gemini API で本文を生成中...")
    gemini_result = call_gemini_body(
        source_file_abs_path = source_file_abs_path,
        wiki_type    = wiki_type,
        title        = title_suggestion,
        destination  = wiki_destination,
        scope        = scope,
        domain       = domain,
        tags         = tags,
        converted_text = converted_text,
    )
    if gemini_result["status"] == "success":
        body = gemini_result["body"]
        generation_method = "gemini"
        print("✅ Gemini による本文生成完了")
    else:
        print(f"⚠️  Gemini 失敗（{gemini_result['reason']}）→ Claude で執筆します")
        # body = None のまま STEP 3（Claude）へフォールバック

# Gemini 未使用 or フォールバック → STEP 3（Claude執筆）へ
if body is None:
    # → 以下の STEP 3 の処理を実行する
    pass
```

---

## STEP 3: wiki本文をLLMが執筆する（Claude モード / Gemini フォールバック時）

`use_gemini=false` の場合、または Gemini が失敗した場合に実行する。
`wiki_type` に応じたテンプレートと変換テキストを使い、LLMが本文を執筆する。

### テンプレート定義

#### `strategy`（戦略・ロードマップ・MVV）
```
## 背景・目的
（元資料から読み取れる背景や目的を2〜4文で記述）

## 主要内容
（ロードマップ・施策・方針を箇条書きまたはフェーズ別に整理）

## 重要ポイント
（意思決定に影響する数値・KPI・優先事項を箇条書き）

## 関連リンク
（分類先フォルダ内の関連ファイルがあればパスを記述、なければ空）
```

#### `organization`（組織図・企業概要）
```
## 概要
（組織・企業の基本情報）

## 組織構成
（部署・チーム・人員構成を箇条書きまたは表で整理）

## 役割・担当
（主要ポストと担当業務）

## 変更履歴
（直近の組織変更があれば記録）
```

#### `issue`（課題一覧・問題点）
```
## 課題一覧

| # | 課題 | 優先度 | 担当 |
|---|------|--------|------|
| 1 | ...  | 高     | ...  |

## 背景・原因
（課題の発生背景や根本原因）

## 対応方針
（解決に向けた方向性・アプローチ）
```

#### `progress`（会議記録・進捗サマリー）
```
## 日時・参加者
- 日時: YYYY-MM-DD HH:MM
- 参加者: （氏名・部署）

## 議題
（議題を箇条書き）

## 決定事項
（決定内容を箇条書き）

## 次回アクション

| 担当 | 内容 | 期限 |
|------|------|------|
```

#### `reference`（調査・参考情報・記事まとめ）
```
## 出典情報
- 媒体/著者:
- 公開日:

## 要点サマリー
（3〜5文で主要な主張・結論を要約）

## 詳細メモ
（重要な数値・固有名詞・ファクトを箇条書き）

## 自社への示唆
（杏林堂やプロジェクトに関連する示唆があれば記述）
```

#### `task`（タスク一覧・優先度管理）
```
## タスク一覧

| # | タスク | 優先度 | 担当 | 期限 | 状態 |
|---|--------|--------|------|------|------|

## 背景・目的
（このタスクリストの目的）
```

#### `log`（議論ログ・作業記録）
```
## 日時
YYYY-MM-DD

## 内容
（議論や作業の概要）

## 判断理由
（なぜその判断をしたか）

## 次のステップ
（続きのアクション）
```

#### `benchmark`（競合比較・ベンチマーク）
```
## 比較軸
（何を比較するかの定義）

## 比較テーブル

| 企業/項目 | 指標1 | 指標2 | 指標3 |
|----------|-------|-------|-------|

## 考察
（比較から読み取れる示唆・杏林堂の立ち位置）
```

#### `research`（リサーチレポート・講義要約）
```
## 出典
- 主催/著者:
- 日時/公開日:
- 形式: セミナー | レポート | 論文

## 概要
（2〜3文でテーマと主旨を説明）

## 重要な知見
（箇条書きで重要な発見・主張を列挙）

## 自社への示唆
（実務・プロジェクトへの応用可能性）
```

---

### LLMへの執筆指示（プロンプトテンプレート）

`detail_level` によって執筆モードを切り替える。
バッチ処理時は `"summary"` がデフォルトでクレジットを削減する。

#### `detail_level: "summary"`（バッチ処理デフォルト・短時間・低トークン）

```
以下の変換テキストを読み、wiki記事の本文を日本語で簡潔に執筆してください。

【元資料テキスト】
{converted_text の先頭 3000 文字}

【執筆ルール（summaryモード）】
- セクション構成: 「## 概要」「## 主要ポイント」「## 関連情報」の3セクションのみ
- 「## 概要」: 2〜3文で文書の目的・主旨を説明
- 「## 主要ポイント」: 箇条書き3〜5項目（重要な事実・数値・固有名詞を中心に）
- 「## 関連情報」: 日付・関係者・出典など補足情報を箇条書き
- 元資料にない内容は推測して書かない
- 文体は「である調」で統一する
- 分量目安: 150〜300文字（簡潔さ優先）
```

#### `detail_level: "full"`（単独処理・詳細執筆）

```
以下の変換テキストを読み、wiki記事の本文を日本語で執筆してください。

【テンプレート】
{上記の wiki_type に対応するテンプレート}

【元資料テキスト】
{converted_text の先頭 6000 文字}

【執筆ルール】
- テンプレートのセクション構成を必ず守る
- 元資料にない内容は推測して書かない
- 元資料に情報が不足するセクションは「（情報なし）」と記載する
- 箇条書きは3〜7項目を目安にする
- 固有名詞・数値・日付は元資料のものを正確に使う
- 文体は「である調」で統一する
- 分量目安: 300〜800文字（ベンチマーク・research は 500〜1000文字）
```

---

## STEP 4: ファイルを保存する

```python
import os

def save_wiki_file(
    kb_root: str,
    wiki_destination: str,
    filename: str,
    frontmatter: str,
    body: str
) -> str:
    """
    wiki ファイルを KnowledgeBase/ に保存する。
    保存先ディレクトリが存在しない場合は自動作成。
    戻り値: 保存した絶対パス
    """
    dest_dir = os.path.join(kb_root, wiki_destination)
    os.makedirs(dest_dir, exist_ok=True)

    content = frontmatter + "\n\n" + body
    file_path = os.path.join(dest_dir, filename)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return file_path
```

---

## STEP 5: _overview.md の更新チェック

保存先フォルダに `_overview.md` が存在する場合、`update-overview.md` スキルを呼び出す。

```python
def check_overview_update(dest_dir: str) -> bool:
    overview_path = os.path.join(dest_dir, "_overview.md")
    return os.path.exists(overview_path)

# _overview.md が存在する場合:
# → update-overview.md スキルを呼び出す（スキル7）
```

---

## STEP 6: 結果を出力する

実行完了後、以下を出力する：

```yaml
status: success
saved_path: "KnowledgeBase/kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md"
filename: "CX推進ロードマップ_v4_20260501.md"
wiki_type: "strategy"
title: "CX推進ロードマップ v4"
overview_updated: true        # _overview.md の更新を実施したか
generation_method: "gemini"   # gemini | claude | claude_fallback
next_skill: "place-wiki.md"   # 次に呼び出すスキル
```

---

## エラーハンドリング

| エラー | 対処 |
|--------|------|
| `wiki_destination` が空 | `analyze.md` に戻り分類を再実行するよう通知 |
| `converted_text` が空 | Front-matter のみのスタブファイルを `status: draft` で保存 |
| 書き込み権限エラー（WinError 5） | 5秒×3回リトライ後、ユーザーに通知 |
| 保存先ディレクトリ作成失敗 | エラーメッセージを表示し処理中断 |

---

## 後追いwiki化での利用方法

`_inbox/` 経由でない既存資料を wiki化する場合：

```yaml
# 直接このスキルを呼び出す際の最低限の入力
file_name: "既存資料.pptx"
file_type: "pptx"
wiki_destination: "kyorindo/cx/strategy/"
title_suggestion: "任意のタイトル"
wiki_type: "strategy"
scope: "kyorindo"
domain: "cx"
tags: []
source: "internal_doc"
source_url: ""
converted_text: "（convert-binary.md で変換したテキスト）"
```

`analyze.md` を経由せずに、このスキルを単独で呼び出すことが可能。

---

## 呼び出し元・呼び出し先

```
【フォールバック経路での位置づけ】
inbox-agent.md（Gemini失敗時）
    └─→ analyze.md
            └─→ write-wiki.md（本スキル）
                    ├─→ update-overview.md（_overview.md が存在する場合）
                    └─→ place-wiki.md（ファイル配置・元ファイル移動）

【正本経路（通常）】
inbox-agent.md / batch-inbox.md
    └─→ gemini_wiki_generator.py --analyze-only → --generate
            └─→ place-wiki.md
```
