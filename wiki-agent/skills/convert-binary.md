# convert-binary.md — バイナリファイルテキスト変換スキル

## 概要

`_inbox/` 内のバイナリファイルをテキスト（Markdown）に変換し、`analyze.md` が内容を分析できる状態にします。
変換結果はメモリ上に保持し、`analyze.md` の STEP 3-C から呼び出されます。

---

## 対応フォーマット一覧

| 分類 | 拡張子 | 変換方法 |
|------|--------|---------|
| PDF | `.pdf` | pdfminer.six（小容量）/ ページ分割読み込み（大容量）|
| Office | `.pptx` | python-pptx テキスト抽出 |
| Office | `.xlsx` | openpyxl セル値抽出 |
| Office | `.docx` | python-docx 段落抽出 |
| 画像 | `.png` `.jpg` `.jpeg` `.gif` `.webp` | マルチモーダル読み込み（LLM直接認識）|
| 音声 | `.mp3` `.wav` `.m4a` `.ogg` | faster-whisper 文字起こし |
| 動画 | `.mp4` `.mov` `.avi` `.mkv` | ffmpeg で音声抽出 → faster-whisper 文字起こし |
| メール | `.eml` | Python 標準 email モジュール |
| 圧縮 | `.zip` | 展開 → 各ファイルを再帰処理 |
| URL リスト | `.txt`（URL行が過半数） | WebFetch で各URL取得（複数行対応）|

---

## OneDrive ロック対策（全処理共通）

ファイル操作で `WinError 5`（アクセス拒否）が発生した場合、以下を実行する：

```python
import time

def safe_open(file_path, mode='rb', retries=3, wait=5):
    for attempt in range(retries):
        try:
            return open(file_path, mode)
        except PermissionError as e:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}/{retries}] OneDriveロック中。{wait}秒後に再試行: {file_path}")
                time.sleep(wait)
            else:
                raise RuntimeError(f"ファイルを開けませんでした（{retries}回試行）: {file_path}") from e
```

---

## STEP 1: ファイル種別判定

```python
import os

def get_file_type(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    TYPE_MAP = {
        '.pdf':  'pdf',
        '.pptx': 'pptx',
        '.xlsx': 'xlsx',
        '.docx': 'docx',
        '.png':  'image',
        '.jpg':  'image',
        '.jpeg': 'image',
        '.gif':  'image',
        '.webp': 'image',
        '.mp3':  'audio',
        '.wav':  'audio',
        '.m4a':  'audio',
        '.ogg':  'audio',
        '.mp4':  'video',
        '.mov':  'video',
        '.avi':  'video',
        '.mkv':  'video',
        '.eml':  'eml',
        '.zip':  'zip',
    }
    return TYPE_MAP.get(ext, 'unknown')

def get_file_type_with_content(file_path: str) -> str:
    """
    .txt ファイルは内容を確認して url_list か通常テキストかを判定する。
    それ以外は拡張子で判定。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines()[:5]
                         if l.strip() and not l.strip().startswith('#')]
            url_lines = [l for l in lines
                         if l.startswith('http://') or l.startswith('https://')]
            if lines and len(url_lines) >= len(lines) / 2:
                return 'url_list'
        except Exception:
            pass
        return 'text'  # 通常テキスト（analyze.md STEP 3-A で処理）
    return get_file_type(file_path)
```

---

## STEP 2: フォーマット別変換処理

### 2-A: PDF

