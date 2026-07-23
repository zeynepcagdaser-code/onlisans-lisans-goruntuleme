"""Tesis API'si: filtre + sayfalama + GeoJSON + KMZ + koordinat/CSV indirme."""
import csv
import gzip
import io
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..coords import (area_centroid, build_rings_latlng, in_turkey,
                      process_polygon, tm_to_wgs84)
from ..database import get_db
from ..kmz import build_kmz
from ..models import Facility, License
from ..schemas import FacilityDetail, FacilityOut, FacilityPage

router = APIRouter(prefix="/api/facilities", tags=["facilities"])

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# Turkce-duyarli arama: SQLite LIKE/ilike sadece ASCII katliyor (İ/Ğ/Ş katlamaz),
# bu yuzden "degirmen" yazinca "DEĞİRMEN"i bulamiyordu. Iki tarafi da ASCII-kucuk'e
# katlayip karsilastir.
_TR_PAIRS = [("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u"),
             ("Ç", "C"), ("Ğ", "G"), ("İ", "I"), ("Ö", "O"), ("Ş", "S"), ("Ü", "U")]


def _fold_sql(col):
    """Bir kolonu SQL icinde Turkce->ASCII katla + kucuk harf (nested REPLACE)."""
    expr = col
    for a, b in _TR_PAIRS:
        expr = func.replace(expr, a, b)
    return func.lower(expr)


def _fold_py(s: str) -> str:
    """Arama terimini Turkce->ASCII katla + kucuk harf."""
    return (s or "").translate(_TR).lower()


def _safe_filename(name: str, default: str = "dosya") -> str:
    """HTTP header (latin-1) icin ASCII-guvenli dosya adi."""
    s = (name or default).translate(_TR)
    s = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in s)
    s = s.strip("_") or default
    return s[:60]

SORTABLE = {
    "tesis_adi": Facility.tesis_adi, "il": Facility.il, "ilce": Facility.ilce,
    "tesis_turu": Facility.tesis_turu, "kaynak_turu": Facility.kaynak_turu,
    "kurulu_guc_mwe": Facility.kurulu_guc_mwe, "kurulu_guc_mwm": Facility.kurulu_guc_mwm,
    "lisans_no": License.lisans_no, "unvan": License.unvan,
    "baslangic_tarihi": License.baslangic_tarihi, "bitis_tarihi": License.bitis_tarihi,
}


def _flatten(fac: Facility) -> dict:
    lic = fac.license
    return {
        "id": fac.id, "license_id": fac.license_id,
        "tesis_adi": fac.tesis_adi, "il": fac.il, "ilce": fac.ilce,
        "tesis_turu": fac.tesis_turu, "kaynak_turu": fac.kaynak_turu,
        "kurulu_guc_mwm": fac.kurulu_guc_mwm, "kurulu_guc_mwe": fac.kurulu_guc_mwe,
        "centroid_lat": fac.centroid_lat, "centroid_lng": fac.centroid_lng,
        "koordinat_alindi": fac.koordinat_alindi, "koordinat_durumu": fac.koordinat_durumu,
        "is_active": fac.is_active,
        "lisans_no": lic.lisans_no if lic else None,
        "lisans_tipi": lic.lisans_tipi if lic else None,
        "unvan": lic.unvan if lic else None,
        "lisans_durumu": lic.lisans_durumu if lic else None,
        "baslangic_tarihi": lic.baslangic_tarihi if lic else None,
        "bitis_tarihi": lic.bitis_tarihi if lic else None,
    }


