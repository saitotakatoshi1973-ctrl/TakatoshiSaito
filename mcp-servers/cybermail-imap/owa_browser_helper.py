#!/usr/bin/env python3
"""
OWA トークン取得ツール（DevTools コンソール版）

動作フロー:
  1. このスクリプトを実行すると JavaScript スニペットが表示される
  2. ユーザーが普通の Chrome で OWA を開き、DevTools コンソールに貼り付ける
  3. トークンがクリップボードにコピーされる
  4. このスクリプトがクリップボードを監視してトークンを検出・保存する
"""

import json
import os
import subprocess
import sys
import time

_dir = os.path.dirname(os.path.abspath(__file__))
TOKEN_CACHE_PATH = os.path.join(_dir, "owa_token_cache.json")

# Chrome DevTools コンソールに貼り付ける JavaScript
# fetch を傍受して outlook.office.com 向け Bearer トークンをキャプチャする
JS_SNIPPET = r"""(function(){
  window.__owt=null;
  const orig=window.fetch;
  window.fetch=function(...args){
    const url=typeof args[0]==='string'?args[0]:(args[0]&&args[0].url||'');
    const opts=args[1]||{};
    let auth='';
    if(opts.headers){
      if(opts.headers instanceof Headers)auth=opts.headers.get('Authorization')||'';
      else auth=opts.headers['Authorization']||opts.headers['authorization']||'';
    }
    if(url.includes('outlook.office.com')&&auth.startsWith('Bearer ')&&auth.length>200){
      window.__owt=auth.substring(7);
    }
    return orig.apply(this,args);
  };
  console.log('✅ インターセプター設置完了。メールを1通クリックしてください...');
  let n=0;
  const t=setInterval(function(){
    n++;
    if(window.__owt){
      clearInterval(t);
      navigator.clipboard.writeText(window.__owt).then(()=>
        console.log('✅ トークンをクリップボードにコピーしました（'+window.__owt.length+'文字）')
      );
    }else if(n>15){
      clearInterval(t);
      console.log('❌ タイムアウト: メールを1通クリックしてから再試行してください');
    }
  },2000);
})();"""


def get_clipboard() -> str:
    """Windows クリップボードの内容を取得"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def is_jwt(text: str) -> bool:
    """JWT トークンらしい文字列か判定（ey で始まり、200文字以上）"""
    return bool(text and text.startswith("ey") and len(text) > 200 and "." in text)


def main():
    print("=" * 60)
    print("  OWA トークン取得ツール")
    print("=" * 60)
    print()
    print("【手順】")
    print("  1. Chrome を開いて https://outlook.office.com/mail/ にアクセス")
    print("     （HENNGE でログイン済みの受信トレイが表示されている状態にする）")
    print()
    print("  2. F12 キーを押して開発者ツールを開く")
    print()
    print("  3. 「コンソール」タブを選択")
    print()
    print("  4. 下記 JavaScript をすべて選択してコピーし、")
    print("     コンソールに貼り付けて Enter を押す")
    print()
    print("-" * 60)
    print(JS_SNIPPET)
    print("-" * 60)
    print()
    print("  5. コンソールに '✅ インターセプター設置完了' と表示されたら")
    print("     受信トレイのメールを1通クリックしてください")
    print()
    print("  6. '✅ トークンをクリップボードにコピーしました' と表示されたら完了")
    print("     このウィンドウに自動的に保存されます。")
    print()
    print("待機中... (最大5分）")

    # クリップボードを 2 秒ごとに監視
    deadline = time.time() + 300
    last_clip = get_clipboard()  # 現在のクリップボード内容を記録（誤検知防止）

    while time.time() < deadline:
        time.sleep(2)
        clip = get_clipboard()

        # 内容が変わり、かつ JWT らしければ取得成功
        if clip and clip != last_clip and is_jwt(clip):
            print()
            print(f"✅ トークンを検出しました（{len(clip)} 文字）")

            cache = {
                "access_token": clip,
                "expires_at":   time.time() + 55 * 60,
                "source":       "devtools_console",
            }
            with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            print(f"SUCCESS: トークンを保存しました → {TOKEN_CACHE_PATH}")
            return

        last_clip = clip

    print()
    print("ERROR: タイムアウト（5分）。JavaScript を再度実行してください。")
    sys.exit(1)


if __name__ == "__main__":
    main()
