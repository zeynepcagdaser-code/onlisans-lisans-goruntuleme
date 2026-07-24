"""Tesis API'si: filtre + sayfalama + GeoJSON + KMZ + koordinat/CSV indirme."""
import csv
import gzip
import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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


def _kml_local(tag):
    return tag.split("}")[-1]        # namespace'siz etiket adi


def _kml_coords(text):
    """KML 'lon,lat,alt lon,lat,alt ...' -> [[lat,lng], ...] (WGS84)."""
    pts = []
    for tok in (text or "").replace("\n", " ").split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0]); lat = float(parts[1])
            except ValueError:
                continue
            pts.append([round(lat, 6), round(lon, 6)])
    return pts


def _child_coords(el):
    for c in el.iter():
        if _kml_local(c.tag) == "coordinates" and c.text and c.text.strip():
            return _kml_coords(c.text)
    return None


def _kml_color_to_css(c):
    """KML rengi 'aabbggrr' (alfa,mavi,yesil,kirmizi) -> (#rrggbb, opaklik 0..1).
    Kullanicinin KMZ'deki rengi KORUNSUN diye; gecersizse (None, None)."""
    if not c:
        return None, None
    c = c.strip().lstrip("#")
    try:
        if len(c) == 8:
            a = int(c[0:2], 16); b = int(c[2:4], 16); g = int(c[4:6], 16); r = int(c[6:8], 16)
            return f"#{r:02x}{g:02x}{b:02x}", round(a / 255, 2)
        if len(c) == 6:                      # rrggbb (nadiren)
            return "#" + c.lower(), 1.0
    except ValueError:
        pass
    return None, None


def _extract_style(style_el):
    """<Style> -> {stroke, fill, fillOpacity} (KML renkleri)."""
    out = {}
    for el in style_el.iter():
        ln = _kml_local(el.tag)
        if ln in ("LineStyle", "PolyStyle", "IconStyle"):
            for c in el:
                if _kml_local(c.tag) == "color" and c.text:
                    hexc, op = _kml_color_to_css(c.text)
                    if not hexc:
                        continue
                    if ln == "PolyStyle":
                        out["fill"] = hexc
                        if op is not None:
                            out["fillOpacity"] = op
                    else:                     # Line/Icon -> cizgi/nokta rengi
                        out["stroke"] = hexc
    return out


def _stylemap_normal(sm_el):
    """<StyleMap> -> 'normal' key'inin styleUrl'i (highlight degil)."""
    for pair in sm_el.iter():
        if _kml_local(pair.tag) != "Pair":
            continue
        k = u = None
        for c in pair:
            l = _kml_local(c.tag)
            if l == "key":
                k = (c.text or "").strip()
            elif l == "styleUrl":
                u = (c.text or "").strip()
        if k == "normal" and u:
            return u
    return None


_KNOWN_NS = {
    "gx": "http://www.google.com/kml/ext/2.2",
    "atom": "http://www.w3.org/2005/Atom",
    "kml": "http://www.opengis.net/kml/2.2",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def _kml_root(kml_bytes):
    """KML baytlarini DAYANIKLI parse et: BOM, bastaki bosluk, kodlama-bildirimi ve
    'unbound prefix' (tanimsiz namespace oneki, or. gx:/atom:) sorunlarina ragmen."""
    if kml_bytes[:3] == b"\xef\xbb\xbf":          # UTF-8 BOM
        kml_bytes = kml_bytes[3:]
    kml_bytes = kml_bytes.lstrip()
    try:
        return ET.fromstring(kml_bytes)
    except ET.ParseError:
        pass
    # metne cevir + XML bildirimini at (Unicode+encoding catismasini onler)
    text = kml_bytes.decode("utf-8", "ignore")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1).lstrip()
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        pass
    # 'unbound prefix': kullanilan ama tanimsiz tum onekleri KOK etikete xmlns ekle
    used = (set(re.findall(r"</?([A-Za-z_][\w.\-]*):", text))
            | set(re.findall(r"[\s\"']([A-Za-z_][\w.\-]*):[\w.\-]+\s*=", text)))
    declared = set(re.findall(r"xmlns:([\w.\-]+)\s*=", text))
    # 'xmlns' ve 'xml' REZERVE oneklerdir; xmlns:X= yazimindan yanlislikla 'xmlns'
    # yakalanabilir -> onlari asla enjekte etme (aksi halde 'reserved prefix' hatasi).
    missing = [p for p in (used - declared) if p not in ("xml", "xmlns")]
    if missing:
        inject = "".join(
            f' xmlns:{p}="{_KNOWN_NS.get(p, "http://unknown.invalid/" + p)}"'
            for p in missing)
        # ilk gercek eleman (kok, or. <kml ...>) ac etiketine enjekte et
        text = re.sub(r"<([A-Za-z_][\w.\-]*)(\s|>)",
                      lambda m: f"<{m.group(1)}{inject}{m.group(2)}", text, count=1)
    return ET.fromstring(text)


