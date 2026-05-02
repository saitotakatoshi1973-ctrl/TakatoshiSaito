# sync-wiki.md — KnowledgeBase直接追加ファイル検知・後処理スキル

## 概要

`KnowledgeBase/` に直接追加された `.md` ファイルを検知し、
Front-matter の自動補完・index への登録・`_overview.md` 更新を行います。
`wiki-embeddings.npz` に未登録のファイルを対象とします。

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `maintenance-agent` | 週次自動実行 |
| ユーザー手動 | KnowledgeBase/ に直接追加した直後 |

---

## ファイル構成

```
KnowledgeBase/
├── _system/
│   └── wiki-embeddings.npz   ← 登録済みファイルの index
├── _inbox/                   ← 対象外
└── kyorindo/                 ← 対象フォルダ（直接追加検知）
    └── cx/
        └── strategy/
            └── 新規追加.md   ← npz 未登録 → このスキルで処理
```

---

## 共通設定

```python
import os
import re
import yaml
import numpy as np
from datetime import date

KB_ROOT   = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"
NPZ_PATH  = os.path.join(KB_ROOT, "_system", "wiki-embeddings.npz")
SKIP_DIRS = {"_inbox", "_system"}   # 走査から除外するフォルダ

# Front-matter の必須フィールド
REQUIRED_FIELDS = {"title", "wiki_type", "scope", "domain"}

# wiki_type の選択肢
WIKI_TYPES = [
    "strategy", "organization", "issue", "progress",
    "reference", "task", "log", "benchmark", "research",
]
```

---

## STEP 1: npz 登録済みパスを読み込む

```python
def load_registered_paths() -> set[str]:
    """
    wiki-embeddings.npz から登録済みの相対パスセットを返す。
    npz が存在しない場合は空セットを返す。
    """
    if not os.path.exists(NPZ_PATH):
        return set()

    data = np.load(NPZ_PATH, allow_pickle=True)
    return set(data["paths"].tolist())
```

---

## STEP 2: KnowledgeBase/ を走査して未登録ファイルを検出する

```python
def find_unregistered_files(registered: set[str]) -> list[str]:
    """
    KnowledgeBase/ 配下の .md ファイルのうち、npz 未登録のものを返す。
    - _inbox/ / _system/ は除外
    - _overview.md は除外
    戻り値: KB_ROOT からの相対パス（スラッシュ区切り）のリスト
    """
    targets = []

    for root, dirs, files in os.walk(KB_ROOT):
        # 除外フォルダを走査から除く
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname == "_overview.md":
                continue

            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, KB_ROOT).replace("\\", "/")

            if rel_path not in registered:
                targets.append(rel_path)

    return targets
```

---

## STEP 3: Front-matter を検査する

```python
def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Markdown 文字列から Front-matter を抽出する。
    戻り値: (front_matter_dict, body_without_frontmatter)
    Front-matter がない場合は ({}, content)
    """
    match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if not match:
        return {}, content

    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}

    body = content[match.end():]
    return fm, body


def check_frontmatter(fm: dict) -> list[str]:
    """
    必須フィールドのうち欠落しているものを返す。
    """
    missing = []
    for field in REQUIRED_FIELDS:
        val = fm.get(field, "")
        if not val or str(val).strip() == "":
            missing.append(field)
    return missing
```

---

## STEP 4: LLM が必須フィールドを推定して Front-matter を補完する

欠落フィールドがある場合、ファイル内容から LLM が補完する。

### LLMへの指示

```
以下は KnowledgeBase wiki に直接追加された Markdown ファイルです。
不足しているフィールドを推定してください。

【ファイルパス】: {rel_path}
【既存 Front-matter】: {existing_fm}
【不足フィールド】: {missing_fields}
【本文（先頭1000文字）】:
{body[:1000]}

【wiki_type の選択肢】:
strategy / organization / issue / progress /
reference / task / log / benchmark / research

【scope の例】: kyorindo / tsuruha-hd / retail / personal
【domain の例】: cx / it-systems / hr / management / finance / strategy

【出力形式（YAMLのみ）】
title: "（ファイルの内容を表す短いタイトル）"
wiki_type: "（上記選択肢から1つ）"
scope: "（対象スコープ）"
domain: "（対象ドメイン）"
tags: []
status: "current"
created: "{today}"
updated: "{today}"
```

### Front-matter 組み立て

```python
def build_frontmatter(existing_fm: dict, inferred: dict, today: str) -> dict:
    """
    既存 Front-matter に LLM 推定値をマージして完全な Front-matter を構築する。
    既存値を優先し、欠落フィールドのみ inferred で補完する。
    """
    fm = {
        "title":     existing_fm.get("title")     or inferred.get("title", ""),
        "wiki_type": existing_fm.get("wiki_type") or inferred.get("wiki_type", "reference"),
        "scope":     existing_fm.get("scope")     or inferred.get("scope", ""),
        "domain":    existing_fm.get("domain")    or inferred.get("domain", ""),
        "tags":      existing_fm.get("tags")      or inferred.get("tags", []),
        "status":    existing_fm.get("status")    or "current",
        "created":   existing_fm.get("created")   or today,
        "updated":   today,
    }
    return fm
```

