"""Degerlendirme setinin yapisini sabitler (standart §11).

Bu dosya CEVAPLARI dogrulayamaz - dogrulama SEC'e canli cikmayi gerektirir ve
test paketi bilerek offline. Yapabilecegi: setin bicimsel olarak saglam
kalmasi ve her sorunun nasil olculdugunun yazili olmasi. Bir soru
<verification> alani olmadan eklenirse, o cevap bir tahmindir; bu test onu
kirmiziya dondurur.
"""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

KOK = pathlib.Path(__file__).resolve().parents[1]
YOL = KOK / "evaluation" / "questions.xml"


def _ciftler() -> list[ET.Element]:
    return ET.parse(YOL).getroot().findall("qa_pair")


def test_xml_gecerli_ve_beklenen_sayida_soru_var():
    ciftler = _ciftler()
    assert len(ciftler) == 18, f"18 soru bekleniyordu, {len(ciftler)} var"


def test_her_arac_degerlendirme_setinde_temsil_ediliyor():
    """Standart: API'yi genisletmek eval set bir bosluk gosterince acilir.
    Tersi de gecerli - yeni bir arac eklendiginde set onu kapsamali, yoksa
    "dogrulandi" dedigimiz sey eski yuzeyin dogrulamasi olur."""
    import asyncio
    import os
    import sys

    sys.path.insert(0, str(KOK / "src"))
    os.environ.setdefault("SEC_USER_AGENT", "Test Runner test@example.com")
    from edgar_mcp.server import mcp

    metin = YOL.read_text(encoding="utf-8")
    eksik = [t.name for t in asyncio.run(mcp.list_tools()) if t.name not in metin]
    assert not eksik, f"degerlendirme seti bu araclari hic cagirmiyor: {eksik}"


def test_her_soru_cevap_ve_olcum_tasiyor():
    for i, c in enumerate(_ciftler(), 1):
        for alan in ("question", "answer", "verification"):
            dugum = c.find(alan)
            assert dugum is not None and (dugum.text or "").strip(), \
                f"{i}. soruda '{alan}' eksik veya bos"


def test_her_olcum_gercek_arac_adlari_kullaniyor():
    """<verification> icinde adi gecen her arac sunucuda gercekten olmali."""
    import asyncio
    import os
    import sys

    sys.path.insert(0, str(KOK / "src"))
    os.environ.setdefault("SEC_USER_AGENT", "Test Runner test@example.com")
    from edgar_mcp.server import mcp

    mevcut = {t.name for t in asyncio.run(mcp.list_tools())}
    metin = YOL.read_text(encoding="utf-8")
    anilan = set(re.findall(r"\b(sec_edgar_\w+)\s*\(", metin))
    assert anilan, "degerlendirme setinde hicbir arac cagrisi yok"
    eksik = anilan - mevcut
    assert not eksik, f"degerlendirme seti var olmayan araci cagiriyor: {sorted(eksik)}"


def test_sorular_en_yeni_donemi_hedeflemiyor():
    """'En son ceyrek' gibi bir soru her yeni dosyalamada bayatlar. Sorular
    adli mali yila baglanmali."""
    yasak = re.compile(r"\b(latest|most recent|current)\b", re.IGNORECASE)
    for i, c in enumerate(_ciftler(), 1):
        soru = (c.findtext("question") or "")
        assert not yasak.search(soru), \
            f"{i}. soru zamana bagli bir ifade kullaniyor: {soru!r}"


def test_readme_soru_sayisi_dosyayla_ayni():
    """15 Agu 2026 denetiminde bulundu: iki README de "on soru" diyordu, dosyada
    on sekiz vardi. P-14 ("dokuman var olmayan davranisi vaat eder") PATTERNS.md
    icin testliydi, README icin degildi. Sayilar yaziyla yazildigi icin bu test
    de yaziyla arıyor."""
    import re

    yazi = {10: "ten", 15: "fifteen", 16: "sixteen", 17: "seventeen",
            18: "eighteen", 19: "nineteen", 20: "twenty"}
    tr_yazi = {10: "on", 15: "on beş", 16: "on altı", 17: "on yedi",
               18: "on sekiz", 19: "on dokuz", 20: "yirmi"}
    n = len(_ciftler())
    assert n in yazi, f"{n} icin yazi karsiligi tabloya eklenmeli"

    en = (KOK / "README.md").read_text(encoding="utf-8")
    tr = (KOK / "README.tr.md").read_text(encoding="utf-8")
    for ad, metin, tablo in (("README.md", en, yazi), ("README.tr.md", tr, tr_yazi)):
        for sayi, kelime in tablo.items():
            if sayi == n:
                continue
            kalip = rf"\b{re.escape(kelime)}\s+(questions|pairs|soru)"
            assert not re.search(kalip, metin, re.IGNORECASE), (
                f"{ad} '{kelime} soru' diyor ama dosyada {n} soru var")


def test_readme_takma_ad_listesi_kodla_ayni():
    """Takma ad listesi README'de elle yaziliydi ve KK-26'nin uc yeni takma adi
    (public_float, shares_outstanding, shares_diluted) eklenmemisti."""
    import asyncio
    import os
    import sys

    sys.path.insert(0, str(KOK / "src"))
    os.environ.setdefault("SEC_USER_AGENT", "Test Runner test@example.com")
    from edgar_mcp.server import CONCEPT_ALIASES

    en = (KOK / "README.md").read_text(encoding="utf-8")
    eksik = [a for a in CONCEPT_ALIASES if f"`{a}`" not in en]
    assert not eksik, f"README bu takma adlari saymiyor: {eksik}"
    del asyncio
