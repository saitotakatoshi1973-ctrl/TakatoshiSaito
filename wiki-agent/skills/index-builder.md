# index-builder.md — ベクトルindex生成・更新スキル

## 概要

`wiki-embeddings.npz` を生成・更新します。
`analyze.md`（分類時の類似検索）と `web-search.md`（重複チェック）が参照します。

---

## 実行モード

| モード | 呼び出し元 | 動作 |
|--------|-----------|------|
| `add` | `place-wiki.md`（都度） | 新規ファイルのembeddingを追加 ＋ 欠損チェック |
| `batch_add` | `flush_batch_post_processing()`（バッチ末尾） | 複数ファイルを npz load/save 各1回で一括追加 ② |
| `rebuild` | `maintenance-agent`（週次） | KnowledgeBase/ 全体を走査して全件再構築 |

---

## 入力

```yaml
# 差分追加モード（add）
mode: "add"
file_path: "KnowledgeBase/kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md"

# 全件再構築モード（rebuild）
mode: "rebuild"
file_path: null
```

---

## 共通設定

```python
import numpy as np
import os
import re
import yaml

KB_ROOT      = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"
NPZ_PATH     = os.path.join(KB_ROOT, "_system", "wiki-embeddings.npz")
MODEL_NAME   = "paraphrase-multilingual-MiniLM-L12-v2"
EMBED_CHARS  = 500   # 本文冒頭の最大文字数
SYSTEM_DIRS  = {"_inbox", "_system"}  # index対象外フォルダ
```

---

## STEP 1: モデルを初期化する

```python
from sentence_transformers import SentenceTransformer

def load_model() -> SentenceTransformer:
    """
    sentence-transformers モデルをロードする。
    初回はダウンロードが発生する（約120MB）。
    """
    return SentenceTransformer(MODEL_NAME)
```

---

## STEP 2: テキスト抽出（タイトル＋本文冒頭500文字）

```python
def extract_embed_text(md_path: str) -> str:
    """
    Markdown ファイルから embedding 用テキストを生成する。
    Front-matter の title ＋ 本文冒頭500文字を結合して返す。
    """
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Front-matter からタイトルを取得
        title = ""
        fm_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
        if fm_match:
            fm = yaml.safe_load(fm_match.group(1)) or {}
            title = fm.get("title", "")
            body = content[fm_match.end():]
        else:
            body = content

        # 本文冒頭500文字（見出し記号・改行を除去）
        body_clean = re.sub(r'#+\s+', '', body).strip()
        body_excerpt = body_clean[:EMBED_CHARS]

        return f"{title}\n{body_excerpt}".strip()

    except Exception as e:
        return ""  # 読み込み失敗時は空文字（後でスキップ）
```

---

## STEP 3: 既存 index の読み込み

```python
def load_index() -> tuple[list[str], np.ndarray]:
    """
    wiki-embeddings.npz を読み込んで (paths, embeddings) を返す。
    ファイルが存在しない場合は空のリスト・配列を返す。
    """
    if not os.path.exists(NPZ_PATH):
        return [], np.empty((0, 384), dtype=np.float32)  # MiniLM の次元数=384

    data = np.load(NPZ_PATH, allow_pickle=True)
    paths      = list(data["paths"])
    embeddings = data["embeddings"]
    return paths, embeddings
```

---

## STEP 4: 欠損チェック（削除されたファイルを除去）

**差分追加・全件再構築の両モードで実行する。**

```python
def remove_missing(paths: list[str], embeddings: np.ndarray) -> tuple[list[str], np.ndarray]:
    """
    npz に記録されているパスのうち、実際には存在しないファイルを除去する。
    paths は KB_ROOT からの相対パスで格納されている前提。
    """
    valid_mask = []
    removed = []

    for path in paths:
        abs_path = os.path.join(KB_ROOT, path)
        if os.path.exists(abs_path):
            valid_mask.append(True)
        else:
            valid_mask.append(False)
            removed.append(path)

    if removed:
        print(f"[欠損除去] {len(removed)} 件を index から削除: {removed}")

    valid_idx = [i for i, v in enumerate(valid_mask) if v]
    new_paths      = [paths[i] for i in valid_idx]
    new_embeddings = embeddings[valid_idx] if len(valid_idx) > 0 else np.empty((0, 384), dtype=np.float32)

    return new_paths, new_embeddings
```

