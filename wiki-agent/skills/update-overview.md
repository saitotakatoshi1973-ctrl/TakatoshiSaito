# update-overview.md — _overview.md 自動更新スキル

## 概要

サブフォルダ内の `_overview.md` を最新状態に更新します。
配下ファイルの一覧・Front-matter 情報を反映し、
`status: draft` のものはLLMが概要本文を自動執筆します。

**このスキルは `_overview.md` を新規作成しません。**
新規作成は `place-wiki.md` が担当します。

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `write-wiki.md` | 新規wikiファイル追加後 |
| `maintenance-agent` | 週次定期メンテナンス時（全フォルダ一括） |

---

## 入力

```yaml
# 単一フォルダ更新（write-wiki.md から呼び出し時）
target_dir: "kyorindo/cx/strategy/"   # KnowledgeBase/ 配下の相対パス

# 全フォルダ一括更新（maintenance-agent から呼び出し時）
target_dir: "__ALL__"

# 差分追記モード（batch-inbox.md から呼び出し時・クレジット削減）
mode: "append"          # "append"（差分追記）/ "rebuild"（全体再生成、デフォルト）
new_files: []           # 今回追加されたファイル名のリスト（append モード専用）
```

> **モード選択の目安**:
> - `mode: "append"` — バッチ処理時。追加ファイルを一覧末尾に追記するだけで完結。フォルダ全体を再スキャンしない。LLM呼び出し不要（文字列追記のみ）。
> - `mode: "rebuild"` — 定期メンテナンス・手動実行時。全ファイルを再スキャンしてLLMが一覧を再生成する。

---

## STEP 0: モード分岐（append / rebuild）

```python
mode      = input_yaml.get("mode", "rebuild")
new_files = input_yaml.get("new_files", [])

if mode == "append" and new_files:
    # ── append モード: LLM不要・ファイル読み書きのみ ──
    # 各 overview_path に対して、new_files を一覧末尾に追記して終了
    for overview_path in get_target_dirs(target_dir):
        _append_to_overview(overview_path, new_files)
    return {"status": "success", "mode": "append", "appended": len(new_files)}

# ── rebuild モード（以下の STEP 1〜5 を実行）──
```

### `_append_to_overview()` の実装（LLM不要）

```python
from datetime import date

def _append_to_overview(overview_path: str, new_files: list[dict]) -> None:
    """
    _overview.md の「配下ファイル一覧」セクション末尾に
    新規ファイルのエントリを追記する（フォルダ全体の再スキャン不要）。

    new_files の各要素: {"filename": str, "title": str, "status": str, "updated": str}
    """
    try:
        with open(overview_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return

    today = date.today().strftime("%Y-%m-%d")
    new_lines = []
    for nf in new_files:
        title   = nf.get("title", nf.get("filename", ""))
        status  = nf.get("status", "current")
        updated = nf.get("updated", today)
        fname   = nf.get("filename", "")
        # テーブル形式の場合は行追加、箇条書きの場合は bullet 追加
        new_lines.append(f"| {fname} | {title} | {status} | {updated} |")

    addition = "\n".join(new_lines)

    # 「配下ファイル一覧」セクションの末尾（次の ## の直前、またはファイル末尾）に追記
    import re
    pattern = r'(## 配下ファイル一覧\n.*?)(\n## |\Z)'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(
            pattern,
            lambda m: m.group(1).rstrip() + "\n" + addition + "\n" + m.group(2),
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.rstrip() + f"\n\n## 配下ファイル一覧\n\n{addition}\n"

    # updated 日付を今日に更新
    content = re.sub(r'(updated:\s*)[\d\-]+', f'\\g<1>{today}', content)

    write_with_retry(overview_path, content)
```

---

## STEP 1: 対象フォルダを決定する

```python
import os
import glob

KB_ROOT = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"

def get_target_dirs(target_dir: str) -> list[str]:
    """
    更新対象の _overview.md パスリストを返す。
    target_dir == "__ALL__" の場合は KnowledgeBase/ 全体を走査。
    """
    if target_dir == "__ALL__":
        pattern = os.path.join(KB_ROOT, "**", "_overview.md")
        return glob.glob(pattern, recursive=True)
    else:
        overview_path = os.path.join(KB_ROOT, target_dir, "_overview.md")
        if os.path.exists(overview_path):
            return [overview_path]
        return []  # 存在しない場合はスキップ（作成はしない）
```

---

## STEP 2: 配下ファイルの Front-matter を収集する

`_overview.md` が存在するフォルダ直下の `.md` ファイル（`_overview.md` 自身を除く）を
読み込み、Front-matter を抽出する。

```python
import re
import yaml

def extract_frontmatter(md_path: str) -> dict:
    """
    Markdown ファイルの Front-matter（--- ブロック）を辞書で返す。
    Front-matter がない場合は空辞書を返す。
    """
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if match:
            return yaml.safe_load(match.group(1)) or {}
    except Exception:
        pass
    return {}

def collect_file_info(overview_path: str) -> list[dict]:
    """
    _overview.md と同フォルダの .md ファイルの情報を収集する。
    サブフォルダは再帰せず、直下のみ対象。
    """
    folder = os.path.dirname(overview_path)
    files = []

    for fname in sorted(os.listdir(folder)):
        if not fname.endswith('.md'):
            continue
        if fname == '_overview.md':
            continue

        fpath = os.path.join(folder, fname)
        fm = extract_frontmatter(fpath)
        files.append({
            "filename": fname,
            "title":   fm.get("title", fname.replace(".md", "")),
            "status":  fm.get("status", ""),
            "updated": fm.get("updated", ""),
            "wiki_type": fm.get("wiki_type", ""),
        })

    return files
```