```python
def convert_pdf(file_path):
    import os
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    try:
        from pdfminer.high_level import extract_text
        
        if file_size_mb <= 10:
            # 小容量: 一括読み込み
            with safe_open(file_path) as f:
                text = extract_text(f)
            return f"# PDF抽出テキスト\n\n{text[:8000]}"
        
        else:
            # 大容量: ページ分割（20ページずつ）
            from pdfminer.high_level import extract_text_to_fp
            from pdfminer.layout import LAParams
            import io
            
            results = []
            page_start = 0
            page_chunk = 20
            
            while True:
                buf = io.StringIO()
                with safe_open(file_path) as f:
                    extract_text_to_fp(
                        f, buf,
                        page_numbers=list(range(page_start, page_start + page_chunk)),
                        laparams=LAParams()
                    )
                chunk_text = buf.getvalue().strip()
                if not chunk_text:
                    break
                results.append(f"## ページ {page_start+1}〜{page_start+page_chunk}\n\n{chunk_text[:4000]}")
                page_start += page_chunk
                
                # 最大60ページ（3チャンク）で打ち切り
                if page_start >= 60:
                    results.append("（60ページ以降は省略）")
                    break
            
            return "\n\n---\n\n".join(results) if results else "（テキスト抽出不可）"
    
    except ImportError:
        return "（pdfminer.six 未インストール: pip install pdfminer.six）"
    except Exception as e:
        return f"（PDF変換エラー: {e}）"
```

### 2-B: PowerPoint (.pptx)

```python
def convert_pptx(file_path):
    try:
        from pptx import Presentation
        
        with safe_open(file_path) as f:
            prs = Presentation(f)
        
        lines = []
        for i, slide in enumerate(prs.slides):
            slide_texts = []
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    slide_texts.append(shape.text.strip())
            if slide_texts:
                lines.append(f"## スライド {i+1}\n\n" + "\n".join(slide_texts))
        
        return "\n\n---\n\n".join(lines) if lines else "（テキストなし）"
    
    except ImportError:
        return "（python-pptx 未インストール: pip install python-pptx）"
    except Exception as e:
        return f"（PPTX変換エラー: {e}）"
```

### 2-C: Excel (.xlsx)

```python
def convert_xlsx(file_path):
    try:
        import openpyxl
        
        with safe_open(file_path) as f:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        
        lines = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows_text = []
            row_count = 0
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else '' for c in row]
                row_str = ' | '.join(cells).strip(' |')
                if row_str:
                    rows_text.append(row_str)
                row_count += 1
                if row_count >= 200:  # 最大200行
                    rows_text.append("（200行以降省略）")
                    break
            if rows_text:
                lines.append(f"## シート: {sheet_name}\n\n" + "\n".join(rows_text))
        
        return "\n\n---\n\n".join(lines) if lines else "（データなし）"
    
    except ImportError:
        return "（openpyxl 未インストール: pip install openpyxl）"
    except Exception as e:
        return f"（XLSX変換エラー: {e}）"
```

### 2-D: Word (.docx)

```python
def convert_docx(file_path):
    try:
        from docx import Document
        
        with safe_open(file_path) as f:
            doc = Document(f)
        
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs[:300]) if paragraphs else "（テキストなし）"
    
    except ImportError:
        return "（python-docx 未インストール: pip install python-docx）"
    except Exception as e:
        return f"（DOCX変換エラー: {e}）"
```

### 2-E: 画像（マルチモーダル）

画像ファイルはLLMのマルチモーダル機能で直接認識する。
Pythonスクリプトは不要。`analyze.md` STEP 3-B の処理に委ねる。

```
[処理なし: analyze.md STEP 3-B で Read ツール（画像）を使用]
```

### 2-F: 音声（faster-whisper）

```python
def convert_audio(file_path):
    try:
        from faster_whisper import WhisperModel
        
        # モデル初期化（初回はダウンロードあり）
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(file_path, beam_size=5, language="ja")
        
        transcript = "\n".join([seg.text for seg in segments])
        return f"# 音声文字起こし\n\n言語: {info.language}\n\n{transcript}" if transcript else "（文字起こし結果なし）"
    
    except ImportError:
        return "（faster-whisper 未インストール: pip install faster-whisper）"
    except Exception as e:
        return f"（音声変換エラー: {e}）"
```

### 2-G: 動画（ffmpeg → faster-whisper）

