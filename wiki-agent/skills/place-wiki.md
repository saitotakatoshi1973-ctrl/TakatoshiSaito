# place-wiki.md — wiki配置後処理スキル

## 概要

`write-wiki.md` が KnowledgeBase/ へwikiファイルを保存した後の後処理を担います。

- `_overview.md` スタブの自動作成（新規サブフォルダの場合）
- `change_log` への記録
- `index-builder.md` 呼び出し（ベクトルindex更新）
- `route-binary.md` 呼び出し（元ファイルを 00personal/ へ移動）

---

## 入力

`write-wiki.md` STEP 6 が出力した以下のYAML：

```yaml
status: success
saved_path: "KnowledgeBase/kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md"
filename: "CX推進ロードマップ_v4_20260501.md"
wiki_type: "strategy"
title: "CX推進ロードマップ v4"
wiki_destination: "kyorindo/cx/strategy/"
overview_updated: true
original_file: "_inbox/CX_roadmap_v4.pptx"   # 元ファイルのパス（_inbox/ 相対）

# ── batch-inbox.md からの場合のみ設定される追加フィールド ──
original_personal_path: "03_CX推進/01_戦略/CX_roadmap_v4.pptx"  # 00personal 相対パス
file_hash: "a3f8c2d1..."                                          # MD5 ハッシュ
skip_route_binary: true   # True の場合 STEP 4 をスキップ（元ファイルは既に 00personal にある）
batch_mode: false         # True の場合 STEP 1（overview更新）/STEP 2（changelog）/STEP 3（index）をスキップ
                          # → batch-inbox.md の flush_batch_post_processing() で一括実行
```

### batch_write_wiki=True 時の特別な入力（① analyze + write-wiki 統合モード）

`batch_write_wiki=True` の場合、`write-wiki.md` は呼び出されない。
代わりに **`analyze.md` STEP 6 統合モードの出力**がそのまま渡される。

```yaml
# analyze.md 統合モードからの入力
analyze_result:
  destination: "kyorindo/cx/strategy/"
  front_matter:
    wiki_type: "strategy"
    title: "CX推進ロードマップ v4"
    scope: "kyorindo"
    domain: "cx"
    status: current
    source: agent
    tags: []
  classification_confidence: high
wiki_content: |
  ## 概要
  （analyze.md が生成した wiki 本文）
  ...
original_personal_path: "..."
file_hash: "..."
skip_route_binary: true
batch_mode: true
batch_write_wiki: true
```

`batch_write_wiki=True` の場合、本スキルの STEP 0 でファイルの保存（write-wiki.md STEP 4 相当）を実行してから、STEP 1 以降の後処理へ進む。

---

## batch_mode での動作（クレジット削減）

`batch_mode: true` の場合、以下のステップをスキップし、
呼び出し元の `batch-inbox.md` が `flush_batch_post_processing()` で一括実行する。

| ステップ | batch_mode=false（通常） | batch_mode=true（バッチ） |
|---------|------------------------|--------------------------|
| STEP 1: _overview.md スタブ作成 | 実行する | **実行する**（新規フォルダのスタブ作成は即時） |
| STEP 1: update-overview.md 呼び出し | 実行する | **スキップ**（flush で一括） |
| STEP 2: change_log 追記 | 実行する | **スキップ**（flush で一括） |
| STEP 2.5: processed-sources.yaml 記録 | 実行する | **実行する**（障害回復のため即時） |
| STEP 3: index-builder 呼び出し | 実行する | **スキップ**（flush で一括） |
| STEP 4: route-binary 呼び出し | skip_route_binary で制御 | skip_route_binary で制御 |

```python
# batch_mode フラグの確認（各ステップで参照）
batch_mode = input_yaml.get("batch_mode", False)
```

---

## STEP 0: batch_write_wiki=True 時のwikiファイル保存（① 統合モード専用）

`batch_write_wiki=True` の場合のみ実行。
`write-wiki.md` が実行されていないため、このステップで wiki ファイルを保存する。

