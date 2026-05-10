# wiki-agent Codex運用アーキテクチャ

## 目的

この文書は、`wiki-agent` を Codex で運用する際の現行アーキテクチャ、主入口、Gemini 生成フロー、保守タスク、並行運用時の注意点をまとめる。

現行の正本フローは `skills/batch-inbox.md` である。`agents/inbox-agent.md` は旧 `_inbox` 入口として残すが、整理予定とする。

---

## 全体像

`wiki-agent` は、`00personal/` に蓄積された資料を `KnowledgeBase/` に wiki 化し、検索しやすい状態を維持する仕組みである。

主な入口は次の3つ。

| 入口 | ファイル | 用途 |
|---|---|---|
| フォルダ一括wiki化 | `skills/batch-inbox.md` | 現行の主入口。指定フォルダから未処理・更新・部分失敗ファイルだけを wiki 化する |
| Web検索wiki化 | `skills/web-search.md` | `search-topics.yaml` に基づいてWeb記事を取得し、wiki化する |
| メンテナンス | `agents/maintenance-agent.md` | index、overview、personal-index、ログ、学習ルールを定期保守する |

旧入口として `agents/inbox-agent.md` がある。これは `KnowledgeBase/_inbox/` 直下のファイルを処理する設計だが、現行の主入口ではない。削除または薄い互換ラッパー化を検討する整理予定ファイルとして扱う。

---

## Codexでの基本運用

| ユーザー依頼 | Codexが使う主な仕様 |
|---|---|
| 指定フォルダを wiki 化して | `batch-inbox.md` |
| `_inbox` 相当の一時処理をしたい | 原則 `batch-inbox.md`。`inbox-agent.md` は旧入口として参照のみ |
| Web検索で情報を追加して | `web-search.md` |
| 週次メンテナンスして | `maintenance-agent.md` の週次タスク |
| 月次メンテナンスして | `maintenance-agent.md` の月次タスク |
| 分類ミスを記録して | `record-feedback.md` |
| フィードバックから分類ルールを作って | `learn-from-feedback.md` |

分類不明、削除済みソースファイル、ファイル削除、プログラム実行、外部コマンド実行など、AGENTS.md または各仕様上ユーザー確認が必要な場面では、Codexは処理を止めて確認する。

---

## batch-inboxフロー

`batch-inbox.md` は、`00personal/` に既に存在する資料を後追いで wiki 化する現行の正本入口である。

1. 指定フォルダを走査する。
2. OneDrive クラウド専用ファイルを検出する。
3. クラウド専用ファイルはファイル名・パスで事前判定し、対象のみローカル化する。
4. 必要に応じて `wiki_filter` で wiki 化価値を事前判定する。
5. `processed-sources.yaml` と照合し、未処理・内容更新・部分失敗のみ対象にする。
6. 削除済みソースファイルを検出した場合は、処理開始前にユーザー確認する。
7. 処理予定を提示し、ユーザー確認後に実行する。
8. 対象ファイルを `KnowledgeBase/_inbox/` に一時コピーする。
9. `convert-binary → analyze → write-wiki → place-wiki` を直列実行する。
10. `skip_route_binary: true` として `route-binary.md` をスキップする。
11. `_inbox/` の一時コピーを削除する。
12. `update-overview`、`change_log`、`index-builder`、`processed-sources.yaml` の重い後処理を一括 flush する。

通常の元ファイルは `00personal/` に残る。`_inbox/` に置かれるファイルは処理用コピーである。

---

## Gemini 分類・生成フロー

分類とwiki本文生成の標準は `scripts/gemini_wiki_generator.py` を利用する Gemini モードである。
Codex/Claude側のコストを抑えるため、通常バッチでは `analyze.md` に分類・本文生成をさせない。

呼び出し関係は次の通り。

```
batch-inbox.md
  └─ run_inbox_pipeline(...)
      ├─ convert-binary.md
      ├─ gemini_wiki_generator.py <source_file_abs_path> --analyze-only --emit-usage
      ├─ gemini_wiki_generator.py <source_file_abs_path> --generate --analysis-json ... --emit-usage
      └─ place-wiki.md
```

`gemini_wiki_generator.py` の役割:

- Excel / PPTX / PDF の内容を抽出する
- `--analyze-only` で `SCHEMA.md` と `classification-hints.md` を参照し、分類結果JSONを出力する
- `--generate` で分類結果JSONを受け取り、wiki本文Markdownを出力する
- `--emit-usage` で Gemini 側の token usage、入出力文字数、モデル名、モードを記録する
- Front-matter、保存先、配置後処理は `place-wiki.md` 側が担当する

Gemini分類が失敗した場合、分類結果が低信頼度の場合、重要資料で分類精度を優先する場合は、`analyze.md` をフォールバックとして使う。
`write-wiki.md` は旧/互換用として残すが、通常の `batch-inbox.md` 正本経路では使わない。

---

