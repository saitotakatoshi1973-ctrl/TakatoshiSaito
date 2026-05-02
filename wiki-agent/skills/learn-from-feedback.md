# learn-from-feedback.md — フィードバック学習・ルール抽出スキル

## 概要

`feedback-log.md` を読み込み、分類修正パターンをLLMが分析します。
3回以上蓄積されたパターンからルール候補を生成し、
ユーザー承認後に `classification-hints.md` へ追記します。

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `maintenance-agent` | 月次自動実行 |
| ユーザー手動 | `record-feedback.md` の100件通知を受けて |

---

## STEP 1: `feedback-log.md` を読み込む

```python
import os
import re

FEEDBACK_LOG = (
    r"C:\Users\takatoshi-saito\OneDrive\00personal"
    r"\KnowledgeBase\_system\learning\feedback-log.md"
)
HINTS_FILE = (
    r"C:\Users\takatoshi-saito\OneDrive\00personal"
    r"\KnowledgeBase\_system\learning\classification-hints.md"
)

def load_feedback_entries(log_content: str) -> list[dict]:
    """
    feedback-log.md から個々の記録エントリを抽出する。
    [学習済み] タグが付いているエントリは除外する。
    """
    entries = []
    blocks = re.split(r'\n## \d{4}-\d{2}-\d{2}\n', '\n' + log_content)

    for block in blocks:
        if not block.strip():
            continue
        if '[学習済み]' in block:
            continue  # 処理済みはスキップ

        entry = {}
        for field, pattern in {
            'file_name':       r'- ファイル: (.+)',
            'source':          r'- 記録元: (.+)',
            'agent_judgment':  r'- エージェント判断: (.+)',
            'user_correction': r'- ユーザー修正: (.+)',
            'confidence':      r'- 信頼度スコア: (.+)',
            'method':          r'- 分類手法: (.+)',
            'comment':         r'- ユーザーコメント: (.+)',
        }.items():
            m = re.search(pattern, block)
            entry[field] = m.group(1).strip() if m else ''

        if entry.get('file_name'):
            entries.append(entry)

    return entries
```

---

## STEP 2: LLMがパターンを分析してルール候補を生成する

未処理エントリをLLMに渡し、scope/domain レベルの傾向を読み取ってルール候補を生成する。

### LLMへの指示

```
以下はwiki-agentの分類修正フィードバック一覧です。
ユーザーがエージェントの判断を修正したケースを分析し、
「3回以上同じ傾向がある」パターンを特定してルール候補を生成してください。

【分析観点】
- scope（kyorindo / tsuruha-hd / retail など）レベルの傾向
- domain（cx / it-systems / hr など）レベルの傾向
- ファイル種別（pptx / xlsx / eml など）と分類先の関係
- ユーザーコメントに共通するキーワード
- agent_judgment と user_correction の差異パターン

【フィードバック一覧】
{entries を番号付きで列挙}

【出力形式】
以下のJSONで出力してください（最大5件）:

[
  {
    "pattern_count": 4,
    "pattern_description": "経営会議向けpptxは management/reports/ に分類される傾向",
    "condition": "「経営会議」「役員」「社長報告」を含むファイル",
    "correct_destination": "kyorindo/management/reports/",
    "rule_table_row": "| 「経営会議」「役員」「社長報告」を含む | `kyorindo/management/reports/` |",
    "evidence_files": ["xxx.pptx", "yyy.pptx", "zzz.pptx", "www.pptx"]
  }
]

パターンが3回未満のものは含めないでください。
```

---

## STEP 3: ルール候補をユーザーに提示して承認を求める

最大5件を一覧表示し、承認・却下を確認する。

### ユーザーへの提示メッセージ

```
📚 分類学習の提案（{n}件）

以下のルール候補を classification-hints.md に追加しますか？
各行に「承認 / 却下」で回答してください。

━━━━━━━━━━━━━━━━━━━━━━━━━━

【候補1】根拠: {pattern_count}件の修正事例
パターン: {pattern_description}
追加するルール行:
  {rule_table_row}
→ 承認 / 却下？

━━━━━━━━━━━━━━━━━━━━━━━━━━

【候補2】根拠: {pattern_count}件の修正事例
...

━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## STEP 4: 承認されたルールを `classification-hints.md` に追記する

```python
import time

