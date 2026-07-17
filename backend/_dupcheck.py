import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
dup = q("select centroid_lat,centroid_lng,count(*) ct, group_concat(tesis_adi,' | ') "
        "from facilities where centroid_lat is not null group by centroid_lat,centroid_lng "
        "having ct>1 order by ct desc")
print("AYNI koordinati paylasan grup sayisi:", len(dup))
print("stale suphesi tesis sayisi:", sum(d[2] for d in dup))
for d in dup[:10]:
    print(f"  ({d[0]:.3f},{d[1]:.3f}) x{d[2]}: {d[3][:70]}")
