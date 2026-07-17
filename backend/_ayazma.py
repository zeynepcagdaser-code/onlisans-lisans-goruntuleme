import sqlite3
c = sqlite3.connect('data/epdk.db'); cur = c.cursor()
r = cur.execute(
    "select f.tesis_adi, l.unvan, f.il, f.centroid_lat, f.centroid_lng, f.koordinat_durumu "
    "from facilities f join licenses l on f.license_id=l.id "
    "where f.tesis_adi like '%AYAZMA%' or l.unvan like '%SELENKA%'").fetchall()
if r:
    for x in r:
        print(x)
else:
    print("DB'de YOK - cekilmesi gerek")
