import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "競合DXベンチマーク"

# ---- カラー定義 ----
C_HEADER_DS   = "1F3864"
C_HEADER_GMS  = "1A5276"
C_HEADER_REF  = "4A235A"
C_COL_TITLE   = "2E4057"
C_ROW_DS      = "EBF5FB"
C_ROW_GMS     = "EAF4F4"
C_ROW_REF     = "F5EEF8"
C_STAR5       = "27AE60"
C_STAR4       = "82E0AA"
C_STAR3       = "F9E79F"
C_STAR2       = "F0B27A"
C_STAR1       = "EC7063"
C_WHITE       = "FFFFFF"

def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def thin_border():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

def align(h="left", v="center", wrap=True):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

STAR_COLOR = {
    "★★★★★": C_STAR5,
    "★★★★":  C_STAR4,
    "★★★":   C_STAR3,
    "★★":    C_STAR2,
    "★":     C_STAR1,
}

COLUMNS = [
    "企業名", "カテゴリ", "静岡県内規模", "DX成熟度",
    "AI活用", "データ基盤", "アプリ・デジタル", "調剤DX",
    "リテールメディア", "EX（従業員体験）", "注目ポイント"
]
COL_WIDTHS = [22, 18, 22, 12, 38, 32, 36, 28, 32, 30, 45]

