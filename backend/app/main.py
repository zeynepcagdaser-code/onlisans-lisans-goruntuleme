"""FastAPI uygulamasi: API + statik (build'siz) frontend servisi."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import BASE_DIR, settings
from .database import init_db
from .api import admin, facilities

FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Scraper/scheduler OPSIYONEL: bulut ortaminda Playwright/APScheduler kurulmaz
# (sadece goruntuleme). Import basarisizsa veri-cekme devre disi, gorsel calisir.
try:
    from .scheduler import shutdown_scheduler, start_scheduler
    from .api import sync as sync_api
    _SCRAPER_OK = True
except Exception:
    _SCRAPER_OK = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if _SCRAPER_OK:
        start_scheduler()
    yield
    if _SCRAPER_OK:
        shutdown_scheduler()


app = FastAPI(title="EPDK Ön-Lisans Görüntüleme", version="1.0", lifespan=lifespan)
# GZip: yanitlari SIKISTIRIR (veriyi DEGISTIRMEZ; tum poligon noktalari birebir
# korunur, sadece transfer kucuk paket -> hizli). 2.8MB JSON ~400KB'a iner.
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(facilities.router)
app.include_router(admin.router)          # sifreli 'Veri Yukle' (her ortamda)
if _SCRAPER_OK:
    app.include_router(sync_api.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- Build'siz frontend ----
if FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/harita")
    def harita():
        return FileResponse(str(FRONTEND_DIR / "harita.html"))

    # Admin sayfasi GIZLI adreste (config.admin_path / .env ADMIN_PATH). Menude link
    # YOK + adres gizli -> sadece adresi bilen (siz) ulasir. Ayrica sifreli.
    @app.get("/" + settings.admin_path.strip("/"))
    def yonetim():
        return FileResponse(str(FRONTEND_DIR / "admin.html"))

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
