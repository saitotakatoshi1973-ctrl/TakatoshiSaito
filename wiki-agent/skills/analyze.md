# analyze — ファイル分析・分類先判定

## 目的
`_inbox/` に投入されたファイルを読み込み、以下を判定する。
1. ファイル種別（テキスト系 / 画像系 / 要変換系）
2. KnowledgeBase の分類先パス
3. 推奨 Front-matter フィールド値
4. `convert-binary.md` が必要か否か
5. バイナリファイルの `00personal/` 移動先

## 参照ファイル

- `KnowledgeBase/_system/SCHEMA.md` — カテゴリ定義・分類ルール
- `KnowledgeBase/_system/learning/classification-hints.md` — 補足分類ルール（学習済み）

> **バッチ処理時の注意（クレジット削減）**:
> `batch-inbox.md` から呼び出された場合、これらのファイルは
> バッチ開始時に **1回だけ** 読み込み済みである。
> ファイルごとに再読み込みしないこと（コンテキスト上のデータをそのまま使う）。
> 単独で呼び出された場合（inbox-agent.md 経由など）のみ、ここで読み込む。

---

## STEP 1: ファイル一覧取得

`KnowledgeBase/_inbox/` 内のファイルを一覧表示する。
**処理は必ず1件ずつ順番に行う**（複数ある場合も並列処理しない）。

バッチ上限: 1回の実行で **最大5ファイル** まで処理する。
5件を超える場合はユーザーに通知し、残りは次回実行を促す。

---

## STEP 2: ファイル種別の判定

拡張子をもとに種別を判定し、次のアクションを決定する。

| 種別 | 対象拡張子 | 次のアクション |
|------|-----------|-------------|
| テキスト系 | `.md` `.yaml` `.json` `.csv` `.html` `.svg` | そのまま読み込み → STEP 3-A |
| テキスト系（.txt） | `.txt` | 先頭5行を確認 → URL行が過半数なら STEP 3-D、それ以外は STEP 3-A |
| 画像系 | `.png` `.jpg` `.jpeg` `.gif` `.webp` | マルチモーダル読み込み → STEP 3-B |
| 要変換系 | `.pdf` `.pptx` `.xlsx` `.docx` `.mp3` `.wav` `.m4a` `.ogg` `.mp4` `.mov` `.avi` `.mkv` `.eml` `.zip` | `convert-binary.md` を呼び出し → STEP 3-C |
| URL リスト | `.txt`（URL行が過半数） | `convert-binary.md`（url_list）を呼び出し → STEP 3-D |

---

## STEP 3: ファイル内容の把握

### 3-A: テキスト系（直接読み込み）

拡張子ごとに以下のポイントを重点的に読み込む。

| 拡張子 | 読み込みポイント |
|--------|--------------|
| `.md` | タイトル（# 行）/ 見出し構造（## ###）/ 冒頭200文字の要旨 |
| `.txt` | 冒頭300文字・末尾100文字 / 固有名詞・組織名 |
| `.yaml` `.json` | キー名と主要な値 / 構造の概要（ネスト深さ） |
| `.csv` | ヘッダー行 + 先頭5行 / 列の意味とデータ件数 |
| `.html` | `<title>` / `<h1>`〜`<h3>` / メインコンテンツ冒頭200文字 |
| `.svg` | `<title>` / `<text>` 要素 / 図の概要（フローチャート・組織図など） |

**全形式共通で抽出する情報**:
- 文書のタイトル・主題
- 日付情報（文書内の日付またはファイル名の日付）
- 登場する組織名・固有名詞（杏林堂 / ツルハ / ベンダー名など）
- 文書の種別（戦略資料 / 議事録 / 調査レポート / タスク一覧など）

### 3-B: 画像系（マルチモーダル読み込み）

`.png` `.jpg` `.jpeg` `.gif` `.webp` を対象とする。

**読み込み手順**:
1. 画像全体を視覚的に解析する
2. 以下の確認項目を順に記録する:

| 確認項目 | 判定内容 |
|---------|---------|
| 画像の種類 | スクリーンショット / フローチャート / グラフ / 写真 / 手書きメモ / 組織図 |
| 可視テキスト | タイトル・見出し・ラベル・数値・日付を抽出 |
| 組織・製品名 | 社名・ロゴ・システム名・ブランド名が含まれるか |
| 日付情報 | 画像内に日付が含まれるか |
| 図の種類 | フローチャート / アーキテクチャ図 / 棒グラフ / 円グラフ / 組織図 |

> **注意**: 画像単体では分類が難しいケースが多い。ファイル名・格納元フォルダも参考にする。

### 3-D: URL リスト（複数URL・1行1URL）

