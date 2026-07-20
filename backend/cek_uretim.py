"""
Bagimsiz uretim-koordinat cekici (uvicorn'dan bagimsiz, TAZE kod).

Neden ayri: uvicorn sureci import edilen eski scraper'i bellekte tutuyordu.
Bu script kendi surecinde calisir -> her zaman guncel scraper.py yuklenir.

Akis:
  1. Tarayici ac, Yururlukte sec, KULLANICI captcha coz + Sorgula.
  2. Tum sayfalari gez; DB'de eksik-koordinatli uretim tesisleri icin koordinat cek.
  3. Bos yanit (0 nokta) izle: art arda COK bos -> captcha dusmus say -> pencerede
     yeniden captcha iste (reauth), kaldigin sayfadan devam.
  4. Her tesiste DB'ye yaz (artimli, guvenli). WAF blogunda bekle-tekrar-dene.

Kullanim (backend/ klasorunde):
    python cek_uretim.py
"""
import time
from datetime import datetime, timezone

from app.scraper import EpdkScraper, ScrapeCallbacks, BlockedError, CaptchaInvalid
from app.coords import tm_to_wgs84
from app.coords import process_polygon
from app.database import SessionLocal
from app.models import Facility, License
from app.sync_manager import facility_hash

CONSEC_EMPTY_REAUTH = 4     # art arda bu kadar BOS -> captcha dustu, yenile
WAF_WAIT_S = 90             # WAF blogunda tek bekleme
FACILITY_DELAY_S = 2.2      # tesisler arasi nezaket (WAF'i geciktir)


def _utcnow():
    return datetime.now(timezone.utc)


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _save_coords(db, fo, saha_pts, turbin_pts):
    """saha_pts -> SAHA poligonu; turbin_pts -> ayri TURBIN noktalari (poligon degil).
    process_polygon'a il verilir -> yanlis EPDK dilim etiketi + placeholder DUZELIR."""
    from app.coords import duzelt_noktalar
    res = process_polygon([{"meridian": p["meridian"], "E": p["E"],
                            "N": p["N"], "ad": p["ad"]} for p in saha_pts], il=fo.il)
    turbin_wgs = []
    for p in duzelt_noktalar(turbin_pts, fo.il):
        la, ln = tm_to_wgs84(p["meridian"], p["E"], p["N"])
        turbin_wgs.append([round(la, 6), round(ln, 6)])
    fo.dilim_meridyeni = res["meridian"]
    fo.ham_koordinat_tm3 = saha_pts + turbin_pts
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


def _fetch_sets(sc, btn_ids):
    """Bir tesisin TUM koordinat butonlarini ayri set olarak cek.
    Doner: (sets, captcha_dustu, hata). sets = [[nokta,...], ...] buton basina."""
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


