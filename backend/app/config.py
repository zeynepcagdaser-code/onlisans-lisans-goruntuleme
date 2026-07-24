"""Uygulama ayarlari (.env'den okunur)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Veritabani
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'epdk.db').as_posix()}"

    # Yonetim (admin 'Veri Yukle' sayfasi). GUVENLIK: canliya kurunca .env'de
    # ADMIN_PASSWORD'u MUTLAKA guclu bir sifreyle degistirin.
    admin_password: str = "degistir-beni"

    # Zamanlayici
    sync_hour: int = 8
    sync_minute: int = 30
    timezone: str = "Europe/Istanbul"
    scheduler_enabled: bool = True

    # Scraper
    headless: bool = False           # captcha icin normalde headed
    rows_per_page: int = 50          # rpp=50 -> daha az postback
    request_delay_ms: int = 400      # istekler arasi nezaket gecikmesi
    captcha_wait_timeout_s: int = 600  # kullanicinin captcha cozmesi icin bekleme (10 dk)
    max_pages: int = 0               # 0 = sinirsiz (tum sayfalar)

    # Koordinat
    coord_datum: str = "ed50"        # 'ed50' (EPDK verisi) | 'wgs84'
    coord_k0: float = 0.9996         # UTM 6-derece olcek faktoru (TM3 icin 1.0)
    # Turkiye sinir kontrolu
    tr_lat_min: float = 35.0
    tr_lat_max: float = 43.0
    tr_lng_min: float = 25.0
    tr_lng_max: float = 45.0

    # Hedef URL (onlisan varsayilan; uretim ikinci tip)
    epdk_url: str = (
        "https://lisans.epdk.gov.tr/epvys-web/faces/pages/lisans/"
        "elektrikUretimOnLisans/elektrikUretimOnLisansOzetSorgula.xhtml"
    )
    epdk_url_uretim: str = (
        "https://lisans.epdk.gov.tr/epvys-web/faces/pages/lisans/"
        "elektrikUretim/elektrikUretimOzetSorgula.xhtml"
    )

    def url_for(self, lisans_tipi: str) -> str:
        return self.epdk_url_uretim if lisans_tipi == "uretim" else self.epdk_url


settings = Settings()

# data/ klasorunu garanti et
(BASE_DIR / "data").mkdir(exist_ok=True)
