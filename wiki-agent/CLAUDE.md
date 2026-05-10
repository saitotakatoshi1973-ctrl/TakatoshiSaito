# wiki-agent CLAUDE.md

## 目的

> LLM検索効率とユーザーの投入手軽さを両立させ、wikiが陳腐化しない仕組みを維持する

---

## 現行方針

`wiki-agent` の主入口は `skills/batch-inbox.md` とする。

`agents/inbox-agent.md` は `_inbox/` 直下のファイルを処理する旧入口として残すが、現行の正本フローではない。今後、削除または薄い互換ラッパーへの整理を検討する。

分類とwiki本文生成は `scripts/gemini_wiki_generator.py` に寄せる Gemini モードを標準とする。`--analyze-only` で分類し、`--generate` で本文生成する。`analyze.md` は分類失敗・低信頼度・重要資料のフォールバックとして残す。

---

## スコープ

### 担当範囲

- `KnowledgeBase/` 全体の管理・整合性維持
- `00personal/` の指定フォルダから、未処理・更新・部分失敗ファイルを wiki 化する
- `processed-sources.yaml` によるソースファイルと wiki の対応管理
- `_overview.md`、`wiki-embeddings.npz`、`change_log`、学習ログの更新
- Web検索結果の wiki 化

### 対象外

- `00personal/` の自律的な整理（将来の personal-agent が担当）
- 既存wiki記事の内容書き換え（ユーザー承認必須）
- `KnowledgeBase/` / 指定された作業対象フォルダ以外の自律的な操作
- AGENTS.md の確認ルールを省略したファイル削除・プログラム実行・外部コマンド実行

---

## 入口

| 入口 | ファイル | 位置づけ |
|------|----------|----------|
| フォルダ一括wiki化 | `skills/batch-inbox.md` | 現行の主入口。指定フォルダを走査し、必要なファイルだけ wiki 化する |
| Web検索wiki化 | `skills/web-search.md` | Web検索結果を wiki 化する単独入口 |
| メンテナンス | `agents/maintenance-agent.md` | index、overview、personal-index、ログ、分類学習の保守 |
| `_inbox` 処理 | `agents/inbox-agent.md` | 旧入口。整理予定。現行の正本フローではない |

---

## スキル一覧

| スキル | 責務 | 主な参照・更新ファイル |
|--------|------|------------------------|
| `batch-inbox.md` | 指定フォルダの未処理・更新・部分失敗ファイルを一括 wiki 化 | `processed-sources.yaml` |
| `convert-binary.md` | PDF / PPTX / XLSX / DOCX 等のテキスト抽出 | 対象ファイル |
| `analyze.md` | ファイル分析・分類先・wiki_type・信頼度判定 | `SCHEMA.md`、`classification-hints.md`、`wiki-embeddings.npz` |
| `write-wiki.md` | 旧/互換用の wiki Markdown 生成 | `SCHEMA.md`、`gemini_wiki_generator.py` |
| `place-wiki.md` | wiki配置後処理のオーケストレーション | `_overview.md`、`change_log_YYYY-MM.md`、`processed-sources.yaml` |
| `route-binary.md` | `_inbox` 旧フロー時の元ファイル振り分け | `personal-index.yaml`、`personal-rules.md` |
| `update-overview.md` | `_overview.md` 自動生成・更新 | 各 wiki ファイルの Front-matter |
| `index-builder.md` | `wiki-embeddings.npz` の add / rebuild | 全 wiki ファイル |
| `check-integrity.md` | Front-matter 欠落、index 未登録、空ファイル等の検出・補正 | `SCHEMA.md`、`processed-sources.yaml` |
| `sync-personal.md` | `00personal/` 実フォルダと personal-index の同期 | `personal-index.yaml` |
| `sync-wiki.md` | KnowledgeBase に直接追加された wiki の検知・後処理 | `wiki-embeddings.npz`、`_overview.md` |
| `update-changelog.md` | 3ヶ月超の月次ログを年次サマリーへ圧縮 | `change_log_YYYY-MM.md` |
| `record-feedback.md` | 分類修正をフィードバックログへ記録 | `feedback-log.md` |
| `learn-from-feedback.md` | 反復する分類修正から補足ルール候補を作成 | `classification-hints.md` |
| `web-search.md` | Web検索、重複チェック、wiki生成 | `search-topics.yaml`、`wiki-embeddings.npz` |

---

## 正本フロー: batch-inbox

