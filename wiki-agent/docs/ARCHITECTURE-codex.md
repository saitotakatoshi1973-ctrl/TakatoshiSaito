# wiki-agent Codex運用アーキテクチャ

## 目的

この文書は、`wiki-agent` を Codex で運用する際の全体像、各エージェント・スキルの使い分け、主要フロー、並行運用時の注意点をまとめる。

図版: [ARCHITECTURE-codex.svg](./ARCHITECTURE-codex.svg)

---

## 全体像

`wiki-agent` は、`KnowledgeBase/` を中心に資料を wiki 化し、検索しやすい状態を維持するための仕組みである。

主な入口は次の2つ。

| 入口 | ファイル | 用途 |
|---|---|---|
| inbox処理 | `agents/inbox-agent.md` | `KnowledgeBase/_inbox/` に投入されたファイルを1件ずつ wiki 化する |
| メンテナンス | `agents/maintenance-agent.md` | index、overview、personal-index、ログ、学習ルールを定期保守する |

追加の補助入口として、`skills/batch-inbox.md` と `skills/web-search.md` がある。

| 入口 | ファイル | 用途 |
|---|---|---|
| フォルダ一括wiki化 | `skills/batch-inbox.md` | `00personal/` の指定フォルダから未処理・更新・部分失敗ファイルだけを wiki 化する |
| Web検索wiki化 | `skills/web-search.md` | `search-topics.yaml` に基づいてWeb記事を取得し、wiki記事を生成する |

---

## Codexでの基本運用

Codexでは、ユーザーの依頼内容に応じて次のように使い分ける。

| ユーザー依頼 | Codexが使う主な仕様 |
|---|---|
| `_inbox` のファイルを処理して | `inbox-agent.md` |
| 指定フォルダを wiki バッチ処理して | `batch-inbox.md` |
| 週次メンテナンスして | `maintenance-agent.md` の週次タスク |
| 月次メンテナンスして | `maintenance-agent.md` の月次タスク |
| 分類ミスを記録して | `record-feedback.md` |
| フィードバックから分類ルールを作って | `learn-from-feedback.md` |
| Web検索で情報を追加して | `web-search.md` |

分類不明、低信頼度、削除済みソースファイルの扱いなど、仕様上ユーザー確認が必要な場面では、Codexは処理を止めて確認する。

---

## inbox処理フロー

`inbox-agent.md` は、`KnowledgeBase/_inbox/` 直下のファイルを更新日時の古い順に処理する。

1. `convert-binary.md`
   - PDF、PPTX、XLSX、DOCX、音声、動画、EML、ZIP、URLリストをテキスト化する。
   - 画像はマルチモーダル解析へ委譲する。

2. `analyze.md`
   - `SCHEMA.md` と `classification-hints.md` を参照して分類先を判定する。
   - `classification-hints`、LLMスコアリング、既存wiki類似検索の順で判断する。
   - 信頼度が低い場合はユーザーに確認する。

3. `record-feedback.md`
   - ユーザーが分類先を修正した場合のみ実行する。
   - `feedback-log.md` に判断差分を記録する。

4. `write-wiki.md`
   - 分類結果と変換テキストから Front-matter 付き Markdown を生成する。
   - `wiki_type` ごとのテンプレートを使う。

5. `place-wiki.md`
   - 後処理の中心となるスキル。
   - `_overview.md` 作成、`change_log` 追記、`processed-sources.yaml` 記録、`index-builder`、`route-binary` を連鎖実行する。

6. `route-binary.md`
   - `_inbox/` の元ファイルを `00personal/` へ移動する。
   - 移動先が判断できない場合はユーザー確認し、必要に応じて学習ログに記録する。

---

## batch-inboxフロー

`batch-inbox.md` は、`00personal/` に既に存在する資料を後追いで wiki 化するための入口である。

1. 指定フォルダを走査する。
2. 必要に応じて `wiki_filter` で wiki 化価値を事前判定する。
3. `processed-sources.yaml` と照合し、未処理・内容更新・部分失敗のみ対象にする。
4. 対象ファイルを `_inbox/` にコピーする。
5. `convert-binary → analyze → write-wiki → place-wiki` を直列実行する。
6. `skip_route_binary: true` として `route-binary.md` をスキップする。
7. `_inbox/` のコピーを削除する。

通常の `inbox-agent` と異なり、元ファイルは `00personal/` に残る。

---

## maintenanceフロー

`maintenance-agent.md` は、週次タスクと月次タスクを順番に実行する。

### 週次タスク

| 順序 | スキル | 役割 |
|---:|---|---|
| 1 | `index-builder.md` | `wiki-embeddings.npz` を全件再構築する |
| 2 | `update-overview.md` | 全 `_overview.md` を更新する |
| 3 | `sync-personal.md` | `00personal/` の実フォルダと `personal-index.yaml` を同期する |
| 4 | `sync-wiki.md` | KnowledgeBaseに直接追加された未登録wikiを検出し、indexとoverviewに反映する |
| 5 | `check-integrity.md` | Front-matter欠落、index未登録、空ファイル、削除済みソースを確認する |

