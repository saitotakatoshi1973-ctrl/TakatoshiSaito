# check-integrity.md — KnowledgeBase整合性チェックスキル

## 概要

`KnowledgeBase/` 全体を走査して以下の3種類の問題を検出します。
軽微な問題（Front-matter欠落・index未登録）は自動修正し、
修正できない問題（空ファイル）はレポートに記録します。

| チェック項目 | 自動修正 |
|-------------|---------|
| A: Front-matter 欠落・必須フィールド不足 | ✅ LLM で補完 |
| C: index（npz）未登録ファイル | ✅ index-builder.md で追加 |
| D: 空ファイル（2文字未満） | ❌ レポートのみ |

---

## 呼び出しパターン

| 呼び出し元 | タイミング |
|-----------|-----------|
| `maintenance-agent` | 週次自動実行 |
| ユーザー手動 | 任意のタイミング |

---

## 共通設定

```python
import os
import re
import yaml
import numpy as np
from datetime import date, datetime

KB_ROOT           = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"
PERSONAL_ROOT     = r"C:\Users\takatoshi-saito\OneDrive\00personal"
NPZ_PATH          = os.path.join(KB_ROOT, "_system", "wiki-embeddings.npz")
REPORT_PATH       = os.path.join(KB_ROOT, "_system", "integrity-report.md")
PROCESSED_SOURCES = os.path.join(KB_ROOT, "_system", "processed-sources.yaml")
SKIP_DIRS         = {"_inbox", "_system"}
REQUIRED_FM       = {"title", "wiki_type", "scope", "domain"}
EMPTY_THRESH      = 2     # この文字数未満を「空ファイル」とみなす
```

---

## STEP 1: KnowledgeBase/ を走査してファイル一覧を収集する

```python
def collect_md_files() -> list[str]:
    """
    KnowledgeBase/ 配下の .md ファイルを収集する。
    - _inbox/ / _system/ は除外
    - _overview.md は除外
    戻り値: KB_ROOT からの相対パス（スラッシュ区切り）のリスト
    """
    files = []

    for root, dirs, fnames in os.walk(KB_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in sorted(fnames):
            if not fname.endswith(".md"):
                continue
            if fname == "_overview.md":
                continue

            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, KB_ROOT).replace("\\", "/")
            files.append(rel_path)

    return files
```

---

## STEP 2: npz 登録済みパスを読み込む

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

## STEP 3: 各ファイルを検査する

```python
def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Front-matter を抽出する。
    戻り値: (front_matter_dict, body)
    Front-matter がない場合は ({}, content)
    """
    match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, content[match.end():]


def inspect_file(rel_path: str, registered: set[str]) -> dict:
    """
    1ファイルを検査して問題リストを返す。
    戻り値: {
        "rel_path": str,
        "abs_path": str,
        "issues": list[str],   # 問題の種別リスト
        "missing_fields": list[str],
        "is_empty": bool,
        "not_in_index": bool,
        "fm": dict,
        "body": str,
    }
    """
    abs_path = os.path.join(KB_ROOT, rel_path.replace("/", os.sep))
    result = {
        "rel_path":      rel_path,
        "abs_path":      abs_path,
        "issues":        [],
        "missing_fields": [],
        "is_empty":      False,
        "not_in_index":  False,
        "fm":            {},
        "body":          "",
    }

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        result["issues"].append(f"read_error: {e}")
        return result

    # D: 空ファイルチェック（Front-matter含む全体が EMPTY_THRESH 未満）
    if len(content.strip()) < EMPTY_THRESH:
        result["is_empty"] = True
        result["issues"].append("empty_file")
        return result   # 空ファイルは以降のチェックをスキップ

    # A: Front-matter チェック
    fm, body = parse_frontmatter(content)
    result["fm"]   = fm
    result["body"] = body

    missing = [f for f in REQUIRED_FM if not str(fm.get(f, "")).strip()]
    if missing:
        result["missing_fields"] = missing
        result["issues"].append("missing_frontmatter")

    # C: index 未登録チェック
    if rel_path not in registered:
        result["not_in_index"] = True
        result["issues"].append("not_in_index")

    return result
```

---

## STEP 4-A: Front-matter 欠落を自動修正する

LLM が必須フィールドを推定してファイルに書き戻す。
ロジックは `sync-wiki.md` の STEP 4〜5 と同一。

### LLMへの指示

