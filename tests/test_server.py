"""SEC'e canli cikmadan sunucuyu dogrular: HTTP katmani mock'lanir."""
import os
import pathlib
import re
import sys

import httpx
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "src"))

TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
           "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
           "2": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
           "3": {"cik_str": 104169, "ticker": "WMT", "title": "Walmart Inc."},
           "4": {"cik_str": 55067, "ticker": "K", "title": "Kellanova"}}
SUBS = {"name": "Apple Inc.", "sicDescription": "Electronic Computers",
        "fiscalYearEnd": "0927",
        # Gercek SEC submissions verisi karisik form turleri icerir; sahte veri de icermeli.
        "filings": {"recent": {
            "accessionNumber": ["0000320193-25-000073","0000320193-25-000058",
                                "0000320193-25-000041","0000320193-24-000123",
                                "0000320193-25-000012","0000320193-26-000110",
                                "0000320193-26-000900"],
            "form":            ["10-K","10-Q","8-K","10-K","4","4","13F-HR"],
            "filingDate":      ["2025-10-31","2025-08-01","2025-06-10","2024-11-01",
                                "2025-02-03","2026-02-20","2026-05-15"],
            "reportDate":      ["2025-09-27","2025-06-28","2025-06-09","2024-09-28",
                                "","2026-02-18","2026-03-31"],
            "primaryDocument": ["aapl-20250927.htm","aapl-20250628.htm","aapl-8k.htm",
                                "aapl-20240928.htm","xslF345X05/form4.xml",
                                "xslF345X03/wf-form4_123.xml",
                                "xslForm13F_X02/primary_doc.xml"],
        },
        # SEC `recent` akisini ~1000 dosyalamada keser ve gerisini AYRI JSON
        # dosyalarina koyar. Sahte veri bunu tasimadigi surece "bu sirketin
        # baska dosyalamasi yok" iddiasini hicbir test yakalayamaz (P-4).
        "files": [{"name": "CIK0000320193-submissions-001.json",
                   "filingCount": 1103, "filingFrom": "1994-01-01",
                   "filingTo": "2015-12-31"}]}}