### 月次タスク

| 順序 | スキル | 役割 |
|---:|---|---|
| 1 | `update-changelog.md` | 3ヶ月超の月次ログを年次サマリーへ圧縮し、archiveへ移動する |
| 2 | `learn-from-feedback.md` | `feedback-log.md` から3回以上の分類修正パターンを抽出し、承認後に `classification-hints.md` へ追記する |

---

## Web検索フロー

`web-search.md` は `search-topics.yaml` の頻度設定に従って検索対象を選び、Web記事を wiki 化する。

1. `search-topics.yaml` から実行対象トピックを選ぶ。
2. Web検索で上位URLを取得する。
3. ページ本文を取得する。
4. `wiki-embeddings.npz` を使って重複チェックする。
5. `write-wiki.md` と `place-wiki.md` で wiki 化する。
6. `last_searched` を更新する。

競合検索モードでは、競合リストから会社名を抽出し、会社ごとに複数テンプレートで検索する。

---

## 共有データストア

Codex運用で特に重要な共有ファイルは以下。

| ファイル | 主な更新元 | 用途 |
|---|---|---|
| `KnowledgeBase/_system/wiki-embeddings.npz` | `index-builder.md` | 分類補助、重複チェック用のベクトルindex |
| `KnowledgeBase/_system/processed-sources.yaml` | `place-wiki.md`, `route-binary.md`, `batch-inbox.md`, `check-integrity.md` | 元ファイルとwikiの対応、処理状態、削除検出 |
| `KnowledgeBase/_system/personal/personal-index.yaml` | `route-binary.md`, `sync-personal.md` | `00personal/` の保管先索引 |
| `KnowledgeBase/_system/change_log_YYYY-MM.md` | `place-wiki.md` | wiki追加・新規フォルダ作成などの月次詳細ログ |
| `KnowledgeBase/_system/learning/feedback-log.md` | `record-feedback.md`, `learn-from-feedback.md` | ユーザー修正履歴 |
| `KnowledgeBase/_system/learning/classification-hints.md` | `learn-from-feedback.md` | 分類補足ルール |
| 各フォルダの `_overview.md` | `place-wiki.md`, `update-overview.md`, `sync-wiki.md` | フォルダ概要と配下ファイル一覧 |

---

## Codex並行運用時の注意点

複数の Codex セッションや別エージェントを同時に動かす場合、以下のファイルは書き込み競合が起きやすい。

- `wiki-embeddings.npz`
- `processed-sources.yaml`
- `personal-index.yaml`
- `change_log_YYYY-MM.md`
- `feedback-log.md`
- `classification-hints.md`
- `_overview.md`

安全な運用ルールは次の通り。

1. `inbox-agent` と `maintenance-agent` は同時実行しない。
2. `batch-inbox` と `inbox-agent` は同時実行しない。
3. `index-builder.md` の `rebuild` 実行中は、`place-wiki.md` による `add` を走らせない。
4. `learn-from-feedback.md` 実行中は、分類修正ログの追記を避ける。
5. OneDrive同期中に書き込み失敗が出た場合は、すぐ再実行せず同期完了を待つ。
6. 削除済みソースファイルの扱いは必ずユーザー確認を挟む。

---

## 仕様上の確認ポイント

現状仕様には、Codex運用前に揃えておくとよい点がある。

| 項目 | 確認内容 |
|---|---|
| `frontmatter.md` | `CLAUDE.md` には記載があるが、実ファイルは存在しない。現在は `check-integrity.md` / `sync-wiki.md` が補完している |
| `consistency-checker.md` | `CLAUDE.md` には記載があるが、実ファイルは `check-integrity.md` として存在する |
| `log-writer.md` | `CLAUDE.md` には記載があるが、実処理は `place-wiki.md` の change_log 追記に統合されている |
| `web-search.md` | `ARCHITECTURE.md` では maintenance 連携だが、`maintenance-agent.md` のタスク一覧には未記載 |
| 削除・上書き確認 | 共通AGENTSでは確認必須だが、wiki-agent仕様では一部自動実行になっているため、実運用ルールを明文化する必要がある |

---

## 推奨実行単位

Codexで実行する場合は、次の単位で分けると安全である。

| 実行単位 | 推奨タイミング | 理由 |
|---|---|---|
| `_inbox` 処理 | 手動投入直後 | 対象が明確で、処理結果を確認しやすい |
| フォルダバッチ処理 | 初回移行・大きな資料整理時 | `processed-sources.yaml` で重複を避けられる |
| 週次メンテナンス | inbox / batch が終わった後 | indexとoverviewを安定状態に戻す |
| 月次メンテナンス | 月初または週次後 | ログ圧縮と分類学習をまとめて実施できる |
| Web検索 | 手動または単独実行 | 外部情報取得と wiki 追加が発生するため、他処理と分ける |

