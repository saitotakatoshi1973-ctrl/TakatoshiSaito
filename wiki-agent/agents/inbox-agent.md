# inbox-agent.md — _inbox/ 処理エージェント

## 概要

ユーザーが「inbox処理して」などと呼びかけたとき、
`_inbox/` にあるファイルを1件ずつ順番にwiki化します。
各スキルを順番に呼び出し、完了後にまとめて結果を報告します。

**正本経路**: `gemini_wiki_generator.py` を直接呼び出し（分類・本文生成ともGemini）。
**フォールバック経路**: Gemini失敗時のみ `analyze.md → write-wiki.md`（Claudeモード）。

---

## 起動方法

Claude Code のチャットで以下のように呼びかけてください：

```
inbox処理して
_inboxのファイルを処理して
新しいファイルをwiki化して
```

Claudeモードで処理したい場合（Geminiを使わない）：
```
inbox処理して。Claudeモードで。
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

### 正本経路（use_gemini=True、デフォルト）

```
_inbox/ のファイル
    │
    ▼
STEP 1: テキスト抽出
    │  convert-binary.md でテキスト化（キャッシュがあればスキップ）
    │  Gemini がファイルを直接読める形式（pptx/xlsx/pdf）は source_file_abs_path を渡すだけでもよい
    │
    ▼
STEP 2: gemini_wiki_generator.py --analyze-only
    │  SCHEMA.md と classification-hints.md を読み
    │  destination / wiki_type / title / confidence_score を JSON で返す
    │
    ├─ needs_review=true → STEP 3: ユーザー確認・修正
    │
    ▼
STEP 4: gemini_wiki_generator.py --generate
    │  分類結果JSON を受け取り、wiki本文 Markdown のみを stdout に出力
    │
    ▼
STEP 5: place-wiki.md
    │  Front-matter 生成・wikiファイル保存・_overview.md 更新
    │  change_log 記録 / index 追加 / route-binary
    │
    ▼
STEP 6: 元ファイルを _inbox/ から削除
```

### フォールバック経路（Gemini失敗時 または use_gemini=False 時）

```
_inbox/ のファイル
    │
    ▼
STEP 1: convert-binary.md（テキスト抽出）
    │
    ▼
STEP 2F: analyze.md（Claude分類）
    │
    ├─ 信頼度 < 6 → STEP 3: ユーザー確認・修正
    │
    ▼
STEP 4F: write-wiki.md（Claude本文生成）
    │
    ▼
STEP 5: place-wiki.md → STEP 6: 元ファイル削除
```

---

## STEP 1: テキスト抽出

```yaml
# convert-binary.md への入力
file_path: "{abs_path}"
```

### 戻り値の種類と後続処理

| convert の結果 | 後続処理 |
|--------------|---------|
| 通常テキスト（str） | → STEP 2 に渡す（1件処理） |
| url_list（list[dict]） | → URLごとにループ（STEP 2〜5 を繰り返す） |
| `status: error` | → スキップしてエラーログに記録 |

---

## STEP 2: gemini_wiki_generator.py --analyze-only（正本経路）

```python
import subprocess, sys, json

GEMINI_SCRIPT = r"C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder\wiki-agent\scripts\gemini_wiki_generator.py"
SCHEMA_PATH   = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase\_system\SCHEMA.md"
HINTS_PATH    = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase\_system\classification-hints.md"

