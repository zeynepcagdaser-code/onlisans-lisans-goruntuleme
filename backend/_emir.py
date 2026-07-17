import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
print("EMIR-1:", q("select tesis_adi, json_array_length(polygon_wgs84), koordinat_durumu from facilities where tesis_adi like 'EM%'"))
print("nokta dagilimi (buyukten):")
for r in q("select tesis_adi, json_array_length(polygon_wgs84) np from facilities where polygon_wgs84 is not null order by np desc limit 6"):
    print("  ", r[0][:30], r[1])
print("durum:", dict(q("select koordinat_durumu,count(*) from facilities group by koordinat_durumu")))
# ayni koordinat paylasan var mi
dup = q("""select count(*) from (select centroid_lat,centroid_lng,count(*) c from facilities
           where centroid_lat is not null group by 1,2 having c>1)""")
print("stale (ayni koordinatli grup sayisi):", dup[0][0])