---

## STEP 3: 「配下ファイル一覧」セクションを生成する（LLM判断）

収集した情報をもとに LLM がファイル一覧の粒度と表現を判断して生成する。

### LLM への指示

```
以下のフォルダに含まれる wiki ファイルの一覧を、
_overview.md の「配下ファイル一覧」セクションとして Markdown で記述してください。

【フォルダ】: {target_dir}
【ファイル情報】:
{file_info のリスト}

【記述ルール】
- ファイルが少ない（5件以下）: タイトル・status・updated を表形式で記載
- ファイルが多い（6件以上）: wiki_type でグループ化して箇条書きで記載
- status: outdated のファイルは ~~取り消し線~~ で表示
- status: draft のファイルには （草稿） と付記
- ファイルが0件の場合: 「（ファイルなし）」と記載

【出力形式】
## 配下ファイル一覧

（上記ルールに従った Markdown）
```

### 出力例（5件以下の場合）

```markdown
## 配下ファイル一覧

| ファイル | タイトル | ステータス | 更新日 |
|---------|---------|-----------|--------|
| CX_roadmap_20260501.md | CX推進ロードマップ v4 | current | 2026-05-01 |
| ~~CX_roadmap_20260416_v3.md~~ | ~~CX推進ロードマップ v3~~ | outdated | 2026-04-16 |
| CX_MVV_20260401.md | CX推進部 MVV | current | 2026-04-01 |
```

### 出力例（6件以上の場合）

```markdown
## 配下ファイル一覧

### strategy（戦略・ロードマップ）
- CX推進ロードマップ v4（current）
- ~~CX推進ロードマップ v3~~（outdated）

### progress（進捗・議事録）
- CX定例 2026-04-25（current）
- CX定例 2026-04-18（current）
```

---

## STEP 4: `_overview.md` を更新する

### 4-1: `status: draft` の場合 → LLMが概要本文も執筆

```python
def is_draft(overview_path: str) -> bool:
    fm = extract_frontmatter(overview_path)
    return fm.get("status") == "draft"
```

`status: draft` の場合、LLM への追加指示：

```
この _overview.md は status: draft（未執筆）です。
配下ファイルの内容から判断して、以下のセクションも執筆してください。

## 概要
（このフォルダの目的・管轄範囲を2〜4文で記述）

## 関連リンク
（関連する他のwikiフォルダへのリンクがあれば記述。なければ省略）

執筆後、Front-matter の status を draft → current に変更してください。
```

### 4-2: `status: current` の場合 → 「配下ファイル一覧」のみ更新

既存の概要・関連リンクセクションは**一切上書きしない**。
「配下ファイル一覧」セクションのみ差し替える。

```python
def update_file_list_section(content: str, new_section: str) -> str:
    """
    既存の _overview.md から「配下ファイル一覧」セクションを
    新しい内容に置き換える。セクションが存在しない場合は末尾に追加。
    """
    pattern = r'(## 配下ファイル一覧\n)(.*?)(\n## |\Z)'

    if re.search(pattern, content, re.DOTALL):
        # 既存セクションを置換（次のセクション見出しは保持）
        updated = re.sub(
            pattern,
            lambda m: new_section + "\n" + (m.group(3) if m.group(3) != '' else ''),
            content,
            flags=re.DOTALL
        )
    else:
        # セクションが存在しない場合は末尾に追加
        updated = content.rstrip() + "\n\n" + new_section + "\n"

    return updated
```

### 4-3: Front-matter の `updated` を今日の日付に更新

```python
from datetime import date

def update_frontmatter_date(content: str) -> str:
    today = date.today().strftime("%Y-%m-%d")
    return re.sub(
        r'(updated:\s*)[\d\-]+',
        f'\\g<1>{today}',
        content
    )
```

### 4-4: ファイルへの書き込み（OneDrive ロック対策）

```python
import time

def write_with_retry(file_path: str, content: str, retries: int = 3, wait: int = 5) -> None:
    for attempt in range(retries):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError(f"_overview.md の書き込みに失敗: {file_path}")
```

---

## STEP 5: 結果を出力する

```yaml
status: success
updated:
  - path: "kyorindo/cx/strategy/_overview.md"
    was_draft: false          # draft から current に昇格したか
    files_listed: 3           # 一覧に掲載したファイル数
skipped:
  - path: "kyorindo/hr/_overview.md"
    reason: "ファイルが存在しない"
errors: []
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `_overview.md` が存在しない | スキップ（ログに記録）。作成はしない |
| Front-matter 解析失敗 | 該当ファイルをスキップして一覧から除外 |
| 書き込み失敗（WinError 5） | 5秒×3回リトライ → 失敗時は `errors` に記録 |
| `__ALL__` 実行で100件超 | 上限100件でバッチ打ち切り。残りは次回 maintenance-agent に委ねる |

---

## 呼び出し元・呼び出し先

```
write-wiki.md（新規ファイル追加後）
maintenance-agent（週次定期）
    └─→ update-overview.md（本スキル）
            （呼び出し先なし：単独完結）
```
