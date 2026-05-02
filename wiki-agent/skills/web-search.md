# web-search.md — Web検索による自動知識化スキル

## 概要

`_system/search-topics.yaml` に定義されたトピックを定期的に検索し、
関連記事を取得して wiki 記事として自動生成します。
`maintenance-agent` から週次・月次で呼び出されます。

---

## 参照ファイル

- `KnowledgeBase/_system/search-topics.yaml` — 検索トピック定義
- `KnowledgeBase/_system/SCHEMA.md` — 分類ルール

---

## `search-topics.yaml` の構成

```yaml
# KnowledgeBase/_system/search-topics.yaml
# 検索トピック定義ファイル
# frequency: weekly（毎週）/ monthly（毎月）/ manual（手動のみ）

topics:
  - keyword: "ドラッグストア DX 動向 2026"
    destination: "retail/trends/"
    wiki_type: "reference"
    scope: "retail"
    domain: "retail"
    tags: ["ドラッグストア", "DX", "業界動向"]
    frequency: weekly
    last_searched: ""          # 実行後に自動更新

  - keyword: "LLMエージェント 最新事例"
    destination: "ai-dx/tech-trends/"
    wiki_type: "research"
    scope: "general"
    domain: "ai-dx"
    tags: ["LLM", "エージェント", "AI"]
    frequency: monthly
    last_searched: ""

  - keyword: "杏林堂 ニュース"
    destination: "kyorindo/organization/"
    wiki_type: "reference"
    scope: "kyorindo"
    domain: "organization"
    tags: ["杏林堂", "ニュース"]
    frequency: weekly
    last_searched: ""

  - keyword: "ツルハHD 決算 IR"
    destination: "tsuruha-hd/strategy/"
    wiki_type: "reference"
    scope: "tsuruha-hd"
    domain: "strategy"
    tags: ["ツルハHD", "IR", "決算"]
    frequency: monthly
    last_searched: ""
```

---

## 実行モード

| モード | トリガー | 内容 |
|-------|---------|------|
| `standard` | `topics` セクションの頻度判定 | 通常キーワード検索 |
| `competitor` | `competitor_searches` セクションの頻度判定 | 競合リストから動的生成して検索 |

---

## STEP 1: 実行対象トピックの選定

`search-topics.yaml` を読み込み、今回実行すべきトピックを絞り込む。

```python
import yaml
from datetime import date, timedelta

def select_topics(yaml_path: str) -> list[dict]:
    """
    frequency と last_searched を比較し、実行対象を返す。
    """
    today = date.today()
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    targets = []
    for topic in config.get('topics', []):
        freq = topic.get('frequency', 'manual')
        last = topic.get('last_searched', '')

        if freq == 'manual':
            continue  # 手動トリガーのみ → スキップ

        if not last:
            targets.append(topic)   # 未実行 → 対象
            continue

        last_date = date.fromisoformat(last)
        if freq == 'weekly' and (today - last_date).days >= 7:
            targets.append(topic)
        elif freq == 'monthly' and (today - last_date).days >= 30:
            targets.append(topic)

    return targets[:3]  # 1回の実行で最大3トピックまで


def select_competitor_searches(yaml_path: str) -> list[dict]:
    """
    competitor_searches セクションから実行対象を返す。
    frequency と last_searched を判定する（standard と同じロジック）。
    """
    today = date.today()
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    targets = []
    for cs in config.get('competitor_searches', []):
        freq = cs.get('frequency', 'manual')
        last = cs.get('last_searched', '')

        if freq == 'manual':
            continue
        if not last:
            targets.append(cs)
            continue

        last_date = date.fromisoformat(last)
        if freq == 'weekly' and (today - last_date).days >= 7:
            targets.append(cs)
        elif freq == 'monthly' and (today - last_date).days >= 30:
            targets.append(cs)

    return targets
```

---

## STEP 1-B: 競合検索モード — 競合リストから会社名を抽出する

```python
import re

KB_ROOT = r"C:\Users\takatoshi-saito\OneDrive\00personal\KnowledgeBase"

def extract_companies_from_md(source_file: str) -> dict[str, list[str]]:
    """
    競合店リスト .md から会社名を抽出する。
    Front-matter の companies フィールドがあればそちらを優先する。
    なければ本文のテーブルから抽出する。

    戻り値: {"direct": [...], "indirect": [...]}
    """
    abs_path = os.path.join(KB_ROOT, source_file.replace("/", os.sep))

    with open(abs_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Front-matter から companies を取得（フォールバック定義）
    fm_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    # ※ search-topics.yaml 自体に companies フィールドがあるため
    # ここではテーブルパースを主とする

    # テーブルから「**会社名**」パターンを抽出
    # 例: | 1 | **ウエルシア薬局** | ...
    companies = {"direct": [], "indirect": []}
    current_section = None

    for line in content.split('\n'):
        if 'ドラッグストア' in line and '直接競合' in line:
            current_section = 'direct'
        elif 'GMS' in line or '間接競合' in line:
            current_section = 'indirect'
        elif current_section and line.startswith('|'):
            # テーブル行から **会社名** を抽出
            match = re.search(r'\*\*(.+?)\*\*', line)
            if match:
                name = match.group(1)
                # 括弧内の補足を除去: "マックスバリュ（東海）" → "マックスバリュ東海"
                name_clean = re.sub(r'[（(][^）)]*[）)]', '', name).strip()
                if current_section:
                    companies[current_section].append(name_clean)

    return companies
```

