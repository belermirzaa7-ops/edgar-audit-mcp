"""Sahiplik dosyalamalari: Form 4 (icerideki islemleri) ve 13F (kurumsal pozisyonlar).

Neden ayri modul: bu iki belge XBRL DEGIL. Kendi semalari olan XML dosyalari ve
tuzaklari da kendilerine ozgu. `xbrl.py` finansal tablo dunyasini, bu modul
sahiplik dunyasini okuyor.

Bagimlilik eklenmedi (KK-3): stdlib `xml.etree.ElementTree` yetiyor.

Iki belge de 16 Agu 2026'da GERCEK dosyalamalar uzerinden olculdu; asagidaki
her yapi karari bir olcume dayaniyor, spesifikasyon okumasina degil.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# ---------------------------------------------------------------- Form 4
# Olculdu (NVDA, 0001310264-26-000008): kok `ownershipDocument`, AD ALANI YOK.
# Degerler `<value>` sarmalayicisi icinde duruyor:
#   <transactionShares><value>1262</value></transactionShares>
# Bu sarmalayici bazi alanlarda `<footnoteId>` de tasiyor, yani metni dogrudan
# elemandan okumak yanlis - once `value` cocugu aranmali.

# Islem kodlari. Bu harita KOZMETIK DEGIL: en sik yapilan analiz hatasi, hisse
# ODULUNU (A) ya da vergi icin KESILEN hisseyi (F) piyasadan alim/satim sanmak.
# "Iceriden alim" sinyali yalnizca P (ve bazi durumlarda M+S zinciri) icin
# anlamlidir. Model bu ayrimi ancak soylenirse yapabilir (§18).
ISLEM_KODLARI = {
    "P": "Open-market or private purchase - cash paid by the insider",
    "S": "Open-market or private sale",
    "A": "Grant, award or other acquisition from the issuer - normally no cash paid",
    "D": "Disposition back to the issuer",
    "F": "Shares withheld by the issuer to pay tax on a vesting award - not a market sale",
    "M": "Exercise or conversion of a derivative security held by the insider",
    "C": "Conversion of a derivative security",
    "E": "Expiration of a short derivative position",
    "H": "Expiration of a long derivative position",
    "G": "Bona fide gift",
    "L": "Small acquisition under Rule 16a-6",
    "W": "Acquisition or disposition by will or the laws of descent",
    "Z": "Deposit into or withdrawal from a voting trust",
    "J": "Other acquisition or disposition - the filing's footnotes explain it",
    "K": "Transaction in equity swap or similar instrument",
    "U": "Disposition due to a tender of shares in a change of control",
    "X": "Exercise of an in-the-money or at-the-money derivative security",
}


@dataclass
class Islem:
    """Form 4'teki tek bir satir."""
    owner_name: str
    owner_cik: str | None
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str | None
    security: str
    transaction_date: str | None
    code: str | None
    shares: float | None
    price_per_share: float | None
    acquired_or_disposed: str | None
    shares_owned_after: float | None
    direct_or_indirect: str | None
    nature_of_ownership: str | None
    is_derivative: bool
    is_holding: bool          # islem degil, yalnizca mevcut pozisyon bildirimi
    owner_count: int = 1      # ortak dosyalamada satirin kac sahibi var


@dataclass
class Form4:
    issuer_cik: str | None = None
    issuer_name: str | None = None
    issuer_ticker: str | None = None
    period: str | None = None
    amendment: bool = False
    islemler: list[Islem] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)


def _deger(e: ET.Element | None, ad: str) -> str | None:
    """`<x><value>3</value></x>` -> "3". Sarmalayici sart: ayni eleman
    `<footnoteId>` de tasiyabiliyor ve elemanin kendi metni bos kaliyor."""
    if e is None:
        return None
    c = e.find(ad)
    if c is None:
        return None
    v = c.find("value")
    metin = (v.text if v is not None else c.text) or ""
    metin = " ".join(metin.split())
    return metin or None


def _sayi(metin: str | None) -> float | None:
    if not metin:
        return None
    try:
        return float(metin.replace(",", ""))
    except ValueError:
        return None


