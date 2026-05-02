# sync-personal.md — 00personal/ 同期スキル

## 概要

`00personal/` フォルダの実態と `personal-index.yaml` を全件比較し、
追加・削除・リネームを自動検知して索引を最新状態に同期します。
変更があった場合のみサマリーをユーザーに報告します。

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `maintenance-agent` | 週次自動実行 |
| ユーザー手動 | 00personal/ を手動変更した直後 |

---

## 共通設定

```python
import os
import yaml
import re
from datetime import date

PERSONAL_ROOT = r"C:\Users\takatoshi-saito\OneDrive\00personal"
INDEX_PATH    = (
    r"C:\Users\takatoshi-saito\OneDrive\00personal"
    r"\KnowledgeBase\_system\personal\personal-index.yaml"
)
MAX_DEPTH = 4        # 索引対象の最大階層深さ
EXCLUDE_DIRS = {     # 走査から除外するフォルダ
    "KnowledgeBase", ".git", "$RECYCLE.BIN",
    "System Volume Information", "ClaudeCodeFolder",
}
```

---

## STEP 1: 実フォルダ一覧を収集する

```python
def scan_actual_folders(root: str, max_depth: int) -> set[str]:
    """
    00personal/ 配下を走査し、フォルダの相対パスセットを返す。
    除外フォルダ・深さ上限を適用する。
    """
    actual = set()

    for dirpath, dirnames, _ in os.walk(root):
        # 除外フォルダを走査から除く（in-place 変更）
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith('.')
        ]

        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel == ".":
            continue

        depth = rel.count("/") + 1
        if depth > max_depth:
            dirnames.clear()  # これ以上深く走査しない
            continue

        actual.add(rel)

    return actual
```

---

## STEP 2: `personal-index.yaml` のフォルダ一覧を読み込む

```python
def load_index_folders(index_path: str) -> dict[str, dict]:
    """
    personal-index.yaml を読み込み、{path: entry} の辞書で返す。
    """
    with open(index_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    return {
        entry['path']: entry
        for entry in data.get('folders', [])
    }
```

---

## STEP 3: 差分を検出する（追加・削除・リネーム）

```python
def detect_diff(
    actual: set[str],
    indexed: dict[str, dict]
) -> dict:
    """
    実フォルダ と indexed を比較して差分を返す。

    リネーム判定:
      削除候補と追加候補が同階層にあり、
      親パスが同一・フォルダ名だけ異なる場合はリネームとみなす。
    """
    indexed_paths = set(indexed.keys())

    added   = actual - indexed_paths
    removed = indexed_paths - actual

    # リネーム判定（親が同じで名前が違う削除+追加ペア）
    renamed = []
    unmatched_removed = set(removed)
    unmatched_added   = set(added)

    for rem in list(unmatched_removed):
        rem_parent = os.path.dirname(rem)
        for add in list(unmatched_added):
            add_parent = os.path.dirname(add)
            if rem_parent == add_parent:
                renamed.append({"old": rem, "new": add})
                unmatched_removed.discard(rem)
                unmatched_added.discard(add)
                break

    return {
        "added":   sorted(unmatched_added),
        "removed": sorted(unmatched_removed),
        "renamed": renamed,
    }
```

---

## STEP 4: LLMが新規フォルダの `description` / `keywords` を推定する

新規追加フォルダに対して、フォルダ名・親フォルダ名から LLM が補完する。

### LLMへの指示

```
以下の新規フォルダ情報から、personal-index.yaml 用の
description と keywords を日本語で推定してください。

【フォルダパス】: {rel_path}
【フォルダ名】: {folder_name}
【親フォルダ名】: {parent_name}
【兄弟フォルダ例】: {sibling_names（最大3件）}

【出力形式】
description: "（20文字以内の説明）"
keywords:
  - "（キーワード1）"
  - "（キーワード2）"
type: "技術資料 | 業務資料 | 人事資料 | 財務資料 | その他"
```

### 推定例

```
フォルダ: 09_InformationOrganization/杏林堂/CX推進/2026年度
→ description: "CX推進2026年度関連資料"
   keywords: ["CX", "2026年度", "杏林堂"]
   type: "業務資料"
```

---

## STEP 5: `personal-index.yaml` を更新する

