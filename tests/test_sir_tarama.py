"""Sir tarayicinin GERCEKTEN taradigini dogrular (standart §1, §2).

Gecici bir git deposu kurulur ve gecmisine kasten sir gomulur; tarayicinin
onu bulmasi beklenir. Bu testler olmadan tarayici "temiz" der ve hicbir sey
kanitlanmis olmaz.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from arac.sir_tarama import calisma_dizini, git_gecmisi  # noqa: E402

# Tarayicinin kendi kaynak dosyasi da taraniyor. Adresi calisma aninda
# birlestiriyoruz ki dosyada BUTUN hali gecmesin - boylece tarayiciya istisna
# acmadan (yani koruma delmeden) sir-benzeri bir girdi uretebiliyoruz.
GIZLI = "gizli.adres" + "@" + "gmail.com"
YER_TUTUCU = "you@example.com"


def _git(kok: pathlib.Path, *a: str) -> None:
    subprocess.run(["git", *a], cwd=kok, check=True, capture_output=True,
                   encoding="utf-8", errors="replace")


@pytest.fixture
def depo(tmp_path: pathlib.Path) -> pathlib.Path:
    kok = tmp_path / "depo"
    kok.mkdir()
    _git(kok, "init", "-q", "-b", "main")
    _git(kok, "config", "user.email", "t@example.com")
    _git(kok, "config", "user.name", "T")
    return kok


def _yaz_commit(kok: pathlib.Path, icerik: str, mesaj: str) -> None:
    (kok / "app.py").write_text(f'ua = "{icerik}"\n', encoding="utf-8")
    _git(kok, "add", "-A")
    _git(kok, "commit", "-qm", mesaj)


def test_temiz_gecmis_bulgu_vermez(depo):
    _yaz_commit(depo, YER_TUTUCU, "ilk")
    bulgular, hata = git_gecmisi(depo)
    assert hata is None
    assert bulgular == []


def test_eklenip_silinen_sir_gecmiste_yakalanir(depo):
    """Asil senaryo: dosyanin son hali temiz ama sir gecmiste duruyor."""
    _yaz_commit(depo, YER_TUTUCU, "ilk")
    _yaz_commit(depo, GIZLI, "e-posta guncelle")
    _yaz_commit(depo, YER_TUTUCU, "geri al")

    assert calisma_dizini(depo) == [], "dosyanin son hali zaten temiz olmaliydi"

    bulgular, hata = git_gecmisi(depo)
    assert hata is None
    assert any(GIZLI in b[2] for b in bulgular), "gecmisteki sir kacirildi"


def test_sig_klon_temiz_demez(depo, tmp_path):
    """En sinsi hata: CI sig klonlar, tarayici tek commit gorup 'temiz' der.
    Tarayici bu durumda BASARISIZLIK bildirmeli.

    Klon tmp_path ICINE aciliyor; pytest kendisi temizler. Onceki surumde
    elle "rm -rf" cagriliyordu ve Windows'ta boyle bir komut olmadigi icin
    test cokuyordu - platform farki (standart §9).
    """
    _yaz_commit(depo, GIZLI, "sir")
    _yaz_commit(depo, YER_TUTUCU, "geri al")
    klon = tmp_path / "sig_klon"
    # as_uri(): Windows'ta "file://C:\\..." elle kurulamaz, dogru bicimi verir
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", depo.as_uri(), str(klon)],
        check=True, capture_output=True, encoding="utf-8", errors="replace",
    )
    bulgular, hata = git_gecmisi(klon)
    assert hata is not None, "sig klon sessizce temiz gecti"
    assert "SIG" in hata or "shallow" in hata.lower()
    assert bulgular == []


def test_git_olmayan_dizin_temiz_demez(tmp_path):
    bulgular, hata = git_gecmisi(tmp_path)
    assert hata is not None
    assert bulgular == []


def test_yer_tutucu_adresler_bulgu_sayilmaz(depo):
    _yaz_commit(depo, "Ad Soyad eposta@ornek.com", "yer tutucu")
    bulgular, hata = git_gecmisi(depo)
    assert hata is None
    assert bulgular == []
