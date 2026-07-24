# EPDK Lisans Görüntüleme — Proje Rehberi

Bu belge projenin **ne yaptığını (adım adım)** ve **nasıl teslim edileceğini** anlatır.
Teknik kurulum ayrıntıları için ayrıca `TESLIM-KURULUM.md`'ye bakın.

---

## 1. Proje nedir? (Tek cümle)

EPDK'daki elektrik **önlisans** ve **üretim lisansı** tesislerini; konumları, koordinatları ve
saha poligonlarıyla birlikte bir **harita + tablo** üzerinde gösteren; kullanıcının kendi
verilerini (KMZ/KML, elle koordinat, çizim) ekleyip indirebildiği bir web uygulaması.

## 2. Ne işe yarar?

- Tüm ruhsatlı üretim/önlisans tesislerini **tek haritada** görmek (rüzgar, güneş, HES, jeotermal…).
- Bir tesisin **koordinatını, saha sınırını (poligon), alanını** görmek/indirmek.
- Kendi projelerini (KMZ/KML) yükleyip EPDK verisiyle **aynı harita üzerinde karşılaştırmak**.
- Harita üzerinde **çizim yapıp** (poligon/yol/nokta) KMZ/DXF olarak **indirmek**.

---

## 3. Ekranlar ve özellikler (adım adım)

### 3.1 Harita ekranı (`/harita`)
- Türkiye haritası; her tesis renkli bir işaret (kaynak türüne göre renk).
- Yakınlaşınca işaretler tek tek ayrılır (kümeleme). Bir işarete tıklayınca **tesis kartı** açılır.
- **Zoom (+/−)** sağ-üstte.

### 3.2 Tablo ekranı (`/`)
- Aynı verinin liste hâli: unvan, lisans no, il/ilçe, kaynak, kurulu güç, tarihler.
- Arama + filtre + sayfalama; her satırdan koordinat/KMZ indirilebilir.

### 3.3 Önlisans / Lisans / Hepsi
- Üstteki 3 düğme: **Önlisans**, **Lisans (üretim)**, **Önlisans + Lisans (hepsi)**.
- "Hepsi" modunda ikisi birden gösterilir: **üretim poligonları YEŞİL, önlisans GRİ**.

### 3.4 Arama ve filtreler
- **Ara** kutusu: tesis adı / unvan / lisans no / il / ilçe içinde arar. **Türkçe duyarlıdır**
  (ör. "degirmen" yazınca "DEĞİRMEN"i bulur).
- **İl** ve **Tesis Türü** açılır menüleriyle daralt.

### 3.5 Poligonlar (saha sınırları) + alan
- "Poligonlar" kutusu işaretlenince tesislerin **saha sınırları** çizilir.
- Sınırlar EPDK verisinden **birebir** alınır (basitleştirme YOK).
- Çok-parçalı sahalar (birden çok blok) ayrı ayrı doğru çizilir.

### 3.6 Tesis kartı (kartın ⋮ menüsü)
- **📄 Koordinat İndir (CSV)** — tesisin tüm köşe koordinatları.
- **🌍 KMZ İndir** — Google Earth'te açılır.
- **🚫 Bu tesisi ekranımdan kaldır** — sadece senin ekranından gizler (bkz. 3.11).

### 3.7 ➕ Koordinat Ekle (üstteki yeşil düğme)
Kendi verini haritaya eklemenin iki yolu (ikisi de **sadece senin tarayıcında** kalır, sunucuya kaydedilmez):
- **📁 KMZ/KML yükle** — dosyanı seç, yükle. Şekiller **kendi renginde** gelir.
- **✏️ Manuel koordinat** — Excel'den yapıştır. Format seç: **WGS84** (enlem/boylam) veya
  **TM/UTM** (E/N + dilim). Poligon ve/veya türbin noktası girilebilir.

### 3.8 📂 Yerler paneli (KMZ klasör ağacı — Google Earth gibi)
- Bir KMZ yükleyince **sol tarafta** dosyanın **klasör ağacı** çıkar (ör. ULAŞTIRMA ALT YAPI, ORMAN…).
- Her öğe/klasör yanında **kutu** ile **göster/gizle** (klasörü kapatınca altındakiler de gizlenir).
- Poligonlarda **alan (ha)** yazar. Öğe yanındaki **◎** ile haritada oraya gidilir.

### 3.9 ✏️ Çizim araçları (üst-orta yatay çubuk)
- **📍 Yer işareti, ⬠ Poligon, 〰️ Yol, ▭ Dikdörtgen** çiz; **düzenle / taşı / sil**.
- Çizdiklerin tarayıcında saklanır (sayfa yenilense de kalır).

