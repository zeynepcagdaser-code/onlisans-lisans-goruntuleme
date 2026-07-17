import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
q = lambda s: cur.execute(s).fetchall()
lg = q('select log_text from scrape_runs order by id desc limit 1')[0][0]
print("=== LOG ilk 12 satir ===")
print('\n'.join(lg.splitlines()[:12]))
print("\n=== ayni centroid'i paylasan tesisler (stale kontrolu) ===")
dup = q("""select centroid_lat, centroid_lng, count(*) c, group_concat(tesis_adi||' ['||il||']','  |  ')
           from facilities where centroid_lat is not null
           group by centroid_lat, centroid_lng having c > 1 order by c desc limit 10""")
if not dup:
    print("  YOK — her tesis benzersiz koordinat (stale bug COZULDU)")
for d in dup:
    print(f"  ({d[0]},{d[1]}) x{d[2]}: {d[3][:120]}")
print("\n=== supheli ornekleri ===")
for r in q("select tesis_adi,il,dilim_meridyeni,centroid_lat,centroid_lng from facilities where koordinat_durumu='supheli' limit 5"):
    print(" ", r)
