const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak
} = require('docx');
const fs = require('fs');

// --- 共通ユーティリティ ---
const cb = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: cb, bottom: cb, left: cb, right: cb };
const noBorders = {
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE }
};

function hCell(text, width, fill = "2E4A87") {
  return new TableCell({
    borders: { top: { style: BorderStyle.SINGLE, size: 1, color: fill }, bottom: { style: BorderStyle.SINGLE, size: 1, color: fill }, left: { style: BorderStyle.SINGLE, size: 1, color: fill }, right: { style: BorderStyle.SINGLE, size: 1, color: fill } },
    width: { size: width, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Meiryo UI", size: 20 })] })]
  });
}

function dCell(text, width, shade = false, bold = false, italic = false, color = "000000") {
  return new TableCell({
    borders: cellBorders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade ? "F5F5F5" : "FFFFFF", type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, font: "Meiryo UI", size: 20, bold, italic, color })] })]
  });
}

// 入力欄セル（グレー背景・斜体ヒントテキスト）
function inputCell(hint, width, height = 1) {
  const rows = Array.from({ length: height }, () =>
    new Paragraph({ children: [new TextRun({ text: height === 1 ? hint : (height === 1 ? hint : ""), font: "Meiryo UI", size: 20, italic: true, color: "BBBBBB" })] })
  );
  // 空行を追加してスペースを確保
  const children = [new Paragraph({ children: [new TextRun({ text: hint, font: "Meiryo UI", size: 20, italic: true, color: "BBBBBB" })] })];
  for (let i = 1; i < height; i++) {
    children.push(new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] }));
  }
  return new TableCell({
    borders: cellBorders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: "FAFAFA", type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children
  });
}

function sectionTitle(text, color = "2E4A87") {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 80 },
    border: { left: { style: BorderStyle.SINGLE, size: 14, color, space: 4 } },
    children: [new TextRun({ text: "  " + text, font: "Meiryo UI", size: 24, bold: true, color })]
  });
}

function themeBar(text, fill = "2E4A87") {
  return new Paragraph({
    spacing: { before: 200, after: 0 },
    shading: { fill, type: ShadingType.CLEAR },
    children: [new TextRun({ text: "  " + text, font: "Meiryo UI", size: 28, bold: true, color: "FFFFFF" })]
  });
}

function labelRow(label, hint, labelWidth = 2200, inputWidth = 7546) {
  return new TableRow({ children: [
    new TableCell({
      borders: cellBorders, width: { size: labelWidth, type: WidthType.DXA },
      shading: { fill: "EEF2FA", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: label, font: "Meiryo UI", size: 20, bold: true })] })]
    }),
    new TableCell({
      borders: cellBorders, width: { size: inputWidth, type: WidthType.DXA },
      shading: { fill: "FAFAFA", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: hint, font: "Meiryo UI", size: 20, italic: true, color: "BBBBBB" })] })]
    })
  ]});
}

// 議論メモ用ブロック：見出し＋メモ欄テーブル
function discussionBlock(sectionLabel, items, memoLines = 4) {
  const elements = [];
  elements.push(new Paragraph({
    spacing: { before: 160, after: 60 },
    children: [new TextRun({ text: sectionLabel, font: "Meiryo UI", size: 21, bold: true, color: "333333" })]
  }));

  // 議論ポイント（グレーテキスト）
  items.forEach(item => {
    elements.push(new Paragraph({
      numbering: { reference: "bullets", level: 0 },
      spacing: { before: 20, after: 20 },
      children: [new TextRun({ text: item, font: "Meiryo UI", size: 19, color: "666666" })]
    }));
  });

  // メモ欄テーブル
  const memoRows = [];
  for (let i = 0; i < memoLines; i++) {
    memoRows.push(new TableRow({ children: [
      new TableCell({
        borders: cellBorders,
        width: { size: 9746, type: WidthType.DXA },
        shading: { fill: "FAFAFA", type: ShadingType.CLEAR },
        margins: { top: 60, bottom: 60, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: i === 0 ? "📝 " : "", font: "Meiryo UI", size: 20, color: "CCCCCC" })] })]
      })
    ]}));
  }
  elements.push(new Table({ width: { size: 9746, type: WidthType.DXA }, columnWidths: [9746], rows: memoRows }));
  return elements;
}