def _apply_filters(q, *, il, ilce, kaynak_turu, tesis_turu, lisans_durumu,
                   search, only_with_coords, only_active, lisans_tipi=None):
    if lisans_tipi in ("onlisan", "uretim"):
        q = q.filter(License.lisans_tipi == lisans_tipi)
    if only_active:
        q = q.filter(Facility.is_active.is_(True))
    if il:
        q = q.filter(Facility.il == il)
    if ilce:
        q = q.filter(Facility.ilce == ilce)
    if kaynak_turu:
        q = q.filter(Facility.kaynak_turu == kaynak_turu)
    if tesis_turu:
        q = q.filter(Facility.tesis_turu == tesis_turu)
    if lisans_durumu:
        q = q.filter(License.lisans_durumu == lisans_durumu)
    if only_with_coords:
        q = q.filter(Facility.centroid_lat.isnot(None))
    if search:
        # Turkce-duyarli: iki tarafi da ASCII-kucuk'e katla -> "degirmen" => "DEĞİRMEN"
        term = f"%{_fold_py(search)}%"
        q = q.filter(or_(
            _fold_sql(Facility.tesis_adi).like(term),
            _fold_sql(License.unvan).like(term),
            _fold_sql(License.lisans_no).like(term),
            _fold_sql(Facility.il).like(term),
            _fold_sql(Facility.ilce).like(term)))
    return q


@router.get("", response_model=FacilityPage)
def list_facilities(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    il: Optional[str] = None,
    ilce: Optional[str] = None,
    kaynak_turu: Optional[str] = None,
    tesis_turu: Optional[str] = None,
    lisans_durumu: Optional[str] = None,
    lisans_tipi: Optional[str] = None,
    search: Optional[str] = None,
    only_with_coords: bool = False,
    only_active: bool = True,
    sort_by: str = "tesis_adi",
    sort_dir: str = "asc",
):
    base = db.query(Facility).join(License, Facility.license_id == License.id,
                                   isouter=True).options(joinedload(Facility.license))
    base = _apply_filters(
        base, il=il, ilce=ilce, kaynak_turu=kaynak_turu, tesis_turu=tesis_turu,
        lisans_durumu=lisans_durumu, search=search,
        only_with_coords=only_with_coords, only_active=only_active, lisans_tipi=lisans_tipi)

    total = base.count()
    col = SORTABLE.get(sort_by, Facility.tesis_adi)
    col = col.desc() if sort_dir == "desc" else col.asc()
    rows = base.order_by(col).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_flatten(r) for r in rows]}


@router.get("/filters")
def filter_options(db: Session = Depends(get_db)):
    def distinct(col):
        return [r[0] for r in db.query(col).filter(col.isnot(None), col != "")
                .distinct().order_by(col).all()]
    return {
        "il": distinct(Facility.il),
        "ilce": distinct(Facility.ilce),
        "kaynak_turu": distinct(Facility.kaynak_turu),
        "tesis_turu": distinct(Facility.tesis_turu),
        "lisans_durumu": distinct(License.lisans_durumu),
    }


# GeoJSON onbellegi: SIKISTIRILMIS (gzip) JSON bytes olarak saklanir. Agir poligon
# uretimi + JSON serialize + gzip HER istekte degil, ayni sorgu icin BIR KEZ yapilir;
# sonraki istekler hazir gzip paketi ANINDA doner. Veriyi DEGISTIRMEZ (tum noktalar
# birebir).
_GEOJSON_CACHE: dict = {}

# DISK onbellegi: ucretsiz sunucuda (throttle CPU) agir poligon paketi uretimi 13-22s
# surer ve worker her yeniden baslayinca BELLEK onbellegi silinir -> her seferinde
# bastan uretim (yavas/502). Cozum: filtresiz butun-veri gorunumlerinin gzip paketini
# DISKE yaz; sonraki isteklerde (yeniden baslasa bile) dosyadan ANINDA oku. Dosya adina
# DB imzasi (koordinatli tesis sayisi + max id) gomulur -> veri degisince otomatik
# gecersizlesir (eski dosya adi tutmaz -> yeniden uretilir). Onceden uretilip commit'lenen
# dosyalar deploy'da hazir gelir -> canli site ILK istekte bile aninda yanit verir.
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data",
                          "geojson_cache")
_DB_SIG = None


def _gzip_json(obj) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, 5)


