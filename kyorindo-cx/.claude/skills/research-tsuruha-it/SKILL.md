---
name: research-tsuruha-it
description: ツルハHDグループ・ウエルシアグループ全社のIT・DX関連記事やプレスリリースをWebで収集し、
  kyorindo-cx/04_references に個別マークダウンファイルとして保存、インデックスMDとExcelデータベースを更新するスキル。
  「ツルハ IT調査」「ツルハHD記事収集」「ツルハDX情報更新」「競合IT情報収集」「ツルハ プレスリリース収集」
  などのフレーズで発動。初回は3年分、2回目以降は直近1か月分を収集する。
---

# ツルハHDグループ IT記事収集スキル

## 調査対象企業

### ツルハグループ
- ツルハホールディングス（ツルハHD）
- ツルハドラッグ（株式会社ツルハ）
- くすりの福太郎
- ツルハグループドラッグ&ファーマシー西日本
- レデイ薬局 / くすりのレデイ
- 杏林堂薬局
- ドラッグイレブン
- ツルハグループマーチャンダイジング
- ツルハフィナンシャルサービス

### ウエルシアグループ（2025年12月よりツルハHD完全子会社）
- ウエルシアホールディングス
- ウエルシア薬局
- ウェルパーク
- コクミン
- ププレひまわり
- クスリのマルエ
- シミズ薬品
- 丸大サクラヰ薬局
- よどや
- ふく薬品
- 株式会社エクスチェンジ（グループ内システム開発・運用）

## ファイル保存先

```
C:/Users/takatoshi-saito/OneDrive/00personal/ClaudeCodeFolder/kyorindo-cx/04_references/
```

- **個別記事ファイル**: 記事1件につき1ファイル
- **インデックスファイル（親）**: `ツルハHD_IT関連記事まとめ_*.md`（最新の日付のもの）

---

## 実行フロー

### STEP 0: 検索期間の判定

`04_references/` 内のツルハHD関連ファイルの存在を確認する：

- **ファイルが存在しない（初回）** → 検索期間 = **過去3年間**
- **ファイルが存在する（2回目以降）** → 検索期間 = **直近1か月**

```
既存ファイル確認方法:
  04_references/ 内に "ツルハHD_" で始まるファイルが何件あるか数える
  → 0件なら初回、1件以上なら継続
```

---

### STEP 1: 記事・プレスリリースをWebSearchで並列収集

以下のクエリを **並列で** WebSearch実行する。
検索期間はSTEP 0で確定した範囲を意識してクエリに含める（例: `2024 2025 2026`）。

| クエリ | 目的 |
|--------|------|
| `"ツルハHD OR ツルハホールディングス" IT DX システム 導入` | グループ全体のIT施策 |
| `"ツルハ OR ウエルシア" AI 生成AI プレスリリース` | AI活用事例 |
| `"くすりの福太郎 OR 杏林堂 OR レデイ薬局 OR ドラッグイレブン" IT デジタル` | 傘下各社のIT動向 |
| `"ウエルシア薬局 OR ウェルパーク OR コクミン" DX システム` | ウエルシア傘下各社 |
| `"ツルハ OR ウエルシア" リテールメディア データクリーンルーム データ活用` | データ・広告基盤 |
| `"ツルハ OR ウエルシア" アプリ ポイント 共通 顧客ID` | 顧客接点・アプリ |
| `"ツルハ OR ウエルシア" セキュリティ インフラ クラウド ネットワーク` | インフラ・セキュリティ |
| `"エクスチェンジ ツルハ OR ウエルシア" システム開発` | グループIT子会社動向 |

---

### STEP 2: 既存ファイルとの重複チェック

`04_references/` 内の既存ファイルを確認し、以下のいずれかに該当すれば **スキップ**する：

- ファイル名に同じ日付・同じキーワードが含まれる
- ファイル内のURLが収集記事のURLと一致する

---

### STEP 3: 新規記事の詳細をWebFetchで取得

新規と判定した記事URLに対し **並列で** WebFetchを実行し、以下を抽出する：

- タイトル・掲載日・著者名・媒体名
- 本文全文（要約でなく詳細）
- 数字・データ（店舗数・ユーザー数・効果指標など）
- システム名・ベンダー名・サービス名
- 今後の展開・スケジュール
- 引用（関係者コメントなど）

---

### STEP 4: 個別マークダウンファイルを作成・保存