```
以下は KnowledgeBase wiki の Markdown ファイルです。
不足しているフィールドを推定してください。

【ファイルパス】: {rel_path}
【既存 Front-matter】: {fm}
【不足フィールド】: {missing_fields}
【本文（先頭1000文字）】:
{body[:1000]}

【wiki_type の選択肢】:
strategy / organization / issue / progress /
reference / task / log / benchmark / research

【scope の例】: kyorindo / tsuruha-hd / retail / personal
【domain の例】: cx / it-systems / hr / management / finance / strategy

【出力形式（YAMLのみ）】
title: "（タイトル）"
wiki_type: "（選択肢から1つ）"
scope: "（スコープ）"
domain: "（ドメイン）"
```

### 書き戻し処理

```python
import time

def fix_frontmatter(abs_path: str, fm: dict, body: str,
                    missing: list[str], today: str,
                    retries: int = 3, wait: int = 5) -> bool:
    """
    Front-matter を補完してファイルに書き戻す。
    成功: True / 失敗: False
    """
    # LLM で不足フィールドを推定
    rel_path = os.path.relpath(abs_path, KB_ROOT).replace("\\", "/")
    inferred = llm_infer_frontmatter(rel_path, fm, body, missing, today)

    # 既存値を優先しながらマージ
    for field in missing:
        fm[field] = inferred.get(field, "")
    fm.setdefault("tags",    [])
    fm.setdefault("status",  "current")
    fm.setdefault("created", today)
    fm["updated"] = today

    fm_str      = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    new_content = f"---\n{fm_str}---\n{body}"

    for attempt in range(retries):
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                return False
```

---

## STEP 4-C: index 未登録ファイルを自動修正する

```yaml
# index-builder.md への入力
mode: "add"
file_path: "{abs_path}"
```

`index-builder.md` の `run()` を呼び出し、wiki-embeddings.npz に追加する。

---

## STEP 4-E: 削除されたソースファイルを検出する

`processed-sources.yaml` の全レコードを走査し、
`source_path` が実際に `00personal/` に存在しないレコードを検出する。
`source_deleted: true` 設定済みのレコードはスキップ（既知の削除として扱う）。

```python
def detect_all_deleted_sources() -> list[dict]:
    """
    processed-sources.yaml 全体から削除済みソースファイルを検出する。
    戻り値: 削除検出レコードのリスト
    """
    if not os.path.exists(PROCESSED_SOURCES):
        return []

    try:
        with open(PROCESSED_SOURCES, "r", encoding="utf-8") as f:
            records = yaml.safe_load(f) or []
    except Exception:
        return []

    deleted = []
    for r in records:
        source_path = r.get("source_path", "")
        if not source_path:
            continue
        # source_deleted: true は既知の削除 → スキップ
        if r.get("source_deleted", False):
            continue
        # binary_moved: "skipped" は batch-inbox 元ファイル → チェック対象
        abs_path = os.path.join(PERSONAL_ROOT, source_path.replace("/", os.sep))
        if not os.path.exists(abs_path):
            deleted.append(r)

    return deleted


def handle_deleted_sources_report(deleted: list[dict]) -> list[dict]:
    """
    削除済みソースをユーザーに確認し、選択（A/B/C）に応じて処理する。
    レポート用の結果リストを返す。
    """
    if not deleted:
        return []

    # ユーザーへの確認
    print(f"\n⚠️  削除されたソースファイルが見つかりました（{len(deleted)}件）\n")
    for i, r in enumerate(deleted, 1):
        print(f"  {i}. {r['source_path']}")
        print(f"     → wiki: {r['wiki_path']}")

    print("""
これらのwikiをどうしますか？
  A. wikiを削除する（change_log に記録）
  B. status: outdated に更新して残す（推奨）
  C. 何もしない（次回も同じ警告が出ます）
A / B / C で回答してください:""")

    # ユーザーの選択を受けて処理
    # （LLM がユーザーの返答を読んで以下を実行する）
    results = []
    for r in deleted:
        wiki_abs = os.path.join(KB_ROOT, r["wiki_path"].replace("/", os.sep))

        # A: 削除
        if user_choice == "A":
            if os.path.exists(wiki_abs):
                os.remove(wiki_abs)
                # index-builder.md で index からも除去
                index_builder_run(mode="remove", file_path=wiki_abs)
            _remove_processed_record(r["source_path"])
            results.append({"action": "deleted", "wiki": r["wiki_path"]})

        # B: outdated 更新
        elif user_choice == "B":
            _update_wiki_status(wiki_abs, "outdated")
            _update_processed_field_global(r["source_path"], {"source_deleted": True})
            results.append({"action": "outdated", "wiki": r["wiki_path"]})

        # C: 何もしない
        else:
            _update_processed_field_global(r["source_path"], {"source_deleted": True})
            results.append({"action": "skipped", "wiki": r["wiki_path"]})

    return results


def _update_wiki_status(wiki_abs: str, status: str) -> None:
    """wiki ファイルの Front-matter status フィールドを更新する"""
    if not os.path.exists(wiki_abs):
        return
    with open(wiki_abs, "r", encoding="utf-8") as f:
        content = f.read()
    today = date.today().isoformat()
    content = re.sub(r'(^status:\s*).*', f'\\g<1>{status}', content, flags=re.MULTILINE)
    content = re.sub(r'(^updated:\s*).*', f'\\g<1>{today}', content, flags=re.MULTILINE)
    with open(wiki_abs, "w", encoding="utf-8") as f:
        f.write(content)


def _remove_processed_record(source_path: str) -> None:
    """processed-sources.yaml から指定の source_path レコードを削除する"""
    if not os.path.exists(PROCESSED_SOURCES):
        return
    with open(PROCESSED_SOURCES, "r", encoding="utf-8") as f:
        records = yaml.safe_load(f) or []
    records = [r for r in records if r.get("source_path") != source_path]
    with open(PROCESSED_SOURCES, "w", encoding="utf-8") as f:
        yaml.dump(records, f, allow_unicode=True, default_flow_style=False)


def _update_processed_field_global(source_path: str, updates: dict) -> None:
    """processed-sources.yaml の指定レコードを更新する"""
    if not os.path.exists(PROCESSED_SOURCES):
        return
    with open(PROCESSED_SOURCES, "r", encoding="utf-8") as f:
        records = yaml.safe_load(f) or []
    for r in records:
        if r.get("source_path") == source_path:
            r.update(updates)
            break
    with open(PROCESSED_SOURCES, "w", encoding="utf-8") as f:
        yaml.dump(records, f, allow_unicode=True, default_flow_style=False)
```

