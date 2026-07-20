# -*- coding: utf-8 -*-
"""Turkiye 81 il merkez koordinatlari (lat, lng). Yanlis/karisik EPDK dilim
etiketini duzeltmek icin referans: bir tesisin noktalarini, ILINE en yakin
dusuren dilimle donustururuz."""

IL_KOORD = {
    "ADANA": (37.00, 35.32), "ADIYAMAN": (37.76, 38.28), "AFYONKARAHISAR": (38.76, 30.54),
    "AGRI": (39.72, 43.05), "AKSARAY": (38.37, 34.03), "AMASYA": (40.65, 35.83),
    "ANKARA": (39.93, 32.85), "ANTALYA": (36.90, 30.70), "ARDAHAN": (41.11, 42.70),
    "ARTVIN": (41.18, 41.82), "AYDIN": (37.85, 27.84), "BALIKESIR": (39.65, 27.88),
    "BARTIN": (41.63, 32.34), "BATMAN": (37.88, 41.13), "BAYBURT": (40.26, 40.22),
    "BILECIK": (40.14, 29.98), "BINGOL": (38.88, 40.50), "BITLIS": (38.40, 42.11),
    "BOLU": (40.74, 31.61), "BURDUR": (37.72, 30.29), "BURSA": (40.19, 29.06),
    "CANAKKALE": (40.15, 26.41), "CANKIRI": (40.60, 33.62), "CORUM": (40.55, 34.95),
    "DENIZLI": (37.78, 29.09), "DIYARBAKIR": (37.91, 40.24), "DUZCE": (40.84, 31.16),
    "EDIRNE": (41.67, 26.56), "ELAZIG": (38.68, 39.22), "ERZINCAN": (39.75, 39.50),
    "ERZURUM": (39.90, 41.27), "ESKISEHIR": (39.78, 30.52), "GAZIANTEP": (37.07, 37.38),
    "GIRESUN": (40.91, 38.39), "GUMUSHANE": (40.46, 39.48), "HAKKARI": (37.58, 43.74),
    "HATAY": (36.20, 36.16), "IGDIR": (39.92, 44.04), "ISPARTA": (37.76, 30.55),
    "ISTANBUL": (41.01, 28.98), "IZMIR": (38.42, 27.14), "KAHRAMANMARAS": (37.58, 36.93),
    "KARABUK": (41.20, 32.63), "KARAMAN": (37.18, 33.22), "KARS": (40.60, 43.10),
    "KASTAMONU": (41.39, 33.78), "KAYSERI": (38.73, 35.49), "KIRIKKALE": (39.85, 33.51),
    "KIRKLARELI": (41.74, 27.22), "KIRSEHIR": (39.15, 34.16), "KILIS": (36.72, 37.12),
    "KOCAELI": (40.85, 29.88), "KONYA": (37.87, 32.48), "KUTAHYA": (39.42, 29.98),
    "MALATYA": (38.36, 38.31), "MANISA": (38.61, 27.43), "MARDIN": (37.31, 40.74),
    "MERSIN": (36.81, 34.64), "MUGLA": (37.22, 28.36), "MUS": (38.74, 41.49),
    "NEVSEHIR": (38.62, 34.71), "NIGDE": (37.97, 34.68), "ORDU": (40.98, 37.88),
    "OSMANIYE": (37.07, 36.25), "RIZE": (41.02, 40.52), "SAKARYA": (40.78, 30.40),
    "SAMSUN": (41.29, 36.33), "SIIRT": (37.93, 41.94), "SINOP": (42.03, 35.15),
    "SIVAS": (39.75, 37.02), "SANLIURFA": (37.17, 38.80), "SIRNAK": (37.52, 42.46),
    "TEKIRDAG": (41.00, 27.51), "TOKAT": (40.31, 36.55), "TRABZON": (41.00, 39.72),
    "TUNCELI": (39.11, 39.55), "USAK": (38.68, 29.41), "VAN": (38.49, 43.38),
    "YALOVA": (40.65, 29.28), "YOZGAT": (39.82, 34.81), "ZONGULDAK": (41.45, 31.79),
}

# Turkce karakter -> ASCII (kod noktasiyla; kaynak-encoding'den bagimsiz)
_TR = {
    0x0130: "I", 0x0131: "I", 0x015E: "S", 0x015F: "S", 0x011E: "G", 0x011F: "G",
    0x00DC: "U", 0x00FC: "U", 0x00D6: "O", 0x00F6: "O", 0x00C7: "C", 0x00E7: "C",
    0x00C2: "A", 0x00E2: "A", 0x00CE: "I", 0x00EE: "I", 0x00DB: "U", 0x00FB: "U",
    0xFFFD: "",
}


def _norm_il(s):
    if not s:
        return ""
    return s.translate(_TR).upper().split("/")[0].strip()


def il_ref(il):
    """Il adindan merkez koordinati bul (Turkce karakterler ASCII'ye cevrilir)."""
    n = _norm_il(il)
    if n in IL_KOORD:
        return IL_KOORD[n]
    for k, v in IL_KOORD.items():           # prefix esnekligi
        if n and (k.startswith(n[:6]) or n.startswith(k[:6])):
            return v
    return None