#### ファイル命名規則

```
ツルハHD_{テーマ}_{YYYYMMDD}.md
```

例：
- `ツルハHD_生成AI店舗ナレッジ検索_20260324.md`
- `ツルハHD_ウエルシアDCR統合_20251202.md`
- `ツルハHD_共通アプリ顧客ID統一_20260417.md`

#### ファイルテンプレート

```markdown
# {タイトル}

**出典**: [{媒体名}]({URL})
**掲載日**: YYYY年MM月DD日
**著者**: {著者名}（なければ省略）

---

## 概要

{3〜5行の要約}

---

## 主要内容

### {見出し1}
{詳細}

### {見出し2}
{詳細}

---

## 数字・データ

| 指標 | 値 |
|------|----|
| {指標名} | {値} |

---

## キーワード

`{タグ1}` `{タグ2}` `{タグ3}` ...

---

## 業界文脈（あれば）

{競合比較・業界における位置づけなど}
```

---

### STEP 5: Excelデータベースを更新

`04_references/ツルハHD_IT記事データベース.xlsx` を作成・更新する。

#### Excelファイルのパス

```
C:/Users/takatoshi-saito/OneDrive/00personal/ClaudeCodeFolder/kyorindo-cx/04_references/ツルハHD_IT記事データベース.xlsx
```

#### カラム定義

| カラム名 | 内容 |
|---------|------|
| 掲載日 | YYYY/MM/DD形式 |
| タイトル | 記事タイトル |
| カテゴリ | 下記カテゴリ一覧より選択 |
| 媒体名 | 掲載媒体・発表元 |
| URL | 元記事URL |
| 概要 | 2〜3行の要約 |
| キーワード | スペース区切りのタグ |
| 関連ベンダー/企業 | ベンダー名・システム名 |
| MDファイル名 | 作成したMDファイルのファイル名 |
| 追加日 | DBへの追加日（YYYY/MM/DD） |

#### カテゴリ一覧

```
AI活用 / 店舗DX / リテールメディア / 調剤・医療 / データ基盤 / インフラ / 決算・経営
```

カテゴリ判定の目安：
- **AI活用**: 生成AI、機械学習、予測AI、VoC分析など
- **店舗DX**: 業務端末、スマートフォン化、店舗オペレーション効率化
- **リテールメディア**: 広告事業、データクリーンルーム、メーカー向け配信
- **調剤・医療**: 薬歴、調剤業務、医療連携
- **データ基盤**: 基幹システム、ID統合、データプラットフォーム
- **インフラ**: クラウド、ネットワーク、セキュリティ
- **決算・経営**: 決算発表、戦略発表、シナジー計画

#### Python実装コード

```python
import sys
import os
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')

try:
    from openpyxl import load_workbook, Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    os.system("pip install openpyxl")
    from openpyxl import load_workbook, Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

EXCEL_PATH = r"C:/Users/takatoshi-saito/OneDrive/00personal/ClaudeCodeFolder/kyorindo-cx/04_references/ツルハHD_IT記事データベース.xlsx"

COLUMNS = ["掲載日", "タイトル", "カテゴリ", "媒体名", "URL", "概要", "キーワード", "関連ベンダー/企業", "MDファイル名", "追加日"]

# ファイルが存在しない場合は新規作成
if not os.path.exists(EXCEL_PATH):
    wb = Workbook()
    ws = wb.active
    ws.title = "記事一覧"
    # ヘッダー行
    for col_idx, col_name in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", start_color="1F3864")
        cell.alignment = Alignment(horizontal="center")
    # 列幅調整
    widths = [12, 40, 14, 20, 50, 50, 30, 30, 45, 12]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    wb.save(EXCEL_PATH)

wb = load_workbook(EXCEL_PATH)
ws = wb.active

# 既存データのURL・MDファイル名を収集（重複チェック用）
existing_urls = set()
existing_md_names = set()
url_col = COLUMNS.index("URL") + 1
md_col = COLUMNS.index("MDファイル名") + 1

for row in ws.iter_rows(min_row=2, values_only=True):
    if row[url_col - 1]:
        existing_urls.add(str(row[url_col - 1]).strip())
    if row[md_col - 1]:
        existing_md_names.add(str(row[md_col - 1]).strip())

today_str = date.today().strftime("%Y/%m/%d")

# new_articles = [ {掲載日, タイトル, カテゴリ, 媒体名, URL, 概要, キーワード, 関連ベンダー/企業, MDファイル名} ]
# ← STEP 4で作成したファイルの情報を辞書リストとして渡す

added = 0
for article in new_articles:
    url = article.get("URL", "").strip()
    md_name = article.get("MDファイル名", "").strip()
    # 重複スキップ
    if url in existing_urls or md_name in existing_md_names:
        continue
    row_data = [
        article.get("掲載日", ""),
        article.get("タイトル", ""),
        article.get("カテゴリ", ""),
        article.get("媒体名", ""),
        url,
        article.get("概要", ""),
        article.get("キーワード", ""),
        article.get("関連ベンダー/企業", ""),
        md_name,
        today_str,
    ]
    ws.append(row_data)
    existing_urls.add(url)
    existing_md_names.add(md_name)
    added += 1

wb.save(EXCEL_PATH)
print(f"Excel更新完了: {added}件追加 → {EXCEL_PATH}")
```

