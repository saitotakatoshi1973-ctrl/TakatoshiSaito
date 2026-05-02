# inbox-agent.md — _inbox/ 処理エージェント

## 概要

ユーザーが「inbox処理して」などと呼びかけたとき、
`_inbox/` にあるファイルを1件ずつ順番にwiki化します。
各スキルを順番に呼び出し、完了後にまとめて結果を報告します。

---

## 起動方法

Claude Code のチャットで以下のように呼びかけてください：

```
inbox処理して
_inboxのファイルを処理して
新しいファイルをwiki化して
```

---

## 処理対象ファイル

`KnowledgeBase/_inbox/` 直下のファイルを対象とします。
サブフォルダ（例: `_processed/`）は除外します。

```python
import os

INBOX_DIR = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase\_inbox"

def collect_inbox_files() -> list[str]:
    """
    _inbox/ 直下のファイル一覧を返す（サブフォルダは除外）。
    戻り値: ファイルの絶対パスリスト（更新日時の古い順）
    """
    files = []
    for entry in os.scandir(INBOX_DIR):
        if entry.is_file():
            files.append(entry.path)

    # 更新日時の古い順（先に入れたものを先に処理）
    files.sort(key=lambda p: os.path.getmtime(p))
    return files
```

---

## 処理フロー（1ファイルあたり）

```
_inbox/ のファイル
    │
    ▼
STEP 1: convert-binary.md
    │  テキスト抽出・URL取得
    │  ※ url_list の場合 → URL数だけループ
    │
    ▼
STEP 2: analyze.md
    │  分類先・wiki_type・信頼度スコアを判定
    │
    ├─ 信頼度 < 6 → STEP 3: ユーザー確認・修正
    │
    ▼
STEP 4: write-wiki.md
    │  wiki Markdown を生成・保存
    │
    ▼
STEP 5: place-wiki.md
    │  _overview.md 更新 / change_log 記録 / index 追加 / route-binary
    │
    ▼
STEP 6: 元ファイルを _inbox/ から削除
```

---

## STEP 1: convert-binary.md を呼び出す

```yaml
# convert-binary.md への入力
file_path: "{abs_path}"
```

### 戻り値の種類と後続処理

| convert の結果 | 後続処理 |
|--------------|---------|
| 通常テキスト（str） | → analyze.md に渡す（1件処理） |
| url_list（list[dict]） | → URLごとにループ（STEP 2〜5 を繰り返す） |
| `status: error` | → スキップしてエラーログに記録 |

---

## STEP 2: analyze.md を呼び出す

```yaml
# analyze.md への入力
content: "{convert で得たテキスト}"
file_name: "{元ファイル名}"
```

### 戻り値（analyze の主要フィールド）

```yaml
wiki_type: "strategy"
destination: "kyorindo/cx/strategy/"
title: "CX推進ロードマップ v4"
confidence_score: 8          # 0〜10
classification_method: "llm_scoring"
```

---

## STEP 3: 信頼度が低い場合はユーザーに確認する（confidence_score < 6）

### ユーザーへの提示メッセージ

```
📋 分類確認が必要です（信頼度: {confidence_score}/10）

ファイル: {file_name}
エージェント判断:
  wiki_type   : {wiki_type}
  保存先      : {destination}
  タイトル候補: {title}
  判断理由    : {reason}

このまま進めますか？
  1. このまま進める
  2. 保存先を修正する → 正しい保存先を入力してください
  3. スキップする（このファイルは処理しない）
```

### ユーザー回答の処理

| 回答 | 処理 |
|------|------|
| 1（このまま） | そのまま STEP 4 へ |
| 2（修正） | ユーザー入力の保存先で上書き → record-feedback.md を呼ぶ → STEP 4 へ |
| 3（スキップ） | スキップリストに追加、元ファイルは _inbox/ に残す |

---

## STEP 4: write-wiki.md を呼び出す

```yaml
# write-wiki.md への入力
wiki_type:   "{wiki_type}"
destination: "{destination}"
title:       "{title}"
content:     "{convert で得たテキスト}"
source_file: "{元ファイル名}"
```

---

## STEP 5: place-wiki.md を呼び出す

```yaml
# place-wiki.md への入力
wiki_path:   "{write-wiki.md が生成したファイルの絶対パス}"
source_file: "{元ファイルの絶対パス}"
```

place-wiki.md が以下を自動実行します：
- `_overview.md` の更新
- `change_log_YYYY-MM.md` への1行追記
- `index-builder.md`（add モード）の呼び出し
- `route-binary.md` の呼び出し（00personal/ への振り分け）

---

## STEP 6: 元ファイルを削除する

wiki化が完了したファイルを `_inbox/` から削除します。

```python
import time

def delete_inbox_file(file_path: str, retries: int = 3, wait: int = 5) -> bool:
    """
    _inbox/ の元ファイルを削除する。
    OneDrive ロック時はリトライ。
    戻り値: True（成功） / False（失敗）
    """
    for attempt in range(retries):
        try:
            os.remove(file_path)
            return True
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                return False
        except FileNotFoundError:
            return True   # 既に存在しない場合は成功とみなす
```

