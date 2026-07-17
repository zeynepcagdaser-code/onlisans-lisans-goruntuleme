"""Veri modeli: licenses, facilities, scrape_runs."""
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text, JSON, Index)
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True)
    lisans_no = Column(String, unique=True, index=True, nullable=False)
    lisans_tipi = Column(String, default="onlisan", index=True)  # onlisan | uretim
    unvan = Column(String, index=True)
    iletisim_adresi = Column(String)
    telefon = Column(String)
    lisans_durumu = Column(String, index=True)
    iptal_tarihi = Column(String)
    iptal_aciklama = Column(String)
    baslangic_tarihi = Column(String)
    bitis_tarihi = Column(String)

    is_active = Column(Boolean, default=True, index=True)
    first_seen = Column(DateTime, default=_utcnow)
    last_seen = Column(DateTime, default=_utcnow)

    facilities = relationship(
        "Facility", back_populates="license",
        cascade="all, delete-orphan", lazy="selectin"
    )


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True)
    license_id = Column(Integer, ForeignKey("licenses.id"), index=True)

    tesis_adi = Column(String, index=True)
    il = Column(String, index=True)
    ilce = Column(String, index=True)
    tesis_turu = Column(String, index=True)
    kaynak_turu = Column(String, index=True)

    kurulu_guc_mwm = Column(Float)
    kurulu_guc_mwe = Column(Float)
    isletme_kapasite_mwm = Column(Float)
    isletme_kapasite_mwe = Column(Float)
    depolama_kapasite_mwh = Column(Float)
    depolama_kurulu_guc_mwe = Column(Float)
    isletme_depolama_kapasite_mwh = Column(Float)
    isletme_depolama_kurulu_guc_mwe = Column(Float)

    # Koordinat
    dilim_meridyeni = Column(Integer)                 # 27/30/33/36/39/42/45
    ham_koordinat_tm3 = Column(JSON)                  # [{ad,E,N}, ...] poligon noktalari
    polygon_wgs84 = Column(JSON)                      # [[lat,lng], ...] SAHA poligonu
    turbine_points = Column(JSON)                     # [[lat,lng], ...] TURBIN noktalari (poligon DEGIL, ayri isaret)
    centroid_lat = Column(Float)
    centroid_lng = Column(Float)
    first_point_lat = Column(Float)
    first_point_lng = Column(Float)
    koordinat_alindi = Column(Boolean, default=False, index=True)
    koordinat_durumu = Column(String, default="beklemede")  # ok | yok | supheli | hata | beklemede

    unique_hash = Column(String, unique=True, index=True)
    first_seen = Column(DateTime, default=_utcnow)
    last_seen = Column(DateTime, default=_utcnow)
    is_active = Column(Boolean, default=True, index=True)

    license = relationship("License", back_populates="facilities")


Index("ix_facility_kaynak_il", Facility.kaynak_turu, Facility.il)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime)
    durum = Column(String, default="running")  # running | waiting_captcha | success | partial | failed | skipped_no_captcha
    lisans_tipi = Column(String, default="onlisan", index=True)  # onlisan | uretim
    total_found = Column(Integer, default=0)
    new_added = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    coords_fetched = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    last_page = Column(Integer, default=0)      # resume icin
    log_text = Column(Text, default="")