def _parse_kml_regex(kml_bytes):
    """SON CARE: XML hic parse edilemezse (cok bozuk KML) koordinatlari duz REGEX
    ile cek. Renk/stil kaybolur ama sekiller yine de haritaya gelir."""
    text = kml_bytes.decode("utf-8", "ignore")
    shapes = []
    for m in re.finditer(r"<Point\b.*?<coordinates>(.*?)</coordinates>", text, re.S | re.I):
        p = _kml_coords(m.group(1))
        if p:
            shapes.append({"kind": "point", "coord": p[0], "color": None, "label": None})
    for m in re.finditer(r"<LineString\b.*?<coordinates>(.*?)</coordinates>", text, re.S | re.I):
        p = _kml_coords(m.group(1))
        if len(p) >= 2:
            shapes.append({"kind": "line", "coords": p, "stroke": None, "label": None})
    for m in re.finditer(r"<Polygon\b(.*?)</Polygon>", text, re.S | re.I):
        rings = []
        for cm in re.finditer(r"<coordinates>(.*?)</coordinates>", m.group(1), re.S | re.I):
            r = _kml_coords(cm.group(1))
            if len(r) >= 3:
                rings.append(r)
        if rings:
            shapes.append({"kind": "polygon", "rings": rings, "stroke": None,
                           "fill": None, "fillOpacity": None, "label": None})
    nm = re.search(r"<name>(.*?)</name>", text, re.S | re.I)
    return (nm.group(1).strip() if nm else None), shapes


def _parse_kml(kml_bytes):
    """KML -> (isim, sekil-listesi). Her sekil KENDI rengini tasir (KMZ'deki gibi).
    sekil = {kind:'polygon'|'line'|'point', ...geometri..., stroke/fill/fillOpacity}."""
    try:
        root = _kml_root(kml_bytes)
    except Exception:
        return _parse_kml_regex(kml_bytes)      # XML parse edilemedi -> son care
    styles, stylemaps = {}, {}
    for el in root.iter():
        ln = _kml_local(el.tag)
        if ln == "Style" and el.get("id"):
            styles["#" + el.get("id")] = _extract_style(el)
        elif ln == "StyleMap" and el.get("id"):
            n = _stylemap_normal(el)
            if n:
                stylemaps["#" + el.get("id")] = n

    def resolve(url):
        seen = set()
        while url in stylemaps and url not in seen:
            seen.add(url); url = stylemaps[url]
        return styles.get(url, {})

    name = None
    shapes = []
    for pm in root.iter():
        if _kml_local(pm.tag) != "Placemark":
            continue
        pmname, style = None, {}
        for ch in pm:
            l = _kml_local(ch.tag)
            if l == "name" and ch.text and ch.text.strip():
                pmname = ch.text.strip()
            elif l == "styleUrl" and ch.text:
                style = resolve(ch.text.strip())
            elif l == "Style":
                style = _extract_style(ch)
        if name is None and pmname:
            name = pmname
        stroke = style.get("stroke")
        fill = style.get("fill")
        fopac = style.get("fillOpacity")
        for geo in pm.iter():
            gl = _kml_local(geo.tag)
            if gl == "Polygon":
                rings = []
                for lr in geo.iter():
                    if _kml_local(lr.tag) == "LinearRing":
                        c = _child_coords(lr)
                        if c and len(c) >= 3:
                            rings.append(c)
                if rings:
                    shapes.append({"kind": "polygon", "rings": rings,
                                   "stroke": stroke or fill, "fill": fill or stroke,
                                   "fillOpacity": fopac, "label": pmname})
            elif gl == "LineString":
                c = _child_coords(geo)
                if c and len(c) >= 2:
                    shapes.append({"kind": "line", "coords": c,
                                   "stroke": stroke or fill, "label": pmname})
            elif gl == "Point":
                c = _child_coords(geo)
                if c:
                    shapes.append({"kind": "point", "coord": c[0],
                                   "color": stroke or fill, "label": pmname})
    return name, shapes