def _db_sig(db: Session) -> str:
    """DB icerik imzasi (koordinatli-aktif tesis sayisi + max id). Salt-okunur sunucuda
    surec omru boyunca sabit -> bir kez hesaplanip saklanir."""
    global _DB_SIG
    if _DB_SIG is None:
        n = (db.query(func.count(Facility.id))
             .filter(Facility.centroid_lat.isnot(None)).scalar()) or 0
        mx = db.query(func.max(Facility.id)).scalar() or 0
        _DB_SIG = f"{n}-{mx}"
    return _DB_SIG


def _disk_file(cache_key, sig):
    """Sadece FILTRESIZ butun-veri gorunumleri (lisans_tipi + poligon disinda hepsi bos)
    icin disk yolu; aksi halde None (filtreli sorgular diske yazilmaz)."""
    lisans_tipi, il, ilce, kaynak_turu, tesis_turu, lisans_durumu, search, inc = cache_key
    if any((il, ilce, kaynak_turu, tesis_turu, lisans_durumu, search)):
        return None
    ad = f"{lisans_tipi or 'hepsi'}_{'poly' if inc else 'pts'}__{sig}.gz"
    return os.path.join(_CACHE_DIR, ad)


@router.get("/geojson")
def facilities_geojson(
    db: Session = Depends(get_db),
    il: Optional[str] = None, ilce: Optional[str] = None,
    kaynak_turu: Optional[str] = None, tesis_turu: Optional[str] = None,
    lisans_durumu: Optional[str] = None, lisans_tipi: Optional[str] = None,
    search: Optional[str] = None,
    include_polygons: bool = False,
):
    cache_key = (lisans_tipi, il, ilce, kaynak_turu, tesis_turu,
                 lisans_durumu, search, include_polygons)
    body = _GEOJSON_CACHE.get(cache_key)
    if body is not None:
        return Response(content=body, media_type="application/json",
                        headers={"Content-Encoding": "gzip"})

    # DISK onbellegi: filtresiz butun-veri gorunumu ise (yeniden baslamaya dayanikli)
    disk = _disk_file(cache_key, _db_sig(db))
    if disk and os.path.exists(disk):
        try:
            with open(disk, "rb") as fh:
                body = fh.read()
            if len(_GEOJSON_CACHE) < 100:
                _GEOJSON_CACHE[cache_key] = body
            return Response(content=body, media_type="application/json",
                            headers={"Content-Encoding": "gzip"})
        except Exception:
            pass

    q = db.query(Facility).join(License, Facility.license_id == License.id,
                                isouter=True).options(joinedload(Facility.license))
    q = _apply_filters(q, il=il, ilce=ilce, kaynak_turu=kaynak_turu,
                       tesis_turu=tesis_turu, lisans_durumu=lisans_durumu,
                       search=search, only_with_coords=True, only_active=True,
                       lisans_tipi=lisans_tipi)
    features = []
    for f in q.all():
        props = _flatten(f)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [f.centroid_lng, f.centroid_lat]},
            "properties": props,
        })
        if include_polygons and f.polygon_wgs84:
            # polygon_wgs84 = halka listesi; her halka ayri poligon (dogru sekil)
            for ring_pts in f.polygon_wgs84:
                if not ring_pts or len(ring_pts) < 3:
                    continue
                ring = [[lng, lat] for lat, lng in ring_pts]
                ring.append(ring[0])
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"id": f.id, "tesis_adi": f.tesis_adi,
                                   "kaynak_turu": f.kaynak_turu, "_is_polygon": True,
                                   "lisans_tipi": f.license.lisans_tipi if f.license else None},
                })
        # TURBIN noktalari: poligon DEGIL; her biri ayri isaret (Point + _is_turbine)
        if f.turbine_points:
            for i, pt in enumerate(f.turbine_points, start=1):
                if not pt or len(pt) < 2:
                    continue
                lat, lng = pt[0], pt[1]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "properties": {"id": f.id, "tesis_adi": f.tesis_adi,
                                   "kaynak_turu": f.kaynak_turu,
                                   "_is_turbine": True, "turbin_no": i},
                })
    body = _gzip_json({"type": "FeatureCollection", "features": features})
    if len(_GEOJSON_CACHE) < 100:      # sinirsiz buyumeyi engelle
        _GEOJSON_CACHE[cache_key] = body
    # Filtresiz butun-veri gorunumunu diske de yaz (ayni deploy icinde yeniden
    # baslamaya dayanikli; commit'lenirse deploy'da hazir gelir).
    if disk:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            tmp = disk + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(body)
            os.replace(tmp, disk)
        except Exception:
            pass
    return Response(content=body, media_type="application/json",
                    headers={"Content-Encoding": "gzip"})


