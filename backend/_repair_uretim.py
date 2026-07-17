"""_deactivate_stale + resume cakismasi yuzunden yanlis pasiflenen URETIM
lisans/tesislerini geri aktiflestir. (680 uretim tesisin hepsi gercek, hepsi
scrape'lerde bulundu -> aktif olmali. Gelecekte temiz tam-tur gerekirse dogru
pasiflestirir.)"""
import sqlite3

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

# uretim lisanslar
n1 = cur.execute("""update licenses set is_active=1
    where lisans_tipi='uretim' and is_active=0""").rowcount
# uretim tesisler
n2 = cur.execute("""update facilities set is_active=1 where is_active=0
    and license_id in (select id from licenses where lisans_tipi='uretim')""").rowcount
c.commit()

print(f"aktiflenen uretim lisans: {n1}")
print(f"aktiflenen uretim tesis : {n2}")
print()
print("uretim aktif tesis:", cur.execute("""select count(*) from facilities f
    join licenses l on f.license_id=l.id where l.lisans_tipi='uretim' and f.is_active=1""").fetchone()[0])
print("uretim koordinatli:", cur.execute("""select count(*) from facilities f
    join licenses l on f.license_id=l.id where l.lisans_tipi='uretim' and f.is_active=1
    and f.centroid_lat is not null""").fetchone()[0])
print("onlisan aktif tesis:", cur.execute("""select count(*) from facilities f
    join licenses l on f.license_id=l.id where l.lisans_tipi='onlisan' and f.is_active=1""").fetchone()[0])