`.txt` ファイルの先頭5行を確認し、`http://` または `https://` で始まる行が過半数の場合、
**URLリストファイル**として処理する。

**処理フロー**:

```python
def detect_url_list(file_path: str) -> bool:
    """先頭5行を読んで URL リストか判定する"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines()[:5] if l.strip() and not l.startswith('#')]
        url_lines = [l for l in lines if l.startswith('http://') or l.startswith('https://')]
        return len(url_lines) >= len(lines) / 2 if lines else False
    except Exception:
        return False
```

**URLリストと判定した場合**:

1. `convert-binary.md`（url_list モード）を呼び出す
2. 戻り値は `list[dict]`（URL と取得コンテンツのペアリスト）
3. **URL 1件ごとに個別の wiki 記事を生成する**（STEP 4〜STEP 6 をループ）
4. バッチ上限は URL リスト内の件数に依らず **1回の実行で最大5件** まで

```
URLリストファイル 1件
    └─→ URL ① → analyze → write-wiki → place-wiki
    └─→ URL ② → analyze → write-wiki → place-wiki
    └─→ URL ③ → analyze → write-wiki → place-wiki
    ...（最大5件まで。残りは次回実行を促す）
```

**各URLの確認ポイント**:

| 確認項目 | 内容 |
|---------|------|
| ページタイトル | `<title>` または `<h1>` |
| 公開日・更新日 | メタタグ・本文中の日付 |
| 媒体・著者 | サイト名・byline |
| 主要トピック | 冒頭500文字の要旨 |
| 組織名・固有名詞 | 杏林堂・ツルハ・ベンダー名など |

**STEP 4 の `source` フィールド**:
```yaml
source: web
source_url: "https://example.com/article"
```

---

### 3-C: 要変換系（convert-binary.md 経由で読み込み）

`convert-binary.md` を呼び出してテキスト化されたものを受け取り、以下を確認する。

**形式別の確認ポイント**:

| 形式 | 確認ポイント |
|------|------------|
| `.pdf` | 冒頭ページのタイトル・著者・発行元 / 章立て・目次（あれば）/ ページ数 |
| `.pptx` | スライドタイトル一覧（全スライド）/ スライド1〜3枚目の本文 / 作成者・日付（プロパティ） |
| `.xlsx` | シート名一覧 / 各シートのヘッダー行（列構造）/ データ件数・主要な集計値 |
| `.docx` | ドキュメントタイトル（スタイル見出し）/ 章・セクション構造（H1・H2の一覧）/ 冒頭段落の要旨 |
| `.mp3` `.wav` `.m4a` `.ogg` | 文字起こし結果の冒頭500文字 / 主要トピック・キーワード |
| `.mp4` `.mov` `.avi` `.mkv` | 文字起こし結果の冒頭500文字 / 発話者の特定（可能であれば）|
| `.eml` | 差出人 / 宛先 / 件名 / 日付 / 本文の要旨（冒頭300文字）/ 添付ファイルの有無と種別 |
| `.zip` | 展開後のファイル一覧 / 各ファイルを上記ルールで再帰的に処理 |

---

## STEP 4: 分類先の判定（ハイブリッド3段階）

以下の順序で判定を進める。早い段階で確定したら以降はスキップしてよい。

---

### 4-1: classification-hints.md パターン照合（最優先・高速）

`classification-hints.md` を読み込み、ファイル名・内容のキーワードが
記載パターンに一致するか確認する。

- **一致した場合**: 即座に分類先を確定。4-2・4-3はスキップ。
- **一致しない場合**: 4-2へ進む。

---

### 4-2: LLMセマンティックスコアリング（追加インフラ不要）

`SCHEMA.md` の各カテゴリ説明文とファイル内容を意味的に比較し、
**トップカテゴリ** → **サブカテゴリ** の順にスコアリングする。

#### トップカテゴリのスコアリング

ファイル内容を以下の7カテゴリ説明文と比較し、類似度（0〜10点）を付与する。

| カテゴリ | 説明文（比較基準） |
|---------|-----------------|
| `kyorindo/` | 杏林堂薬局の社内情報。組織・人事・CX推進・情報システム・業務システム・予算など自社業務全般 |
| `tsuruha-hd/` | ツルハホールディングスおよびグループ会社（ウエルシア・TGN・薬の福太郎等）の情報。経営戦略・IT・DXなど |
| `retail/` | 小売業界の外部情報。ドラッグストア・スーパー・ホームセンター各社の動向・トレンド・ベンチマーク |
| `ai-dx/` | AI・DX・IT技術に関する業種横断の情報。ツール比較・活用事例・ガバナンス・トレンド |
| `vendor/` | ベンダー・コンサルとの取引関係に基づく情報。契約・見積・打ち合わせ記録・サービス概要 |
| `research/` | 調査・リサーチ・公的機関・セミナー・Web記事。テーマや内容ベースで整理される情報 |
| `_unsorted` | 上記いずれにも明確に当てはまらない場合の一時保留 |

