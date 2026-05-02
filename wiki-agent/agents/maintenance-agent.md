# maintenance-agent.md — 定期メンテナンスエージェント

## 概要

週次・月次のメンテナンスタスクをまとめて実行します。
ユーザーが「wiki週次メンテナンス実行」などと呼びかけて起動します。
エラーが発生してもスキップして続行し、最後に結果をまとめて報告します。

---

## 起動方法

Claude Code のチャットで以下のように呼びかけてください：

| 呼びかけ例 | 実行内容 |
|-----------|---------|
| `wiki週次メンテナンス実行` | 週次タスクのみ実行 |
| `wiki月次メンテナンス実行` | 月次タスクのみ実行 |
| `wikiメンテナンス全部実行` | 週次 ＋ 月次を全て実行 |
| `wikiメンテナンス実行` | → どちらか確認してから実行 |

---

## タスク一覧

### 週次タスク（毎週実行）

| 順序 | スキル | 内容 |
|------|-------|------|
| 1 | `index-builder.md` | KnowledgeBase/ 全体の index を再構築（rebuild） |
| 2 | `update-overview.md` | 全フォルダの `_overview.md` を更新 |
| 3 | `sync-personal.md` | 00personal/ フォルダ構成を personal-index.yaml に同期 |
| 4 | `sync-wiki.md` | KnowledgeBase/ に直接追加されたファイルを検知・後処理 |
| 5 | `check-integrity.md` | Front-matter 欠落・index 未登録・空ファイルを検査・修正 |

### 月次タスク（毎月実行）

| 順序 | スキル | 内容 |
|------|-------|------|
| 6 | `update-changelog.md` | 3ヶ月経過の月次ログを年次ファイルに圧縮・アーカイブ |
| 7 | `learn-from-feedback.md` | フィードバックログから分類ルール候補を抽出・提案 |

---

## 実行モードと起動フロー

```python
from datetime import date

def determine_mode(user_input: str) -> str:
    """
    ユーザーの発言からモードを判定する。
    戻り値: "weekly" | "monthly" | "all" | "ask"
    """
    if "週次" in user_input:
        return "weekly"
    if "月次" in user_input:
        return "monthly"
    if "全部" in user_input or "すべて" in user_input:
        return "all"
    return "ask"   # 不明な場合はユーザーに確認

def resolve_mode(mode: str) -> str:
    """
    "ask" の場合、ユーザーに週次/月次/全部を確認する。
    """
    if mode != "ask":
        return mode

    # ユーザーへの確認メッセージ
    ask_user(
        "どのメンテナンスを実行しますか？\n"
        "  1. 週次タスクのみ（index再構築・overview更新・sync・整合性チェック）\n"
        "  2. 月次タスクのみ（changelog圧縮・フィードバック学習）\n"
        "  3. 全部（週次 ＋ 月次）"
    )
    # ユーザー回答に応じて "weekly" / "monthly" / "all" を返す
```

---

## メイン実行フロー

```python
def run(mode: str) -> dict:
    today   = date.today().isoformat()
    results = {}
    errors  = []

    # 実行するタスクリストを組み立てる
    tasks = []
    if mode in ("weekly", "all"):
        tasks += ["index_builder", "update_overview", "sync_personal", "sync_wiki", "check_integrity"]
    if mode in ("monthly", "all"):
        tasks += ["update_changelog", "learn_from_feedback"]

    # 各タスクを順番に実行
    for task in tasks:
        print(f"▶ {TASK_LABELS[task]} を実行中...")
        try:
            result = TASK_RUNNERS[task]()
            results[task] = result
            print(f"  ✅ {TASK_LABELS[task]} 完了")
        except Exception as e:
            errors.append({"task": task, "error": str(e)})
            print(f"  ❌ {TASK_LABELS[task]} 失敗: {e}")

    # ログ記録
    log_entry = build_log_entry(today, mode, results, errors)
    append_maintenance_log(log_entry)
    compress_old_log_entries()   # 3ヶ月超えのエントリをアーカイブ

    return {
        "status":   "success" if not errors else "partial",
        "mode":     mode,
        "date":     today,
        "results":  results,
        "errors":   errors,
    }


# タスク名 → 表示ラベル
TASK_LABELS = {
    "index_builder":      "index 再構築（index-builder rebuild）",
    "update_overview":    "overview 全更新（update-overview）",
    "sync_personal":      "personal 同期（sync-personal）",
    "sync_wiki":          "wiki 同期（sync-wiki）",
    "check_integrity":    "整合性チェック（check-integrity）",
    "update_changelog":   "changelog 圧縮（update-changelog）",
    "learn_from_feedback":"フィードバック学習（learn-from-feedback）",
}
```

---

## ログ管理

### ログファイルパス

```python
import os

KB_SYSTEM    = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase\_system"
LOG_PATH     = os.path.join(KB_SYSTEM, "maintenance-log.md")
ARCHIVE_DIR  = os.path.join(KB_SYSTEM, "archive")
```

### ログエントリの形式

