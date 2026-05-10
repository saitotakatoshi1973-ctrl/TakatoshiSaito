# Wiki Agent アーキテクチャ（Gemini統合版）

作成日: 2026-05-10

---

## 1. 全体相関図

```
╔══════════════════════════════════════════════════════════════════════╗
║                    Claude Code（ユーザーとの対話）                    ║
╚══════════════════════════════════════════════════════════════════════╝
         │ スキル呼び出し（Skill ツール）
         ▼
╔══════════════════════════════════════════════════════════════════════╗
║                         スキル（.md）                                 ║
║                                                                      ║
║  【ユーザー向けスキル】           【インフラスキル】                   ║
║  ┌─────────────────┐            ┌──────────────────────┐            ║
║  │ wiki-inbox      │            │ convert-binary.md    │            ║
║  │ wiki-batch      │            │ analyze.md           │            ║
║  └────────┬────────┘            │ write-wiki.md        │            ║
║           │ 呼び出し            │ place-wiki.md        │            ║
║           ▼                     │ update-overview.md   │            ║
║  ┌─────────────────┐            │ update-changelog.md  │            ║
║  │ inbox-agent.md  │──呼び出し→ │ index-builder.md     │            ║
║  │ (エージェント)  │            │ route-binary.md      │            ║
║  └─────────────────┘            │ record-feedback.md   │            ║
║                                 └──────────────────────┘            ║
╚══════════════════════════════════════════════════════════════════════╝
         │ Bash ツールで起動
         ▼
╔══════════════════════════════════════════════════════════════════════╗
║                       Python スクリプト                               ║
║                                                                      ║
║  【既存】                          【今回追加】                        ║
║  mcp-servers/                      wiki-agent/scripts/               ║
║  ├ cybermail-imap/                  └ gemini_wiki_generator.py ★NEW  ║
║  │  ├ server.py  (MCPサーバー)                                        ║
║  │  └ sync.py    (メール同期)                                         ║
║  └ skills/important-mail/                                            ║
║     └ export_important_mail_top50.py                                 ║
║                                                                      ║
║  kyorindo-cx/                                                        ║
║  └ generate_dx_benchmark.py                                          ║
╚══════════════════════════════════════════════════════════════════════╝
         │ API呼び出し
         ▼
╔══════════════════════════════════════════════════════════════════════╗
║                         外部API / LLM                                ║
║                                                                      ║
║   Claude API          Gemini API（★今回追加）    Cybermail IMAP      ║
║   （Claude Code本体）  gemini-2.5-flash          （メール取得）       ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 2. gemini_wiki_generator と既存スクリプトの関係

```
                    ┌───────────────────────────────────────┐
                    │         wiki生成フロー 比較             │
                    └───────────────────────────────────────┘

【現在：Claude主体】                  【Gemini版：Python主体】

  wiki-batch スキル                     wiki-batch スキル（将来改修）
       │                                         │
       │ Claude自身が処理                         │ Python呼び出し
       ▼                                         ▼
  convert-binary.md               gemini_wiki_generator.py
  （Claude がファイル読み取り）    │
       │                          ├─ openpyxl   → Excel読み取り ✅
       │ Excel/PPTX：読めない      ├─ python-pptx → PPTX読み取り ✅
       │ PDF：一部読める           ├─ pymupdf    → PDF読み取り  ✅
       ▼                          │
  analyze.md                      ▼
  （Claude がLLM分析）            Gemini 2.5 Flash API
       │                          （wiki Markdown生成）
       ▼                                         │
  write-wiki.md                                  ▼
  （Claude がwiki生成）             KnowledgeBase/ に保存
       │                                         │
       ▼                                         ▼
  place-wiki.md                    processed-sources.yaml 更新
  （後処理一式）


【スクリプト比較】

  スクリプト                         役割                  LLM使用
  ─────────────────────────────────────────────────────────────────
  server.py                          メールMCPサーバー      なし
  sync.py                            メール同期処理         なし
  export_important_mail_top50.py     メール抽出レポート     なし
  generate_dx_benchmark.py           DXベンチマーク生成     なし
  gemini_wiki_generator.py ★        Excel/PPTX/PDF→wiki   Gemini 2.5 Flash
```

---

## 3. 現状の位置づけと将来計画

```
  gemini_wiki_generator.py
         │
         ├─ 【現在】スタンドアロン（1ファイルずつ処理）
         │         コマンド: python gemini_wiki_generator.py <file> --dest <path>
         │         Claude Code から手動呼び出し
         │
         └─ 【将来】wiki-batch スキルに統合
                   フォルダ指定 → 自動バッチ処理
                   Claude は管理のみ / 生成は Gemini が担当


  【将来の統合フロー】

  wiki-batch スキル（改修版）
       │
       ├─ フォルダスキャン（Claude）
       ├─ processed-sources.yaml 照合（Claude）
       ├─ 処理対象ファイルを特定（Claude）
       │
       │  ↓ 各ファイルに対して
       ▼
  gemini_wiki_generator.py（バッチ版）
       ├─ テキスト抽出（openpyxl / python-pptx / pymupdf）
       ├─ Gemini API でwiki生成
       ├─ KnowledgeBase/ に保存
       └─ YAML更新
       │
       ▼
  Claude（後処理）
       ├─ _overview.md 更新
       └─ change_log 記録


  【コスト比較】

  処理方式                           推定コスト（100件）
  ─────────────────────────────────────────────────────
  Claude Sonnet（現在）             $1.00 〜 $3.00
  Claude Haiku + Batch API          $0.15 〜 $0.50
  Gemini 2.5 Flash（将来）          $0.05 〜 $0.20
```

---

## 4. ファイル構成

```
ClaudeCodeFolder/
├── wiki-agent/
│   ├── agents/
│   │   ├── inbox-agent.md          # 受信トレイ処理エージェント
│   │   └── maintenance-agent.md    # メンテナンスエージェント
│   ├── skills/
│   │   ├── analyze.md              # 分類・分析
│   │   ├── batch-inbox.md          # バッチ処理
│   │   ├── convert-binary.md       # テキスト抽出
│   │   ├── index-builder.md        # インデックス管理
│   │   ├── place-wiki.md           # wiki配置後処理
│   │   ├── route-binary.md         # バイナリ振り分け
│   │   ├── update-overview.md      # overview更新
│   │   ├── update-changelog.md     # 変更ログ更新
│   │   └── write-wiki.md           # wiki生成
│   ├── scripts/
│   │   ├── gemini_wiki_generator.py ★ NEW（Gemini API wiki生成）
│   │   └── requirements.txt
│   └── docs/                       ← このファイルの場所
│       ├── architecture-gemini.md  # 本ファイル
│       └── architecture-gemini.svg # SVG版
│
├── mcp-servers/
│   ├── cybermail-imap/
│   │   ├── server.py               # MCPサーバー
│   │   └── sync.py                 # メール同期
│   └── skills/important-mail/
│       └── export_important_mail_top50.py
│
└── kyorindo-cx/
    └── generate_dx_benchmark.py
```