def gemini_analyze(file_path: str, converted_text: str = "") -> dict:
    """
    gemini_wiki_generator.py --analyze-only を呼び出し分類結果JSONを返す。
    戻り値: {
        "destination": "kyorindo/cx/strategy/",
        "wiki_type":   "strategy",
        "title":       "CX推進ロードマップ v4",
        "confidence_score": 8,
        "needs_review": False,
        "tags": [...],
        "scope": "kyorindo",
        "domain": "cx",
    }
    または {"status": "error", "reason": "..."}
    """
    cmd = [
        sys.executable, GEMINI_SCRIPT, file_path,
        "--analyze-only", "--emit-usage",
        "--schema-path",  SCHEMA_PATH,
        "--hints-path",   HINTS_PATH,
    ]
    if converted_text:
        cmd += ["--converted-text", converted_text[:30000]]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        if result.returncode != 0:
            return {"status": "error", "reason": result.stderr.strip()}
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"status": "error", "reason": str(e)}
```

### 戻り値（analyze の主要フィールド）

```yaml
destination:       "kyorindo/cx/strategy/"
wiki_type:         "strategy"
title:             "CX推進ロードマップ v4"
confidence_score:  8          # 0〜10
needs_review:      false      # true の場合 STEP 3 へ
tags:              ["CX", "ロードマップ", "2026"]
scope:             "kyorindo"
domain:            "cx"
```

---

## STEP 3: needs_review=true の場合はユーザーに確認する

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

## STEP 4: gemini_wiki_generator.py --generate（正本経路）

```python
def gemini_generate(file_path: str, analysis: dict, converted_text: str = "") -> dict:
    """
    gemini_wiki_generator.py --generate を呼び出し wiki 本文 Markdown を返す。
    戻り値: {"status": "success", "body": str}
         または {"status": "error", "reason": str}
    """
    import tempfile, os

    # 分類結果を一時ファイル経由で渡す
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(analysis, f, ensure_ascii=False)
        analysis_json_path = f.name

    cmd = [
        sys.executable, GEMINI_SCRIPT, file_path,
        "--generate", "--emit-usage",
        "--analysis-json", analysis_json_path,
    ]
    if converted_text:
        cmd += ["--converted-text", converted_text[:30000]]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        os.unlink(analysis_json_path)
        if result.returncode != 0:
            return {"status": "error", "reason": result.stderr.strip()}
        body = result.stdout.strip()
        if not body:
            return {"status": "error", "reason": "Gemini から空の本文が返されました"}
        return {"status": "success", "body": body}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