# Gercek companyconcept satirlari `accn` (erisim numarasi) tasir; revizyon
# gecmisi aracinin izlenebilirligi ona dayaniyor, o yuzden sahte veride de var.
CONCEPT = {"label": "Revenues", "units": {"USD": [
    # 2023 10-K: uc yillik karsilastirma, UCUNUN DE fy'si 2023 (SEC boyle veriyor)
    {"start":"2020-09-27","end":"2021-09-25","val":365_817_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03","accn":"0000320193-23-000106"},
    {"start":"2021-09-26","end":"2022-09-24","val":394_328_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03","accn":"0000320193-23-000106"},
    {"start":"2022-09-25","end":"2023-09-30","val":383_285_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03","accn":"0000320193-23-000106"},
    # AYNI donem, AYNI deger, sonraki dosyalamada tekrar: bu revizyon DEGIL
    {"start":"2021-09-26","end":"2022-09-24","val":394_328_000_000,"fy":2024,"fp":"FY","form":"10-K","filed":"2024-11-01","accn":"0000320193-24-000123"},
    # ayni donem 2024 10-K'sinda tekrar raporlanmis (revize deger)
    {"start":"2022-09-25","end":"2023-09-30","val":383_290_000_000,"fy":2024,"fp":"FY","form":"10-K","filed":"2024-11-01","accn":"0000320193-24-000123"},
    # ceyreklik veri ayni listede
    {"start":"2023-04-02","end":"2023-07-01","val": 81_797_000_000,"fy":2023,"fp":"Q3","form":"10-Q","filed":"2023-08-04","accn":"0000320193-23-000077"},
    # AYNI GUN biten yil-basindan-beri satiri. Gercek 10-Q'lar ikisini birden
    # tasir ve ikisi de dogrudur; sahte veri bunu tasimazsa "ayni bitis =
    # ayni donem" varsayimi hicbir testte gorunmez (P-4). Canli olculdu
    # (17 Agu 2026): AAPL'in 2021-03-27'sinde 89.584 uc aylik, 201.023 alti
    # ayliktir ve IKISI DE ayni dosyalamadan gelir.
    {"start":"2022-09-25","end":"2023-07-01","val":293_787_000_000,"fy":2023,"fp":"Q3","form":"10-Q","filed":"2023-08-04","accn":"0000320193-23-000077"},
]}}

# Apple gerçekte "Revenues" DEGIL bunu kullanir; ilk aday 404 vermeli ki
# takma ad fallback zinciri gercekten sinansin.
GERCEK_GELIR_ETIKETI = "RevenueFromContractWithCustomerExcludingAssessedTax"

NET_INCOME = {"label": "Net Income (Loss)", "units": {"USD": [
    {"start":"2022-09-25","end":"2023-09-30","val":96_995_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03"},
]}}

def _satirlar(n: int) -> list[dict]:
    """companyfacts satirlari companyconcept ile AYNI sekle sahiptir. Sahte
    veri bunu taklit etmeli: bos sozlukler koymak, companyfacts'e dusen kodu
    sinanamaz hale getirir (P-4)."""
    return [
        {"start": f"{2016 + i}-09-25", "end": f"{2017 + i}-09-30",
         "val": 100_000_000_000 + i, "fy": 2017 + i, "fp": "FY",
         "form": "10-K", "filed": f"{2017 + i}-11-03"}
        for i in range(n)
    ]


DEI_FLOAT = {"label": "Entity Public Float", "units": {"USD": [
    {"end": "2024-03-29", "val": 2_600_000_000_000, "fy": 2024, "fp": "FY",
     "form": "10-K", "filed": "2024-11-01", "accn": "0000320193-24-000123"},
    {"end": "2025-03-28", "val": 2_900_000_000_000, "fy": 2025, "fp": "FY",
     "form": "10-K", "filed": "2025-10-31", "accn": "0000320193-25-000079"},
]}}

FACTS = {"facts": {"dei": {
    "EntityPublicFloat": DEI_FLOAT,
    "EntityCommonStockSharesOutstanding": {
        "label": "Entity Common Stock, Shares Outstanding",
        "units": {"shares": [{"end": "2025-10-17", "val": 14_840_000_000,
                              "fy": 2025, "fp": "FY", "form": "10-K",
                              "filed": "2025-10-31"}]},
    },
}, "us-gaap": {
    GERCEK_GELIR_ETIKETI: {"label": "Revenue from Contract with Customer",
                           "units": {"USD": _satirlar(3)}},
    "NetIncomeLoss":      {"label": "Net Income (Loss)", "units": {"USD": _satirlar(2)}},
    "SalesRevenueNet":    {"label": "Sales Revenue, Net", "units": {"USD": _satirlar(4)}},
    "Assets":             {"label": "Assets", "units": {"USD": _satirlar(1)}},
    "DeferredRevenue":    {"label": "Deferred Revenue", "units": {"USD": _satirlar(1)}},
}}}

# Apple 2018 oncesi geliri BASKA bir etiketle raporladi. Gercek dunyada
# oldugu gibi: iki etiket, kismi ortusme, farkli dosyalama tarihleri.
SALES_REVENUE = {"label": "Sales Revenue, Net", "units": {"USD": [
    {"start":"2016-09-25","end":"2017-09-30","val":229_234_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    {"start":"2017-10-01","end":"2018-09-29","val":265_595_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    {"start":"2018-09-30","end":"2019-09-28","val":260_174_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    # ORTUSEN donem: modern etikette de var, ama bu kayit DAHA ESKI sunulmus
    {"start":"2020-09-27","end":"2021-09-25","val":999_000_000_000,"fy":2021,"fp":"FY","form":"10-K","filed":"2021-10-29"},
]}}


# --------------------------------------------------------- sahte 10-K belgesi
# Gercek bir 10-K'nin iki ozelligini tasimali, yoksa metin araci sinanmis olmaz:
# (1) icindekiler tablosu ayni basliklari ONCE kisa baglantilar olarak icerir,
# (2) mali tablolar HTML tablosudur.
MDA_ISARET = "OPERATING MARGIN FELL BECAUSE OF PRICING"
VERGI_ISARET = "valuation allowance release of $5.0 billion"

BELGE_HTML = """<html><head><title>10-K</title>
<style>.x { color: red; }</style>
<script>var gizli = "SCRIPT ICERIGI SIZDI";</script></head>
<body>
<div style="display:none">false0001318605 http://fasb.org/us-gaap/2023#RevenueFromContractWithCustomerExcludingAssessedTax GIZLI IXBRL GURULTUSU</div>
<div>Table of Contents</div>
<div>Item 1. Business</div>
<div>Item 1A. Risk Factors</div>
<div>Item 3. Legal Proceedings</div>
<div>Item 7. Management's Discussion and Analysis</div>
<div>Item 8. Financial Statements</div>

<div>Item 1. Business</div>
<p>We design and sell things. """ + "Business filler. " * 40 + """</p>

<div>Item 1A. Risk Factors</div>
<p>Demand may fall. """ + "Risk filler. " * 40 + """</p>

<div>Item 7. Management's Discussion and Analysis</div>
<p>""" + MDA_ISARET + """ and mix. Research &amp; development rose.</p>
<table><tr><td>Revenue</td><td>391,035</td></tr>
<tr><td>Net income</td><td>93,736</td></tr></table>
<p>""" + "MD&A filler. " * 40 + """</p>

<div>Item 8. Financial Statements</div>
<p>""" + "Statement filler. " * 40 + """</p>

<div>Note 12. Income Taxes</div>
<p>The benefit includes a """ + VERGI_ISARET + """. """ + "Tax filler. " * 40 + """</p>
</body></html>"""


# Ikinci sahte belge: icindekiler tablosu UZUN, yani esik filtresini gecer.
# Bu durumda "hangi eslesme?" sorusunu esik degil, uzunluk kurali cozer.
UZUN_TOC_ISARET = "REAL SECTION SEVEN BODY"
BELGE_UZUN_TOC = """<html><body>
<div>Item 7. Management's Discussion and Analysis</div>
<p>""" + "See page 44 for a summary of results and outlook. " * 20 + """</p>
<div>Item 8. Financial Statements</div>
<p>""" + "See page 61 for the audited statements and notes. " * 20 + """</p>

<div>Item 7. Management's Discussion and Analysis</div>
<p>""" + UZUN_TOC_ISARET + """. """ + "Detailed discussion. " * 200 + """</p>
</body></html>"""


# Ucuncu belge: basliklar TABLO icinde. Gercek 10-K'larin cogu boyle yerlesir;
# metne cevrilince satir " | " ile basladigi icin satir-basi capasi tutmaz.
TABLO_ISARET = "TABLE LAYOUT SECTION BODY"
# Bolum SIFIRDAN ILERIDE basliyor (once kapak paragrafi) ve ICINDE gercek bir
# tablo var. Ikisi birlikte olmazsa "bolum kesilince tablo konumu kayiyor mu"
# sorusu olculemez: bolum 0'dan basliyorsa kaydirma zaten kimlik islemidir ve
# kaldirilsa bile hicbir test kirmiziya donmez (15 Agu 2026, enjeksiyon
# "KORUMASIZ" dedi).
BELGE_TABLO = """<html><body>
<p>""" + "Cover page filler. " * 30 + """</p>
<table><tr><td>Item 7.</td><td>Management's Discussion and Analysis</td></tr></table>
<p>""" + TABLO_ISARET + """. """ + "Discussion filler. " * 60 + """</p>
<table>
  <tr><td>Segment</td><td>Revenue</td></tr>
  <tr><td>Automotive</td><td>71,462</td></tr>
  <tr><td>Energy</td><td>10,086</td></tr>
</table>
<p>""" + "More discussion. " * 40 + """</p>
<table><tr><td>Item 8.</td><td>Financial Statements</td></tr></table>
<p>""" + "Statements filler. " * 60 + """</p>
</body></html>"""


# Dorduncu belge: "taxes" ifadesi IKI farkli baslikta geciyor; kisa olan bir
# atif, uzun olan asil dipnot.
VERGI_UZUN_ISARET = "REAL TAX FOOTNOTE BODY"
BELGE_IKI_VERGI = """<html><body>
<div>Note 3 – Deferred Taxes Summary</div>
<p>""" + "See Note 12 for the detail. " * 20 + """</p>
<div>Note 12 – Income Taxes</div>
<p>""" + VERGI_UZUN_ISARET + """. """ + "Tax detail. " * 200 + """</p>
</body></html>"""


# 8-K: govde birincil belgede DEGIL, ekte. Gercek olcum (14 Agu 2026): TSLA'nin
# 2026 Q2 teslimat bulteni `exhibit...htm` icinde; birincil belge kapak sayfasi.
EK_ISARET = "total deliveries of 480,126 vehicles"
BELGE_8K_KAPAK = """<html><body>
<div>Item 2.02 Results of Operations and Financial Condition</div>
<p>""" + "On July 2, 2026 the registrant issued a press release. " * 12 + """</p>
<div>Item 9.01 Financial Statements and Exhibits</div>
<p>99.1 Press Release dated July 2, 2026. """ + "Exhibit index filler. " * 12 + """</p>
</body></html>"""
# Ek belgeye GERCEK bir tablo eklendi: bu isin asil ornegi teslimat/uretim
# tablosu (adetler XBRL'de yok, metinde ve TABLODA var). Uc sey birlikte
# duruyor, cunku ucunun de ayri bir kod yolu var:
#   (1) veri tasiyan tablo (satir/hucre olarak donmeli),
#   (2) yerlesim icin kullanilan tek satirlik tablo (elenmeli ama SAYILMALI),
#   (3) gizli blok icindeki tablo (ne metne ne yapiya girmeli).
GIZLI_TABLO_ISARET = "HIDDEN TABLE CELL"
BELGE_8K_EK = """<html><body>
<p>Tesla reported production of 451,758 vehicles and """ + EK_ISARET + """
in the second quarter of 2026, and deployed 13.5 GWh of energy storage.</p>
<table><tr><td colspan="3">Quarterly summary</td></tr></table>
<table>
  <tr><td>Period</td><td>Production</td><td>Deliveries</td></tr>
  <tr><td>Q2 2026</td><td>451,758</td><td>480,126</td></tr>
  <tr><td>Q1 2026</td><td>362,615</td><td>336,681</td></tr>
  <tr><td></td><td></td><td></td></tr>
  <tr><td>Q2 2025</td><td>410,244</td><td>384,122</td></tr>
</table>
<div style="display:none"><table><tr><td>""" + GIZLI_TABLO_ISARET + """</td><td>x</td></tr>
<tr><td>y</td><td>z</td></tr></table></div>
<p>""" + "Press release filler. " * 60 + """</p>
</body></html>"""

# Dosya listesi ve BOYUTLAR gercek bir dosyalamadan kopyalandi (TSLA 8-K
# 0001628280-26-046717, index.json, 14 Agu 2026) - yalnizca sirket adlari
# degistirildi. Ilk surumde boyutlari kendim uydurmustum ve ekI en buyuk dosya
# yapmistim; gercek dosyalamada oyle DEGIL (kapak 26.572 > ek 13.243, ve en
# buyuk .htm goruntuleyici ciktisi olan R1.htm). Mock'u varsayimima gore
# yazdigim icin test yanlis bir kurali dogruluyordu (P-4).
# `type` alani da gercekte oldugu gibi: her dosya icin "text.gif" - yani belge
# TURU degil, EDGAR'in listede gosterdigi ikonun adi. Belge turunu buradan
# okumak mumkun degil.
DIZIN_JSON = {"directory": {"name": "/Archives/edgar/data/320193/000032019325000041",
                            "parent-dir": "/Archives/edgar/data/320193",
                            "item": [
    {"name": "0000320193-25-000041-index-headers.html", "type": "text.gif", "size": ""},
    {"name": "0000320193-25-000041-index.html", "type": "text.gif", "size": ""},
    {"name": "0000320193-25-000041-xbrl.zip", "type": "compressed.gif", "size": "10687"},
    {"name": "exhibit991.htm", "type": "text.gif", "size": "13243"},
    {"name": "FilingSummary.xml", "type": "text.gif", "size": "1694"},
    {"name": "MetaLinks.json", "type": "text.gif", "size": "17454"},
    {"name": "R1.htm", "type": "text.gif", "size": "38047"},
    {"name": "report.css", "type": "text.gif", "size": "2766"},
    {"name": "Show.js", "type": "text.gif", "size": "1084"},
    {"name": "aapl-8k.htm", "type": "text.gif", "size": "26572"},
    {"name": "aapl-8k.xsd", "type": "text.gif", "size": "1848"},
    {"name": "aapl-8k_lab.xml", "type": "text.gif", "size": "21885"},
    {"name": "aapl-8k_htm.xml", "type": "text.gif", "size": "2667"},
]}}


# ---- SEC `frames` ucu: bir donemin TUM sirketlerdeki degeri.
# Satir bicimi ve BOYUTLAR gercek yanittan kopyalandi (us-gaap/
# RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2025Q1, 14 Agu 2026).
# Apple satiri birebir gercek: {"accn":"0000320193-26-000013","cik":320193,
# "entityName":"Apple Inc.","loc":"US-CA","start":"2024-12-29",
# "end":"2025-03-29","val":95359000000}
#
# Dikkat edilen sey: bitis tarihleri AYNI DEGIL. Gercek cercevede en erken
# bitis 2025-02-23, en gec 2025-05-04 olarak olculdu - 70 gun. Sahte veri bunu
# taklit etmezse "ayni donemi karsilastiriyoruz" yanilgisini hicbir test
# yakalayamaz (P-4).
CERCEVE_GELIR = {
    "taxonomy": "us-gaap",
    "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "ccp": "CY2025Q1",
    "uom": "USD",
    "label": "Revenue from Contract with Customer, Excluding Assessed Tax",
    "pts": 4,
    "data": [
        {"accn": "0000320193-26-000013", "cik": 320193, "entityName": "Apple Inc.",
         "loc": "US-CA", "start": "2024-12-29", "end": "2025-03-29", "val": 95359000000},
        {"accn": "0000354950-25-000060", "cik": 354950, "entityName": "HOME DEPOT, INC.",
         "loc": "US-GA", "start": "2025-02-03", "end": "2025-05-04", "val": 39860000000},
        {"accn": "0000023217-25-000034", "cik": 23217, "entityName": "CONAGRA BRANDS, INC.",
         "loc": "US-IL", "start": "2024-11-25", "end": "2025-02-23", "val": 2843300000},
        {"accn": "0001069878-25-000011", "cik": 1069878, "entityName": "PRIVATE FILER LLC",
         "loc": None, "start": "2025-01-01", "end": "2025-03-31", "val": 121000000},
    ],
}

# Bilanco kalemi: SUREsel cerceve 404 verir, ANLIK olan calisir. Gercek olcum
# (14 Agu 2026): us-gaap/Assets/USD/CY2025Q1 -> 404, .../CY2025Q1I -> dolu.
# Anlik satirlarda `start` YOKTUR.
CERCEVE_VARLIK = {
    "taxonomy": "us-gaap", "tag": "Assets", "ccp": "CY2025Q1I", "uom": "USD",
    "label": "Assets", "pts": 2,
    "data": [
        {"accn": "0000320193-26-000013", "cik": 320193, "entityName": "Apple Inc.",
         "loc": "US-CA", "end": "2025-03-29", "val": 331233000000},
        {"accn": "0000001750-25-000519", "cik": 1750, "entityName": "AAR CORP",
         "loc": "US-IL", "end": "2025-02-28", "val": 2859100000},
    ],
}

CERCEVE_BOS = {"taxonomy": "us-gaap", "tag": "OperatingIncomeLoss",
               "ccp": "CY2025Q1", "uom": "USD", "label": "Operating Income (Loss)",
               "pts": 0, "data": []}


# ---- XBRL instance (C: boyutlu fact'ler)
# Kok, ad alanlari ve context bicimi GERCEK dosyalamadan alindi (TSLA FY2025
# 10-K, `tsla-20251231_htm.xml`, 14 Agu 2026 - birebir alintiyla dogrulandi).
# `<unit>` ve sayisal fact niteliklerinin (`decimals`, `unitRef`) yazimi ise
# XBRL 2.1 spesifikasyonundan kuruldu: 2,7 MB'lik dosyanin yalnizca basi
# okunabildi, o kisimda sayisal fact yok. Bu ayrim bilerek kayitli - ilk canli
# calistirma bunu dogrulayacak.
#
# Fixture'a bilerek konulan zor durumlar:
#   c-3/c-4  segment ekseninde iki uye; toplamlari konsolide ile TAM tutuyor
#   c-5      AYNI context'te iki boyut (segment + cografya) -> toplama girmemeli
#   c-6      cografya ekseni, gross_profit; uye toplami konsolideyle TUTMUYOR
#   c-7      typed dimension
#   c-8      `scenario` icinde boyut (segment yerine) - ikisi de gecerli
#   f-nil    xsi:nil fact
#   metin    sayisal olmayan fact
INSTANCE_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xml:lang="en-US"
  xmlns="http://www.xbrl.org/2003/instance"
  xmlns:dei="http://xbrl.sec.gov/dei/2025"
  xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
  xmlns:srt="http://fasb.org/srt/2025"
  xmlns:tsla="http://www.tesla.com/20251231"
  xmlns:us-gaap="http://fasb.org/us-gaap/2025"
  xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
  xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-2">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier></entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="c-3">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">
          tsla:AutomotiveSegmentMember
        </xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-4">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">
          tsla:EnergyGenerationAndStorageSegmentMember
        </xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-5">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier>
      <segment>
        <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">
          tsla:AutomotiveSegmentMember
        </xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="srt:StatementGeographicalAxis">
          country:US
        </xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-6">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier>
      <segment>
        <xbrldi:explicitMember dimension="srt:StatementGeographicalAxis">
          country:CN
        </xbrldi:explicitMember>
      </segment>
    </entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-7">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier>
      <segment>
        <xbrldi:typedMember dimension="tsla:PlantAxis">
          <tsla:PlantName>Fremont</tsla:PlantName>
        </xbrldi:typedMember>
      </segment>
    </entity>
    <period><instant>2025-12-31</instant></period>
  </context>
  <context id="c-8">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001318605</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    <scenario>
      <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">
        tsla:EnergyStorageMember
      </xbrldi:explicitMember>
    </scenario>
  </context>
  <unit id="usd"><measure>iso4217:USD</measure></unit>
  <unit id="usdPerShare">
    <divide>
      <unitNumerator><measure>iso4217:USD</measure></unitNumerator>
      <unitDenominator><measure>xbrli:shares</measure></unitDenominator>
    </divide>
  </unit>
  <us-gaap:Revenues contextRef="c-1" unitRef="usd" decimals="-6" id="f-1">97690000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-3" unitRef="usd" decimals="-6" id="f-2">77000000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-4" unitRef="usd" decimals="-6" id="f-3">20690000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-5" unitRef="usd" decimals="-6" id="f-4">41000000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c-8" unitRef="usd" decimals="-6" id="f-5">10100000000</us-gaap:Revenues>
  <us-gaap:SalesRevenueNet contextRef="c-3" unitRef="usd" decimals="-6" id="f-16">77000000000</us-gaap:SalesRevenueNet>
  <us-gaap:SalesRevenueNet contextRef="c-4" unitRef="usd" decimals="-6" id="f-17">20690000000</us-gaap:SalesRevenueNet>
  <us-gaap:GrossProfit contextRef="c-1" unitRef="usd" decimals="-6" id="f-6">17094000000</us-gaap:GrossProfit>
  <us-gaap:GrossProfit contextRef="c-6" unitRef="usd" decimals="-6" id="f-7">4000000000</us-gaap:GrossProfit>
  <us-gaap:OperatingIncomeLoss contextRef="c-1" unitRef="usd" xsi:nil="true" id="f-13"/>
  <us-gaap:OperatingIncomeLoss contextRef="c-3" unitRef="usd" decimals="-6" id="f-14">9000000000</us-gaap:OperatingIncomeLoss>
  <us-gaap:OperatingIncomeLoss contextRef="c-4" unitRef="usd" decimals="-6" id="f-15">1500000000</us-gaap:OperatingIncomeLoss>
  <us-gaap:Assets contextRef="c-7" unitRef="usd" decimals="-6" id="f-8">12000000000</us-gaap:Assets>
  <us-gaap:Assets contextRef="c-2" unitRef="usd" decimals="-6" id="f-9">130000000000</us-gaap:Assets>
  <us-gaap:EarningsPerShareDiluted contextRef="c-3" unitRef="usdPerShare" decimals="2" id="f-10">2.15</us-gaap:EarningsPerShareDiluted>
  <us-gaap:Revenues contextRef="c-6" unitRef="usd" xsi:nil="true" id="f-nil"/>
  <dei:EntityRegistrantName contextRef="c-1" id="f-11">Tesla, Inc.</dei:EntityRegistrantName>
  <tsla:SegmentDescription contextRef="c-3" id="f-12">Design and sale of vehicles</tsla:SegmentDescription>
</xbrl>"""

# Inline XBRL zorunlulugundan onceki dosyalama: `_htm.xml` yok, dosyalayanin
# sundugu bagimsiz instance var. Linkbase'ler ayni uzantiyi paylasiyor.
DIZIN_ESKI_JSON = {"directory": {"item": [
    # Sira bilerek boyle: linkbase'ler instance'tan ONCE. SEC index.json'in
    # siralamasini hicbir yerde garanti etmiyor; ilk .xml'i alan bir kod
    # olculen dosyalamada kazara dogru calisiyordu.
    {"name": "tsla-20181231_lab.xml", "type": "text.gif", "size": "800"},
    {"name": "tsla-20181231_def.xml", "type": "text.gif", "size": "700"},
    {"name": "tsla-20181231_cal.xml", "type": "text.gif", "size": "500"},
    {"name": "tsla-20181231_pre.xml", "type": "text.gif", "size": "400"},
    {"name": "MetaLinks.json", "type": "text.gif", "size": "600"},
    {"name": "tsla-20181231.xml", "type": "text.gif", "size": "3100"},
    {"name": "tsla-20181231.xsd", "type": "text.gif", "size": "900"},
    {"name": "aapl-20240928.htm", "type": "text.gif", "size": "2400"},
]}}

# ---- Etiket linkbase'i (`*_lab.xml`).
# Yapi 15 Agu 2026'da canli olculdu (tsla-20251231_lab.xml): uc parca - `loc`
# elemani QName'i, `label` elemani metni tasiyor, ikisini `labelArc` BAGLIYOR.
# Sahte veri gercek dosyanin uc ozelligini tasimali, yoksa kod sinanmis olmaz:
#   (1) ayni eleman birden fazla ROLDE etiketlenir (standart rol kazanmali),
#   (2) `loc_`/`lab_` isimlendirmesi bir aliskanlik; yay olmadan baglanti yok,
#   (3) etiketi olmayan elemanlar vardir (us-gaap:GrossProfit burada yok).
LAB_XML = """<?xml version="1.0" encoding="utf-8"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase"
               xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:labelLink xlink:type="extended" xlink:role="http://www.xbrl.org/2003/role/link">
    <link:loc xlink:type="locator" xlink:label="loc_1"
      xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_StatementBusinessSegmentsAxis"/>
    <link:label xlink:type="resource" xlink:label="lab_1" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/terseLabel">Segments</link:label>
    <link:label xlink:type="resource" xlink:label="lab_1" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/label">Segment Reporting Information [Axis]</link:label>
    <link:labelArc xlink:type="arc" xlink:from="loc_1" xlink:to="lab_1"
      xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label" order="1"/>

    <link:loc xlink:type="locator" xlink:label="loc_2"
      xlink:href="tsla-20251231.xsd#tsla_AutomotiveSegmentMember"/>
    <link:label xlink:type="resource" xlink:label="lab_2" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/label">Automotive Segment [Member]</link:label>
    <link:labelArc xlink:type="arc" xlink:from="loc_2" xlink:to="lab_2"
      xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label" order="1"/>

    <link:loc xlink:type="locator" xlink:label="loc_3"
      xlink:href="tsla-20251231.xsd#tsla_EnergyGenerationAndStorageSegmentMember"/>
    <link:label xlink:type="resource" xlink:label="lab_3" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/label">Energy Generation and Storage Segment [Member]</link:label>
    <link:labelArc xlink:type="arc" xlink:from="loc_3" xlink:to="lab_3"
      xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label" order="1"/>

    <link:loc xlink:type="locator" xlink:label="loc_4"
      xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_Revenues"/>
    <link:label xlink:type="resource" xlink:label="lab_4" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/label">Revenues</link:label>
    <link:label xlink:type="resource" xlink:label="lab_4" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/documentation">Amount of revenue recognized from goods sold, services rendered.</link:label>
    <link:labelArc xlink:type="arc" xlink:from="loc_4" xlink:to="lab_4"
      xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label" order="1"/>

    <!-- Yay YOK: konum ve etiket var ama baglanti kurulmamis. Isimlendirmeye
         guvenen bir kod bunu yine de eslestirir. -->
    <link:loc xlink:type="locator" xlink:label="loc_5"
      xlink:href="tsla-20251231.xsd#tsla_PlantAxis"/>
    <link:label xlink:type="resource" xlink:label="lab_5" xml:lang="en-US"
      xlink:role="http://www.xbrl.org/2003/role/label">Plant [Axis]</link:label>
  </link:labelLink>
</link:linkbase>
"""


# XBRL var ama ETIKET LINKBASE'I YOK. Gercekte olabilir: eski dosyalamalarda
# etiket linkbase'i ayri bir ek olarak sunulmayabiliyor. Kod bu durumda adlari
# QName olarak gostermeye devam etmeli - cevabi dusurmemeli.
DIZIN_ETIKETSIZ_JSON = {"directory": {"item": [
    {"name": "aapl-20250628.htm", "type": "text.gif", "size": "2400"},
    {"name": "aapl-20250628_htm.xml", "type": "text.gif", "size": "2667"},
    {"name": "aapl-20250628.xsd", "type": "text.gif", "size": "900"},
]}}

DIZIN_XBRLSIZ_JSON = {"directory": {"item": [
    {"name": "aapl-8k.htm", "type": "text.gif", "size": "2400"},
    {"name": "report.css", "type": "text.gif", "size": "100"},
]}}


# WMT tipi: mali yil 31 Ocak'ta biter, yani KENDI ceyrekleri onceki takvim
# yilinda biter. Ceyreklik satirlar ve ANLIK (bilanco) satirlar birlikte -
# ikisi de 15 Agu 2026'da bulunan iki ayri sessiz yanlisligin fixture'i.
OCAK_SONU = {"cik": 104169, "taxonomy": "us-gaap", "tag": "Revenues",
             "label": "Revenues", "entityName": "WALMART INC.", "units": {"USD": [
    {"start": "2025-02-01", "end": "2026-01-31", "val": 700000, "fy": 2026,
     "fp": "FY", "form": "10-K", "filed": "2026-03-20", "accn": "a-1"},
    {"start": "2024-02-01", "end": "2025-01-31", "val": 650000, "fy": 2025,
     "fp": "FY", "form": "10-K", "filed": "2025-03-20", "accn": "a-0"},
    # FY2026'nin ilk ceyregi: 2025 takvim yilinda bitiyor
    {"start": "2025-02-01", "end": "2025-04-30", "val": 165000, "fy": 2026,
     "fp": "Q1", "form": "10-Q", "filed": "2025-05-15", "accn": "a-2"},
    {"start": "2025-05-01", "end": "2025-07-31", "val": 169000, "fy": 2026,
     "fp": "Q2", "form": "10-Q", "filed": "2025-08-15", "accn": "a-3"},
]}}

# Bilanco kalemi: yalnizca ANLIK satirlar, hem yil sonu hem ceyrek sonlari
ANLIK = {"cik": 104169, "taxonomy": "us-gaap", "tag": "Assets", "label": "Assets",
         "entityName": "WALMART INC.", "units": {"USD": [
    {"end": "2026-01-31", "val": 260000, "fy": 2026, "fp": "FY",
     "form": "10-K", "filed": "2026-03-20", "accn": "a-1"},
    {"end": "2025-01-31", "val": 250000, "fy": 2025, "fp": "FY",
     "form": "10-K", "filed": "2025-03-20", "accn": "a-0"},
    {"end": "2025-04-30", "val": 253000, "fy": 2026, "fp": "Q1",
     "form": "10-Q", "filed": "2025-05-15", "accn": "a-2"},
    {"end": "2025-07-31", "val": 256000, "fy": 2026, "fp": "Q2",
     "form": "10-Q", "filed": "2025-08-15", "accn": "a-3"},
]}}


# Revize edilip GERI ALINAN deger: 100 -> 90 -> 100. Farkli degerlerin
# sonuncusu 90'dir ama EN SON DOSYALANAN deger 100'dur. Bu ayrimi tasimayan
# sahte veri, "latest_value" hatasini yakalayamaz (P-4).
GERI_ALINAN = {"cik": 789019, "taxonomy": "us-gaap", "tag": "Revenues",
               "label": "Revenues", "entityName": "MICROSOFT CORP", "units": {"USD": [
    {"start": "2024-07-01", "end": "2025-06-30", "val": 100, "fy": 2025, "fp": "FY",
     "form": "10-K", "filed": "2025-07-30", "accn": "m-1"},
    {"start": "2024-07-01", "end": "2025-06-30", "val": 90, "fy": 2026, "fp": "Q2",
     "form": "10-Q", "filed": "2026-01-30", "accn": "m-2"},
    {"start": "2024-07-01", "end": "2025-06-30", "val": 100, "fy": 2026, "fp": "FY",
     "form": "10-K", "filed": "2026-07-30", "accn": "m-3"},
]}}


# 52/53 haftalik takvim: yil sonu Aralik ile Ocak arasinda gidip geliyor.
# Kellanova'nin gercek 10-K donem sonlari (dei `fy` degerleriyle birlikte).
YIL_SONU_OYNAK = {"cik": 55067, "taxonomy": "us-gaap", "tag": "Revenues",
                  "label": "Revenues", "entityName": "KELLANOVA", "units": {"USD": [
    {"start": "2021-01-03", "end": "2022-01-01", "val": 14181, "fy": 2021, "fp": "FY",
     "form": "10-K", "filed": "2022-02-22", "accn": "k-1"},
    {"start": "2022-01-02", "end": "2022-12-31", "val": 15315, "fy": 2022, "fp": "FY",
     "form": "10-K", "filed": "2023-02-21", "accn": "k-2"},
    {"start": "2023-01-01", "end": "2023-12-30", "val": 13122, "fy": 2023, "fp": "FY",
     "form": "10-K", "filed": "2024-02-20", "accn": "k-3"},
    {"start": "2023-12-31", "end": "2025-01-04", "val": 12749, "fy": 2024, "fp": "FY",
     "form": "10-K", "filed": "2025-02-18", "accn": "k-4"},
]}}

YIL_SONU_OYNAK_ANLIK = {"cik": 55067, "taxonomy": "us-gaap", "tag": "Assets",
                        "label": "Assets", "entityName": "KELLANOVA", "units": {"USD": [
    {"end": "2022-01-01", "val": 18178, "fy": 2021, "fp": "FY",
     "form": "10-K", "filed": "2022-02-22", "accn": "k-1"},
    {"end": "2022-12-31", "val": 18496, "fy": 2022, "fp": "FY",
     "form": "10-K", "filed": "2023-02-21", "accn": "k-2"},
    {"end": "2023-12-30", "val": 15621, "fy": 2023, "fp": "FY",
     "form": "10-K", "filed": "2024-02-20", "accn": "k-3"},
    {"end": "2025-01-04", "val": 15282, "fy": 2024, "fp": "FY",
     "form": "10-K", "filed": "2025-02-18", "accn": "k-4"},
]}}


# ---- SEC'in ESKI dosyalama akisi (`filings.files[]` altinda adi gecen dosya).
# Bicim olculdu (15 Agu 2026, CIK0001318605-submissions-001.json): ust duzeyde
# `recent` ile AYNI paralel diziler, saran nesne YOK. `primaryDocument`
# anahtarinin BULUNMAMASI da olculdu - sahte veri onu tasisaydi, eksik alani
# ele alan kod hic sinanmamis olurdu (P-4).
EK_SUBS = {
    "accessionNumber": ["0000320193-99-000010", "0000320193-97-000005"],
    "form":            ["10-K", "8-K"],
    "filingDate":      ["1999-12-22", "1997-12-19"],
    "reportDate":      ["1999-09-25", ""],
}

# ---- EDGAR tam metin aramasi (efts.sec.gov/LATEST/search-index).
# Yanit bicimi 15 Agu 2026'da canli olctugum yanittan kopyalandi. Iki ozelligi
# taklit etmesi sart:
#   (1) `_id` = "<erisim numarasi>:<belge adi>" - vurus DOSYALAMA degil BELGE,
#   (2) ilk vurus bir EK (SUPPLY AGREEMENT), yillik raporun kendisi degil.
# Ikinci hit'in CIK'i company_tickers.json'da YOK: ticker cozulemeyen vurus
# yolu ancak boyle sinanir.
FTS = {
    "took": 12, "timed_out": False,
    "_shards": {"total": 3, "successful": 3, "skipped": 0, "failed": 0},
    "hits": {
        "total": {"value": 12, "relation": "eq"},
        "max_score": 6.45,
        "hits": [
            {"_index": "edgar_file",
             "_id": "0001193125-12-081990:d279413dex1050.htm",
             "_score": 6.45,
             "_source": {"ciks": ["0001318605"], "period_ending": "2011-12-31",
                         "display_names": ["Tesla, Inc.  (TSLA)  (CIK 0001318605)"],
                         "root_forms": ["10-K"], "file_date": "2012-02-27",
                         "form": "10-K", "adsh": "0001193125-12-081990",
                         "file_type": "EX-10.50",
                         "file_description": "SUPPLY AGREEMENT", "items": []}},
            {"_index": "edgar_file",
             "_id": "0000999999-24-000001:fund-main.htm",
             "_score": 3.10,
             "_source": {"ciks": ["0000999999"], "period_ending": None,
                         "display_names": ["Example Fund Trust  (CIK 0000999999)"],
                         "root_forms": ["10-K"], "file_date": "2024-05-02",
                         "form": "10-K", "adsh": "0000999999-24-000001",
                         "file_type": "10-K", "file_description": "10-K",
                         "items": []}},
        ],
    },
    "query": {"query_string": {"query": "\"tariff\"", "size": 100}},
}

FTS_BOS = {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}

# Elasticsearch buyuk kumelerde sayiyi ALT SINIR olarak bildirir.
FTS_ALT_SINIR = {"hits": {"total": {"value": 10000, "relation": "gte"},
                          "hits": FTS["hits"]["hits"][:1]}}

# Olculdu (15 Agu 2026): `from=9990` istegine SEC sonuc kumesi degil bu govdeyi
# donuyor. Bos sonuc saymak "hicbir sey bulunamadi" diye okunurdu.
FTS_HATA = {"error": "Result window is too large, from + size must be less "
                     "than or equal to: [10000] but was [10090].",
            "errorType": "illegal_argument_exception"}



# ---- Form 4 (icerideki islemleri). Yapi 16 Agu 2026'da GERCEK dosyalamalardan
# olculdu (NVDA 0001310264-26-000008 ve 0001197647-26-000007). Taklit edilmesi
# sart olan ozellikler:
#   (1) degerler `<value>` sarmalayicisi icinde - eleman metnini dogrudan
#       okuyan kod bos alir,
#   (2) fiyat alani `<footnoteId>` de tasiyabiliyor,
#   (3) `nonDerivativeHolding` (islem DEGIL, mevcut pozisyon) ayni tabloda,
#   (4) turev tablosu ayri: opsiyon/RSU satirlari hisse satirlariyla ayni
#       listeye konursa ayni olay iki kez sayilir,
#   (5) dolayli sahiplikte `natureOfOwnership` ("By Trust").
FORM4_XML = """<?xml version="1.0"?><ownershipDocument>
<documentType>4</documentType><periodOfReport>2026-02-18</periodOfReport>
<issuer><issuerCik>0000320193</issuerCik><issuerName>Apple Inc.</issuerName>
<issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0001214128</rptOwnerCik>
<rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer>
<isTenPercentOwner>0</isTenPercentOwner><officerTitle>Chief Executive Officer</officerTitle>
</reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2026-02-18</value></transactionDate>
<transactionCoding><transactionCode>A</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>511000</value></transactionShares>
<transactionPricePerShare><value>0</value><footnoteId id="F1"/></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>3789000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
</nonDerivativeTransaction>
<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2026-02-18</value></transactionDate>
<transactionCoding><transactionCode>F</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>240000</value></transactionShares>
<transactionPricePerShare><value>243.15</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>3549000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
</nonDerivativeTransaction>
<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2026-02-19</value></transactionDate>
<transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>100000</value></transactionShares>
<transactionPricePerShare><value>245.00</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>3449000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
<natureOfOwnership><value>By Trust</value></natureOfOwnership></ownershipNature>
</nonDerivativeTransaction>
<nonDerivativeHolding><securityTitle><value>Common Stock</value></securityTitle>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>57378</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
<natureOfOwnership><value>By 401(k) plan</value></natureOfOwnership></ownershipNature></nonDerivativeHolding>
</nonDerivativeTable>
<derivativeTable>
<derivativeTransaction><securityTitle><value>Restricted Stock Unit</value></securityTitle>
<transactionDate><value>2026-02-18</value></transactionDate>
<transactionCoding><transactionCode>M</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>511000</value></transactionShares>
<transactionPricePerShare><value>0</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
</derivativeTransaction>
</derivativeTable></ownershipDocument>"""

# ---- 13F. Ad alani ve alan adlari Berkshire'in 2026 Q2 dosyalamasindan
# olculdu. Iki satir AYNI ihracci: bir yonetici her alt yonetici icin ayri
# satir yaziyor ve bunlar mukerrer DEGIL, ayni pozisyonun parcalari.
T13F_TABLO = """<?xml version="1.0"?><informationTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
<value>86841985318</value><shrsOrPrnAmt><sshPrnamt>669429166</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
<investmentDiscretion>DFND</investmentDiscretion><otherManager>4,11</otherManager>
<votingAuthority><Sole>669429166</Sole><Shared>0</Shared><None>0</None></votingAuthority></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
<value>1000000000</value><shrsOrPrnAmt><sshPrnamt>7708000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
<investmentDiscretion>DFND</investmentDiscretion><otherManager>4</otherManager>
<votingAuthority><Sole>7708000</Sole><Shared>0</Shared><None>0</None></votingAuthority></infoTable>
<infoTable><nameOfIssuer>ALLY FINL INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>02005N100</cusip>
<value>577211815</value><shrsOrPrnAmt><sshPrnamt>12561737</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
<investmentDiscretion>DFND</investmentDiscretion>
<votingAuthority><Sole>12561737</Sole><Shared>0</Shared><None>0</None></votingAuthority></infoTable>
</informationTable>"""

T13F_KAPAK = """<?xml version="1.0"?><edgarSubmission>
<formData><coverPage><filingManager><name>Apple Asset Management</name></filingManager>
<reportType>13F HOLDINGS REPORT</reportType></coverPage>
<summaryPage><otherIncludedManagersCount>14</otherIncludedManagersCount>
<tableEntryTotal>3</tableEntryTotal><tableValueTotal>88419197133</tableValueTotal></summaryPage></formData>
<headerData><filerInfo><periodOfReport>03-31-2026</periodOfReport></filerInfo></headerData>
</edgarSubmission>"""

# 13F dizininde bilgi tablosunun adi RASTGELE ("56757.xml", "18337.xml"
# olculdu). Bu yuzden ad tahmin edilemez, dizinden bulunmasi gerekiyor.
DIZIN_13F = {"directory": {"item": [
    {"name": "0000320193-26-000900-index.html", "type": "text.gif", "size": ""},
    {"name": "primary_doc.xml", "type": "text.gif", "size": "5555"},
    {"name": "77219.xml", "type": "text.gif", "size": "44724"},
]}}


ISTEK_KAYDI: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    ISTEK_KAYDI.append(u)
    assert "@" in request.headers["User-Agent"], "SEC User-Agent e-posta icermeli"
    if "company_tickers" in u:
        return httpx.Response(200, json=TICKERS)
    if "efts.sec.gov" in u:
        if "q=bos" in u:
            return httpx.Response(200, json=FTS_BOS)
        if "q=altsinir" in u:
            return httpx.Response(200, json=FTS_ALT_SINIR)
        if "q=hata" in u:
            return httpx.Response(200, json=FTS_HATA)
        return httpx.Response(200, json=FTS)
    if "-submissions-" in u:            # eski akis dosyasi
        return httpx.Response(200, json=EK_SUBS)
    if "/submissions/" in u:
        # Var olmayan CIK'e SEC 404 doner. Sahte veri her CIK'e ayni yaniti
        # verseydi "bilinmeyen numara" yolu hic sinanmazdi (P-4).
        bilinen = {str(r["cik_str"]).zfill(10) for r in TICKERS.values()}
        if not any(c in u for c in bilinen):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=SUBS)
    if "companyfacts" in u:
        return httpx.Response(200, json=FACTS)
    if u.endswith("_lab.xml"):
        return httpx.Response(200, text=LAB_XML,
                              headers={"Content-Type": "application/xml"})
    if u.endswith("_htm.xml") or u.endswith("tsla-20181231.xml"):
        return httpx.Response(200, text=INSTANCE_XML,
                              headers={"Content-Type": "application/xml"})
    if "/api/xbrl/frames/" in u:
        if "/Assets/USD/CY2025Q1I.json" in u:
            return httpx.Response(200, json=CERCEVE_VARLIK)
        if "/OperatingIncomeLoss/USD/CY2025Q1.json" in u:
            return httpx.Response(200, json=CERCEVE_BOS)
        if "RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2025Q1.json" in u:
            return httpx.Response(200, json=CERCEVE_GELIR)
        return httpx.Response(404, json={"error": "not found"})
    if u.endswith("/index.json"):
        if "000032019326000900" in u:
            return httpx.Response(200, json=DIZIN_13F)
        if "000032019324000123" in u:
            return httpx.Response(200, json=DIZIN_ESKI_JSON)
        if "000032019325000058" in u:
            return httpx.Response(200, json=DIZIN_ETIKETSIZ_JSON)
        if "000032019325000012" in u:
            return httpx.Response(200, json=DIZIN_XBRLSIZ_JSON)
        return httpx.Response(200, json=DIZIN_JSON)
    if "/Archives/edgar/data/" in u:
        if "wf-form4_123.xml" in u:
            return httpx.Response(200, text=FORM4_XML,
                                  headers={"Content-Type": "application/xml"})
        if u.endswith("/primary_doc.xml"):
            return httpx.Response(200, text=T13F_KAPAK,
                                  headers={"Content-Type": "application/xml"})
        if u.endswith("/77219.xml"):
            return httpx.Response(200, text=T13F_TABLO,
                                  headers={"Content-Type": "application/xml"})
        if "exhibit991.htm" in u:
            return httpx.Response(200, text=BELGE_8K_EK,
                                  headers={"Content-Type": "text/html"})
        if "aapl-20250628.htm" in u:
            return httpx.Response(200, text=BELGE_TABLO,
                                  headers={"Content-Type": "text/html"})
        if "form4.xml" in u:
            return httpx.Response(200, text=BELGE_IKI_VERGI,
                                  headers={"Content-Type": "text/html"})
        if "aapl-8k.htm" in u:
            return httpx.Response(200, text=BELGE_8K_KAPAK,
                                  headers={"Content-Type": "text/html"})
        if "aapl-20240928.htm" in u:
            return httpx.Response(200, text=BELGE_UZUN_TOC,
                                  headers={"Content-Type": "text/html"})
        return httpx.Response(200, text=BELGE_HTML,
                              headers={"Content-Type": "text/html"})
    if "companyconcept" in u and "CIK0000055067" in u:
        return httpx.Response(200, json=YIL_SONU_OYNAK_ANLIK if "/Assets" in u
                              else YIL_SONU_OYNAK)
    if "companyconcept" in u and "CIK0000789019" in u:
        return httpx.Response(200, json=GERI_ALINAN)
    if "companyconcept" in u and "CIK0000104169" in u:
        return httpx.Response(200, json=ANLIK if "/Assets" in u else OCAK_SONU)
    if "companyconcept" in u:
        if "/dei/EntityPublicFloat" in u:
            return httpx.Response(200, json=DEI_FLOAT)
        if "/dei/" in u:
            return httpx.Response(404)      # dei'de olmayan etiket
        if GERCEK_GELIR_ETIKETI in u:
            return httpx.Response(200, json=CONCEPT)
        if "NetIncomeLoss" in u:
            return httpx.Response(200, json=NET_INCOME)
        if "SalesRevenueNet" in u:
            return httpx.Response(200, json=SALES_REVENUE)
        return httpx.Response(404)          # SEC bilinmeyen etikete 404 doner
    return httpx.Response(404)

@pytest.fixture
def srv(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@ornek.com")
    # Kesim ortam degiskeni butun araclari etkiliyor: kabukta unutulmus bir
    # `SEC_AS_OF`, test paketinin tamamini baska bir dunyada kosturur ve
    # basarisizlik kodda aranir. Testler kendi ortamini kendi kurar.
    monkeypatch.delenv("SEC_AS_OF", raising=False)
    from edgar_mcp import server as s
    from edgar_mcp.client import EdgarClient
    c = EdgarClient()
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                headers={"User-Agent": "Test Runner test@ornek.com"})
    s._client = c
    # Belge metni onbellegi modul duzeyinde: testler arasi sizarsa bir test
    # otekinin onbellegini kullanir ve "indirildi mi" olcumu anlamsizlasir.
    s._BELGE_METNI.clear()
    s._client._index_cache.clear()
    s._client._extra_cache.clear()
    s._ETIKET.clear()
    s._CERCEVE.clear()
    s._INSTANCE.clear()
    return s

@pytest.mark.anyio
async def test_profile(srv):
    p = await srv.get_company_profile(ticker="aapl")
    assert p.cik == "0000320193" and p.name == "Apple Inc." and p.ticker == "AAPL"

@pytest.mark.anyio
async def test_filings_filter(srv):
    """Karisik form turleri arasindan SADECE istenen tur donmeli."""
    s = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=5)
    assert [x.form for x in s.filings] == ["10-K", "10-K"], "10-K disi form sizdi"
    assert s.filings[0].primary_document_url.endswith(
        "000032019325000073/aapl-20250927.htm"
    )


@pytest.mark.anyio
async def test_filings_filtresiz_hepsini_dondurur(srv):
    """Kontrol testi: filtre yokken gercekten baska turler var mi?
    Bu olmadan yukaridaki test bos bir kumeyi 'filtrelenmis' sanabilir."""
    s = await srv.list_recent_filings(ticker="AAPL", limit=10)
    assert {x.form for x in s.filings} == {"10-K", "10-Q", "8-K", "4", "13F-HR"}


@pytest.mark.anyio
async def test_filings_limit_uygulanir(srv):
    s = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert len(s.filings) == 2


@pytest.mark.anyio
async def test_filings_sayfalama_bilgisi_verir(srv):
    """Standart §16: limit tek basina yetmez. Model, listenin tamami mi yoksa
    kirpilmis mi oldugunu bilmeden 'sirketin N dosyalamasi var' diyebilir."""
    kirpik = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert kirpik.total_matching == 7
    assert kirpik.returned == 2
    assert kirpik.has_more is True

    tam = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert tam.total_matching == 7
    assert tam.returned == 7
    # Sayfa tamamlandi ama SEC'in `recent` akisi disinda dosyalamalar var:
    # `has_more` yine True, sebebi ayri alanda. "Hepsini gordum" sonucuna
    # varmak, otuz yillik gecmisi olan bir sirkette yanlis olurdu.
    assert tam.has_more is True
    assert tam.older_filings_exist is True


@pytest.mark.anyio
async def test_filings_sayfalama_filtreyle_birlikte_dogru(srv):
    """total_matching, filtre UYGULANDIKTAN sonraki sayi olmali - filtresiz
    toplami raporlamak modeli yaniltir."""
    s = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=1)
    assert s.total_matching == 2, "filtre disi dosyalamalar sayima girmis"
    assert s.returned == 1
    assert s.has_more is True


@pytest.mark.anyio
async def test_seri_sayfalama_bilgisi_verir(srv):
    az = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=2)
    assert az.returned == 2
    assert az.has_more is True
    assert az.total_periods > 2

    hepsi = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    assert hepsi.has_more is False
    assert hepsi.returned == hepsi.total_periods


@pytest.mark.anyio
async def test_seri_kirpmada_EN_YENI_donemler_kalir(srv):
    """Kirpma yonu onemli: model trend analizi yapiyorsa en yeni donemleri
    gormeli, en eskileri degil."""
    az = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=2)
    hepsi = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    assert [p.period_end for p in az.points] == [p.period_end for p in hepsi.points[-2:]]


# ============================================== §19: annotations ipucudur
@pytest.mark.anyio
async def test_tum_araclar_salt_okunur_ilan_ediyor():
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        a = t.annotations
        assert a is not None, f"{t.name}: annotations yok"
        assert a.read_only_hint is True, f"{t.name}: read_only_hint True degil"
        assert a.destructive_hint is False, f"{t.name}: destructive_hint False degil"


def test_kodda_hicbir_yazma_yolu_yok():
    """Standart §19: annotations bir IPUCUDUR, garanti degil. Gercek garanti,
    yazma yolunun hic BULUNMAMASI. Bu test ipucunu kanita cevirir - biri
    ileride bir POST ekler ve read_only_hint'i guncellemeyi unutursa yakalanir."""
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    yasak = re.compile(r"\.(post|put|patch|delete)\s*\(", re.I)
    for f in kok.glob("*.py"):
        metin = f.read_text(encoding="utf-8")
        bulunan = yasak.findall(metin)
        assert not bulunan, f"{f.name} yazma cagrisi iceriyor: {bulunan}"


@pytest.mark.anyio
async def test_donem_yili_bitis_tarihinden_gelir(srv):
    """SEC'in fy alani DOSYALAMANIN yilidir. Bir 10-K'daki 3 yillik karsilastirmanin
    ucu de ayni fy'ye sahiptir; yil mutlaka donem sonundan turetilmelidir."""
    s = await srv.get_concept_series(
        ticker="AAPL", concept=GERCEK_GELIR_ETIKETI, period="annual"
    )
    assert [p.fiscal_year for p in s.points] == [2021, 2022, 2023]
    deger = {p.fiscal_year: p.value for p in s.points}
    assert deger[2021] == 365_817_000_000
    assert deger[2022] == 394_328_000_000


@pytest.mark.anyio
async def test_ceyreklik_yillik_seriye_sizmaz(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", period="annual")
    assert all(300 <= p.days <= 400 for p in s.points)
    assert 81_797_000_000 not in [p.value for p in s.points]


@pytest.mark.anyio
async def test_ayni_donem_tekrar_raporlanirsa_en_guncel_alinir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", period="annual")
    fy23 = [p for p in s.points if p.fiscal_year == 2023][0]
    assert fy23.filed == "2024-11-01"
    assert fy23.value == 383_290_000_000


@pytest.mark.anyio
async def test_ua_zorunlu(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    from edgar_mcp.client import EdgarClient
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        EdgarClient()

@pytest.fixture
def anyio_backend(): return "asyncio"


# ---------------------------------------------------------------- ISS-1: takma adlar
@pytest.mark.anyio
async def test_takma_ad_gercek_etikete_cozulur(srv):
    """'revenue' takma adi, sirketin fiilen kullandigi etikete cozulmeli."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert GERCEK_GELIR_ETIKETI in s.resolved_concepts
    assert s.requested_concept == "revenue"


@pytest.mark.anyio
async def test_takma_ad_ilk_aday_404_verirse_sonrakini_dener(srv):
    """Fallback zinciri gercekten calisiyor mu: 'Revenues' 404, ucuncu aday tutuyor."""
    ISTEK_KAYDI.clear()
    await srv.get_concept_series(ticker="AAPL", concept="revenue")
    denenen = [u.rsplit("/", 1)[-1].replace(".json", "")
               for u in ISTEK_KAYDI if "companyconcept" in u]
    assert denenen[0] == GERCEK_GELIR_ETIKETI, "aday sirasi bozulmus"


@pytest.mark.anyio
async def test_ham_gaap_etiketi_de_kabul_edilir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="NetIncomeLoss")
    assert s.resolved_concepts == ["NetIncomeLoss"]


@pytest.mark.anyio
async def test_buyuk_harf_ve_bosluk_toleransi(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="  REVENUE ")
    assert GERCEK_GELIR_ETIKETI in s.resolved_concepts


@pytest.mark.anyio
async def test_bilinmeyen_etiket_eyleme_donusturulebilir_hata_verir(srv):
    """Standart §18: hata mesaji modele ne yapacagini soylemeli."""
    with pytest.raises(ValueError) as e:
        await srv.get_concept_series(ticker="AAPL", concept="UyduRulmusEtiket")
    m = str(e.value)
    assert "sec_edgar_list_available_concepts" in m, "kesif araci onerilmiyor"
    assert "revenue" in m, "gecerli takma adlar listelenmiyor"


# ---------------------------------------------------------------- kesif araci
@pytest.mark.anyio
async def test_kesif_araci_arama_filtreler(srv):
    k = await srv.list_available_concepts(ticker="AAPL", search="revenue")
    etiketler = [c.tag for c in k.concepts]
    assert GERCEK_GELIR_ETIKETI in etiketler
    assert "DeferredRevenue" in etiketler
    assert "Assets" not in etiketler, "filtre disi etiket sizdi"


@pytest.mark.anyio
async def test_kesif_araci_etiket_metninde_de_arar(srv):
    k = await srv.list_available_concepts(ticker="AAPL", search="net income")
    assert "NetIncomeLoss" in [c.tag for c in k.concepts]


@pytest.mark.anyio
async def test_kesif_araci_sayfalama_bilgisi_verir(srv):
    """Standart §16: limit tek basina yetmez, toplam ve has_more da lazim."""
    k = await srv.list_available_concepts(ticker="AAPL", limit=2)
    assert k.total_matching == 5
    assert k.returned == 2
    assert len(k.concepts) == 2
    assert k.has_more is True

    hepsi = await srv.list_available_concepts(ticker="AAPL", limit=50)
    assert hepsi.has_more is False


@pytest.mark.anyio
async def test_kesif_araci_veri_yogunluguna_gore_siralar(srv):
    k = await srv.list_available_concepts(ticker="AAPL", limit=50)
    sayilar = [c.data_points for c in k.concepts]
    assert sayilar == sorted(sayilar, reverse=True), "azalan siralama bozuk"
    assert k.concepts[0].data_points == max(sayilar)


@pytest.mark.anyio
async def test_companyfacts_bir_kez_cekilir(srv):
    """companyfacts birkac MB; iki cagri tek HTTP istegi yapmali (onbellek)."""
    ISTEK_KAYDI.clear()
    await srv.list_available_concepts(ticker="AAPL")
    await srv.list_available_concepts(ticker="AAPL", search="assets")
    assert sum("companyfacts" in u for u in ISTEK_KAYDI) == 1


# ---------------------------------------------------------------- IS-2: isim onegi
@pytest.mark.anyio
async def test_arac_isimleri_servis_onekli():
    """Standart §15: jenerik isimler baska sunucularla cakisir.
    Bu test, ileride oneki dusuren bir degisikligi yapisal olarak yakalar."""
    from edgar_mcp.server import mcp
    isimler = {t.name for t in await mcp.list_tools()}
    assert isimler == {
        "sec_edgar_get_company_profile",
        "sec_edgar_list_filings",
        "sec_edgar_search_filings",
        "sec_edgar_get_concept_series",
        "sec_edgar_get_fact_revisions",
        "sec_edgar_read_filing_text",
        "sec_edgar_list_available_concepts",
        "sec_edgar_compare_companies",
        "sec_edgar_list_fact_dimensions",
        "sec_edgar_get_dimensional_facts",
        "sec_edgar_get_insider_transactions",
        "sec_edgar_get_institutional_holdings",
    }, f"beklenmeyen arac isimleri: {isimler}"


# ---------------------------------------------------------------- hiz siniri
@pytest.mark.anyio
async def test_hiz_sinirlayici_gercekten_bekletir():
    """Testlerde hiz siniri ortam degiskeniyle gevsetiliyor; sinirlayicinin
    KENDISI burada dogrudan sinaniyor ki koruma kaldirilmis olmasin."""
    import time

    from edgar_mcp.client import RateLimiter

    r = RateLimiter(rate_per_sec=20.0)          # 50 ms araliK
    t0 = time.monotonic()
    for _ in range(3):
        await r.acquire()
    gecen = time.monotonic() - t0
    assert gecen >= 0.09, f"sinirlayici bekletmedi ({gecen:.3f}s)"


def test_varsayilan_hiz_sec_sinirinin_altinda():
    from edgar_mcp.client import RateLimiter
    assert RateLimiter.VARSAYILAN_HIZ < 10.0, "SEC ust siniri 10 istek/sn"


# ================================================================ H-1: mali yil
def test_kayma_apple_tipi_sifir():
    """Bitis yiliyla adlandiran sirket (Apple, Walmart, Microsoft): kayma 0."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        {"start":"2022-09-25","end":"2023-09-30","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2021-09-26","end":"2022-09-24","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2023-10-01","end":"2024-09-28","fy":2024,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (0, True)


def test_kayma_target_tipi_eksi_bir():
    """Baslangic yiliyla adlandiran perakendeci (Target/Gap): 3 Subat 2024'te
    biten yil 'fiscal 2023'tur. Kayma -1 olarak TURETILMELI, varsayilmamali."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        {"start":"2023-01-29","end":"2024-02-03","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2022-01-30","end":"2023-01-28","fy":2023,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (-1, True)


def test_kayma_capa_yoksa_turetilmedi_isaretlenir():
    """10-K capasi yoksa uydurma yapma - 0 dondur ama TURETILMEDI de."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [{"start":"2024-01-01","end":"2024-03-31","fy":2024,"fp":"Q1","form":"10-Q"}]
    assert _fy_kaymasi(rows) == (0, False)


def test_kayma_ceyreklik_satirlari_capa_saymaz():
    """Ilk yazdigim bu test KUSURLUYDU: filtre kaldirilinca da ayni sonucu
    veriyordu, yani hicbir sey korumuyordu (enjeksiyon yakaladi).
    Yeniden kuruldu: kisa donemler capa sayilirsa mod 0'dan 1'e KAYMALI."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        # tek gecerli capa: yillik donem, kayma 0
        {"start":"2022-09-25","end":"2023-09-30","fy":2023,"fp":"FY","form":"10-K"},
        # kisa donemler; capa sayilirlarsa ikisi de kayma 1 verir ve mod'u calar
        {"start":"2024-07-01","end":"2024-09-28","fy":2025,"fp":"FY","form":"10-K"},
        {"start":"2025-07-01","end":"2025-09-27","fy":2026,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (0, True), "kisa donemler capa sayilmis"


@pytest.mark.anyio
async def test_seri_mali_yilin_turetildigini_bildirir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert s.fiscal_year_derived is True


# ================================================================ H-2: birlestirme
@pytest.mark.anyio
async def test_etiket_degisiminde_gecmis_kirpilmaz(srv):
    """Muhasebe standardi degisikligi 10 yillik gecmisi sessizce siliyordu."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    yillar = sorted(p.fiscal_year for p in s.points)
    assert 2017 in yillar, "eski etiketten gelen donemler kayip"
    assert 2023 in yillar, "yeni etiketten gelen donemler kayip"
    assert set(s.resolved_concepts) == {GERCEK_GELIR_ETIKETI, "SalesRevenueNet"}


@pytest.mark.anyio
async def test_her_nokta_kaynak_etiketini_tasir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    kaynaklar = {p.source_tag for p in s.points}
    assert kaynaklar == {GERCEK_GELIR_ETIKETI, "SalesRevenueNet"}


@pytest.mark.anyio
async def test_ortusen_donemde_en_son_sunulan_kazanir(srv):
    """2021 donemi iki etikette de var. Eski etiketteki kayit 2021'de,
    yenisi 2023'te sunulmus -> yeni kazanmali (999 milyar SAHTE degerdir)."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    fy21 = [p for p in s.points if p.period_end == "2021-09-25"]
    assert len(fy21) == 1, "ortusen donem cift sayilmis"
    assert fy21[0].value == 365_817_000_000
    assert fy21[0].source_tag == GERCEK_GELIR_ETIKETI


@pytest.mark.anyio
async def test_tum_adaylar_denenir_ilk_eslesende_durulmaz(srv):
    ISTEK_KAYDI.clear()
    await srv.get_concept_series(ticker="AAPL", concept="revenue")
    cagrilan = [u.rsplit("/", 1)[-1].replace(".json", "")
                for u in ISTEK_KAYDI if "companyconcept" in u]
    assert "SalesRevenueNet" in cagrilan, "ilk eslesende durulmus"


# ================================================== §15: tanim = arayuzun kendisi
@pytest.mark.anyio
async def test_her_arac_ve_parametre_aciklamali():
    """Standart §15: modelin gordugu tek sey tanimlardir. Aciklamasiz bir
    parametre, modelin tahmin etmesi demektir. Bu test, ileride aciklamasiz
    arac/parametre eklenmesini yapisal olarak engeller."""
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        assert t.description and len(t.description) >= 80, \
            f"{t.name}: tanim yok veya cok kisa"
        for ad, sema in (t.input_schema.get("properties") or {}).items():
            assert sema.get("description"), f"{t.name}.{ad}: parametre aciklamasi yok"


# --- Dil kontrolu: iki kat, tests/dil.py ------------------------------------
# Eski surum " ve " gibi bosluk-cevreli alt dizgiler ariyordu ve YALNIZCA
# t.description'a bakiyordu. Ikisi de yetersizdi; ustelik kara listenin kendisi
# ayni gun uc kez yetersiz kaldi. Bkz. PATTERNS.md P-17, CLAUDE.md KK-21/KK-22.
from dil import bilinmeyen_kelimeler, turkce_izleri, yabanci_izler  # noqa: E402


def _disa_bakan_yuzey(t) -> list[tuple[str, str]]:
    """Modelin/musterinin gordugu TUM metinler: arac tanimi, parametre
    aciklamalari ve donus semasindaki alan aciklamalari."""
    parcalar = [(f"{t.name}.description", t.description or "")]
    for ad, sema in (t.input_schema.get("properties") or {}).items():
        parcalar.append((f"{t.name}.in.{ad}", sema.get("description") or ""))
    cikti = t.output_schema or {}
    for model, tanim in (cikti.get("$defs") or {}).items():
        for ad, sema in (tanim.get("properties") or {}).items():
            parcalar.append((f"{t.name}.out.{model}.{ad}", sema.get("description") or ""))
    for ad, sema in (cikti.get("properties") or {}).items():
        parcalar.append((f"{t.name}.out.{ad}", sema.get("description") or ""))
    return parcalar


def test_dil_kontrolu_bilinen_ornekleri_ayirt_ediyor():
    """Sezicinin kendisi olculur, varsayilmaz (§2). Ilk iki dizge 13 Agu
    2026'da canlida bulunan gercek kacaklardir - regresyon capasi. Ikincisi
    ayni zamanda kara listenin NEDEN yetmedigini gosterir: icinde Turkceye
    ozgu harf yok ve hicbir kelimesi elle yazilmis listede degildi."""
    TURKCE = [
        "Takma ad (revenue, net_income, total_assets, ...) veya ham "
        "US-GAAP etiketi (orn. NetIncomeLoss)",
        "Ticker bulunamadi: AAPL",
        "Sirketin dosyalamalarini dondurur",
        "Dondurulecek maksimum donem sayisi",
    ]
    INGILIZCE = [
        "Stock ticker symbol, e.g. AAPL",
        "Maximum number of periods to return, most recent last",
        "True if more filings matched than were returned; raise limit",
        "Period end date - the only reliable identifier of a period",
        "US-GAAP tag this value was reported under",
    ]
    for m in TURKCE:
        assert yabanci_izler(m), f"Turkce dizge temiz sayildi: {m!r}"
    for m in INGILIZCE:
        assert not yabanci_izler(m), f"Ingilizce dizge yabanci sanildi: {m!r}"

    # Kara listenin siniri: bu dizgeyi YALNIZCA pozitif liste yakalar.
    assert not turkce_izleri("Ticker bulunamadi: AAPL".replace("bulunamadi", "yok")), \
        "kara liste beklenmedik bicimde eslesti - test artik neyi olctugunu bilmiyor"
    assert bilinmeyen_kelimeler("Ticker yok: AAPL") == ["yok"]


def test_kelime_dagarcigi_kullanilmayan_kelime_biriktirmiyor():
    """Dagarcik disa bakan metinlerden turetildi; olu kelime birikirse liste
    zamanla her seyi kabul eden bir sunger haline gelir (§11)."""
    import asyncio

    from dil import DAGARCIK

    from edgar_mcp.server import mcp

    async def metinler():
        out = []
        for t in await mcp.list_tools():
            out += [m for _, m in _disa_bakan_yuzey(t)]
        return out


    hepsi = " ".join(asyncio.run(metinler()))
    for _, m in _hata_metinleri():
        hepsi += " " + m

    import re as _re

    kullanilan = {
        w.lower()
        for w in _re.findall(r"[A-Za-z]+", hepsi)
        if len(w) >= 2 and not any(c.isupper() for c in w[1:])
    }
    olu = sorted(DAGARCIK - kullanilan)
    assert not olu, f"kelime dagarciginda artik kullanilmayan kelimeler var: {olu}"


def _hata_metinleri() -> list[tuple[str, str]]:
    """Modele giden hata metinleri: `raise` icindeki dizgiler ARTI bir raise
    tarafindan CAGRILAN fonksiyonlarin dondurdugu dizgiler.

    Ikinci kisim 15 Agu 2026'da eklendi: HTTP durum mesajlari `_durum_mesaji()`
    yardimcisina tasininca `raise ValueError(_durum_mesaji(...))` oldular ve
    yalnizca `raise` dugumunu gezen tarayici onlari GORMEZ hale geldi. Yeni
    yazilan sekiz mesajin hicbiri dil kapisindan gecmemisti. P-17'nin tekrari:
    disa bakan yuzey, tarayicinin baktigi yerden daha genis.
    """
    import ast
    import pathlib as _p

    kok = _p.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    out: list[tuple[str, str]] = []
    for f in sorted(kok.glob("*.py")):
        agac = ast.parse(f.read_text(encoding="utf-8"))
        dolayli: set[str] = set()
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Raise):
                continue
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                    out.append((f.name, alt.value))
                elif isinstance(alt, ast.Call) and isinstance(alt.func, ast.Name):
                    dolayli.add(alt.func.id)
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.FunctionDef) and dugum.name in dolayli:
                for alt in ast.walk(dugum):
                    if isinstance(alt, ast.Constant) and isinstance(alt.value, str) \
                            and len(alt.value) > 20:
                        out.append((f.name, alt.value))
    return out


def test_hata_mesajlari_ingilizce():
    """Hata mesajlari semada gorunmez ama modele ve musteriye AYNEN gider.
    Sema taramasi bunlari kacirir; bu yuzden kaynak agacindan `raise`
    ifadeleri VE onlarin cagirdigi yardimcilar ayrica taranir. 13 Agu 2026'da
    bu tarama `client.py` icinde "Ticker bulunamadi: ..." mesajini yakaladi;
    15 Agu 2026'da dolayli mesajlarin hic taranmadigi ortaya cikti."""
    metinler = _hata_metinleri()
    assert len(metinler) > 20, "hata metni taramasi coktu"
    for dosya, metin in metinler:
        izler = yabanci_izler(metin)
        assert not izler, f"{dosya}: hata mesaji Ingilizce degil {izler} -> {metin!r}"


@pytest.mark.anyio
async def test_arac_tanimlari_ingilizce():
    """Disariya bakan yuzeyin TAMAMI Ingilizce olmali - musteri ABD/AB.
    Kod yorumlari ve karar kayitlari Turkce kalir, onlar ic belgelendirme."""
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        for etiket, metin in _disa_bakan_yuzey(t):
            izler = yabanci_izler(metin)
            assert not izler, f"{etiket} Ingilizce degil: {izler} -> {metin!r}"


# ============================================== KK-11: cekirdek .env okumaz
def test_cekirdek_dotenv_bagimliligi_tasimaz():
    """MCP sunucusu ortamini kendisini calistiran uygulamadan alir. Cekirdege
    dotenv sizarsa gereksiz bir calisma-zamani bagimliligi olur ve Docker/
    Claude Desktop yolunda hicbir sey kazandirmaz."""
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    for f in kok.glob("*.py"):
        assert "dotenv" not in f.read_text(), f"{f.name} dotenv'e bagimli olmus"


def test_env_example_gercekten_okunan_degiskeni_belgeler():
    """Dokuman ile davranis ortusmeli (§1): .env.example'daki degisken adi,
    kodun gercekte okudugu degisken olmali."""
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1]
    ornek = (kok / ".env.example").read_text()
    istemci = (kok / "src" / "edgar_mcp" / "client.py").read_text()
    belgelenen = set(re.findall(r"^([A-Z_]+)=", ornek, re.M))
    assert belgelenen, ".env.example hicbir degisken belgelemiyor"
    for ad in belgelenen:
        assert ad in istemci, f"{ad} belgelenmis ama kod okumuyor"


# ========================= KO olayi (13 Agu 2026): bos companyconcept yaniti
def _srv_ozel(monkeypatch, ozel_handler):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@ornek.com")
    from edgar_mcp import server as s
    from edgar_mcp.client import EdgarClient

    c = EdgarClient()
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(ozel_handler),
        headers={"User-Agent": "Test Runner test@ornek.com"},
    )
    s._client = c
    return s


def _bos_units_handler(bos_facts: bool = False):
    """SEC'in KO icin verdigi gercek yanit: HTTP 200, dogru label, units.USD
    VAR ama icinde satir YOK. 404 degil, hata degil - bos basari."""
    def h(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "companyconcept" in u:
            ISTEK_KAYDI.append(u)
            # Gercek govde (KO, 13 Agu 2026): USD bir dizi degil, BOS SOZLUK.
            return httpx.Response(200, json={"cik": 320193, "taxonomy": "us-gaap",
                                             "label": "Assets", "units": {"USD": {}}})
        if "companyfacts" in u and bos_facts:
            ISTEK_KAYDI.append(u)
            bos = {"facts": {"us-gaap": {t: {"label": t, "units": {"USD": []}}
                                         for t in FACTS["facts"]["us-gaap"]}}}
            return httpx.Response(200, json=bos)
        return handler(request)
    return h


@pytest.mark.anyio
async def test_bos_companyconcept_yanitinda_companyfacts_e_dusulur(monkeypatch):
    """Olculdu (13 Agu 2026, KO): companyconcept bes farkli kosulda da bos
    dondu, ayni etiket companyfacts'te 144 satirdi. Bos yanit basari sayilirsa
    model 'bu sirket bunu raporlamiyor' diye okur - yanlis cevap, hata yok."""
    ISTEK_KAYDI.clear()
    s = _srv_ozel(monkeypatch, _bos_units_handler())
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")

    assert seri.source_endpoint == "companyfacts", "yedek uca dusulmemis"
    assert seri.total_periods > 0, "companyfacts'te veri varken bos donuldu"
    assert any("companyfacts" in u for u in ISTEK_KAYDI)


@pytest.mark.anyio
async def test_normal_durumda_companyfacts_cekilmez(srv):
    """companyfacts birkac MB. Yedek yol yalnizca gerektiginde acilmali,
    her cagride degil."""
    ISTEK_KAYDI.clear()
    seri = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert seri.source_endpoint == "companyconcept"
    assert not any("companyfacts" in u for u in ISTEK_KAYDI), \
        "gerek yokken 5 MB'lik uc cekilmis"


@pytest.mark.anyio
async def test_iki_uc_da_bossa_sessiz_basari_yerine_hata(monkeypatch):
    """Ikisi de bossa donecek veri yok. O zaman bos bir 'basari' degil,
    eyleme donusturulebilir hata verilir (P-13)."""
    s = _srv_ozel(monkeypatch, _bos_units_handler(bos_facts=True))
    with pytest.raises(ValueError) as e:
        await s.get_concept_series(ticker="AAPL", concept="revenue")
    mesaj = str(e.value)
    assert "companyfacts" in mesaj and "companyconcept" in mesaj
    assert "sec_edgar_list_available_concepts" in mesaj


@pytest.mark.anyio
async def test_liste_olmayan_birim_govdesi_cokertmez(monkeypatch):
    """SEC'in bos yaniti `units.USD` icin dizi degil SOZLUK veriyor ({}).
    Bos sozluk zaten sifir satir sayilir; bu test bir adim otesini,
    BOS OLMAYAN bir sozlugu kapsiyor. Boyle bir yanit gozlenmedi - bu
    savunma amacli bir koruma: beklenmedik sekil ne cokertmeli ne de
    sessizce basari gibi gorunmeli."""
    def h(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "companyconcept" in u:
            return httpx.Response(200, json={
                "label": "Assets",
                "units": {"USD": {"0": {"end": "2025-12-31", "val": 1}}},
            })
        return handler(request)

    s = _srv_ozel(monkeypatch, h)
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")
    # companyconcept kullanilamaz sekilde geldi -> yedek uc devreye girmeli
    assert seri.source_endpoint == "companyfacts"
    assert seri.total_periods > 0


@pytest.mark.anyio
async def test_karisik_birim_sekli_gecerli_satirlari_korur(monkeypatch):
    """Bir birim kullanilabilir liste, digeri kullanilamaz sekil olabilir.
    Bu durumda gecerli satirlar KAYBOLMAMALI ve kod cokmemeli - yani
    kullanilamaz birim atlanir, yedek uca da dusulmez (veri zaten var)."""
    def h(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json={
                "label": "Revenues",
                "units": {"USD": CONCEPT["units"]["USD"], "shares": {"0": {}}},
            })
        return handler(request)

    s = _srv_ozel(monkeypatch, h)
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")
    assert seri.source_endpoint == "companyconcept", "gereksiz yere yedege dusuldu"
    assert seri.total_periods > 0
    assert all(p.unit == "USD" for p in seri.points)


# ==================================== revizyon gecmisi (Tesla raporu bosluk 6)
@pytest.mark.anyio
async def test_revizyon_degisen_degeri_yakalar(srv):
    """Ayni donem sonraki dosyalamada FARKLI bir degerle raporlanmissa, bu bir
    revizyondur ve gorunmelidir. Seri araci bunu bilerek gizler (en guncel
    degeri verir); revizyon araci tam tersini yapar."""
    r = await srv.get_fact_revisions(ticker="AAPL", concept="revenue")

    donemler = {(x.source_tag, x.period_end): x for x in r.revisions}
    anahtar = (GERCEK_GELIR_ETIKETI, "2023-09-30")
    assert anahtar in donemler, f"revize donem yok: {list(donemler)}"
    rev = donemler[anahtar]
    assert rev.distinct_values == 2
    assert rev.first_value == 383_285_000_000
    assert rev.latest_value == 383_290_000_000
    assert rev.change == 5_000_000
    assert [e.filed for e in rev.entries] == ["2023-11-03", "2024-11-01"], "sira eski->yeni degil"
    assert all(e.accession_number for e in rev.entries), "erisim numarasi tasinmiyor"


@pytest.mark.anyio
async def test_revizyon_ayni_degerin_tekrari_revizyon_sayilmaz(srv):
    """Bir 10-K uc yillik karsilastirma tasir; ayni deger her yil tekrar
    raporlanir. Tekrari revizyon saymak, her donemi 'revize edilmis' gosterir
    ve arac ise yaramaz hale gelir."""
    r = await srv.get_fact_revisions(ticker="AAPL", concept="revenue", only_revised=False)

    donemler = {(x.source_tag, x.period_end): x for x in r.revisions}
    tekrar = donemler[(GERCEK_GELIR_ETIKETI, "2022-09-24")]   # iki dosyalamada AYNI deger
    assert tekrar.distinct_values == 1, "ayni deger revizyon sayilmis"
    assert tekrar.entries[0].times_repeated == 2, "tekrar sayisi kaydedilmemis"
    assert tekrar.change == 0
    assert r.periods_revised == 1, f"beklenmeyen revize donem sayisi: {r.periods_revised}"
    assert r.periods_examined > r.periods_revised


@pytest.mark.anyio
async def test_revizyon_varsayilan_olarak_sadece_revize_donemleri_verir(srv):
    """Varsayilan cikti sinyal olmali: revize edilmemis donemler gurultudur."""
    sadece = await srv.get_fact_revisions(ticker="AAPL", concept="revenue")
    hepsi = await srv.get_fact_revisions(ticker="AAPL", concept="revenue", only_revised=False)
    assert len(sadece.revisions) < len(hepsi.revisions)
    assert all(x.distinct_values > 1 for x in sadece.revisions)


@pytest.mark.anyio
async def test_revizyon_ve_seri_ayni_gercekte_ayni_seyi_soyluyor(srv):
    """Iki arac ayni veriyi farkli amacla sunuyor; celismemeleri gerekir.
    Serideki deger, revizyon gecmisindeki EN SON degerle ayni olmali."""
    seri = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    rev = await srv.get_fact_revisions(ticker="AAPL", concept="revenue", only_revised=False)

    # Ayni donem birden fazla ETIKETTE olabilir; seri bunlardan birini secer.
    # Karsilastirma etiket bazinda yapilmali, yoksa test yanlis yerden kirilir.
    seri_degerleri = {(p.source_tag, p.period_end): p.value for p in seri.points}
    eslesen = 0
    for x in rev.revisions:
        anahtar = (x.source_tag, x.period_end)
        if anahtar in seri_degerleri:
            eslesen += 1
            assert seri_degerleri[anahtar] == x.latest_value, (
                f"{anahtar}: seri {seri_degerleri[anahtar]}, "
                f"revizyon {x.latest_value}"
            )
    assert eslesen >= 3, f"karsilastirma bos kalmis ({eslesen} eslesme)"


# ============================ dei taksonomisi (Tesla raporu bosluk 3, kismi)
@pytest.mark.anyio
async def test_takma_ad_dei_taksonomisine_gidebiliyor(srv):
    """Olculdu (14 Agu 2026): companyfacts'te dei/us-gaap/ffd var. Piyasa
    degerine SEC icinde kalarak ulasilabilecek tek capa dei:EntityPublicFloat;
    sunucu us-gaap disina cikamadigi icin erisilemiyordu."""
    ISTEK_KAYDI.clear()
    seri = await srv.get_concept_series(ticker="AAPL", concept="public_float",
                                        period="all")
    assert seri.taxonomy == "dei"
    assert seri.resolved_concepts == ["dei:EntityPublicFloat"]
    assert seri.total_periods == 2
    assert seri.points[-1].value == 2_900_000_000_000
    assert seri.points[-1].source_tag == "EntityPublicFloat", "etiket adi nitelikli kalmis"
    assert any("/dei/EntityPublicFloat.json" in u for u in ISTEK_KAYDI), \
        "istek us-gaap yoluna gitmis"


@pytest.mark.anyio
async def test_ham_nitelikli_etiket_de_kabul_ediliyor(srv):
    seri = await srv.get_concept_series(ticker="AAPL",
                                        concept="dei:EntityPublicFloat",
                                        period="all")
    assert seri.taxonomy == "dei" and seri.total_periods == 2


@pytest.mark.anyio
async def test_kesif_araci_taksonomileri_kendisi_bildiriyor(srv):
    """Model hangi taksonomilerin oldugunu tahmin etmemeli; yanit soylemeli."""
    k = await srv.list_available_concepts(ticker="AAPL", taxonomy="dei")
    assert k.taxonomy == "dei"
    assert set(k.available_taxonomies) == {"dei", "us-gaap"}
    assert any(c.tag == "EntityPublicFloat" for c in k.concepts)


@pytest.mark.anyio
async def test_olmayan_taksonomi_eyleme_donusturulebilir_hata_verir(srv):
    """P-13: hata mesaji modelin bir sonraki hamlesini icermeli."""
    with pytest.raises(ValueError) as e:
        await srv.list_available_concepts(ticker="AAPL", taxonomy="tsla")
    mesaj = str(e.value)
    assert "tsla" in mesaj and "us-gaap" in mesaj and "dei" in mesaj


# ================== belge metni araci (Tesla raporu bosluk 4 ve 5)
@pytest.mark.anyio
async def test_belge_bolumleri_kesfedilebilir(srv):
    """Model hangi bolumlerin oldugunu tahmin etmemeli; ilk cagri onlari
    listelemeli (§18)."""
    b = await srv.read_filing_text(ticker="AAPL")
    basliklar = " | ".join(b.available_sections).lower()
    assert "item 7" in basliklar and "item 1a" in basliklar
    assert "note 12" in basliklar
    assert b.form == "10-K" and b.accession_number == "0000320193-25-000073"


@pytest.mark.anyio
async def test_icindekiler_tablosu_bolum_sanilmiyor(srv):
    """ASIL TUZAK: "Item 7. ..." ifadesi belgede EN AZ IKI kez gecer - once
    icindekiler tablosunda, sonra bolumun kendisinde. Ilk eslesmeyi almak
    modele iki satirlik bir baglanti listesi dondurur ve bolum bos gorunur."""
    b = await srv.read_filing_text(ticker="AAPL", section="Item 7")

    assert MDA_ISARET in b.text, "icindekiler tablosu bolum sanilmis"
    assert "Item 8" not in b.text, "bolum siniri asilmis"
    assert b.section_matched and "item 7" in b.section_matched.lower()
    # Icindekiler girisleri liste disi kalmali: her baslik BIR kez gorunmeli
    yediler = [x for x in b.available_sections if x.lower().startswith("item 7")]
    assert len(yediler) == 1, f"icindekiler girisi de bolum sayilmis: {yediler}"

    # Icindekilerde adi gecen ama GOVDESI OLMAYAN madde listeye girmemeli.
    # Gercek ornek: TSLA FY2025 10-K'da ITEM 3 yok, FY2023'te var.
    ucler = [x for x in b.available_sections if x.lower().startswith("item 3")]
    assert not ucler, f"govdesiz icindekiler girisi bolum sayilmis: {ucler}"


@pytest.mark.anyio
async def test_dipnot_basligiyla_da_bolum_secilebiliyor(srv):
    """Rapordaki 5. bosluk: 2023 vergi kaleminin GEREKCESI dipnotta."""
    b = await srv.read_filing_text(ticker="AAPL", section="income taxes")
    assert VERGI_ISARET in b.text
    assert b.section_matched and "note 12" in b.section_matched.lower()


@pytest.mark.anyio
async def test_belge_metni_sayfalaniyor(srv):
    """Bir 10-K milyonlarca karakter; kirpilmadan dondurmek modeli bogar."""
    ilk = await srv.read_filing_text(ticker="AAPL", section="Item 7",
                                     max_characters=500)
    assert ilk.returned_characters == 500
    assert ilk.has_more is True
    assert ilk.offset == 0

    devam = await srv.read_filing_text(ticker="AAPL", section="Item 7",
                                       offset=500, max_characters=500)
    assert devam.offset == 500
    assert devam.text != ilk.text
    assert devam.total_characters == ilk.total_characters

    hepsi = await srv.read_filing_text(ticker="AAPL", section="Item 7",
                                       max_characters=40000)
    assert hepsi.has_more is False
    assert hepsi.text.startswith(ilk.text[:200])


@pytest.mark.anyio
async def test_script_ve_stil_metne_karismiyor(srv):
    """HTML'i duz atmak <script> govdesini metne sokar; model onu belge
    icerigi sanir."""
    b = await srv.read_filing_text(ticker="AAPL", max_characters=40000)
    assert "SCRIPT ICERIGI SIZDI" not in b.text
    assert "color: red" not in b.text
    assert "Research & development" in b.text, "HTML varligi cozulmemis"
    assert "Revenue | 391,035" in b.text, "tablo hucreleri birbirine yapismis"


@pytest.mark.anyio
async def test_olmayan_bolum_eyleme_donusturulebilir_hata_verir(srv):
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL", section="Item 99")
    mesaj = str(e.value)
    assert "Item 99" in mesaj
    assert "Item 7" in mesaj, "hata mesaji mevcut bolumleri listelemiyor"


@pytest.mark.anyio
async def test_ayni_belge_iki_kez_indirilmiyor(srv):
    """Sayfalama ayni belgeyi tekrar tekrar ister; her seferinde 5-15 MB
    indirmek hem yavas hem SEC hiz sinirini yer."""
    ISTEK_KAYDI.clear()
    await srv.read_filing_text(ticker="AAPL", max_characters=500)
    await srv.read_filing_text(ticker="AAPL", offset=500, max_characters=500)
    indirme = [u for u in ISTEK_KAYDI if u.endswith(".htm")]
    assert len(indirme) == 1, f"belge {len(indirme)} kez indirilmis"
    # Dosya listesi de her cagride yeniden istenmemeli: kucuk bir JSON ama
    # SEC hiz siniri istek SAYAR, bayt degil.
    dizin = [u for u in ISTEK_KAYDI if u.endswith("/index.json")]
    assert len(dizin) == 1, f"dosya listesi {len(dizin)} kez istenmis"


@pytest.mark.anyio
async def test_erisim_numarasiyla_belirli_dosyalama_okunabiliyor(srv):
    b = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-24-000123")
    assert b.accession_number == "0000320193-24-000123"
    assert b.filing_date == "2024-11-01"
    assert "000032019324000123/aapl-20240928.htm" in b.document_url


@pytest.mark.anyio
async def test_olmayan_erisim_numarasi_eyleme_donusturulebilir_hata_verir(srv):
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL", accession_number="0000-00-000")
    assert "sec_edgar_list_filings" in str(e.value)


@pytest.mark.anyio
async def test_ayni_baslik_iki_kez_gecerse_ASIL_bolum_secilir(srv):
    """Esik filtresi icindekiler tablosunu her zaman elemez: bazi dosyalamalarda
    icindekiler girisleri uzun aciklamalar tasir ve esigi gecer. O durumda
    ayirt edici olan UZUNLUKTUR - asil bolum daima daha uzundur."""
    b = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-24-000123",
                                   section="Item 7", max_characters=40000)
    assert UZUN_TOC_ISARET in b.text, "kisa icindekiler girisi secilmis"
    assert "See page 44" not in b.text


@pytest.mark.anyio
async def test_tablo_icindeki_basliklar_da_bulunuyor(srv):
    """Gercek 10-K'larin cogunda bolum basliklari HTML TABLOSU icinde durur.
    Metne cevrilince satir " | " ile basladigi icin satir-basi capasi tutmaz ve
    hicbir bolum bulunamaz - dosyalama "bolumsuz" gorunur."""
    b = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-25-000058",
                                   section="Item 7", max_characters=40000)
    assert TABLO_ISARET in b.text
    assert b.section_matched and "item 7" in b.section_matched.lower()


@pytest.mark.anyio
async def test_gizli_ixbrl_blogu_metne_girmiyor(srv):
    """Olculdu (14 Agu 2026, TSLA FY2023 10-K): modern dosyalamalar
    `display:none` bir blokla basliyor ve belgenin ILK 1200 karakteri ad alani
    URL'lerinden ibaret. Model belgeyi bastan okudugunda gurultuyle karsilasir
    ve icerigi orada sanir."""
    b = await srv.read_filing_text(ticker="AAPL", max_characters=2000)
    assert "GIZLI IXBRL GURULTUSU" not in b.text
    assert "fasb.org" not in b.text
    assert b.text.lstrip().startswith("Table of Contents"), b.text[:120]


@pytest.mark.anyio
async def test_belge_metne_bir_kez_cevriliyor(srv, monkeypatch):
    """Olculdu (14 Agu 2026): 2,2 MB HTML'i metne cevirmek 0,61 saniye.
    Sayfalama ayni belgeyi defalarca ister; her cagride yeniden cevirmek
    bir bolumu bes parcada okurken saniyeleri bosa harcar."""
    from edgar_mcp import belge as b
    from edgar_mcp import server as s

    sayac = {"n": 0}
    gercek = b.cevir

    def sayan(govde: str, gizliyi_atla: bool = True):
        sayac["n"] += 1
        return gercek(govde, gizliyi_atla=gizliyi_atla)

    monkeypatch.setattr(s, "cevir", sayan)

    await srv.read_filing_text(ticker="AAPL", max_characters=500)
    await srv.read_filing_text(ticker="AAPL", offset=500, max_characters=500)
    await srv.read_filing_text(ticker="AAPL", section="Item 7", max_characters=500)
    assert sayac["n"] == 1, f"belge {sayac['n']} kez ayristirilmis"


@pytest.mark.anyio
async def test_bolum_listesi_ayni_kodu_bir_kez_veriyor(srv):
    """Canli olcumde (TSLA FY2023 10-K) esikten gecen ikinci bir "Item 16"
    listenin BASINDA, ITEM 1'den once goruluyordu - kapak sayfasindaki bir
    referans bolum sanilmisti."""
    b = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-24-000123")
    kodlar = [x.lower().split(".")[0].strip() for x in b.available_sections]
    assert len(kodlar) == len(set(kodlar)), f"ayni kod birden fazla: {kodlar}"
    # ve kalan, kisa icindekiler girisi degil ASIL bolum olmali
    tam = await srv.read_filing_text(ticker="AAPL",
                                     accession_number="0000320193-24-000123",
                                     section="Item 7", max_characters=40000)
    assert UZUN_TOC_ISARET in tam.text


@pytest.mark.anyio
async def test_alt_dize_aramasinda_en_uzun_bolum_kazanir(srv):
    """Iki FARKLI baslik ayni ifadeyi tasiyabilir ("taxes"). Tekillestirme
    burada yardim etmez - kodlar farkli. Kural: en uzun blok kazanir, cunku
    asil bolum ozet/atif satirindan uzundur."""
    b = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-25-000012",
                                   section="taxes", max_characters=40000)
    assert VERGI_UZUN_ISARET in b.text
    assert b.section_matched and "note 12" in b.section_matched.lower()


# ============ 8-K eki ve dosyalama ici arama (B1 + B2, 14 Agu 2026 olcumu)
@pytest.mark.anyio
async def test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor(srv):
    """Olculdu: TSLA'nin 2026 Q2 teslimat bulteni 8-K'nin BIRINCIL belgesinde
    degil, ekinde. Arac yalnizca birincil belgeyi okusaydi teslimat adetleri
    ulasilamaz kalirdi - raporun kapanmayan bosluklarindan biri buydu."""
    kapak = await srv.read_filing_text(ticker="AAPL",
                                       accession_number="0000320193-25-000041")
    assert EK_ISARET not in kapak.text, "kapak sayfasi zaten icerigi tasiyor mu?"
    adlar = [b.name for b in kapak.available_documents]
    assert "exhibit991.htm" in adlar
    assert not any("index" in a for a in adlar), "gezinme sayfasi listeye girmis"
    assert not any(a.endswith(".xsd") for a in adlar), "okunamaz dosya listede"
    assert not any(re.fullmatch(r"R\d+\.html?", a, re.I) for a in adlar), (
        "XBRL goruntuleyicisinin urettigi rapor dosyasi listeye girmis"
    )
    # Modelin ihtiyaci olan sinyal boyut degil, hangisinin birincil oldugu:
    # gercek dosyalamada kapak (26.572) ekten (13.243) BUYUK.
    birincil = [b.name for b in kapak.available_documents if b.is_primary]
    assert birincil == ["aapl-8k.htm"], f"birincil belge isaretlenmemis: {birincil}"
    boyutlu = [b for b in kapak.available_documents if b.size_bytes]
    assert boyutlu == sorted(boyutlu, key=lambda b: -(b.size_bytes or 0)), \
        "dosya listesi buyukten kucuge sirali degil"

    ek = await srv.read_filing_text(ticker="AAPL",
                                    accession_number="0000320193-25-000041",
                                    document="exhibit991.htm",
                                    max_characters=40000)
    assert EK_ISARET in ek.text
    assert ek.document_name == "exhibit991.htm"


@pytest.mark.anyio
async def test_olmayan_belge_adi_eyleme_donusturulebilir_hata_verir(srv):
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-25-000041",
                                   document="yok.htm")
    mesaj = str(e.value)
    assert "yok.htm" in mesaj and "exhibit991.htm" in mesaj


@pytest.mark.anyio
async def test_arama_bolum_adini_bilmeden_yeri_buluyor(srv):
    """Vergi dipnotunu bulabilmemin tek sebebi adinin listede gorunmesiydi.
    Model her zaman dogru basligi bilemez; arama o bagimliligi kaldirir."""
    b = await srv.read_filing_text(ticker="AAPL", section=None,
                                   search="valuation allowance release",
                                   max_characters=500)
    assert b.search_total_matches >= 1
    assert b.search_hits, "eslesme bulundu ama konum verilmedi"
    ilk = b.search_hits[0]
    assert VERGI_ISARET.split(" of ")[0] in ilk.context or "valuation" in ilk.context
    # Bildirilen konum gercekten oraya goturmeli
    devam = await srv.read_filing_text(ticker="AAPL", offset=ilk.position,
                                       max_characters=200)
    assert "valuation allowance" in devam.text.lower()


@pytest.mark.anyio
async def test_arama_bulunamayinca_sifir_bildiriyor(srv):
    b = await srv.read_filing_text(ticker="AAPL", search="olmayan bir ifade xyzzy")
    assert b.search_total_matches == 0
    assert b.search_hits == []


@pytest.mark.anyio
async def test_arama_vurgu_sayisi_sinirli_ama_toplam_dogru(srv):
    """Bir ifade yuzlerce kez gecebilir; hepsini baglamiyla dondurmek yaniti
    sisirir. Kirpma var ama toplam sayi dogru bildirilmeli (§16)."""
    from edgar_mcp import server as s

    b = await srv.read_filing_text(ticker="AAPL", search="filler")
    assert b.search_total_matches > s.ARAMA_VURGU_SINIRI
    assert len(b.search_hits) == s.ARAMA_VURGU_SINIRI


# ============ Sirketler arasi karsilastirma (B3, `frames` ucu)
@pytest.mark.anyio
async def test_cerceve_degere_gore_siraliyor_ve_kirpmayi_bildiriyor(srv):
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1", limit=2)
    assert [c.company for c in b.companies] == ["Apple Inc.", "HOME DEPOT, INC."]
    assert [c.rank for c in b.companies] == [1, 2]
    assert b.total_companies == 4 and b.returned == 2 and b.has_more is True
    assert b.resolved_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert b.frame == "CY2025Q1" and b.frame_kind == "duration"


@pytest.mark.anyio
async def test_cerceve_artan_siralamada_sira_numarasi_da_donuyor(srv):
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1",
                                    order="value_asc", limit=1)
    assert b.companies[0].company == "PRIVATE FILER LLC"
    assert b.companies[0].rank == 1, "sira numarasi istenen siralamayi izlemeli"


@pytest.mark.anyio
async def test_cerceve_donem_bitisleri_ayni_degil_ve_bu_gorunuyor(srv):
    """Bir cerceve 'ayni donem' DEGIL, 'ayni takvim kovasina dusen donemler'.
    Gercek olcumde (14 Agu 2026, CY2025Q1 gelir cercevesi) en erken bitis
    2025-02-23, en gec 2025-05-04 - 70 gun. Bunu gizlemek, karsilastirmayi
    esdeger sanmaya davet eder."""
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1", limit=100)
    assert b.period_end_earliest == "2025-02-23"
    assert b.period_end_latest == "2025-05-04"
    assert b.period_end_earliest != b.period_end_latest
    bitisler = {c.company: c.period_end for c in b.companies}
    assert bitisler["Apple Inc."] == "2025-03-29", "sirketin kendi donem sonu korunmali"
    assert bitisler["HOME DEPOT, INC."] == "2025-05-04"


@pytest.mark.anyio
async def test_cerceve_bilanco_kaleminde_anlik_esine_dusuyor(srv):
    """Olculdu: us-gaap/Assets/USD/CY2025Q1 -> 404, CY2025Q1I -> dolu. Model
    bu ayrimi bilmek zorunda kalmamali, ama hangisinin cevapladigini gormeli."""
    b = await srv.compare_companies(concept="total_assets", period="CY2025Q1")
    assert b.frame_requested == "CY2025Q1"
    assert b.frame == "CY2025Q1I" and b.frame_kind == "instant"
    assert b.companies[0].period_start is None, "anlik cercevede donem baslangici yok"
    assert b.companies[0].period_end == "2025-03-29"


@pytest.mark.anyio
async def test_cerceve_istenen_ticker_yoksa_sessizce_dusmuyor(srv):
    """Bir sirketin cercevede olmamasi 'sifir' ya da 'raporlamiyor' demek
    degil - farkli etiketle raporluyor ya da mali donemi kovaya oturmuyor
    olabilir. Sessizce listeden dusurmek modele yanlis sonuc cikartir."""
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1",
                                    tickers=["AAPL", "MSFT", "TSLA"])
    assert [c.ticker for c in b.companies] == ["AAPL"]
    assert b.missing_tickers == ["MSFT", "TSLA"]
    assert b.total_companies == 4, "total_companies cercevenin tamamini saymali"
    assert b.matching_request == 1, "istege uyan sayi ayri alanda olmali"


@pytest.mark.anyio
async def test_cerceve_filtrelense_de_sira_tum_sirketlere_gore(srv):
    """Uc sirket istendiginde 'birinci' olmak, sadece o ucun icinde birinci
    olmak degil; sira TUM cerceveye gore verilmezse rakam yaniltir."""
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1",
                                    tickers=["AAPL"], order="value_asc")
    assert b.companies[0].rank == 4, "artan siralamada Apple 4 sirketin sonuncusu"


@pytest.mark.anyio
async def test_cerceve_tickeri_olmayan_sirket_cokmeye_yol_acmiyor(srv):
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1", limit=100)
    ozel = [c for c in b.companies if c.company == "PRIVATE FILER LLC"][0]
    assert ozel.ticker is None and ozel.location is None
    assert [c for c in b.companies if c.ticker == "AAPL"], "ticker cozumu calismiyor"


@pytest.mark.parametrize("yazim", ["CY2025Q1", "2025Q1", "2025q1", " cy2025 q1 ",
                                   "2025-Q1", "2025_q1"])
@pytest.mark.anyio
async def test_cerceve_donem_yazimi_serbest(srv, yazim):
    b = await srv.compare_companies(concept="revenue", period=yazim, limit=1)
    assert b.frame == "CY2025Q1"


@pytest.mark.anyio
async def test_cerceve_anlasilmayan_donem_eyleme_donusturulebilir_hata_verir(srv):
    with pytest.raises(ValueError) as e:
        await srv.compare_companies(concept="revenue", period="last quarter")
    mesaj = str(e.value)
    assert "CY2025Q1" in mesaj and "CY2025" in mesaj


@pytest.mark.anyio
async def test_cerceve_bulunamayinca_denenenleri_sayiyor(srv):
    with pytest.raises(ValueError) as e:
        await srv.compare_companies(concept="OlmayanEtiket", period="CY2025Q1")
    mesaj = str(e.value)
    assert "OlmayanEtiket" in mesaj and "CY2025Q1" in mesaj
    assert "sec_edgar_list_available_concepts" in mesaj


@pytest.mark.anyio
async def test_cerceve_bos_data_sessiz_basari_olmuyor(srv):
    """KK-23'un ayni ilkesi: bos bir basari, gercek 'veri yok' cevabindan
    ayirt edilemez. Cerceve var ama icinde sirket yoksa bu bir anomalidir."""
    with pytest.raises(ValueError) as e:
        await srv.compare_companies(concept="OperatingIncomeLoss", period="CY2025Q1")
    assert "no companies" in str(e.value)


@pytest.mark.anyio
async def test_cerceve_ikinci_kez_indirilmiyor(srv):
    """Bir cerceve yanit gercekte megabaytlarca (olculdu: CY2025Q1 gelir
    cercevesi 2.543 sirket). Sayfalama icin yeniden indirmek SEC hiz sinirini
    yer."""
    ISTEK_KAYDI.clear()
    await srv.compare_companies(concept="revenue", period="CY2025Q1", limit=1)
    await srv.compare_companies(concept="revenue", period="CY2025Q1", limit=3)
    istekler = [u for u in ISTEK_KAYDI if "/frames/" in u]
    assert len(istekler) == 1, f"cerceve {len(istekler)} kez indirilmis"


# ============ Boyutlu XBRL (C): segment/cografya kirilimlari
@pytest.mark.anyio
async def test_boyut_kesfi_eksenleri_ve_uyeleri_listeliyor(srv):
    """Model eksen adini tahmin etmemeli; dosyalamanin kendi adlarini gormeli."""
    b = await srv.list_fact_dimensions(ticker="AAPL",
                                       accession_number="0000320193-25-000041")
    eksenler = {a.axis for a in b.axes}
    assert "us-gaap:StatementBusinessSegmentsAxis" in eksenler
    assert "srt:StatementGeographicalAxis" in eksenler
    assert "srt:ProductOrServiceAxis" in eksenler, "scenario icindeki boyut kacti"
    assert "tsla:PlantAxis" in eksenler, "typed dimension listelenmemis"

    segment = [a for a in b.axes if a.axis.endswith("StatementBusinessSegmentsAxis")][0]
    assert "tsla:AutomotiveSegmentMember" in segment.members
    assert "tsla:EnergyGenerationAndStorageSegmentMember" in segment.members
    assert b.dimensional_facts < b.total_facts, "boyutsuz fact'ler de sayilmali"
    assert "us-gaap:Revenues" in b.tags_with_dimensions


@pytest.mark.anyio
async def test_boyut_kesfi_kavrama_gore_daraltiliyor(srv):
    b = await srv.list_fact_dimensions(ticker="AAPL",
                                       accession_number="0000320193-25-000041",
                                       concept="gross_profit")
    assert {a.axis for a in b.axes} == {"srt:StatementGeographicalAxis"}
    assert b.tags_with_dimensions == ["us-gaap:GrossProfit"]


@pytest.mark.anyio
async def test_segment_kirilimi_geliyor_ve_kaynagina_kadar_izlenebiliyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    uyeler = {f.dimensions[0].member: f.value for f in b.facts
              if len(f.dimensions) == 1}
    assert uyeler["tsla:AutomotiveSegmentMember"] == 77000000000
    assert uyeler["tsla:EnergyGenerationAndStorageSegmentMember"] == 20690000000

    otomotiv = [f for f in b.facts
                if f.dimensions[0].member == "tsla:AutomotiveSegmentMember"
                and len(f.dimensions) == 1][0]
    assert otomotiv.context_id == "c-3" and otomotiv.fact_id == "f-2"
    assert otomotiv.unit == "USD" and otomotiv.decimals == "-6"
    assert otomotiv.period_start == "2025-01-01" and otomotiv.period_end == "2025-12-31"
    assert b.instance_url.endswith("_htm.xml")


@pytest.mark.anyio
async def test_uye_toplami_ile_konsolide_yan_yana_veriliyor(srv):
    """Arac hangisinin dogru oldugunu SECMEZ, ikisini de gosterir."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    assert len(b.reconciliation) == 1
    m = b.reconciliation[0]
    assert m.members_sum == 97690000000
    assert m.consolidated_value == 97690000000
    assert m.agrees is True and m.difference == 0


@pytest.mark.anyio
async def test_tutmayan_toplam_gizlenmiyor(srv):
    """Gercek dosyalamalar uye toplamini tutturamayabiliyor (XBRL US DQC_0150
    kurali tam bunun icin var). Tutmadiginda arac bunu SOYLEMELI."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="gross_profit", axis="srt:StatementGeographicalAxis")
    m = b.reconciliation[0]
    assert m.members_sum == 4000000000
    assert m.consolidated_value == 17094000000
    assert m.agrees is False
    assert m.difference == 13094000000


@pytest.mark.anyio
async def test_cok_boyutlu_fact_toplamaya_girmiyor(srv):
    """Segment VE cografya ile nitelenmis bir rakam, segment kiriliminin bir
    parcasi degil kesisimidir; toplama katmak cift sayar."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    cok = [f for f in b.facts if len(f.dimensions) > 1]
    assert cok, "cok boyutlu fact hic donmemis - fixture bozulmus olabilir"
    assert {d.axis for d in cok[0].dimensions} == {
        "us-gaap:StatementBusinessSegmentsAxis", "srt:StatementGeographicalAxis"}
    assert b.reconciliation[0].members_sum == 97690000000, \
        "41 milyarlik kesisim toplama karismis"


@pytest.mark.anyio
async def test_eksen_verilmezse_mutabakat_hesaplanmiyor(srv):
    """Farkli eksenlerdeki uyeleri toplamak anlamsiz; sessizce yapmaktansa
    hic yapmamak dogru."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041", concept="revenue")
    assert b.reconciliation == []
    assert b.total_matching >= 4


@pytest.mark.anyio
async def test_uyeye_gore_daraltma_calisiyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis",
        member="tsla:EnergyGenerationAndStorageSegmentMember")
    assert b.total_matching == 1
    assert b.facts[0].value == 20690000000


