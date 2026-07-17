"""Uretim sayfasindaki form alanlarini kesfet (captcha YOK, headless)."""
from playwright.sync_api import sync_playwright
from app.config import settings

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(locale="tr-TR")
    pg.goto(settings.url_for("uretim"), wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)
    title = pg.title()
    body_len = pg.evaluate("() => document.body ? document.body.innerText.length : 0")
    all_inputs = pg.evaluate("() => document.querySelectorAll('input,select,textarea').length")
    print(f"TITLE: {title!r}  body_len={body_len}  input_say={all_inputs}")
    # ilk 500 karakter govde
    txt = pg.evaluate("() => (document.body ? document.body.innerText : '').slice(0,600)")
    print("--- BODY ilk 600 ---")
    print(txt)
    # TUM input id+name (hidden dahil)
    info = pg.evaluate(r"""
    () => Array.from(document.querySelectorAll('input,select,textarea'))
      .map(el => ({id: el.id||'', name: el.name||'', type:(el.type||'').toLowerCase()}))
    """)
    print(f"\n--- TUM {len(info)} ALAN ---")
    for r in info:
        print(r)
    b.close()
