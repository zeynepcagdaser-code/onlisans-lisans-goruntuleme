"""Tesis API'si: filtre + sayfalama + GeoJSON + KMZ + koordinat/CSV indirme."""
import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..coords import tm_to_wgs84
from ..database import get_db
from ..kmz import build_kmz
from ..models import Facility, License
from ..schemas import FacilityDetail, FacilityOut, FacilityPage

router = APIRouter(prefix="/api/facilities", tags=["facilities"])

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


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
        like = f"%{search}%"
        q = q.filter(or_(
            Facility.tesis_adi.ilike(like), License.unvan.ilike(like),
            License.lisans_no.ilike(like), Facility.il.ilike(like),
            Facility.ilce.ilike(like)))
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


@router.get("/geojson")
def facilities_geojson(
    db: Session = Depends(get_db),
    il: Optional[str] = None, ilce: Optional[str] = None,
    kaynak_turu: Optional[str] = None, tesis_turu: Optional[str] = None,
    lisans_durumu: Optional[str] = None, lisans_tipi: Optional[str] = None,
    search: Optional[str] = None,
    include_polygons: bool = False,
):
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
                                   "kaynak_turu": f.kaynak_turu, "_is_polygon": True},
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
    return {"type": "FeatureCollection", "features": features}


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