```python
import time

def update_index(
    index_path: str,
    diff: dict,
    indexed: dict[str, dict],
    new_entries: dict[str, dict],   # LLMが生成した新規エントリ
    retries: int = 3,
    wait: int = 5
) -> None:
    """
    差分を personal-index.yaml に反映する。
    追加→append / 削除→remove / リネーム→path更新
    """
    today = date.today().isoformat()

    # 追加
    for path in diff['added']:
        entry = new_entries.get(path, {})
        indexed[path] = {
            'path':        path,
            'description': entry.get('description', f'{os.path.basename(path)} 関連資料'),
            'type':        entry.get('type', 'その他'),
            'keywords':    entry.get('keywords', []),
            'file_count':  0,
            'last_updated': today,
            'searchable':  True,
        }

    # 削除
    for path in diff['removed']:
        indexed.pop(path, None)

    # リネーム（old → new にパスを更新）
    for rename in diff['renamed']:
        old_entry = indexed.pop(rename['old'], {})
        old_entry['path'] = rename['new']
        old_entry['last_updated'] = today
        indexed[rename['new']] = old_entry

    # ソートして書き戻し
    updated_folders = sorted(indexed.values(), key=lambda x: x['path'])
    data = {
        'meta': {
            'generated':    today,
            'root':         PERSONAL_ROOT,
            'max_depth':    MAX_DEPTH,
            'total_entries': len(updated_folders),
            'description':  '00personal フォルダ索引（深さ4・KnowledgeBase Skill参照用）',
        },
        'folders': updated_folders,
    }

    for attempt in range(retries):
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True,
                          default_flow_style=False, sort_keys=False)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError("personal-index.yaml の書き込みに失敗しました")
```

---

## STEP 6: サマリーをユーザーに報告する（変更があった場合のみ）

```python
def build_summary(diff: dict) -> str | None:
    total = len(diff['added']) + len(diff['removed']) + len(diff['renamed'])
    if total == 0:
        return None  # 変更なし → 報告しない

    lines = [f"📁 personal-index.yaml を同期しました（{total}件の変更）\n"]

    if diff['added']:
        lines.append(f"✅ 追加 ({len(diff['added'])}件):")
        lines += [f"  + {p}" for p in diff['added']]

    if diff['removed']:
        lines.append(f"🗑️ 削除 ({len(diff['removed'])}件):")
        lines += [f"  - {p}" for p in diff['removed']]

    if diff['renamed']:
        lines.append(f"✏️ リネーム ({len(diff['renamed'])}件):")
        lines += [f"  {r['old']} → {r['new']}" for r in diff['renamed']]

    return "\n".join(lines)
```

---

## STEP 7: メイン実行フロー

```python
def run() -> dict:
    # 実フォルダ収集
    actual  = scan_actual_folders(PERSONAL_ROOT, MAX_DEPTH)

    # index 読み込み
    indexed = load_index_folders(INDEX_PATH)

    # 差分検出
    diff = detect_diff(actual, indexed)

    total_changes = len(diff['added']) + len(diff['removed']) + len(diff['renamed'])
    if total_changes == 0:
        return {"status": "success", "changes": 0, "message": "変更なし"}

    # 新規フォルダの description/keywords を LLM で推定
    new_entries = {}
    for path in diff['added']:
        new_entries[path] = llm_infer_folder_meta(path)

    # index を更新
    update_index(INDEX_PATH, diff, indexed, new_entries)

    # サマリー生成・報告
    summary = build_summary(diff)
    if summary:
        print(summary)

    return {
        "status":  "success",
        "changes": total_changes,
        "added":   len(diff['added']),
        "removed": len(diff['removed']),
        "renamed": len(diff['renamed']),
        "summary": summary,
    }
```

---

## STEP 8: 結果を出力する

```yaml
# 変更があった場合
status: success
changes: 3
added: 1
removed: 1
renamed: 1
summary: |
  📁 personal-index.yaml を同期しました（3件の変更）
  ✅ 追加 (1件):
    + 09_InformationOrganization/杏林堂/CX推進/2026年度
  🗑️ 削除 (1件):
    - 09_InformationOrganization/杏林堂/旧フォルダ
  ✏️ リネーム (1件):
    09_InformationOrganization/杏林堂/CX → 09_InformationOrganization/杏林堂/CX推進

# 変更がなかった場合（報告なし）
status: success
changes: 0
message: "変更なし"
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `personal-index.yaml` 読み込み失敗 | エラーを返して終了 |
| フォルダ走査中のアクセス拒否 | 該当フォルダをスキップしてログに記録 |
| LLM meta 推定失敗 | デフォルト値（`type: その他`・`keywords: []`）で代替 |
| `personal-index.yaml` 書き込み失敗 | 5秒×3回リトライ → 失敗時はエラーを返す |

---

## 呼び出し元・呼び出し先

```
maintenance-agent（週次）
ユーザー手動
    └─→ sync-personal.md（本スキル）
            （呼び出し先なし：単独完結）
```