@router.get("/export.csv")
def export_csv(
    db: Session = Depends(get_db),
    il: Optional[str] = None, ilce: Optional[str] = None,
    kaynak_turu: Optional[str] = None, tesis_turu: Optional[str] = None,
    lisans_durumu: Optional[str] = None, lisans_tipi: Optional[str] = None,
    search: Optional[str] = None, only_with_coords: bool = False,
):
    q = db.query(Facility).join(License, Facility.license_id == License.id,
                                isouter=True).options(joinedload(Facility.license))
    q = _apply_filters(q, il=il, ilce=ilce, kaynak_turu=kaynak_turu,
                       tesis_turu=tesis_turu, lisans_durumu=lisans_durumu,
                       search=search, only_with_coords=only_with_coords, only_active=True,
                       lisans_tipi=lisans_tipi)
    cols = ["lisans_no", "unvan", "lisans_durumu", "tesis_adi", "il", "ilce",
            "tesis_turu", "kaynak_turu", "kurulu_guc_mwm", "kurulu_guc_mwe",
            "baslangic_tarihi", "bitis_tarihi", "centroid_lat", "centroid_lng",
            "koordinat_durumu"]
    buf = io.StringIO()
    buf.write("﻿")  # Excel UTF-8 BOM
    w = csv.writer(buf, delimiter=";")
    w.writerow(cols)
    for f in q.order_by(Facility.tesis_adi).all():
        d = _flatten(f)
        w.writerow([d.get(c, "") if d.get(c) is not None else "" for c in cols])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tesisler.csv"})


@router.get("/{fac_id}", response_model=FacilityDetail)
def facility_detail(fac_id: int, db: Session = Depends(get_db)):
    f = db.query(Facility).options(joinedload(Facility.license)).get(fac_id)
    if not f:
        raise HTTPException(404, "Tesis bulunamadi")
    d = _flatten(f)
    d.update({"dilim_meridyeni": f.dilim_meridyeni, "polygon_wgs84": f.polygon_wgs84,
              "ham_koordinat_tm3": f.ham_koordinat_tm3,
              "isletme_kapasite_mwm": f.isletme_kapasite_mwm,
              "isletme_kapasite_mwe": f.isletme_kapasite_mwe})
    return d


@router.get("/{fac_id}/coordinates")
def facility_coordinates(fac_id: int, db: Session = Depends(get_db)):
    """TM3 (E/N + dilim) ve WGS84 (lat/lng) tum poligon noktalari, CSV."""
    f = db.query(Facility).options(joinedload(Facility.license)).get(fac_id)
    if not f:
        raise HTTPException(404, "Tesis bulunamadi")
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Ad", "Dilim", "E", "N", "lat", "lng"])
    for p in (f.ham_koordinat_tm3 or []):
        lat = lng = None
        if p.get("meridian") is not None and p.get("E") is not None and p.get("N") is not None:
            lat, lng = tm_to_wgs84(p["meridian"], p["E"], p["N"])
        w.writerow([p.get("ad"), p.get("meridian"), p.get("E"), p.get("N"), lat, lng])
    fname = "koordinat_" + _safe_filename(f.tesis_adi or str(fac_id)) + ".csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/{fac_id}/kmz")
