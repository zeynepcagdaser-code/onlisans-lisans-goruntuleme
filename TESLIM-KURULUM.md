# EPDK Lisans Görüntüleme — Kurulum ve Kullanım (Teslim Belgesi)

Bu uygulama EPDK önlisans/üretim-lisans tesislerini **harita ve tablo** olarak gösterir;
kullanıcılar KMZ/KML yükleyip çizim yapabilir, veriyi KMZ/KML/GeoJSON/DXF olarak indirebilir.

## Mimari (önemli)

```
[Şirket sunucusu]  energyai.selenkaenerji.com (ya da alt alan adı: harita.selenkaenerji.com)
     = GÖRÜNTÜLEME uygulaması (FastAPI + uvicorn). Sadece veriyi gösterir.
                 ▲
                 │  aylık: yeni epdk.db yüklenir (şifreli /yonetim sayfası)
                 │
[Kullanıcı PC]   = VERİ ÇEKME burada yapılır (EPDK captcha'sı insan tarafından çözülür).
```

- **Veri çekme sunucuda YAPILMAZ.** EPDK'nın captcha/WAF'ı insan gerektirir; bu yüzden çekim
  kullanıcının bilgisayarında (görünür tarayıcı) yapılır. Sunucu yalnızca **görüntüler.**
- Güncelleme **aylık** yeterli. Kullanıcı PC'de çeker → `/yonetim` sayfasından yeni DB'yi yükler.

---

## A) SUNUCUYA KURULUM (yönetici — bir kez)

Sunucunuz zaten Python/uvicorn çalıştırıyor. Bu uygulamayı ayrı bir port/alt alan adında yayınlayın.

**1. Dosyaları sunucuya kopyalayın** (repo: github.com/zeynepcagdaser-code/onlisans-lisans-goruntuleme).

**2. Bağımlılıklar** (Python 3.11+):
```bash
cd backend
pip install -r requirements-web.txt
```
> `requirements-web.txt` HAFİF sürümdür (Playwright YOK — sunucuda çekim yapılmaz, sadece görüntüleme).

**3. Yönetici şifresini AYARLAYIN** (GÜVENLİK — zorunlu):
`backend/.env` dosyası oluşturun:
```
ADMIN_PASSWORD=buraya-guclu-bir-sifre
```
> Ayarlamazsanız varsayılan `degistir-beni` olur — mutlaka değiştirin.

**4. Uygulamayı çalıştırın** (kalıcı servis olarak — systemd / IIS reverse-proxy / nssm):
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8100
```
Sonra ters proxy (nginx/IIS) ile `harita.selenkaenerji.com` → `127.0.0.1:8100` yönlendirin.

**5. Kalıcı disk:** `backend/data/epdk.db` sunucuda **kalıcı** bir dizinde olmalı (yüklenen veri
kaybolmasın diye). Konteyner kullanıyorsanız `backend/data` klasörünü volume yapın.

**Sayfalar:**
- `/` tablo · `/harita` harita · `/yonetim` **veri yükleme (şifreli)**

---

## B) AYLIK VERİ GÜNCELLEME (kullanıcı — kendi PC'sinde)

**1. Çekim (PC'de, bir kez kurulum):**
```bash
cd backend
pip install -r requirements.txt        # tam sürüm (Playwright dahil)
python -m playwright install chromium
```

**2. Her ay çekim:**
```bash
cd backend
python cek_ters.py            # üretim koordinatları (son sayfadan geriye)
# ya da lokal siteyi açıp "Senkronize Et" butonunu kullan
```
Açılan tarayıcıda **"Ben robot değilim" + Sorgula** → captcha'yı çöz, gerisi otomatik.
Sonuç `backend/data/epdk.db`'ye kaydedilir. Bitince kontrol noktası (checkpoint) için:
```bash
python -c "import sqlite3;c=sqlite3.connect('data/epdk.db');c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.execute('PRAGMA journal_mode=DELETE');c.commit()"
```

**3. Siteye yükle:**
- Tarayıcıda `https://harita.selenkaenerji.com/yonetim` aç → şifreyle gir
- `backend/data/epdk.db` dosyasını seç → **Yükle ve Yayınla**
- Site herkese güncel veriyi gösterir. ✓

---

## Notlar
- **Güvenlik:** `/yonetim` şifrelidir; `.env`'deki `ADMIN_PASSWORD`'u güçlü tutun. Sadece yükleme
  yapan kişi bilmeli.
- **Yedek:** Her yüklemede eski DB `epdk.db.yedek` olarak saklanır.
- **Veri değişmez:** Uygulama poligon sınırlarını birebir korur (basitleştirme yok); yanıtlar
  yalnızca sıkıştırılır (gzip).
- **Çekim yalnızca PC'de:** Sunucuda Playwright yoktur; "Senkronize Et" butonu yalnızca lokalde görünür.