```python
def save_wiki_from_combined(analyze_result: dict, wiki_content: str) -> str:
    """
    analyze.md 統合モードの出力から wiki ファイルを保存する。
    write-wiki.md STEP 1〜4 相当の処理を実行する。
    戻り値: 保存した絶対パス
    """
    fm_data       = analyze_result["front_matter"]
    destination   = analyze_result["destination"]
    title         = fm_data["title"]
    today         = date.today().strftime("%Y-%m-%d")

    # ファイル名生成（write-wiki.md STEP 1 相当）
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title).strip()
    filename   = f"{safe_title}_{date.today().strftime('%Y%m%d')}.md"

    # 衝突チェック
    dest_dir = os.path.join(KB_ROOT, destination)
    os.makedirs(dest_dir, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    version = 2
    while os.path.exists(os.path.join(dest_dir, filename)):
        filename = f"{stem}_v{version}{ext}"
        version += 1

    # Front-matter 生成（write-wiki.md STEP 2 相当）
    tags_str = "\n".join([f'  - "{t}"' for t in fm_data.get("tags", [])])
    frontmatter = f"""---
wiki_type: {fm_data["wiki_type"]}
title: "{title}"
aliases: []
created: {today}
updated: {today}
source: {fm_data.get("source", "agent")}
source_url: "{fm_data.get("source_url", "")}"
tags:
{tags_str}
scope: {fm_data["scope"]}
domain: {fm_data["domain"]}
status: {fm_data.get("status", "current")}
related: []
---"""

    # ファイル保存
    content   = frontmatter + "\n\n" + wiki_content
    file_path = os.path.join(dest_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


# batch_write_wiki=True 時の分岐
if input_yaml.get("batch_write_wiki", False):
    saved_path = save_wiki_from_combined(
        analyze_result = input_yaml["analyze_result"],
        wiki_content   = input_yaml["wiki_content"],
    )
    # 以降の STEP 1〜4 は saved_path を参照して通常通り実行
```

---

## STEP 1: 新規サブフォルダの `_overview.md` スタブ作成

`write-wiki.md` が新しいサブフォルダを作成した場合（`_overview.md` が存在しない場合）、
スタブファイルを自動作成する。（batch_mode でも実行する）

```python
import os
from datetime import date

def create_overview_stub(dest_dir: str, folder_name: str) -> bool:
    """
    _overview.md が存在しない場合にスタブを作成する。
    戻り値: True=作成した / False=既存のためスキップ
    """
    overview_path = os.path.join(dest_dir, "_overview.md")
    if os.path.exists(overview_path):
        return False

    today = date.today().strftime("%Y-%m-%d")
    stub_content = f"""---
wiki_type: reference
title: "{folder_name} 概要"
created: {today}
updated: {today}
source: agent
tags: []
scope: ""
domain: ""
status: draft
related: []
---

## 概要

（このフォルダの目的・管轄範囲を記述してください）

## 配下ファイル一覧

（wiki管理エージェントが自動更新します）

## 関連リンク

（関連する他のwikiエントリへのリンク）
"""
    with open(overview_path, 'w', encoding='utf-8') as f:
        f.write(stub_content)
    return True
```

### 実行

```python
kb_root = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"
dest_dir = os.path.join(kb_root, wiki_destination)
folder_name = os.path.basename(dest_dir.rstrip("/\\"))

overview_created = create_overview_stub(dest_dir, folder_name)
```

---

### _overview.md 更新（batch_mode=False の場合のみ即時実行）

```python
# _overview.md が存在する場合のみ更新。batch_mode=True はスキップ（flush で一括）
if not batch_mode:
    overview_path = os.path.join(dest_dir, "_overview.md")
    if os.path.exists(overview_path):
        update_overview_run(overview_path)
```

---

## STEP 2: `change_log` に1行追記する

> `batch_mode=True` の場合はこのステップをスキップする。
> エントリは `run_batch()` の `deferred_changelog` に積まれ、
> `flush_batch_post_processing()` で一括書き込みされる。

月次ファイル（`_system/change_log_YYYY-MM.md`）に1行追記する。
ファイルが存在しない場合は新規作成する。

```python
from datetime import date
import os

def append_change_log(kb_root: str, entry: str) -> None:
    """
    _system/change_log_YYYY-MM.md に1行追記する。
    ファイル未存在の場合はヘッダ付きで新規作成。
    """
    today = date.today()
    log_filename = f"change_log_{today.strftime('%Y-%m')}.md"
    log_path = os.path.join(kb_root, "_system", log_filename)

    # ファイル未存在の場合はヘッダを作成
    if not os.path.exists(log_path):
        header = f"# KnowledgeBase 変更履歴 {today.strftime('%Y年%m月')}\n\n"
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(header)

    # 1行追記
    log_entry = f"- {today.strftime('%Y-%m-%d')} {entry}\n"
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(log_entry)
```

### 追記フォーマット

