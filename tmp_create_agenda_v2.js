const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak
} = require('docx');
const fs = require('fs');

// --- 共通スタイル ---
const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };

function headerCell(text, width, color = "2E4A87") {
  return new TableCell({
    borders: { top: { style: BorderStyle.SINGLE, size: 1, color }, bottom: { style: BorderStyle.SINGLE, size: 1, color }, left: { style: BorderStyle.SINGLE, size: 1, color }, right: { style: BorderStyle.SINGLE, size: 1, color } },
    width: { size: width, type: WidthType.DXA },
    shading: { fill: color, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })] })]
  });
}

function dataCell(text, width, shade = false, bold = false) {
  return new TableCell({
    borders: cellBorders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade ? "EEF2FA" : "FFFFFF", type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, font: "Arial", size: 20, bold })] })]
  });
}

function makeTable(widths, headerLabels, rows) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headerLabels.map((h, i) => headerCell(h, widths[i])) }),
      ...rows.map((row, ri) => new TableRow({ children: row.map((cell, ci) => dataCell(cell, widths[ci], ri % 2 === 1)) }))
    ]
  });
}

function divider(color = "CCCCCC") {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 3, color, space: 1 } },
    spacing: { before: 80, after: 80 },
    children: []
  });
}

function themeHeader(label, color = "1F3A6B") {
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    shading: { fill: color, type: ShadingType.CLEAR },
    spacing: { before: 200, after: 0 },
    border: { left: { style: BorderStyle.SINGLE, size: 24, color: "F0A500", space: 0 } },
    children: [new TextRun({ text: "  " + label, font: "Arial", size: 30, bold: true, color: "FFFFFF" })]
  });
}

function sectionTitle(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 100 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: "4472C4", space: 4 } },
    children: [new TextRun({ text: "  " + text, font: "Arial", size: 24, bold: true, color: "2E4A87" })]
  });
}

function subHeading(text) {
  return new Paragraph({
    spacing: { before: 160, after: 60 },
    children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: "333333" })]
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 20 })]
  });
}

function para(text, bold = false, color = "000000") {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, font: "Arial", size: 20, bold, color })]
  });
}

function sp(before = 100, after = 0) {
  return new Paragraph({ spacing: { before, after }, children: [] });
}

