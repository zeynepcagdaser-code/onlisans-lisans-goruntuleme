"""Ayni koordinati paylasan (stale suphesi) tesisleri temizle -> yeniden cekilsin."""
import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
# ayni centroid'i paylasan gruplarin TUM uyeleri
dups = cur.execute("""
  select id from facilities where centroid_lat is not null and (centroid_lat,centroid_lng) in
  (select centroid_lat,centroid_lng from facilities where centroid_lat is not null
   group by centroid_lat,centroid_lng having count(*)>1)""").fetchall()
ids = [r[0] for r in dups]
print("stale-suphesi tesis:", len(ids))
for i in ids:
    cur.execute("""update facilities set koordinat_alindi=0, koordinat_durumu='beklemede',
                   polygon_wgs84=NULL, ham_koordinat_tm3=NULL, centroid_lat=NULL,
                   centroid_lng=NULL where id=?""", (i,))
c.commit()
print("temizlendi -> sonraki cekimde yeniden alinacak")
print("kalan koordinatli:", cur.execute("select count(*) from facilities where centroid_lat is not null").fetchone()[0])
