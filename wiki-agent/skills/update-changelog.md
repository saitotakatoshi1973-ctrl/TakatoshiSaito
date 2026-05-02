# update-changelog.md — 変更履歴管理・圧縮スキル

## 概要

`change_log_YYYY-MM.md`（月次ファイル）を管理し、
3ヶ月経過したファイルをLLMが要約して年次ファイルに集約します。
月次ファイルはアーカイブとして `_system/archive/` に移動します。

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `maintenance-agent` | 月次（毎月1日） |

---

## ファイル構成

```
KnowledgeBase/_system/
├── change_log.md              # 構造変更・大規模変更のみ記録（手動管理）
├── change_log_2026-03.md      # 月次詳細ログ（3ヶ月以内）
├── change_log_2026-04.md      # 月次詳細ログ（3ヶ月以内）
├── change_log_2026-05.md      # 月次詳細ログ（最新）
├── change_log_2026.md         # 年次サマリー（3ヶ月経過分を圧縮）← このスキルが生成
└── archive/
    └── change_log_2026-02.md  # 圧縮済みアーカイブ
```

---

## STEP 1: 圧縮対象ファイルを特定する

```python
import os
import re
import glob
from datetime import date, timedelta

KB_SYSTEM = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase\_system"

def find_compressible_logs() -> list[str]:
    """
    3ヶ月以上前の change_log_YYYY-MM.md を返す。
    archive/ 配下のファイルは除外する。
    """
    today = date.today()
    cutoff = today.replace(day=1) - timedelta(days=1)   # 先月末
    cutoff = (cutoff.replace(day=1) - timedelta(days=1)).replace(day=1)  # 3ヶ月前の月初
    # 3ヶ月前 = today の月 - 3
    y, m = today.year, today.month
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    cutoff = date(y, m, 1)

    pattern = os.path.join(KB_SYSTEM, "change_log_????-??.md")
    targets = []

    for path in sorted(glob.glob(pattern)):
        fname = os.path.basename(path)
        match = re.search(r'change_log_(\d{4})-(\d{2})\.md', fname)
        if not match:
            continue
        file_year  = int(match.group(1))
        file_month = int(match.group(2))
        file_date  = date(file_year, file_month, 1)

        if file_date < cutoff:
            targets.append(path)

    return targets
```

---

## STEP 2: 月次ファイルの内容を読み込む

```python
def read_log_file(log_path: str) -> str:
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"（読み込み失敗: {e}）"
```

---

## STEP 3: LLMが月次サマリーを生成する

各月次ファイルの内容を LLM に渡し、2〜4文の要約を生成する。

### LLMへの指示

```
以下は KnowledgeBase wiki の {YYYY}年{MM}月 の変更ログです。
主な変更内容を2〜4文の日本語で要約してください。

【要約ルール】
- 追加・削除・移動したファイル数を含める
- 特に重要な変更（新規カテゴリ作成・大量追加・削除）を優先して記述
- 細かいファイル名は省略し、カテゴリ・フォルダ名で表現する
- 文体は「〜した。」調で統一

【変更ログ】
{log_content}

【出力形式】
summary: "（2〜4文の要約）"
added_count: （追加件数）
removed_count: （削除件数）
key_changes:
  - "（主要変更1）"
  - "（主要変更2）"
```

### サマリー例

```
summary: "kyorindo/cx/ 配下に戦略資料・議事録を中心に12件追加した。
tsuruha-hd/subsidiaries/ に welcia/ サブフォルダを新設し4件移行した。
旧フォルダ構成の整理により重複ファイル2件を削除した。"
added_count: 12
removed_count: 2
key_changes:
  - "kyorindo/cx/strategy/ に CX_roadmap v4 追加"
  - "tsuruha-hd/subsidiaries/welcia/ 新設"
```

---

## STEP 4: 年次ファイルにサマリーを追記する

`change_log_YYYY.md` が存在しない場合は新規作成する。

