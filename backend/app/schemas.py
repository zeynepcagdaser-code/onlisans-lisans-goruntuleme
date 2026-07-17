"""Pydantic semalari (API cikti)."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_id: int
    tesis_adi: Optional[str] = None
    il: Optional[str] = None
    ilce: Optional[str] = None
    tesis_turu: Optional[str] = None
    kaynak_turu: Optional[str] = None
    kurulu_guc_mwm: Optional[float] = None
    kurulu_guc_mwe: Optional[float] = None
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None
    koordinat_alindi: bool = False
    koordinat_durumu: Optional[str] = None
    is_active: bool = True

    # lisans alanlari (join ile duzlestirilir)
    lisans_no: Optional[str] = None
    lisans_tipi: Optional[str] = None
    unvan: Optional[str] = None
    lisans_durumu: Optional[str] = None
    baslangic_tarihi: Optional[str] = None
    bitis_tarihi: Optional[str] = None


class FacilityDetail(FacilityOut):
    dilim_meridyeni: Optional[int] = None
    polygon_wgs84: Optional[Any] = None
    ham_koordinat_tm3: Optional[Any] = None
    isletme_kapasite_mwm: Optional[float] = None
    isletme_kapasite_mwe: Optional[float] = None


class FacilityPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[FacilityOut]


class ScrapeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    durum: str
    total_found: int = 0
    new_added: int = 0
    updated: int = 0
    coords_fetched: int = 0
    errors: int = 0
    last_page: int = 0


class SyncStatus(BaseModel):
    running: bool
    durum: str
    message: str
    run: Optional[ScrapeRunOut] = None