### 3.10 ⬇️ İndir (sağ tarafta)
- Çizdiğin şekilleri seçtiğin formatta indir: **KMZ, KML, GeoJSON, DXF (AutoCAD)**.
- DXF koordinatları CAD için **UTM metre**. (Gerçek .dwg sunucuda üretilemez; DXF'i AutoCAD
  doğrudan açar, tek tıkla "Farklı Kaydet → DWG" yapılır.)

### 3.11 🚫 Tesis gizle / geri getir
- Tesis kartından "ekranımdan kaldır" → tesis senin ekranından gizlenir.
- **Sol-altta** "Gizlenen (N)" panelinden tek tek ya da "hepsini geri getir".
- Tamamen kişisel; sunucudaki veriye dokunmaz.

### 3.12 🔄 Senkronize Et (VERİ ÇEKME — yalnızca lokal)
- Bu düğme **sadece senin bilgisayarında** görünür (canlı sitede gizli).
- Basınca görünür tarayıcı açılır; **captcha'yı sen çözersin**, gerisi otomatik EPDK'dan çeker.
- Önlisans/Lisans ayrı çekilir; **Lisans Durumu** seçilebilir (Yürürlükte / diğerleri / hepsi).

### 3.13 🔒 Yönetim — Veri Yükle (`/yonetim`)
- Şifreli sayfa. Bilgisayarında çektiğin güncel `epdk.db`'yi siteye yükler.
- Site DB'yi doğrular, eskisini yedekler, değiştirir → herkes güncel veriyi görür.
- **Aylık güncellemenin** yapıldığı yer.

---

## 4. Nasıl çalışıyor? (Mimari — basitçe)

| Parça | Ne yapar | Teknoloji |
|---|---|---|
| **Backend** | Veriyi sunar (API), sayfaları verir | Python + FastAPI + uvicorn |
| **Frontend** | Harita/tablo/çizim arayüzü | HTML/JS + Leaflet (build gerektirmez) |
| **Veritabanı** | Tesis + lisans + koordinatlar | SQLite (`backend/data/epdk.db`) |
| **Scraper** | EPDK'dan veri çeker (LOKAL) | Playwright (görünür tarayıcı + insan captcha) |

- Harita hızlı olsun diye poligonlar **gzip + disk önbelleğinde** tutulur (veri değişmez, sadece sıkışır).
- **Koordinat dönüşümü:** EPDK TM/UTM → WGS84 (pyproj, ED50 + UTM k0=0.9996), resmi KML ile ~0.14 m doğrulandı.

## 5. Veri nereden geliyor? (Çekim akışı)

```
EPDK sitesi ──(captcha'yı SEN çözersin, görünür tarayıcı)──> scraper ──> epdk.db (koordinatlar işlenir)
```
- EPDK'nın WAF/captcha'sı otomatik çekimi engeller → bu yüzden çekim **insanlı** ve **lokal**.
- Üretim koordinatları "ters çekim" ile tamamlandı (haritada ~1286 tesis; kalanların EPDK'da koordinatı yok).

## 6. Nasıl teslim edilir? (Adım adım)

**Sen (kullanıcı) → Yönetici:**
1. GitHub repo linkini ver: `github.com/zeynepcagdaser-code/onlisans-lisans-goruntuleme`
2. Şu iki belgeyi göster: **`PROJE-REHBERI.md`** (bu belge) + **`TESLIM-KURULUM.md`** (kurulum).

**Yönetici → Şirket sunucusu (bir kez):**
1. Repo'yu sunucuya al.
2. `cd backend && pip install -r requirements-web.txt` (hafif sürüm — çekim yok, sadece görüntüleme).
3. `backend/.env` içine **güçlü** `ADMIN_PASSWORD=...` yaz (güvenlik — şart).
4. `uvicorn app.main:app --host 0.0.0.0 --port 8100` çalıştır; ters proxy ile
   `harita.selenkaenerji.com` → `127.0.0.1:8100`.
5. `backend/data/epdk.db` **kalıcı** diskte olsun.

> Not: Şirket sunucunuz (energyai.selenkaenerji.com) zaten Python/uvicorn çalıştırıyor → uyumlu.

## 7. Aylık güncelleme (sürdürme)

```
1. Kendi PC'nde:  python cek_ters.py  → captcha çöz  → epdk.db güncellenir
2. Siteye gir:    /yonetim → şifre → epdk.db'yi yükle
3. Site herkese güncel veriyi gösterir ✓
```
Ayda bir bu kadar. Çekme sende kalır, site sadece gösterir.

---

**Özet:** Bu, EPDK lisans verisini haritalayan + kendi verini (KMZ/çizim) ekleyip indirebildiğin
bir görselleştirme aracı. Çekme lokalde (captcha insanlı), yayın şirket sunucusunda; aylık
güncelleme `/yonetim`'den DB yükleyerek yapılır.
