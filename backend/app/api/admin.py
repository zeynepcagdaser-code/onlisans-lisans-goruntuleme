"""Yonetim: sifreli 'Veri Yukle' — kullanici PC'sinde cektigi epdk.db'yi siteye
yukler; site DB'yi degistirip onbellegi yeniler. Boylece cekim LOKALDE kalir,
site sadece guncel veriyi gosterir (aylik akis)."""
import os
import shutil
import sqlite3
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import settings
from ..database import engine

router = APIRouter(prefix="/api/admin", tags=["admin"])

DB_PATH = settings.database_url.replace("sqlite:///", "")


def _check(pw: str) -> bool:
    return bool(pw) and pw == (settings.admin_password or "degistir-beni")


@router.post("/dogrula")
def dogrula(password: str = Form(...)):
    """Sifre dogru mu (admin sayfasi girisinde)."""
    if not _check(password):
        raise HTTPException(403, "Sifre yanlis")
    return {"ok": True}


@router.post("/upload-db")
async def upload_db(file: UploadFile = File(...), password: str = Form(...)):
    """Yeni epdk.db yukle -> dogrula -> yedekle -> degistir -> onbellek sifirla."""
    if not _check(password):
        raise HTTPException(403, "Sifre yanlis")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Bos dosya")
    if data[:16] != b"SQLite format 3\x00":
        raise HTTPException(400, "Bu bir SQLite veritabani (.db) degil")
    if len(data) > 300 * 1024 * 1024:
        raise HTTPException(400, "Dosya cok buyuk (>300MB)")

    tmp = DB_PATH + ".yeni"
    with open(tmp, "wb") as f:
        f.write(data)
    # --- dogrula: beklenen tablolar + tesis sayisi ---
    try:
        c = sqlite3.connect(tmp)
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "facilities" not in tabs or "licenses" not in tabs:
            c.close(); os.remove(tmp)
            raise HTTPException(400, "Beklenen tablolar (facilities/licenses) bulunamadi")
        nfac = c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
        ncoord = c.execute("SELECT COUNT(*) FROM facilities WHERE centroid_lat IS NOT NULL").fetchone()[0]
        c.close()
    except HTTPException:
        raise
    except Exception as e:
        try: os.remove(tmp)
        except Exception: pass
        raise HTTPException(400, f"Veritabani dogrulanamadi: {str(e)[:120]}")

    # --- motoru kapat + dosyayi guvenli degistir (yedekle) ---
    engine.dispose()
    if os.path.exists(DB_PATH):
        try: shutil.copy2(DB_PATH, DB_PATH + ".yedek")
        except Exception: pass
    last = None
    for _ in range(5):
        try:
            os.replace(tmp, DB_PATH)
            last = None
            break
        except Exception as e:
            last = e
            time.sleep(0.6)
    if last is not None:
        try: os.remove(tmp)
        except Exception: pass
        raise HTTPException(500, f"Veritabani degistirilemedi (dosya kullanimda olabilir): {str(last)[:120]}")

    # eski WAL/SHM'yi temizle (yeni DB tek dosya)
    for ext in ("-wal", "-shm"):
        p = DB_PATH + ext
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass

    # onbellegi sifirla -> site yeni veriyi gosterir
    try:
        from .facilities import reset_geojson_cache
        reset_geojson_cache()
    except Exception:
        pass

    return {"ok": True, "tesis_sayisi": nfac, "koordinatli": ncoord}