```python
def append_to_annual_log(
    year: int,
    month: int,
    summary_text: str,
    added: int,
    removed: int,
    key_changes: list[str]
) -> None:
    annual_path = os.path.join(KB_SYSTEM, f"change_log_{year}.md")

    # ファイル未存在時はヘッダを作成
    if not os.path.exists(annual_path):
        header = f"# KnowledgeBase 変更履歴 {year}年（年次サマリー）\n\n"
        header += f"> 各月の詳細ログは `_system/archive/change_log_{year}-MM.md` を参照。\n\n"
        with open(annual_path, 'w', encoding='utf-8') as f:
            f.write(header)

    # 月次サマリーブロックを追記
    key_lines = "\n".join([f"  - {k}" for k in key_changes])
    entry = f"""## {year}年{month:02d}月

{summary_text}

- 追加: {added}件 / 削除: {removed}件
- 主な変更:
{key_lines}

---

"""
    with open(annual_path, 'a', encoding='utf-8') as f:
        f.write(entry)
```

---

## STEP 5: 月次ファイルをアーカイブに移動する

```python
import shutil
import time

def archive_log_file(log_path: str, retries: int = 3, wait: int = 5) -> str:
    """
    月次ファイルを _system/archive/ に移動する。
    OneDrive ロック時はリトライ。
    戻り値: 移動後のパス
    """
    archive_dir = os.path.join(KB_SYSTEM, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    dest_path = os.path.join(archive_dir, os.path.basename(log_path))

    # 同名ファイルが archive に既にある場合は _v2 を付与
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(dest_path)
        version = 2
        while os.path.exists(f"{base}_v{version}{ext}"):
            version += 1
        dest_path = f"{base}_v{version}{ext}"

    for attempt in range(retries):
        try:
            shutil.move(log_path, dest_path)
            return dest_path
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError(f"アーカイブ移動に失敗: {log_path}")
```

---

## STEP 6: メイン実行フロー

```python
def run() -> dict:
    targets = find_compressible_logs()

    if not targets:
        return {"status": "success", "message": "圧縮対象なし", "processed": 0}

    results = []
    errors  = []

    for log_path in targets:
        fname   = os.path.basename(log_path)
        match   = re.search(r'change_log_(\d{4})-(\d{2})\.md', fname)
        year    = int(match.group(1))
        month   = int(match.group(2))

        # 内容読み込み
        content = read_log_file(log_path)

        # LLM でサマリー生成（STEP 3 のプロンプトを使用）
        summary_result = llm_summarize(year, month, content)

        # 年次ファイルに追記
        try:
            append_to_annual_log(
                year, month,
                summary_result["summary"],
                summary_result["added_count"],
                summary_result["removed_count"],
                summary_result["key_changes"],
            )
        except Exception as e:
            errors.append({"file": fname, "step": "annual_append", "error": str(e)})
            continue

        # アーカイブに移動
        try:
            archived_path = archive_log_file(log_path)
            results.append({
                "month": f"{year}-{month:02d}",
                "archived_to": archived_path,
                "added": summary_result["added_count"],
                "removed": summary_result["removed_count"],
            })
        except Exception as e:
            errors.append({"file": fname, "step": "archive_move", "error": str(e)})

    return {
        "status": "success" if not errors else "partial",
        "processed": len(results),
        "results": results,
        "errors": errors,
    }
```

---

## STEP 7: 結果を出力する

```yaml
status: success
processed: 2
results:
  - month: "2026-02"
    archived_to: "_system/archive/change_log_2026-02.md"
    added: 8
    removed: 1
  - month: "2026-03"
    archived_to: "_system/archive/change_log_2026-03.md"
    added: 12
    removed: 2
errors: []
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| 月次ファイル読み込み失敗 | `errors` に記録してスキップ |
| LLM サマリー生成失敗 | 件数カウントのみの最小サマリーで代替 |
| 年次ファイル書き込み失敗（WinError 5） | 5秒×3回リトライ |
| アーカイブ移動失敗 | `errors` に記録。月次ファイルはそのまま残す |

---

## 呼び出し元・呼び出し先

```
maintenance-agent（月次）
    └─→ update-changelog.md（本スキル）
            （呼び出し先なし：単独完結）
```
