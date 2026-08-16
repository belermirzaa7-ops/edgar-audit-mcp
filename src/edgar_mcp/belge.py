"""Dosyalama belgesini metne cevirir ve bolumlerine ayirir.

Neden bagimlilik yok: cekirdek yalnizca mcp/httpx/pydantic'e dayaniyor
(KK-3). HTML ayristirmasi icin stdlib `html.parser` yetiyor; BeautifulSoup
eklemek calisma-zamani bagimliligini sirf birkac satir icin buyuturdu.

Iki tuzak burada cozuluyor, ikisi de olculebilir:

1. **Icindekiler tablosu.** Bir 10-K'da "Item 7. Management's Discussion..."
   ifadesi en az iki kez gecer: once icindekiler tablosunda, sonra bolumun
   kendisinde. Ilk eslesmeyi almak, modele iki satirlik bir baglanti listesi
   dondurur ve bolum "bos" gorunur. Cozum: bir baslik adayi, ancak kendisinden
   sonraki metin ANLAMLI uzunluktaysa gercek bolum sayilir.
2. **Tablolar.** Mali tablolar HTML tablosudur; etiketler duz atilirsa satirlar
   birbirine yapisir ve sayilar okunamaz hale gelir. Hucreler ` | ` ile,
   satirlar yeni satirla ayriliyor.
3. **Gizli iXBRL basligi.** Modern dosyalamalar `display:none` bir blokla
   basliyor; icinde yuzlerce ad alani URL'si ve etiket var. Olculdu (14 Agu
   2026, TSLA FY2023 10-K): belgenin ILK 1200 karakteri tamamen bu gurultu.
   Gizlenmis ogeler metne alinmiyor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Bir bolum basligi sayilmak icin ardindan gelmesi gereken en az karakter.
# Icindekiler tablosundaki girisler birbirini birkac on karakterde izler;
# gercek bolumler binlerce karakter surer. 400 ikisinin arasinda genis bir
# aralikta duruyor - olculdu: tipik icindekiler girisi < 120 karakter.
BOLUM_ESIGI = 400

_ATLANAN = {"script", "style", "head", "title", "meta", "link"}
_BLOK = {"p", "div", "br", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6",
         "li", "ul", "ol", "section", "article", "header", "footer"}

# Kapanis etiketi OLMAYAN elemanlar. Yigina konursa sonsuza kadar acik kalirlar.
_KAPANMAYAN = {"area", "base", "br", "col", "embed", "hr", "img", "input",
               "link", "meta", "param", "source", "track", "wbr"}

# HTML kapanis etiketini ZORUNLU TUTMAZ: `<td>a<td>b` gecerlidir ve ikinci
# `<td>` birincisini kapatir. Tarayicilar bunu "implied end tag" diye uygular.
# Gercek EDGAR dosyalamalari bu bicimde HTML uretiyor; uygulamazsak ayni ada
# sahip elemanlar yigin uzerinde birikir.
# DEMET, kume DEGIL - ve hepsi kapatilir, ilkinde durulmaz.
# 15 Agu 2026'da olculdu: bunlar kume olunca iterasyon sirasi CPython'un
# surec basina rastgelelesen string hash'ine bagli kaliyordu. `<tr>` bir `<td>`
# aciken geldiginde tarayici IKISINI de kapatir; kumeden once `td` gelirse ve
# ilk eslesmede durulursa disaridaki `tr` yiginda ASILI kalir. O `tr` gizliyse
# `_atla` bir daha sifirlanmaz ve tablonun geri kalani yutulur.
# Sonuc: ayni dosyalama, ayni kod, farkli SURECTE farkli cevap -
# PYTHONHASHSEED=0/2'de mali tablo geliyor, 1/3'te bos donuyordu.
_ORTULU_KAPANIS = {
    "p": ("p",),
    "li": ("li",),
    "tr": ("td", "th", "tr"),
    "td": ("td", "th"),
    "th": ("td", "th"),
    "option": ("option",),
    "dd": ("dd", "dt"),
    "dt": ("dd", "dt"),
}


# Tablo basina en fazla kac satir dondurulur. Gercek bir 10-K'nin en uzun
# tablosu (hisse bazli odeme hareket tablosu, vergi mutabakati) yuzlerce satir
# olabiliyor; sinir SESSIZ DEGIL, `Tablo.kirpildi` ve `toplam_satir` ile
# bildiriliyor.
SATIR_SINIRI = 200
# Hucre metni siniri. Mali tablo hucreleri kisa; bu siniri asan sey genelde
# yerlesim icin tablo kullanan bir paragraftir.
HUCRE_SINIRI = 300


@dataclass
class Tablo:
    """Bir HTML tablosunun satir/hucre yapisi.

    Neden yapiyi da donduruyoruz: duz metinde tablo ` | ` ile ayrilmis tek bir
    satira donusuyor ve modelin sutunlari hizalamasi gerekiyor - teslimat
    adetleri, vergi mutabakati, segment tablosu hep boyle okunuyordu. Yapiyi
    dondurup yorumu modele birakmak, sirkete ozel ayristirici yazmaktan daha az
    kirilgan: EDGAR'da tablo bicimi dosyalayandan dosyalayana degisiyor.
    """
    baslangic: int                       # tablonun metindeki karakter konumu
    satirlar: list[list[str]] = field(default_factory=list)
    toplam_satir: int = 0                # kirpma ONCESI satir sayisi
    kirpildi: bool = False
    hucre_kirpildi: bool = False


@dataclass
class Cikti:
    metin: str
    tablolar: list[Tablo] = field(default_factory=list)
    # Sekil filtresine takilan tablolar: EDGAR HTML'i sayfa YERLESIMI icin de
    # tablo kullanir (tek hucrelik ara verici, tek satirlik baslik seridi).
    # Sayisi bildiriliyor, cunku "tablo yok" ile "tablolarin hepsi yerlesimdi"
    # ayni sey degil.
    yerlesim_tablolari: int = 0


class _TabloKurucu:
    def __init__(self, ham_konum: int) -> None:
        self.ham_konum = ham_konum
        self.satirlar: list[list[str]] = []
        self._satir: list[str] | None = None
        self._hucre: list[str] | None = None
        self.hucre_kirpildi = False

    def satir_baslat(self) -> None:
        self.hucre_kapat()
        self._satir = []
        self.satirlar.append(self._satir)

    def hucre_baslat(self) -> None:
        self.hucre_kapat()
        if self._satir is None:
            self.satir_baslat()
        self._hucre = []
        assert self._satir is not None
        self._satir.append("")

    def yaz(self, veri: str) -> None:
        if self._hucre is not None:
            self._hucre.append(veri)

    def hucre_kapat(self) -> None:
        if self._hucre is None or self._satir is None:
            self._hucre = None
            return
        metin = " ".join("".join(self._hucre).split())
        if len(metin) > HUCRE_SINIRI:
            metin = metin[:HUCRE_SINIRI]
            self.hucre_kirpildi = True
        self._satir[-1] = metin
        self._hucre = None

    def bitir(self) -> Tablo:
        self.hucre_kapat()
        # Tamami bos satirlar atiliyor: EDGAR tablolari araya bos satirlar ve
        # girinti hucreleri koyuyor, ikisi de bilgi tasimiyor. Bos HUCRE
        # atilmiyor - sutun hizasi onunla duruyor.
        dolu = [s for s in self.satirlar if any(h for h in s)]
        t = Tablo(baslangic=self.ham_konum, toplam_satir=len(dolu),
                  hucre_kirpildi=self.hucre_kirpildi)
        t.satirlar = dolu[:SATIR_SINIRI]
        t.kirpildi = len(dolu) > SATIR_SINIRI
        return t


def _gizli_mi(attrs: list) -> bool:
    """`style="display:none"` tasiyan oge ve altindaki her sey metne girmez.
    Inline XBRL dosyalamalari gizli bir blokla baslar; o blok yuzlerce ad alani
    URL'si icerir ve belgenin ilk sayfasini gurultuye cevirir."""
    for ad, deger in attrs:
        if ad and ad.lower() == "style" and deger:
            duz = deger.replace(" ", "").lower()
            if "display:none" in duz:
                return True
    return False