def main():
    db = SessionLocal()

    # Ne kadar isimiz var?
    toplam_eksik = db.query(Facility).join(License).filter(
        License.lisans_tipi == "uretim",
        (Facility.koordinat_alindi == False) |
        (Facility.koordinat_durumu.in_(["beklemede", "hata", "yok"]))
    ).count()
    log(f"Eksik-koordinatli uretim tesisi: ~{toplam_eksik}")

    cb = ScrapeCallbacks(log=log)
    sc = EpdkScraper(cb, lisans_tipi="uretim")
    sc.start()
    sc.select_filters()
    log(">>> ACILAN PENCEREDE: 'Ben robot degilim' kutucugunu isaretle + Sorgula'ya bas. (10 dk bekliyorum)")
    if not sc.wait_for_captcha_and_results():
        log("[!] Sonuc gelmedi (captcha cozulmedi). Cikiliyor.")
        sc.close(); db.close(); return

    sc.set_rows_per_page()
    total_pg = sc.total_pages()
    log(f"Toplam sayfa: {total_pg}")

    done_ok = 0
    done_empty = 0
    consec_empty = 0
    page = 1

    def reauth():
        """Captcha dustu -> pencerede yeniden captcha iste, ayni sayfaya don."""
        nonlocal total_pg, consec_empty
        log(">>> Koordinat gelmiyor — CAPTCHA DUSMUS olabilir. PENCEREDE tekrar "
            "'Ben robot degilim' + Sorgula yap. Bekliyorum...")
        sc.reauth_navigate()
        if not sc.wait_for_captcha_and_results():
            return False
        sc.set_rows_per_page()
        total_pg = sc.total_pages()
        consec_empty = 0
        if page > 1:
            sc.goto_page(page)
        return True

    while True:
        lics = sc.parse_current_page()
        restart_page = False
        for lic in lics:
            lno = lic.get("lisans_no") or ""
            if not lno:
                continue
            for fac in lic.get("facilities", []):
                uh = facility_hash(lno, fac.get("tesis_adi"), fac.get("il"), fac.get("ilce"))
                fo = db.query(Facility).filter_by(unique_hash=uh).first()
                if fo is None:
                    continue  # liste henuz DB'de degil; liste modu ayri
                # Zaten gecerli koordinati olani atla (artimli)
                if fo.koordinat_alindi and fo.koordinat_durumu in (
                        "ok", "supheli", "koordinat_yok_teyitli"):
                    continue
                btn_ids = fac.get("coord_btn_ids") or (
                    [fac.get("coord_btn_id")] if fac.get("coord_btn_id") else [])
                if not btn_ids:
                    fo.koordinat_durumu = "yok"
                    fo.koordinat_alindi = True
                    db.commit()
                    continue

                time.sleep(FACILITY_DELAY_S)
                # TUM butonlari ayri set olarak cek (cok-setli: RES sahasi + turbin)
                sets, captcha_dustu, hata = _fetch_sets(sc, btn_ids)

                if captcha_dustu:
                    # GERCEK captcha dusmesi (validationFailed) -> reauth
                    log(f"    [captcha dustu] {fac.get('tesis_adi')} -> oturum yenileniyor")
                    if not reauth():
                        log("[!] Captcha yenilenemedi. Cikiliyor.")
                        sc.close(); db.close(); return
                    restart_page = True
                    break
                elif sets:
                    # en cok noktali set = SAHA poligonu; digerleri = TURBIN noktalari
                    sets.sort(key=len, reverse=True)
                    saha = sets[0]
                    turbin = [p for s in sets[1:] for p in s]
                    res, nt = _save_coords(db, fo, saha, turbin)
                    done_ok += 1
                    tstr = f" + {nt} turbin" if nt else ""
                    log(f"OK  {fac.get('tesis_adi')} -> {len(saha)} saha{tstr} nokta "
                        f"({res['centroid_lat']},{res['centroid_lng']}) [OK={done_ok}]")
                elif hata:
                    # WAF/network hatasi -> ISARETLEME (koordinat_alindi=False kalir),
                    # sonraki turda tekrar denenir. Yanlislikla 'yok' YAZMA.
                    log(f"    [HATA-atlandi] {fac.get('tesis_adi')}: {hata}")
                else:
                    # [] = contentLoad 'Kayit Bulunamadi' -> tesis GERCEKTEN
                    # koordinatsiz (captcha DEGIL). Teyitli isaretle + GEC.
                    fo.koordinat_durumu = "koordinat_yok_teyitli"
                    fo.koordinat_alindi = True
                    fo.last_seen = _utcnow()
                    db.commit()
                    done_empty += 1
                    log(f"YOK-teyitli {fac.get('tesis_adi')} (koordinat girilmemis) [yok={done_empty}]")
            if restart_page:
                break

        if restart_page:
            continue  # ayni sayfayi yeni oturumla yeniden parse et

        # sonraki sayfa
        if page >= total_pg:
            break
        if not sc.next_page():
            log(f"[!] Sayfalama {page}/{total_pg}'de takildi. Duruluyor.")
            break
        page += 1
        log(f"--- Sayfa {page}/{total_pg} (OK={done_ok}, bos={done_empty}) ---")

    log(f"=== BITTI: yeni koordinat={done_ok}, bos-yanit={done_empty} ===")
    sc.close()
    db.close()


if __name__ == "__main__":
    main()
