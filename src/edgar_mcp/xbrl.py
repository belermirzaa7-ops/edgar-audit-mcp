"""XBRL instance belgesini ayristirir - BOYUTLU (dimensional) fact'ler dahil.

Neden bu modul var: SEC'in XBRL REST API'si (companyfacts/companyconcept/frames)
boyutlu fact'leri TASIMAZ. SEC kendi API sayfasinda bu uclari tarif ederken
"Apply to the entire filing entity" diyor; segment fact'i tuzel kisinin bir
PARCASINA ait oldugu icin kapsam disinda kaliyor. SEC "dimensional" kelimesini
kullanmiyor - bu yuzden bu, alintiyla desteklenen bir cikarim, birebir teyit
degil. Olculebilir sonuc ise net: TSLA'nin segment kirilimi companyfacts'te yok
(KK-26), dosyalamanin XBRL'inde var.

Bagimlilik eklenmedi: stdlib `xml.etree.ElementTree` yetiyor (KK-3). `lxml`'in
kazandirdigi sey hiz; bu isin darbogazi 2,7 MB'lik dosyayi INDIRMEK, ayristirmak
degil. Ayristirma tek geciste ve `iterparse` ile yapiliyor - ad alani onekleri
ancak `start-ns` olaylarindan okunabiliyor, ki QName'leri dosyalamada gorulen
haliyle (`us-gaap:Revenues`) verebilelim.

Okunan dosya hakkinda durust olmak gerekiyor: `<mnemonic>-<tarih>_htm.xml`
dosyalayanin sundugu bir belge DEGIL, SEC'in inline XBRL belgesinden mekanik
olarak AYIKLADIGI instance'tir. SEC'in dagitim spesifikasyonu onu
"EDGAR-generated" ciktilar arasinda sayiyor. Fark onemli ama kucuk: degerler
dosyalayanin isaretledigi degerler, context'ler dosyalayanin context'leri;
degisen sey kabuk. Gercekten ham olan tek sey inline `.htm`'in kendisidir ve
onu ayristirmak `ix:nonFraction`'in `scale`/`sign` niteliklerini yonetmek
demektir - kendi olcek tuzagiyla birlikte.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

INSTANCE_NS = "http://www.xbrl.org/2003/instance"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


@dataclass(frozen=True)
class Boyut:
    """Bir fact'in hangi kirilimda raporlandigi.

    `axis`/`member` adlandirmasi bilincli: SEC kendi dokumanlarinda "axis and
    member" diyor ve dosyalamada gorulen QName'ler `...Axis` / `...Member` ile
    bitiyor. XBRL spesifikasyonunun kendi dili "dimension/member"; kullaniciya
    bakan yuzde dosyalamada gorulen terim tercih edildi.
    """
    axis: str
    member: str | None       # typed dimension'da None
    typed_value: str | None = None   # typedMember'in ic degeri, varsa


@dataclass
class Baglam:
    id: str
    start: str | None
    end: str | None          # instant ise `start` None, `end` o tarih
    instant: bool
    boyutlar: tuple[Boyut, ...] = ()


@dataclass
class Olgu:
    """Tek bir raporlanan deger."""
    tag: str                 # `us-gaap:Revenues` - dosyalamadaki onekle
    context_id: str
    deger: str | None
    unit_id: str | None = None
    decimals: str | None = None
    fact_id: str | None = None
    nil: bool = False


@dataclass
class Instance:
    baglamlar: dict[str, Baglam] = field(default_factory=dict)
    birimler: dict[str, str] = field(default_factory=dict)
    olgular: list[Olgu] = field(default_factory=list)
    onekler: dict[str, str] = field(default_factory=dict)   # uri -> onek

    def boyutlu(self) -> list[Olgu]:
        return [o for o in self.olgular
                if self.baglamlar.get(o.context_id, BOS_BAGLAM).boyutlar]

    def boyutsuz(self) -> list[Olgu]:
        return [o for o in self.olgular
                if not self.baglamlar.get(o.context_id, BOS_BAGLAM).boyutlar]


BOS_BAGLAM = Baglam(id="", start=None, end=None, instant=False)


def _yerel(tag: str) -> tuple[str, str]:
    """`{uri}local` -> (uri, local). Ad alani yoksa uri bos doner."""
    if tag.startswith("{"):
        uri, _, ad = tag[1:].partition("}")
        return uri, ad
    return "", tag


def _qname(tag: str, onekler: dict[str, str]) -> str:
    """`{http://fasb.org/us-gaap/2025}Revenues` -> `us-gaap:Revenues`.

    Onek dosyalamanin kendi bildirimlerinden gelir; boylece dondugumuz ad,
    dosyalamayi acan birinin gordugu adla AYNI olur. Onek bilinmiyorsa ad alani
    aciktan yazilir - uydurma onek uretilmez.
    """
    uri, ad = _yerel(tag)
    if not uri:
        return ad
    onek = onekler.get(uri)
    return f"{onek}:{ad}" if onek else f"{{{uri}}}{ad}"


def _metin(e: ET.Element | None) -> str | None:
    if e is None or e.text is None:
        return None
    return " ".join(e.text.split()) or None


def _birim_metni(e: ET.Element) -> str:
    """`<measure>iso4217:USD</measure>` -> "USD";
    divide yapisi -> "USD/shares". Onek atilir: `iso4217:` ve `xbrli:` bilgi
    tasimiyor, birimin kendisi tasiyor."""
    def sade(m: str | None) -> str:
        return (m or "").split(":")[-1]

    olcumler = [sade(_metin(x)) for x in e.findall(f"{{{INSTANCE_NS}}}measure")]
    if olcumler:
        return "/".join(o for o in olcumler if o)

    bol = e.find(f"{{{INSTANCE_NS}}}divide")
    if bol is not None:
        pay = bol.find(f"{{{INSTANCE_NS}}}unitNumerator")
        payda = bol.find(f"{{{INSTANCE_NS}}}unitDenominator")
        p = sade(_metin(pay.find(f"{{{INSTANCE_NS}}}measure"))) if pay is not None else ""
        d = sade(_metin(payda.find(f"{{{INSTANCE_NS}}}measure"))) if payda is not None else ""
        if p or d:
            return f"{p}/{d}".strip("/")
    return ""


def _boyutlari_oku(baglam: ET.Element) -> tuple[Boyut, ...]:
    """Boyutlar `entity/segment` ICINDE ya da `scenario` icinde durabilir.

    Ikisi de spesifikasyona uygun ve gercek dosyalamalarda ikisi de goruluyor;
    yalnizca birine bakmak bazi dosyalamalarda TUM segment kirilimini gorunmez
    yapar. Ayni context birden fazla boyut tasiyabilir (segment VE cografya) -
    bu yuzden liste doner, tek cift degil.
    """
    out: list[Boyut] = []
    for kapsayici in (f".//{{{INSTANCE_NS}}}segment", f".//{{{INSTANCE_NS}}}scenario"):
        for kap in baglam.findall(kapsayici):
            for uye in kap.findall(f"{{{XBRLDI_NS}}}explicitMember"):
                eksen = (uye.get("dimension") or "").strip()
                if eksen:
                    out.append(Boyut(axis=eksen, member=_metin(uye)))
            for uye in kap.findall(f"{{{XBRLDI_NS}}}typedMember"):
                eksen = (uye.get("dimension") or "").strip()
                if not eksen:
                    continue
                ic = list(uye)
                out.append(Boyut(axis=eksen, member=None,
                                 typed_value=_metin(ic[0]) if ic else None))
    return tuple(out)


def _baglam_oku(e: ET.Element) -> Baglam:
    donem = e.find(f"{{{INSTANCE_NS}}}period")
    bas = son = None
    anlik = False
    if donem is not None:
        an = _metin(donem.find(f"{{{INSTANCE_NS}}}instant"))
        if an:
            anlik, son = True, an
        else:
            bas = _metin(donem.find(f"{{{INSTANCE_NS}}}startDate"))
            son = _metin(donem.find(f"{{{INSTANCE_NS}}}endDate"))
    return Baglam(id=e.get("id", ""), start=bas, end=son, instant=anlik,
                  boyutlar=_boyutlari_oku(e))


def ayristir(govde: str) -> Instance:
    """XBRL instance metni -> Instance.

    Tek gecis: `start-ns` olaylari ad alani oneklerini verir (ElementTree bunu
    baska turlu gostermiyor), `end` olaylari da elemanlari. Islenen ust duzey
    eleman `clear()` ile bosaltiliyor - 2,7 MB'lik bir 10-K instance'inda tum
    agaci bellekte tutmanin anlami yok.
    """
    inst = Instance()
    ayristirici = ET.iterparse(io.StringIO(govde), events=("start-ns", "end"))
    try:
        _doldur(inst, ayristirici)
    except ET.ParseError as e:
        # Cig bir traceback, cagirana ne yapacagini soylemez (§18). Bu durum
        # gercekten olabilir: kesilmis indirme, ya da XML yerine HTML hata
        # sayfasi donmesi.
        bas = govde.lstrip()[:60].replace("\n", " ")
        raise ValueError(
            f"This XBRL instance document could not be parsed as XML ({e}). "
            f"The response began with: {bas!r}. If that looks like HTML rather "
            "than XML, SEC returned an error page instead of the document; "
            "retrying the same call usually resolves it."
        ) from e
    return inst


def _doldur(inst: Instance, ayristirici) -> None:
    for olay, veri in ayristirici:
        if olay == "start-ns":
            onek, uri = veri
            # Ilk bildirim kazanir: varsayilan ad alani ("" oneki) bir sonraki
            # bildirimle ezilirse QName'ler dosyalamadakinden farkli cikar.
            inst.onekler.setdefault(uri, onek)
            continue

        uri, ad = _yerel(veri.tag)
        if uri == INSTANCE_NS and ad == "context":
            b = _baglam_oku(veri)
            inst.baglamlar[b.id] = b
            veri.clear()
        elif uri == INSTANCE_NS and ad == "unit":
            inst.birimler[veri.get("id", "")] = _birim_metni(veri)
            veri.clear()
        elif veri.get("contextRef"):
            inst.olgular.append(Olgu(
                tag=_qname(veri.tag, inst.onekler),
                context_id=veri.get("contextRef", ""),
                deger=_metin(veri),
                unit_id=veri.get("unitRef"),
                decimals=veri.get("decimals"),
                fact_id=veri.get("id"),
                nil=(veri.get(f"{{{XSI_NS}}}nil") or "").lower() == "true",
            ))
            veri.clear()


_SAYI = re.compile(r"^-?\d+(\.\d+)?$")


def sayi_mi(deger: str | None) -> bool:
    """Deger sayisal mi. XBRL'de metin fact'leri de vardir (politika metni,
    tarih, bayrak); onlari sayiya cevirmeye calismak sessiz hataya yol acar."""
    return bool(deger and _SAYI.match(deger.strip()))