ROWS = [
    # --- ドラッグストア直接競合 ---
    {"_section": "■ ドラッグストア（直接競合）", "_header_color": C_HEADER_DS},
    {
        "企業名": "ウエルシア薬局",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "約215店（県内最多）",
        "DX成熟度": "★★★★★",
        "AI活用": "ダイナミックプライシング（粗利+30%）\nAI売上予測「SalesSensor」\nカスタマーAI（工数90%削減）",
        "データ基盤": "Treasure Data CDP\n医療・健康・POS統合\nMAツール実装",
        "アプリ・デジタル": "混雑チェックアプリ\nモバイルTカード\n1to1マーケティング（True Data）",
        "調剤DX": "オンライン服薬指導",
        "リテールメディア": "デジタルサイネージ1,600店\nイオングループとのデータ統合検討中",
        "EX（従業員体験）": "業務端末リプレイス（2026年）\nカスタマーAIで業務工数削減",
        "注目ポイント": "「ウエルシア2.0」でデータ経営に転換。イオン×ウエルシア×マックスバリュのデータ統合が進むと最大脅威",
    },
    {
        "企業名": "クリエイトエス・ディー",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "約95〜100店",
        "DX成熟度": "★★★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "公式アプリ\n（ポイントカード・クーポン・チラシ・処方箋送信）",
        "調剤DX": "処方箋事前送信（アプリ）",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "食品強化×調剤×ドミナント戦略で5,000億円規模を目指す。DXよりも出店拡大に注力",
    },
    {
        "企業名": "スギ薬局",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "約35〜37店",
        "DX成熟度": "★★★★★",
        "AI活用": "AIファースト宣言\n品揃え最適化AI（エクサウィザーズ）\n薬剤師アシスタントAI（200店・2026年4月本番）",
        "データ基盤": "データレイクハウス構築中\nAWS活用のデータドリブン経営",
        "アプリ・デジタル": "スギ薬局アプリ\nアバター遠隔接客（対応時間1/4）\n生活習慣病リスクレポート",
        "調剤DX": "スギスマホでお薬\nクリニック併設・在宅医療型展開",
        "リテールメディア": "リテールメディア「お茶の間」戦略\n購買率前年比144%",
        "EX（従業員体験）": "生成AI QAボット（1ヶ月で構築・200店展開）\nDX戦略本部に約670人",
        "注目ポイント": "「2030年にAI DXを外部提供できる武器に」宣言。東海地盤で杏林堂商圏と一部重複",
    },
    {
        "企業名": "マツキヨコクミン",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "約30〜32店",
        "DX成熟度": "★★★★★",
        "AI活用": "商品DNA（全商品に意識スコアをタグ付け）\nデータ活用PB開発（新規顧客9割）",
        "データ基盤": "会員2,342万人・接点1億5,000万超\nリアル×デジタル統合プラットフォーム",
        "アプリ・デジタル": "ARメイクシミュレーター\n肌診断・髪診断ツール\n店舗発送型EC（21都道府県展開）",
        "調剤DX": "処方箋事前送信・電子お薬手帳\n（マツキヨコクミンMe）",
        "リテールメディア": "「Matsukiyo Ads」\nGoogle広告×購買データでメーカー向け広告",
        "EX（従業員体験）": "不明",
        "注目ポイント": "ビューティー×デジタルで明確に差別化。リテールメディア事業化が最先進",
    },
    {
        "企業名": "クスリのアオキ",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "静岡進出中（拡大中）",
        "DX成熟度": "★★★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "公式アプリ\n（Aocaポイント・処方箋送信・電子お薬手帳）",
        "調剤DX": "処方箋スマホ送信・電子お薬手帳（アプリ内）",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "2025年3月に1,000店舗達成。食品強化型で急速拡大。静岡への進出が加速中",
    },
    {
        "企業名": "ゲンキー",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "東海エリア展開中",
        "DX成熟度": "★★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "低価格食品訴求型。DXより価格競争力で差別化",
    },
    {
        "企業名": "コスモス薬品",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "進出未確認",
        "DX成熟度": "★★★",
        "AI活用": "確認できていない",
        "データ基盤": "POS×棚割り連動\n本部一元管理の自動発注システム",
        "アプリ・デジタル": "アプリ内オンラインストア\n（アプリ限定商品・クーポン）",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "本部×店舗の役割分担明確化でオペ効率化",
        "注目ポイント": "先端技術よりもオペレーション効率化を優先。「安売り」を支える堅固なデータ基盤",
    },
    {
        "企業名": "サンドラッグ",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "進出未確認",
        "DX成熟度": "★★★★",
        "AI活用": "AI FAQシステム（ユーザーローカル）\nAIカメラ実証実験（Ultimatrust）",
        "データ基盤": "Salesforce Service Cloud＋Experience Cloud",
        "アプリ・デジタル": "Shopify Plus ECサイトリニューアル",
        "調剤DX": "確認できていない",
        "リテールメディア": "Criteoリテールメディア（業界先駆け）\nトクスルビジョン（全1,000店・2025年3月）",
        "EX（従業員体験）": "不明",
        "注目ポイント": "リテールメディアへの早期参入が強み。ファーストパーティデータ活用が進んでいる",
    },
    {
        "企業名": "カワチ薬品",
        "カテゴリ": "直接競合（DS）",
        "静岡県内規模": "進出未確認",
        "DX成熟度": "★★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "大型郊外店型。静岡への進出は現時点で未確認",
    },
    # --- GMS・スーパー間接競合 ---
    {"_section": "■ GMS・スーパー・ディスカウント（間接競合）", "_header_color": C_HEADER_GMS},
    {
        "企業名": "マックスバリュ東海（イオン）",
        "カテゴリ": "間接競合（GMS）",
        "静岡県内規模": "約77店（県内GMS1位）",
        "DX成熟度": "★★★★",
        "AI活用": "AIワーク・MaIボード（約350店）\n生成AI推進（グループ1,000人トライアル）",
        "データ基盤": "イオングループ全体のデジタル売上高1兆円目標（2026年度）",
        "アプリ・デジタル": "独自アプリは2025年2月終了\n→WAONアプリ等グループ共通基盤に統合",
        "調剤DX": "ウエルシアとのグループ連携",
        "リテールメディア": "イオングループとしてのリテールメディア展開",
        "EX（従業員体験）": "AI活用による業務効率化（グループ全体施策）",
        "注目ポイント": "ウエルシア×マックスバリュのデータ統合が進むと杏林堂への最大脅威になりうる",
    },
    {
        "企業名": "イオン（GMS旗艦）",
        "カテゴリ": "間接競合（GMS）",
        "静岡県内規模": "約7店",
        "DX成熟度": "★★★★",
        "AI活用": "AIワーク・MaIボード（約350店）\n生成AI内製化推進",
        "データ基盤": "デジタル売上高1兆円目標（2026年度）\n顧客データをグループ全体で統合",
        "アプリ・デジタル": "iAEONアプリ（WAON統合）\nネットスーパー強化",
        "調剤DX": "ウエルシア（調剤）×イオン（食品）の複合対応",
        "リテールメディア": "イオンメディアグループによる展開",
        "EX（従業員体験）": "AI活用による店舗業務効率化",
        "注目ポイント": "イオンスタイル静岡が2026年春開業予定。体験型GMS×ウエルシア調剤の複合出店の可能性",
    },
    {
        "企業名": "アピタ（ユニー／PPIH）",
        "カテゴリ": "間接競合（GMS）",
        "静岡県内規模": "静岡・東海展開",
        "DX成熟度": "★★★",
        "AI活用": "PPIHグループとしてのAI活用",
        "データ基盤": "PPIHグループ共通のデジタル基盤",
        "アプリ・デジタル": "majicaアプリ（PPIH共通ポイント）",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "2026年春、セントラルスクエア静岡をリニューアル予定。PPIHグループのDX施策が波及する可能性",
    },
    {
        "企業名": "バロー（バローHD）",
        "カテゴリ": "間接競合（GMS）",
        "静岡県内規模": "東海エリア展開",
        "DX成熟度": "★★★",
        "AI活用": "グループ内データ共有クラウド本格稼働",
        "データ基盤": "製造から流通・販売まで一元管理\n「製造小売業」DX。3つのコネクト戦略",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "調剤併設型の展開（確認中）",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "グループ約1,300店舗へのデータ共有基盤展開",
        "注目ポイント": "東海圏で急拡大中。スーパー×ドラッグ×ペット×ホームセンターの複合展開",
    },
    {
        "企業名": "遠鉄ストア",
        "カテゴリ": "間接競合（GMS）",
        "静岡県内規模": "浜松市中心に展開",
        "DX成熟度": "★★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "遠州鉄道グループ。浜松市内で杏林堂と本拠地が完全一致。地域住民の日常購買での直接競合",
    },
    {
        "企業名": "田子重",
        "カテゴリ": "間接競合（スーパー）",
        "静岡県内規模": "焼津市本部・静岡県内",
        "DX成熟度": "★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "対象外",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "静岡県内人気スーパーランキング上位。地元密着・生鮮強みで顧客を囲い込み",
    },
    {
        "企業名": "ドン・キホーテ（PPIH）",
        "カテゴリ": "間接競合（ディスカウント）",
        "静岡県内規模": "県内複数店",
        "DX成熟度": "★★★★",
        "AI活用": "AIプライシング導入（価格最適化）\n内製DXチームによる業務自動化",
        "データ基盤": "内製チームで年間300万時間のムダを削減",
        "アプリ・デジタル": "majicaアプリ（PPIH共通ポイント）",
        "調剤DX": "確認できていない",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "内製DXによる現場業務の自動化",
        "注目ポイント": "無人店舗「キャンパスドンキ」（AIカメラ×重量センサー）実証。深夜営業×低価格でDS需要を代替",
    },
    {
        "企業名": "業務スーパー（神戸物産）",
        "カテゴリ": "間接競合（ディスカウント）",
        "静岡県内規模": "県内展開",
        "DX成熟度": "★",
        "AI活用": "確認できていない",
        "データ基盤": "不明",
        "アプリ・デジタル": "確認できていない",
        "調剤DX": "対象外",
        "リテールメディア": "確認できていない",
        "EX（従業員体験）": "不明",
        "注目ポイント": "節約志向顧客を取り込む価格競合。DXより調達・製造コスト削減で競争",
    },
    # --- ツルハHD参考 ---
    {"_section": "■ ツルハHD（参考：グループ親会社）", "_header_color": C_HEADER_REF},
    {
        "企業名": "ツルハHD（参考：親会社）",
        "カテゴリ": "参考（グループ親会社）",
        "静岡県内規模": "杏林堂経由で全店",
        "DX成熟度": "★★★",
        "AI活用": "生成AIナレッジ検索（NEC共同開発・1,000店舗完了・2026年2月）",
        "データ基盤": "業界初データクリーンルーム「ツルハDCR」（2025年2月）\nSmartDB（契約管理・内部統制）",
        "アプリ・デジタル": "スマホアプリ（楽天ポイント連携・個別商品提案・クーポン）\n独自キャッシュレス決済",
        "調剤DX": "確認できていない",
        "リテールメディア": "データクリーンルーム活用のリテールメディア強化\nリテールAIアワード2024受賞",
        "EX（従業員体験）": "生成AIナレッジ検索（画像・図表対応）",
        "注目ポイント": "グループ資産（生成AI検索・DCR）を杏林堂に横展開することが最速のDX戦略",
    },
]