---

## STEP 5: レポートを生成する

```python
def build_report(
    total: int,
    fixed_fm: list[str],
    fixed_index: list[str],
    empty_files: list[str],
    deleted_sources: list[dict],
    errors: list[dict],
    today: str,
) -> str:
    """
    integrity-report.md の内容を生成する。
    """
    lines = [
        f"# KnowledgeBase 整合性チェックレポート",
        f"",
        f"実行日: {today}",
        f"対象ファイル数: {total}",
        f"",
        f"---",
        f"",
    ]

    # 自動修正済み: Front-matter
    lines.append(f"## ✅ 自動修正: Front-matter 補完（{len(fixed_fm)}件）")
    if fixed_fm:
        lines += [f"- {p}" for p in fixed_fm]
    else:
        lines.append("- なし")
    lines.append("")

    # 自動修正済み: index 追加
    lines.append(f"## ✅ 自動修正: index 追加（{len(fixed_index)}件）")
    if fixed_index:
        lines += [f"- {p}" for p in fixed_index]
    else:
        lines.append("- なし")
    lines.append("")

    # 要対応: 空ファイル
    lines.append(f"## ⚠️ 要対応: 空ファイル（{len(empty_files)}件）")
    if empty_files:
        lines += [f"- {p}" for p in empty_files]
    else:
        lines.append("- なし")
    lines.append("")

    # 削除済みソースファイル
    lines.append(f"## 🗑️ 削除済みソースファイル（{len(deleted_sources)}件）")
    if deleted_sources:
        for r in deleted_sources:
            action = r.get("action", "")
            label  = {"deleted": "wiki削除", "outdated": "outdated更新", "skipped": "スキップ"}.get(action, action)
            lines.append(f"- [{label}] {r['wiki']} ← {r.get('source_path', '')}")
    else:
        lines.append("- なし")
    lines.append("")

    # エラー
    lines.append(f"## ❌ エラー（{len(errors)}件）")
    if errors:
        for e in errors:
            lines.append(f"- {e['file']}: {e['error']}")
    else:
        lines.append("- なし")

    return "\n".join(lines)
```

---

## STEP 6: レポートを保存する

```python
def save_report(content: str, retries: int = 3, wait: int = 5) -> None:
    """
    integrity-report.md に保存する。OneDrive ロック時はリトライ。
    """
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)

    for attempt in range(retries):
        try:
            with open(REPORT_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                raise RuntimeError("integrity-report.md の保存に失敗しました")
```