```

---

## STEP 2F / 4F: フォールバック経路（Gemini失敗時 / Claudeモード時）

Gemini（STEP 2 または STEP 4）が失敗した場合、または `use_gemini=False` の場合に実行。

```yaml
# analyze.md への入力
content: "{STEP 1 で得たテキスト}"
file_name: "{元ファイル名}"
```

```yaml
# write-wiki.md への入力
wiki_type:            "{wiki_type}"
destination:          "{destination}"
title:                "{title}"
content:              "{変換テキスト}"
source_file:          "{元ファイル名}"
use_gemini:           false          # フォールバック時は Claude で生成
source_file_abs_path: "{絶対パス}"
```

---

## STEP 5: place-wiki.md を呼び出す

```yaml
# place-wiki.md への入力（正本経路）
wiki_path:    "{生成した wiki ファイルの絶対パス}"
source_file:  "{元ファイルの絶対パス}"
wiki_content: "{front-matter + body の完成 Markdown}"
analysis:     "{STEP 2 の分類結果 dict}"
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
def run(use_gemini: bool = True) -> dict:
    files = collect_inbox_files()

    if not files:
        return {
            "status":    "success",
            "message":   "_inbox/ に処理対象ファイルがありません",
            "processed": 0,
        }

    results  = []   # 処理成功
    skipped  = []   # ユーザーがスキップを選択
    errors   = []   # エラーでスキップ

    for file_path in files:
        fname = os.path.basename(file_path)

        # STEP 1: テキスト抽出（convert-binary.md）
        convert_result = convert_binary_run(file_path)

        if convert_result.get("status") == "error":
            errors.append({"file": fname, "step": "convert", "error": convert_result.get("reason")})
            continue

        items = (
            convert_result["items"]
            if convert_result.get("type") == "url_list"
            else [{"content": convert_result["content"], "source": fname}]
        )

        file_has_error = False

        for item in items:
            content    = item["content"]
            item_label = item.get("url") or fname

            wiki_body      = None
            analysis       = None
            generation_method = "gemini"

            # ── 正本経路: Gemini ──────────────────────────
            if use_gemini:
                # STEP 2: Gemini 分類
                analysis = gemini_analyze(file_path, converted_text=content)

                if analysis.get("status") == "error":
                    print(f"⚠️  Gemini 分類失敗（{analysis['reason']}）→ Claude フォールバック")
                    use_gemini_for_item = False
                else:
                    use_gemini_for_item = True

                    # STEP 3: needs_review=true の場合ユーザー確認
                    if analysis.get("needs_review"):
                        user_choice = ask_user_classify_confirm(fname, analysis)
                        if user_choice == "skip":
                            skipped.append({"file": item_label, "reason": "ユーザーがスキップを選択"})
                            file_has_error = True
                            continue
                        if user_choice.get("correction"):
                            analysis["destination"] = user_choice["correction"]
                            record_feedback_run(
                                source                   = "analyze",
                                file_name                = fname,
                                agent_judgment           = analysis.get("destination"),
                                user_correction          = user_choice["correction"],
                                classification_confidence= analysis.get("confidence_score", 0),
                                classification_method    = "gemini_analyze",
                                user_comment             = user_choice.get("comment", ""),
                            )

                    # STEP 4: Gemini 本文生成
                    gen_result = gemini_generate(file_path, analysis, converted_text=content)
                    if gen_result.get("status") == "error":
                        print(f"⚠️  Gemini 本文生成失敗（{gen_result['reason']}）→ Claude フォールバック")
                        use_gemini_for_item = False
                    else:
                        wiki_body = gen_result["body"]
                        generation_method = "gemini"

            else:
                use_gemini_for_item = False

            # ── フォールバック経路: Claude ────────────────
            if not use_gemini or not use_gemini_for_item or wiki_body is None:
                generation_method = "claude"

                # STEP 2F: analyze.md（Claude分類）
                analyze_result = analyze_run(content=content, file_name=fname)

                if analyze_result.get("status") == "error":
                    errors.append({"file": item_label, "step": "analyze", "error": analyze_result.get("reason")})
                    file_has_error = True
                    continue

                confidence = analyze_result.get("confidence_score", 10)
                if confidence < 6:
                    user_choice = ask_user_classify_confirm(fname, analyze_result)
                    if user_choice == "skip":
                        skipped.append({"file": item_label, "reason": "ユーザーがスキップを選択"})
                        file_has_error = True
                        continue
                    if user_choice.get("correction"):
                        analyze_result["destination"] = user_choice["correction"]
                        record_feedback_run(
                            source                   = "analyze",
                            file_name                = fname,
                            agent_judgment           = analyze_result.get("destination_original"),
                            user_correction          = user_choice["correction"],
                            classification_confidence= confidence,
                            classification_method    = analyze_result.get("classification_method"),
                            user_comment             = user_choice.get("comment", ""),
                        )

                analysis = analyze_result

                # STEP 4F: write-wiki.md（Claude本文生成）
                write_result = write_wiki_run(
                    wiki_type            = analysis["wiki_type"],
                    destination          = analysis["destination"],
                    title                = analysis["title"],
                    content              = content,
                    source_file          = fname,
                    use_gemini           = False,
                    source_file_abs_path = file_path,
                )

                if write_result.get("status") == "error":
                    errors.append({"file": item_label, "step": "write_wiki", "error": write_result.get("reason")})
                    file_has_error = True
                    continue

                wiki_body = write_result.get("body")

            # STEP 5: place-wiki.md
            place_result = place_wiki_run(
                wiki_path    = build_wiki_path(analysis),
                source_file  = file_path,
                wiki_content = build_wiki_content(analysis, wiki_body),
                analysis     = analysis,
            )

            results.append({
                "file":              item_label,
                "wiki_path":         place_result.get("wiki_path"),
                "destination":       analysis["destination"],
                "generation_method": generation_method,
            })

        # STEP 6: 元ファイルを削除（エラーなく全 item を処理できた場合）
        if not file_has_error:
            deleted = delete_inbox_file(file_path)
            if not deleted:
                errors.append({"file": fname, "step": "delete", "error": "ファイル削除失敗（手動削除してください）"})

    return {
        "status":       "success" if not errors else "partial",
        "processed":    len(results),
        "skipped":      len(skipped),
        "errors":       len(errors),
        "results":      results,
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
  - {file} → {wiki_path}  ({generation_method})

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
| Gemini 分類失敗（STEP 2） | Claude フォールバック（analyze.md）へ |
| Gemini 本文生成失敗（STEP 4） | Claude フォールバック（write-wiki.md）へ |
| analyze.md 失敗（フォールバック） | スキップ・エラーログ記録 |
| write-wiki.md 失敗（フォールバック） | スキップ・エラーログ記録、元ファイルは _inbox/ に残す |
| place-wiki.md 失敗 | wikiファイルはそのまま残す・エラーログ記録 |
| 元ファイル削除失敗 | エラーログ記録・ユーザーに手動削除を促す |

---

## 呼び出し先スキル・スクリプト

```
inbox-agent.md
    ├─→ convert-binary.md              （テキスト抽出）
    │
    ├─→ [正本経路]
    │       ├─→ gemini_wiki_generator.py --analyze-only  （Gemini分類）
    │       ├─→ gemini_wiki_generator.py --generate      （Gemini本文生成）
    │       └─→ place-wiki.md                            （後処理一式）
    │               ├─→ update-overview.md
    │               ├─→ change_log_YYYY-MM.md
    │               ├─→ index-builder.md（add）
    │               └─→ route-binary.md
    │
    └─→ [フォールバック経路（Gemini失敗時）]
            ├─→ analyze.md             （Claude分類）
            ├─→ record-feedback.md     （ユーザー修正時のみ）
            ├─→ write-wiki.md          （Claude本文生成）
            └─→ place-wiki.md          （後処理一式）
```