**確定条件**: 最高スコアが **7以上** かつ 2位との差が **3以上** → 確定し4-3はスキップ。
それ以外は4-3へ進む。

#### サブカテゴリのスコアリング（トップカテゴリ確定後）

確定したトップカテゴリ配下のサブカテゴリに対して同様にスコアリングを行う。

**`kyorindo/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| CXロードマップ・戦略・MVV・方針 | `kyorindo/cx/strategy/` |
| CX推進部の会議記録・進捗サマリー | `kyorindo/cx/progress/` |
| 課題一覧・問題点の整理 | `kyorindo/cx/issues/` |
| AIユースケース一覧 | `kyorindo/cx/ai-usecase/` |
| タスク一覧・議論ログ | `kyorindo/cx/tasks/` |
| 組織図・体制図 | `kyorindo/organization/` |
| 現行システム一覧・アーキテクチャ | `kyorindo/it-systems/architecture/` |
| NW・サーバー・複合機 | `kyorindo/it-systems/infrastructure/` |
| セキュリティ・統制 | `kyorindo/it-systems/security/` |
| 規程・就業規則・職務規定 | `kyorindo/hr/regulations/` |
| 人事考課・人事異動 | `kyorindo/hr/personnel/` |
| 予算関連 | `kyorindo/budget/{cx\|it-systems\|productivity}/` |
| 業務システム（{system-name}単位） | `kyorindo/business-systems/` |

**`tsuruha-hd/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| 組織・経営・人事 | `tsuruha-hd/organization/` |
| 中期経営計画・LIFESTOREビジョン・経営戦略 | `tsuruha-hd/strategy/` |
| IT・DX記事・システム導入・データ基盤 | `tsuruha-hd/it-dx/` |
| ウエルシア関連 | `tsuruha-hd/subsidiaries/welcia/` |
| TGN関連 | `tsuruha-hd/subsidiaries/tgn/` |
| 薬の福太郎関連 | `tsuruha-hd/subsidiaries/kusuri-no-fukutaro/` |

**`retail/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| ドラッグストア各社の個別情報 | `retail/drugstore/{company}/` |
| 業界トレンド・市場データ | `retail/trends/` |
| DXベンチマーク・競合比較 | `retail/benchmark/` |
| スーパー・GMS | `retail/supermarket/` |
| ホームセンター | `retail/home-center/` |

**`ai-dx/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| AIツール・プラットフォーム比較・紹介 | `ai-dx/ai-tools/` |
| AI活用事例（業種横断） | `ai-dx/ai-cases/` |
| AIガバナンス・ポリシー・教育 | `ai-dx/ai-governance/` |
| DX戦略・方法論 | `ai-dx/dx-strategy/` |
| ITトレンド・新技術 | `ai-dx/tech-trends/` |

**`vendor/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| ベンダーとの打ち合わせ記録・見積・契約 | `vendor/{vendor-name}/` |
| ベンダー名で検索しそうな情報 | `vendor/{vendor-name}/` |

**`research/` のサブカテゴリ判定**:

| 内容の特徴 | 分類先 |
|-----------|--------|
| セミナー・展示会・講義の内容要約 | `research/seminar/` |
| 調査レポート・統計データ | `research/reports/` |
| デジ庁・経産省・自治体等の公的情報 | `research/public-sector/` |
| Web記事まとめ | `research/web-articles/` |

---

### 4-3: 既存wiki類似検索（スコアが拮抗している場合のみ）

`sentence-transformers` で事前生成した埋め込みインデックスを使い、
既存wikiファイルとのコサイン類似度を計算して分類先の裏付けを取る。

**インデックスファイル**: `KnowledgeBase/_system/wiki-embeddings.npz`
（`index-builder.md` が生成・更新する。存在しない場合はこのSTEPをスキップ）

```python
# 概念コード（Pythonスクリプトとして実行）
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# 新ファイルの埋め込みを生成（タイトル＋冒頭500文字）
new_embedding = model.encode(title + "\n" + file_content[:500])

# 既存インデックスを読み込み
data = np.load('KnowledgeBase/_system/wiki-embeddings.npz', allow_pickle=True)
embeddings = data['embeddings']   # shape: (N, dim)
paths = data['paths']             # 各wikiファイルのパス