## コアパイプライン

| 順序 | スキル | 役割 |
|---:|---|---|
| 1 | `convert-binary.md` | PDF、PPTX、XLSX、DOCX、音声、動画、ZIP、URLリストをテキスト化する |
| 2 | `gemini_wiki_generator.py --analyze-only` | `SCHEMA.md`、`classification-hints.md` を参照して分類結果JSONを返す |
| 3 | `gemini_wiki_generator.py --generate` | 分類結果JSONを受け取り、wiki本文Markdownを生成する |
| 4 | `place-wiki.md` | 配置後処理、`processed-sources.yaml` 記録、一括後処理用バッファ作成を行う |

`batch-inbox.md` から呼び出す場合は `batch_mode: true` を使い、`_overview.md` 更新、`change_log` 追記、`index-builder` 更新などを一括化する。

`analyze.md` はフォールバック分類用に残す。旧 `batch_write_wiki=True` 経路は、`write-wiki.md` を飛ばす代わりに `analyze.md` が本文生成まで担うため、Codex/Claude側コストが残る。

---

## Web検索フロー

`web-search.md` は `inbox-agent.md` を経由しない。Web検索結果を取得し、`write-wiki.md` と `place-wiki.md` を直接使って wiki 化する。

1. `search-topics.yaml` から実行対象トピックを選ぶ。
2. Web検索で上位URLを取得する。
3. ページ本文を取得する。
4. `wiki-embeddings.npz` を使って重複チェックする。
5. `write-wiki.md` と `place-wiki.md` で wiki 化する。
6. `last_searched` を更新する。

競合検索モードでは、競合リストから会社名を抽出し、会社ごとに複数テンプレートで検索する。

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

## 共有データストア

| ファイル | 主な更新元 | 用途 |
|---|---|---|
| `KnowledgeBase/_system/wiki-embeddings.npz` | `index-builder.md` | 分類補助、重複チェック用のベクトルindex |
| `KnowledgeBase/_system/processed-sources.yaml` | `batch-inbox.md`, `place-wiki.md`, `route-binary.md`, `check-integrity.md` | 元ファイルとwikiの対応、処理状態、削除検出 |
| `KnowledgeBase/_system/personal/personal-index.yaml` | `route-binary.md`, `sync-personal.md` | `00personal/` の保管先索引 |
| `KnowledgeBase/_system/change_log_YYYY-MM.md` | `place-wiki.md`, `batch-inbox.md`, `update-changelog.md` | wiki追加・新規フォルダ作成などの月次詳細ログ |
| `KnowledgeBase/_system/learning/feedback-log.md` | `record-feedback.md`, `learn-from-feedback.md` | ユーザー修正履歴 |
| `KnowledgeBase/_system/learning/classification-hints.md` | `learn-from-feedback.md` | 分類補足ルール |
| `KnowledgeBase/_system/search-topics.yaml` | `web-search.md` | Web検索トピック定義 |
| 各フォルダの `_overview.md` | `place-wiki.md`, `batch-inbox.md`, `update-overview.md`, `sync-wiki.md` | フォルダ概要と配下ファイル一覧 |

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

1. `batch-inbox.md` と `maintenance-agent.md` は同時実行しない。
2. 複数の `batch-inbox.md` を同時実行しない。
3. `index-builder.md` の `rebuild` 実行中は、`place-wiki.md` による `add` を走らせない。
4. `learn-from-feedback.md` 実行中は、分類修正ログの追記を避ける。
5. OneDrive同期中に書き込み失敗が出た場合は、すぐ再実行せず同期完了を待つ。
6. 削除済みソースファイルの扱いは必ずユーザー確認を挟む。

---

## 整理予定

| 項目 | 方針 |
|---|---|
| `agents/inbox-agent.md` | 旧 `_inbox` 入口。現行主入口ではない。削除または薄い互換ラッパー化を検討する |
| `docs/ARCHITECTURE.md` / 図版 | 旧 `inbox-agent` 中心の図が残っているため、最終整理時に更新する |
| `docs/architecture-gemini.md` / 図版 | Gemini統合の説明として有用だが、主入口を `batch-inbox.md` に合わせて更新する |
| `processed-sources.yaml` 形式 | `batch-inbox.md` / `place-wiki.md` / `gemini_wiki_generator.py` の更新形式を統一する |

---

## 推奨実行単位

| 実行単位 | 推奨タイミング | 理由 |
|---|---|---|
| フォルダバッチ処理 | 初回移行・大きな資料整理時・日常の資料追加後 | `processed-sources.yaml` で重複を避けられる |
| Web検索 | 手動または単独実行 | 外部情報取得と wiki 追加が発生するため、他処理と分ける |
| 週次メンテナンス | batch / web-search が終わった後 | indexとoverviewを安定状態に戻す |
| 月次メンテナンス | 月初または週次後 | ログ圧縮と分類学習をまとめて実施できる |