@pytest.mark.anyio
async def test_sayisal_olmayan_ve_nil_fact_sessizce_sayiya_cevrilmiyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="tsla:SegmentDescription")
    f = b.facts[0]
    assert f.value is None and f.text_value == "Design and sale of vehicles"

    n = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="srt:StatementGeographicalAxis")
    nil = [x for x in n.facts if x.is_nil]
    assert nil and nil[0].value is None, "nil fact sifir sanilmis"
    # Toplanacak sayisal uye kalmadiginda mutabakat satiri HIC uretilmiyor.
    # "members_sum = 0" demek, sifirlarin toplandigini soylerdi; dogru olan,
    # toplanacak bir sey olmadigini soylemek.
    assert n.reconciliation == [], "nil fact toplama girmis ve 0 diye raporlanmis"


@pytest.mark.anyio
async def test_typed_dimension_dusurulmuyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="total_assets", axis="tsla:PlantAxis")
    d = b.facts[0].dimensions[0]
    assert d.member is None and d.typed_value == "Fremont"


@pytest.mark.anyio
async def test_pay_bolu_payda_birimi_okunuyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="eps_diluted")
    assert b.facts[0].unit == "USD/shares"


@pytest.mark.anyio
async def test_inline_oncesi_dosyalamada_dosyalayanin_instance_i_okunuyor(srv):
    """Inline XBRL zorunlulugu kademeli geldi (buyuk hizlandirilmis
    dosyalayanlar icin 2019-06-15'te biten donemler). Oncesinde `_htm.xml` yok;
    instance'i dosyalayan sunuyordu. Linkbase'ler ayni uzantiyi paylasir."""
    b = await srv.list_fact_dimensions(ticker="AAPL",
                                       accession_number="0000320193-24-000123")
    assert b.instance_url.endswith("tsla-20181231.xml")
    assert not b.instance_url.endswith("_lab.xml"), "linkbase instance sanilmis"