def _bayrak(e: ET.Element | None, ad: str) -> bool:
    d = _deger(e, ad)
    return (d or "").strip() in ("1", "true", "TRUE", "True")


def form4_ayristir(govde: str) -> Form4:
    """Form 4 XML -> Form4. Bozuk belge eyleme donusturulebilir hata verir."""
    try:
        kok = ET.parse(io.StringIO(govde)).getroot()
    except ET.ParseError as e:
        bas = govde.lstrip()[:60].replace("\n", " ")
        raise ValueError(
            f"This Form 4 document could not be parsed as XML ({e}). The "
            f"response began with: {bas!r}. SEC also publishes a styled copy of "
            "each Form 4 under an xsl.../ path; the machine-readable XML is the "
            "same file name without that prefix."
        ) from e

    ihrac = kok.find("issuer")
    out = Form4(
        issuer_cik=_deger(ihrac, "issuerCik") if ihrac is not None else None,
        issuer_name=_deger(ihrac, "issuerName") if ihrac is not None else None,
        issuer_ticker=_deger(ihrac, "issuerTradingSymbol") if ihrac is not None else None,
        period=_deger(kok, "periodOfReport"),
    )

    # Bir Form 4 birden fazla `reportingOwner` tasiyabilir (ortak dosyalama:
    # bir fon grubu, bir aile, bir ortaklik). ISLEM TABLOLARI BELGEYE AITTIR,
    # sahibe DEGIL - kok altinda tek bir `nonDerivativeTable` vardir.
    #
    # 18 Agu 2026, denetimde bulundu: tablolar sahip dongusunun ICINDE
    # okunuyordu, dolayisiyla dort sahipli bir dosyalamada her islem DORT KEZ
    # donuyordu. Olculdu (CoreWeave, 0001104659-26-097435, dort sahipli
    # Magnetar dosyalamasi): belgede 24 satir / 307.131 hisse, arac 96 satir /
    # 1.228.524 hisse bildiriyordu - tam dort kati. Bu, "iceriden alim" diye
    # okunacak bir sayiyi dort katina cikaran sessiz bir hata.
    sahipler = kok.findall("reportingOwner")
    kimlikler = [s.find("reportingOwnerId") for s in sahipler]
    iliskiler = [s.find("reportingOwnerRelationship") for s in sahipler]
    adlar = [(_deger(k, "rptOwnerName") or "") for k in kimlikler]
    out.owners = [a for a in adlar if a]
    out.amendment = (_deger(kok, "documentType") or "").strip().upper().endswith("/A")

    # Ortak dosyalamada islem TEK bir kisiye atfedilemez; adlar birlestiriliyor
    # ve kac sahip oldugu satirda yaziyor. Ilk sahibi secip otekileri dusurmek,
    # kimin islem yaptigi hakkinda uydurma bir kesinlik verirdi.
    ad = "; ".join(out.owners)
    cik = _deger(kimlikler[0], "rptOwnerCik") if kimlikler else None
    yonetici = any(_bayrak(i, "isDirector") for i in iliskiler)
    gorevli = any(_bayrak(i, "isOfficer") for i in iliskiler)
    onda_bir = any(_bayrak(i, "isTenPercentOwner") for i in iliskiler)
    unvan = next((u for u in (_deger(i, "officerTitle") for i in iliskiler) if u), None)
    sahip_sayisi = max(1, len(sahipler))

    for tablo_adi, turev in (("nonDerivativeTable", False), ("derivativeTable", True)):
        tablo = kok.find(tablo_adi)
        if tablo is None:
            continue
        for cocuk in tablo:
            # `...Transaction` islem, `...Holding` yalnizca mevcut pozisyon.
            # Ikisini ayni listede ayrimsiz vermek, hic alinip satilmamis bir
            # pozisyonu "islem" gibi gosterirdi.
            tutma = cocuk.tag.endswith("Holding")
            if not (cocuk.tag.endswith("Transaction") or tutma):
                continue
            kodlama = cocuk.find("transactionCoding")
            miktar = cocuk.find("transactionAmounts")
            sonrasi = cocuk.find("postTransactionAmounts")
            doga = cocuk.find("ownershipNature")
            out.islemler.append(Islem(
                owner_name=ad,
                owner_cik=cik,
                is_director=yonetici,
                is_officer=gorevli,
                is_ten_percent_owner=onda_bir,
                officer_title=unvan,
                security=_deger(cocuk, "securityTitle") or "",
                transaction_date=_deger(cocuk, "transactionDate"),
                code=_deger(kodlama, "transactionCode") if kodlama is not None else None,
                shares=_sayi(_deger(miktar, "transactionShares") if miktar is not None else None),
                price_per_share=_sayi(
                    _deger(miktar, "transactionPricePerShare") if miktar is not None else None),
                acquired_or_disposed=(
                    _deger(miktar, "transactionAcquiredDisposedCode")
                    if miktar is not None else None),
                shares_owned_after=_sayi(
                    _deger(sonrasi, "sharesOwnedFollowingTransaction")
                    if sonrasi is not None else None),
                direct_or_indirect=(
                    _deger(doga, "directOrIndirectOwnership") if doga is not None else None),
                nature_of_ownership=(
                    _deger(doga, "natureOfOwnership") if doga is not None else None),
                is_derivative=turev,
                is_holding=tutma,
                owner_count=sahip_sayisi,
            ))
    return out