// --- ドキュメント ---
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 600, hanging: 300 } } }
      }]
    },
    {
      reference: "steps",
      levels: [{
        level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 600, hanging: 300 } } }
      }]
    }]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
        run: { size: 36, bold: true, font: "Arial", color: "1F3A6B" },
        paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
        run: { size: 24, bold: true, font: "Arial", color: "2E4A87" },
        paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 }
      }
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

      // ===== タイトルブロック =====
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 160, after: 60 },
        children: [new TextRun({ text: "杏林堂 CX推進部 検討会議", font: "Arial", size: 28, bold: true, color: "888888" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 60 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "2E4A87", space: 6 } },
        children: [new TextRun({ text: "AI-Ready化 & 業務改善推進　ミーティングアジェンダ", font: "Arial", size: 38, bold: true, color: "1F3A6B" })]
      }),

      sp(120),

      // 会議概要テーブル
      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [1800, 7946],
        rows: [
          new TableRow({ children: [dataCell("日時", 1800, true, true), dataCell("2026年4月（日程調整中）", 7946)] }),
          new TableRow({ children: [dataCell("場所", 1800, false, true), dataCell("TBD", 7946)] }),
          new TableRow({ children: [dataCell("参加者", 1800, true, true), dataCell("CX推進部（横井・鈴木孝・足立・石川・齋藤・鈴木佑）", 7946)] }),
          new TableRow({ children: [dataCell("総所要時間", 1800, false, true), dataCell("約120分（2時間）", 7946)] }),
        ]
      }),

      sp(160),

      // 大テーマ サマリー
      new Paragraph({
        spacing: { before: 0, after: 100 },
        children: [new TextRun({ text: "▌大テーマ", font: "Arial", size: 24, bold: true, color: "1F3A6B" })]
      }),
      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [600, 6746, 2400],
        rows: [
          new TableRow({ tableHeader: true, children: [headerCell("#", 600), headerCell("テーマ", 6746), headerCell("時間", 2400)] }),
          new TableRow({ children: [dataCell("A", 600, false, true), dataCell("AI-Ready化", 6746, false, true), dataCell("約60分", 2400)] }),
          new TableRow({ children: [dataCell("B", 600, true, true), dataCell("業務改善の進め方（Qasee展開）", 6746, true, true), dataCell("約55分", 2400, true)] }),
        ]
      }),

      sp(200),

      // ===== テーマA =====
      themeHeader("テーマA：AI-Ready化（約60分）", "2E4A87"),

      sp(80),

      sectionTitle("A-0. オープニング（5分）"),
      bullet("会議の目的・ゴール確認"),
      bullet("「AI-Ready」の定義確認（何ができる状態を目指すか）"),

      divider(),

      sectionTitle("A-1. 現状確認：AIに関連する進行中タスクの整理（20分）"),
      sp(60),
      makeTable(
        [3400, 1900, 4446],
        ["タスク", "担当", "現状"],
        [
          ["#5 議事録自動化AIエージェント（JAPAN AI）", "横井/鈴木孝/足立", "トライアル契約完了・4/7説明会"],
          ["#6 資料作成AIエージェント（NotebookLM）", "横井/鈴木孝/足立", "8アカウント導入完了"],
          ["#8 ツルハAIチャットボット", "足立/鈴木孝", "杏林堂9月リリース目標"],
          ["#30 AI使用ガイドライン作成", "鈴木孝/石川", "ガートナーとの壁打ち予定"],
          ["#33 AI-OCR", "鈴木孝/足立", "5月再打合わせ予定"],
          ["#40 AIエージェント開発環境構築", "CX推進部", "未着手"],
        ]
      ),

      divider(),

      sectionTitle("A-2. AI-Ready化のギャップ分析（20分）"),
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

      sectionTitle("A-3. 優先ユースケースの特定（15分）"),
      sp(60),
      makeTable(
        [1400, 4446, 3900],
        ["優先度", "ユースケース", "対応課題"],
        [
          ["高", "マニュアルQ&A（チャットボット）", "マニュアル分散管理"],
          ["高", "SV業務記録のAI支援", "SV業務の未記録"],
          ["中", "欠品・発注のAI分析", "属人的な発注/欠品"],
          ["中", "チラシ入力のAI-OCR化", "売価調整の手動入力"],
          ["参考", "シフト需要予測（DX1.5）", "レイバースケジュール負荷"],
        ]
      ),

      sp(200),

      // ===== テーマB =====
      themeHeader("テーマB：業務改善の進め方（Qasee展開）（約55分）", "1B6B3A"),

      sp(80),

      sectionTitle("B-1. Qasee現状共有（10分）"),
      bullet("現状：商品部（主要バイヤー）にQaseeを導入、業務の可視化を実施中"),
      bullet("商品部振り返りミーティング：4/16予定"),
      bullet("可視化で判明した業務ボトルネック・気づきの共有"),
      bullet("　→ どの業務にどれだけの時間がかかっているか"),
      bullet("　→ 削減可能な業務・属人化している業務の洗い出し状況"),

      divider(),

      sectionTitle("B-2. 展開先の検討（20分）"),
      para("次の展開先候補の優先順位を議論：", false),
      sp(60),
      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [2300, 3800, 3646],
        rows: [
          new TableRow({ tableHeader: true, children: [headerCell("展開候補", 2300, "1B6B3A"), headerCell("メリット", 3800, "1B6B3A"), headerCell("留意点", 3646, "1B6B3A")] }),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2300, type: WidthType.DXA }, shading: { fill: "FFFFFF", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "店舗オペレーション", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3800, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "多店舗展開でスケールメリット大・業務標準化に直結", font: "Arial", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3646, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "店舗端末でのログ取得可否を確認要・スマートデバイス（#22）整備とセット検討", font: "Arial", size: 20 })] })] }),
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2300, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "商品部 営業事務", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3800, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "バイヤーと同一部署で展開しやすい・隣接業務の可視化", font: "Arial", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3646, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "バイヤーの可視化結果との比較分析が可能", font: "Arial", size: 20 })] })] }),
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2300, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "リベート管理課", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3800, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "属人化・紙運用が多く改善余地大", font: "Arial", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3646, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "経理・商品部との連携が必要", font: "Arial", size: 20 })] })] }),
          ]}),
          new TableRow({ children: [
            new TableCell({ borders: cellBorders, width: { size: 2300, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "営業推進部", font: "Arial", size: 20, bold: true })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3800, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "販促業務の可視化でQasee×AI-OCR（#33）との連携可能", font: "Arial", size: 20 })] })] }),
            new TableCell({ borders: cellBorders, width: { size: 3646, type: WidthType.DXA }, shading: { fill: "EEF2FA", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: "業務の複雑性・範囲が広い", font: "Arial", size: 20 })] })] }),
          ]}),
        ]
      }),

      sp(100),
      subHeading("展開判断の評価軸（議論）"),
      bullet("業務時間削減見込み・ROI・属人化度などの判断基準を統一する"),

      divider(),

      sectionTitle("B-3. 業務改善のPDCAサイクル設計（15分）"),
      para("Qaseeを「入れっぱなし」にしないための改善ループを設計する："),
      sp(60),
      new Table({
        width: { size: 9746, type: WidthType.DXA },
        columnWidths: [600, 2600, 6546],
        rows: [
          new TableRow({ tableHeader: true, children: [headerCell("Step", 600, "1B6B3A"), headerCell("フェーズ", 2600, "1B6B3A"), headerCell("内容", 6546, "1B6B3A")] }),
          new TableRow({ children: [dataCell("1", 600, false, true), dataCell("可視化（Qasee）", 2600, false, true), dataCell("業務ログの自動収集・時間分布の把握", 6546)] }),
          new TableRow({ children: [dataCell("2", 600, true, true), dataCell("分析・課題特定", 2600, true, true), dataCell("CX推進部が業務ボトルネックを特定・優先順位付け", 6546, true)] }),
          new TableRow({ children: [dataCell("3", 600, false, true), dataCell("改善施策の実行", 2600, false, true), dataCell("RPA・AI・業務フロー変更で対処", 6546)] }),
          new TableRow({ children: [dataCell("4", 600, true, true), dataCell("効果測定", 2600, true, true), dataCell("削減時間・ミス率などを定量評価", 6546, true)] }),
          new TableRow({ children: [dataCell("5", 600, false, true), dataCell("横展開 or 撤退判断", 2600, false, true), dataCell("KPIに基づく次展開部署の意思決定", 6546)] }),
        ]
      }),

      sp(100),
      subHeading("連携施策との統合案"),
      bullet("Qasee × AI（AI-Ready）：可視化した業務をAI適用候補に昇格させる仕組みをつくる"),
      bullet("Qasee × 改鮮活動（#36）：Qasee結果をロート製薬との改鮮活動のインプットとして活用"),
      bullet("Qasee × 業務可視化（#39）：Cacooによる業務フロー図と組み合わせたボトルネック分析"),

      divider(),

      sectionTitle("B-4. アクション・ロードマップ確認（10分）"),
      bullet("4/16 商品部振り返りのアウトプット活用方針"),
      bullet("次展開先・展開時期の暫定決定"),
      bullet("CX推進部内の担当者アサイン"),

      sp(200),

      // ===== まとめ =====
      themeHeader("まとめ：アクションプランの確定（5分）", "555555"),
      sp(80),
      bullet("テーマA・B 各タスクのオーナーと期日を決定"),
      bullet("次回会議の日程・確認事項"),

      sp(160),
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 4 } },
        spacing: { before: 80, after: 0 },
        children: [new TextRun({ text: "作成日：2026年4月6日　CX推進部", font: "Arial", size: 18, color: "888888" })]
      }),
    ]
  }]
});

const outputPath = "C:\\Users\\takatoshi-saito\\OneDrive\\00personal\\ClaudeCodeFolder\\kyorindo-cx\\07_deliverables\\AI_Ready_ミーティングアジェンダ_20260406_v2.docx";

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log("保存完了: " + outputPath);
}).catch(err => {
  console.error("エラー:", err);
  process.exit(1);
});
