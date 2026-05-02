# route-binary.md — バイナリ元ファイル振り分けスキル

## 概要

`_inbox/` 内の元ファイル（.pptx / .pdf / .xlsx など）を
`00personal/` 配下の適切なフォルダへ移動します。
移動先は `analyze.md` の分類結果と `personal-index.yaml` の照合で決定し、
見つからない場合はユーザーに確認して学習に回します。

---

## 入力

`place-wiki.md` から渡される情報：

```yaml
original_file: "KnowledgeBase/_inbox/CX_roadmap_v4.pptx"  # 絶対パスまたは _inbox/ 相対
wiki_destination: "kyorindo/cx/strategy/"                   # analyze.md の分類結果
scope: "kyorindo"
file_name: "CX_roadmap_v4.pptx"
```

---

## STEP 1: personal-index.yaml を読み込む

```python
import yaml
import os

def load_personal_index(index_path: str) -> list[dict]:
    with open(index_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get('folders', [])
```

---

## STEP 2: wiki_destination から移動先フォルダを検索する

`wiki_destination`（例: `kyorindo/cx/strategy/`）をもとに
`personal-index.yaml` 内の最適なフォルダを探す。

### 2-1: scope キーワードマッピング

| wiki scope | personal-index 検索キーワード |
|------------|---------------------------|
| `kyorindo` | `杏林堂`, `kyorindo`, `CX`, `情報システム` |
| `tsuruha-hd` | `ツルハ`, `tsuruha`, `HD` |
| `retail` | `小売`, `retail`, `ドラッグストア` |
| `ai-dx` | `AI`, `DX`, `IT` |
| `vendor` | `ベンダー`, `vendor`, `外部` |
| `research` | `調査`, `research`, `リサーチ` |

### 2-2: domain キーワードマッピング

| wiki domain | personal-index 追加検索キーワード |
|-------------|-------------------------------|
| `cx` | `CX`, `顧客`, `アプリ` |
| `it-systems` | `IT`, `システム`, `インフラ` |
| `hr` | `人事`, `労務`, `総務` |
| `management` | `経営`, `会議`, `役員` |
| `strategy` | `戦略`, `計画`, `ロードマップ` |
| `organization` | `組織`, `体制` |

### 2-3: LLM によるフォルダ候補の選定

```python
def find_personal_folder(
    folders: list[dict],
    wiki_destination: str,
    scope: str,
    domain: str
) -> list[dict]:
    """
    personal-index.yaml の全フォルダから候補を最大5件返す。
    キーワードマッピングで絞り込み → LLM が最適なフォルダを選ぶ。
    """
    scope_kws = SCOPE_KEYWORDS.get(scope, [])
    domain_kws = DOMAIN_KEYWORDS.get(domain, [])
    all_kws = scope_kws + domain_kws

    candidates = []
    for folder in folders:
        folder_text = (
            folder.get('description', '') + ' ' +
            ' '.join(folder.get('keywords', []))
        ).lower()
        # いずれかのキーワードが含まれる場合を候補とする
        if any(kw.lower() in folder_text for kw in all_kws):
            candidates.append(folder)

    return candidates[:10]  # 上位10件をLLMに渡す
```

LLM への選定指示：

```
以下の personal-index.yaml フォルダ候補から、
「{wiki_destination}」に対応する最適な保管先を1つ選んでください。

【wiki_destination】: {wiki_destination}
【ファイル名】: {file_name}

【フォルダ候補】:
{candidates を列挙}

選定基準：
- wiki の分類先フォルダと意味的に最も近いフォルダ
- ファイル種別（pptx=資料系、xlsx=データ系）も考慮する
- サブフォルダが深い方が具体的で望ましい

回答形式:
selected_path: "09_InformationOrganization/杏林堂/CX推進/"
confidence: 8   # 0〜10
```

---

## STEP 3: 候補が見つからない場合 → ユーザー確認 + 学習