# ------------------------------------------------------------------- 13F
# Olculdu (Berkshire Hathaway): bilgi tablosu AD ALANLI -
# `http://www.sec.gov/edgar/document/thirteenf/informationtable`. Dosya adi
# rastgele ("56757.xml", "18337.xml"), yani dizinden bulunmasi gerekiyor.
BILGI_TABLOSU_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"

# SEC 2023'te 13F deger biriminini BINDEN tam dolara cevirdi. Olculdu ve iki
# ucta da dogrulandi (Berkshire, ayni 669.429.166 Apple hissesi):
#   14 Kas 2022 dosyalamasi -> value 92.515.111      (bin dolar, ~138 $/hisse)
#   14 Sub 2023 dosyalamasi -> value 86.841.985.318  (tam dolar, ~129,72 $/hisse)
# Ayni pozisyon, ardisik iki ceyrek, BIN KAT fark. Normalize etmeden iki ceyregi
# karsilastiran bir model "pozisyon 1000 katina cikti" der - ve bunu hicbir
# hata mesaji durdurmaz. Sinir tarihi SEC'in kural degisikliginin yururluk
# tarihi; iki olcum sinirin iki yanindan.
BIRIM_SINIRI = "2023-01-03"


@dataclass
class Pozisyon:
    issuer: str
    cusip: str | None
    title_of_class: str | None
    value_as_filed: float | None
    shares_or_principal: float | None
    share_type: str | None          # SH (hisse) ya da PRN (anapara)
    investment_discretion: str | None
    voting_sole: float | None
    voting_shared: float | None
    voting_none: float | None