@pytest.mark.anyio
async def test_xbrl_tasimayan_dosyalamada_eyleme_donusturulebilir_hata(srv):
    with pytest.raises(ValueError) as e:
        await srv.list_fact_dimensions(ticker="AAPL",
                                       accession_number="0000320193-25-000012")
    mesaj = str(e.value)
    assert "no XBRL instance" in mesaj and "aapl-8k.htm" in mesaj


@pytest.mark.anyio
async def test_boyutlu_fact_bulunamayinca_mevcut_etiketler_soyleniyor(srv):
    with pytest.raises(ValueError) as e:
        await srv.get_dimensional_facts(
            ticker="AAPL", accession_number="0000320193-25-000041",
            concept="operating_cash_flow")
    mesaj = str(e.value)
    assert "sec_edgar_list_fact_dimensions" in mesaj
    assert "us-gaap:Revenues" in mesaj


@pytest.mark.anyio
async def test_instance_ikinci_kez_indirilmiyor(srv):
    ISTEK_KAYDI.clear()
    await srv.list_fact_dimensions(ticker="AAPL",
                                   accession_number="0000320193-25-000041")
    await srv.get_dimensional_facts(ticker="AAPL",
                                    accession_number="0000320193-25-000041",
                                    concept="revenue")
    indirme = [u for u in ISTEK_KAYDI if u.endswith("_htm.xml")]
    assert len(indirme) == 1, f"instance {len(indirme)} kez indirilmis"


