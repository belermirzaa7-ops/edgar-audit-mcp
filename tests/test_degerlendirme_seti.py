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
    assert len(ciftler) == 22, f"22 soru bekleniyordu, {len(ciftler)} var"


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
            18: "eighteen", 19: "nineteen", 20: "twenty",
            21: "twenty-one", 22: "twenty-two"}
    tr_yazi = {10: "on", 15: "on beş", 16: "on altı", 17: "on yedi",
               18: "on sekiz", 19: "on dokuz", 20: "yirmi",
               21: "yirmi bir", 22: "yirmi iki"}
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


def test_kayit_defteri_kimligi_uc_dosyada_da_ayni():
    """MCP registry sunucu adi UC yerde birden geciyor ve ucu de birbirine
    esit OLMAK ZORUNDA: `server.json`'daki `name`, PyPI paketinin sahiplik
    isareti (README'deki `mcp-name:` yorumu, PyPI aciklamasina bu dosyadan
    geciyor) ve OCI imajinin `io.modelcontextprotocol.server.name` etiketi.

    Kayit defteri bunlari karsilastiriyor; tutmazsa yayin "Registry validation
    failed for package" ile reddediliyor (16 Agu 2026'da kayit defterinin kendi
    paket-turu dokumaninda olculdu). Bir yeniden adlandirma uc dosyanin ikisini
    guncelleyip ucuncusunu unutursa hata YAYIN aninda cikar - o an geri bildirim
    dongusu en pahalidir. Burada tek bir test yeter.
    """
    import json

    ad = json.loads((KOK / "server.json").read_text(encoding="utf-8"))["name"]
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", ad), (
        f"server.json adi kayit defterinin desenine uymuyor: {ad}")

    okuma = (KOK / "README.md").read_text(encoding="utf-8")
    assert f"<!-- mcp-name: {ad} -->" in okuma, (
        "README'deki mcp-name isareti server.json'daki adla ayni degil "
        "(PyPI sahiplik dogrulamasi bu satiri okuyor)")

    docker = (KOK / "Dockerfile").read_text(encoding="utf-8")
    assert f'LABEL io.modelcontextprotocol.server.name="{ad}"' in docker, (
        "Dockerfile etiketi server.json'daki adla ayni degil "
        "(OCI sahiplik dogrulamasi bu etiketi okuyor)")


def _iddia_edilen_sayilar(metin: str, kalip: str) -> list[int]:
    return [int(m) for m in re.findall(kalip, metin)]


def test_dokumanlardaki_sayilar_gercekle_ayni():
    """Satis malzemesindeki sayilar KODDAN dogrulanir, elle guncellenmez.

    17 Agu 2026'da uc iddia birden bayatti: vaka calismasi "250 tests" ve
    "170 fault injections" diyordu (gercek 264 ve 175), iki README de
    "30 failures" diyordu (gercek 31). Hicbiri yanlis bir sey OGRETMIYOR ama
    hepsi ayni sinifin ornegi (P-14): dokumanda duran, kodun dogrulamadigi bir
    iddia. Musteriye giden bir sayfada bayat sayi, olcum kulturu iddiasini
    dogrudan zayiflatir.

    Sayilar buyudugu icin bu test zamanla kirmiziya doner - dogrusu budur:
    bir insan gelip dokumani gunceller.
    """
    import subprocess
    import sys

    # 1) Hata enjeksiyonu sayisi
    sys.path.insert(0, str(KOK))
    from arac.enjeksiyon import ENJEKSIYONLAR

    vaka = (KOK / "docs" / "case-study.md").read_text(encoding="utf-8")
    enj = _iddia_edilen_sayilar(vaka, r"\*\*(\d+) fault injections")
    assert enj == [len(ENJEKSIYONLAR)], (
        f"vaka calismasi {enj} enjeksiyon diyor, harness'ta {len(ENJEKSIYONLAR)} var")

    # 2) PATTERNS girdisi sayisi
    p_sayisi = len(re.findall(r"^### P-", (KOK / "PATTERNS.md").read_text(
        encoding="utf-8"), re.MULTILINE))
    for ad in ("README.md", "README.tr.md", "docs/case-study.md"):
        metin = (KOK / ad).read_text(encoding="utf-8")
        iddia = _iddia_edilen_sayilar(metin, r"(\d+)\s+(?:failures|hata)\b")
        assert iddia and set(iddia) == {p_sayisi}, (
            f"{ad} {iddia} diyor, PATTERNS.md'de {p_sayisi} girdi var")

    # 3) Test sayisi - pytest'in kendi saydigi sayi, `def test_` sayisi degil:
    # parametreli testler calisma aninda birden fazla teste aciliyor.
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=KOK, capture_output=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r"(\d+) tests? collected", r.stdout or "")
    assert m, f"pytest toplama ciktisi okunamadi: {(r.stdout or '')[-300:]}"
    toplanan = int(m.group(1))
    test_iddia = _iddia_edilen_sayilar(vaka, r"\*\*(\d+) tests\*\*")
    assert test_iddia == [toplanan], (
        f"vaka calismasi {test_iddia} test diyor, pytest {toplanan} topluyor")