def bilgi_tablosu_ayristir(govde: str) -> list[Pozisyon]:
    """13F bilgi tablosu XML -> pozisyon listesi (ham satirlar, birlestirilmemis)."""
    try:
        kok = ET.parse(io.StringIO(govde)).getroot()
    except ET.ParseError as e:
        bas = govde.lstrip()[:60].replace("\n", " ")
        raise ValueError(
            f"This 13F information table could not be parsed as XML ({e}). The "
            f"response began with: {bas!r}. SEC publishes a styled copy under an "
            "xslForm13F.../ path; the machine-readable table is the file without "
            "that prefix."
        ) from e

    def al(e: ET.Element, ad: str) -> str | None:
        # Ad alani BILDIRILMIS olabilir de olmayabilir de: eski dosyalamalarda
        # onek kullanimi degisiyor. Ikisi de deneniyor.
        c = e.find(f"{{{BILGI_TABLOSU_NS}}}{ad}")
        if c is None:
            c = e.find(ad)
        if c is None:
            return None
        return " ".join((c.text or "").split()) or None

    def ic(e: ET.Element, kapsayici: str, ad: str) -> str | None:
        k = e.find(f"{{{BILGI_TABLOSU_NS}}}{kapsayici}")
        if k is None:
            k = e.find(kapsayici)
        return al(k, ad) if k is not None else None

    out: list[Pozisyon] = []
    for satir in kok:
        if not satir.tag.endswith("infoTable"):
            continue
        out.append(Pozisyon(
            issuer=al(satir, "nameOfIssuer") or "",
            cusip=al(satir, "cusip"),
            title_of_class=al(satir, "titleOfClass"),
            value_as_filed=_sayi(al(satir, "value")),
            shares_or_principal=_sayi(ic(satir, "shrsOrPrnAmt", "sshPrnamt")),
            share_type=ic(satir, "shrsOrPrnAmt", "sshPrnamtType"),
            investment_discretion=al(satir, "investmentDiscretion"),
            voting_sole=_sayi(ic(satir, "votingAuthority", "Sole")),
            voting_shared=_sayi(ic(satir, "votingAuthority", "Shared")),
            voting_none=_sayi(ic(satir, "votingAuthority", "None")),
        ))
    return out


@dataclass
class KapakSayfasi:
    manager_name: str | None = None
    report_type: str | None = None
    period_of_report: str | None = None
    table_entry_total: int | None = None
    table_value_total: float | None = None
    other_managers: int | None = None
    # Duzeltme bilgisi. `report_type` BASKA bir kutu (HOLDINGS / NOTICE /
    # COMBINATION) ve duzeltme durumuyla ilgisi yok - 18 Agu 2026 denetiminde
    # tam da bu karistirildi: bir 13F-HR/A "13F HOLDINGS REPORT" diye
    # donuyordu ve okuyan, 1,7 milyar dolarlik tek pozisyonu Berkshire'in tum
    # portfoyu saniyordu (gercek ~313 milyar).
    amendment: bool = False
    amendment_number: int | None = None
    amendment_type: str | None = None


def kapak_ayristir(govde: str) -> KapakSayfasi:
    """13F `primary_doc.xml` -> kapak bilgisi. Bozuksa BOS doner, hata vermez:
    kapak sayfasi olmadan da pozisyonlar okunabiliyor ve eksik bir ozet, hic
    cevap vermemekten iyi."""
    try:
        kok = ET.parse(io.StringIO(govde)).getroot()
    except ET.ParseError:
        return KapakSayfasi()

    def bul(ad: str) -> str | None:
        for e in kok.iter():
            if e.tag.split("}")[-1] == ad:
                metin = " ".join((e.text or "").split())
                if metin:
                    return metin
        return None

    # `name` hem dosyalayan yoneticide hem imza blogunda geciyor; kapak
    # sayfasindaki ilki dosyalayan yoneticidir.
    sayi = _sayi(bul("tableEntryTotal"))
    diger = _sayi(bul("otherIncludedManagersCount"))
    duzeltme_no = _sayi(bul("amendmentNo"))
    # `amendmentType` iki degerden biri: RESTATEMENT (orijinalin YERINE gecer)
    # ya da NEW HOLDINGS (orijinale EKLENIR). Ikisi tumuyle farkli okunur ve
    # varsayilan yorum yanlis olandir.
    duzeltme_tipi = bul("amendmentType")
    bayrak = bul("isAmendment")
    return KapakSayfasi(
        amendment=(duzeltme_no is not None or duzeltme_tipi is not None
                   or str(bayrak or "").strip().lower() in ("true", "y", "1")),
        amendment_number=int(duzeltme_no) if duzeltme_no is not None else None,
        amendment_type=duzeltme_tipi,
        manager_name=bul("name"),
        report_type=bul("reportType"),
        period_of_report=bul("periodOfReport"),
        table_entry_total=int(sayi) if sayi is not None else None,
        table_value_total=_sayi(bul("tableValueTotal")),
        other_managers=int(diger) if diger is not None else None,
    )