def facility_kmz(fac_id: int, db: Session = Depends(get_db)):
    f = db.query(Facility).options(joinedload(Facility.license)).get(fac_id)
    if not f:
        raise HTTPException(404, "Tesis bulunamadi")
    data = build_kmz([f], doc_name=f.tesis_adi or f"Tesis {fac_id}")
    fname = _safe_filename(f.tesis_adi or str(fac_id)) + ".kmz"
    return StreamingResponse(
        io.BytesIO(data), media_type="application/vnd.google-earth.kmz",
        headers={"Content-Disposition": f"attachment; filename={fname}"})


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:          # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # 39,5 -> 39.5
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_pts(rows):
    """[{label,v1,v2}, ...] -> temiz [{ad,a,b}] (v1/v2 sayiya cevrilmis)."""
    out = []
    for r in rows or []:
        a = _to_float(r.get("v1"))
        b = _to_float(r.get("v2"))
        if a is None or b is None:
            continue
        out.append({"ad": str(r.get("label") or "").strip(), "a": a, "b": b})
    return out


@router.post("/convert")
def convert_coords(payload: dict):
    """Manuel koordinatlari WGS84'e cevir + poligon halkalari / turbin noktalari kur.
    KAYDETMEZ (veritabanina yazmaz) - sonuc yalnizca kullanicinin KENDI tarayicisinda
    haritada gostermesi + localStorage'da saklamasi icindir. Bu yuzden auth gerekmez,
    canli sitede herkese acik olabilir; kimse baskasinin ekledigini gormez.
    coord_type: 'wgs84' (a=enlem,b=boylam) veya 'tm' (a=E,b=N + dilim)."""
    ctype = "tm" if payload.get("coord_type") == "tm" else "wgs84"
    dilim = payload.get("dilim")
    try:
        dilim = int(dilim) if dilim not in (None, "") else None
    except (ValueError, TypeError):
        dilim = None
    if ctype == "tm" and not dilim:
        raise HTTPException(400, "TM/UTM icin dilim (meridyen) secilmeli")

    poly = _parse_pts(payload.get("polygon"))
    turb = _parse_pts(payload.get("turbine"))
    if not poly and not turb:
        raise HTTPException(400, "En az bir poligon ya da turbin noktasi gerekli")

    # --- WGS84'e cevir + halka/nokta kur (DB'ye DOKUNMAZ) ---
    if ctype == "tm":
        raw = [{"ad": p["ad"], "meridian": dilim, "E": p["a"], "N": p["b"]} for p in poly]
        res = process_polygon(raw) if raw else {"polygon_wgs84": None}
        rings = res.get("polygon_wgs84")
        turb_wgs = [[round(la, 6), round(ln, 6)]
                    for la, ln in (tm_to_wgs84(dilim, t["a"], t["b"]) for t in turb)]
    else:  # wgs84: a=enlem, b=boylam
        rings = build_rings_latlng([{"ad": p["ad"], "lat": p["a"], "lng": p["b"]} for p in poly])
        turb_wgs = [[round(t["a"], 6), round(t["b"], 6)] for t in turb]

    # merkez: once poligon alan-merkezi, yoksa turbin ortalamasi
    clat = clng = None
    if rings:
        clat, clng = area_centroid(rings)
    elif turb_wgs:
        clat = sum(t[0] for t in turb_wgs) / len(turb_wgs)
        clng = sum(t[1] for t in turb_wgs) / len(turb_wgs)
    if clat is None:
        raise HTTPException(400, "Gecerli koordinat cikmadi (degerleri/format'i kontrol edin)")

    tumu = [pt for r in (rings or []) for pt in r] + (turb_wgs or [])
    supheli = not all(in_turkey(la, ln) for la, ln in tumu)
    return {
        "polygon_wgs84": rings or None,
        "turbine_points": turb_wgs or None,
        "centroid": [round(clat, 6), round(clng, 6)],
        "durum": "supheli" if supheli else "ok",
    }
