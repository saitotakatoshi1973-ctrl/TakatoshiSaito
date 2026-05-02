const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat
} = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const headerBorder = { style: BorderStyle.SINGLE, size: 1, color: "4472C4" };
const headerBorders = { top: headerBorder, bottom: headerBorder, left: headerBorder, right: headerBorder };

// テーブル共通設定
function makeHeaderRow(cells, widths) {
  return new TableRow({
    tableHeader: true,
    children: cells.map((text, i) =>
      new TableCell({
        borders: headerBorders,
        width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: "4472C4", type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })]
        })]
      })
    )
  });
}

function makeDataRow(cells, widths, shade) {
  return new TableRow({
    children: cells.map((text, i) =>
      new TableCell({
        borders,
        width: { size: widths[i], type: WidthType.DXA },
        shading: shade ? { fill: "EEF2FA", type: ShadingType.CLEAR } : { fill: "FFFFFF", type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text, font: "Arial", size: 20 })]
        })]
      })
    )
  });
}

// 仕切り線
function divider() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } },
    spacing: { before: 100, after: 100 },
    children: []
  });
}

// セクションタイトル
function sectionTitle(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: "2E4A87" })]
  });
}

// サブ見出し
function subHeading(text) {
  return new Paragraph({
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: "1F3A6B" })]
  });
}

// 箇条書き
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 20 })]
  });
}