@pytest.mark.anyio
async def test_raporlanmayan_toplam_sifir_sanilmiyor(srv):
    """Bir dosyalama toplami `xsi:nil` ile isaretleyebilir. Onu 0 diye okumak,
    "toplam raporlanmadi" ile "toplam sifir" arasindaki farki yok eder ve
    mutabakati uydurma bir 9,0 milyar dolarlik fark uzerine kurar."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="operating_income", axis="us-gaap:StatementBusinessSegmentsAxis")
    m = b.reconciliation[0]
    assert m.members_sum == 10500000000
    assert m.consolidated_value is None, "nil toplam 0 sanilmis"
    assert m.difference is None and m.agrees is None


@pytest.mark.anyio
async def test_bozuk_instance_cig_traceback_yerine_eyleme_donusturulebilir_hata(srv):
    """SEC bazen XML yerine HTML hata sayfasi dondurur; indirme de kesilebilir.
    Cig bir ParseError cagirana ne yapacagini soylemez (§18)."""
    from edgar_mcp import xbrl

    with pytest.raises(ValueError) as e:
        xbrl.ayristir("<html><body>Service temporarily unavailable</body>")
    mesaj = str(e.value)
    assert "could not be parsed as XML" in mesaj
    assert "<html>" in mesaj, "hata mesaji ne geldigini gostermiyor"


# ============ Ceyreklik mali yil etiketi ve ANLIK kayitlar (15 Agu 2026)
@pytest.mark.anyio
async def test_ceyreklik_mali_yil_etiketi_sirketin_kendi_yiliyla_ayni(srv):
    """WMT'nin mali yili 31 Ocak'ta biter, yani KENDI ceyrekleri bir onceki
    takvim yilinda biter. Kayma yillik capalardan turetilip ceyrekliklere
    oldugu gibi uygulanirsa etiket bir yil geri kayar: arac yila FY2026,
    o yilin ilk ceyregine FY2025 derdi. Ayni arac, ayni sirket, iki cevap."""
    yillik = await srv.get_concept_series(ticker="WMT", concept="revenue",
                                          period="annual")
    assert {p.fiscal_year for p in yillik.points} == {2025, 2026}

    ceyrek = await srv.get_concept_series(ticker="WMT", concept="revenue",
                                          period="quarterly")
    etiketler = {p.period_end: p.fiscal_year for p in ceyrek.points}
    assert etiketler["2025-04-30"] == 2026, "FY2026'nin Q1'i FY2025 sanilmis"
    assert etiketler["2025-07-31"] == 2026
    assert yillik.fiscal_year_derived and ceyrek.fiscal_year_derived


@pytest.mark.anyio
async def test_yillik_seri_ceyrek_sonu_bakiyeleri_icermiyor(srv):
    """Bilanco kalemleri ANIdir, `days` tasimazlar. Yillik filtreden oldugu
    gibi gecerlerse `total_assets` + `annual` her CEYREK sonu bakiyeyi
    dondurur ve ayni mali yil birden fazla kez tekrarlanir."""
    b = await srv.get_concept_series(ticker="WMT", concept="total_assets",
                                     period="annual")
    bitisler = [p.period_end for p in b.points]
    assert bitisler == ["2025-01-31", "2026-01-31"], bitisler
    assert len({p.fiscal_year for p in b.points}) == len(b.points), \
        "ayni mali yil birden fazla kez donmus"


@pytest.mark.anyio
async def test_ceyreklik_seri_anlik_kalemi_bos_dondurmuyor(srv):
    """`period="quarterly"` anlik kayitlari tamamen eliyordu: HTTP 200 + BOS
    liste. KK-23: bos bir basari, gercek "veri yok" cevabindan ayirt edilemez."""
    b = await srv.get_concept_series(ticker="WMT", concept="total_assets",
                                     period="quarterly")
    assert b.total_periods == 4, f"{b.total_periods} donem dondu"
    assert {p.period_end for p in b.points} >= {"2025-04-30", "2025-07-31"}


# ============ 15 Agu 2026 denetiminde bulunan kusurlar
def test_gizli_blok_kapanmayan_etikette_belgeyi_yutmuyor():
    """Gercek EDGAR HTML'i `<td>`/`<tr>` kapanislarini atlar ve `<img>` gibi
    kapanmayan elemanlar tasir. Ilk surumde gizli bir `<td>` acildiktan sonra
    her sey gizli sayiliyordu: olculdu, 2,4 MB'lik bir belge 3 karaktere
    dusuyordu - HTTP 200, hata yok, "bu dosyalama bos" (P-19)."""
    from edgar_mcp.belge import metne_cevir

    kapanmamis = ('<table><tr><td style="display:none">gizli<tr><td>Revenue'
                  '<td>391,035</table><div>Item 7.</div><p>' + "Govde. " * 60 + "</p>")
    m = metne_cevir(kapanmamis)
    assert "Revenue" in m and "391,035" in m and "Govde." in m
    assert "gizli" not in m, "gizli hucre metne sizmis"

    assert "REAL" in metne_cevir('<img style="display:none"><p>REAL BODY</p>')

    # Ic ice ayni ad: erken kapanip gizli icerigi SIZDIRMAMALI
    ic_ice = '<div style="display:none"><div>x</div>SIZINTI</div><p>GERCEK</p>'
    m2 = metne_cevir(ic_ice)
    assert "GERCEK" in m2 and "SIZINTI" not in m2


def test_gizli_filtresi_belgeyi_yutarsa_filtresiz_donuyor():
    """Emniyet agi: filtre belgenin neredeyse tamamini yutuyorsa filtre
    yaniliyordur. Gurultulu ama dolu metin, sessizce bos metinden iyidir."""
    from edgar_mcp.belge import metne_cevir

    govde = '<div style="display:none">' + "x" * 100 + "<p>" + "gercek govde. " * 2000
    m = metne_cevir(govde)
    assert len(m) > 20000, f"emniyet agi devreye girmedi: {len(m)} karakter"


@pytest.mark.anyio
async def test_mutabakat_sayfalama_sinirindan_etkilenmiyor(srv):
    """Mutabakat dondurulen SAYFA uzerinden hesaplaniyordu, konsolide deger
    dosyalamanin TAMAMI uzerinden: limit=1 ile ayni dosyalama "20,7 milyar
    dolarlik fark var" diyordu. Gercek bir 10-K'da segment sorgusu varsayilan
    40 satiri asiyor, yani bu uydurma fark sahada gorulurdu."""
    genis = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis", limit=40)
    dar = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis", limit=1)
    assert dar.returned == 1 and genis.returned > 1
    assert dar.reconciliation[0].members_sum == genis.reconciliation[0].members_sum
    assert dar.reconciliation[0].agrees is True


@pytest.mark.anyio
async def test_mutabakat_disarida_biraktiklarini_sayiyor(srv):
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    m = b.reconciliation[0]
    assert m.members_counted == 2
    assert m.excluded_from_sum == {"multi_axis": 1}, m.excluded_from_sum


@pytest.mark.anyio
async def test_revizyon_geri_alinan_degerde_seriyle_celismiyor(srv):
    """Bir rakam 100 -> 90 -> 100 diye revize edilip geri alinirsa, FARKLI
    degerlerin sonuncusu 90'dir ama EN SON DOSYALANAN deger 100'dur. Ilk surum
    "en son 90" diyordu ve seri araci ayni donem icin 100 gosteriyordu - iki
    arac, ayni gercek, iki cevap."""
    seri = await srv.get_concept_series(ticker="MSFT", concept="revenue",
                                        period="annual")
    rev = await srv.get_fact_revisions(ticker="MSFT", concept="revenue")
    son_seri = {p.period_end: p.value for p in seri.points}
    for r in rev.revisions:
        assert r.latest_value == son_seri[r.period_end], (
            f"{r.period_end}: revizyon {r.latest_value}, seri {son_seri[r.period_end]}")


@pytest.mark.anyio
async def test_ust_kaynak_hatasi_eyleme_donusturulebilir(srv):
    """SEC'in gercek kisitlama yaniti HTTP 403 + HTML govde. Ilk surumde bu
    cig `HTTPStatusError` olarak modele gidiyordu; model ne yapacagini
    bilemezdi."""
    import httpx as _h

    from edgar_mcp.client import EdgarClient

    def kisitli(request: _h.Request) -> _h.Response:
        if "company_tickers" in str(request.url):
            return _h.Response(200, json=TICKERS)
        return _h.Response(403, text="<html>Undeclared Automated Tool</html>")

    c = EdgarClient()
    c._http = _h.AsyncClient(transport=_h.MockTransport(kisitli),
                             headers={"User-Agent": "Test Runner test@example.com"})
    srv._client = c
    with pytest.raises(ValueError) as e:
        await srv.get_company_profile(ticker="AAPL")
    mesaj = str(e.value)
    assert "403" in mesaj and "SEC_USER_AGENT" in mesaj


@pytest.mark.anyio
async def test_json_yerine_html_gelirse_soyleniyor(srv):
    import httpx as _h

    from edgar_mcp.client import EdgarClient

    def html_don(request: _h.Request) -> _h.Response:
        return _h.Response(200, text="<html><body>Service unavailable</body></html>")

    c = EdgarClient()
    c._http = _h.AsyncClient(transport=_h.MockTransport(html_don),
                             headers={"User-Agent": "Test Runner test@example.com"})
    srv._client = c
    with pytest.raises(ValueError) as e:
        await srv.get_company_profile(ticker="AAPL")
    assert "not JSON" in str(e.value) and "<html>" in str(e.value)


@pytest.mark.anyio
async def test_ayni_cik_iki_sembol_tasiyorsa_ikisi_de_gorunuyor(srv):
    """GOOG/GOOGL gibi hisse siniflari ayni CIK'e duser. CIK'i anahtar yapan
    ilk surumde ikinci sembol birinciyi eziyordu ve istenen sirket ne listede
    ne de missing_tickers'ta goruluyordu."""
    b = await srv.compare_companies(concept="revenue", period="CY2025Q1",
                                    tickers=["AAPL", "AAPL"])
    assert b.matching_request == 1
    assert b.companies[0].ticker == "AAPL, AAPL"