STEP 2 で候補が見つからない、または `confidence < 5` の場合：

### 3-1: ユーザーへの質問

```
「{file_name}」の保管先が personal-index.yaml から特定できませんでした。

ファイル情報:
  - 種別: {file_type}
  - wiki分類先: {wiki_destination}

00personal/ 配下のどのフォルダに移動しますか？
パスを入力してください（例: 09_InformationOrganization/杏林堂/CX推進/）
```

### 3-2: ユーザーの回答を `feedback-log.md` に記録

```python
from datetime import date

def record_route_feedback(
    feedback_log_path: str,
    file_name: str,
    wiki_destination: str,
    user_selected_path: str
) -> None:
    """
    route-binary.md が判断できなかったケースをフィードバックログに記録する。
    同じパターンが3回蓄積したら classification-hints.md への追記を提案する。
    """
    today = date.today().isoformat()
    entry = f"""
## {today}
- ファイル: {file_name}
- wiki分類先: {wiki_destination}
- エージェント判断: （候補なし / 低信頼度）
- ユーザー選択: {user_selected_path}
- 理由: route-binary.md による00personal/振り分け
"""
    with open(feedback_log_path, 'a', encoding='utf-8') as f:
        f.write(entry)
```

### 3-3: 同一パターンが3回以上蓄積した場合の提案

`feedback-log.md` を読み込み、同じ `wiki_destination → personal_path` の
パターンが3回以上あれば、以下をユーザーに提案する：

```
以下のルールを classification-hints.md に追加しますか？

## 00personal/ 振り分けルール（学習）
| wiki_destination パターン | personal 保管先 |
|--------------------------|----------------|
| kyorindo/cx/             | 09_InformationOrganization/杏林堂/CX推進/ |

→ 承認する場合は「はい」と回答してください。
```

---

## STEP 4: ファイルを移動する

### 4-1: 移動先ディレクトリの確認

```python
import os
import shutil
import time

PERSONAL_ROOT = r"C:\Users\takatoshi-saito\OneDrive\00personal"

def move_to_personal(
    inbox_path: str,
    dest_folder: str,
    file_name: str,
    retries: int = 3,
    wait: int = 5
) -> str:
    """
    _inbox/ のファイルを 00personal/ の指定フォルダへ移動する。
    OneDrive ロック時は 5秒×3回リトライ。
    戻り値: 移動後の絶対パス
    """
    dest_dir = os.path.join(PERSONAL_ROOT, dest_folder)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, file_name)

    # 衝突チェック → _v2 自動付与
    dest_path = resolve_collision(dest_path)

    for attempt in range(retries):
        try:
            shutil.move(inbox_path, dest_path)
            return dest_path
        except PermissionError:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行")
                time.sleep(wait)
            else:
                raise RuntimeError(f"ファイル移動に失敗しました: {inbox_path}")
```

### 4-2: ファイル名衝突時の自動リネーム（_v2 付与）

```python
def resolve_collision(dest_path: str) -> str:
    """
    移動先に同名ファイルが存在する場合、_v2/_v3 を自動付与する。
    """
    if not os.path.exists(dest_path):
        return dest_path

    base, ext = os.path.splitext(dest_path)
    version = 2
    while os.path.exists(f"{base}_v{version}{ext}"):
        version += 1
    return f"{base}_v{version}{ext}"
```

---

## STEP 5: `personal-index.yaml` のフォルダ統計を更新する

移動先フォルダの `file_count` と `last_updated`（独自フィールド）を更新する。