### ファイル種別ごとの削除方針

| ファイル種別 | 削除理由 |
|------------|---------|
| .pptx / .xlsx / .docx / .pdf 等 | 元ファイルは `00personal/` に存在するためコピーを削除 |
| .md | wiki化済みのため削除 |
| .txt（URL リスト） | 全URL処理完了後に削除 |

---

## メイン実行フロー

```python
def run() -> dict:
    files = collect_inbox_files()

    if not files:
        return {
            "status": "success",
            "message": "_inbox/ に処理対象ファイルがありません",
            "processed": 0,
        }

    results  = []   # 処理成功
    skipped  = []   # ユーザーがスキップを選択
    errors   = []   # エラーでスキップ

    for file_path in files:
        fname = os.path.basename(file_path)

        # STEP 1: convert-binary.md
        convert_result = convert_binary_run(file_path)

        if convert_result.get("status") == "error":
            errors.append({"file": fname, "step": "convert", "error": convert_result.get("reason")})
            continue

        # url_list の場合は複数ループ、通常テキストは1件として処理
        items = (
            convert_result["items"]
            if convert_result.get("type") == "url_list"
            else [{"content": convert_result["content"], "source": fname}]
        )

        file_has_error = False

        for item in items:
            content    = item["content"]
            item_label = item.get("url") or fname   # ログ表示用

            # STEP 2: analyze.md
            analyze_result = analyze_run(content=content, file_name=fname)

            if analyze_result.get("status") == "error":
                errors.append({"file": item_label, "step": "analyze", "error": analyze_result.get("reason")})
                file_has_error = True
                continue

            confidence = analyze_result.get("confidence_score", 10)

            # STEP 3: 信頼度 < 6 → ユーザー確認
            if confidence < 6:
                user_choice = ask_user_classify_confirm(fname, analyze_result)

                if user_choice == "skip":
                    skipped.append({"file": item_label, "reason": "ユーザーがスキップを選択"})
                    file_has_error = True
                    continue

                if user_choice.get("correction"):
                    # ユーザーが保存先を修正した場合
                    analyze_result["destination"] = user_choice["correction"]
                    record_feedback_run(
                        source            = "analyze",
                        file_name         = fname,
                        agent_judgment    = analyze_result.get("destination_original"),
                        user_correction   = user_choice["correction"],
                        classification_confidence = confidence,
                        classification_method     = analyze_result.get("classification_method"),
                        user_comment      = user_choice.get("comment", ""),
                    )

            # STEP 4: write-wiki.md
            write_result = write_wiki_run(
                wiki_type   = analyze_result["wiki_type"],
                destination = analyze_result["destination"],
                title       = analyze_result["title"],
                content     = content,
                source_file = fname,
            )

            if write_result.get("status") == "error":
                errors.append({"file": item_label, "step": "write_wiki", "error": write_result.get("reason")})
                file_has_error = True
                continue

            # STEP 5: place-wiki.md
            place_result = place_wiki_run(
                wiki_path   = write_result["wiki_path"],
                source_file = file_path,
            )

            results.append({
                "file":      item_label,
                "wiki_path": write_result["wiki_path"],
                "destination": analyze_result["destination"],
            })

        # STEP 6: 元ファイルを削除（エラーなく全 item を処理できた場合）
        if not file_has_error:
            deleted = delete_inbox_file(file_path)
            if not deleted:
                errors.append({"file": fname, "step": "delete", "error": "ファイル削除失敗（手動削除してください）"})

    return {
        "status":    "success" if not errors else "partial",
        "processed": len(results),
        "skipped":   len(skipped),
        "errors":    len(errors),
        "results":   results,
        "skipped_list": skipped,
        "error_list":   errors,
    }
```

---

## 完了レポート（ユーザーへの通知）

全ファイルの処理が完了したら、以下の形式でまとめて報告します。

```
✅ _inbox/ の処理が完了しました

処理成功: {processed}件
スキップ: {skipped}件
エラー:   {errors}件

【処理済みファイル】
{results を1行ずつ表示}
  - {file} → {wiki_path}

【スキップ】
{skipped_list を1行ずつ表示（ある場合のみ）}

【エラー（手動対応が必要）】
{error_list を1行ずつ表示（ある場合のみ）}
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| convert-binary.md 失敗 | スキップ・エラーログ記録 |
| analyze.md 失敗 | スキップ・エラーログ記録 |
| write-wiki.md 失敗 | スキップ・エラーログ記録、元ファイルは _inbox/ に残す |
| place-wiki.md 失敗 | wikiファイルはそのまま残す・エラーログ記録 |
| 元ファイル削除失敗 | エラーログ記録・ユーザーに手動削除を促す |

---

## 呼び出し先スキル

```
inbox-agent.md
    ├─→ convert-binary.md   （テキスト抽出）
    ├─→ analyze.md          （分類）
    ├─→ record-feedback.md  （ユーザー修正時のみ）
    ├─→ write-wiki.md       （wiki生成）
    └─→ place-wiki.md       （後処理一式）
            ├─→ update-overview.md
            ├─→ change_log_YYYY-MM.md
            ├─→ index-builder.md（add）
            └─→ route-binary.md
```
