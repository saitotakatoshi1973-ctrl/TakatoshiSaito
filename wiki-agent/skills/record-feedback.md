# record-feedback.md — 分類フィードバック記録スキル

## 概要

エージェントの分類判断をユーザーが修正したとき、
その差分を `feedback-log.md` に即時記録します。
同じファイルの重複記録を防止し、100件超過時はユーザーに通知します。

---

## 呼び出しパターン

| 呼び出し元 | タイミング | source 値 |
|-----------|-----------|-----------|
| `analyze.md`（STEP 7） | wiki分類先をユーザーが修正したとき | `analyze` |
| `route-binary.md`（STEP 3-2） | 00personal/ 移動先をユーザーが確認したとき | `route_binary` |

---

## 入力

```yaml
# analyze.md からの呼び出し例
source: "analyze"
file_name: "CX_roadmap_v4.pptx"
agent_judgment: "kyorindo/cx/strategy/"
user_correction: "kyorindo/management/reports/"
classification_confidence: 6
classification_method: "llm_scoring"
user_comment: "経営会議向けの資料のため"

# route-binary.md からの呼び出し例
source: "route_binary"
file_name: "CX_roadmap_v4.pptx"
agent_judgment: "（候補なし）"
user_correction: "09_InformationOrganization/杏林堂/CX推進/"
classification_confidence: null
classification_method: null
user_comment: ""
```

---

## STEP 1: `feedback-log.md` を読み込む

```python
import os
import re
from datetime import date

FEEDBACK_LOG = (
    r"C:\Users\takatoshi-saito\OneDrive\00personal"
    r"\KnowledgeBase\_system\learning\feedback-log.md"
)

def load_feedback_log() -> str:
    if not os.path.exists(FEEDBACK_LOG):
        return ""
    with open(FEEDBACK_LOG, 'r', encoding='utf-8') as f:
        return f.read()
```

---

## STEP 2: 重複チェック

同じ `file_name` の記録が既に存在する場合はスキップする。

```python
def is_duplicate(log_content: str, file_name: str) -> bool:
    """
    feedback-log.md に同一ファイル名の記録が存在するか確認する。
    """
    return f"- ファイル: {file_name}" in log_content
```

重複検出時の出力：

```yaml
status: skipped
reason: "同一ファイルの記録が既に存在します"
file_name: "CX_roadmap_v4.pptx"
```

---

## STEP 3: 件数カウント

```python
def count_entries(log_content: str) -> int:
    """
    feedback-log.md の記録件数をカウントする。
    「- ファイル:」行の数を数える。
    """
    return len(re.findall(r'^- ファイル:', log_content, re.MULTILINE))
```

---

## STEP 4: フィードバックエントリを生成する

共通フォーマットで記録エントリを生成する。

```python
def build_entry(
    source: str,
    file_name: str,
    agent_judgment: str,
    user_correction: str,
    confidence: int | None,
    method: str | None,
    user_comment: str,
) -> str:
    today = date.today().isoformat()

    source_label = {
        "analyze":      "wiki分類（analyze.md）",
        "route_binary": "00personal振り分け（route-binary.md）",
    }.get(source, source)

    confidence_str = str(confidence) if confidence is not None else "N/A"
    method_str     = method if method else "N/A"
    comment_str    = user_comment if user_comment else "（コメントなし）"

    return f"""
## {today}
- ファイル: {file_name}
- 記録元: {source_label}
- エージェント判断: {agent_judgment}
- ユーザー修正: {user_correction}
- 信頼度スコア: {confidence_str}
- 分類手法: {method_str}
- ユーザーコメント: {comment_str}
"""
```

---

## STEP 5: `feedback-log.md` に追記する

```python
import time

def append_entry(entry: str, retries: int = 3, wait: int = 5) -> None:
    """
    feedback-log.md にエントリを追記する。OneDrive ロック時はリトライ。
    """
    for attempt in range(retries):
        try:
            with open(FEEDBACK_LOG, 'a', encoding='utf-8') as f:
                f.write(entry)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError("feedback-log.md への書き込みに失敗しました")
```

---

## STEP 6: 件数超過チェック（100件超過でユーザーに通知）

```python
def check_overflow(count_after: int) -> str | None:
    """
    記録後の件数が100件を超えた場合、通知メッセージを返す。
    """
    if count_after > 100:
        return (
            f"⚠️ feedback-log.md の記録が {count_after} 件に達しました。\n"
            f"`learn-from-feedback.md` を実行してルール抽出・整理することをお勧めします。"
        )
    return None
```

---

## STEP 7: メイン実行フロー

```python
def run(
    source: str,
    file_name: str,
    agent_judgment: str,
    user_correction: str,
    classification_confidence: int | None = None,
    classification_method: str | None = None,
    user_comment: str = "",
) -> dict:

    # 読み込み
    log_content = load_feedback_log()

    # 重複チェック
    if is_duplicate(log_content, file_name):
        return {
            "status": "skipped",
            "reason": "同一ファイルの記録が既に存在します",
            "file_name": file_name,
        }

    # エントリ生成
    entry = build_entry(
        source, file_name,
        agent_judgment, user_correction,
        classification_confidence, classification_method,
        user_comment,
    )

    # 追記
    append_entry(entry)

    # 件数チェック
    count_before = count_entries(log_content)
    count_after  = count_before + 1
    overflow_msg = check_overflow(count_after)

    return {
        "status": "success",
        "file_name": file_name,
        "total_entries": count_after,
        "overflow_warning": overflow_msg,
    }
```

---

## STEP 8: 結果を出力する

```yaml
# 正常記録
status: success
file_name: "CX_roadmap_v4.pptx"
total_entries: 42
overflow_warning: null

# 100件超過時
status: success
file_name: "CX_roadmap_v4.pptx"
total_entries: 101
overflow_warning: "⚠️ feedback-log.md の記録が101件に達しました。learn-from-feedback.md を実行してルール抽出・整理することをお勧めします。"

# 重複スキップ
status: skipped
reason: "同一ファイルの記録が既に存在します"
file_name: "CX_roadmap_v4.pptx"
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `feedback-log.md` 読み込み失敗 | 空ファイルとして扱い処理続行 |
| 書き込み失敗（WinError 5） | 5秒×3回リトライ → 失敗時はエラーを返す |

---

## 呼び出し元・呼び出し先

```
analyze.md（STEP 7: ユーザー修正時）
route-binary.md（STEP 3-2: ユーザー確認後）
    └─→ record-feedback.md（本スキル）
            └─→ （呼び出し先なし）
                 ※ 100件超過時はユーザーへの通知のみ
                 ※ ルール抽出は learn-from-feedback.md が担当
```