---

## STEP 5-A: 差分追加モード（add）

```python
def add_to_index(model: SentenceTransformer, file_path: str) -> dict:
    """
    1件の wiki ファイルを index に追加する。
    file_path: KnowledgeBase/ 配下の絶対パス
    """
    # 相対パスに変換（npz 内での識別子）
    rel_path = os.path.relpath(file_path, KB_ROOT).replace("\\", "/")

    # 既存 index を読み込み
    paths, embeddings = load_index()

    # 欠損チェック（削除ファイルを除去）
    paths, embeddings = remove_missing(paths, embeddings)

    # 既に登録済みの場合は上書き更新
    if rel_path in paths:
        idx = paths.index(rel_path)
        paths.pop(idx)
        embeddings = np.delete(embeddings, idx, axis=0)

    # テキスト抽出 → embedding 生成
    text = extract_embed_text(file_path)
    if not text:
        return {"status": "skipped", "reason": "テキスト抽出失敗", "path": rel_path}

    new_emb = model.encode(text, normalize_embeddings=True).astype(np.float32)

    # index に追加
    paths.append(rel_path)
    if embeddings.shape[0] == 0:
        embeddings = new_emb.reshape(1, -1)
    else:
        embeddings = np.vstack([embeddings, new_emb.reshape(1, -1)])

    # 保存
    save_index(paths, embeddings)

    return {
        "status": "success",
        "mode": "add",
        "path": rel_path,
        "total_entries": len(paths),
    }
```

---

## STEP 5-A2: バッチ追加モード（batch_add）

`place-wiki.md` から1件ずつ呼ばれる `add` モードに代わり、
バッチ処理終了後に **まとめて1回** npz を更新するモード。
`flush_batch_post_processing()` から呼び出される。

```python
def batch_add_to_index(model: SentenceTransformer, file_paths: list[str]) -> dict:
    """
    複数の wiki ファイルを index に一括追加する。
    npz の load / save を各1回で済ませる（add を n 回呼ぶより大幅に I/O 削減）。

    file_paths: KnowledgeBase/ 配下の絶対パスリスト
    """
    # 既存 index を1回だけ読み込み
    paths, embeddings = load_index()
    paths, embeddings = remove_missing(paths, embeddings)

    added   = []
    skipped = []

    for file_path in file_paths:
        if not os.path.exists(file_path):
            skipped.append({"path": file_path, "reason": "ファイルが存在しない"})
            continue

        rel_path = os.path.relpath(file_path, KB_ROOT).replace("\\", "/")

        # 既に登録済みの場合は上書き更新（削除してから再追加）
        if rel_path in paths:
            idx = paths.index(rel_path)
            paths.pop(idx)
            embeddings = np.delete(embeddings, idx, axis=0)

        text = extract_embed_text(file_path)
        if not text:
            skipped.append({"path": rel_path, "reason": "テキスト抽出失敗"})
            continue

        new_emb = model.encode(text, normalize_embeddings=True).astype(np.float32)
        paths.append(rel_path)
        if embeddings.shape[0] == 0:
            embeddings = new_emb.reshape(1, -1)
        else:
            embeddings = np.vstack([embeddings, new_emb.reshape(1, -1)])
        added.append(rel_path)

    # 全件追加後に1回だけ保存
    if added:
        save_index(paths, embeddings)

    return {
        "status": "success",
        "mode": "batch_add",
        "added": len(added),
        "skipped": len(skipped),
        "total_entries": len(paths),
        "skipped_files": skipped,
    }
```

---

## STEP 5-B: 全件再構築モード（rebuild）

