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
_ORTULU_KAPANIS = {
    "p": {"p"},
    "li": {"li"},
    "tr": {"td", "th", "tr"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "option": {"option"},
    "dd": {"dd", "dt"},
    "dt": {"dd", "dt"},
}


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

    def _kapat(self, tag: str) -> bool:
        """Yiginda `tag`'i geriye dogru arar ve oraya kadar her seyi kapatir."""
        for i in range(len(self._yigin) - 1, -1, -1):
            if self._yigin[i][0] == tag:
                for _, gizli in self._yigin[i:]:
                    if gizli:
                        self._atla -= 1
                del self._yigin[i:]
                return True
        return False      # eslesmeyen kapanis etiketi: yok sayilir

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _KAPANMAYAN:
            if tag == "br" and not self._atla:
                self.parcalar.append("\n")
            return

        for kapanacak in _ORTULU_KAPANIS.get(tag, ()):
            if any(a == kapanacak for a, _ in self._yigin):
                self._kapat(kapanacak)
                break

        gizli = tag in _ATLANAN or (self._gizliyi_atla and _gizli_mi(attrs))
        self._yigin.append((tag, gizli))
        if gizli:
            self._atla += 1
        elif tag in ("td", "th"):
            self.parcalar.append(" | ")
        elif tag in _BLOK:
            self.parcalar.append("\n")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "br" and not self._atla:
            self.parcalar.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _KAPANMAYAN:
            return
        if self._kapat(tag) and not self._atla and tag in _BLOK:
            self.parcalar.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._atla:
            self.parcalar.append(data)


# Gizli blok filtresi belgenin bu kesrinden fazlasini yutarsa, filtre yaniliyor
# demektir. Olculdu: gercek bir 10-K'da gizli iXBRL basligi ~1.200 karakter,
# belge 2,4 MB - yani normalde binde birden az. 1/200 genis bir emniyet payi.
_YUTMA_ORANI = 200
_YUTMA_TABANI = 5000


def metne_cevir(govde: str, gizliyi_atla: bool = True) -> str:
    """HTML (ya da duz metin) -> okunabilir duz metin.

    Emniyet agi: gizli blok filtresi belgeyi neredeyse tamamen yutuyorsa,
    filtresiz yeniden cevrilir. Gizli bir blok yuzunden BOS bir metin
    dondurmek, modele "bu dosyalama bos" dedirtir - bu deponun butun tezi olan
    "sessiz yanlislik"in ta kendisi (P-19). Gurultulu ama dolu bir metin,
    sessizce bos bir metinden iyidir.
    """
    if "<" not in govde:
        return _bosluk_topla(govde)
    ayristirici = _MetinToplayici(gizliyi_atla=gizliyi_atla)
    ayristirici.feed(govde)
    ayristirici.close()
    metin = _bosluk_topla("".join(ayristirici.parcalar))

    if (gizliyi_atla and len(govde) >= _YUTMA_TABANI
            and len(metin) < len(govde) // _YUTMA_ORANI):
        return metne_cevir(govde, gizliyi_atla=False)
    return metin


def _bosluk_topla(metin: str) -> str:
    metin = metin.replace("\xa0", " ").replace("​", "")
    metin = re.sub(r"[ \t]+", " ", metin)
    metin = re.sub(r" *\n *", "\n", metin)
    metin = re.sub(r"\n{3,}", "\n\n", metin)
    return metin.strip()


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
