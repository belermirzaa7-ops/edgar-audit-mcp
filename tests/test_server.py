"""SEC'e canli cikmadan sunucuyu dogrular: HTTP katmani mock'lanir."""
import pathlib
import re
import sys

import httpx
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
           "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
           "2": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
           "3": {"cik_str": 104169, "ticker": "WMT", "title": "Walmart Inc."}}
SUBS = {"name": "Apple Inc.", "sicDescription": "Electronic Computers",
        "fiscalYearEnd": "0927",
        # Gercek SEC submissions verisi karisik form turleri icerir; sahte veri de icermeli.
        "filings": {"recent": {
            "accessionNumber": ["0000320193-25-000073","0000320193-25-000058",
                                "0000320193-25-000041","0000320193-24-000123",
                                "0000320193-25-000012"],
            "form":            ["10-K","10-Q","8-K","10-K","4"],
            "filingDate":      ["2025-10-31","2025-08-01","2025-06-10","2024-11-01","2025-02-03"],
            "reportDate":      ["2025-09-27","2025-06-28","2025-06-09","2024-09-28",""],
            "primaryDocument": ["aapl-20250927.htm","aapl-20250628.htm","aapl-8k.htm",
                                "aapl-20240928.htm","xslF345X05/form4.xml"],
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
BELGE_TABLO = """<html><body>
<table><tr><td>Item 7.</td><td>Management's Discussion and Analysis</td></tr></table>
<p>""" + TABLO_ISARET + """. """ + "Discussion filler. " * 60 + """</p>
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
BELGE_8K_EK = """<html><body>
<p>Tesla reported production of 451,758 vehicles and """ + EK_ISARET + """
in the second quarter of 2026, and deployed 13.5 GWh of energy storage.</p>
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


ISTEK_KAYDI: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    ISTEK_KAYDI.append(u)
    assert "@" in request.headers["User-Agent"], "SEC User-Agent e-posta icermeli"
    if "company_tickers" in u:
        return httpx.Response(200, json=TICKERS)
    if "/submissions/" in u:
        return httpx.Response(200, json=SUBS)
    if "companyfacts" in u:
        return httpx.Response(200, json=FACTS)
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
        if "000032019324000123" in u:
            return httpx.Response(200, json=DIZIN_ESKI_JSON)
        if "000032019325000012" in u:
            return httpx.Response(200, json=DIZIN_XBRLSIZ_JSON)
        return httpx.Response(200, json=DIZIN_JSON)
    if "/Archives/edgar/data/" in u:
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
    assert {x.form for x in s.filings} == {"10-K", "10-Q", "8-K", "4"}


@pytest.mark.anyio
async def test_filings_limit_uygulanir(srv):
    s = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert len(s.filings) == 2


@pytest.mark.anyio
async def test_filings_sayfalama_bilgisi_verir(srv):
    """Standart §16: limit tek basina yetmez. Model, listenin tamami mi yoksa
    kirpilmis mi oldugunu bilmeden 'sirketin N dosyalamasi var' diyebilir."""
    kirpik = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert kirpik.total_matching == 5
    assert kirpik.returned == 2
    assert kirpik.has_more is True

    tam = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert tam.total_matching == 5
    assert tam.returned == 5
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
        "sec_edgar_get_concept_series",
        "sec_edgar_get_fact_revisions",
        "sec_edgar_read_filing_text",
        "sec_edgar_list_available_concepts",
        "sec_edgar_compare_companies",
        "sec_edgar_list_fact_dimensions",
        "sec_edgar_get_dimensional_facts",
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
    gercek = b.metne_cevir

    def sayan(govde: str) -> str:
        sayac["n"] += 1
        return gercek(govde)

    monkeypatch.setattr(s, "metne_cevir", sayan)

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
    sunucu aciliyor, dokuz araci ilan ediyor ve ancak ilk cagride patliyordu -
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

    for cik in ("0000000001", "0000000002", "0000000003",
                "0000000004", "0000000005", "0000000006"):
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