@pytest.mark.anyio
async def test_recent_akisinin_disindaki_dosyalamalar_bildiriliyor(srv):
    """SEC `filings.recent` alanini ~1000 dosyalamada keser. Bunu okumadan
    `has_more: false` demek, otuz yillik gecmisi olan bir sirket icin
    "baska dosyalama yok" iddiasi olurdu."""
    b = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=50)
    assert b.older_filings_exist is True
    assert b.has_more is True, "eski dosyalamalar varken has_more False kalmis"


def test_main_kullanici_ajani_olmadan_baslamayi_reddediyor(monkeypatch):
    """README "refuses to start without SEC_USER_AGENT" diyor. Ilk surumde
    sunucu aciliyor, on araci ilan ediyor ve ancak ilk cagride patliyordu -
    yani ortam degiskeni eksik bir konteyner canlilik kontrolunu geciyordu."""
    from edgar_mcp import server as s

    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setattr(s, "_client", None)
    with pytest.raises(RuntimeError) as e:
        s.main()
    assert "SEC_USER_AGENT" in str(e.value)


@pytest.mark.anyio
async def test_onbellekler_sinirli(srv):
    """companyfacts en buyuk nesne: olculdu, 11 MB JSON -> 45 MB yerlesik.
    Sinirsiz birakmak, masaustu istemci acik kaldigi surece yasayan bir stdio
    surecinde yirmi sirket taraninca ~1 GB demekti. Diger her onbellek acik
    bir sinirla ve gerekcesiyle yaziliydi; en buyugu tek sinirsiz olandi."""
    c = srv._client
    for cik in ("0000000001", "0000000002", "0000000003", "0000000004"):
        await c.company_facts(cik)
    assert len(c._facts_cache) <= 2, f"{len(c._facts_cache)} companyfacts tutuluyor"
    assert "0000000004" in c._facts_cache, "en son cekilen girdi atilmis"

    # Gercek CIK'ler kullaniliyor: sahte veri artik bilinmeyen CIK'e 404
    # donuyor (gercek sozlesme), uydurma numaralar burada hata verirdi.
    for cik in ("0000320193", "0000789019", "0001318605",
                "0000104169", "0000055067", "0000320193"):
        await c.submissions(cik)
    assert len(c._subs_cache) <= 4, f"{len(c._subs_cache)} submissions tutuluyor"


@pytest.mark.anyio
async def test_takma_ad_boyutlu_fact_te_cift_saymiyor(srv):
    """Seri aracinda takma adin TUM etiketlerini birlestirmek dogru (KK-8:
    tarihsel gecmis kirpilmasin). Boyutlu fact'lerde AYNI sey cift sayimdir:
    bir dosyalama ayni segmenti hem `Revenues` hem `SalesRevenueNet` altinda
    tasiyorsa ikisi de toplama girer ve uye toplami konsolidenin iki katina
    cikar. Fixture bu iki etiketi ayni context'lerde tasiyor."""
    b = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    assert {f.tag for f in b.facts} == {b.resolved_tag}, \
        f"birden fazla etiket karismis: {sorted({f.tag for f in b.facts})}"
    assert b.reconciliation[0].members_sum == 97690000000


# ============ Ilerleme bildirimi (MCP 2026-07-28, basic/utilities/progress)
class _SahteBaglam:
    """Gercek `Context` yerine: yalnizca `report_progress` cagrilarini kaydeder."""

    def __init__(self) -> None:
        self.cagrilar: list[tuple[float, float | None, str | None]] = []

    async def report_progress(self, progress, total=None, message=None):
        self.cagrilar.append((progress, total, message))


@pytest.mark.anyio
async def test_uzun_suren_araclar_ilerleme_bildiriyor(srv):
    """Spesifikasyon bunu zorunlu tutmuyor ama bekleten bir cagride kullanim
    ornegi tam olarak bu: 2,7 MB instance indirmek ya da 2,4 MB dosyalamayi
    metne cevirmek saniyeler suruyor."""
    b = _SahteBaglam()
    await srv.read_filing_text(ticker="AAPL", max_characters=500, ctx=b)
    assert len(b.cagrilar) >= 2, b.cagrilar
    assert all(t == 3 for _, t, _ in b.cagrilar), "toplam adim bildirilmiyor"
    assert any("Downloading" in (m or "") for *_, m in b.cagrilar)

    b2 = _SahteBaglam()
    await srv.list_fact_dimensions(ticker="AAPL",
                                   accession_number="0000320193-25-000041", ctx=b2)
    assert any("XBRL" in (m or "") for *_, m in b2.cagrilar), b2.cagrilar

    b3 = _SahteBaglam()
    await srv.compare_companies(concept="revenue", period="CY2025Q1", ctx=b3)
    assert b3.cagrilar


@pytest.mark.anyio
async def test_baglam_yokken_araclar_calismaya_devam_ediyor(srv):
    """`ctx` opsiyonel olmali: testler arac fonksiyonlarini dogrudan cagiriyor
    ve istemci `progressToken` yollamadiginda SDK zaten hicbir sey gondermiyor."""
    b = await srv.read_filing_text(ticker="AAPL", max_characters=200)
    assert b.returned_characters == 200


@pytest.mark.anyio
async def test_baglam_parametresi_arac_semasinda_gorunmuyor(srv):
    """SDK baglami tur ipucundan bulup enjekte ediyor; modele bir parametre
    gibi gostermek onu doldurmaya calismasina yol acardi.

    Olculdu (15 Agu 2026): IKI ayri `Context` sinifi var ve arac katmani
    yalnizca `mcp.server.mcpserver.context.Context`'i taniyor;
    `mcp.server.context.Context` ile yazilinca sunucu ACILMIYOR bile
    (PydanticInvalidForJsonSchema)."""
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        ozellikler = (t.input_schema or {}).get("properties", {})
        assert "ctx" not in ozellikler, f"{t.name} baglami semada gosteriyor"


def test_hicbir_arac_protokol_hatasi_firlatmiyor():
    """SDK v2'de `MCPError` PROTOKOL hatasidir ve model onu HIC gormez; her
    baska istisna `isError=True` + `str(e)` olarak modele ulasir. Bu depodaki
    hata mesajlari modelin ne yapacagini soylemek icin yazildi (§18/P-13), yani
    onlari `MCPError` ile firlatmak butun o emegi gorunmez kilardi."""
    import ast
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    for f in sorted(kok.glob("*.py")):
        agac = ast.parse(f.read_text(encoding="utf-8"))
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Raise) or dugum.exc is None:
                continue
            cagri = dugum.exc
            ad = getattr(getattr(cagri, "func", cagri), "id", None) \
                or getattr(getattr(cagri, "func", cagri), "attr", None)
            assert ad not in ("MCPError", "McpError"), (
                f"{f.name}: protokol hatasi firlatiliyor, model mesaji gormez")


# ============ Ikinci denetim turu (15 Agu 2026 aksami)
def test_metin_cikarimi_surecten_surece_ayni_sonucu_veriyor():
    """`_ORTULU_KAPANIS` degerleri KUME oldugunda iterasyon sirasi CPython'un
    surec basina rastgelelesen string hash'ine baglanıyordu: `<tr>` bir `<td>`
    aciken geldiginde hangisinin kapatildigi seed'e gore degisiyor, gizli bir
    `<tr>` yiginda asili kaliyor ve tablonun geri kalani yutuluyordu.
    PYTHONHASHSEED=0/2'de mali tablo geliyor, 1/3'te bos donuyordu - ayni
    dosyalama, ayni kod. Sunucunun kendi tanimi "deterministic tool calls"."""
    import subprocess
    import sys

    kod = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from edgar_mcp.belge import metne_cevir\n"
        "h = '<table><tr style=\"display:none\"><td>GIZLI<tr><td>Revenue"
        "<td>391035</table><div>Item 8.</div><p>' + 'Govde. ' * 80\n"
        "print(metne_cevir(h))\n"
    )
    ciktilar = set()
    for seed in ("0", "1", "2", "3", "5"):
        r = subprocess.run([sys.executable, "-c", kod],
                           cwd=str(KOK), capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        ciktilar.add(r.stdout)
    assert len(ciktilar) == 1, f"{len(ciktilar)} farkli cikti uretildi"
    (tek,) = ciktilar
    assert "391035" in tek and "GIZLI" not in tek


def test_gizli_blok_icinde_ayirici_uretilmiyor():
    """Yutulan bir tablo yine de tum `|` iskeletini yaziyordu; cikti uzun
    kaldigi icin `metne_cevir` icindeki yutma emniyet agi HIC devreye
    girmiyordu. Emniyet agini kor eden sey buydu."""
    from edgar_mcp.belge import metne_cevir

    m = metne_cevir('<div style="display:none"><table><tr><td>a<td>b</table></div><p>X</p>')
    assert m.strip() == "X", repr(m)


@pytest.mark.anyio
async def test_yil_sonu_aralik_ocak_arasinda_oynayan_takvim(srv):
    """52/53 haftalik takvimlerde yil sonu yil basi ile yil sonu arasinda gidip
    geliyor (2022-12-31, sonraki yil 2024-01-04). Sinir donemin kendi TAKVIM
    yilinda kurulunca Aralik'ta biten her yil sona ~360 gun uzak dusuyor:
    yillik bilancolarin yarisi eleniyor ve iki ardisik mali yil ayni etiketi
    aliyordu."""
    y = await srv.get_concept_series(ticker="K", concept="revenue", period="annual")
    etiketler = {p.period_end: p.fiscal_year for p in y.points}
    assert etiketler == {"2022-01-01": 2021, "2022-12-31": 2022,
                         "2023-12-30": 2023, "2025-01-04": 2024}, etiketler
    assert len(set(etiketler.values())) == len(etiketler), "ayni yil iki kez"

    b = await srv.get_concept_series(ticker="K", concept="total_assets",
                                     period="annual")
    assert b.total_periods == 4, f"{b.total_periods} yil sonu bilancosu dondu"


@pytest.mark.anyio
async def test_uye_filtresi_mutabakati_bozmuyor(srv):
    """P-27 `limit` icin duzeltilmisti; `member` ayni yoldan siziyordu: tek bir
    uye istendiginde o uyenin degeri tuzel kisi geneli toplamiyla
    karsilastiriliyor ve tam tutan bir dosyalama fark uyduruyordu."""
    hepsi = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis")
    tek = await srv.get_dimensional_facts(
        ticker="AAPL", accession_number="0000320193-25-000041",
        concept="revenue", axis="us-gaap:StatementBusinessSegmentsAxis",
        member="tsla:AutomotiveSegmentMember")
    # Iki fact: uyenin tek basina oldugu context ve segment+cografya kesisimi.
    assert tek.total_matching == 2, "uye filtresi uygulanmamis"
    assert all(any(d.member == "tsla:AutomotiveSegmentMember" for d in f.dimensions)
               for f in tek.facts)
    assert tek.reconciliation[0].members_sum == hepsi.reconciliation[0].members_sum
    assert tek.reconciliation[0].agrees is True


@pytest.mark.anyio
async def test_belge_indirmede_403_eyleme_donusturulebilir(srv):
    """`filing_document` `www.sec.gov/Archives`'e giden TEK yol, yani SEC'in
    "Undeclared Automated Tool" engel sayfasini gorecek en olasi yer - ve
    hata yolu duzeltildiginde bu metot atlanmisti."""
    import httpx as _h

    from edgar_mcp.client import EdgarClient

    def engelli(request: _h.Request) -> _h.Response:
        u = str(request.url)
        if "company_tickers" in u:
            return _h.Response(200, json=TICKERS)
        if "/submissions/" in u:
            return _h.Response(200, json=SUBS)
        if u.endswith("/index.json"):
            return _h.Response(200, json=DIZIN_JSON)
        return _h.Response(403, text="<html>Undeclared Automated Tool</html>")

    c = EdgarClient()
    c._http = _h.AsyncClient(transport=_h.MockTransport(engelli),
                             headers={"User-Agent": "Test Runner test@example.com"})
    srv._client = c
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL", max_characters=200)
    assert "403" in str(e.value) and "SEC_USER_AGENT" in str(e.value)


@pytest.mark.anyio
async def test_200_ile_gelen_engel_sayfasi_dosyalama_metni_sanilmiyor(srv):
    """SEC kisitlamayi bazen HTTP 200 ile de yapiyor. Engel sayfasini metne
    cevirip dondurmek, modele "dosyalama bu kadarmis" dedirtir (P-19)."""
    import httpx as _h

    from edgar_mcp.client import EdgarClient

    def iki_yuz(request: _h.Request) -> _h.Response:
        u = str(request.url)
        if "company_tickers" in u:
            return _h.Response(200, json=TICKERS)
        if "/submissions/" in u:
            return _h.Response(200, json=SUBS)
        if u.endswith("/index.json"):
            return _h.Response(200, json=DIZIN_JSON)
        return _h.Response(200, text="<html><body>Your Request Originates from "
                                     "an Undeclared Automated Tool</body></html>")

    c = EdgarClient()
    c._http = _h.AsyncClient(transport=_h.MockTransport(iki_yuz),
                             headers={"User-Agent": "Test Runner test@example.com"})
    srv._client = c
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL", max_characters=200)
    assert "block page" in str(e.value)


# ------------------------------------------------------- eski dosyalama akislari
@pytest.mark.anyio
async def test_eski_akis_varsayilan_olarak_okunmuyor_ama_bildiriliyor(srv):
    """Varsayilan davranis degismedi: recent akisi okunur, eski akislarin
    VARLIGI bildirilir. Bildirmemek "sirketin baska dosyalamasi yok" diye
    okunurdu (§16)."""
    s = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert s.older_filings_exist is True
    assert s.older_filings_read is False
    assert s.has_more is True, "eksik gecmis has_more ile de isaretlenmeli"
    assert all(x.accession_number.startswith("0000320193-2") for x in s.filings), \
        "eski akis istenmedigi halde okunmus"


@pytest.mark.anyio
async def test_eski_akis_include_older_ile_birlesiyor(srv):
    s = await srv.list_recent_filings(ticker="AAPL", limit=50, include_older=True)
    numaralar = [x.accession_number for x in s.filings]
    assert "0000320193-99-000010" in numaralar, "eski akis okunmadi"
    assert "0000320193-97-000005" in numaralar
    assert s.older_filings_read is True
    assert s.older_feeds_skipped == 0
    assert s.total_matching == 9, numaralar   # 7 recent + 2 eski
    # Birlesik liste TARIHE gore siralanmali: iki akisin kendi ic sirasi,
    # birlestirildiginde dogru sirayi vermez.
    tarihler = [x.filing_date for x in s.filings]
    assert tarihler == sorted(tarihler, reverse=True), tarihler


@pytest.mark.anyio
async def test_eski_akiste_birincil_belge_yoksa_alan_bos_kaliyor(srv):
    """Olculdu: eski akis dosyasinda `primaryDocument` bulunmuyordu. Kod bunu
    IndexError'a cevirmemeli; erisim numarasi hala dosyalamayi tanimliyor."""
    s = await srv.list_recent_filings(ticker="AAPL", limit=50, include_older=True)
    eski = [x for x in s.filings if x.accession_number == "0000320193-99-000010"][0]
    assert eski.primary_document_url is None
    yeni = [x for x in s.filings if x.accession_number == "0000320193-25-000073"][0]
    assert yeni.primary_document_url.endswith("aapl-20250927.htm")


@pytest.mark.anyio
async def test_form_filtresi_buyuk_kucuk_harf_duyarsiz(srv):
    """`10-k` yazan bir cagri eskiden BOS liste donuyordu - "bu sirket hic
    10-K vermemis" gibi okunan bir sonuc."""
    kucuk = await srv.list_recent_filings(ticker="AAPL", form_type="10-k", limit=50)
    buyuk = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=50)
    assert kucuk.total_matching == buyuk.total_matching == 2
    # Amendment ayri belge olarak KALIYOR: 10-K/A, 10-K degildir.
    assert all(x.form == "10-K" for x in kucuk.filings)


@pytest.mark.anyio
async def test_eski_akis_siniri_sessiz_degil(srv, monkeypatch):
    """Kapsam kisitlamasi bildirilmezse "hepsini gordum" diye okunur."""
    import copy
    cok = copy.deepcopy(SUBS)
    cok["filings"]["files"] = [
        {"name": f"CIK0000320193-submissions-{i:03d}.json"} for i in range(1, 7)
    ]

    async def sahte(cik):
        return cok

    monkeypatch.setattr(srv._client, "submissions", sahte)
    s = await srv.list_recent_filings(ticker="AAPL", limit=50, include_older=True)
    assert s.older_feeds_skipped == 2, "6 dosyanin 4'u okunur, 2'si bildirilmeli"
    assert s.has_more is True


