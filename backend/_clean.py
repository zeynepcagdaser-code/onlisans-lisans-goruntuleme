"""Yururlukte disi (yanlislikla eklenen) lisans+tesisleri temizle."""
import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
bad = cur.execute("select id from licenses where lisans_durumu != 'Yürürlükte'").fetchall()
ids = [r[0] for r in bad]
print("silinecek lisans (Yururlukte disi):", len(ids))
for lid in ids:
    cur.execute("delete from facilities where license_id=?", (lid,))
    cur.execute("delete from licenses where id=?", (lid,))
c.commit()
print("kalan lisans:", cur.execute("select count(*) from licenses").fetchone()[0])
print("durum dagilimi:", dict(cur.execute("select lisans_durumu,count(*) from licenses group by lisans_durumu").fetchall()))
print("koordinatli tesis:", cur.execute("select count(*) from facilities where centroid_lat is not null").fetchone()[0])
cur.execute("update scrape_runs set durum='partial' where durum in ('scraping','running')")
c.commit()