---

### STEP 6: インデックスファイル（親ファイル）を更新

`04_references/` 内の `ツルハHD_IT関連記事まとめ_*.md` を検索し、最新のものを更新する。
存在しない場合は `ツルハHD_IT関連記事まとめ_{今日の日付}.md` を新規作成する。

#### インデックスファイルの構成

```markdown
# ツルハHD IT関連記事・プレスリリース まとめ

**更新日**: YYYY年MM月DD日

---

## 記事一覧（新しい順）

| 日付 | タイトル | テーマ | ファイル |
|------|---------|--------|--------|
| 2026/04/17 | DX戦略：共通アプリ・顧客ID統一 | DX戦略 | [link](ツルハHD_DX戦略_共通アプリ顧客ID統一_20260417.md) |
| ...（新規追記） | | | |

---

## DX戦略 全体像

{既存の全体構造図を維持しつつ、新情報があれば追記}

---

## 参考URL

{記事URLのリスト（新規追記）}
```

新規記事は **表の先頭行に追記**（新しい順を維持）する。

---

### STEP 7: GitHubへコミット＆プッシュ

STEP 4〜6で作成・更新したファイルをまとめてGitHubにプッシュする。

```bash
cd "C:/Users/takatoshi-saito/OneDrive/00personal/ClaudeCodeFolder/kyorindo-cx"

# 新規MDファイル・Excel・インデックスMDをステージ
git add "04_references/ツルハHD_*.md"
git add "04_references/ツルハHD_IT記事データベース.xlsx"

# コミット（新規追加件数・期間を含む）
git commit -m "ツルハHD IT記事収集: {N}件追加（{検索期間}分）

- 新規MDファイル {N}件
- Excelデータベース更新 ({N}件追加)
- インデックスMD更新"

# プッシュ
git push origin main
```

#### GitHubでの確認URL

プッシュ後、以下で確認できる：

```
https://github.com/{owner}/{repo}/blob/main/04_references/ツルハHD_IT記事データベース.xlsx
```

※ `.xlsx` はGitHub上でプレビュー表示される。

#### 注意

- `git push` 前に `git status` で意図しないファイルが含まれていないか確認する
- Excelファイルが大きい場合（>50MB）はGit LFSが必要だが、通常の記事データベースは問題ない

---

### STEP 8: 完了報告

以下を日本語で報告する：

```
## 収集完了

**検索期間**: {初回: 過去3年 / 継続: 直近1か月}
**新規作成ファイル**: {N}件
  - {ファイル名1}
  - {ファイル名2}
**スキップ（重複）**: {N}件
**Excelデータベース**: {N}件追加 → ツルハHD_IT記事データベース.xlsx
**インデックス更新**: {更新済 / 新規作成}
**GitHub**: プッシュ済 → {リポジトリURL}/blob/main/04_references/ツルハHD_IT記事データベース.xlsx
```

---

## 注意事項

- 記事の要約ではなく**詳細情報**を保存する（数字・引用・スケジュールは必ず含める）
- ペイウォール（有料記事）でWebFetchが取得できない場合は、タイトル・日付・URLのみ記録してスキップ旨を明記する
- 同一プレスリリースが複数媒体に掲載されている場合は、**最も詳細な1件**のみ保存する
- ウエルシアグループの記事でもツルハHDグループとして命名・分類する（2025年12月に完全子会社化済み）