```python
def convert_video(file_path):
    import subprocess
    import tempfile
    import os
    
    # ffmpegが使えるか確認
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "（ffmpeg が見つかりません。インストールしてください）"
    
    # 一時ファイルに音声抽出
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        subprocess.run(
            ['ffmpeg', '-i', file_path, '-vn', '-acodec', 'pcm_s16le',
             '-ar', '16000', '-ac', '1', tmp_path, '-y'],
            capture_output=True, check=True
        )
        # 抽出した音声を文字起こし
        result = convert_audio(tmp_path)
        return result
    except subprocess.CalledProcessError as e:
        return f"（動画→音声抽出エラー: {e}）"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
```

### 2-H: メール (.eml)

```python
def convert_eml(file_path):
    import email
    from email import policy
    from email.parser import BytesParser
    
    try:
        with safe_open(file_path) as f:
            msg = BytesParser(policy=policy.default).parse(f)
        
        lines = []
        lines.append(f"**From**: {msg.get('From', '')}")
        lines.append(f"**To**: {msg.get('To', '')}")
        lines.append(f"**Date**: {msg.get('Date', '')}")
        lines.append(f"**Subject**: {msg.get('Subject', '')}")
        lines.append("")
        
        # 本文取得
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                    break
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='replace')
        
        lines.append(body[:5000])
        
        # 添付ファイル名一覧
        attachments = []
        for part in msg.walk():
            filename = part.get_filename()
            if filename:
                attachments.append(filename)
        if attachments:
            lines.append(f"\n**添付ファイル**: {', '.join(attachments)}")
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"（EML変換エラー: {e}）"
```

### 2-I: ZIP（再帰処理）

```python
def convert_zip(file_path, depth=0):
    import zipfile
    import tempfile
    import shutil
    import os
    
    if depth > 2:
        return "（ZIPネスト上限（2階層）に達しました）"
    
    results = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)
            
            for root, dirs, files in os.walk(tmpdir):
                for fname in files[:20]:  # 最大20ファイル
                    inner_path = os.path.join(root, fname)
                    file_type = get_file_type(inner_path)
                    
                    if file_type == 'unknown':
                        continue
                    elif file_type == 'image':
                        results.append(f"### {fname}\n\n（画像ファイル: analyze.md STEP 3-B で処理）")
                    elif file_type == 'zip':
                        results.append(f"### {fname}\n\n" + convert_zip(inner_path, depth + 1))
                    else:
                        converted = convert_binary(inner_path)
                        results.append(f"### {fname}\n\n{converted[:2000]}")
        
        except zipfile.BadZipFile:
            return "（ZIPファイルが破損しています）"
        except Exception as e:
            return f"（ZIP展開エラー: {e}）"
    
    return "\n\n---\n\n".join(results) if results else "（変換可能なファイルなし）"
```

### 2-J: URL リスト (.txt)

`.txt` ファイルに記載された複数のURLを順に取得し、
各URLのページ内容を Markdown テキストとして返す。

**ルール**:
- 1行1URL（空行・`#` で始まるコメント行はスキップ）
- 最大5件まで処理（超過分は次回実行を促すメッセージを付与）
- 各URLは `WebFetch` ツールで取得する

