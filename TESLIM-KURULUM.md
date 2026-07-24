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

**3. Yönetici şifresini + gizli admin adresini AYARLAYIN** (GÜVENLİK — zorunlu):
`backend/.env` dosyası oluşturun:
```
ADMIN_PASSWORD=buraya-guclu-bir-sifre
ADMIN_PATH=gizli-veri-x7k2m
```
- **ADMIN_PASSWORD:** veri yükleme sayfasının şifresi. Ayarlamazsanız varsayılan `degistir-beni` olur — mutlaka değiştirin.
- **ADMIN_PATH:** veri yükleme sayfasının **gizli adresi**. Tahmin edilemez bir şey yapın
  (ör. `gizli-veri-x7k2m`). Böylece sayfa `harita.selenkaenerji.com/gizli-veri-x7k2m` adresinde
  olur; `/yonetim` yazan biri **404** görür (hiçbir şey bulamaz). Menüde de link yoktur.
  Bu adresi + şifreyi **sadece veri yükleyecek kişi** bilmeli.

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

## Otomatik güncelleme (opsiyonel — "push → canlı", Render gibi)

Kullanıcı repoya `git push` yapınca sitenin **kendiliğinden güncellenmesi** isteniyorsa
(Render'daki gibi), sunucuda şu yöntemlerden biri kurulur (IT tercih eder):

**Yöntem 1 — Zamanlı `git pull` (en basit, önerilen):**
Sunucuda küçük bir betik + zamanlanmış görev; birkaç dakikada bir repoyu kontrol eder,
değişiklik varsa çeker ve uygulamayı yeniden başlatır.

Linux (betik `guncelle.sh` + cron `*/5 * * * *`):
```bash
cd /opt/onlisans-lisans-goruntuleme
git fetch origin main
if ! git diff --quiet HEAD origin/main; then
  git pull
  pip install -r backend/requirements-web.txt   # bağımlılık değiştiyse
  systemctl restart epdk-harita                  # uygulamayı yeniden başlat
fi
```

Windows (Görev Zamanlayıcı + `guncelle.bat`, 5 dakikada bir):
```bat
cd C:\apps\onlisans-lisans-goruntuleme
git pull
nssm restart epdk-harita
```

**Yöntem 2 — GitHub Webhook (anında):**
GitHub, push olunca sunucudaki küçük bir uç noktaya haber verir; o da `git pull` + yeniden
başlatma yapar. Anında güncellenir ama biraz daha kurulum ister (webhook dinleyici).

> Not: Bu yöntemde **veri de** repo ile gider (kullanıcı `epdk.db`'yi commit + push eder).
> Ayrı `/yonetim` yüklemesine gerek kalmaz — kullanıcı her şeyi tek `git push` ile yayınlar.

## Lisans durumu seçimi (çekimde)

Varsayılan olarak **yalnızca "Yürürlükte"** lisanslar çekilir. Başka durum(lar) çekmek için
(çekimi yapan PC'de) `backend/.env` dosyasına ekleyin:
```
# Tek durum:
LISANS_DURUMU=Sona Ermiş
# ya da tüm durumlar (boş bırak):
LISANS_DURUMU=
```
Değerler EPDK menüsündeki metinle eşleşir (Yürürlükte / Sona Ermiş / İptal Edilmiş ...).
Ayrıca çekim sırasında açılan tarayıcıda **"Lisans Durumu" menüsünden elle de** seçebilirsiniz
(otomatik seçim başarısız olursa uyarı verir ve elle seçmenizi ister).

## Notlar
- **Güvenlik:** `/yonetim` şifrelidir; `.env`'deki `ADMIN_PASSWORD`'u güçlü tutun. Sadece yükleme
  yapan kişi bilmeli.
- **Yedek:** Her yüklemede eski DB `epdk.db.yedek` olarak saklanır.
- **Veri değişmez:** Uygulama poligon sınırlarını birebir korur (basitleştirme yok); yanıtlar
  yalnızca sıkıştırılır (gzip).
- **Çekim yalnızca PC'de:** Sunucuda Playwright yoktur; "Senkronize Et" butonu yalnızca lokalde görünür.
