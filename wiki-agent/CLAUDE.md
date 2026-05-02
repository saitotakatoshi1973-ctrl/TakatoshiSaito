# wiki-agent CLAUDE.md

## 目的

> LLM検索効率とユーザーの投入手軽さを両立させ、wikiが陳腐化しない仕組みを維持する

---

## スコープ

### 担当範囲
- `KnowledgeBase/` 全体の管理・整合性維持
- `_inbox/` の処理（分析 → wiki生成 → 配置 → 連鎖処理）
- `_inbox/` 処理時に限り `00personal/` へのバイナリファイル振り分けを行う

### 対象外
- `00personal/` の自律的な整理（将来の personal-agent が担当）
- 既存wiki記事の**内容**書き換え（ユーザー承認必須）
- `KnowledgeBase/` 以外のファイルの自律的な操作（inbox処理時の振り分けを除く）

---

## エージェント構成

### inbox-agent
- **責務**: `_inbox/` のファイルを処理。wiki生成 → 配置 → 自動連鎖までを一括実行
- **トリガー**: ユーザー呼び出し（`/wiki-inbox` コマンド または 会話）
- **完了後に自動連鎖**: `frontmatter.md` → `overview-updater.md` → `index-builder.md` → `log-writer.md`

### maintenance-agent
- **責務**: 定期メンテナンス（index.yaml再生成 / 整合性チェック / ログ圧縮）
- **トリガー**: 週次定期実行 ＋ ユーザー呼び出し
- **個別スキルの単体呼び出しも可能**

---

## スキル一覧

| スキル | 責務 | 主な参照ファイル |
|--------|------|----------------|
| `analyze.md` | ファイル分析・分類先判定 | `SCHEMA.md`、`classification-hints.md` |
| `write-wiki.md` | .md 要約wiki生成（他エージェントからも再利用可） | `SCHEMA.md` |
| `place-wiki.md` | .md を KnowledgeBase の正しい場所へ配置・Front-matter付与 | `SCHEMA.md` |
| `route-binary.md` | binary を 00personal/ へ振り分け・索引更新 | `personal-index.yaml`、`personal-rules.md` |
| `frontmatter.md` | Front-matter 検証・欠落時に `status: draft` 自動付与 | `SCHEMA.md` |
| `overview-updater.md` | `_overview.md` 自動生成・更新 | `SCHEMA.md` |
| `index-builder.md` | `index.yaml` 全エントリ集約・再生成 | 全wikiファイルのFront-matter |
| `consistency-checker.md` | リンク切れ・命名規則・status不整合の検出 | `SCHEMA.md`、`index.yaml` |
| `log-writer.md` | change_log 月次ファイル記録・3ヶ月後圧縮 | `change_log_YYYY-MM.md` |

---

## 処理ルール

### inbox処理フロー

```
_inbox/ にファイル投入
    ↓
[analyze.md]
  ├─ ファイル種別・内容・分類先を判定
  └─ 分類不明 → ユーザーに同期質問（自動判断しない）
    ↓
[write-wiki.md]
  └─ 元資料から .md 要約wiki を生成
    ↓
[place-wiki.md]
  └─ .md を KnowledgeBase/ の正しい場所へ移動・Front-matter付与
    ↓
[route-binary.md]  ※ binary ファイルがある場合のみ
  ├─ 00personal/ の正しいフォルダへ移動
  └─ personal-index.yaml・personal-rules.md を更新
    ↓ 自動連鎖
[frontmatter.md]      → Front-matter欠落ファイルに status:draft 自動付与
[overview-updater.md] → 変更のあったサブフォルダの _overview.md を更新
[index-builder.md]    → index.yaml を再生成
[log-writer.md]       → change_log_YYYY-MM.md に1件ずつ記録
```

### 自動実行（承認不要）

- `_inbox/` ファイルの分類・移動
- .md 要約wiki の新規生成
- Front-matter 新規付与・メタデータ（updated等）書き換え
- `_overview.md` 自動生成・更新
- `index.yaml` 再生成
- 既存カテゴリ配下への新サブフォルダ作成
- 重複ファイルの上書き（新しい方を優先）
- `change_log` への記録

### ユーザー承認必須

- 既存wiki記事の**内容**書き換え
- 新トップカテゴリの追加
- 既存カテゴリの廃止・統合
- ファイルの削除

### 分類不明ファイルの扱い

分類先が判断できない場合は、その場でユーザーに質問して待つ（同期）。
推測で移動しない。

### 重複ファイルの扱い

同名ファイルが `_inbox/` に来た場合は新しい方で自動上書き。`change_log` に記録する。

---

## change_log 管理

- **記録粒度**: ファイル1件ずつ詳細記録
- **ファイル分け**: 月次（`change_log_YYYY-MM.md`）
- **インデックス**: `change_log.md`（各月ファイルへのリンクのみ記載）
- **圧縮**: 3ヶ月経過後に月次サマリーへ圧縮

```
_system/
├── change_log.md              # インデックス（月次リンク一覧）
├── change_log_2026-05.md      # 今月：フルログ
├── change_log_2026-04.md      # 先月：フルログ
└── change_log_2026-01.md      # 3ヶ月超：月次サマリーに圧縮済み
```

---

## 自動学習

セッション間のメモリはファイルベースで実現する。

### A. フィードバック記録（`_system/learning/feedback-log.md`）

ユーザーがエージェントの分類を修正したとき、自動で記録する。

```markdown
## YYYY-MM-DD
- ファイル: （ファイル名）
- エージェント判断: （分類先）
- ユーザー修正: （修正後の分類先）
- 理由: （ユーザーのコメントがあれば記載）
```

### C. 分類補足ルール（`_system/learning/classification-hints.md`）

同じパターンのフィードバックが **3回以上** 蓄積したら、`classification-hints.md` への補足ルール追加をユーザーに提案する。
承認後に追記し、安定したら `SCHEMA.md` への正式ルール昇格を提案する。

---

## 参照ファイル一覧

| ファイル | 用途 |
|---------|------|
| `KnowledgeBase/_system/SCHEMA.md` | wiki構造ルール・カテゴリ定義 |
| `KnowledgeBase/_system/personal/personal-index.yaml` | 00personal/ フォルダ索引 |
| `KnowledgeBase/_system/personal/personal-rules.md` | 00personal/ 構成ルール |
| `KnowledgeBase/_system/learning/feedback-log.md` | 分類フィードバック記録 |
| `KnowledgeBase/_system/learning/classification-hints.md` | 分類補足ルール（学習済み） |

---

## バックアップ方針

OneDrive のバージョン履歴に委ねる。エージェントによるバックアップファイル作成は不要。

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-04-30 | 初版作成（STEP 1〜6 の設計をもとに策定） |
