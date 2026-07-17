"""
Tek tesis cek + koordinatlarini goster (dogrulama icin).
Kullanim:  python fetch_one.py AYAZMA
Site'nin 'Tesis Adi' aramasiyla filtreler; sen captcha + Sorgula yaparsin;
bulunan tesis(ler)in TUM koordinatlari TM3 + WGS84 + merkez olarak yazilir.
"""
import sys
import time

from app.scraper import EpdkScraper, ScrapeCallbacks
from app.coords import process_polygon
from app.config import settings

TESIS_ADI = "#elektrikUretimOzetForm\\:tesisAdiInput"


def main():
    aranan = (sys.argv[1] if len(sys.argv) > 1 else "AYAZMA").upper()
    cb = ScrapeCallbacks(log=lambda m: print("  ", m))
    sc = EpdkScraper(cb)
    sc.start()
    sc.select_filters()  # Yururlukte
    try:
        sc.page.fill(TESIS_ADI, aranan)
        print(f"[*] Tesis Adi filtresi = '{aranan}'")
    except Exception as e:
        print("[!] tesis adi yazilamadi:", e)

    print("\n>>> Acilan pencerede: 'Ben robot degilim' + Sorgula. Bekleniyor...\n")
    if not sc.wait_for_captcha_and_results():
        print("[!] Sonuc gelmedi."); sc.close(); return

    sc.set_rows_per_page()
    lics = sc.parse_current_page()
    print(f"[*] {len(lics)} lisans bulundu.")
    for lic in lics:
        for fac in lic.get("facilities", []):
            ad = (fac.get("tesis_adi") or "").upper()
            if aranan not in ad:
                continue
            print("\n" + "=" * 60)
            print(f"TESIS : {fac.get('tesis_adi')}")
            print(f"UNVAN : {lic.get('unvan')}")
            print(f"IL/ILCE: {fac.get('il')} / {fac.get('ilce')}  | KAYNAK: {fac.get('kaynak_turu')}")
            print(f"LISANS NO: {lic.get('lisans_no')}")
            btn = fac.get("coord_btn_id")
            if not btn:
                print("  koordinat butonu YOK"); continue
            pts = sc.fetch_coordinates(btn)
            res = process_polygon(pts)
            print(f"NOKTA SAYISI: {len(pts)}  | dilim: {res['meridian']}  | durum: {res['durum']}")
            print(f"MERKEZ (WGS84): {res['centroid_lat']}, {res['centroid_lng']}")
            print(f"Google Maps: https://www.google.com/maps?q={res['centroid_lat']},{res['centroid_lng']}")
            print("--- ilk 5 ham nokta (TM3) ve WGS84 ---")
            for i, p in enumerate(pts[:5]):
                ll = res["polygon_wgs84"][i] if res["polygon_wgs84"] and i < len(res["polygon_wgs84"]) else None
                print(f"  {p['ad']}: dilim={p['meridian']} E={p['E']} N={p['N']}  ->  {ll}")
    time.sleep(2)
    sc.close()
    print("\n[*] Bitti.")


if __name__ == "__main__":
    main()