---

## STEP 5: ファイルに Front-matter を書き戻す

```python
import time

def write_frontmatter(abs_path: str, fm: dict, body: str,
                      retries: int = 3, wait: int = 5) -> None:
    """
    Front-matter と本文を結合してファイルを上書き保存する。
    OneDrive ロック時はリトライ。
    """
    fm_str   = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    new_content = f"---\n{fm_str}---\n{body}"

    for attempt in range(retries):
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Front-matter 書き戻し失敗: {abs_path}")
```

---

## STEP 6: index-builder.md を呼び出す（add モード）

```yaml
# index-builder.md への入力
mode: "add"
file_path: "{abs_path}"
```

`index-builder.md` の `run()` を呼び出し、wiki-embeddings.npz にファイルを登録する。

---

## STEP 7: update-overview.md を呼び出す

```yaml
# update-overview.md への入力
target_dir: "{os.path.dirname(abs_path)}"
```

処理したファイルが属するサブフォルダの `_overview.md` を更新する。
同じフォルダで複数ファイルを処理した場合は、**最後に1回だけ呼び出す**（フォルダ単位で重複しないようにする）。

```python
def collect_unique_dirs(processed_files: list[str]) -> list[str]:
    """
    処理済みファイルのディレクトリ一覧を重複なく返す。
    """
    dirs = set()
    for rel_path in processed_files:
        dirs.add(os.path.dirname(rel_path))
    return sorted(dirs)
```

---

## STEP 8: メイン実行フロー

```python
def run() -> dict:
    today = date.today().isoformat()

    # STEP 1: npz 登録済みパス読み込み
    registered = load_registered_paths()

    # STEP 2: 未登録ファイル検出
    targets = find_unregistered_files(registered)

    if not targets:
        return {
            "status": "success",
            "message": "未登録ファイルなし",
            "processed": 0,
        }

    processed = []
    skipped   = []
    errors    = []

    for rel_path in targets:
        abs_path = os.path.join(KB_ROOT, rel_path.replace("/", os.sep))

        try:
            # ファイル読み込み
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # STEP 3: Front-matter 検査
            fm, body = parse_frontmatter(content)
            missing  = check_frontmatter(fm)

            # STEP 4: Front-matter 補完（欠落フィールドがある場合）
            if missing:
                inferred = llm_infer_frontmatter(rel_path, fm, body, missing, today)
                fm = build_frontmatter(fm, inferred, today)

                # STEP 5: ファイル書き戻し
                write_frontmatter(abs_path, fm, body)
                action = "frontmatter_updated"
            else:
                action = "index_only"

            # STEP 6: index に追加
            index_result = index_builder_run(mode="add", file_path=abs_path)
            if index_result.get("status") != "success":
                errors.append({"file": rel_path, "step": "index_builder", "error": index_result})
                continue

            processed.append({"file": rel_path, "action": action})

        except Exception as e:
            errors.append({"file": rel_path, "step": "unknown", "error": str(e)})

    # STEP 7: update-overview.md をフォルダ単位で呼び出す
    processed_files = [p["file"] for p in processed]
    unique_dirs = collect_unique_dirs(processed_files)
    for d in unique_dirs:
        update_overview_run(target_dir=os.path.join(KB_ROOT, d.replace("/", os.sep)))

    return {
        "status":    "success" if not errors else "partial",
        "processed": len(processed),
        "skipped":   len(skipped),
        "errors":    errors,
        "results":   processed,
    }
```

---

## STEP 9: 結果を出力する

```yaml
# 未登録ファイルが検出・処理された場合
status: success
processed: 3
skipped: 0
errors: []
results:
  - file: "kyorindo/cx/strategy/新規追加_20260501.md"
    action: "frontmatter_updated"   # Front-matter を補完した
  - file: "kyorindo/management/報告書_20260430.md"
    action: "frontmatter_updated"
  - file: "kyorindo/hr/採用計画_20260428.md"
    action: "index_only"            # Front-matter は既に存在、index 追加のみ

# 未登録ファイルなしの場合
status: success
message: "未登録ファイルなし"
processed: 0
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| ファイル読み込み失敗 | `errors` に記録してスキップ |
| LLM Front-matter 推定失敗 | デフォルト値（`wiki_type: reference`・`scope/domain: ""`）で代替 |
| Front-matter 書き戻し失敗（WinError 5） | 5秒×3回リトライ → 失敗時は `errors` に記録 |
| index-builder.md 失敗 | `errors` に記録し当該ファイルをスキップ |
| update-overview.md 失敗 | `errors` に記録（処理済みファイルはそのまま残す） |

---

## 呼び出し元・呼び出し先

```
maintenance-agent（週次）
ユーザー手動
    └─→ sync-wiki.md（本スキル）
            ├─→ index-builder.md（add モード）
            └─→ update-overview.md（フォルダ単位）
```