// 通常テキスト
function para(text, bold = false) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, font: "Arial", size: 20, bold })]
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 600, hanging: 300 } } }
        }]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: "1F3A6B" },
        paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E4A87" },
        paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 }
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1200, right: 1200, bottom: 1200, left: 1200 }
      }
    },
    children: [
      // タイトル
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200, after: 80 },
        children: [new TextRun({ text: "杏林堂 AI-Ready化に向けたCX推進部 検討会議", font: "Arial", size: 40, bold: true, color: "1F3A6B" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "4472C4", space: 4 } },
        spacing: { before: 0, after: 200 },
        children: [new TextRun({ text: "ミーティングアジェンダ", font: "Arial", size: 26, color: "4472C4" })]
      }),

      // 会議情報テーブル
      new Table({
        width: { size: 9506, type: WidthType.DXA },
        columnWidths: [2000, 7506],
        rows: [
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 2000, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "日時", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders, width: { size: 7506, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "2026年4月（日程調整中）", font: "Arial", size: 20 })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 2000, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "場所", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders, width: { size: 7506, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "TBD", font: "Arial", size: 20 })] })] })
          ]}),
          new TableRow({ children: [
            new TableCell({ borders, width: { size: 2000, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "参加者", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders, width: { size: 7506, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "CX推進部（横井・鈴木孝・足立・石川・齋藤・鈴木佑）", font: "Arial", size: 20 })] })] })
          ]})
        ]
      }),

      new Paragraph({ spacing: { before: 200, after: 0 }, children: [] }),

      // 0. オープニング
      sectionTitle("0. オープニング（5分）"),
      bullet("会議の目的・ゴール確認"),
      bullet("「AI-Ready」の定義確認（何ができる状態を目指すか）"),

      divider(),

      // 1. 現状確認
      sectionTitle("1. 現状確認：AIに関連する進行中タスクの整理（20分）"),

      new Table({
        width: { size: 9506, type: WidthType.DXA },
        columnWidths: [3400, 2006, 4100],
        rows: [
          makeHeaderRow(["タスク", "担当", "現状"], [3400, 2006, 4100]),
          makeDataRow(["#5 議事録自動化AIエージェント（JAPAN AI）", "横井/鈴木孝/足立", "トライアル契約完了・4/7説明会"], [3400, 2006, 4100], false),
          makeDataRow(["#6 資料作成AIエージェント（NotebookLM）", "横井/鈴木孝/足立", "8アカウント導入完了"], [3400, 2006, 4100], true),
          makeDataRow(["#8 ツルハAIチャットボット", "足立/鈴木孝", "杏林堂9月リリース目標"], [3400, 2006, 4100], false),
          makeDataRow(["#30 AI使用ガイドライン作成", "鈴木孝/石川", "ガートナーとの壁打ち予定"], [3400, 2006, 4100], true),
          makeDataRow(["#33 AI-OCR", "鈴木孝/足立", "5月再打合わせ予定"], [3400, 2006, 4100], false),
          makeDataRow(["#40 AIエージェント開発環境構築", "CX推進部", "未着手"], [3400, 2006, 4100], true),
        ]
      }),

      divider(),

      // 2. ギャップ分析
      sectionTitle("2. AI-Ready化のギャップ分析（30分）"),
      para("AI-Readyになるために必要な4領域を議論："),

      subHeading("① データ基盤"),
      bullet("KOGOROデータの活用可能状態の確認"),
      bullet("MDM（商品・棚・店舗・従業員）整備の優先順位"),
      bullet("AIが参照できるデータの粒度・鮮度の現状"),

      subHeading("② AIツール・環境"),
      bullet("JAPAN AI / Claude Code / NotebookLM の役割整理"),
      bullet("AIエージェント開発環境（#40）の5レイヤー構想の具体化"),

      subHeading("③ ガバナンス・ルール"),
      bullet("AI使用ガイドライン（#30）の策定スケジュール"),
      bullet("セキュリティ・個人情報保護の観点（IT-BCP連携）"),

      subHeading("④ 人材・組織"),
      bullet("CX推進部メンバーのAIリテラシー現状確認"),
      bullet("AIを使った内製開発ができる体制の検討"),

      divider(),

      // 3. 優先ユースケース
      sectionTitle("3. 優先ユースケースの特定（25分）"),
      para("既存課題とAIの掛け合わせで、今期着手すべきユースケースを議論："),

      new Table({
        width: { size: 9506, type: WidthType.DXA },
        columnWidths: [1400, 4406, 3700],
        rows: [
          makeHeaderRow(["優先度", "ユースケース", "対応課題"], [1400, 4406, 3700]),
          makeDataRow(["高", "マニュアルQ&A（チャットボット）", "マニュアル分散管理"], [1400, 4406, 3700], false),
          makeDataRow(["高", "SV業務記録のAI支援", "SV業務の未記録"], [1400, 4406, 3700], true),
          makeDataRow(["中", "欠品・発注のAI分析", "属人的な発注/欠品"], [1400, 4406, 3700], false),
          makeDataRow(["中", "チラシ入力のAI-OCR化", "売価調整の手動入力"], [1400, 4406, 3700], true),
          makeDataRow(["参考", "シフト需要予測（DX1.5）", "レイバースケジュール負荷"], [1400, 4406, 3700], false),
        ]
      }),

      divider(),

      // 4. ロードマップ設計
      sectionTitle("4. AI-Ready ロードマップの設計（20分）"),
      para("DX1.0ロードマップの「今期中旬〜AI-Ready」を具体化："),
      bullet("今期前半（〜8月）: データ整備・ガイドライン策定・AIツール評価"),
      bullet("今期中旬（9月〜）: パイロットユースケース実行（チャットボット等）"),
      bullet("今期後半（〜来年2月）: 成果検証・横展開計画策定"),

      divider(),

      // 5. アクションプラン
      sectionTitle("5. アクションプランの確定（10分）"),
      bullet("各タスクのオーナーと期日を決定"),
      bullet("次回会議の日程・確認事項"),

      new Paragraph({ spacing: { before: 240, after: 0 }, children: [] }),

      // フッター的まとめ
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "4472C4", space: 4 } },
        spacing: { before: 120, after: 0 },
        children: [new TextRun({ text: "総所要時間：約110分（2時間弱）", font: "Arial", size: 20, bold: true, color: "2E4A87" })]
      }),
    ]
  }]
});

const outputPath = "C:\\Users\\takatoshi-saito\\OneDrive\\00personal\\ClaudeCodeFolder\\kyorindo-cx\\07_deliverables\\AI_Ready_ミーティングアジェンダ_20260406.docx";

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log("保存完了: " + outputPath);
}).catch(err => {
  console.error("エラー:", err);
  process.exit(1);
});
