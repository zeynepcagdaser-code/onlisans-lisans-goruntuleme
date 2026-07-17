"""KML/KMZ uretimi. Her tesis icin Polygon (sinir) + Point (centroid) placemark."""
import io
import zipfile
from xml.sax.saxutils import escape


def _facility_description(fac) -> str:
    rows = [
        ("Lisans No", getattr(fac.license, "lisans_no", "") if fac.license else ""),
        ("Unvan", getattr(fac.license, "unvan", "") if fac.license else ""),
        ("Tesis Adı", fac.tesis_adi), ("İl", fac.il), ("İlçe", fac.ilce),
        ("Tesis Türü", fac.tesis_turu), ("Kaynak Türü", fac.kaynak_turu),
        ("Kurulu Güç (MWm)", fac.kurulu_guc_mwm), ("Kurulu Güç (MWe)", fac.kurulu_guc_mwe),
        ("Merkez", f"{fac.centroid_lat}, {fac.centroid_lng}"),
    ]
    html = "<![CDATA[<table>" + "".join(
        f"<tr><td><b>{escape(str(k))}</b></td><td>{escape(str(v)) if v is not None else ''}</td></tr>"
        for k, v in rows) + "</table>]]>"
    return html


def _placemarks_for(fac) -> str:
    name = escape(fac.tesis_adi or f"Tesis {fac.id}")
    desc = _facility_description(fac)
    parts = []
    # Centroid noktasi
    if fac.centroid_lat is not None and fac.centroid_lng is not None:
        parts.append(f"""
    <Placemark>
      <name>{name}</name>
      <description>{desc}</description>
      <styleUrl>#pointStyle</styleUrl>
      <Point><coordinates>{fac.centroid_lng},{fac.centroid_lat},0</coordinates></Point>
    </Placemark>""")
    # Poligon sinir(lar)i - polygon_wgs84 zaten halka listesi (dogru kurulmus)
    for ring_pts in (fac.polygon_wgs84 or []):
        if not ring_pts or len(ring_pts) < 3:
            continue
        ring = ring_pts + [ring_pts[0]]  # kapat
        coord_str = " ".join(f"{lng},{lat},0" for lat, lng in ring)
        parts.append(f"""
    <Placemark>
      <name>{name} (sınır)</name>
      <styleUrl>#polyStyle</styleUrl>
      <Polygon><outerBoundaryIs><LinearRing>
        <coordinates>{coord_str}</coordinates>
      </LinearRing></outerBoundaryIs></Polygon>
    </Placemark>""")
    return "".join(parts)


def build_kml(facilities, doc_name="EPDK Tesisler") -> str:
    body = "".join(_placemarks_for(f) for f in facilities)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{escape(doc_name)}</name>
    <Style id="pointStyle">
      <IconStyle><scale>1.1</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href></Icon>
      </IconStyle>
    </Style>
    <Style id="polyStyle">
      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
      <PolyStyle><color>4d0000ff</color></PolyStyle>
    </Style>
    {body}
  </Document>
</kml>"""


def build_kmz(facilities, doc_name="EPDK Tesisler") -> bytes:
    kml = build_kml(facilities, doc_name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
    return buf.getvalue()
