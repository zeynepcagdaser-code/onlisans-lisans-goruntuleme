"""SQLAlchemy engine/session. SQLite varsayilan; DATABASE_URL ile PG'ye gecilebilir."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # FastAPI/APScheduler farkli thread'lerden erisebilir
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):
        # WAL: yazan (scraper) + okuyan (arayuz) es zamanli calisabilsin.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=8000")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite():
    """Hafif otomatik migration: eksik kolonlari ekle (SQLite)."""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(licenses)"))]
        if cols and "lisans_tipi" not in cols:
            conn.execute(text(
                "ALTER TABLE licenses ADD COLUMN lisans_tipi VARCHAR DEFAULT 'onlisan'"))
            conn.execute(text(
                "UPDATE licenses SET lisans_tipi='onlisan' WHERE lisans_tipi IS NULL"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_licenses_lisans_tipi ON licenses(lisans_tipi)"))
        rcols = [r[1] for r in conn.execute(text("PRAGMA table_info(scrape_runs)"))]
        if rcols and "lisans_tipi" not in rcols:
            conn.execute(text(
                "ALTER TABLE scrape_runs ADD COLUMN lisans_tipi VARCHAR DEFAULT 'onlisan'"))
            conn.execute(text(
                "UPDATE scrape_runs SET lisans_tipi='onlisan' WHERE lisans_tipi IS NULL"))


def init_db():
    from . import models  # noqa: F401  (modelleri kaydet)
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