| 操作 | フォーマット例 |
|------|--------------|
| wiki追加 | `2026-05-01 [追加] kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md` |
| _overview.md作成 | `2026-05-01 [新規フォルダ] kyorindo/hr/regulations/ (_overview.md 作成)` |
| エラー | `2026-05-01 [エラー] route-binary.md 失敗: CX_roadmap_v4.pptx` |

### 実行

```python
# wikiファイル追加の記録
append_change_log(
    kb_root,
    f"[追加] {wiki_destination}{filename}"
)

# _overview.md 新規作成の記録（作成した場合のみ）
if overview_created:
    append_change_log(
        kb_root,
        f"[新規フォルダ] {wiki_destination} (_overview.md 作成)"
    )
```

---

## STEP 2.5: `processed-sources.yaml` に初期レコードを記録する

wiki 保存が完了したこのタイミングで処理状態を記録する。
`index_registered` / `binary_moved` は後続ステップ完了後に更新される。

> **batch_mode=True の場合（クレジット削減）**:
> ファイルごとに YAML 読み書きすると O(n²) の I/O が発生する。
> `batch_mode=True` 時はレコードをメモリ上の `batch_records_buffer` に積むだけにし、
> `flush_batch_post_processing()` がバッチ末尾で **1回だけ** ファイルに書き込む。
>
> ```python
> # batch_mode=True の場合: バッファに積む
> if batch_mode:
>     batch_records_buffer.append(new_record)   # flush で一括書き込み
>     return
> # batch_mode=False の場合: 即時書き込み（従来通り）
> upsert_processed_record(source_path, file_hash, wiki_path, today)
> ```
>
> `batch_records_buffer` は `run_batch()` が管理し、
> `flush_batch_post_processing()` の末尾で `upsert_all_processed_records(buffer)` を呼ぶ。

```python
import hashlib
import yaml
import time

PROCESSED_SOURCES_PATH = os.path.join(
    r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase",
    "_system", "processed-sources.yaml"
)

def upsert_processed_record(
    source_path: str,
    file_hash: str,
    wiki_path: str,
    processed_date: str,
    retries: int = 3,
    wait: int = 5,
) -> None:
    """
    processed-sources.yaml に初期レコードを追加（または既存レコードを更新）する。
    source_path をキーとして照合する。
    """
    # 既存データを読み込む
    records = []
    if os.path.exists(PROCESSED_SOURCES_PATH):
        try:
            with open(PROCESSED_SOURCES_PATH, "r", encoding="utf-8") as f:
                records = yaml.safe_load(f) or []
        except Exception:
            records = []

    # 既存レコードを検索
    idx = next((i for i, r in enumerate(records)
                if r.get("source_path") == source_path), None)

    new_record = {
        "source_path":       source_path,
        "file_hash":         file_hash,
        "wiki_path":         wiki_path,
        "processed_date":    processed_date,
        "index_registered":  False,   # STEP 3 完了後に True へ更新
        "binary_moved":      False,   # STEP 4 完了後に True へ更新（skip 時は "skipped"）
        "binary_destination": "",
        "source_deleted":    False,
    }

    if idx is not None:
        # 既存レコードを上書き（wiki 再処理ケース）
        records[idx] = new_record
    else:
        records.append(new_record)

    # ファイルに書き戻す
    os.makedirs(os.path.dirname(PROCESSED_SOURCES_PATH), exist_ok=True)
    for attempt in range(retries):
        try:
            with open(PROCESSED_SOURCES_PATH, "w", encoding="utf-8") as f:
                yaml.dump(records, f, allow_unicode=True, default_flow_style=False)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                raise RuntimeError("processed-sources.yaml への書き込みに失敗しました")


def update_processed_field(
    source_path: str,
    updates: dict,
    retries: int = 3,
    wait: int = 5,
) -> None:
    """
    processed-sources.yaml の特定レコードのフィールドを更新する。
    route-binary.md / index-builder.md の完了後に呼ぶ。
    """
    if not os.path.exists(PROCESSED_SOURCES_PATH):
        return

    for attempt in range(retries):
        try:
            with open(PROCESSED_SOURCES_PATH, "r", encoding="utf-8") as f:
                records = yaml.safe_load(f) or []

            for r in records:
                if r.get("source_path") == source_path:
                    r.update(updates)
                    break

            with open(PROCESSED_SOURCES_PATH, "w", encoding="utf-8") as f:
                yaml.dump(records, f, allow_unicode=True, default_flow_style=False)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                raise RuntimeError("processed-sources.yaml の更新に失敗しました")
```