```python
def convert_url_list(file_path: str) -> list[dict]:
    """
    URLリスト .txt ファイルを読み込み、各URLのコンテンツを取得する。

    戻り値: [
        {"url": "https://...", "content": "取得したテキスト", "title": "ページタイトル"},
        ...
    ]
    """
    results = []
    skipped = []

    with safe_open(file_path, 'r') as f:
        raw_lines = f.read().splitlines()

    # コメント・空行を除外
    urls = [
        line.strip() for line in raw_lines
        if line.strip() and not line.strip().startswith('#')
        and (line.strip().startswith('http://') or line.strip().startswith('https://'))
    ]

    if len(urls) > 5:
        skipped = urls[5:]
        urls = urls[:5]
        print(f"[URL上限] 最大5件まで処理します。残り{len(skipped)}件は次回実行を促します。")

    for url in urls:
        try:
            # WebFetch ツールで取得（Claude の組み込みツールを使用）
            # ここでは WebFetch の呼び出しを示す（実行時はツール経由）
            page_content = web_fetch(url)   # → WebFetch ツール呼び出し
            results.append({
                "url": url,
                "content": page_content[:8000],  # 先頭8000文字
                "title": extract_title(page_content),
                "skipped_urls": skipped,
            })
        except Exception as e:
            results.append({
                "url": url,
                "content": f"（取得失敗: {e}）",
                "title": "",
                "skipped_urls": skipped,
            })

    return results


def extract_title(html_or_text: str) -> str:
    """ページテキストからタイトルを抽出する（簡易実装）"""
    import re
    # <title>タグ
    m = re.search(r'<title[^>]*>(.*?)</title>', html_or_text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()[:100]
    # # 見出し（Markdown）
    m = re.search(r'^#\s+(.+)', html_or_text, re.MULTILINE)
    if m:
        return m.group(1).strip()[:100]
    return ""
```

> **注意**: `web_fetch(url)` は Claude の `WebFetch` 組み込みツールを呼び出す。
> スクリプト実行ではなく、LLMエージェントとして動作する際に自動的に利用できる。

---

## STEP 3: メイン呼び出し関数

```python
def convert_binary(file_path):
    """
    バイナリファイルをテキストに変換してMarkdown文字列で返す。
    analyze.md STEP 3-C から呼び出す。

    url_list の場合は list[dict] を返す（analyze.md STEP 3-D で処理）。
    """
    file_type = get_file_type_with_content(file_path)  # .txt はコンテンツ確認

    # URL リストは特別処理（複数URLの list を返す）
    if file_type == 'url_list':
        return convert_url_list(file_path)

    # 通常テキスト（analyze.md STEP 3-A へ委譲）
    if file_type == 'text':
        return '__TEXT__'

    converters = {
        'pdf':   convert_pdf,
        'pptx':  convert_pptx,
        'xlsx':  convert_xlsx,
        'docx':  convert_docx,
        'audio': convert_audio,
        'video': convert_video,
        'eml':   convert_eml,
        'zip':   convert_zip,
        # 'image' は analyze.md STEP 3-B (マルチモーダル) に委譲
    }
    
    if file_type == 'image':
        return '__IMAGE__'  # analyze.md 側でマルチモーダル処理を行うシグナル
    
    if file_type == 'unknown':
        return f"（未対応フォーマット: {os.path.splitext(file_path)[1]}）"
    
    converter = converters.get(file_type)
    return converter(file_path)
```

---

## 出力仕様

| 戻り値 | 意味 |
|--------|------|
| Markdown文字列 | 変換成功。`analyze.md` が内容分析に使用する |
| `'__IMAGE__'` | 画像ファイル。`analyze.md` STEP 3-B でマルチモーダル処理する |
| `（エラーメッセージ）` | 変換失敗。`analyze.md` はエラーメッセージを出力YAMLの `note` に記載する |

---

## 依存ライブラリ

```bash
pip install pdfminer.six python-pptx openpyxl python-docx faster-whisper
# ffmpeg は別途 https://ffmpeg.org/ からインストール
```

| ライブラリ | 用途 |
|-----------|------|
| `pdfminer.six` | PDF テキスト抽出 |
| `python-pptx` | PPTX テキスト抽出 |
| `openpyxl` | XLSX セル値抽出 |
| `python-docx` | DOCX 段落抽出 |
| `faster-whisper` | 音声・動画の文字起こし |
| `ffmpeg`（外部） | 動画から音声ストリーム抽出 |
| `email`（標準） | EML 解析 |
| `zipfile`（標準） | ZIP 展開 |