def _polygon_area_ha(rings):
    """WGS84 halka listesinin alanini HEKTAR olarak (UTM'e projelendirip shoelace;
    ilk halka dis sinir, digerleri delik)."""
    if not rings or len(rings[0]) < 3:
        return None
    from pyproj import Transformer
    outer = rings[0]
    lon0 = sum(p[1] for p in outer) / len(outer)
    lat0 = sum(p[0] for p in outer) / len(outer)
    zone = int((lon0 + 180) / 6) + 1
    epsg = (32600 if lat0 >= 0 else 32700) + zone
    tf = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    def shoelace(ring):
        xy = [tf.transform(p[1], p[0]) for p in ring]
        a = 0.0
        for i in range(len(xy)):
            x0, y0 = xy[i]
            x1, y1 = xy[(i + 1) % len(xy)]
            a += x0 * y1 - x1 * y0
        return abs(a) / 2

    try:
        area = shoelace(outer) - sum(shoelace(r) for r in rings[1:] if len(r) >= 3)
        return round(area / 10000.0, 1)
    except Exception:
        return None


def _kml_tree(kml_bytes):
    """KML -> (dokuman_adi, agac). Klasor hiyerarsisini KORUR (Google Earth 'Yerler').
    dugum: {type:'folder',name,children} | {type:'placemark',name,shapes,area_ha}."""
    root = _kml_root(kml_bytes)
    styles, stylemaps = {}, {}
    for el in root.iter():
        ln = _kml_local(el.tag)
        if ln == "Style" and el.get("id"):
            styles["#" + el.get("id")] = _extract_style(el)
        elif ln == "StyleMap" and el.get("id"):
            n = _stylemap_normal(el)
            if n:
                stylemaps["#" + el.get("id")] = n

    def resolve(url):
        seen = set()
        while url in stylemaps and url not in seen:
            seen.add(url); url = stylemaps[url]
        return styles.get(url, {})

    def name_of(el):
        for ch in el:
            if _kml_local(ch.tag) == "name" and ch.text and ch.text.strip():
                return ch.text.strip()
        return None

    def pm_shapes(pm):
        style = {}
        for ch in pm:
            l = _kml_local(ch.tag)
            if l == "styleUrl" and ch.text:
                style = resolve(ch.text.strip())
            elif l == "Style":
                style = _extract_style(ch)
        stroke, fill, fopac = style.get("stroke"), style.get("fill"), style.get("fillOpacity")
        out = []
        for geo in pm.iter():
            gl = _kml_local(geo.tag)
            if gl == "Polygon":
                rings = []
                for lr in geo.iter():
                    if _kml_local(lr.tag) == "LinearRing":
                        c = _child_coords(lr)
                        if c and len(c) >= 3:
                            rings.append(c)
                if rings:
                    out.append({"kind": "polygon", "rings": rings, "stroke": stroke or fill,
                                "fill": fill or stroke, "fillOpacity": fopac})
            elif gl == "LineString":
                c = _child_coords(geo)
                if c and len(c) >= 2:
                    out.append({"kind": "line", "coords": c, "stroke": stroke or fill})
            elif gl == "Point":
                c = _child_coords(geo)
                if c:
                    out.append({"kind": "point", "coord": c[0], "color": stroke or fill})
        return out

    def walk(el):
        nodes = []
        for ch in el:
            l = _kml_local(ch.tag)
            if l in ("Folder", "Document"):
                nodes.append({"type": "folder", "name": name_of(ch) or l, "children": walk(ch)})
            elif l == "Placemark":
                shp = pm_shapes(ch)
                if not shp:
                    continue
                area = None
                for s in shp:
                    if s["kind"] == "polygon":
                        a = _polygon_area_ha(s["rings"])
                        if a:
                            area = round((area or 0) + a, 1)
                nodes.append({"type": "placemark", "name": name_of(ch) or "(isimsiz)",
                              "shapes": shp, "area_ha": area})
        return nodes

    return name_of(root), walk(root)