```markdown
## 2026-05-01（週次）

| タスク | 結果 | 詳細 |
|-------|------|------|
| index 再構築 | ✅ | 87件 / スキップ0件 |
| overview 全更新 | ✅ | 12フォルダ更新 |
| personal 同期 | ✅ | 変更なし |
| wiki 同期 | ✅ | 未登録2件を処理 |
| 整合性チェック | ✅ | Front-matter補完1件・空ファイル0件 |

エラー: なし

---
```

### ログ追記処理

```python
import time

def build_log_entry(today: str, mode: str, results: dict, errors: list) -> str:
    mode_label = {"weekly": "週次", "monthly": "月次", "all": "週次＋月次"}.get(mode, mode)
    lines = [f"## {today}（{mode_label}）\n"]
    lines.append("| タスク | 結果 | 詳細 |")
    lines.append("|-------|------|------|")

    for task, result in results.items():
        label  = TASK_LABELS.get(task, task)
        status = "✅" if result.get("status") in ("success", "skipped") else "⚠️"
        detail = summarize_result(task, result)
        lines.append(f"| {label} | {status} | {detail} |")

    for err in errors:
        label = TASK_LABELS.get(err["task"], err["task"])
        lines.append(f"| {label} | ❌ | {err['error']} |")

    lines.append(f"\nエラー: {'なし' if not errors else f'{len(errors)}件'}\n\n---\n")
    return "\n".join(lines)


def append_maintenance_log(entry: str, retries: int = 3, wait: int = 5) -> None:
    """maintenance-log.md に追記する。OneDrive ロック時はリトライ。"""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    # ファイルが存在しない場合はヘッダを作成
    if not os.path.exists(LOG_PATH):
        header = "# KnowledgeBase メンテナンスログ\n\n"
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write(header)

    for attempt in range(retries):
        try:
            with open(LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(entry)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                raise RuntimeError("maintenance-log.md への書き込みに失敗しました")
```

### ログ圧縮（3ヶ月超えをアーカイブ）

```python
import re
from datetime import date, timedelta

def compress_old_log_entries() -> None:
    """
    maintenance-log.md から3ヶ月超えのエントリを抽出し、
    _system/archive/maintenance-log-YYYY.md に移動する。
    本体ファイルは直近3ヶ月分のみ残す。
    """
    if not os.path.exists(LOG_PATH):
        return

    with open(LOG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    today   = date.today()
    y, m    = today.year, today.month
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    cutoff = date(y, m, 1)

    # エントリを日付ごとに分割
    # パターン: "## YYYY-MM-DD（..."
    blocks = re.split(r'(?=^## \d{4}-\d{2}-\d{2})', content, flags=re.MULTILINE)

    keep    = []
    archive = {}   # year → list of blocks

    for block in blocks:
        if not block.strip():
            continue
        m = re.match(r'^## (\d{4})-(\d{2})-(\d{2})', block)
        if not m:
            keep.append(block)   # ヘッダ行など
            continue

        entry_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if entry_date >= cutoff:
            keep.append(block)
        else:
            year = entry_date.year
            archive.setdefault(year, []).append(block)

    # アーカイブファイルに追記
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    for year, year_blocks in archive.items():
        archive_path = os.path.join(ARCHIVE_DIR, f"maintenance-log-{year}.md")
        archive_header = f"# KnowledgeBase メンテナンスログ {year}年（アーカイブ）\n\n"
        if not os.path.exists(archive_path):
            with open(archive_path, 'w', encoding='utf-8') as f:
                f.write(archive_header)
        with open(archive_path, 'a', encoding='utf-8') as f:
            f.write("".join(year_blocks))

    # 本体ファイルを直近3ヶ月分のみで上書き
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write("".join(keep))
```

---

## 完了レポート（ユーザーへの通知）

```
🔧 メンテナンス完了（週次）

✅ index 再構築       → 87件登録 / スキップ0件
✅ overview 全更新    → 12フォルダ更新
✅ personal 同期      → 変更なし
✅ wiki 同期          → 未登録2件を処理
✅ 整合性チェック     → Front-matter補完1件・空ファイル0件

エラー: なし
ログ保存: KnowledgeBase/_system/maintenance-log.md
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| 各スキルの実行失敗 | スキップして次のタスクへ。エラー内容をログに記録 |
| maintenance-log.md 書き込み失敗 | 5秒×3回リトライ → 失敗時は警告のみ（処理は継続） |
| ログ圧縮失敗 | 警告のみ（次回実行時に再試行） |
| learn-from-feedback.md の承認待ち | ユーザーとのやり取りが発生するため、月次タスクの最後に実行する |

---

## 呼び出し先スキル

```
maintenance-agent.md（手動起動）
    │
    ├─── 週次タスク ──────────────────────────────
    ├─→ index-builder.md（mode: rebuild）
    ├─→ update-overview.md（target_dir: "__ALL__"）
    ├─→ sync-personal.md
    ├─→ sync-wiki.md
    ├─→ check-integrity.md
    │
    └─── 月次タスク ──────────────────────────────
    ├─→ update-changelog.md
    └─→ learn-from-feedback.md（ユーザー承認あり）
```