```
ユーザーが対象フォルダを指定
    ↓
[batch-inbox.md]
  ├─ 対象フォルダを走査
  ├─ クラウド専用ファイルをファイル名・パスで事前判定
  ├─ 必要に応じて OneDrive からローカル化
  ├─ processed-sources.yaml と照合
  ├─ 未処理・内容更新・部分失敗のみ処理対象化
  └─ 処理予定を提示し、ユーザー確認後に実行
    ↓
対象ファイルを KnowledgeBase/_inbox/ に一時コピー
    ↓
[convert-binary.md]
    ↓
[gemini_wiki_generator.py --analyze-only]
  ├─ SCHEMA.md / classification-hints.md を参照
  ├─ 分類先・wiki_type・title・信頼度をJSONで出力
  └─ --emit-usage でGemini側の使用量を記録
    ↓
[gemini_wiki_generator.py --generate]
  ├─ 分類結果JSONを受け取り、本文Markdownを生成
  └─ --emit-usage で本文生成コストを記録
    ↓
[place-wiki.md]
  ├─ batch_mode=true で重い後処理は一括 flush へ延期
  ├─ skip_route_binary=true で route-binary.md は実行しない
  └─ processed-sources.yaml に処理状態を記録
    ↓
_inbox/ の一時コピーを削除
    ↓
一括後処理
  ├─ update-overview.md
  ├─ change_log_YYYY-MM.md
  ├─ index-builder.md add
  └─ processed-sources.yaml 一括更新
```

`batch-inbox.md` では元ファイルは `00personal/` に残る。`_inbox/` に置くファイルは処理用コピーであり、処理後に削除する。

---

## Gemini 分類・生成方針

- 標準は `use_gemini: true`
- 分類は `gemini_wiki_generator.py --analyze-only` を使う
- 本文生成は `gemini_wiki_generator.py --generate` を使う
- `--emit-usage` で Gemini 側の token usage と入出力文字数を記録する
- Front-matter、保存、配置後処理は `place-wiki.md` 側で管理する
- Gemini 分類が失敗した場合、分類結果が低信頼度の場合、重要資料で分類精度を優先する場合は `analyze.md` へフォールバックする
- `write-wiki.md` は旧/互換用として残すが、batch-inbox の正本低コスト経路では原則使わない

---

## ユーザー確認が必要な操作

AGENTS.md の運用ルールを優先する。

- ファイル削除
- プログラム実行
- 外部コマンド実行
- 新トップカテゴリ追加
- 既存カテゴリの廃止・統合
- 既存wiki記事の内容書き換え
- 削除済みソースファイルに対応する wiki の削除または outdated 化
- 分類先が判断できない場合の保存先決定

`batch-inbox.md` の `_inbox/` 一時コピー削除は、ユーザーがその処理計画を承認した batch 実行の範囲内で行う。

---

## change_log 管理

- 記録粒度: ファイル1件ずつ詳細記録
- ファイル分け: 月次（`change_log_YYYY-MM.md`）
- インデックス: `change_log.md`（各月ファイルへのリンク）
- 圧縮: 3ヶ月経過後に `update-changelog.md` が年次サマリーへ集約

```
_system/
├── change_log.md
├── change_log_2026-05.md
├── change_log_2026-04.md
└── archive/
    └── change_log_2026.md
```

---

## 自動学習

セッション間のメモリはファイルベースで実現する。

### フィードバック記録（`_system/learning/feedback-log.md`）

ユーザーが分類を修正したとき、`record-feedback.md` が記録する。

```markdown
## YYYY-MM-DD
- ファイル: （ファイル名）
- エージェント判断: （分類先）
- ユーザー修正: （修正後の分類先）
- 理由: （ユーザーのコメントがあれば記載）
```

### 分類補足ルール（`_system/learning/classification-hints.md`）

同じパターンのフィードバックが3回以上蓄積したら、`learn-from-feedback.md` が補足ルール候補を作成する。追記はユーザー承認後に行う。

---

## 参照ファイル一覧

| ファイル | 用途 |
|---------|------|
| `KnowledgeBase/_system/SCHEMA.md` | wiki構造ルール・カテゴリ定義 |
| `KnowledgeBase/_system/wiki-embeddings.npz` | 類似検索・重複チェック用 index |
| `KnowledgeBase/_system/processed-sources.yaml` | ソースファイルと wiki の対応、処理状態、削除検出 |
| `KnowledgeBase/_system/personal/personal-index.yaml` | `00personal/` フォルダ索引 |
| `KnowledgeBase/_system/personal/personal-rules.md` | `00personal/` 構成ルール |
| `KnowledgeBase/_system/learning/feedback-log.md` | 分類フィードバック記録 |
| `KnowledgeBase/_system/learning/classification-hints.md` | 分類補足ルール |
| `KnowledgeBase/_system/search-topics.yaml` | Web検索トピック定義 |

---

## バックアップ方針

OneDrive のバージョン履歴に委ねる。エージェントによるバックアップファイル作成は不要。

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-04-30 | 初版作成（STEP 1〜6 の設計をもとに策定） |
| 2026-05-10 | 主入口を `batch-inbox.md` に統一し、分類・本文生成を `gemini_wiki_generator.py` に寄せる方針を明記 |