```python
def update_personal_index(
    index_path: str,
    dest_folder: str,
    moved_file_path: str
) -> None:
    """
    personal-index.yaml の対象フォルダエントリを更新する。
    フォルダが索引に未登録の場合は新規エントリを追加する。
    """
    today = date.today().isoformat()

    with open(index_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    folders = data.get('folders', [])
    target = next((f for f in folders if f['path'] == dest_folder), None)

    if target:
        # 既存エントリを更新
        target['file_count'] = target.get('file_count', 0) + 1
        target['last_updated'] = today
    else:
        # 新規エントリを追加
        folders.append({
            'path': dest_folder,
            'description': f'{dest_folder} 関連資料',
            'type': 'その他',
            'keywords': [],
            'file_count': 1,
            'last_updated': today,
            'searchable': True,
        })
        data['folders'] = sorted(folders, key=lambda x: x['path'])

    # メタ情報も更新
    data['meta']['generated'] = today

    with open(index_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
```

---

## STEP 5.5: `processed-sources.yaml` の移動結果を更新する

ファイル移動が完了したタイミングで、`processed-sources.yaml` の該当レコードを更新する。

```python
import yaml
import time

PROCESSED_SOURCES_PATH = os.path.join(
    r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase",
    "_system", "processed-sources.yaml"
)

def update_binary_result(
    inbox_file_name: str,
    dest_personal_path: str,
    retries: int = 3,
    wait: int = 5,
) -> None:
    """
    processed-sources.yaml のレコードを更新する。
    通常の inbox-agent フローでは source_path が inbox ファイル名で仮登録されている。
    移動完了後に source_path を 00personal 相対パスに確定させ、移動結果を記録する。
    """
    if not os.path.exists(PROCESSED_SOURCES_PATH):
        return

    for attempt in range(retries):
        try:
            with open(PROCESSED_SOURCES_PATH, "r", encoding="utf-8") as f:
                records = yaml.safe_load(f) or []

            for r in records:
                # inbox ファイル名を仮キーとして照合
                if r.get("source_path") == inbox_file_name:
                    r["source_path"]        = dest_personal_path   # 確定パスに更新
                    r["binary_moved"]       = True
                    r["binary_destination"] = dest_personal_path
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
# STEP 4 のファイル移動が成功した場合のみ実行
inbox_file_name    = os.path.basename(original_file)   # "_inbox/xxx.pptx" のファイル名部分
dest_personal_path = os.path.relpath(
    moved_to,
    r"C:\Users\takatoshi-saito\OneDrive\00personal"
).replace("\\", "/")

update_binary_result(inbox_file_name, dest_personal_path)
```

---

## STEP 6: 結果を出力する

```yaml
status: success
original_file: "KnowledgeBase/_inbox/CX_roadmap_v4.pptx"
moved_to: "00personal/09_InformationOrganization/杏林堂/CX推進/CX_roadmap_v4.pptx"
dest_folder: "09_InformationOrganization/杏林堂/CX推進/"
collision_resolved: false          # _v2 付与したか
personal_index_updated: true       # personal-index.yaml を更新したか
processed_sources_updated: true    # processed-sources.yaml を更新したか
user_confirmed: false              # ユーザー確認を経たか
feedback_recorded: false           # feedback-log.md に記録したか
errors: []
```

---

## エラーハンドリング

| 発生箇所 | 対処 |
|---------|------|
| `personal-index.yaml` 読み込み失敗 | エラーを出力しSTEP 2をスキップ → ユーザー確認（Q4-B）へ |
| フォルダ作成失敗（WinError 5） | 5秒×3回リトライ → 失敗時はエラーを記録してスキップ |
| ファイル移動失敗（WinError 5） | 同上 |
| `personal-index.yaml` 書き込み失敗 | エラーを記録。ファイル移動自体はロールバックしない |

---

## エラーハンドリング追記

| 発生箇所 | 対処 |
|---------|------|
| `processed-sources.yaml` 更新失敗 | エラーを記録するが、ファイル移動はロールバックしない |

---

## 呼び出し元・呼び出し先

```
place-wiki.md
    └─→ route-binary.md（本スキル）
            ├─→ feedback-log.md（ユーザー確認が発生した場合に記録）
            └─→ processed-sources.yaml（binary_moved / binary_destination を更新）
```