```python
def rebuild_index(model: SentenceTransformer) -> dict:
    """
    KnowledgeBase/ 全体を走査して wiki-embeddings.npz を再構築する。
    _inbox/ と _system/ は対象外。
    """
    all_paths = []
    all_embeddings = []
    skipped = []

    for root, dirs, files in os.walk(KB_ROOT):
        # _inbox/ と _system/ を走査から除外
        dirs[:] = [d for d in dirs if d not in SYSTEM_DIRS]

        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname == "_overview.md":
                continue  # _overview.md は index 対象外

            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, KB_ROOT).replace("\\", "/")

            text = extract_embed_text(abs_path)
            if not text:
                skipped.append(rel_path)
                continue

            emb = model.encode(text, normalize_embeddings=True).astype(np.float32)
            all_paths.append(rel_path)
            all_embeddings.append(emb)

    if all_embeddings:
        embeddings = np.vstack(all_embeddings)
    else:
        embeddings = np.empty((0, 384), dtype=np.float32)

    save_index(all_paths, embeddings)

    return {
        "status": "success",
        "mode": "rebuild",
        "total_entries": len(all_paths),
        "skipped": len(skipped),
        "skipped_files": skipped,
    }
```

---

## STEP 6: index を保存する

```python
import time

def save_index(paths: list[str], embeddings: np.ndarray, retries: int = 3, wait: int = 5) -> None:
    """
    wiki-embeddings.npz に保存する。OneDrive ロック時はリトライ。
    """
    os.makedirs(os.path.dirname(NPZ_PATH), exist_ok=True)

    for attempt in range(retries):
        try:
            np.savez_compressed(
                NPZ_PATH,
                paths=np.array(paths, dtype=object),
                embeddings=embeddings.astype(np.float32),
            )
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError(f"wiki-embeddings.npz の保存に失敗しました")
```

---

## STEP 7: メイン呼び出し関数

```python
def run(mode: str, file_path: str = None, file_paths: list[str] = None) -> dict:
    """
    index-builder.md のエントリポイント。
    mode: "add" | "batch_add" | "rebuild"
    file_path:  add モード時のみ必要（絶対パス）
    file_paths: batch_add モード時のみ必要（絶対パスリスト）
    """
    model = load_model()

    if mode == "add":
        if not file_path or not os.path.exists(file_path):
            return {"status": "error", "reason": f"ファイルが存在しません: {file_path}"}
        return add_to_index(model, file_path)

    elif mode == "batch_add":
        # ② バッチ追加モード: flush_batch_post_processing() から呼び出される
        # npz の load/save を1回に集約し、n 件追加でも I/O コストを O(1) に抑える
        if not file_paths:
            return {"status": "skipped", "reason": "file_paths が空"}
        return batch_add_to_index(model, file_paths)

    elif mode == "rebuild":
        return rebuild_index(model)

    else:
        return {"status": "error", "reason": f"不明なモード: {mode}"}
```

---

## STEP 8: 結果を出力する

```yaml
# 差分追加モードの場合
status: success
mode: add
path: "kyorindo/cx/strategy/CX推進ロードマップ_v4_20260501.md"
total_entries: 87

# バッチ追加モードの場合（② flush_batch_post_processing から呼び出し）
status: success
mode: batch_add
added: 8
skipped: 0
total_entries: 95

# 全件再構築モードの場合
status: success
mode: rebuild
total_entries: 87
skipped: 2
skipped_files:
  - "kyorindo/cx/progress/議事録_20260401.md"   # テキスト抽出失敗
```

---

## 初回セットアップ

wiki-agent を初めて使う際は `rebuild` モードで初期index を生成する：

```
index-builder.md を起動する
mode: rebuild
→ KnowledgeBase/ 全体をスキャンして wiki-embeddings.npz を生成
```

---

## 依存ライブラリ

```bash
pip install sentence-transformers numpy
```

| ライブラリ | 用途 |
|-----------|------|
| `sentence-transformers` | embedding 生成（`paraphrase-multilingual-MiniLM-L12-v2`）|
| `numpy` | npz 形式での保存・読み込み |

---

## 呼び出し元・呼び出し先

```
place-wiki.md（新規ファイル追加後）→ index-builder.md（mode: add）
maintenance-agent（週次）         → index-builder.md（mode: rebuild）
analyze.md（類似検索）            → wiki-embeddings.npz を直接参照
web-search.md（重複チェック）     → wiki-embeddings.npz を直接参照
```
