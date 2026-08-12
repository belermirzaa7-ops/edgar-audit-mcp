"""Depoya sir sizmis mi tarar (standart §8).

Iki mod:
  (varsayilan)  calisma dizinindeki dosyalar
  --gecmis      ek olarak git gecmisi (bir commit'te eklenip sonra silinen sir
                dosyada gorunmez ama gecmiste durur ve public repoda okunabilir)

CI'da her push'ta calisir. Bulgu varsa exit code 1 doner.
Yer tutucu ornek adresler (example.com, ornek.com) bilerek disarida.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
YOKSAY_DIZIN = {".venv", "__pycache__", ".git", ".pytest_cache", ".ruff_cache",
                "dist", ".enjeksiyon_yedek", "node_modules", ".mypy_cache"}
YOKSAY_ALAN = ("example.com", "ornek.com", "alanadi.com", "epostan.com")

DESENLER = {
    "private key":  r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "AWS key id":   r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{16,}",
    "Slack token":  r"xox[abprs]-[A-Za-z0-9-]{10,}",
    "OpenAI key":   r"sk-[A-Za-z0-9]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9-]{20,}",
    "assigned secret": r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[=:]\s*['\"][^'\"\s]{8,}['\"]",
    "email":        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
}


def _sorunlu(ad: str, deger: str) -> bool:
    """Yer tutucu ornek adresler bulgu sayilmaz."""
    return not (ad == "email" and any(a in deger for a in YOKSAY_ALAN))


def calisma_dizini(kok: pathlib.Path | None = None) -> list[tuple[str, str, str]]:
    """(konum, desen_adi, deger)"""
    kok = kok or KOK
    bulgular = []
    for f in sorted(kok.rglob("*")):
        if not f.is_file() or any(p in YOKSAY_DIZIN for p in f.parts):
            continue
        if f.suffix in {".pyc", ".zip", ".png", ".jpg", ".gif"}:
            continue
        try:
            metin = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ad, desen in DESENLER.items():
            for m in re.finditer(desen, metin):
                if not _sorunlu(ad, m.group(0)):
                    continue
                satir = metin[: m.start()].count("\n") + 1
                bulgular.append((f"{f.relative_to(kok)}:{satir}", ad, m.group(0)[:70]))
    return bulgular


def _git(*args: str, kok: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    # encoding acikca verilmeli: Windows'ta text=True yerel kod sayfasini
    # (orn. cp1254) kullanir ve git'in UTF-8 ciktisinda cokerek stdout'u
    # None birakir. errors="replace" cozulemeyen baytta tarama durmasin diye.
    return subprocess.run(
        ["git", *args], cwd=kok or KOK, capture_output=True,
        encoding="utf-8", errors="replace", check=False,
    )


def git_gecmisi(kok: pathlib.Path | None = None) -> tuple[list[tuple[str, str, str]], str | None]:
    """Gecmisteki commit'lerde EKLENEN satirlari tarar.

    Doner: (bulgular, hata_mesaji). hata_mesaji doluysa tarama GUVENILIR DEGIL
    ve cagiran bunu basarisizlik saymalidir - sessizce 'temiz' demek, taramanin
    hic calismadigi durumu basariyla karistirir.
    """
    kok = kok or KOK
    if _git("rev-parse", "--git-dir", kok=kok).returncode != 0:
        return [], "git deposu degil (veya git kurulu degil)"

    if (_git("rev-parse", "--is-shallow-repository", kok=kok).stdout or "").strip() == "true":
        return [], (
            "depo SIG (shallow) klonlanmis - gecmisin tamami yok. "
            "CI'da actions/checkout icin 'fetch-depth: 0' gerekiyor."
        )

    r = _git("log", "--all", "-p", "--no-color", "--format=commit %H %s", kok=kok)
    if r.returncode != 0:
        return [], f"git log basarisiz: {(r.stderr or '').strip()[:120]}"

    bulgular = []
    commit = "?"
    for satir in (r.stdout or "").splitlines():
        if satir.startswith("commit "):
            commit = satir[7:].split(" ")[0][:9] + " " + satir[7:].split(" ", 1)[-1][:40]
            continue
        if not satir.startswith("+") or satir.startswith("+++"):
            continue
        for ad, desen in DESENLER.items():
            for m in re.finditer(desen, satir[1:]):
                if not _sorunlu(ad, m.group(0)):
                    continue
                bulgular.append((f"commit {commit}", ad, m.group(0)[:70]))
    # ayni sir birden cok commit'te tekrar edebilir
    return sorted(set(bulgular)), None


def main() -> int:
    ap = argparse.ArgumentParser(description="Depo sir taramasi")
    ap.add_argument("--gecmis", action="store_true",
                    help="git gecmisini de tara (silinmis ama commit'lenmis sirlar)")
    a = ap.parse_args()

    bulgular = [("CALISMA DIZINI", *b) for b in calisma_dizini()]
    hata = None
    if a.gecmis:
        gecmis, hata = git_gecmisi()
        bulgular += [("GIT GECMISI", *b) for b in gecmis]

    if hata:
        print(f"GECMIS TARAMASI YAPILAMADI: {hata}")
        print("Bu bir basarisizliktir - tarama calismadi, 'temiz' anlamina gelmez.")
        return 2

    if not bulgular:
        kapsam = "calisma dizini + git gecmisi" if a.gecmis else "calisma dizini"
        print(f"Sir taramasi temiz ({kapsam}).")
        return 0

    print(f"{len(bulgular)} olasi sir bulundu:\n")
    for nerede, konum, ad, deger in bulgular:
        print(f"  [{nerede}] {konum}  [{ad}]  {deger}")
    print("\nYer tutucu ise arac/sir_tarama.py icindeki YOKSAY_ALAN listesine ekle.")
    print("Git gecmisindeki bir bulgu dosyadan silinmekle YOK OLMAZ; gecmisi")
    print("yeniden yazmak gerekir.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
