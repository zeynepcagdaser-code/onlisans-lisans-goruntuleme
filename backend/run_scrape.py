"""
CLI: Senkronu (insan-destekli captcha akisi) dogrudan baslatir; sunucu gerekmez.
Tarayici acilir, 'Yururlukte' secilir, SEN captcha'yi cozup Sorgula'ya basarsin,
gerisi otomatik (tum sayfalar + koordinatlar + artimli).

Kullanim:
    python run_scrape.py                # tam cekim (varsayilan resume)
    python run_scrape.py --no-resume    # bastan
    python run_scrape.py --max-pages 2  # hizli test (ilk 2 sayfa)
"""
import argparse
import time

from app.config import settings
from app.database import init_db
from app import sync_manager


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args()

    if args.max_pages is not None:
        settings.max_pages = args.max_pages

    init_db()
    print("[*] Senkron baslatiliyor. Tarayici acilinca captcha'yi cozup Sorgula'ya bas.")
    sync_manager.start_sync(resume=not args.no_resume)

    last_msg = None
    while sync_manager.is_running():
        snap = sync_manager.STATE.snapshot()
        if snap["message"] != last_msg:
            print(f"    [{snap['durum']}] {snap['message']}")
            last_msg = snap["message"]
        time.sleep(1)
    snap = sync_manager.STATE.snapshot()
    print(f"[*] Bitti: {snap['durum']} - {snap['message']}")


if __name__ == "__main__":
    main()