def append_rule(rule_table_row: str, section_header: str, retries: int = 3, wait: int = 5) -> None:
    """
    classification-hints.md の適切なセクションにルール行を追記する。
    セクションが存在しない場合は末尾に新規セクションを作成する。
    """
    with open(HINTS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 既存セクションに追記できるか確認
    if section_header in content:
        # セクション内の表の末尾に行を追加
        insert_pos = content.find(section_header)
        next_section = content.find('\n## ', insert_pos + 1)
        section_block = content[insert_pos:next_section] if next_section != -1 else content[insert_pos:]

        # 表の末尾（最後の `|` 行）を探して挿入
        table_end = section_block.rfind('\n|')
        abs_pos = insert_pos + table_end + 1
        new_content = content[:abs_pos] + '\n' + rule_table_row + content[abs_pos:]
    else:
        # 新規セクションを末尾に追加
        new_section = f"\n\n## {section_header}\n\n"
        new_section += "| 条件 | 分類先 |\n|------|--------|\n"
        new_section += rule_table_row + "\n"
        new_content = content.rstrip() + new_section

    for attempt in range(retries):
        try:
            with open(HINTS_FILE, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError("classification-hints.md への書き込みに失敗しました")
```

---

## STEP 5: 処理済みエントリに `[学習済み]` タグを付ける

承認・却下にかかわらず、今回提示した全エントリを処理済みにマークする。

```python
def mark_as_learned(log_content: str, evidence_files: list[str]) -> str:
    """
    根拠として使用したフィードバックエントリに [学習済み] タグを付与する。
    """
    for file_name in evidence_files:
        log_content = log_content.replace(
            f"- ファイル: {file_name}",
            f"- ファイル: {file_name} [学習済み]"
        )
    return log_content

def save_feedback_log(new_content: str, retries: int = 3, wait: int = 5) -> None:
    for attempt in range(retries):
        try:
            with open(FEEDBACK_LOG, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                raise RuntimeError("feedback-log.md の更新に失敗しました")
```

---

## STEP 6: メイン実行フロー

```python
def run() -> dict:
    # feedback-log.md を読み込み
    with open(FEEDBACK_LOG, 'r', encoding='utf-8') as f:
        log_content = f.read()

    entries = load_feedback_entries(log_content)

    if len(entries) < 3:
        return {
            "status": "skipped",
            "reason": f"未処理エントリが{len(entries)}件のみ（3件以上で分析を実施）",
            "entry_count": len(entries),
        }

    # LLMがパターン分析・ルール候補生成（STEP 2）
    candidates = llm_analyze_patterns(entries)  # 最大5件

    if not candidates:
        return {
            "status": "skipped",
            "reason": "3回以上のパターンが検出されませんでした",
            "entry_count": len(entries),
        }

    # ユーザーに提示・承認確認（STEP 3）
    approved = []
    rejected = []
    all_evidence = []

    for candidate in candidates:
        # ユーザーへの提示（同期質問）
        user_answer = ask_user_approval(candidate)
        all_evidence.extend(candidate['evidence_files'])

        if user_answer == 'approved':
            approved.append(candidate)
        else:
            rejected.append(candidate)

    # 承認済みルールを classification-hints.md に追記（STEP 4）
    for rule in approved:
        section = rule.get('section_header', '学習済みルール')
        append_rule(rule['rule_table_row'], section)

    # 処理済みエントリに [学習済み] タグを付与（STEP 5）
    updated_log = mark_as_learned(log_content, all_evidence)
    save_feedback_log(updated_log)

    return {
        "status": "success",
        "candidates_presented": len(candidates),
        "approved": len(approved),
        "rejected": len(rejected),
        "rules_added": [r['pattern_description'] for r in approved],
    }
```

---

## STEP 7: 結果を出力する

```yaml
status: success
candidates_presented: 3
approved: 2
rejected: 1
rules_added:
  - "経営会議向けpptxは management/reports/ に分類される傾向"
  - "ウエルシア主語のファイルは tsuruha-hd/subsidiaries/welcia/ に分類"
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `feedback-log.md` 読み込み失敗 | エラーを返して終了 |
| LLM パターン分析失敗 | エラーを返して終了（ルールは追記しない）|
| `classification-hints.md` 書き込み失敗 | 5秒×3回リトライ → 失敗時はエラーを記録 |
| `feedback-log.md` タグ付け失敗 | エラーを記録。ルール追記はロールバックしない |

---

## 呼び出し元・呼び出し先

```
maintenance-agent（月次）
ユーザー手動
    └─→ learn-from-feedback.md（本スキル）
            ├─→ classification-hints.md（承認済みルールを追記）
            └─→ feedback-log.md（[学習済み] タグを付与）
```
