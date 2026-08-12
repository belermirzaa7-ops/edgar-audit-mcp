"""GERCEK SEC verisine karsi dogrulama (standart §3: sahte ortam gercegi kanitlamaz).

H-1 (KK-7) ve H-2 (KK-8) duzeltmelerinin canli veride tuttugunu olcer.

  $env:SEC_USER_AGENT = "Ad Soyad eposta@ornek.com"
  python dogrula.py
"""
import asyncio
import logging
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from arac.ortam import env_yukle  # noqa: E402
from edgar_mcp.server import get_company_profile, get_concept_series

logging.disable(logging.INFO)
env_yukle()

# (ticker, sirketin KENDI adlandirmasiyla en son tamamlanan mali yilin bitisi)
# Kaynak: sirketlerin kendi yillik raporlari.
HEDEFLER = [
    ("AAPL", "Eylul sonu  - takvim yilina yakin"),
    ("WMT",  "31 Ocak     - takvim disi"),
    ("NKE",  "31 Mayis    - takvim disi"),
    ("MSFT", "30 Haziran  - eski heuristigin tam sinirinda"),
]


async def h1_mali_yil():
    print("\n" + "=" * 78)
    print("H-1 (KK-7): mali yil adi SEC verisinden turetiliyor mu?")
    print("=" * 78)
    print(f"{'Ticker':<7}{'SEC mali yil sonu':<20}{'Bizim etiket':<14}"
          f"{'Donem sonu':<13}{'Kayma':<7}Turetildi")
    print("-" * 78)
    for t, _aciklama in HEDEFLER:
        p = await get_company_profile(ticker=t)
        s = await get_concept_series(ticker=t, concept="revenue", limit=1)
        if not s.points:
            print(f"{t:<7}{p.fiscal_year_end:<20}veri yok")
            continue
        pt = s.points[-1]
        kayma = pt.fiscal_year - int(pt.period_end[:4])
        print(f"{t:<7}{p.fiscal_year_end + '  (AAGG)':<20}FY{pt.fiscal_year:<12}"
              f"{pt.period_end:<13}{kayma:+d}      {s.fiscal_year_derived}")
    print("\nKONTROL: WMT/NKE/MSFT icin 'Bizim etiket', donem sonunun takvim")
    print("yiliyla AYNI olmali (bu sirketler mali yili bittigi yilla adlandirir).")
    print("Eski heuristik bir yil geride veriyordu.")


async def h2_gecmis():
    print("\n" + "=" * 78)
    print("H-2 (KK-8): etiket degisiminde gecmis kirpiliyor mu?")
    print("=" * 78)
    s = await get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    yillar = sorted(p.fiscal_year for p in s.points)
    print(f"  birlestirilen etiketler : {', '.join(s.resolved_concepts)}")
    print(f"  donem sayisi            : {len(yillar)}")
    print(f"  kapsam                  : FY{min(yillar)} - FY{max(yillar)}")
    kaynak_sayisi = {}
    for p in s.points:
        kaynak_sayisi[p.source_tag] = kaynak_sayisi.get(p.source_tag, 0) + 1
    print("  hangi etiketten kac donem:")
    for k, v in sorted(kaynak_sayisi.items(), key=lambda x: -x[1]):
        print(f"      {v:>3} donem  {k}")
    print()
    if min(yillar) <= 2010 and len(kaynak_sayisi) > 1:
        print("  DUZELTME TUTTU: birden fazla etiket birlestirildi, gecmis tam.")
    elif len(kaynak_sayisi) == 1:
        print("  DIKKAT: tek etiket kullanilmis. Birlestirme calismamis olabilir.")
    else:
        print(f"  DIKKAT: kapsam FY{min(yillar)}'de basliyor, beklenenden kisa.")
    print()


async def main():
    if not os.environ.get("SEC_USER_AGENT"):
        print("\nHATA: $env:SEC_USER_AGENT tanimla.\n")
        sys.exit(1)
    await h1_mali_yil()
    await h2_gecmis()


asyncio.run(main())