@pytest.mark.anyio
async def test_eski_akis_ana_submissions_onbellegini_atmiyor(srv):
    """Ek akislar `_subs_cache`i paylassaydi, DORT ek dosya (onbellek siniri
    da dort) 1-2 MB'lik ana kaydi disari atar ve sonraki cagri onu yeniden
    indirirdi. Dort dosya, siniri ASMAK icin secildi: ucle bu test paylasilan
    onbellekte de yesil kalir, yani hicbir sey olcmezdi."""
    c = srv._client
    ISTEK_KAYDI.clear()
    await c.submissions("0000320193")
    for i in range(1, 5):
        await c.submissions_extra(f"CIK0000320193-submissions-{i:03d}.json")
    await c.submissions("0000320193")
    assert sum(u.endswith("/submissions/CIK0000320193.json") for u in ISTEK_KAYDI) == 1
    assert sum("-submissions-" in u for u in ISTEK_KAYDI) == 4


@pytest.mark.anyio
async def test_eski_akis_ayni_cagride_iki_kez_indirilmiyor(srv):
    ISTEK_KAYDI.clear()
    await srv.list_recent_filings(ticker="AAPL", limit=5, include_older=True)
    await srv.list_recent_filings(ticker="AAPL", limit=5, include_older=True)
    assert sum("-submissions-001.json" in u for u in ISTEK_KAYDI) == 1


@pytest.mark.anyio
async def test_metin_araci_eski_akistaki_dosyalamayi_okuyabiliyor(srv):
    """Arac kendi ciktisini reddetmemeli: include_older ile donen bir erisim
    numarasi, metin aracina verildiginde de bulunmali."""
    t = await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-99-000010",
                                   max_characters=200)
    assert t.accession_number == "0000320193-99-000010"
    # Birincil belge adi bilinmiyor: en buyuk okunabilir dosya secildi ve bu
    # SOYLENDI. Sessizce secmek "SEC'in birincil belgesi budur" iddiasi olurdu.
    assert t.primary_document_known is False
    assert t.document_name == "aapl-8k.htm", [b.name for b in t.available_documents]
    assert all(b.is_primary is False for b in t.available_documents)


@pytest.mark.anyio
async def test_bilinmeyen_erisim_numarasi_eylem_soyluyor(srv):
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL", accession_number="0000000000-00-000000")
    assert "sec_edgar_list_filings" in str(e.value)


# ------------------------------------------------------------ tam metin aramasi
@pytest.mark.anyio
async def test_arama_vurusu_okunabilir_adrese_cevriliyor(srv):
    r = await srv.search_filings(query='"tariff"', form_type="10-K", ticker="TSLA")
    ilk = r.results[0]
    # `_id` = erisim numarasi + belge adi. Ikisi de read_filing_text'in
    # parametreleri; ayirmadan donmek modele bir dizge birakirdi.
    assert ilk.accession_number == "0001193125-12-081990"
    assert ilk.document == "d279413dex1050.htm"
    assert ilk.document_url == ("https://www.sec.gov/Archives/edgar/data/1318605/"
                                "000119312512081990/d279413dex1050.htm")
    assert ilk.ticker == "TSLA" and ilk.cik == "0001318605"
    assert ilk.description == "SUPPLY AGREEMENT"
    assert ilk.relevance_score == 6.45
    assert r.total_matching == 12 and r.total_is_exact is True
    assert r.has_more is True, "12 vurusun 2'si donduruldu"
    assert r.coverage_note is None


@pytest.mark.anyio
async def test_arama_ticker_cozulemeyen_vurusu_gizlemiyor(srv):
    """company_tickers.json fon ve yabanci ihracci tasimaz. Bu vuruslari
    atmak, sonucu sessizce eksiltirdi."""
    r = await srv.search_filings(query='"tariff"')
    fon = r.results[1]
    assert fon.cik == "0000999999" and fon.ticker is None
    assert fon.document_url.endswith("000099999924000001/fund-main.htm")


@pytest.mark.anyio
async def test_arama_ticker_ve_tarih_filtreleri_sorguya_giriyor(srv):
    ISTEK_KAYDI.clear()
    await srv.search_filings(query="tariff", ticker="TSLA", form_type="10-K",
                             start_date="2020-01-01", end_date="2021-12-31",
                             offset=100)
    u = [x for x in ISTEK_KAYDI if "efts" in x][0]
    assert "ciks=0001318605" in u and "forms=10-K" in u
    assert "dateRange=custom" in u and "startdt=2020-01-01" in u
    assert "enddt=2021-12-31" in u and "from=100" in u


@pytest.mark.anyio
async def test_arama_bos_sonucta_kapsam_notu_veriyor(srv):
    """Sifir sonuc "hic dosyalanmamis" DEGIL: indeks 2001 oncesini pratikte
    tasimiyor ve bunu soylemeyen bir yanit yanlis okunur."""
    r = await srv.search_filings(query="bos")
    assert r.results == [] and r.total_matching == 0
    assert r.coverage_note and "2001" in r.coverage_note
    assert r.has_more is False


@pytest.mark.anyio
async def test_arama_2001_oncesine_uzaninca_uyariyor(srv):
    r = await srv.search_filings(query="tariff", start_date="1998-01-01")
    assert r.coverage_note and "1996" in r.coverage_note


@pytest.mark.anyio
async def test_arama_alt_sinir_kesin_sayi_gibi_sunulmuyor(srv):
    r = await srv.search_filings(query="altsinir")
    assert r.total_matching == 10000 and r.total_is_exact is False
    assert r.has_more is True


@pytest.mark.anyio
async def test_arama_hata_govdesi_bos_sonuc_sanilmiyor(srv):
    """SEC hatayi HTTP 200 + govde ile de bildiriyor (olculdu). Bunu bos sonuc
    saymak, en sessiz yanlis cevabi uretirdi."""
    with pytest.raises(ValueError) as e:
        await srv.search_filings(query="hata")
    assert "Result window is too large" in str(e.value)


@pytest.mark.anyio
async def test_arama_gecersiz_tarih_sessizce_yok_sayilmiyor(srv):
    """SEC gecersiz tarihi yok sayip FARKLI bir kume donuyor; model bunu
    istedigi filtre sanir."""
    with pytest.raises(ValueError) as e:
        await srv.search_filings(query="tariff", start_date="2024")
    assert "YYYY-MM-DD" in str(e.value)
    with pytest.raises(ValueError) as e:
        await srv.search_filings(query="tariff", end_date="2024-02-31")
    assert "calendar date" in str(e.value)


@pytest.mark.anyio
async def test_arama_ters_tarih_araligi_yakalaniyor(srv):
    with pytest.raises(ValueError) as e:
        await srv.search_filings(query="tariff", start_date="2025-01-01",
                                 end_date="2024-01-01")
    assert "Swap" in str(e.value)


@pytest.mark.anyio
async def test_arama_bos_sorgu_baska_araca_yonlendiriyor(srv):
    with pytest.raises(ValueError) as e:
        await srv.search_filings(query="   ")
    assert "sec_edgar_list_filings" in str(e.value)


@pytest.mark.anyio
async def test_arama_offset_siniri_semada_ilan_ediliyor(srv):
    """Olculdu: SEC `from + size > 10000` istegini reddediyor. Sinir sema
    disinda kalsaydi model onu ancak hatayla ogrenirdi."""
    from edgar_mcp.server import mcp
    arac = [t for t in await mcp.list_tools() if t.name == "sec_edgar_search_filings"][0]
    ozellik = arac.input_schema["properties"]["offset"]
    assert ozellik["maximum"] == 9900
    assert arac.input_schema["properties"]["limit"]["maximum"] == 100


@pytest.mark.anyio
async def test_arama_limit_sayfayi_kirpiyor(srv):
    r = await srv.search_filings(query='"tariff"', limit=1)
    assert r.returned == 1 and len(r.results) == 1
    assert r.has_more is True


# ------------------------------------------------------------------ etiketler
@pytest.mark.anyio
async def test_eksen_ve_uye_adlari_insan_okunur_geliyor(srv):
    b = await srv.list_fact_dimensions(ticker="AAPL", form_type="8-K")
    eksen = [a for a in b.axes if a.axis == "us-gaap:StatementBusinessSegmentsAxis"][0]
    # Ayni eleman iki rolde etiketli: STANDART rol kazanmali, kisa rol degil.
    assert eksen.axis_label == "Segment Reporting Information [Axis]"
    assert eksen.member_labels["tsla:AutomotiveSegmentMember"] == \
        "Automotive Segment [Member]"
    assert b.label_source == "aapl-8k_lab.xml"
    # Etiketi COZULMEYEN uye haritada hic gorunmemeli: bos dizgeyle doldurmak
    # "adi yok" ile "bulamadim"i ayni gosterirdi.
    cografya = [a for a in b.axes if a.axis == "srt:StatementGeographicalAxis"][0]
    assert cografya.member_labels == {}, cografya.member_labels
    assert all(v for v in eksen.member_labels.values())


@pytest.mark.anyio
async def test_etiketi_olmayan_ad_uydurulmuyor(srv):
    """Linkbase'de yay kurulmamis eleman ETIKETSIZDIR. `loc_5`/`lab_5`
    isimlendirmesine bakan bir kod ona 'Plant [Axis]' derdi."""
    b = await srv.list_fact_dimensions(ticker="AAPL", form_type="8-K")
    eksen = [a for a in b.axes if a.axis == "tsla:PlantAxis"][0]
    assert eksen.axis_label is None
    assert eksen.axis == "tsla:PlantAxis", "ad her halukarda QName olarak duruyor"


@pytest.mark.anyio
async def test_fact_etiketleri_dokumantasyon_metnini_kullanmiyor(srv):
    """`documentation` rolu etiket degil TANIM metnidir; onu ad diye gostermek
    her satiri paragrafa cevirirdi."""
    b = await srv.get_dimensional_facts(ticker="AAPL", concept="revenue",
                                        form_type="8-K",
                                        axis="us-gaap:StatementBusinessSegmentsAxis")
    assert b.facts[0].tag_label == "Revenues"
    boyut = b.facts[0].dimensions[0]
    assert boyut.axis_label == "Segment Reporting Information [Axis]"
    assert boyut.member_label and "Segment [Member]" in boyut.member_label
    assert b.label_source == "aapl-8k_lab.xml"


@pytest.mark.anyio
async def test_etiket_istenmediginde_indirilmiyor(srv):
    """Etiket linkbase'i olculen dosyalamada 1,21 MB. Istenmedigi halde
    indirmek her cagriya bedava olmayan bir maliyet eklerdi."""
    ISTEK_KAYDI.clear()
    b = await srv.list_fact_dimensions(ticker="AAPL", form_type="8-K",
                                       include_labels=False)
    assert not any("_lab.xml" in u for u in ISTEK_KAYDI)
    assert b.label_source is None
    assert b.axes and all(a.axis_label is None for a in b.axes)


@pytest.mark.anyio
async def test_etiket_dosyasi_yokken_calismaya_devam_ediyor(srv):
    """Linkbase yoksa cevap yine gelmeli: etiket bir sus payi, veri degil."""
    b = await srv.list_fact_dimensions(ticker="AAPL",
                                       accession_number="0000320193-25-000058")
    assert b.label_source is None
    assert b.axes, "etiket dosyasi yok diye boyutlar kaybolmamali"


@pytest.mark.anyio
async def test_etiket_dosyasi_ayni_cagrida_iki_kez_indirilmiyor(srv):
    ISTEK_KAYDI.clear()
    await srv.list_fact_dimensions(ticker="AAPL", form_type="8-K")
    await srv.get_dimensional_facts(ticker="AAPL", concept="revenue", form_type="8-K")
    assert sum("_lab.xml" in u for u in ISTEK_KAYDI) == 1


def test_etiket_ayristirici_onek_uyusmazliginda_yerel_ada_dusuyor():
    """Linkbase'deki onek, instance'daki onekle ayni olmak ZORUNDA degil.
    Yerel ad tek anlamliysa kullanilir; degilse hicbir sey uydurulmaz."""
    from edgar_mcp.xbrl import etiketleri_ayristir
    e = etiketleri_ayristir(LAB_XML)
    assert e.bul("us-gaap:Revenues") == "Revenues"
    assert e.bul("baskaonek:Revenues") == "Revenues", "yerel ad yedegi calismali"
    assert e.bul("us-gaap:GrossProfit") is None


def test_etiket_ayristirici_cok_anlamli_yerel_adi_tahmin_etmiyor():
    ikili = LAB_XML.replace(
        '<link:loc xlink:type="locator" xlink:label="loc_4"\n'
        '      xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_Revenues"/>',
        '<link:loc xlink:type="locator" xlink:label="loc_4"\n'
        '      xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_Revenues"/>\n'
        '    <link:loc xlink:type="locator" xlink:label="loc_6"\n'
        '      xlink:href="tsla-20251231.xsd#tsla_Revenues"/>\n'
        '    <link:label xlink:type="resource" xlink:label="lab_6" xml:lang="en-US"\n'
        '      xlink:role="http://www.xbrl.org/2003/role/label">Company Revenues</link:label>\n'
        '    <link:labelArc xlink:type="arc" xlink:from="loc_6" xlink:to="lab_6"\n'
        '      xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label" order="1"/>')
    from edgar_mcp.xbrl import etiketleri_ayristir
    e = etiketleri_ayristir(ikili)
    assert e.bul("us-gaap:Revenues") == "Revenues", "tam eslesme hala calismali"
    assert e.bul("tsla:Revenues") == "Company Revenues"
    assert e.bul("baskaonek:Revenues") is None, "iki aday varken tahmin edilmemeli"


def test_etiket_ayristirici_bozuk_xml_de_cokmuyor():
    from edgar_mcp.xbrl import etiketleri_ayristir
    e = etiketleri_ayristir("<link:linkbase><link:loc kapanmamis")
    assert e.qname == {} and e.bul("us-gaap:Revenues") is None


# ------------------------------------------------------------------- tablolar
async def _ek_tablolu(srv, **kw):
    return await srv.read_filing_text(
        ticker="AAPL", accession_number="0000320193-25-000041",
        document="exhibit991.htm", **kw)


@pytest.mark.anyio
async def test_tablolar_istenmedikce_donmuyor(srv):
    """Varsayilan kapali: yapiya ihtiyaci olmayan her cagriya yuzlerce hucre
    eklemek, sayfalama butcesini bosa harcar."""
    b = await _ek_tablolu(srv, max_characters=40000)
    assert b.tables == [] and b.total_tables == 0


@pytest.mark.anyio
async def test_tablo_satir_ve_hucre_olarak_donuyor(srv):
    """Asil kazanc: duz metinde sayilar ` | ` ile birbirine yapisik geliyor ve
    modelin sutunlari goz kararı hizalamasi gerekiyordu."""
    b = await _ek_tablolu(srv, tables=True, max_characters=40000)
    veri = [t for t in b.tables if t.column_count == 3]
    assert veri, [t.rows for t in b.tables]
    t = veri[0]
    assert t.rows[0] == ["Period", "Production", "Deliveries"]
    assert t.rows[1] == ["Q2 2026", "451,758", "480,126"]
    # Tamami bos satir atiliyor (yerlesim artigi), bos HUCRE atilmiyor.
    assert ["", "", ""] not in t.rows
    assert t.row_count == 4 and t.total_rows == 4 and t.rows_truncated is False


@pytest.mark.anyio
async def test_yerlesim_tablosu_sessizce_dusurulmuyor(srv):
    """EDGAR sayfa yerlesimi icin de tablo kullaniyor. Elemek dogru, ama
    "tablo yok" ile "tablolarin hepsi yerlesimdi" ayni sey degil."""
    b = await _ek_tablolu(srv, tables=True, max_characters=40000)
    assert b.layout_tables_skipped >= 1
    assert all(t.row_count >= 2 for t in b.tables)


@pytest.mark.anyio
async def test_gizli_bloktaki_tablo_yapiya_da_girmiyor(srv):
    """Gizli blok filtresini metinde uygulayip yapida uygulamamak, filtreyi bir
    kapidan kovup otekinden almak olurdu."""
    b = await _ek_tablolu(srv, tables=True, max_characters=40000)
    assert GIZLI_TABLO_ISARET not in b.text
    hucreler = [h for t in b.tables for satir in t.rows for h in satir]
    assert GIZLI_TABLO_ISARET not in hucreler
    # Gizli tablo hic KURULMAMALI. Kurulup sonra "yerlesim" diye elenirse
    # sayac sisiyor ve model olmayan bir tablodan haberdar ediliyor: belgede
    # bir yerlesim tablosu var (colspan'li ozet seridi), gizli olan sayilmaz.
    assert b.layout_tables_skipped == 1, b.layout_tables_skipped


@pytest.mark.anyio
async def test_tablo_konumu_dondurulen_metne_denk_geliyor(srv):
    """`text_offset` `offset` ile AYNI koordinatta olmali; degilse model
    tabloyu yanlis pasaja baglar."""
    b = await _ek_tablolu(srv, tables=True, max_characters=40000)
    t = [x for x in b.tables if x.column_count == 3][0]
    yerel = t.text_offset - b.offset
    assert b.text[yerel:yerel + 40].startswith("| Period")


@pytest.mark.anyio
async def test_tablolar_sayfalama_penceresiyle_sinirli(srv):
    """Pencerenin disinda BASLAYAN tablo dondurulmuyor, ama toplam sayi tum
    bolumu bildiriyor - "bu belgede tablo yok" yanilgisi olusmasin."""
    tam = await _ek_tablolu(srv, tables=True, max_characters=40000)
    assert tam.tables, "kontrol: tam okumada tablo var"
    konum = tam.tables[0].text_offset
    # Tablonun BASLADIGI yerden SONRA acilan bir pencere: tablo donmemeli, ama
    # toplam sayi degismemeli - yoksa model "bu belgede tablo yok" sanir.
    sonra = await _ek_tablolu(srv, tables=True, offset=konum + 10, max_characters=500)
    assert sonra.tables == [], sonra.tables
    assert sonra.total_tables == tam.total_tables == 1


@pytest.mark.anyio
async def test_bolum_secilince_tablo_konumu_bolume_gore(srv):
    """Bolum kesildiginde metin kayiyor; tablo konumu kaymazsa dogru tablo
    yanlis yerde gorunur."""
    b = await srv.read_filing_text(ticker="AAPL", section="Item 7",
                                   accession_number="0000320193-25-000058",
                                   tables=True, max_characters=40000)
    for t in b.tables:
        yerel = t.text_offset - b.offset
        assert 0 <= yerel < len(b.text)
        assert b.text[yerel:yerel + 2] == "| ", b.text[yerel:yerel + 20]


def test_bosluk_sadelestirme_eski_regex_zinciriyle_ayni():
    """Sadelestirme regex zincirinden tek gecise tasindi (tablo konumlari
    onunla birlikte tasinsin diye). Davranis BIREBIR ayni kalmali; bu test iki
    uygulamayi ayni girdilerle karsilastiriyor."""
    import re as _re

    from edgar_mcp.belge import _topla

    def eski(metin: str) -> str:
        metin = metin.replace("\xa0", " ").replace("​", "")
        metin = _re.sub(r"[ \t]+", " ", metin)
        metin = _re.sub(r" *\n *", "\n", metin)
        metin = _re.sub(r"\n{3,}", "\n\n", metin)
        return metin.strip()

    ornekler = [
        "  a \n\n b ", "a\t\t b", "a\n\n\n\n\nb", "a\xa0​b", "\n\n", "",
        "a \n \n \n b", "a\r\n\r\nb", " | a | b \n | c ", "tek",
        BELGE_HTML, BELGE_TABLO, BELGE_8K_EK, BELGE_UZUN_TOC,
    ]
    for o in ornekler:
        yeni, _ = _topla(o, [])
        assert yeni == eski(o), repr(o[:80])


def test_uzun_tablo_kirpiliyor_ve_bunu_soyluyor():
    from edgar_mcp.belge import SATIR_SINIRI, cevir

    satirlar = "".join(f"<tr><td>r{i}</td><td>{i}</td></tr>"
                       for i in range(SATIR_SINIRI + 25))
    c = cevir(f"<html><body><table>{satirlar}</table></body></html>")
    t = c.tablolar[0]
    assert len(t.satirlar) == SATIR_SINIRI
    assert t.toplam_satir == SATIR_SINIRI + 25 and t.kirpildi is True


def test_uzun_hucre_kirpiliyor_ve_bunu_soyluyor():
    from edgar_mcp.belge import HUCRE_SINIRI, cevir

    uzun = "söz " * 200
    c = cevir(f"<html><body><table><tr><td>{uzun}</td><td>b</td></tr>"
              "<tr><td>c</td><td>d</td></tr></table></body></html>")
    t = c.tablolar[0]
    assert len(t.satirlar[0][0]) == HUCRE_SINIRI and t.hucre_kirpildi is True


def test_ic_ice_tablolar_ayri_ayri_donuyor():
    """EDGAR yerlesim icin tablo ICINE tablo koyuyor. Ic teki tablonun
    hucreleri disaridakine yazilirsa iki tablo tek bir karisim olur."""
    from edgar_mcp.belge import cevir

    c = cevir("<html><body><table>"
              "<tr><td><table><tr><td>ic1</td><td>ic2</td></tr>"
              "<tr><td>ic3</td><td>ic4</td></tr></table></td><td>dis2</td></tr>"
              "<tr><td>dis3</td><td>dis4</td></tr>"
              "</table></body></html>")
    kumeler = [[h for satir in t.satirlar for h in satir] for t in c.tablolar]
    assert ["ic1", "ic2", "ic3", "ic4"] in kumeler, kumeler
    assert any("dis3" in k and "ic3" not in k for k in kumeler), kumeler
    # Ic tablonun metni dis hucreye KOPYALANMIYOR: ayni sayilari iki tabloda
    # birden dondurmek, toplam alan bir modele veriyi iki kez saydirir.
    dis = [k for k in kumeler if "dis3" in k][0]
    assert dis[0] == "", dis


def test_kapanmamis_tablo_da_donuyor():
    """EDGAR HTML'i kapanis etiketlerini atlayabiliyor ve belgenin son tablosu
    tam da mali tablolar olabiliyor."""
    from edgar_mcp.belge import cevir

    # Belge tablonun ORTASINDA bitiyor: hicbir kapanis etiketi yok, dolayisiyla
    # yigini bosaltan tek yol `close()`. `</body>` yazsaydik `_kapat` tabloyu
    # zaten bitirirdi ve bu yol hic sinanmazdi.
    c = cevir("<html><body><table><tr><td>a<td>b<tr><td>c<td>d")
    assert c.tablolar and c.tablolar[0].satirlar == [["a", "b"], ["c", "d"]]


# --------------------------------------------------- tek tarafli tarih araligi
@pytest.mark.anyio
async def test_tek_tarafli_tarih_araligi_tamamlaniyor(srv):
    """Olculdu (16 Agu 2026, canli): SEC tek tarafli araligi SESSIZCE
    dusuruyor. `start_date=2026-01-01` tek basina verildiginde 162 sonuc
    donuyordu, en eskisi 2009 tarihli - model filtrelenmis sandigi bir listeyi
    okuyor. Eksik uc dolduruluyor ve gonderilen aralik yanitta yaziyor."""
    from datetime import date

    ISTEK_KAYDI.clear()
    r = await srv.search_filings(query="tariff", start_date="2026-01-01")
    u = [x for x in ISTEK_KAYDI if "efts" in x][0]
    assert "startdt=2026-01-01" in u and f"enddt={date.today().isoformat()}" in u
    assert r.date_range_applied == f"2026-01-01..{date.today().isoformat()}"

    ISTEK_KAYDI.clear()
    r2 = await srv.search_filings(query="tariff", end_date="2012-12-31")
    u2 = [x for x in ISTEK_KAYDI if "efts" in x][0]
    assert "startdt=1994-01-01" in u2 and "enddt=2012-12-31" in u2
    assert r2.date_range_applied == "1994-01-01..2012-12-31"
    # 1994 baslangici 2001 esiginin gerisinde: kapsam notu da gelmeli.
    assert r2.coverage_note and "1996" in r2.coverage_note


