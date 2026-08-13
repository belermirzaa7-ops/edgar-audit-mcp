"""Programi GERCEK SEC verisine baglar.

PowerShell:
    $env:SEC_USER_AGENT = "Mirza Beler senin@epostan.com"
    python dene.py
"""
import asyncio
import logging
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from arac.ortam import env_yukle  # noqa: E402
from edgar_mcp.server import (
    get_company_profile,
    get_concept_series,
    list_available_concepts,
    list_recent_filings,
)

logging.disable(logging.INFO)
env_yukle()
TICKER = "AAPL"


def para(x):
    return f"{x/1e9:,.2f} milyar $" if abs(x) >= 1e9 else f"{x:,.0f} $"


async def main():
    if not os.environ.get("SEC_USER_AGENT"):
        print('\nHATA: once sunu calistir:\n  $env:SEC_USER_AGENT = "Ad Soyad eposta@ornek.com"\n')
        sys.exit(1)

    print(f"\nSEC EDGAR'a baglaniliyor... ({TICKER})")

    p = await get_company_profile(ticker=TICKER)
    print(f"\n--- SIRKET ---\n  {p.name}\n  CIK: {p.cik}\n  Sektor: {p.sic_description}")

    print("\n--- SON YILLIK RAPORLAR ---")
    sayfa = await list_recent_filings(ticker=TICKER, form_type="10-K", limit=3)
    print(f"  toplam eslesen: {sayfa.total_matching}, gosterilen: {sayfa.returned}, "
          f"devami var mi: {sayfa.has_more}")
    for f in sayfa.filings:
        print(f"  {f.filing_date}  ->  {f.primary_document_url}")

    # Artik ham XBRL etiketi degil, takma ad veriyoruz. Dogru etiketi sunucu buluyor.
    for takma in ("revenue", "net_income"):
        s = await get_concept_series(ticker=TICKER, concept=takma, limit=5)
        print(f"\n--- {takma.upper()} ---")
        print(f"  cozulen etiket: {', '.join(s.resolved_concepts)}")
        print(f"  toplam donem: {s.total_periods}, gosterilen: {s.returned}, "
              f"daha eskisi var mi: {s.has_more}")
        onceki = None
        for pt in s.points:
            art = f"   ({(pt.value/onceki-1)*100:+.1f}%)" if onceki else ""
            print(f"  FY{pt.fiscal_year}   {para(pt.value):>18}{art}")
            onceki = pt.value

    print("\n--- KESIF ARACI: 'revenue' iceren etiketler ---")
    k = await list_available_concepts(ticker=TICKER, search="revenue", limit=5)
    print(f"  toplam eslesen: {k.total_matching}, gosterilen: {k.returned}, devami var mi: {k.has_more}")
    for c in k.concepts:
        print(f"    {c.tag}  ({c.data_points} veri noktasi)")
    print()


asyncio.run(main())
