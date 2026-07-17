"""
HEDEFLI liste cekici: hedefler.txt'teki tesisleri ilk sayfalarda bulup ceker.
Sadece hedef tesisler cekilir (bos tesisler taranmaz -> WAF minimum). Her tesis
HISAR gibi cok-buton + turbin/saha ayrimiyla islenir. ARTIMLI DEGIL: hedefler
'ok' olsa bile yeniden cekilir (turbin/ikinci set icin).

Kullanim (backend/):  python cek_liste.py
"""
import re
import time
from datetime import datetime, timezone

from app.scraper import EpdkScraper, ScrapeCallbacks, BlockedError, CaptchaInvalid
from app.coords import process_polygon, tm_to_wgs84
from app.database import SessionLocal
from app.models import Facility, License
from app.sync_manager import facility_hash

MAX_SAYFA = 6          # hedefler ilk sayfalarda; gereksiz derine inme
FACILITY_DELAY_S = 2.0
WAF_WAIT_S = 90

_TRLOW = str.maketrans("ÇĞİıÖŞÜ", "CGIIOSU")


def norm(s):
    s = (s or "").translate(_TRLOW).upper()
    s = s.replace("-", " ").replace(".", " ").replace(",", " ")
    return re.sub(r"\s+", " ", s).strip()


def _utcnow():
    return datetime.now(timezone.utc)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


HEDEFLER = {}
with open("hedefler.txt", encoding="utf-8") as fh:
    for line in fh:
        t = line.strip()
        if t:
            HEDEFLER[norm(t)] = t
log(f"{len(HEDEFLER)} hedef tesis yuklendi.")


def _fetch_sets(sc, btn_ids):
    sets = []
    for bid in btn_ids:
        try:
            seg = sc.fetch_coordinates(bid)
        except CaptchaInvalid:
            return sets, True, None
        except BlockedError:
            log(f"    [WAF BLOK] {WAF_WAIT_S}sn bekleniyor...")
            time.sleep(WAF_WAIT_S)
            try:
                seg = sc.fetch_coordinates(bid)
            except CaptchaInvalid:
                return sets, True, None
            except Exception as e:
                return sets, False, f"waf-sonrasi: {str(e)[:60]}"
        except Exception as e:
            return sets, False, str(e)[:80]
        if seg:
            sets.append(seg)
    return sets, False, None


def _save(db, fo, saha, turbin):
    res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                            "N": p["N"], "ad": p["ad"]} for p in saha])
    turbin_wgs = []
    for p in turbin:
        la, ln = tm_to_wgs84(p["meridian"], p["E"], p["N"])
        turbin_wgs.append([round(la, 6), round(ln, 6)])
    fo.dilim_meridyeni = res["meridian"]
    fo.ham_koordinat_tm3 = saha + turbin
    fo.polygon_wgs84 = res["polygon_wgs84"]
    fo.turbine_points = turbin_wgs or None
    fo.centroid_lat = res["centroid_lat"]
    fo.centroid_lng = res["centroid_lng"]
    fo.first_point_lat = res["first_point_lat"]
    fo.first_point_lng = res["first_point_lng"]
    fo.koordinat_durumu = res["durum"]
    fo.koordinat_alindi = True
    fo.last_seen = _utcnow()
    db.commit()
    return res, len(turbin_wgs)


def main():
    db = SessionLocal()
    cb = ScrapeCallbacks(log=log)
    sc = EpdkScraper(cb, lisans_tipi="uretim")
    sc.start()
    sc.select_filters()
    log(">>> ACILAN PENCEREDE: 'Ben robot degilim' + Sorgula. Bekliyorum (10dk)...")
    if not sc.wait_for_captcha_and_results():
        log("[!] Sonuc gelmedi."); sc.close(); db.close(); return
    sc.set_rows_per_page()
    total_pg = sc.total_pages()

    bulunan = set()
    done_ok = 0
    page = 1
    while page <= min(MAX_SAYFA, total_pg):
        lics = sc.parse_current_page()
        reauth_oldu = False
        for lic in lics:
            if reauth_oldu:
                break
            lno = lic.get("lisans_no") or ""
            for fac in lic.get("facilities", []):
                nad = norm(fac.get("tesis_adi"))
                hit = nad in HEDEFLER or any(h in nad or nad in h for h in HEDEFLER)
                if not hit or nad in bulunan:
                    continue
                btn_ids = fac.get("coord_btn_ids") or (
                    [fac.get("coord_btn_id")] if fac.get("coord_btn_id") else [])
                if not btn_ids:
                    log(f"  (buton yok: {fac.get('tesis_adi')})"); continue
                time.sleep(FACILITY_DELAY_S)
                sets, captcha_dustu, hata = _fetch_sets(sc, btn_ids)
                if captcha_dustu:
                    log(f"  [captcha dustu] {fac.get('tesis_adi')} -> pencerede tekrar Sorgula")
                    sc.reauth_navigate()
                    if not sc.wait_for_captcha_and_results():
                        log("[!] Yenilenemedi."); sc.close(); db.close(); return
                    sc.set_rows_per_page(); total_pg = sc.total_pages()
                    sc.goto_page(page)
                    reauth_oldu = True
                    break
                if hata:
                    log(f"  [HATA-atlandi] {fac.get('tesis_adi')}: {hata}"); continue
                if not sets:
                    log(f"  YOK: {fac.get('tesis_adi')} (koordinat girilmemis)"); continue
                uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
                fo = db.query(Facility).filter_by(unique_hash=uh).first()
                if not fo:
                    log(f"  (DB'de yok: {fac.get('tesis_adi')})"); continue
                sets.sort(key=len, reverse=True)
                saha = sets[0]; turbin = [p for s in sets[1:] for p in s]
                res, nt = _save(db, fo, saha, turbin)
                done_ok += 1
                bulunan.add(nad)
                tstr = f" + {nt} turbin" if nt else ""
                log(f"OK  {fac.get('tesis_adi')} ({fac.get('il')}) -> {len(saha)} saha{tstr} "
                    f"nokta ({res['centroid_lat']},{res['centroid_lng']}) [OK={done_ok}/{len(HEDEFLER)}]")
        if reauth_oldu:
            continue  # ayni sayfayi yeni oturumla yeniden isle
        if page >= min(MAX_SAYFA, total_pg):
            break
        if not sc.next_page():
            log(f"[!] Sayfa {page} sonrasi ilerlenemedi."); break
        page += 1

    log(f"=== BITTI: {done_ok}/{len(HEDEFLER)} hedef cekildi ===")
    eksik = [HEDEFLER[h] for h in HEDEFLER if h not in bulunan]
    if eksik:
        log(f"Bulunamayan/cekilmeyen ({len(eksik)}): {', '.join(eksik[:20])}")
    sc.close(); db.close()


if __name__ == "__main__":
    main()