---

## STEP 7: メイン実行フロー

```python
def run() -> dict:
    today      = date.today().isoformat()
    all_files  = collect_md_files()
    registered = load_registered_paths()

    fixed_fm        = []   # Front-matter 自動修正済み
    fixed_index     = []   # index 自動追加済み
    empty_files     = []   # 空ファイル（手動対応が必要）
    deleted_results = []   # 削除済みソースの処理結果
    errors          = []

    # STEP 4-E: 削除されたソースファイルを全体スイープ
    deleted = detect_all_deleted_sources()
    if deleted:
        deleted_results = handle_deleted_sources_report(deleted)

    for rel_path in all_files:
        result = inspect_file(rel_path, registered)

        if "read_error" in result["issues"]:
            errors.append({"file": rel_path, "error": result["issues"][0]})
            continue

        # D: 空ファイル → レポートのみ
        if result["is_empty"]:
            empty_files.append(rel_path)
            continue

        abs_path = result["abs_path"]

        # A: Front-matter 補完（自動修正）
        if result["missing_fields"]:
            ok = fix_frontmatter(
                abs_path, result["fm"], result["body"],
                result["missing_fields"], today
            )
            if ok:
                fixed_fm.append(rel_path)
            else:
                errors.append({"file": rel_path, "error": "Front-matter 書き戻し失敗"})

        # C: index 追加（自動修正）
        if result["not_in_index"]:
            idx_result = index_builder_run(mode="add", file_path=abs_path)
            if idx_result.get("status") == "success":
                fixed_index.append(rel_path)
            else:
                errors.append({"file": rel_path, "error": f"index 追加失敗: {idx_result}"})

    # レポート生成・保存
    report_content = build_report(
        total           = len(all_files),
        fixed_fm        = fixed_fm,
        fixed_index     = fixed_index,
        empty_files     = empty_files,
        deleted_sources = deleted_results,
        errors          = errors,
        today           = today,
    )
    save_report(report_content)

    return {
        "status":          "success" if not errors else "partial",
        "total":           len(all_files),
        "fixed_fm":        len(fixed_fm),
        "fixed_index":     len(fixed_index),
        "empty_files":     len(empty_files),
        "deleted_sources": len(deleted_results),
        "errors":          len(errors),
        "report_path":     REPORT_PATH,
        "report":          report_content,   # チャット表示用
    }
```

---

## STEP 8: 結果を出力する

```yaml
status: success
total: 95
fixed_fm: 2
fixed_index: 1
empty_files: 1
deleted_sources: 2
errors: 0
report_path: "KnowledgeBase/_system/integrity-report.md"
report: |
  # KnowledgeBase 整合性チェックレポート

  実行日: 2026-05-01
  対象ファイル数: 95

  ---

  ## ✅ 自動修正: Front-matter 補完（2件）
  - kyorindo/cx/strategy/旧資料_20260301.md
  - kyorindo/hr/採用方針_20260401.md

  ## ✅ 自動修正: index 追加（1件）
  - kyorindo/management/報告書_20260430.md

  ## ⚠️ 要対応: 空ファイル（1件）
  - kyorindo/cx/progress/メモ_20260401.md

  ## 🗑️ 削除済みソースファイル（2件）
  - [outdated更新] kyorindo/cx/strategy/旧_CX方針_20260101.md ← 03_CX推進/01_戦略/旧_CX方針.pptx
  - [wiki削除] kyorindo/cx/strategy/CX方針暫定_20260215.md ← 03_CX推進/01_戦略/CX方針_暫定版.pptx

  ## ❌ エラー（0件）
  - なし
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| ファイル読み込み失敗 | `errors` に記録してスキップ |
| LLM Front-matter 推定失敗 | デフォルト値で代替（`wiki_type: reference`）|
| Front-matter 書き戻し失敗（WinError 5） | 5秒×3回リトライ → 失敗時は `errors` に記録 |
| index-builder.md 失敗 | `errors` に記録（当該ファイルはスキップ）|
| integrity-report.md 保存失敗 | 5秒×3回リトライ → 失敗時は例外を raise |

---

## 呼び出し元・呼び出し先

```
maintenance-agent（週次）
ユーザー手動
    └─→ check-integrity.md（本スキル）
            ├─→ index-builder.md（add/remove モード）
            ├─→ processed-sources.yaml（削除済みソースの source_deleted 更新）
            └─→ integrity-report.md（チェック結果を保存）
```