# コサイン類似度を計算して上位5件を取得
similarities = np.dot(embeddings, new_embedding) / (
    np.linalg.norm(embeddings, axis=1) * np.linalg.norm(new_embedding)
)
top5_idx = np.argsort(similarities)[-5:][::-1]
top5 = [(paths[i], float(similarities[i])) for i in top5_idx]
```

**結果の活用**:
- 上位3件の **過半数が同一カテゴリ** → そのカテゴリに確定
- 分散していて判断できない → STEP 5（ユーザー同期質問）へ

---

### 4-4: vendor / research の境界判定（迷いやすいケースの特別ルール）

4-1〜4-3でスコアが拮抗しやすいケース。以下の軸で最終判断する。

| 判断軸 | `vendor/` | `research/` または `ai-dx/` |
|--------|-----------|---------------------------|
| 検索起点 | ベンダー名で検索する | テーマ・技術名で検索する |
| 内容の性質 | 取引・関係性ベース（契約・見積・MTG記録） | 知識・内容ベース（講義・調査・一般知見） |
| 具体例 | Salesforce との打ち合わせ資料 | Salesforce の機能比較記事 |
| 具体例 | 松尾研の契約・見積 | 松尾研セッションの講義内容要約 |

---

### 4-5: 新規サブフォルダの必要性判定

既存サブフォルダに該当カテゴリがない場合:
- 同種のファイルが将来 **5件以上** 見込まれる → 新規サブフォルダを自動作成してよい
- 5件未満の見込み → 親フォルダに直接配置

---

### 4-6: バイナリファイルの 00personal/ 振り分け先判定

バイナリファイル（元資料）の移動先は `personal-index.yaml` と
`personal-rules.md` を参照して決定する。

| ファイルの帰属 | 00personal/ の移動先 |
|-------------|-------------------|
| 杏林堂CX推進部関係 | `03_CX推進/{適切なサブフォルダ}/` |
| ツルハHD関係 | `09_InformationOrganization/他社/ツルハHD/{適切なフォルダ}/` |
| ベンダー関係 | `09_InformationOrganization/ベンダー・コンサル/{ベンダー名}/` |
| その他 | `personal-index.yaml` の `type` と `path` を参照して最適フォルダを選択 |

---

## STEP 5: 分類不明の場合

### 通常モード（batch_auto_classify=False）

分類先が確定できない場合は **必ずユーザーに同期質問する**。
推測で移動しない。

```
質問例:
「[ファイル名] の内容は「〇〇」と読み取りましたが、
分類先が確定できませんでした。以下のどれが適切ですか？

1. tsuruha-hd/strategy/
2. tsuruha-hd/it-dx/
3. retail/benchmark/
4. その他（パスを指定してください）
```

### バッチ自動進行モード（batch_auto_classify=True）

`batch_auto_classify=True` の場合、信頼度 < 6 でも **ユーザー確認なしで自動進行** する。

```python
if batch_auto_classify and confidence_score < 6:
    # 最高スコアの候補を採用して処理続行
    # 出力YAMLに auto_classified=True を付加してバッチ側でリスト管理する
    result["auto_classified"] = True
    result["confidence_score"] = confidence_score
    # → STEP 6 へ進む（ユーザー確認なし）
```

バッチ処理完了後、STEP 7 完了レポートに自動進行ファイルの一覧を表示する：

```
⚠️ 低信頼度で自動分類したファイル（要レビュー）: 2件
  - データ受け渡しファイル定義.xlsx → kyorindo/it-systems/architecture/ [信頼度: 5]
  - 体制図220826.pptx → kyorindo/organization/ [信頼度: 4]
  → 分類が誤っている場合は手動で移動してください
```

---

## STEP 6: 分析結果の出力

以下のYAML形式で判定結果を出力し、次のスキルへ渡す。

```yaml
file: （ファイル名）
file_type: text | image | binary
needs_convert: true | false
destination: （KnowledgeBase相対パス / 例: kyorindo/cx/strategy/）
binary_destination: （00personal相対パス / バイナリの場合のみ）
front_matter:
  wiki_type: organization | strategy | issue | progress | reference | task | log | benchmark | research
  title: （推奨タイトル）
  scope: kyorindo | tsuruha-hd | retail | industry | general
  domain: cx | it-systems | hr | management | budget | retail | ai-dx | vendor | research
  status: current | draft
  source: agent | web | internal_doc | seminar
  source_url: （Web記事の場合のみ）
  tags: []
classification_confidence: high | medium | low
classification_method: hints | llm_score | embedding | user
```

---

## STEP 7: ユーザー修正の検知

分析結果をユーザーが修正した場合（分類先・Front-matter値の変更）は、
処理継続前に `record-feedback.md` を呼び出して修正内容を記録する。

記録後、**修正された値** を使って処理を継続する。
