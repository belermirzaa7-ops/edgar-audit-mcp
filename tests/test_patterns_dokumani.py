"""PATTERNS.md'nin cürümesini engeller (standart §11).

Doküman "bu pattern su testle korunuyor" diyor. Test yeniden adlandirilirsa
dokuman sessizce yalan soylemeye baslar. Bu dosya onu yapisal olarak engeller.
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

KOK = pathlib.Path(__file__).resolve().parents[1]
PATTERNS = (KOK / "PATTERNS.md").read_text(encoding="utf-8")


def _mevcut_testler() -> set[str]:
    return {
        m
        for f in (KOK / "tests").glob("*.py")
        for m in re.findall(r"def (test_\w+)", f.read_text(encoding="utf-8"))
    }


def test_atif_yapilan_testler_gercekten_var():
    atif = set(re.findall(r"`(test_\w+)`", PATTERNS))
    assert atif, "PATTERNS.md hicbir teste atif yapmiyor"
    eksik = atif - _mevcut_testler()
    assert not eksik, f"PATTERNS.md var olmayan teste atif yapiyor: {sorted(eksik)}"


def test_atif_yapilan_araclar_gercekten_var():
    for yol in set(re.findall(r"`(arac/\w+\.py)`", PATTERNS)):
        assert (KOK / yol).exists(), f"PATTERNS.md var olmayan dosyaya atif yapiyor: {yol}"


def test_atif_yapilan_ci_isleri_gercekten_var():
    ci = yaml.safe_load((KOK / ".github" / "workflows" / "ci.yml").read_text())
    atif = {a or b for a, b in re.findall(r"CI job `([\w-]+)`|job `([\w-]+)`", PATTERNS)}
    eksik = atif - set(ci["jobs"])
    assert not eksik, f"PATTERNS.md var olmayan CI isine atif yapiyor: {sorted(eksik)}"


def test_kontrol_listesi_pattern_sayisiyla_ortusuyor():
    satir = re.findall(r"^\| \[(P-\d+)\]", PATTERNS, re.M)
    baslik = re.findall(r"^### (P-\d+) ·", PATTERNS, re.M)
    assert satir == baslik, (
        "kontrol listesi ile pattern basliklari ayristi "
        f"(liste={satir}, basliklar={baslik})"
    )


@pytest.mark.parametrize("alan", ["**Symptom.**", "**Root cause.**",
                                  "**Detection.**", "**Incident.**"])
def test_her_pattern_dort_alani_tasiyor(alan):
    for blok in re.split(r"^### P-\d+ · ", PATTERNS, flags=re.M)[1:]:
        kod = blok.split("\n")[0][:40]
        assert alan in blok, f"'{kod}' patterninde {alan} eksik"


def test_her_pattern_tarihli_bir_olaya_dayaniyor():
    """Giris kurali: olculmemis bir sey pattern degildir. Olay alani tarih tasimali."""
    for blok in re.split(r"^### P-\d+ · ", PATTERNS, flags=re.M)[1:]:
        kod = blok.split("\n")[0][:40]
        olay = blok.split("**Incident.**")[1]
        assert re.search(r"\d{1,2} \w{3} \d{4}", olay), f"'{kod}' olayinda tarih yok"


def _kontrol_listesi() -> list[tuple[str, str]]:
    return re.findall(r"^\| \[(P-\d+)\][^|]*\|[^|]*\|\s*([^|]+?)\s*\|", PATTERNS, re.M)


def test_korumasiz_patternler_iki_yerde_de_isaretli():
    """Otomatik korumasi olmayan pattern hem tabloda hem govdede 'none' demeli.
    Sessizce bosluk birakmak, boslugun kendisinden kotudur."""
    korumasiz = [k for k, g in _kontrol_listesi() if "none" in g.lower()]
    assert korumasiz, "hicbir pattern korumasiz isaretlenmemis - bu supheli"
    for kod in korumasiz:
        blok = re.split(rf"^### {kod} · ", PATTERNS, flags=re.M)[1]
        assert "Guard: none" in blok, f"{kod} listede korumasiz ama govdesinde belirtilmemis"


def test_koruma_sutunu_tek_bir_kelime_dagarcigi_kullaniyor():
    """Ayni durumu iki farkli kelimeyle yazmak ('manual' ve 'none') okuyucuyu
    yaniltti - disaridan okuyan once 'sadece biri korumasiz' sandi. Koruma
    sutunu ya bir test/arac/CI isi adlandirir ya da 'none' der."""
    for kod, guard in _kontrol_listesi():
        g = guard.lower()
        tanimli = ("none" in g or "test_" in g or "arac/" in g
                   or "job `" in g or "matrix" in g)
        assert tanimli, f"{kod} koruma sutunu taninmayan bir ifade kullaniyor: {guard!r}"


def test_govdesinde_guard_none_olan_tabloda_da_none_diyor():
    """Ters yon: govdede korumasiz denip tabloda test adi yazilmasin."""
    for kod in re.findall(r"^### (P-\d+) ·", PATTERNS, re.M):
        blok = re.split(rf"^### {kod} · ", PATTERNS, flags=re.M)[1].split("\n### ")[0]
        tablo = dict(_kontrol_listesi()).get(kod, "")
        if "Guard: none" in blok:
            assert "none" in tablo.lower(), f"{kod} govdede korumasiz, tabloda degil"