# ---- タイトル行 ----
ws.merge_cells("A1:K1")
c = ws["A1"]
c.value = "杏林堂 競合DXベンチマーク一覧（2026年4月23日）"
c.font = Font(bold=True, color="FFFFFF", size=14)
c.fill = fill("1A3A5C")
c.alignment = align("center", "center")
ws.row_dimensions[1].height = 30

# ---- 列ヘッダー行 ----
for ci, col_name in enumerate(COLUMNS, 1):
    c = ws.cell(row=2, column=ci, value=col_name)
    c.font = Font(bold=True, color="FFFFFF", size=10)
    c.fill = fill(C_COL_TITLE)
    c.alignment = align("center", "center")
    c.border = thin_border()
ws.row_dimensions[2].height = 36

# ---- 列幅 ----
for i, w in enumerate(COL_WIDTHS, 1):
    ws.column_dimensions[get_column_letter(i)].width = w

# ---- 行ごとのカテゴリ別塗り色 ----
def row_fill_color(cat):
    if "DS" in cat:       return C_ROW_DS
    elif "参考" in cat:   return C_ROW_REF
    else:                  return C_ROW_GMS

# ---- データ書き込み ----
current_row = 3

for row_data in ROWS:
    # セクションヘッダー
    if "_section" in row_data:
        ws.merge_cells(f"A{current_row}:K{current_row}")
        c = ws.cell(row=current_row, column=1, value=row_data["_section"])
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = fill(row_data["_header_color"])
        c.alignment = align("left", "center")
        ws.row_dimensions[current_row].height = 24
        current_row += 1
        continue

    # データ行
    cat = row_data["カテゴリ"]
    row_color = row_fill_color(cat)
    star = row_data["DX成熟度"]

    for ci, col_name in enumerate(COLUMNS, 1):
        c = ws.cell(row=current_row, column=ci, value=row_data[col_name])
        c.border = thin_border()
        c.alignment = align("left", "center")
        c.font = Font(size=9)

        if col_name == "企業名":
            c.font = Font(bold=True, size=10)
            c.fill = fill(row_color)
        elif col_name == "DX成熟度":
            c.fill = fill(STAR_COLOR.get(star, C_STAR1))
            is_dark = star in ["★★★★★", "★★★★"]
            c.font = Font(bold=True, size=11,
                          color="FFFFFF" if is_dark else "333333")
            c.alignment = align("center", "center")
        elif col_name == "注目ポイント":
            c.fill = fill("FDFEFE")
            c.font = Font(size=9, italic=True)
        else:
            c.fill = fill(row_color)

    ws.row_dimensions[current_row].height = 75
    current_row += 1