---

## STEP 1-C: 競合検索モード — pre_search でリストを最新化する

```python
def pre_search_competitor_update(pre_search_query: str, known_companies: dict) -> dict:
    """
    WebSearch で競合リストを最新化する。
    - 検索結果から新たな競合チェーンが見つかれば known_companies に追記
    - LLM が検索結果を解析して既存リストと差分を確認する

    戻り値: 更新後の companies dict（追加があれば含む）
    """
    # WebSearch を呼び出す
    search_results = WebSearch(query=pre_search_query)

    # LLMへの指示
    prompt = f"""
以下は競合チェーンの最新情報を確認するための検索結果です。
既知の競合リストと比較して、新たに把握すべき競合チェーンがあれば追記してください。

【既知の直接競合（ドラッグストア）】
{known_companies['direct']}

【既知の間接競合（GMS・スーパー）】
{known_companies['indirect']}

【Web検索結果】
{search_results}

【出力形式】
new_direct: ["（新規直接競合があれば）"]
new_indirect: ["（新規間接競合があれば）"]
notes: "（変化があれば一言メモ）"
※ 変化がなければ new_direct: [] / new_indirect: [] でOK
"""
    result = llm_call(prompt)
    # 新規企業があれば追記
    for c in result.get('new_direct', []):
        known_companies['direct'].append(c)
    for c in result.get('new_indirect', []):
        known_companies['indirect'].append(c)

    return known_companies
```

---

## STEP 2: Web検索の実行

各トピックについて `WebSearch` ツールで検索し、上位3〜5件のURLを取得する。

```
WebSearch を呼び出す:
  query: topic["keyword"]
  → 検索結果（タイトル・URL・スニペット）のリストを取得
  → 上位3〜5件のURLを選定
```

### 記事の選定基準

| 優先 | 条件 |
|------|------|
| 高 | 公開日が直近3ヶ月以内 |
| 高 | 信頼性の高いメディア（業界紙・公式サイト・省庁） |
| 低 | まとめサイト・個人ブログ |
| 除外 | 既に wiki 化済みのURL（`source_url` フィールドで確認） |

---

## STEP 3: ページ内容の取得

選定した各URLに対して `WebFetch` で本文を取得する。

```
WebFetch を呼び出す:
  url: 選定したURL
  → ページ本文（Markdown or テキスト）を取得
  → 先頭8000文字を使用
```

---

## STEP 4: 重複チェック

既存 wiki に類似記事がないか確認する（`index-builder.md` のベクトル検索を利用）。

```python
def is_duplicate(title: str, content: str, threshold: float = 0.92) -> bool:
    """
    wiki-embeddings.npz を使って類似記事を検索。
    類似度が threshold 以上なら重複とみなしてスキップ。
    """
    from sentence_transformers import SentenceTransformer
    import numpy as np

    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    new_emb = model.encode(title + "\n" + content[:500])

    data = np.load('KnowledgeBase/_system/wiki-embeddings.npz', allow_pickle=True)
    embeddings = data['embeddings']
    paths = data['paths']

    similarities = np.dot(embeddings, new_emb) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(new_emb)
    )
    max_sim = float(np.max(similarities))
    if max_sim >= threshold:
        most_similar = paths[int(np.argmax(similarities))]
        print(f"[重複スキップ] 類似度 {max_sim:.2f}: {most_similar}")
        return True
    return False
```

---

## STEP 5: wiki 記事の生成

重複でない記事に対して `write-wiki.md` スキルを呼び出す。

```yaml
# write-wiki.md への入力
file_name: "（URLから生成）"
file_type: "url"
wiki_destination: topic["destination"]
title_suggestion: "（ページタイトルから生成）"
wiki_type: topic["wiki_type"]
scope: topic["scope"]
domain: topic["domain"]
tags: topic["tags"]
source: "web"
source_url: "取得したURL"
converted_text: "WebFetch で取得したページ本文"
```

---

## STEP 6: `search-topics.yaml` の `last_searched` を更新

実行完了後、処理したトピックの `last_searched` を今日の日付に更新する。

```python
def update_last_searched(yaml_path: str, keyword: str) -> None:
    today = date.today().isoformat()
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    for topic in config.get('topics', []):
        if topic['keyword'] == keyword:
            topic['last_searched'] = today
            break

    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
```

---

## STEP 6-B: 競合検索モードのメインループ