// 決定事項・アクション欄
function actionTable() {
  return new Table({
    width: { size: 9746, type: WidthType.DXA },
    columnWidths: [4200, 3000, 2546],
    rows: [
      new TableRow({ tableHeader: true, children: [hCell("内容", 4200, "1B6B3A"), hCell("担当者", 3000, "1B6B3A"), hCell("期日", 2546, "1B6B3A")] }),
      ...Array.from({ length: 4 }, (_, i) => new TableRow({ children: [
        new TableCell({ borders: cellBorders, width: { size: 4200, type: WidthType.DXA }, shading: { fill: i % 2 === 0 ? "FFFFFF" : "F5F5F5", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
        new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, shading: { fill: i % 2 === 0 ? "FFFFFF" : "F5F5F5", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
        new TableCell({ borders: cellBorders, width: { size: 2546, type: WidthType.DXA }, shading: { fill: i % 2 === 0 ? "FFFFFF" : "F5F5F5", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
      ]}))
    ]
  });
}

function sp(before = 100) {
  return new Paragraph({ spacing: { before, after: 0 }, children: [] });
}

function divider() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: "DDDDDD", space: 1 } },
    spacing: { before: 60, after: 60 }, children: []
  });
}

// ===== ドキュメント構築 =====
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "・", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 480, hanging: 240 } } } }]
    }]
  },
  styles: {
    default: { document: { run: { font: "Meiryo UI", size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
        run: { size: 36, bold: true, font: "Meiryo UI", color: "1F3A6B" },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
        run: { size: 24, bold: true, font: "Meiryo UI", color: "2E4A87" },
        paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 1 } }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
      }
    },
    children: [

      // ===== タイトル =====
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 100, after: 40 },
        children: [new TextRun({ text: "杏林堂 CX推進部 検討会議", font: "Meiryo UI", size: 24, color: "888888" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "2E4A87", space: 6 } },
        spacing: { before: 0, after: 0 },
        children: [new TextRun({ text: "MTG メモ", font: "Meiryo UI", size: 42, bold: true, color: "1F3A6B" })]
      }),

      sp(160),

      // ===== 会議情報 =====
      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [2200, 7546],
        rows: [
          labelRow("日時", "　　　年　　月　　日（　）　　：　　〜　　：　　"),
          labelRow("場所", ""),
          labelRow("参加者", ""),
          labelRow("記録者", ""),
        ]
      }),

      sp(180),

      // ===== テーマA =====
      themeBar("テーマA：AI-Ready化", "2E4A87"),
      sp(80),

      // A-0
      sectionTitle("A-0. オープニング（5分）"),
      ...discussionBlock("議論ポイント", [
        "「AI-Ready」の定義：何ができる状態を目指すか",
        "今日のゴール確認・ブレストの進め方"
      ], 3),

      sp(80),
      new Paragraph({ spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "▶ 合意した定義・ゴール", font: "Meiryo UI", size: 20, bold: true, color: "2E4A87" })] }),
      new Table({
        width: { size: 9746, type: WidthType.DXA }, columnWidths: [9746],
        rows: Array.from({ length: 2 }, () => new TableRow({ children: [new TableCell({
          borders: cellBorders, width: { size: 9746, type: WidthType.DXA },
          shading: { fill: "EEF6FF", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })]
        })]}))
      }),

      divider(),

      // A-1
      sectionTitle("A-1. 現状確認：AIに関連する進行中タスク（20分）"),
      ...discussionBlock("気になった点・コメント", [
        "#5 議事録自動化AIエージェント（JAPAN AI）",
        "#6 資料作成AIエージェント（NotebookLM）",
        "#8 ツルハAIチャットボット（杏林堂9月リリース目標）",
        "#30 AI使用ガイドライン作成",
        "#33 AI-OCR　　#40 AIエージェント開発環境構築"
      ], 4),

      divider(),

      // A-2
      sectionTitle("A-2. AI-Ready化のギャップ分析（15分）"),
      sp(40),
      new Paragraph({ spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "※ ツルハHD-経営企画部-AI推進Gの動向踏まえて議論", font: "Meiryo UI", size: 19, italic: true, color: "888888" })] }),

      ...discussionBlock("① データ基盤", [
        "KOGORO・かみさんの更新・欠品調査・物流買取DC発注データ：活用可能状態は？",
        "対象データ範囲の検討",
        "AIが参照できるデータの粒度・鮮度"
      ], 3),
      ...discussionBlock("② AIツール・環境", [
        "JAPAN AI / Claude Code / NotebookLM の役割整理",
        "AIエージェント開発環境の具体化"
      ], 3),
      ...discussionBlock("③ ガバナンス・ルール", [
        "AI使用ガイドラインの運用について"
      ], 2),
      ...discussionBlock("④ 人材・組織", [
        "CX推進部メンバーのAIリテラシー現状",
        "内製開発ができる体制の検討"
      ], 2),

      divider(),

      // A-3
      sectionTitle("A-3. ユースケースのブレインストーミング（20分）"),
      sp(40),
      new Paragraph({ spacing: { before: 0, after: 80 }, children: [new TextRun({ text: "以下のユースケース候補を起点に自由にブレスト。優先順位・実現性・担当部署などを書き込む", font: "Meiryo UI", size: 19, italic: true, color: "888888" })] }),

      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [3600, 3046, 3100],
        rows: [
          new TableRow({ tableHeader: true, children: [hCell("ユースケース", 3600), hCell("対応課題", 3046), hCell("コメント・優先度", 3100)] }),
          ...[
            ["マニュアルQ&A（チャットボット）", "マニュアル分散管理"],
            ["議事録エージェント作成", "議事録作成効率化"],
            ["欠品・発注のAI分析", "属人的な発注/欠品"],
            ["チラシ入力のAI-OCR化", "売価調整の手動入力"],
            ["シフト作成エージェント", "レイバースケジュール負荷"],
            ["トレンドサーチ・商品発掘エージェント", "SNSトレンド分析、ECランキング分析"],
            ["売れ筋レコメンドエージェント", "天候・花粉・感染症連動、イベント影響分析"],
            ["価格最適化エージェント", "競合価格、販売弾性"],
            ["商談支援エージェント", "原価分析、取引履歴、価格交渉支援"],
            ["VOC分析エージェント", "クレーム解析、ECレビュー分析"],
            ["AI棚割", "棚割作成効率化、精度向上"],
            ["店舗オペレーション統括エージェント", "作業の自動整理、優先順位付け"],
            ["商品位置検索", "在庫位置、在庫数表示"],
            ["登録販売者研修エージェント", "ツルハ開発中？"],
            ["接客・商品案内エージェント", "商品比較の即答、用途別おすすめ提案"],
            ["（その他）", ""],
          ].map((row, i) => new TableRow({ children: [
            dCell(row[0], 3600, i % 2 === 1),
            dCell(row[1], 3046, i % 2 === 1),
            new TableCell({
              borders: cellBorders, width: { size: 3100, type: WidthType.DXA },
              shading: { fill: "FAFAFA", type: ShadingType.CLEAR },
              margins: { top: 60, bottom: 60, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })]
            })
          ]}))
        ]
      }),

      sp(80),
      new Paragraph({ spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "▶ テーマAの決定事項・次アクション", font: "Meiryo UI", size: 20, bold: true, color: "2E4A87" })] }),
      actionTable(),

      sp(200),

      // ===== ページ区切り =====
      new Paragraph({ children: [new PageBreak()] }),

      // ===== テーマB =====
      themeBar("テーマB：業務改善の進め方（Qasee展開）", "1B6B3A"),
      sp(80),

      // B-1
      sectionTitle("B-1. Qasee現状共有（10分）", "1B6B3A"),
      ...discussionBlock("議論ポイント・気づき", [
        "商品部（主要バイヤー）の可視化結果：どの業務に何時間？",
        "削減可能な業務・属人化している業務はどれか",
        "ヒアリングシートからの発見事項"
      ], 4),

      divider(),

      // B-2
      sectionTitle("B-2. 展開先の検討（20分）", "1B6B3A"),
      sp(40),
      new Paragraph({ spacing: { before: 0, after: 80 }, children: [new TextRun({ text: "各候補の賛否・補足コメントを記入", font: "Meiryo UI", size: 19, italic: true, color: "888888" })] }),

      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [2400, 4346, 3000],
        rows: [
          new TableRow({ tableHeader: true, children: [hCell("展開候補", 2400, "1B6B3A"), hCell("メリット・留意点（参考）", 4346, "1B6B3A"), hCell("議論メモ・優先順位", 3000, "1B6B3A")] }),
          ...[
            ["店舗オペレーション", "スケールメリット大・標準化に直結\n留意：端末ログ取得可否、スマートデバイスとセット"],
            ["商品部 営業事務", "バイヤーと同一部署で展開しやすい\n留意：バイヤー結果との比較分析が可能"],
            ["リベート管理課", "属人化・紙運用が多く改善余地大\n留意：経理・商品部との連携が必要"],
            ["営業推進部", "Qasee×AI-OCR（#33）との連携可能\n留意：業務の複雑性・範囲が広い"],
          ].map((row, i) => new TableRow({ children: [
            dCell(row[0], 2400, i % 2 === 1, true),
            new TableCell({
              borders: cellBorders, width: { size: 4346, type: WidthType.DXA },
              shading: { fill: i % 2 === 1 ? "F5F5F5" : "FFFFFF", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: row[1].split('\n').map((line, j) => new Paragraph({ children: [new TextRun({ text: line, font: "Meiryo UI", size: 18, color: j === 0 ? "333333" : "888888", italic: j === 1 })] }))
            }),
            new TableCell({
              borders: cellBorders, width: { size: 3000, type: WidthType.DXA },
              shading: { fill: "FAFAFA", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })]
            }),
          ]}))
        ]
      }),

      sp(80),
      ...discussionBlock("展開判断の評価軸（議論）", [
        "どのKPIを達成したら展開と判断するか",
        "業務時間削減見込み・ROI・属人化度の測定方法"
      ], 3),

      divider(),

      // B-3
      sectionTitle("B-3. 業務改善のPDCAサイクル設計（15分）", "1B6B3A"),
      ...discussionBlock("議論ポイント", [
        "5ステップ（可視化→分析→改善→効果測定→横展開判断）の運用体制は？",
        "Qasee × AI-Ready・改鮮活動（#36）・業務可視化（#39）との連携方針",
        "サイクルの回転頻度（月次？四半期？）"
      ], 4),

      divider(),

      // B-4
      sectionTitle("B-4. アクション・ロードマップ（暫定版）確認（10分）", "1B6B3A"),
      ...discussionBlock("確認事項", [
        "4/16 商品部振り返りのアウトプット活用方針",
        "次展開先・展開時期の暫定決定",
        "CX推進部内の担当者アサイン"
      ], 3),

      sp(80),
      new Paragraph({ spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "▶ テーマBの決定事項・次アクション", font: "Meiryo UI", size: 20, bold: true, color: "1B6B3A" })] }),
      actionTable(),

      sp(200),

      // ===== まとめ =====
      themeBar("まとめ・アクションプランの確定（5分）", "555555"),
      sp(80),
      new Paragraph({ spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "▶ 全体アクションプラン（テーマA＋B統合）", font: "Meiryo UI", size: 20, bold: true, color: "333333" })] }),

      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [600, 4700, 2646, 1800],
        rows: [
          new TableRow({ tableHeader: true, children: [hCell("#", 600, "555555"), hCell("アクション内容", 4700, "555555"), hCell("担当者", 2646, "555555"), hCell("期日", 1800, "555555")] }),
          ...Array.from({ length: 8 }, (_, i) => new TableRow({ children: [
            dCell(String(i + 1), 600, i % 2 === 1, true),
            new TableCell({ borders: cellBorders, width: { size: 4700, type: WidthType.DXA }, shading: { fill: i % 2 === 1 ? "F5F5F5" : "FFFFFF", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 2646, type: WidthType.DXA }, shading: { fill: i % 2 === 1 ? "F5F5F5" : "FFFFFF", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 1800, type: WidthType.DXA }, shading: { fill: i % 2 === 1 ? "F5F5F5" : "FFFFFF", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "", font: "Meiryo UI", size: 20 })] })] }),
          ]}))
        ]
      }),

      sp(80),
      ...discussionBlock("次回会議", [
        "日程：",
        "確認事項・議題："
      ], 2),

      sp(160),
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
        spacing: { before: 80, after: 0 },
        children: [new TextRun({ text: "記録日：　　　年　　月　　日　　記録者：　　　　　　　　　CX推進部", font: "Meiryo UI", size: 18, color: "888888" })]
      }),
    ]
  }]
});

const outputPath = "C:\\Users\\takatoshi-saito\\OneDrive\\00personal\\ClaudeCodeFolder\\kyorindo-cx\\07_deliverables\\AI_Ready_MTGメモ_20260406.docx";

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log("保存完了: " + outputPath);
}).catch(err => {
  console.error("エラー:", err);
  process.exit(1);
});
