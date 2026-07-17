"""HIZLI TESHIS: tek captcha, ilk sayfadaki (TEMIZ DOM) ilk 5 tesisin
koordinatini cek. Amac: koordinat mekanizmasi temiz DOM'da calisiyor mu?
Her ham yanit teshis/fetch_raw.txt'e (ilk cagri) yazilir."""
import time
from datetime import datetime

from app.scraper import EpdkScraper, ScrapeCallbacks
from app.coords import process_polygon


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


cb = ScrapeCallbacks(log=log)
sc = EpdkScraper(cb, lisans_tipi="uretim")
sc.start()
sc.select_filters()
log(">>> ACILAN PENCEREDE: (arama kutusu BOS) 'Ben robot degilim' + Sorgula. Bekliyorum...")
if not sc.wait_for_captcha_and_results():
    log("[!] Sonuc gelmedi."); sc.close(); raise SystemExit

sc.set_rows_per_page()
lics = sc.parse_current_page()
log(f"Ilk sayfada {len(lics)} lisans parse edildi.")

count = 0
for lic in lics:
    for fac in lic.get("facilities", []):
        btn = fac.get("coord_btn_id")
        if not btn:
            log(f"  (buton yok: {fac.get('tesis_adi')})")
            continue
        count += 1
        log(f"TEST {count}: {fac.get('tesis_adi')} ({fac.get('il')}) btn={btn[-40:]}")
        try:
            pts = sc.fetch_coordinates(btn)
            if pts:
                res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                                        "N": p["N"], "ad": p["ad"]} for p in pts])
                log(f"   -> {len(pts)} NOKTA  merkez=({res['centroid_lat']},{res['centroid_lng']})")
            else:
                log(f"   -> BOS (0 nokta)")
        except Exception as e:
            log(f"   -> HATA: {str(e)[:120]}")
        time.sleep(1.2)
        if count >= 5:
            break
    if count >= 5:
        break

log("=== TEST BITTI. teshis/fetch_raw.txt olustu (ilk cagri ham yaniti). ===")
time.sleep(1)
sc.close()