class _MetinToplayici(HTMLParser):
    """Gizli bloklari atlayarak metni toplar.

    Yigin yonetimi (15 Agu 2026'da bulunan hata): ilk surum gizli etiketleri
    bir yigina koyuyor ve kapanis etiketi YALNIZCA yiginin tepesiyle
    eslesirse cikariyordu. Gercek EDGAR HTML'inde bu, belgenin TAMAMINI
    yutuyordu:
      - `<td style="display:none">gizli<tr><td>Revenue` - ilk `td` hic
        kapanmiyor, `_atla` bir daha sifirlanmiyor, geri kalan her sey gizli
        sayiliyor. Olculdu: 2,4 MB'lik bir belge 3 karaktere dusuyordu.
      - `<img style="display:none">` - kapanis etiketi olmayan eleman, ayni
        sonuc.
      - `<div style="display:none"><div>x</div>SIZINTI</div>` - ic teki `div`
        yigini erken bosaltiyor ve gizli icerik metne SIZIYOR.
    Cozum tarayicilarin yaptigi: yigin (ad, gizli_mi) ciftleri tutar, kapanis
    etiketi yiginda GERIYE DOGRU aranir ve o noktaya kadar her sey kapatilir,
    kapanmayan elemanlar hic yigina girmez, ve `<td>a<td>b` gibi ortulu
    kapanislar uygulanir.
    """

    def __init__(self, gizliyi_atla: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self.parcalar: list[str] = []
        self._gizliyi_atla = gizliyi_atla
        self._atla = 0
        self._yigin: list[tuple[str, bool]] = []
        # Tablo toplama. `_acik` ic ice tablolari tutar (EDGAR yerlesim icin
        # tablo ICINE tablo koyar); hucre metni EN ICTEKI tabloya yazilir,
        # kapanan her tablo kendi kaydi olarak listeye girer.
        self._acik: list[_TabloKurucu] = []
        self.tablolar: list[Tablo] = []
        self._uzunluk = 0        # `parcalar`in ham toplam uzunlugu

    def _yaz(self, parca: str) -> None:
        self.parcalar.append(parca)
        self._uzunluk += len(parca)

    def _tablo_bitir(self, kurucu: _TabloKurucu) -> None:
        self.tablolar.append(kurucu.bitir())

    def _tablo_kapsami(self) -> int:
        """Ortulu kapanis aramasinin inebilecegi en alt indeks.

        Neden sinir gerekiyor (15 Agu 2026, tablo modu yazilirken bulundu):
        EDGAR yerlesim icin tablo ICINE tablo koyuyor. Ic tablonun `<tr>`'si
        ortulu kapanis kuraliyla DIS tablonun acik `<td>`'sini kapatiyordu -
        tarayicilar bunu yapmaz, ic tablo yeni bir tablo baglami acar. Sonuc
        olculdu: dis tablonun satirlari tumden kayboluyor ve metin de bozuluyor
        (`| \n\n| ic1 | ic2 ... | dis2` - dis satirin ilk hucresi yok).
        """
        for i in range(len(self._yigin) - 1, -1, -1):
            if self._yigin[i][0] == "table":
                return i + 1
        return 0

    def _kapat(self, tag: str, alt: int = 0) -> bool:
        """Yiginda `tag`'i geriye dogru arar ve oraya kadar her seyi kapatir."""
        for i in range(len(self._yigin) - 1, alt - 1, -1):
            if self._yigin[i][0] == tag:
                for ad, gizli in self._yigin[i:]:
                    if gizli:
                        self._atla -= 1
                    # Ortulu kapanis bir tabloyu da kapatabilir (`<table>` acikken
                    # disaridaki `<div>` kapanirsa). Tablo kurucusu yiginla
                    # birlikte kapanmazsa sonraki tablonun hucreleri buna yazilir.
                    if ad == "table" and self._acik:
                        self._tablo_bitir(self._acik.pop())
                del self._yigin[i:]
                return True
        return False      # eslesmeyen kapanis etiketi: yok sayilir

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _KAPANMAYAN:
            if tag == "br" and not self._atla:
                self._yaz("\n")
            return

        # Satir/hucre etiketleri yalnizca KENDI tablosunun icinde ortulu
        # kapanis uretir; oteki etiketler (p, li, dt/dd) icin sinir yok.
        alt = self._tablo_kapsami() if tag in ("tr", "td", "th") else 0
        for kapanacak in _ORTULU_KAPANIS.get(tag, ()):
            if any(a == kapanacak for a, _ in self._yigin[alt:]):
                self._kapat(kapanacak, alt)

        gizli = tag in _ATLANAN or (self._gizliyi_atla and _gizli_mi(attrs))
        self._yigin.append((tag, gizli))
        if gizli:
            self._atla += 1
        elif not self._atla:
            # Gizli bir blogun icindeki tablo toplanmiyor: metne girmeyen bir
            # tabloyu yapisal olarak dondurmek, filtreyi bir kapidan kovup
            # otekinden almak olurdu.
            if tag == "table":
                self._acik.append(_TabloKurucu(self._uzunluk))
            elif self._acik:
                if tag == "tr":
                    self._acik[-1].satir_baslat()
                elif tag in ("td", "th"):
                    self._acik[-1].hucre_baslat()
        # Ayirici de gizli blogun ICINDE uretilmemeli: `handle_endtag` bunu
        # kontrol ediyordu, `handle_starttag` etmiyordu. Yutulan bir tablo yine
        # de tum `|` iskeletini yaziyor, cikti uzun kaliyor ve `metne_cevir`
        # icindeki yutma emniyet agi HIC devreye girmiyordu (15 Agu 2026).
        if self._atla:
            pass
        elif tag in ("td", "th"):
            self._yaz(" | ")
        elif tag in _BLOK:
            self._yaz("\n")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "br" and not self._atla:
            self._yaz("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _KAPANMAYAN:
            return
        if tag in ("td", "th") and self._acik and not self._atla:
            self._acik[-1].hucre_kapat()
        if self._kapat(tag) and not self._atla and tag in _BLOK:
            self._yaz("\n")

    def handle_data(self, data: str) -> None:
        if not self._atla:
            self._yaz(data)
            if self._acik:
                self._acik[-1].yaz(data)

    def close(self) -> None:
        super().close()
        # Kapanmamis tablolar da dondurulur: EDGAR HTML'i kapanis etiketlerini
        # atlayabiliyor ve belgenin son tablosu tam da mali tablolar olabiliyor.
        while self._acik:
            self._tablo_bitir(self._acik.pop())


# Gizli blok filtresi belgenin bu kesrinden fazlasini yutarsa, filtre yaniliyor
# demektir. Olculdu: gercek bir 10-K'da gizli iXBRL basligi ~1.200 karakter,
# belge 2,4 MB - yani normalde binde birden az. 1/200 genis bir emniyet payi.
_YUTMA_ORANI = 200
_YUTMA_TABANI = 5000


def cevir(govde: str, gizliyi_atla: bool = True) -> Cikti:
    """HTML (ya da duz metin) -> metin VE tablolarin satir/hucre yapisi.

    Emniyet agi: gizli blok filtresi belgeyi neredeyse tamamen yutuyorsa,
    filtresiz yeniden cevrilir. Gizli bir blok yuzunden BOS bir metin
    dondurmek, modele "bu dosyalama bos" dedirtir - bu deponun butun tezi olan
    "sessiz yanlislik"in ta kendisi (P-19). Gurultulu ama dolu bir metin,
    sessizce bos bir metinden iyidir.

    Tablolar metinle AYNI gecisde toplaniyor. Ayri bir gecis daha ucuz olurdu
    ama tablonun metindeki KONUMU kaybolurdu; o konum olmadan "su an okudugun
    parcanin tablolari" diye bir soru sorulamaz ve model, ilgisiz bir tabloyu
    okudugu bolume ait sanar.
    """
    if "<" not in govde:
        metin, _ = _topla(govde, [])
        return Cikti(metin=metin)

    ayristirici = _MetinToplayici(gizliyi_atla=gizliyi_atla)
    ayristirici.feed(govde)
    ayristirici.close()
    ham = "".join(ayristirici.parcalar)
    metin, esleme = _topla(ham, [t.baslangic for t in ayristirici.tablolar])

    if (gizliyi_atla and len(govde) >= _YUTMA_TABANI
            and len(metin) < len(govde) // _YUTMA_ORANI):
        return cevir(govde, gizliyi_atla=False)

    tablolar: list[Tablo] = []
    yerlesim = 0
    for t in ayristirici.tablolar:
        if len(t.satirlar) < 2 or max((len(s) for s in t.satirlar), default=0) < 2:
            yerlesim += 1
            continue
        t.baslangic = esleme.get(t.baslangic, 0)
        tablolar.append(t)
    tablolar.sort(key=lambda t: t.baslangic)
    return Cikti(metin=metin, tablolar=tablolar, yerlesim_tablolari=yerlesim)


def metne_cevir(govde: str, gizliyi_atla: bool = True) -> str:
    """Yalnizca metin isteyen cagiranlar icin ince sarmalayici."""
    return cevir(govde, gizliyi_atla=gizliyi_atla).metin


_BOSLUKLAR = " \t\n\xa0"
_ATILAN = "​"


def _topla(metin: str, konumlar: list[int]) -> tuple[str, dict[int, int]]:
    """Bosluk sadelestirme + verilen ham konumlarin yeni karsiliklari.

    Neden regex zinciri degil tek gecis: tablo konumlari HAM metinde olculuyor,
    sadelestirme ise karakter siliyor. Iki islemi ayirinca konumlari yeniden
    hesaplamak icin ayni sadelestirmenin ikinci bir uygulamasi gerekiyordu -
    iki uygulama zamanla birbirinden ayrilir. Burada tek uygulama var ve
    konumlar onunla birlikte tasiniyor.

    Davranis eski regex zinciriyle BIREBIR ayni olmali; bir test bunu her
    fixture uzerinde karsilastiriyor (`test_bosluk_sadelestirme_eski_regex_
    zinciriyle_ayni`).
    """
    parcalar: list[str] = []
    uzunluk = 0
    esleme: dict[int, int] = {}
    hedefler = sorted(set(konumlar))
    j = 0
    i = 0
    n = len(metin)

    while i < n:
        while j < len(hedefler) and hedefler[j] <= i:
            esleme[hedefler[j]] = uzunluk
            j += 1

        c = metin[i]
        if c in _ATILAN:
            i += 1
            continue
        if c in _BOSLUKLAR:
            satir = 0
            bekleyen: list[int] = []
            while i < n and (metin[i] in _BOSLUKLAR or metin[i] in _ATILAN):
                while j < len(hedefler) and hedefler[j] <= i:
                    bekleyen.append(hedefler[j])
                    j += 1
                if metin[i] == "\n":
                    satir += 1
                i += 1
            parca = "\n" * min(satir, 2) if satir else " "
            parcalar.append(parca)
            uzunluk += len(parca)
            # Bosluk yiginin ICINDEKI konum, yigindan SONRAKI ilk karaktere
            # baglaniyor: tablo "buradan basliyor" demek, "buradan once bir
            # bosluk vardi" demek degil.
            for h in bekleyen:
                esleme[h] = uzunluk
            continue
        parcalar.append(c)
        uzunluk += 1
        i += 1

    while j < len(hedefler):
        esleme[hedefler[j]] = uzunluk
        j += 1

    ham = "".join(parcalar)
    kirpilan = len(ham) - len(ham.lstrip())
    sonuc = ham.strip()
    return sonuc, {k: min(max(v - kirpilan, 0), len(sonuc)) for k, v in esleme.items()}


# "Item 7.", "ITEM 1A -", "Item 9B." ... Baslik satirin basinda olmali.
# Satir basindaki `|`, tire ve yildizlar: gercek dosyalamalarda basliklar
# HTML TABLOSU icinde durur, metne cevrilince satir " | " ile baslar. Bu izni
# vermezsek tablo yerlesimli 10-K'larda hicbir bolum bulunamaz.
_ONEK = r"^[\s|>*\-–—.]*"
_ITEM = re.compile(_ONEK + r"item\s+(\d{1,2}[a-c]?)\s*[.\-:—|]?\s*(.{0,90})$",
                   re.IGNORECASE | re.MULTILINE)
# "Note 12. Income Taxes" ya da tek basina "Income Taxes" gibi dipnot basliklari
_NOT = re.compile(_ONEK + r"note\s+(\d{1,2})\s*[.\-:—|]?\s*(.{0,90})$",
                  re.IGNORECASE | re.MULTILINE)


def _kod(baslik: str) -> str:
    """Basligin kimligi: "ITEM 7. MANAGEMENT'S..." -> "item 7"."""
    m = re.match(r"\s*(item|note)\s+(\d{1,2}[a-c]?)", baslik, re.IGNORECASE)
    return f"{m.group(1).lower()} {m.group(2).lower()}" if m else baslik.lower()


def bolumler(metin: str, esik: int = BOLUM_ESIGI) -> list[tuple[str, int, int]]:
    """(baslik, baslangic, bitis) listesi. Icindekiler tablosu elenir ve ayni
    bolum kodu bir kez listelenir.

    Eleme kurali: bir aday basliktan sonraki metin, bir sonraki adaya kadar
    `esik` karakterden kisaysa o aday gercek bolum degildir.

    Tekillestirme (olculdu, 14 Agu 2026, TSLA FY2023 10-K): esikten gecen
    ikinci bir "Item 16" listenin BASINDA, ITEM 1'den once goruluyordu - kapak
    sayfasindaki bir referans. Ayni kod birden fazla kez gecerse EN UZUN blok
    kalir; listedeki sira belgedeki sira olur.
    """
    adaylar: list[tuple[str, int]] = []
    for kalip in (_ITEM, _NOT):
        for m in kalip.finditer(metin):
            baslik = " ".join(m.group(0).split()).strip(" |*-.")
            adaylar.append((baslik, m.start()))
    adaylar.sort(key=lambda x: x[1])

    gecerli: list[tuple[str, int, int]] = []
    for i, (baslik, bas) in enumerate(adaylar):
        son = adaylar[i + 1][1] if i + 1 < len(adaylar) else len(metin)
        if son - bas >= esik:
            gecerli.append((baslik, bas, son))

    en_uzun: dict[str, tuple[str, int, int]] = {}
    for b in gecerli:
        k = _kod(b[0])
        if k not in en_uzun or (b[2] - b[1]) > (en_uzun[k][2] - en_uzun[k][1]):
            en_uzun[k] = b
    return sorted(en_uzun.values(), key=lambda b: b[1])


def bolum_sec(
    bolumler_listesi: list[tuple[str, int, int]], istek: str
) -> tuple[str, int, int] | None:
    """Kullanicinin verdigi ifadeye en iyi uyan bolum.

    Once "item 7" gibi kod eslesmesi, sonra baslik icinde alt dize aramasi.
    Birden fazla eslesirse EN UZUN bolum secilir: ayni kod hem ozet hem asil
    bolumde gecebilir, asil olan uzun olandir.
    """
    q = " ".join(istek.split()).lower().rstrip(".")
    kod = re.match(r"^item\s+(\d{1,2}[a-c]?)$", q)

    if kod:
        hedef = f"item {kod.group(1)}"
        eslesen = [
            b for b in bolumler_listesi
            if re.match(rf"^item\s+{re.escape(kod.group(1))}\b", b[0].lower())
        ]
    else:
        hedef = q
        eslesen = [b for b in bolumler_listesi if hedef in b[0].lower()]

    if not eslesen:
        return None
    return max(eslesen, key=lambda b: b[2] - b[1])
