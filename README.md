# EPDK Ön-Lisans Görüntüleme Uygulaması

EPDK elektrik üretim **ön-lisans** kayıtlarını (yürürlükteki lisanslar + tesisler +
koordinatlar) çeker, SQLite'a yazar ve bir **tablo** + **harita** arayüzünde gösterir.
Tesis koordinatları Google Earth için **KMZ** ve **CSV** olarak indirilebilir.

> **Önemli — reCAPTCHA:** EPDK sorgu formunda Google reCAPTCHA v2 var ve sorgu için
> zorunlu. Tamamen otomatik (insansız) çekim **mümkün değil**. Ancak **tek bir insan
> çözümü tüm oturumu açıyor** — siz bir kez captcha'yı çözüp "Sorgula"ya basarsınız,
> geri kalan her şeyi (208 sayfa + koordinatlar + artımlı güncelleme) uygulama otomatik yapar.

---

## Kurulum (Windows, Node gerektirmez)

```powershell
cd backend
python -m pip install -r requirements.txt
python -m playwright install chromium        # tarayıcı motoru (bir kez)
copy .env.example .env                        # ayarları düzenleyin (opsiyonel)
```

- Python 3.11+ gerekir. `pyproj` (koordinat dönüşümü) ve `playwright` otomatik kurulur.
- Frontend **build gerektirmez** (statik HTML/JS; React/Leaflet CDN'den). Node/npm gerekmez.

## Çalıştırma

### A) Uygulama (arayüz + zamanlayıcı)
```powershell
cd backend
python -m uvicorn app.main:app --port 8000
```
Tarayıcıda aç: **http://127.0.0.1:8000**
- **Tablo** sayfası: filtre / arama / sıralama / sayfalama / CSV-Excel indirme.
- **Harita** sayfası (`/harita`): kümelenmiş işaretçiler, kaynak türüne göre renk + lejant,
  poligon katmanı, işaretçi kartında **⋮** menüsü → Koordinat (CSV) / KMZ indirme.
- Sağ üstteki **Senkronize Et** ile çekim başlatılır (aşağıya bakın).

### B) Sadece çekim (arayüzsüz, CLI)
```powershell
cd backend
python run_scrape.py                 # tam çekim (yarım kaldıysa kaldığı yerden devam)
python run_scrape.py --no-resume     # baştan
python run_scrape.py --max-pages 1   # hızlı test (ilk sayfa)
```

## Senkron (veri çekme) akışı

1. **Senkronize Et**'e bas (ya da `run_scrape.py`).
2. **Görünür bir Chrome penceresi açılır**; "Lisans Durumu = Yürürlükte" otomatik seçilir.
3. **Sen** pencerede **"Ben robot değilim"** kutusunu işaretle ve **"Sorgula"**ya bas.
4. Uygulama devralır: tüm sayfaları gezer, her tesisin koordinat popup'ını açıp **tüm
   poligon noktalarını** okur, TM3→WGS84 çevirir, SQLite'a yazar.
5. Durum sağ üstte canlı görünür (Captcha bekleniyor / Çekiliyor / Tamamlandı).

**İlk tam çekim ~1.5–3 saat** sürebilir (2.073 lisans; en pahalı adım koordinat popup'ı).
Sonraki çekimler **artımlı**dır: yalnızca yeni/değişen tesisler için koordinat çekilir.

### Otomatik zamanlama
`.env` içindeki `SYNC_HOUR=8 / SYNC_MINUTE=30` ile her gün 08:30'da (Europe/Istanbul)
senkron **tetiklenir** — tarayıcı açılır ve captcha çözmeniz beklenir. Çözmezseniz
(varsayılan 10 dk) çalışma "atlandı" olarak loglanır. Kapatmak için `SCHEDULER_ENABLED=false`.

## Koordinat formatı

EPDK koordinatları **Türkiye Ulusal TM (Transverse Mercator, 3-derece dilim)**
projeksiyonunda verir: `Dilim Orta Boylamı · E (Easting) · N (Northing)` (metre, virgül ondalık).
Her tesis bir **poligon** (köşe köşe). Uygulama:
- Tüm noktaları `ham_koordinat_tm3` (TM3) olarak saklar,
- WGS84'e çevirip `polygon_wgs84` + `centroid` (harita pini) hesaplar,
- Türkiye sınırı (lat 35–43, lng 25–45) dışındaysa `koordinat_durumu=supheli` işaretler.

**Datum:** Varsayılan `COORD_DATUM=wgs84` (keşifte doğrulandı). EPDK eski verisi ED50
olabilir; `.env`'de `COORD_DATUM=ed50` ile deneyip bilinen bir tesisle karşılaştırabilirsiniz
(fark tipik olarak metreler mertebesinde).

## Yapı

```
backend/
  app/
    config.py       # .env ayarları
    database.py     # SQLAlchemy (SQLite; PG'ye soyut)
    models.py       # licenses, facilities, scrape_runs
    coords.py       # TM3 -> WGS84 (pyproj)
    scraper.py      # Playwright human-in-the-loop scraper (sınırsız koordinat)
    sync_manager.py # orkestrasyon + artımlı upsert + resume + durum
    scheduler.py    # APScheduler 08:30
    kmz.py          # KML/KMZ (Polygon + centroid)
    api/            # facilities.py, sync.py
    main.py         # FastAPI + statik frontend servisi
  run_scrape.py     # CLI çekim
  .env.example
  requirements.txt
frontend/           # index.html (tablo), harita.html (harita), *.js, style.css
poc/                # keşif (referans; dokunulmadı)
```

## API (özet)

| Uç | Açıklama |
|---|---|
| `GET /api/facilities` | filtre + sıralama + sayfalama |
| `GET /api/facilities/filters` | dropdown değerleri (il/ilçe/kaynak/tesis/durum) |
| `GET /api/facilities/geojson` | haritada gösterilen koordinatlı tesisler (opsiyonel poligon) |
| `GET /api/facilities/export.csv` | filtreli tablo CSV/Excel |
| `GET /api/facilities/{id}/coordinates` | tesisin tüm TM3+WGS84 noktaları (CSV) |
| `GET /api/facilities/{id}/kmz` | tesis KMZ (Polygon + centroid) |
| `POST /api/sync/start` · `GET /api/sync/status` · `POST /api/sync/stop` | senkron kontrol |
| `GET /api/sync/runs` · `/runs/{id}/log` · `/stats` | çalışma geçmişi / log / istatistik |

## Notlar / bilinen davranışlar

- Koordinat popup'ında nadiren "execution context destroyed" yarışı olur → 3 kez retry ile ele alınır.
- Koordinatı olmayan tesisler `koordinat_durumu=yok`; hata olanlar `hata` (sonraki senkronda tekrar denenir).
- Artık listede olmayan lisans/tesis silinmez; `is_active=false` yapılır.
- Uzun çekimde oturum düşerse: durdurup tekrar başlatın; kaldığı sayfadan **devam** eder.
- Paralı captcha-çözme servisi **kullanılmaz** (maliyet + EPDK şartları).
```
