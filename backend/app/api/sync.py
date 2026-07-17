"""Senkron API'si: baslat / durum / durdur / calisma gecmisi."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ScrapeRun
from ..schemas import ScrapeRunOut
from .. import sync_manager

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/start")
def start(resume: bool = True, lisans_tipi: str = "onlisan", sadece_liste: bool = False):
    return sync_manager.start_sync(resume=resume, lisans_tipi=lisans_tipi,
                                   sadece_liste=sadece_liste)


@router.post("/stop")
def stop():
    sync_manager.request_stop()
    return {"stopping": True}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    snap = sync_manager.STATE.snapshot()
    run = None
    if snap["run_id"]:
        run = db.query(ScrapeRun).get(snap["run_id"])
    return {
        "running": snap["running"], "durum": snap["durum"],
        "message": snap["message"], "lisans_tipi": snap.get("lisans_tipi", "onlisan"),
        "run": ScrapeRunOut.model_validate(run).model_dump() if run else None,
    }


@router.get("/runs")
def runs(db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(limit).all()
    return [ScrapeRunOut.model_validate(r).model_dump() for r in rows]


@router.get("/runs/{run_id}/log")
def run_log(run_id: int, db: Session = Depends(get_db)):
    r = db.query(ScrapeRun).get(run_id)
    return {"id": run_id, "log": r.log_text if r else "", "durum": r.durum if r else None}


@router.get("/stats")
def stats(db: Session = Depends(get_db), lisans_tipi: str | None = None):
    from ..models import Facility, License
    lq = db.query(License).filter(License.is_active.is_(True))
    fq = db.query(Facility).join(License, Facility.license_id == License.id).filter(
        Facility.is_active.is_(True))
    cq = fq.filter(Facility.centroid_lat.isnot(None))
    if lisans_tipi in ("onlisan", "uretim"):
        lq = lq.filter(License.lisans_tipi == lisans_tipi)
        fq = fq.filter(License.lisans_tipi == lisans_tipi)
        cq = cq.filter(License.lisans_tipi == lisans_tipi)
    return {
        "licenses": lq.count(),
        "facilities": fq.count(),
        "with_coords": cq.count(),
        # her iki tip icin ayri sayac (arayuz rozetleri)
        "by_tipi": {
            t: db.query(Facility).join(License, Facility.license_id == License.id).filter(
                Facility.is_active.is_(True), License.lisans_tipi == t).count()
            for t in ("onlisan", "uretim")
        },
    }