# ---- 凡例シート ----
ws2 = wb.create_sheet("凡例・説明")
legend = [
    ("DX成熟度", "説明", None),
    ("★★★★★", "業界最先進。複数のAI施策・データ基盤・リテールメディア事業化が揃っている", C_STAR5),
    ("★★★★",  "高水準。AI活用・データ基盤・デジタル施策が進んでいる",                C_STAR4),
    ("★★★",   "標準的。基本的なアプリ・デジタル施策は整備済み",                       C_STAR3),
    ("★★",    "初期段階。デジタル施策は限定的、または情報が少ない",                    C_STAR2),
    ("★",     "情報なし・未着手、またはDX優先度が低い",                               C_STAR1),
]
ws2.column_dimensions["A"].width = 14
ws2.column_dimensions["B"].width = 70
for ri, (star, desc, color) in enumerate(legend, 1):
    ca = ws2.cell(row=ri, column=1, value=star)
    cb = ws2.cell(row=ri, column=2, value=desc)
    for c in (ca, cb):
        c.border = thin_border()
        c.alignment = align("left", "center")
    if ri == 1:
        for c in (ca, cb):
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = fill(C_COL_TITLE)
    else:
        ca.fill = fill(color)
        cb.fill = fill(color)
        is_dark = star in ["★★★★★", "★★★★"]
        ca.font = Font(bold=True, size=12,
                       color="FFFFFF" if is_dark else "333333")
    ws2.row_dimensions[ri].height = 24

# ---- 保存 ----
OUTPUT = (
    r"C:\Users\takatoshi-saito\OneDrive\00personal\ClaudeCodeFolder"
    r"\.claude\worktrees\admiring-hypatia-5eb71d"
    r"\kyorindo-cx\04_references\競合DXベンチマーク_20260423.xlsx"
)
wb.save(OUTPUT)
print(f"保存完了: {OUTPUT}")