@pytest.mark.anyio
async def test_tarih_verilmediginde_aralik_uydurulmuyor(srv):
    ISTEK_KAYDI.clear()
    r = await srv.search_filings(query="tariff")
    u = [x for x in ISTEK_KAYDI if "efts" in x][0]
    assert "dateRange" not in u and "startdt" not in u
    assert r.date_range_applied is None


# ------------------------------------------------------------ CIK ile adresleme
@pytest.mark.anyio
async def test_cik_ile_adresleme_calisiyor(srv):
    """Olculdu: tam metin aramasi ticker'i OLMAYAN dosyalayanlar donduruyor
    (fonlar, yabanci ihraccilar). Ticker zorunlu kalsaydi arac kendi buldugu
    belgeyi acamazdi."""
    for girdi in ("0000320193", "320193", "CIK0000320193"):
        p = await srv.get_company_profile(ticker=girdi)
        assert p.cik == "0000320193" and p.name == "Apple Inc."
        # Sembol UYDURULMUYOR: CIK ile soruldu, SEC'in dosyasindan cozuldu.
        assert p.ticker == "AAPL", girdi


@pytest.mark.anyio
async def test_ticker_girdisi_oldugu_gibi_yansiyor(srv):
    """Kullanici GOOGL yazdiysa yanitta GOOGL gorunmeli; ayni CIK'e bagli
    baska bir sinif (GOOG) donmemeli."""
    p = await srv.get_company_profile(ticker="aapl")
    assert p.ticker == "AAPL"
    s = await srv.list_recent_filings(ticker="aapl", limit=1)
    assert s.ticker == "AAPL"


@pytest.mark.anyio
async def test_cik_ile_dosyalama_listesi_ve_metin(srv):
    s = await srv.list_recent_filings(ticker="320193", form_type="10-K", limit=2)
    assert s.total_matching == 2
    t = await srv.read_filing_text(ticker="CIK0000320193", max_characters=500)
    assert t.accession_number == "0000320193-25-000073"


@pytest.mark.anyio
async def test_bilinmeyen_cik_eyleme_donusturulebilir_hata(srv):
    """CIK ile adresleme acilinca en olasi kullanici hatasi var olmayan bir
    numara; cig HTTPStatusError modele ne yapacagini soylemez."""
    with pytest.raises(ValueError) as e:
        await srv.get_company_profile(ticker="9999999999")
    mesaj = str(e.value)
    assert "9999999999" in mesaj and "ticker symbol works here too" in mesaj


@pytest.mark.anyio
async def test_aramada_cik_filtresi_de_kabul_ediliyor(srv):
    ISTEK_KAYDI.clear()
    await srv.search_filings(query="tariff", ticker="1318605")
    u = [x for x in ISTEK_KAYDI if "efts" in x][0]
    assert "ciks=0001318605" in u


# ------------------------------------------------- Form 4 (icerideki islemler)
@pytest.mark.anyio
async def test_form4_islemleri_kod_anlamiyla_donuyor(srv):
    """En sik yapilan analiz hatasi: hisse ODULUNU (A) ya da vergi icin
    KESILEN hisseyi (F) piyasadan alim/satim sanmak. Kod tek basina bunu
    anlatmiyor; anlami yanitin icinde gitmeli (§18)."""
    r = await srv.get_insider_transactions(ticker="AAPL")
    assert r.issuer_name == "Apple Inc." and r.ticker == "AAPL"
    kodlar = {t.code for t in r.transactions}
    assert kodlar == {"A", "F", "S"}, kodlar
    odul = [t for t in r.transactions if t.code == "A"][0]
    assert odul.code_meaning and "no cash" in odul.code_meaning
    assert odul.price_per_share == 0 and odul.shares == 511000
    assert odul.officer_title == "Chief Executive Officer"
    assert odul.is_director is True and odul.is_officer is True
    kesinti = [t for t in r.transactions if t.code == "F"][0]
    assert kesinti.code_meaning and "not a market sale" in kesinti.code_meaning


@pytest.mark.anyio
async def test_form4_turev_satirlari_varsayilan_olarak_disarida(srv):
    """Turev satiri (RSU) ile hisse satiri AYNI olayin iki asamasi: RSU
    vesting'i hem `M` turev satiri hem `A` hisse satiri olarak gorunur.
    Ikisini birden saymak ayni hisseyi iki kez sayar."""
    varsayilan = await srv.get_insider_transactions(ticker="AAPL")
    assert all(t.is_derivative is False for t in varsayilan.transactions)
    genis = await srv.get_insider_transactions(ticker="AAPL", include_derivative=True)
    turevler = [t for t in genis.transactions if t.is_derivative]
    assert len(turevler) == 1 and turevler[0].security == "Restricted Stock Unit"


@pytest.mark.anyio
async def test_form4_pozisyon_bildirimi_islem_sanilmiyor(srv):
    """`nonDerivativeHolding` alinip satilan bir sey DEGIL, yalnizca mevcut
    pozisyon. Islem listesine karistirmak "bugun 57.378 hisse aldi" dedirtir."""
    varsayilan = await srv.get_insider_transactions(ticker="AAPL")
    assert all(t.is_holding is False for t in varsayilan.transactions)
    genis = await srv.get_insider_transactions(ticker="AAPL", include_holdings=True)
    tutma = [t for t in genis.transactions if t.is_holding]
    assert len(tutma) == 1
    assert tutma[0].shares is None and tutma[0].shares_owned_after == 57378
    assert tutma[0].nature_of_ownership == "By 401(k) plan"
    # Pozisyon satiri kod toplamlarina GIRMEMELI: alinip satilan bir sey yok.
    assert sum(k.transactions for k in genis.code_totals) == 3


@pytest.mark.anyio
async def test_form4_kod_toplamlari_netlestirilmiyor(srv):
    """Odul + vergi kesintisi + satis TEK bir "net alim" sayisina indirgenmiyor:
    uc farkli olay, toplami hicbir seyi olcmez (KK-31 mutabakat ilkesi)."""
    r = await srv.get_insider_transactions(ticker="AAPL")
    tablo = {k.code: k for k in r.code_totals}
    assert tablo["A"].shares == 511000 and tablo["A"].transactions == 1
    assert tablo["F"].shares == 240000
    assert tablo["S"].shares == 100000
    assert all(k.meaning for k in r.code_totals), "kod anlamlari toplamlarda da olmali"


@pytest.mark.anyio
async def test_form4_stil_onekli_yol_ham_xml_e_cevriliyor(srv):
    """Olculdu: `primaryDocument` stil sayfasi yolunu gosteriyor
    (`xslF345X03/wf-form4_123.xml`); makine okunur XML oneksiz halidir."""
    ISTEK_KAYDI.clear()
    await srv.get_insider_transactions(ticker="AAPL")
    istekler = [u for u in ISTEK_KAYDI if "form4" in u]
    assert istekler and all("xsl" not in u for u in istekler), istekler


@pytest.mark.anyio
async def test_form4_dosyalama_sayisi_bildiriliyor(srv):
    """Kac dosyalama okundugu ve kac tane oldugu ayri ayri: model "iceriden
    islem yok" ile "bakilan dosyalamalarda yok"u ayirt edebilmeli."""
    r = await srv.get_insider_transactions(ticker="AAPL", filings=1)
    assert r.filings_read == 1 and r.filings_available == 2
    assert r.has_more is True
    assert "does not show trading by anyone else" in r.coverage_note


# ------------------------------------------------------ 13F (kurumsal pozisyon)
@pytest.mark.anyio
async def test_13f_ayni_ihraccinin_satirlari_birlestiriliyor(srv):
    """Bir yonetici her alt yonetici icin ayri satir yaziyor. Bunlar mukerrer
    DEGIL, ayni pozisyonun parcalari - toplanmali ve kac satirdan geldigi
    soylenmeli."""
    h = await srv.get_institutional_holdings(ticker="AAPL")
    apple = [p for p in h.positions if p.issuer == "APPLE INC"][0]
    assert apple.rows_combined == 2
    assert apple.shares_or_principal == 669429166 + 7708000
    assert apple.value_usd == 86841985318 + 1000000000
    assert h.rows_in_table == 3 and h.unique_positions == 2


@pytest.mark.anyio
async def test_13f_2023_oncesi_deger_bin_dolar_olarak_isaretleniyor(srv, monkeypatch):
    """OLCULDU (Berkshire, ayni 669.429.166 Apple hissesi): Kas 2022
    dosyalamasinda deger 92.515.111, Sub 2023 dosyalamasinda 86.841.985.318 -
    BIN KAT. SEC 2023'te birimi bin dolardan tam dolara cevirdi. Normalize
    etmeyen bir arac, iki ceyregi karsilastiran modele "pozisyon bin katina
    cikti" dedirtir."""
    yeni = await srv.get_institutional_holdings(ticker="AAPL")
    assert yeni.value_basis == "whole_dollars"

    import copy
    eski_sub = copy.deepcopy(SUBS)
    i = eski_sub["filings"]["recent"]["form"].index("13F-HR")
    eski_sub["filings"]["recent"]["filingDate"][i] = "2022-11-14"

    async def sahte(cik):
        return eski_sub

    monkeypatch.setattr(srv._client, "submissions", sahte)
    srv._client._index_cache.clear()
    eski = await srv.get_institutional_holdings(ticker="AAPL")
    assert eski.value_basis == "thousands"
    assert eski.total_value_usd == yeni.total_value_usd * 1000


@pytest.mark.anyio
async def test_13f_kapak_sayfasi_ve_tablo_ayri_ayri_bildiriliyor(srv):
    """Kapak sayfasindaki toplam ile tablonun toplami tutmayabilir. Ikisini de
    dondurmek, farki gorunur kilar (KK-31: sessizce birini secme)."""
    h = await srv.get_institutional_holdings(ticker="AAPL")
    assert h.reported_entry_count == 3
    assert h.reported_value_total == 88419197133
    assert h.total_value_usd == 86841985318 + 1000000000 + 577211815
    assert h.manager_name == "Apple Asset Management"
    assert h.period_of_report == "03-31-2026"


@pytest.mark.anyio
async def test_13f_bilgi_tablosu_dizinden_bulunuyor(srv):
    """Bilgi tablosunun adi rastgele ("56757.xml", "18337.xml" olculdu);
    tahmin edilemez, dizinden bulunmasi gerekiyor."""
    ISTEK_KAYDI.clear()
    await srv.get_institutional_holdings(ticker="AAPL")
    assert any(u.endswith("/77219.xml") for u in ISTEK_KAYDI), ISTEK_KAYDI
    assert any(u.endswith("/index.json") for u in ISTEK_KAYDI)


@pytest.mark.anyio
async def test_13f_kapsam_notu_sinirlari_soyluyor(srv):
    h = await srv.get_institutional_holdings(ticker="AAPL")
    for ifade in ("short positions", "45 days"):
        assert ifade in h.coverage_note


@pytest.mark.anyio
async def test_13f_ihracci_araması_ve_siralama(srv):
    h = await srv.get_institutional_holdings(ticker="AAPL", search="ally")
    assert h.total_matching == 1 and h.positions[0].issuer == "ALLY FINL INC"
    tum = await srv.get_institutional_holdings(ticker="AAPL")
    degerler = [p.value_usd for p in tum.positions]
    assert degerler == sorted(degerler, reverse=True), "en buyuk pozisyon basta olmali"


# ------------------------------------------------- kesim tarihi (point-in-time)
# Zaaf 3 (17 Agu 2026): degerlendirme seti 2025'te yazildi, kosu 2026'da
# yapildi ve bes soruda "son uc yil" gibi ifadeler baska dosyalamalara denk
# geldi. Bunun genel adi look-ahead: bir tarihte BILINMEYEN veriyi o tarihte
# biliniyormus gibi kullanmak. Kesim tarihi bu sinifi kapatiyor.


@pytest.mark.anyio
async def test_as_of_o_tarihte_bilinen_degeri_donduruyor(srv):
    """Asil sinav bu: FY2023 geliri once 383.285 diye sunuldu (2023-11-03),
    2024 10-K'sinda 383.290 olarak revize edildi. 2024 basinda duran birinin
    gordugu sayi ILKIDIR. Donem sonuna bakan bir filtre revizyonu iceri alir,
    cunku donem ikisinde de ayni - ayirici olan SUNULMA tarihidir."""
    kesimli = await srv.get_concept_series(ticker="AAPL", concept="revenue",
                                           as_of="2024-01-01")
    kesimsiz = await srv.get_concept_series(ticker="AAPL", concept="revenue")

    def deger(seri, bitis):
        return next(p.value for p in seri.points if p.period_end == bitis)

    assert deger(kesimli, "2023-09-30") == 383_285_000_000
    assert deger(kesimsiz, "2023-09-30") == 383_290_000_000, "revizyon kayboldu"
    assert kesimli.as_of_applied == "2024-01-01"
    assert kesimsiz.as_of_applied is None
    assert all(p.filed <= "2024-01-01" for p in kesimli.points)


@pytest.mark.anyio
async def test_as_of_dosyalama_listesini_o_tarihe_gore_kesiyor(srv):
    s = await srv.list_recent_filings(ticker="AAPL", limit=50,
                                      as_of="2025-06-30")
    assert s.filings, "kesim her seyi sildi"
    assert all(f.filing_date <= "2025-06-30" for f in s.filings)
    # §16/KK-17: toplam FILTREDEN SONRAKI sayidir; filtresiz toplami bildirmek
    # modele "gormedigin dosyalamalar var" der ve kesimin anlamini bozar.
    assert s.total_matching == len(s.filings)
    assert s.as_of_applied == "2025-06-30"

    tumu = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert tumu.total_matching > s.total_matching, "kesim hicbir sey elemedi"


@pytest.mark.anyio
async def test_as_of_acikca_istenen_gec_dosyalamayi_sessizce_vermiyor(srv):
    """Erisim numarasi ACIKCA verildiginde bile kesim geciyor. Tek satirlik bir
    istisna, cagiranin elinde yanlis bir guvence birakirdi."""
    with pytest.raises(ValueError) as e:
        await srv.read_filing_text(ticker="AAPL",
                                   accession_number="0000320193-25-000073",
                                   as_of="2025-06-30")
    mesaj = str(e.value)
    assert "2025-10-31" in mesaj and "2025-06-30" in mesaj, mesaj
    assert "sec_edgar_list_filings" in mesaj, "ne yapacagini soylemiyor (§18)"


@pytest.mark.anyio
async def test_as_of_ortam_degiskeni_cagri_vermeden_de_uygulaniyor(srv, monkeypatch):
    """`SEC_AS_OF` oturum capinda bir soz: her arac, parametre verilmese de
    ona uyar. Degerlendirme kosusu bunun uzerine kuruluyor."""
    monkeypatch.setenv("SEC_AS_OF", "2025-06-30")
    s = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert s.as_of_applied == "2025-06-30"
    assert all(f.filing_date <= "2025-06-30" for f in s.filings)


@pytest.mark.anyio
async def test_as_of_cagri_ile_ortamdan_erken_olani_kazaniyor(srv, monkeypatch):
    """Ikisi carpistiginda gec olani secmek, oturum capinda verilen sozu cagri
    basina bozmak olurdu."""
    monkeypatch.setenv("SEC_AS_OF", "2025-06-30")
    gec = await srv.list_recent_filings(ticker="AAPL", limit=50,
                                        as_of="2026-01-01")
    assert gec.as_of_applied == "2025-06-30", "cagri, ortamin sozunu asti"
    erken = await srv.list_recent_filings(ticker="AAPL", limit=50,
                                          as_of="2025-01-01")
    assert erken.as_of_applied == "2025-01-01", "daha dar kesim uygulanmadi"


@pytest.mark.anyio
async def test_as_of_uygulayamayan_arac_sessizce_gecmiyor(srv, monkeypatch):
    """`compare_companies` SEC'in cerceve ucunu kullaniyor ve o uc satir basina
    SUNULMA TARIHI vermiyor. Tutamayacagi bir sozu tutmus gibi yapmak yerine
    cagriyi reddediyor ve tutan alternatifi soyluyor."""
    monkeypatch.setenv("SEC_AS_OF", "2025-06-30")
    with pytest.raises(ValueError) as e:
        await srv.compare_companies(concept="revenue", period="2025Q1")
    mesaj = str(e.value)
    assert "2025-06-30" in mesaj
    assert "sec_edgar_get_concept_series" in mesaj, "alternatif soylenmiyor (§18)"


@pytest.mark.anyio
async def test_as_of_sahiplik_araclarini_da_kesiyor(srv):
    """Form 4 akisinda iki dosyalama var (2025-02-03 ve 2026-02-20); 13F ise
    yalnizca 2026-05-15'te. Kesim ikisini de gormeli."""
    r = await srv.get_insider_transactions(ticker="AAPL", as_of="2025-12-31")
    assert r.filings_available == 1, "kesimden sonraki Form 4 sayima girdi"
    assert r.as_of_applied == "2025-12-31"

    with pytest.raises(ValueError) as e:
        await srv.get_institutional_holdings(ticker="AAPL", as_of="2025-12-31")
    assert "2025-12-31" in str(e.value)


@pytest.mark.anyio
async def test_as_of_revizyon_gecmisini_de_kesiyor(srv):
    """Revizyon aracinin cevabi kesimle DEGISMELI: 2024 basinda o revizyon
    henuz sunulmamisti, dolayisiyla gorunmemeli."""
    kesimli = await srv.get_fact_revisions(ticker="AAPL", concept="revenue",
                                           as_of="2024-01-01")
    kesimsiz = await srv.get_fact_revisions(ticker="AAPL", concept="revenue")
    assert kesimsiz.periods_revised >= 1, "fixture revizyon tasimiyor"
    assert kesimli.periods_revised == 0, "kesimden sonraki revizyon sizdi"
    assert kesimli.as_of_applied == "2024-01-01"


@pytest.mark.anyio
async def test_as_of_aramanin_ust_sinirini_da_kisiyor(srv, monkeypatch):
    """Tam metin aramasinin kendi tarih araligi var; kesim ayri bir parametre
    olarak degil, `end_date`in TAVANI olarak giriyor. Gonderilen aralik
    yanitta gorunuyor - sessiz bir daraltma olmuyor."""
    monkeypatch.setenv("SEC_AS_OF", "2025-06-30")
    r = await srv.search_filings(query="revenue", end_date="2026-01-01")
    assert r.date_range_applied is not None
    assert r.date_range_applied.endswith("2025-06-30"), r.date_range_applied


def test_as_of_bilinmeyen_tarih_iceri_alinmiyor():
    """Sunulma tarihi bos bir kayit, "su tarihte biliniyordu" sozunu
    dolduramaz. Iceri almak sozu sessizce bozardi."""
    from edgar_mcp.server import _kesimden_sonra
    assert _kesimden_sonra("", "2025-06-30") is True
    assert _kesimden_sonra(None, "2025-06-30") is True
    # Kesim yokken hicbir sey elenmez - bilinmeyen tarih dahil.
    assert _kesimden_sonra("", None) is False
    assert _kesimden_sonra("2025-06-30", "2025-06-30") is False, "kesim gunu dahil"
    assert _kesimden_sonra("2025-07-01", "2025-06-30") is True


@pytest.mark.anyio
async def test_as_of_bicimsiz_tarihi_reddediyor(srv):
    """SEC gecersiz tarihi sessizce yok sayiyor; burada da sessiz gecerse
    model filtreledigini sanir (P-29)."""
    with pytest.raises(ValueError) as e:
        await srv.list_recent_filings(ticker="AAPL", as_of="2025")
    assert "YYYY-MM-DD" in str(e.value)


# --------------------------------------- ayni gun biten, farkli uzunluktaki donemler
# 17 Agu 2026, CANLI kullanimda bulundu (test paketi bunu gormuyordu, cunku
# sahte veri ayni bitisli iki donem tasimiyordu - P-4). Bir 10-Q hem ceyregi
# hem yil basindan beri toplami raporlar; ikisi ayni gun biter, ikisi de
# dogrudur, ve ikisi de AYNI dosyalamadan gelir.


@pytest.mark.anyio
async def test_ayni_gun_biten_farkli_uzunluktaki_donemler_birbirini_dusurmuyor(srv):
    """Olculdu (AAPL, `period="all"`): 2025-03-29 icin donen deger 219.659 -
    yani alti aylik toplam - ve o ceyregin kendi rakami 95.359 listede HIC
    yoktu. Bitis tarihi tek basina bir donemin kimligi degildir."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue",
                                     period="all", limit=60)
    ayni_bitis = [p for p in s.points if p.period_end == "2023-07-01"]
    assert len(ayni_bitis) == 2, f"donemlerden biri sessizce dustu: {ayni_bitis}"
    assert {p.value for p in ayni_bitis} == {81_797_000_000, 293_787_000_000}
    assert {p.days for p in ayni_bitis} == {90, 279}


@pytest.mark.anyio
async def test_farkli_uzunluktaki_donemler_revizyon_sanilmiyor(srv):
    """Bir revizyon ayni dosyalamanin icinde olamaz. Olculdu (AAPL,
    `period="all"`): 87 donemin 55'i "revize" gorunuyordu ve 2021-03-27'nin iki
    degeri de ayni erisim numarasindan (0000320193-21-000056) geliyordu -
    biri uc aylik, oteki alti aylik rakamdi."""
    r = await srv.get_fact_revisions(ticker="AAPL", concept="revenue",
                                     period="all", only_revised=True, limit=60)
    for rev in r.revisions:
        dosyalamalar = {e.accession_number for e in rev.entries}
        assert len(dosyalamalar) > 1, (
            f"{rev.period_end}: 'revizyon'un tum degerleri ayni dosyalamadan "
            f"geliyor ({dosyalamalar}) - bu bir revizyon degil, farkli "
            "uzunlukta iki donem")
    assert not [x for x in r.revisions if x.period_end == "2023-07-01"], (
        "ayni gun biten uc aylik ve dokuz aylik rakam revizyon sayildi")


def test_donem_kovasi_52_haftalik_takvimi_ayni_kovada_tutuyor():
    """Kova ham gun sayisi OLSAYDI, 52/53 haftalik takvimlerde ayni yillik
    donem 363 ve 365 gun surer ve listede iki kez cikardi. Ayirmasi gereken
    sey uzunluk SINIFI: uc aylik, alti aylik, yillik."""
    from edgar_mcp.server import _donem_kovasi
    assert _donem_kovasi(363) == _donem_kovasi(364) == _donem_kovasi(365) == 12
    assert _donem_kovasi(90) == 3 and _donem_kovasi(92) == 3
    assert _donem_kovasi(181) == 6 and _donem_kovasi(188) == 6
    assert _donem_kovasi(272) == 9 and _donem_kovasi(279) == 9
    assert _donem_kovasi(None) is None, "anlik olguda uzunluk yoktur"
    # Ayirt etmesi gereken siniflar gercekten ayri kovalarda
    assert len({_donem_kovasi(g) for g in (90, 181, 272, 364)}) == 4