@router.post("/import-kmz")
async def import_kmz(file: UploadFile = File(...)):
    """KMZ/KML dosyasini ayristir -> WGS84 halka/nokta doner. KAYDETMEZ (yalnizca
    kullanicinin kendi haritasinda gostermesi icin; /convert ile ayni mantik)."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Bos dosya")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "Dosya cok buyuk (>25MB)")
    try:
        if data[:2] == b"PK":                       # ZIP (KMZ) imzasi
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
                if not kmls:
                    raise HTTPException(400, "KMZ icinde .kml bulunamadi")
                # doc.kml varsa onu tercih et (ana dosya); yoksa ilk .kml
                kmls.sort(key=lambda n: (not n.lower().endswith("doc.kml"), n.lower()))
                kml_bytes = z.read(kmls[0])
        else:                                        # duz KML (xml)
            kml_bytes = data
        try:
            doc_name, tree = _kml_tree(kml_bytes)     # klasor agacini KORU
        except Exception:
            # XML hic parse edilemedi -> duz regex, tek duz liste
            nm, flat = _parse_kml_regex(kml_bytes)
            tree = [{"type": "placemark", "name": (s.get("label") or "(sekil)"),
                     "shapes": [s],
                     "area_ha": (_polygon_area_ha(s["rings"]) if s["kind"] == "polygon" else None)}
                    for s in flat]
            doc_name = nm
    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(400, "KMZ dosyasi bozuk (gecerli bir zip degil)")
    except Exception as e:
        raise HTTPException(400, f"KMZ/KML okunamadi ({type(e).__name__}): {str(e)[:150]}")

    allpts = []

    def _collect(nodes):
        for n in nodes:
            if n["type"] == "folder":
                _collect(n["children"])
            else:
                for s in n["shapes"]:
                    if s["kind"] == "polygon":
                        allpts.extend(p for r in s["rings"] for p in r)
                    elif s["kind"] == "line":
                        allpts.extend(s["coords"])
                    elif s["kind"] == "point":
                        allpts.append(s["coord"])
    _collect(tree)
    if not allpts:
        raise HTTPException(400, "Dosyada koordinat (poligon/cizgi/nokta) bulunamadi")

    clat = sum(p[0] for p in allpts) / len(allpts)
    clng = sum(p[1] for p in allpts) / len(allpts)
    supheli = not all(in_turkey(la, ln) for la, ln in allpts)
    return {
        "name": doc_name,
        "tree": tree,                                # Google Earth 'Yerler' agaci
        "centroid": [round(clat, 6), round(clng, 6)],
        "durum": "supheli" if supheli else "ok",
    }


# ---------- Cizim DISA AKTARMA (KMZ / KML / GeoJSON / DXF) ----------
def _xml_esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _kml_coord_str(coords):
    """GeoJSON [[lng,lat],...] -> KML 'lng,lat,0 ...'."""
    return " ".join(f"{c[0]},{c[1]},0" for c in coords if len(c) >= 2)


def _kml_rings(rings):
    out = []
    for i, r in enumerate(rings):
        tag = "outerBoundaryIs" if i == 0 else "innerBoundaryIs"
        out.append(f"<{tag}><LinearRing><coordinates>{_kml_coord_str(r)}"
                   f"</coordinates></LinearRing></{tag}>")
    return "".join(out)


def _geojson_to_kml(features, doc_name):
    p = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f"<name>{_xml_esc(doc_name)}</name>"]
    for f in features:
        g = f.get("geometry") or {}
        t = g.get("type"); c = g.get("coordinates")
        nm = _xml_esc((f.get("properties") or {}).get("name") or "")
        if not c:
            continue
        if t == "Point":
            p.append(f"<Placemark><name>{nm}</name><Point><coordinates>"
                     f"{c[0]},{c[1]},0</coordinates></Point></Placemark>")
        elif t == "LineString":
            p.append(f"<Placemark><name>{nm}</name><LineString><coordinates>"
                     f"{_kml_coord_str(c)}</coordinates></LineString></Placemark>")
        elif t == "Polygon":
            p.append(f"<Placemark><name>{nm}</name><Polygon>{_kml_rings(c)}</Polygon></Placemark>")
        elif t == "MultiPolygon":
            for poly in c:
                p.append(f"<Placemark><name>{nm}</name><Polygon>{_kml_rings(poly)}</Polygon></Placemark>")
    p.append("</Document></kml>")
    return "\n".join(p)


def _first_coord(features):
    for f in features:
        g = f.get("geometry") or {}
        c = g.get("coordinates"); t = g.get("type")
        if not c:
            continue
        if t == "Point":
            return c
        if t == "LineString":
            return c[0]
        if t == "Polygon":
            return c[0][0]
        if t == "MultiPolygon":
            return c[0][0][0]
    return None


def _geojson_to_dxf(features):
    """GeoJSON -> DXF (bytes). WGS84 -> UTM metre (CAD metre ister). Poligon/cizgi =
    LWPOLYLINE, nokta = POINT. Zone, ilk koordinatin boylamindan secilir."""
    import ezdxf                              # tembel import: yoksa sadece DXF cokmesin
    from pyproj import Transformer
    fc = _first_coord(features) or [35.0, 39.0]
    zone = int((fc[0] + 180) / 6) + 1
    epsg = (32600 if fc[1] >= 0 else 32700) + zone
    tf = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    def xy(c):
        x, y = tf.transform(c[0], c[1])
        return (round(x, 3), round(y, 3))

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for f in features:
        g = f.get("geometry") or {}
        t = g.get("type"); c = g.get("coordinates")
        if not c:
            continue
        if t == "Point":
            msp.add_point(xy(c))
        elif t == "LineString":
            msp.add_lwpolyline([xy(pt) for pt in c])
        elif t == "Polygon":
            for r in c:
                msp.add_lwpolyline([xy(pt) for pt in r], close=True)
        elif t == "MultiPolygon":
            for poly in c:
                for r in poly:
                    msp.add_lwpolyline([xy(pt) for pt in r], close=True)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8"), epsg


def _dl(body, filename, media):
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/export")
def export_shapes(payload: dict):
    """Kullanicinin CIZDIGI sekilleri (GeoJSON) secilen formata cevirip indir.
    format: kmz | kml | geojson | dxf. KAYDETMEZ (stateless)."""
    fmt = (payload.get("format") or "kml").lower()
    gj = payload.get("geojson") or {}
    features = gj.get("features") or []
    if not features:
        raise HTTPException(400, "Disa aktarilacak cizim yok")
    name = _safe_filename(payload.get("name") or "cizimlerim")
    doc_name = payload.get("name") or "cizimlerim"

    if fmt == "geojson":
        body = json.dumps(gj, ensure_ascii=False).encode("utf-8")
        return _dl(body, f"{name}.geojson", "application/geo+json")
    if fmt in ("kml", "kmz"):
        kml = _geojson_to_kml(features, doc_name)
        if fmt == "kml":
            return _dl(kml.encode("utf-8"), f"{name}.kml",
                       "application/vnd.google-earth.kml+xml")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", kml)
        return _dl(buf.getvalue(), f"{name}.kmz", "application/vnd.google-earth.kmz")
    if fmt == "dxf":
        try:
            data, _epsg = _geojson_to_dxf(features)
        except ImportError:
            raise HTTPException(500, "DXF icin 'ezdxf' gerekli (sunucuda kurulu degil)")
        return _dl(data, f"{name}.dxf", "application/dxf")
    raise HTTPException(400, "Bilinmeyen format")