### 実行

```python
today        = date.today().isoformat()
# source_path は batch-inbox 時は original_personal_path、通常時は inbox ファイル名
source_path  = original_personal_path if skip_route_binary else os.path.basename(original_file)
wiki_rel     = os.path.relpath(saved_path, kb_root).replace("\\", "/")

upsert_processed_record(
    source_path    = source_path,
    file_hash      = file_hash,      # batch-inbox 時のみ実値、通常時は空文字
    wiki_path      = wiki_rel,
    processed_date = today,
)

# batch-inbox の場合: route-binary をスキップするので binary_moved を "skipped" にしておく
if skip_route_binary:
    update_processed_field(source_path, {
        "binary_moved":      "skipped",
        "binary_destination": source_path,   # 元の場所のまま
    })
```

---

```python
# batch_mode=True の場合はスキップ（flush で一括書き込み）
if not batch_mode:
    append_change_log(kb_root, f"[追加] {wiki_destination}{filename}")
    if overview_created:
        append_change_log(kb_root, f"[新規フォルダ] {wiki_destination} (_overview.md 作成)")
```

---

## STEP 3: `index-builder.md` スキルを呼び出す

> `batch_mode=True` の場合はこのステップをスキップする。
> 全ファイル処理後に `flush_batch_post_processing()` が
> `index_builder_run(mode="add_batch", file_paths=[...])` を1回だけ呼ぶ。

ベクトルindex（`wiki-embeddings.npz`）に新規wikiファイルを追加登録する。

```python
# batch_mode=True の場合はスキップ（flush で一括）
if not batch_mode:
    idx_result = index_builder_run(mode="add", file_path=saved_path)
    if idx_result.get("status") == "success":
        update_processed_field(source_path, {"index_registered": True})
```

> `index-builder.md` の実装詳細はスキル8を参照。

---

index-builder 完了後、`processed-sources.yaml` の `index_registered` を更新する：

```python
idx_result = index_builder_run(mode="add", file_path=saved_path)
if idx_result.get("status") == "success":
    update_processed_field(source_path, {"index_registered": True})
```

---

## STEP 4: `route-binary.md` スキルを呼び出す

`skip_route_binary = True`（batch-inbox からの処理）の場合はこのステップをスキップする。
元ファイルは既に `00personal/` に存在するため移動不要。

```python
if skip_route_binary:
    # スキップ。binary_moved は STEP 2.5 で "skipped" 設定済み
    pass
else:
    # 通常の inbox-agent フロー: 元ファイルを 00personal/ へ移動
    # → route-binary.md を呼び出す
    #   入力: original_file（_inbox/ 内の元ファイルパス）
    #   動作: 00personal/ 配下への移動 + personal-index.yaml 更新
    #         + processed-sources.yaml の binary_moved / binary_destination 更新
    pass
```

> `route-binary.md` の実装詳細はスキル5を参照。

---

## STEP 5: 結果を出力する

```yaml
status: success
wiki_saved: "KnowledgeBase/kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md"
overview_created: false        # 新規フォルダで _overview.md を作成したか
change_log_updated: true       # change_log への記録完了
index_updated: true            # wiki-embeddings.npz の更新完了
original_moved: true           # 元ファイルの 00personal/ への移動完了（skip_route_binary=True 時は "skipped"）
processed_sources_updated: true  # processed-sources.yaml への記録完了
errors: []                     # エラーがあれば内容を記載
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `_overview.md` 書き込み失敗（WinError 5） | 5秒×3回リトライ → 失敗時は `errors` に記録してスキップ |
| `change_log` 書き込み失敗 | 同上 |
| `index-builder.md` 失敗 | `errors` に記録。wikiファイルは残す（次回の定期メンテで補完） |
| `route-binary.md` 失敗 | `errors` に記録。元ファイルは `_inbox/` に残す（手動対応を促す） |

**wikiファイルは削除しない**。エラー発生箇所のみ `errors` に記録してユーザーに通知する。

---

## 呼び出し元・呼び出し先

```
write-wiki.md
    └─→ place-wiki.md（本スキル）
            ├─→ index-builder.md（ベクトルindex更新）
            ├─→ route-binary.md（元ファイルを 00personal/ へ移動）※skip_route_binary=False 時のみ
            └─→ processed-sources.yaml（処理状態を記録）
```