```python
def run_competitor_search(cs: dict, yaml_path: str) -> dict:
    """
    competitor_search 型トピックを処理する。
    1. .md から会社名を抽出
    2. pre_search でリスト最新化
    3. 各社 × 3テンプレートで検索・wiki生成
    """
    today = date.today().isoformat()
    source_file = cs['source_file']
    templates   = cs['search_templates']       # ["{company} DX 2026", ...]
    target      = cs.get('target', 'all')      # "direct" / "all"
    destination = cs['destination_template']
    yaml_config = cs                           # wiki_type / scope / domain / tags

    results = []
    errors  = []

    # STEP 1-B: .md から会社名を抽出
    companies = extract_companies_from_md(source_file)

    # フォールバック: YAML に companies が定義されている場合はそちらも参照
    fallback = cs.get('companies', {})
    if not companies['direct'] and fallback.get('direct'):
        companies['direct'] = fallback['direct']
    if not companies['indirect'] and fallback.get('indirect'):
        companies['indirect'] = fallback['indirect']

    # STEP 1-C: pre_search でリスト最新化
    if cs.get('pre_search'):
        companies = pre_search_competitor_update(
            cs.get('pre_search_query', 'ドラッグストア 競合 最新'),
            companies
        )

    # 対象会社リストを組み立てる
    target_companies = list(companies['direct'])
    if target == 'all':
        target_companies += companies['indirect']

    print(f"対象会社: {len(target_companies)}社 × {len(templates)}テンプレート")

    # 各社 × 各テンプレートで検索
    for company in target_companies:
        for template in templates:
            keyword = template.replace('{company}', company)

            # STEP 2: Web検索
            search_results = WebSearch(query=keyword)
            top_urls = select_top_urls(search_results, max_count=3)

            for url in top_urls:
                # STEP 3: ページ取得
                page_content = WebFetch(url=url)
                if not page_content:
                    continue

                title = extract_title(page_content, keyword, company)

                # STEP 4: 重複チェック
                if is_duplicate(title, page_content[:500]):
                    continue

                # STEP 5: wiki生成
                write_wiki_run(
                    wiki_type   = yaml_config['wiki_type'],
                    destination = destination,
                    title       = f"【{company}】{title}",
                    content     = page_content[:8000],
                    source_file = keyword,
                    source_url  = url,
                    scope       = yaml_config['scope'],
                    domain      = yaml_config['domain'],
                    tags        = yaml_config['tags'] + [company],
                )
                results.append({"company": company, "keyword": keyword, "url": url, "title": title})

    # last_searched を更新
    update_competitor_last_searched(yaml_path, cs['source_file'], today)

    return {
        "status":   "success",
        "mode":     "competitor",
        "companies_searched": len(target_companies),
        "articles_written":   len(results),
        "errors":   errors,
    }


def update_competitor_last_searched(yaml_path: str, source_file: str, today: str) -> None:
    """competitor_searches の last_searched を更新する。"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    for cs in config.get('competitor_searches', []):
        if cs.get('source_file') == source_file:
            cs['last_searched'] = today
            break

    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
```

---

## STEP 7: 結果を出力する

```yaml
# 通常検索モードの場合
status: success
executed_topics:
  - keyword: "ドラッグストア DX 動向 2026"
    articles_found: 4
    articles_written: 3
    articles_skipped: 1   # 重複のためスキップ
  - keyword: "LLMエージェント 最新事例"
    articles_found: 3
    articles_written: 3
    articles_skipped: 0
skipped_topics:
  - keyword: "杏林堂 ニュース"
    reason: "last_searched から7日未経過"
errors: []

# 競合検索モードの場合
status: success
mode: competitor
companies_searched: 17
articles_written: 23
errors: []
detail:
  - company: "ウエルシア薬局"
    keyword: "ウエルシア薬局 DX 2026"
    title: "【ウエルシア薬局】2026年DX戦略：デジタル処方箋とアプリ統合"
    url: "https://..."
  - company: "ウエルシア薬局"
    keyword: "ウエルシア薬局 アプリ 最新"
    title: "【ウエルシア薬局】ウエルシアアプリ 新機能リリース"
    url: "https://..."
```

---

## 手動実行（特定トピックのみ）

`frequency: manual` のトピックや、任意のキーワードを1回だけ検索したい場合：

```
web-search.md を起動する際に以下を指定:

keyword: "任意の検索キーワード"
destination: "kyorindo/cx/strategy/"
wiki_type: "reference"
scope: "kyorindo"
domain: "cx"
tags: ["CX"]
```

---

## 呼び出し元・呼び出し先

```
maintenance-agent（週次自動）
    └─→ web-search.md（本スキル）
            ├─→ WebSearch（検索）
            ├─→ WebFetch（ページ取得）
            ├─→ index-builder.md（重複チェック用ベクトル検索）
            └─→ write-wiki.md（wiki記事生成）
                    └─→ place-wiki.md（配置・index更新）
```

---

## 依存ライブラリ

```bash
pip install pyyaml sentence-transformers numpy
```

| ライブラリ | 用途 |
|-----------|------|
| `pyyaml` | search-topics.yaml の読み書き |
| `sentence-transformers` | 重複チェック用ベクトル生成 |
| `WebSearch` | Claude 組み込みツール（検索） |
| `WebFetch` | Claude 組み込みツール（ページ取得） |
