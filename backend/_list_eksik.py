"""Koordinatsiz (eksik) tesisleri lisans bilgisiyle listele + dosyaya yaz."""
import sqlite3

c = sqlite3.connect('data/epdk.db')
cur = c.cursor()

rows = cur.execute("""
    select f.tesis_adi, f.il, f.ilce, f.kaynak_turu, f.koordinat_durumu,
           l.lisans_no, l.unvan
    from facilities f left join licenses l on f.license_id = l.id
    where f.centroid_lat is null and f.is_active = 1
    order by f.tesis_adi
""").fetchall()

out = []
out.append(f"KOORDINATSIZ TESISLER — Toplam: {len(rows)}")
out.append("=" * 70)
for i, (adi, il, ilce, kaynak, durum, lno, unvan) in enumerate(rows, 1):
    out.append(f"{i}. {adi}")
    out.append(f"   Il/Ilce   : {il} / {ilce}")
    out.append(f"   Kaynak    : {kaynak}")
    out.append(f"   Lisans No : {lno}")
    out.append(f"   Unvan     : {unvan}")
    out.append(f"   Durum     : {durum}")
    out.append("")

text = "\n".join(out)
path = "../eksik_tesisler.txt"
with open(path, "w", encoding="utf-8") as fh:
    fh.write(text)

print(text)
print(f"\n[Dosyaya da yazildi: eksik_tesisler.txt (proje klasorunde)]")
