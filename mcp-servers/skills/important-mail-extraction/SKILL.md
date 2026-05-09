---
name: important-mail-extraction
description: Outlookメールから重要メールを抽出し、必要に応じて対象期間内の重要候補すべてをExcelに出力する。sender_rules.xlsx の指定個人アドレス、internal、important_vendor を From/To/Cc に照合して必ず重要扱いし、さらにAIの内容判定で対応必要メールを補完する。重要メール、対応必要メール、Outlookメール整理、sender_rules.xlsx を使うメール判定、3日前から最新までの重要メール確認、重要メール上位50件、重要メールをExcel出力、重要メール全件をExcel、important-mail-extraction を使う依頼のときに使用する。
---

# Important Mail Extraction

## 基本方針

Outlookメールから重要メールを抽出するときは、次の2系統を併用する。

1. `sender_rules.xlsx` 由来の明示ルール
2. AIによる内容ベースの重要判定

明示ルールに一致したメールは、メルマガ、自動通知、広告らしく見えても除外しない。AI判定は、明示ルールに一致しないメールから対応必要そうなものを補完するために使う。

## 参照ファイル

既定の送信者ルール:

`C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder\mcp-servers\cybermail-imap\sender_rules.xlsx`

既定のメールDB:

`C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder\mcp-servers\cybermail-imap\kb\emails.db`

## 発動条件

ユーザー依頼が次のいずれかに該当するときは、このスキルを使う。

- 重要メール、対応必要メール、要確認メール、Outlookメール整理を依頼されたとき
- `sender_rules.xlsx` を使ったメール判定、社内・重要ベンダー・指定個人アドレスの抽出を依頼されたとき
- 「3日前から最新まで」「昨日から最新まで」など、期間指定つきで重要メール確認を依頼されたとき
- 「重要メール上位50件」「上位50件をExcel」「Excelに出力」「重要メール一覧をxlsx」「重要候補すべてをExcel」「全件出力」など、抽出結果のExcel化を依頼されたとき
- ユーザーが `important-mail-extraction` スキル名を明示したとき

## sender_rules 判定

`sender_rules.xlsx` から、次に該当するルールを重要扱いする。

- 指定個人アドレスとして定義されているもの
- `sender_type` が `internal` のもの
- `sender_type` が `important_vendor` のもの

照合対象フィールド:

- `From`
- `To`
- `Cc`

メールDBに `cc_addr` がない場合は、保存済み本文やヘッダ相当テキストにCc情報が含まれるか確認する。確認できない場合は、`From` と `To` で判定し、出力に「CcはDB上で確認不可」と明記する。

## AI自動重要判定

sender_rules に一致しないメールも、件名・本文・差出人・宛先・文脈から重要そうなものを抽出する。

重視する語や文脈:

- 依頼、確認、対応、相談、期限、承認、回答、返信
- 障害、エラー、不具合、復旧
- 請求、支払、契約、見積
- 会議、資料送付、日程調整
- 案件進行、外部ベンダー、社内関係者からの依頼
- 宿題、期日、締切、情報セキュリティ、体制図、運用開始、部内へ共有、準備完了
- 精算、取り消し、取消、精算戻し、機能確認
- `5/14`、`5月14日`、`2026-05-14` など、期日・期限文脈にある明確な日付

除外方針:

- メルマガ、広告、自動通知は原則除外する
- ただし sender_rules の指定個人アドレス、`internal`、`important_vendor` に一致するものは除外しない
- 障害通知やメンテナンス通知は、影響確認や社内共有が必要そうなら含める

## 分類

抽出したメールには、次の分類のいずれかを付ける。

- `対応必要`
- `重要情報`
- `関係先フォロー`
- `社内重要`
- `重要ベンダー`
- `障害・メンテ`
- `請求・契約`
- `参考`

## 出力形式

一覧には最低限、次を含める。

- 日時
- From
- To/Cc の重要一致
- 件名
- 分類
- 抽出理由: `sender_rules` / `AI判定` / `複合`
- 重要理由
- 推奨アクション

最後に、検索対象期間、参照したDBまたはデータ元、Cc判定の可否、除外した主なカテゴリを簡潔に補足する。

## Excel出力

ユーザーがExcel出力を依頼した場合は、対象期間内の重要候補すべてを重要度順で `.xlsx` に保存する。ユーザーが上位件数を明示した場合だけ、`--limit` で件数を絞る。

既定の出力先:

`C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder\mcp-servers\cybermail-imap\outputs\important_mail_all_YYYYMMDD_HHMMSS.xlsx`

Excel列:

- `rank`
- `score`
- `date`
- `from_addr`
- `to_addr`
- `to_cc_important_match`
- `subject`
- `classification`
- `extraction_reason`
- `important_reason`
- `recommended_action`
- `body_preview`
- `email_id`

推奨スクリプト:

`scripts/export_important_mail_top50.py`

実行例:

```powershell
$env:PYTHONIOENCODING='utf-8'; python .\skills\important-mail-extraction\scripts\export_important_mail_top50.py --since 2026-05-06
```

期間が相対指定の場合は、現在日付を基準に絶対日付へ直して `--since` に渡す。上位50件だけが必要なときは `--limit 50` を追加する。出力ファイルのパス、対象件数、候補件数、出力件数をユーザーへ報告する。

## 実行時の注意

作業前にユーザーへ対象期間を確認する。期間が相対指定の場合は、現在日付を基準に絶対日付へ直して扱う。

このユーザー環境では、ファイル確認、プログラム実行、外部コマンド実行の前に作業計画を提示し、`y/n` 確認を取る。承認後も、別アプローチが必要になった場合は再度確認する。
