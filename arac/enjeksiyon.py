"""Hata enjeksiyonu (standart §2): her korumayi bilerek boz, testin KIRMIZIYA
dondugunu gor, geri al.

Cokmeye dayanikli: yedekler once diske yazilir, calisma basinda artik yedek
varsa once o geri yuklenir, sinyal ve istisna durumunda finally ile geri alinir.
`git checkout` KULLANILMAZ - commit edilmemis isi silerdi.
"""
import ast
import atexit
import hashlib
import os
import pathlib
import signal
import subprocess
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
YEDEK_DIZIN = KOK / ".enjeksiyon_yedek"
KILIT = KOK / ".enjeksiyon_kilit"
# Hangi enjeksiyonun UYGULANMIS oldugu; sert oldurmeden sonra tek ipucu bu.
UYGULANAN = YEDEK_DIZIN / "_uygulanan.txt"
DOSYALAR = [
    "src/edgar_mcp/server.py",
    "src/edgar_mcp/client.py",
    "arac/sir_tarama.py",
    "arac/ortam.py",
    "src/edgar_mcp/belge.py",
    "src/edgar_mcp/xbrl.py",
    "src/edgar_mcp/sahiplik.py",
    "Dockerfile",
]

ORTAM = {**os.environ, "SEC_RATE_LIMIT_PER_SEC": "1000"}
# Tek bir test kosusunun ust siniri (saniye). Asilirsa o enjeksiyon "olculemedi"
# sayilir; sessizce "koruma yok" sayilmaz.
SURE_SINIRI = int(os.environ.get("ENJEKSIYON_TEST_SURESI", "900"))


def hashle(f):
    return hashlib.sha256((KOK / f).read_bytes()).hexdigest()


def ciktiyi_utf8_yap() -> None:
    """Kendi ciktimizi da yerel kod sayfasina birakma (P-37'nin ikinci yuzu).

    Enjeksiyon adlari `§` gibi karakterler tasiyor. Cikti bir dosyaya ya da
    boruya yonlendirildiginde Python yerel kod sayfasini kullanir; ASCII'ye
    dusen bir ortamda ilk `print` `UnicodeEncodeError` ile harness'i olduruyor.

    Bu, CI'yi kiran hatanin AYNISI DEGIL: `§` hem cp1252'de hem cp1254'te var,
    yani Windows runner'inda bu satir patlamazdi. 18 Agu 2026'da duzeltmeyi
    dogrulamak icin ASCII yerel ayarda kosarken cikti - yani CI'dan daha DAR
    bir ortamda. Ayni sinif oldugu ve tek satir oldugu icin burada kapatiliyor;
    olcum aracinin kendi ciktisi, uzerinde kostugu makinenin kod sayfasina
    bagli olmamali.
    """
    for akis in (sys.stdout, sys.stderr):
        yeniden = getattr(akis, "reconfigure", None)
        if yeniden is not None:
            yeniden(encoding="utf-8", errors="replace")


def oku(yol: pathlib.Path) -> str:
    """Kaynagi HER ZAMAN UTF-8 olarak oku. `read_text()` KULLANMA.

    Neden (18 Agu 2026, CI #15-#30 - KK-49): `Path.read_text()` encoding
    verilmezse yerel kod sayfasini kullanir. Windows runner'inda bu cp1252;
    `belge.py` icindeki `–`/`—` karakterleri UTF-8'den cp1252'ye YANLIS
    cozuluyor (`Â–`) ve o dosyayi hedefleyen enjeksiyon dizgisi artik
    eslesmiyordu. Harness bunu dogru sekilde "ENJEKSIYON UYGULANAMADI" diye
    raporladi ve exit 1 dondu (KK-10) - yani CI dort gun boyunca hakli olarak
    kirmiziydi ve kirmizinin sebebi korunan kod degil, olcen aracin kendisiydi.

    Bayt duzeyinde okuyup acikca cozmek encoding'i sabitlemekle kalmiyor,
    universal-newline cevrimini de kapatiyor: `read_text()` CRLF'i LF'e cevirir,
    `write_text()` geri cevirir ve dosya, hicbir enjeksiyon uygulanmadan
    bayt olarak degisir.
    """
    return yol.read_bytes().decode("utf-8")


def yaz(yol: pathlib.Path, metin: str) -> None:
    """Kaynagi HER ZAMAN UTF-8 olarak yaz. Gerekce icin bkz. `oku`."""
    yol.write_bytes(metin.encode("utf-8"))


def yedekle():
    YEDEK_DIZIN.mkdir(exist_ok=True)
    for f in DOSYALAR:
        (YEDEK_DIZIN / pathlib.Path(f).name).write_bytes((KOK / f).read_bytes())


def geri_al(sessiz=True):
    if not YEDEK_DIZIN.exists():
        return
    for f in DOSYALAR:
        y = YEDEK_DIZIN / pathlib.Path(f).name
        if y.exists() and y.read_bytes() != (KOK / f).read_bytes():
            (KOK / f).write_bytes(y.read_bytes())
            if not sessiz:
                print(f"  geri yuklendi: {f}")
    UYGULANAN.unlink(missing_ok=True)


def artiklar() -> tuple[bool, bool, list[str], str]:
    """Onceki bir calismadan artik kalmis mi: (yedek, kilit, farkli dosyalar, not).

    Neden (16 Agu 2026 olayi - KK-41): harness istisnaya, SIGINT'e ve SIGTERM'e
    dayanikliydi ama SERT OLDURMEYE degil. Surec 32/163'te oldu; `finally`,
    `atexit` ve sinyal isleyicilerinin hicbiri calismadi ve `belge.py` enjekte
    edilmis halde kaldi. Kendi geri yuklemesi bir sonraki harness calismasinda
    devreye giriyordu - ama testleri kosturan, paketleyen ya da commit eden
    hicbir adim harness'i calistirmiyor. Yani artik, harness'tan BASKA hicbir
    yerden gorulmuyordu.

    Bu fonksiyon o boslugu kapatiyor: durum tespiti, onarimdan AYRI. CI ve
    paketleme oncesi `--kontrol` bunu cagirir ve kirli durumda kirmiziya doner;
    onarim yalnizca normal calismanin basinda yapilir.
    """
    yedek = YEDEK_DIZIN.exists()
    kilit = KILIT.exists()
    farkli = []
    if yedek:
        for f in DOSYALAR:
            y = YEDEK_DIZIN / pathlib.Path(f).name
            if y.exists() and y.read_bytes() != (KOK / f).read_bytes():
                farkli.append(f)
    not_ = UYGULANAN.read_text(encoding="utf-8") if UYGULANAN.exists() else ""
    return yedek, kilit, farkli, not_


def kilitle() -> bool:
    """Ayni anda iki harness calisamaz.

    Neden (14 Agu 2026, olay): iki harness yanlislikla ayni anda baslatildi.
    Biri dosyayi bozmusken oteki testleri kosturdu; ILGISIZ testler kirmiziya
    dondu ve iki koruma "KORUMASIZ" diye raporlandi. Daha kotusu, biri
    oldurulunce geri alma tamamlanmadi ve calisma dizininde enjekte edilmis bir
    dosya KALDI - sonraki testler onun uzerinde kosuyordu.
    """
    try:
        with open(KILIT, "x", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        print(f"  DURDU: baska bir enjeksiyon calismasi var gibi ({KILIT}).")
        print("  Calisan yoksa bu dosyayi silip tekrar dene.")
        return False


def kilidi_birak():
    KILIT.unlink(missing_ok=True)


def temizle():
    geri_al(sessiz=False)
    for x in YEDEK_DIZIN.glob("*"):
        x.unlink()
    if YEDEK_DIZIN.exists():
        YEDEK_DIZIN.rmdir()


def testler() -> list[str] | None:
    """Kirmizi test adlari; zaman asiminda `None` (bos liste DEGIL).

    Bos liste "hicbir test kirmiziya donmedi" demek, yani "koruma yok". Zaman
    asimi ise olcumun HIC yapilamadigi demek. Ikisini ayni degerle bildirmek,
    calisan bir korumayi KORUMASIZ diye raporlardi - `sozdizimi_gecerli` ile
    ayni ayrim (KK-10), ve KK-23'un "bos basari, gercek bos cevaptan ayirt
    edilemez" kuralinin harness'taki karsiligi.
    """
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider"],
            cwd=KOK, capture_output=True, env=ORTAM,
            encoding="utf-8", errors="replace", timeout=SURE_SINIRI,
        )
    except subprocess.TimeoutExpired:
        return None
    return [
        satir.split("::")[1].split()[0]
        for satir in (r.stdout or "").splitlines()
        if satir.startswith("FAILED")
    ]


ENJEKSIYONLAR = [
 ("Mali yili SEC'in fy alanindan al (ESKI HATAM)",
  "src/edgar_mcp/server.py",
  "            mali_yil, kaynak = takvim.yil(end)",
  "            mali_yil, kaynak = (row.get('fy') or takvim.yil(end)[0]), 'reported'",
  "test_donem_yili_bitis_tarihinden_gelir"),

 ("Donem uzunlugu filtresini kaldir (ceyreklik sizsin)",
  "src/edgar_mcp/server.py",
  "        return 300 <= days <= 400",
  "        return True",
  "test_ceyreklik_yillik_seriye_sizmaz"),

 ("Dedup anahtarina source_tag ekle (ayni donem cift sayilsin)",
  "src/edgar_mcp/server.py",
  "        k = (pt.period_end, pt.unit, _donem_kovasi(pt.days))",
  "        k = (pt.period_end, pt.unit, _donem_kovasi(pt.days), pt.source_tag)",
  "test_ortusen_donemde_en_son_sunulan_kazanir"),

 ("SEC User-Agent zorunlulugunu kaldir",
  "src/edgar_mcp/client.py",
  'if not ua or "@" not in ua:',
  'if False:',
  "test_ua_zorunlu"),

 ("Form turu filtresini kaldir (10-K istenince hepsi gelsin)",
  "src/edgar_mcp/server.py",
  "        if not _form_uyuyor(form, form_type):\n            continue",
  "        if False:\n            continue",
  "test_filings_filter"),

 ("list_filings: limit kirpmasini kaldir",
  "src/edgar_mcp/server.py",
  "        filings=dosyalamalar[:limit],",
  "        filings=dosyalamalar,",
  "test_filings_limit_uygulanir"),

 ("Takma ad haritasini bosalt (ISS-1 korumasi)",
  "src/edgar_mcp/server.py",
  '"revenue": [\n        "RevenueFromContractWithCustomerExcludingAssessedTax",',
  '"revenue": [\n        "YOK_OLAN_ETIKET",',
  "test_takma_ad_gercek_etikete_cozulur"),

 ("Takma ad fallback'ini kaldir (sadece ilk adayi dene)",
  "src/edgar_mcp/server.py",
  "adaylar = CONCEPT_ALIASES.get(anahtar, [concept.strip()])",
  "adaylar = [CONCEPT_ALIASES.get(anahtar, [concept.strip()])[-1]]",
  "test_takma_ad_gercek_etikete_cozulur"),

 ("Hata mesajindan takma ad listesini cikar (§18)",
  "src/edgar_mcp/server.py",
  'f"Try one of these aliases first: {ALIAS_LIST}. "',
  '""',
  "test_bilinmeyen_etiket_eyleme_donusturulebilir_hata_verir"),

 ("Kesif aracinin arama filtresini kaldir",
  "src/edgar_mcp/server.py",
  "if q and q not in tag.lower() and q not in (etiket or \"\").lower():",
  "if False:",
  "test_kesif_araci_arama_filtreler"),

 ("has_more'u sabit False yap (§16 sayfalama)",
  "src/edgar_mcp/server.py",
  "has_more=len(eslesen) > limit,",
  "has_more=False,",
  "test_kesif_araci_sayfalama_bilgisi_verir"),

 ("companyfacts onbellegini kaldir",
  "src/edgar_mcp/client.py",
  "if cik not in self._facts_cache:",
  "if True:",
  "test_companyfacts_bir_kez_cekilir"),

 ("Arac isim onegini dusur (IS-2)",
  "src/edgar_mcp/server.py",
  'name="sec_edgar_get_concept_series",',
  'name="get_concept_series",',
  "test_arac_isimleri_servis_onekli"),

 ("H-1: donemden SONRAKI capayi arama (kural: yil, yilin sonunda biter)",
  "src/edgar_mcp/server.py",
  "        sonraki = next(((e, fy) for e, fy in self.capalar if e > end), None)",
  "        sonraki = None if True else next(iter(self.capalar))",
  "test_takvim_baslangic_yiliyla_adlandiran_perakendeci"),

 ("H-1: capa yokken 'turetildi' de (yalan bayrak)",
  "src/edgar_mcp/server.py",
  "        return bool(self.capalar)",
  "        return True",
  "test_takvim_capa_yoksa_takvim_yili_ve_isaret"),

 ("H-1: ceyreklik satirlari da capa say",
  "src/edgar_mcp/server.py",
  "        if start and not (300 <= _gun_farki(start, end) <= 400):\n            continue",
  "        if False:\n            continue",
  "test_takvim_ceyreklik_satirlari_capa_saymaz"),

 ("H-2: ilk eslesen etikette dur (gecmisi kirp)",
  "src/edgar_mcp/server.py",
  "        v = await _ham_kayitlar(cik, tag)\n        if v is not None:\n            veriler.append((tag, v))",
  "        v = await _ham_kayitlar(cik, tag)\n        if v is not None:\n            veriler.append((tag, v))\n            break",
  "test_etiket_degisiminde_gecmis_kirpilmaz"),

 ("H-2: ortusen donemde eski kaydi tut",
  "src/edgar_mcp/server.py",
  "        kazanan, kaybeden = ((pt, mevcut) if sira(pt) > sira(mevcut)",
  "        kazanan, kaybeden = ((pt, mevcut) if sira(pt) < sira(mevcut)",
  "test_ortusen_donemde_en_son_sunulan_kazanir"),

 ("H-2: source_tag'i sabitle (kaynak izlenebilirligi)",
  "src/edgar_mcp/server.py",
  "                    source_tag=tag,",
  "                    source_tag='bilinmiyor',",
  "test_her_nokta_kaynak_etiketini_tasir"),

 ("Sir tarayici: sig klonu normal depo say (sessizce 'temiz' desin)",
  'arac/sir_tarama.py',
  'or "").strip() == "true":',
  'or "").strip() == "asla":',
  'test_sig_klon_temiz_demez'),

 ('Sir tarayici: gecmiste EKLENEN satir filtresini kaldir',
  'arac/sir_tarama.py',
  '        if not satir.startswith("+") or satir.startswith("+++"):',
  '        if True:',
  'test_eklenip_silinen_sir_gecmiste_yakalanir'),

 ('Sir tarayici: git deposu degilken hata yerine temiz don',
  'arac/sir_tarama.py',
  'return [], "git deposu degil (veya git kurulu degil)"',
  'return [], None',
  'test_git_olmayan_dizin_temiz_demez'),

 ('Sir tarayici: yer tutucu filtresini her seye uygula',
  'arac/sir_tarama.py',
  'return not (ad == "email" and any(a in deger for a in YOKSAY_ALAN))',
  'return False',
  'test_eklenip_silinen_sir_gecmiste_yakalanir'),


 ("Annotations: read_only_hint'i kaldir (§19 ipucu)",
  'src/edgar_mcp/server.py',
  '        read_only_hint=True,',
  '        read_only_hint=False,',
  'test_tum_araclar_salt_okunur_ilan_ediyor'),

 ("list_filings: has_more'u sabit False yap",
  'src/edgar_mcp/server.py',
  '        has_more=len(dosyalamalar) > limit or eksik_kaldi,',
  '        has_more=False,',
  'test_filings_sayfalama_bilgisi_verir'),

 ("list_filings: total_matching'i filtresiz say",
  'src/edgar_mcp/server.py',
  '        total_matching=len(dosyalamalar),',
  '        total_matching=len(r["accessionNumber"]),',
  'test_filings_sayfalama_filtreyle_birlikte_dogru'),

 ('Seri: en YENI yerine en ESKI donemleri dondur',
  'src/edgar_mcp/server.py',
  '    ordered = tumu[-limit:]',
  '    ordered = tumu[:limit]',
  'test_seri_kirpmada_EN_YENI_donemler_kalir'),

 ("Seri: has_more'u sabit False yap",
  'src/edgar_mcp/server.py',
  '        has_more=len(tumu) > len(ordered),',
  '        has_more=False,',
  'test_seri_sayfalama_bilgisi_verir'),

 ("Dockerfile: acik host'u kaldir (konteynerde loopback'e baglanir)",
  "Dockerfile",
  "mcp.run(transport='streamable-http', host='0.0.0.0', stateless_http=True)",
  "mcp.run(transport='streamable-http')",
  "test_dockerfile_loopback_disina_baglaniyor"),

 ("Belge: satir basi isaretlerine izni kaldir (tablo yerlesimi kaybolsun)",
  "src/edgar_mcp/belge.py",
  '_ONEK = r"^[\\s|>*\\-–—.]*"',
  '_ONEK = r"^\\s*"',
  "test_tablo_icindeki_basliklar_da_bulunuyor"),

 ("Belge: cevrilmis metin onbellegini kapat (her sayfada yeniden ayristir)",
  "src/edgar_mcp/server.py",
  "    if url in _BELGE_METNI:",
  "    if False:",
  "test_belge_metne_bir_kez_cevriliyor"),

 ("Belge: bolum listesini tekillestirme (ayni kod iki kez cikssin)",
  "src/edgar_mcp/belge.py",
  "    return sorted(en_uzun.values(), key=lambda b: b[1])",
  "    return gecerli",
  "test_bolum_listesi_ayni_kodu_bir_kez_veriyor"),

 ("Belge: tekillestirmede EN UZUN yerine ilkini tut",
  "src/edgar_mcp/belge.py",
  "        if k not in en_uzun or (b[2] - b[1]) > (en_uzun[k][2] - en_uzun[k][1]):",
  "        if k not in en_uzun:",
  "test_ayni_baslik_iki_kez_gecerse_ASIL_bolum_secilir"),

 ("Belge: gizli iXBRL blogunu metne al (ad alani gurultusu)",
  "src/edgar_mcp/belge.py",
  "        gizli = tag in _ATLANAN or (self._gizliyi_atla and _gizli_mi(attrs))",
  "        gizli = tag in _ATLANAN",
  "test_gizli_ixbrl_blogu_metne_girmiyor"),

 ("Belge: icindekiler tablosu esigini kaldir (TOC bolum sayilsin)",
  "src/edgar_mcp/belge.py",
  "BOLUM_ESIGI = 400",
  "BOLUM_ESIGI = 0",
  "test_icindekiler_tablosu_bolum_sanilmiyor"),

 ("Belge: ayni baslikta ILK eslesmeyi al (asil bolum yerine ozet)",
  "src/edgar_mcp/belge.py",
  "    return max(eslesen, key=lambda b: b[2] - b[1])",
  "    return eslesen[0]",
  "test_alt_dize_aramasinda_en_uzun_bolum_kazanir"),

 ("Belge: script/style atlamayi kapat (govde metne sizsin)",
  "src/edgar_mcp/belge.py",
  "        gizli = tag in _ATLANAN or (self._gizliyi_atla and _gizli_mi(attrs))",
  "        gizli = (self._gizliyi_atla and _gizli_mi(attrs))",
  "test_script_ve_stil_metne_karismiyor"),

 ("Belge: sayfalamayi kaldir (tum belgeyi don)",
  "src/edgar_mcp/server.py",
  "    parca = metin[offset:offset + max_characters]",
  "    parca = metin[offset:]",
  "test_belge_metni_sayfalaniyor"),

 ("Taksonomi onekini yoksay (her etiketi us-gaap'ta ara)",
  "src/edgar_mcp/server.py",
  '        tax, _, ad = tag.partition(":")',
  '        tax, _, ad = "us-gaap", None, tag',
  "test_takma_ad_dei_taksonomisine_gidebiliyor"),

 ("Kesif araci: mevcut taksonomileri sabit us-gaap raporla",
  "src/edgar_mcp/server.py",
  "    mevcut = list(tumu)",
  '    mevcut = ["us-gaap"]',
  "test_kesif_araci_taksonomileri_kendisi_bildiriyor"),

 ("Revizyon: ayni donemin eski degerlerini at (seri gibi dedup et)",
  "src/edgar_mcp/server.py",
  "                gruplar.setdefault(\n                    (tag, end, birim, _donem_kovasi(days)), []\n                ).append(",
  "                gruplar.setdefault(\n                    (tag, end, birim, _donem_kovasi(days)), []\n                ).clear() or gruplar[(tag, end, birim, _donem_kovasi(days))].append(",
  "test_revizyon_degisen_degeri_yakalar"),

 ("Revizyon: tekrarlanan ayni degeri de farkli deger say",
  "src/edgar_mcp/server.py",
  "            if deger in gorulen:",
  "            if False:",
  "test_revizyon_ayni_degerin_tekrari_revizyon_sayilmaz"),

 ("Revizyon: only_revised filtresini etkisiz birak",
  "src/edgar_mcp/server.py",
  "        revizyonlar = [r for r in revizyonlar if r.distinct_values > 1]",
  "        revizyonlar = list(revizyonlar)",
  "test_revizyon_varsayilan_olarak_sadece_revize_donemleri_verir"),

 ("Kullanilamaz birim govdesini (SEC'in {} yaniti) normal say",
  "src/edgar_mcp/server.py",
  "        if isinstance(satirlar, list)",
  "        if True",
  "test_liste_olmayan_birim_govdesi_cokertmez"),

 ("KO olayi: bos companyconcept yanitinda yedek uca dusme",
  "src/edgar_mcp/server.py",
  'veriler, kaynak_uc = yedek, "companyfacts"',
  'pass',
  "test_bos_companyconcept_yanitinda_companyfacts_e_dusulur"),

 ("KO olayi: yedek uc her cagride cekilsin (5 MB bosuna)",
  "src/edgar_mcp/server.py",
  "if veriler and _satir_sayisi(veriler) == 0:",
  "if veriler:",
  "test_normal_durumda_companyfacts_cekilmez"),

 ("KO olayi: iki uc da bossa hata yerine bos basari don",
  "src/edgar_mcp/server.py",
  "if son_satir == 0:",
  "if False:",
  "test_iki_uc_da_bossa_sessiz_basari_yerine_hata"),

 ("Hata mesajini Turkceye cevir (semada gorunmeyen yuzey)",
  "src/edgar_mcp/client.py",
  'f"Ticker \'{ticker}\' is not in SEC\'s company_tickers.json. "',
  'f"Ticker bulunamadi: {ticker}. "',
  "test_hata_mesajlari_ingilizce"),

 ("Parametre aciklamasini Turkceye cevir (disa bakan yuzey)",
  "src/edgar_mcp/server.py",
  '"US-GAAP tag (e.g. NetIncomeLoss). Call "',
  '"US-GAAP etiketi (orn. NetIncomeLoss). Cagir "',
  "test_arac_tanimlari_ingilizce"),

 ("Donus semasi alan aciklamasini Turkceye cevir",
  "src/edgar_mcp/server.py",
  '"US-GAAP tag this value was reported under"',
  '"Bu degerin raporlandigi US-GAAP etiketi"',
  "test_arac_tanimlari_ingilizce"),

 ("CIK sifir dolgusunu kaldir",
  "src/edgar_mcp/client.py",
  'str(row["cik_str"]).zfill(10)',
  'str(row["cik_str"])',
  "test_profile"),

 # ---- B1: dosyalama icindeki dosya listesi (8-K ekleri)
 ("Okunamayan uzantilari da dosya listesine koy",
  "src/edgar_mcp/server.py",
  "        if not ad.lower().endswith(OKUNABILIR_UZANTILAR):\n            continue\n",
  "        if False:\n            continue\n",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("Gezinme sayfasi (index-*) elemesini kaldir",
  "src/edgar_mcp/server.py",
  '        if "index" in ad.lower():',
  "        if False:",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("Dosya siralamasini ters cevir (kucukten buyuge)",
  "src/edgar_mcp/server.py",
  "    out.sort(key=lambda b: (b.size_bytes or 0), reverse=True)",
  "    out.sort(key=lambda b: (b.size_bytes or 0), reverse=False)",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("XBRL goruntuleyici ciktilarini (R1.htm) elemeyi kaldir",
  "src/edgar_mcp/server.py",
  "        if _URETILEN_RAPOR.match(ad):",
  "        if False:",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("Birincil belge bayragini hep False birak",
  "src/edgar_mcp/server.py",
  "            is_primary=(ad == birincil),",
  "            is_primary=False,",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("document parametresini yoksay (hep birincil belgeyi oku)",
  "src/edgar_mcp/server.py",
  "    ad = document or birincil",
  "    ad = birincil",
  "test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor"),

 ("Olmayan belge adini dogrulamadan gec",
  "src/edgar_mcp/server.py",
  "    if document and not any(b.name == document for b in belgeler):",
  "    if False and not any(b.name == document for b in belgeler):",
  "test_olmayan_belge_adi_eyleme_donusturulebilir_hata_verir"),

 ("Belge hatasi mevcut dosyalari listelemesin",
  "src/edgar_mcp/server.py",
  '            f"This filing has no readable file named \'{document}\'. It has: "\n'
  '            f"{\', \'.join(b.name for b in belgeler) or \'none\'}."',
  '            f"This filing has no readable file named \'{document}\'."',
  "test_olmayan_belge_adi_eyleme_donusturulebilir_hata_verir"),

 ("Dizin listesi onbellegini kapat (her cagride yeniden iste)",
  "src/edgar_mcp/client.py",
  "        if url not in self._index_cache:",
  "        if True:",
  "test_ayni_belge_iki_kez_indirilmiyor"),

 # ---- B2: dosyalama ici arama
 ("Arama toplam sayacini durdur (kirpilmis liste toplam sanilsin)",
  "src/edgar_mcp/server.py",
  "        toplam += 1",
  "        toplam += 0",
  "test_arama_vurgu_sayisi_sinirli_ama_toplam_dogru"),

 ("Arama vurgu kirpmasini kaldir (yaniti sisir)",
  "src/edgar_mcp/server.py",
  "        if len(vurgular) < ARAMA_VURGU_SINIRI:",
  "        if True:",
  "test_arama_vurgu_sayisi_sinirli_ama_toplam_dogru"),

 # ---- B3: sirketler arasi karsilastirma (frames)
 ("B3: suresel/anlik es cercevesini deneme",
  "src/edgar_mcp/server.py",
  "    for aday in (cerceve, _cerceve_esi(cerceve)):",
  "    for aday in (cerceve,):",
  "test_cerceve_bilanco_kaleminde_anlik_esine_dusuyor"),

 ("B3: sira numarasini filtreden SONRA say",
  "src/edgar_mcp/server.py",
  "                rank=i,",
  "                rank=len(secilenler) + 1,",
  "test_cerceve_filtrelense_de_sira_tum_sirketlere_gore"),

 ("B3: cercevede olmayan tickeri sessizce dusur",
  "src/edgar_mcp/server.py",
  "            ad for cik, adlar in istenen.items() if cik not in gorulen",
  "            ad for cik, adlar in istenen.items() if False",
  "test_cerceve_istenen_ticker_yoksa_sessizce_dusmuyor"),

 ("B3: donem araligini tek noktaya cokert",
  "src/edgar_mcp/server.py",
  'period_end_earliest=bitisler[0] if bitisler else "",',
  'period_end_earliest=bitisler[-1] if bitisler else "",',
  "test_cerceve_donem_bitisleri_ayni_degil_ve_bu_gorunuyor"),

 ("B3: cerceve onbellegini kapat",
  "src/edgar_mcp/server.py",
  "        if anahtar in _CERCEVE:",
  "        if False:",
  "test_cerceve_ikinci_kez_indirilmiyor"),

 ("B3: bos cerceveyi sessiz basari say",
  "src/edgar_mcp/server.py",
  "    if not satirlar:",
  "    if False:",
  "test_cerceve_bos_data_sessiz_basari_olmuyor"),

 ("B3: donem yazimini katilastir (yalniz CY... kabul et)",
  "src/edgar_mcp/server.py",
  r'_CERCEVE_KALIBI = re.compile(r"^(?:cy)?\s*(\d{4})\s*(?:[-_ ]?q([1-4]))?\s*(i?)$",',
  r'_CERCEVE_KALIBI = re.compile(r"^cy(\d{4})(?:q([1-4]))?(i?)$",',
  "test_cerceve_donem_yazimi_serbest"),

 ("B3: siralama yonunu yoksay",
  "src/edgar_mcp/server.py",
  "reverse=ters)",
  "reverse=True)",
  "test_cerceve_artan_siralamada_sira_numarasi_da_donuyor"),

 ("B3: limit kirpmasini kaldir",
  "src/edgar_mcp/server.py",
  "        if len(secilenler) >= limit:",
  "        if False:",
  "test_cerceve_degere_gore_siraliyor_ve_kirpmayi_bildiriyor"),

 ("B3: CIK -> ticker cozumunu kapat",
  "src/edgar_mcp/client.py",
  "        return eslesen[0] if eslesen else None",
  "        return None",
  "test_cerceve_tickeri_olmayan_sirket_cokmeye_yol_acmiyor"),

 # ---- C: boyutlu XBRL
 ("C: scenario icindeki boyutlari gormezden gel",
  "src/edgar_mcp/xbrl.py",
  'for kapsayici in (f".//{{{INSTANCE_NS}}}segment", f".//{{{INSTANCE_NS}}}scenario"):',
  'for kapsayici in (f".//{{{INSTANCE_NS}}}segment",):',
  "test_boyut_kesfi_eksenleri_ve_uyeleri_listeliyor"),

 ("C: typed dimension'lari dusur",
  "src/edgar_mcp/xbrl.py",
  "            for uye in kap.findall(f\"{{{XBRLDI_NS}}}typedMember\"):",
  "            for uye in []:",
  "test_typed_dimension_dusurulmuyor"),

 ("C: uye metnindeki bosluklari temizleme",
  "src/edgar_mcp/xbrl.py",
  "    return \" \".join(e.text.split()) or None",
  "    return e.text or None",
  "test_segment_kirilimi_geliyor_ve_kaynagina_kadar_izlenebiliyor"),

 ("C: pay/payda birimini okuma",
  "src/edgar_mcp/xbrl.py",
  '    bol = e.find(f"{{{INSTANCE_NS}}}divide")',
  "    bol = None",
  "test_pay_bolu_payda_birimi_okunuyor"),

 ("C: nil fact'i normal deger say",
  "src/edgar_mcp/xbrl.py",
  'nil=(veri.get(f"{{{XSI_NS}}}nil") or "").lower() == "true",',
  "nil=False,",
  "test_sayisal_olmayan_ve_nil_fact_sessizce_sayiya_cevrilmiyor"),

 ("C: sayisal olmayan degeri de sayiya cevirmeye calis",
  "src/edgar_mcp/server.py",
  "            value=float(o.deger) if sayi_mi(o.deger) and o.deger else None,",
  "            value=None,",
  "test_segment_kirilimi_geliyor_ve_kaynagina_kadar_izlenebiliyor"),

 ("C: cok boyutlu fact'i de toplama kat (cift sayim)",
  "src/edgar_mcp/server.py",
  "        if len(f.dimensions) != 1:",
  "        if False:",
  "test_cok_boyutlu_fact_toplamaya_girmiyor"),

 ("C: nil fact'i toplama kat",
  "src/edgar_mcp/server.py",
  "        if o.tag != etiket or not sayi_mi(o.deger) or o.nil:",
  "        if o.tag != etiket:",
  "test_raporlanmayan_toplam_sifir_sanilmiyor"),

 ("C: eksen verilmeden de mutabakat hesapla",
  "src/edgar_mcp/server.py",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, eksen_kumesi) if axis else [],",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, eksen_kumesi),",
  "test_eksen_verilmezse_mutabakat_hesaplanmiyor"),

 ("C: linkbase dosyasini instance sanmayi engelleyen filtreyi kaldir",
  "src/edgar_mcp/server.py",
  "        if ad.lower().endswith(\".xml\") and not _LINKBASE.search(ad) \\",
  "        if ad.lower().endswith(\".xml\") and not None \\",
  "test_inline_oncesi_dosyalamada_dosyalayanin_instance_i_okunuyor"),

 ("C: instance onbellegini kapat",
  "src/edgar_mcp/server.py",
  "    if url not in _INSTANCE:",
  "    if True:",
  "test_instance_ikinci_kez_indirilmiyor"),

 ("C: XBRL'siz dosyalamada sessizce bos don",
  "src/edgar_mcp/server.py",
  '    raise ValueError(\n        "This filing has no XBRL instance document',
  '    return ""\n    raise ValueError(\n        "This filing has no XBRL instance document',
  "test_xbrl_tasimayan_dosyalamada_eyleme_donusturulebilir_hata"),

 ("C: bozuk XML'i cig traceback olarak birak",
  "src/edgar_mcp/xbrl.py",
  "    except ET.ParseError as e:",
  "    except ZeroDivisionError as e:",
  "test_bozuk_instance_cig_traceback_yerine_eyleme_donusturulebilir_hata"),

 # ---- 15 Agu 2026 denetimi
 ("D: gizli yigini eski (tepe-eslesme) haline dondur",
  "src/edgar_mcp/belge.py",
  "        if self._kapat(tag) and not self._atla and tag in _BLOK:",
  "        if self._yigin and self._yigin[-1][0] == tag and self._atla:\n            self._yigin.pop()\n            self._atla -= 1\n        elif tag in _BLOK:",
  "test_gizli_blok_kapanmayan_etikette_belgeyi_yutmuyor"),

 ("D: kapanmayan elemanlari da yigina koy",
  "src/edgar_mcp/belge.py",
  "        if tag in _KAPANMAYAN:\n            if tag == \"br\" and not self._atla:",
  "        if False:\n            if tag == \"br\" and not self._atla:",
  "test_gizli_blok_kapanmayan_etikette_belgeyi_yutmuyor"),

 ("D: ortulu kapanislari uygulama",
  "src/edgar_mcp/belge.py",
  "        for kapanacak in _ORTULU_KAPANIS.get(tag, ()):",
  "        for kapanacak in ():",
  "test_gizli_blok_kapanmayan_etikette_belgeyi_yutmuyor"),

 ("D: yutma emniyet agini kaldir",
  "src/edgar_mcp/belge.py",
  "    if (gizliyi_atla and len(govde) >= _YUTMA_TABANI",
  "    if (False and len(govde) >= _YUTMA_TABANI",
  "test_gizli_filtresi_belgeyi_yutarsa_filtresiz_donuyor"),

 ("D: mutabakati yine sayfa uzerinden hesapla",
  "src/edgar_mcp/server.py",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, eksen_kumesi) if axis else [],",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, secilen) if axis else [],",
  "test_mutabakat_sayfalama_sinirindan_etkilenmiyor"),

 ("D: disarida birakilanlari raporlama",
  "src/edgar_mcp/server.py",
  "            excluded_from_sum=disarida.get(k, {}),",
  "            excluded_from_sum={},",
  "test_mutabakat_disarida_biraktiklarini_sayiyor"),

 ("D: en son degeri yine ilk-gorulme sirasindan al",
  "src/edgar_mcp/server.py",
  '        son = float(satirlar[-1]["val"])',
  "        son = sirali_degerler[-1]",
  "test_revizyon_geri_alinan_degerde_seriyle_celismiyor"),

 ("D: anlik kayitlari yillik filtreden oldugu gibi gecir",
  "src/edgar_mcp/server.py",
  "        if ay_gun is None or not end:\n            return True          # capa yok: eleyecek olcut de yok",
  "        return True\n        if ay_gun is None or not end:\n            return True",
  "test_yillik_seri_ceyrek_sonu_bakiyeleri_icermiyor"),

 ("D: ceyreklik filtresinde anlik kayitlari yine ele",
  "src/edgar_mcp/server.py",
  "    if days is None:\n        if period != \"annual\":\n            return True",
  "    if days is None:\n        if period == \"quarterly\":\n            return False\n        if period != \"annual\":\n            return True",
  "test_ceyreklik_seri_anlik_kalemi_bos_dondurmuyor"),

 ("D: ust-kaynak hata mesajini cig birak",
  "src/edgar_mcp/client.py",
  "        if r.status_code >= 400:\n            raise ValueError(_durum_mesaji(r.status_code, url))",
  "        if r.status_code >= 400:\n            r.raise_for_status()",
  "test_ust_kaynak_hatasi_eyleme_donusturulebilir"),

 ("D: JSON olmayan govdeyi cig JSONDecodeError birak",
  "src/edgar_mcp/client.py",
  "        except ValueError as e:\n            bas = (r.text or \"\").lstrip()[:60].replace(\"\\n\", \" \")",
  "        except ZeroDivisionError as e:\n            bas = (r.text or \"\").lstrip()[:60].replace(\"\\n\", \" \")",
  "test_json_yerine_html_gelirse_soyleniyor"),

 ("D: ayni CIK'te ikinci sembolu yine ez",
  "src/edgar_mcp/server.py",
  "            istenen.setdefault((await _kimlik_coz(t))[0], []).append(t.strip().upper())",
  "            istenen[(await _kimlik_coz(t))[0]] = [t.strip().upper()]",
  "test_ayni_cik_iki_sembol_tasiyorsa_ikisi_de_gorunuyor"),

 ("D: recent disindaki dosyalamalari yok say",
  "src/edgar_mcp/server.py",
  '    daha_eski = bool(sub.get("filings", {}).get("files"))',
  "    daha_eski = False",
  "test_recent_akisinin_disindaki_dosyalamalar_bildiriliyor"),

 ("D: sunucu ortam degiskeni olmadan da acilsin",
  "src/edgar_mcp/server.py",
  "    _c()\n    mcp.run(transport=\"stdio\")",
  '    mcp.run(transport="stdio")',
  "test_main_kullanici_ajani_olmadan_baslamayi_reddediyor"),

 ("D: companyfacts onbellegini yine sinirsiz birak",
  "src/edgar_mcp/client.py",
  "            self._sinirla(self._facts_cache, cik, await self._get(\n                f\"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json\"), 2)",
  "            self._facts_cache[cik] = await self._get(\n                f\"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json\")",
  "test_onbellekler_sinirli"),

 ("D: takma adin tum etiketlerini yine kabul et (cift sayim)",
  "src/edgar_mcp/server.py",
  "        if not cozulen_etiket or o.tag != cozulen_etiket:",
  "        if not _etiket_uyuyor(o.tag, adaylar):",
  "test_takma_ad_boyutlu_fact_te_cift_saymiyor"),

 ("E: ilerleme bildirimini sessizce yut",
  "src/edgar_mcp/server.py",
  "    if ctx is not None:\n        await ctx.report_progress(adim, toplam, mesaj)",
  "    if False:\n        await ctx.report_progress(adim, toplam, mesaj)",
  "test_uzun_suren_araclar_ilerleme_bildiriyor"),

 ("E: belge indirme adimini bildirme",
  "src/edgar_mcp/server.py",
  '    await _ilerleme(ctx, 1, 3, f"Downloading {ad}")',
  "    pass",
  "test_uzun_suren_araclar_ilerleme_bildiriyor"),

 # ---- Ikinci denetim turu (15 Agu 2026 aksami)
 ("F: ortulu kapanislari yine kume yap + ilkinde dur",
  "src/edgar_mcp/belge.py",
  '    "tr": ("td", "th", "tr"),',
  '    "tr": ("td",),',
  "test_metin_cikarimi_surecten_surece_ayni_sonucu_veriyor"),

 ("F: gizli blok icinde ayirici uret",
  "src/edgar_mcp/belge.py",
  "        if self._atla:\n            pass\n        elif tag in (\"td\", \"th\"):",
  "        if False:\n            pass\n        elif tag in (\"td\", \"th\"):",
  "test_gizli_blok_icinde_ayirici_uretilmiyor"),

 ("F: anlik sinirinda komsu yillari deneme (52/53 haftalik takvim)",
  "src/edgar_mcp/server.py",
  "        for aday_yil in (hedef, hedef - 1, hedef + 1):",
  "        for aday_yil in (hedef,):",
  "test_yil_sonu_aralik_ocak_arasinda_oynayan_takvim"),

 ("F: mutabakati yine uye-filtreli kume uzerinden hesapla",
  "src/edgar_mcp/server.py",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, eksen_kumesi) if axis else [],",
  "        reconciliation=_mutabakat(inst, cozulen_etiket, tumu) if axis else [],",
  "test_uye_filtresi_mutabakati_bozmuyor"),

 ("F: belge indirmede durum kontrolunu atla",
  "src/edgar_mcp/client.py",
  "        self._durumu_kontrol_et(r, url)\n        govde = r.text or \"\"",
  '        r.raise_for_status()\n        govde = r.text or ""',
  "test_belge_indirmede_403_eyleme_donusturulebilir"),

 ("F: 200 ile gelen engel sayfasini dosyalama metni say",
  "src/edgar_mcp/client.py",
  "        if _engel_sayfasi_mi(govde):",
  "        if False:",
  "test_200_ile_gelen_engel_sayfasi_dosyalama_metni_sanilmiyor"),

 ("G: eski akislari okumayi sessizce atla",
  "src/edgar_mcp/server.py",
  "    if not eski_dahil:\n        return kayitlar, 0",
  "    if True:\n        return kayitlar, 0",
  "test_eski_akis_include_older_ile_birlesiyor"),

 ("G: birlesik listeyi tarihe gore siralama",
  "src/edgar_mcp/server.py",
  "    kayitlar.sort(key=lambda f: f.filing_date, reverse=True)",
  "    pass",
  "test_eski_akis_include_older_ile_birlesiyor"),

 ("G: okunmayan eski akis sayisini sifir bildir",
  "src/edgar_mcp/server.py",
  "    return kayitlar, max(0, len(dosyalar) - len(okunacak))",
  "    return kayitlar, 0",
  "test_eski_akis_siniri_sessiz_degil"),

 ("G: form karsilastirmasini yine harfe duyarli yap",
  "src/edgar_mcp/server.py",
  "    return not istenen or form.upper() == istenen.upper()",
  "    return not istenen or form == istenen",
  "test_form_filtresi_buyuk_kucuk_harf_duyarsiz"),

 ("G: ek akislari ana submissions onbellegine koy",
  "src/edgar_mcp/client.py",
  "        if ad not in self._extra_cache:\n            self._sinirla(self._extra_cache, ad,\n"
  "                          await self._get(f\"{SEC_DATA}/submissions/{ad}\"), 4)\n"
  "        return self._extra_cache[ad]",
  "        if ad not in self._subs_cache:\n            self._sinirla(self._subs_cache, ad,\n"
  "                          await self._get(f\"{SEC_DATA}/submissions/{ad}\"), 4)\n"
  "        return self._subs_cache[ad]",
  "test_eski_akis_ana_submissions_onbellegini_atmiyor"),

 ("G: metin araci yine yalnizca recent akisina baksin",
  "src/edgar_mcp/server.py",
  "    dosyalar = list(sub.get(\"filings\", {}).get(\"files\") or [])[:EK_AKIS_SINIRI]",
  "    dosyalar = []",
  "test_metin_araci_eski_akistaki_dosyalamayi_okuyabiliyor"),

 ("G: birincil belge bilinmezken bilinir gibi bildir",
  "src/edgar_mcp/server.py",
  "        primary_document_known=bool(birincil),",
  "        primary_document_known=True,",
  "test_metin_araci_eski_akistaki_dosyalamayi_okuyabiliyor"),

 ("H: arama vurusunun belge adini erisim numarasindan ayirma",
  "src/edgar_mcp/server.py",
  "        acc, _, belge = str(vurus.get(\"_id\") or \"\").partition(\":\")",
  "        acc, belge = str(vurus.get(\"_id\") or \"\"), \"\"",
  "test_arama_vurusu_okunabilir_adrese_cevriliyor"),

 ("H: alt sinir sayisini kesin say",
  "src/edgar_mcp/server.py",
  "        kesin = str(sayac.get(\"relation\") or \"eq\") == \"eq\"",
  "        kesin = True",
  "test_arama_alt_sinir_kesin_sayi_gibi_sunulmuyor"),

 ("H: bos sonucta kapsam notunu sus",
  "src/edgar_mcp/server.py",
  "    if not kayitlar:\n        not_ = _KAPSAM_YOK",
  "    if False:\n        not_ = _KAPSAM_YOK",
  "test_arama_bos_sonucta_kapsam_notu_veriyor"),

 ("H: hata govdesini bos sonuc say",
  "src/edgar_mcp/server.py",
  "    if not isinstance(kume, dict):",
  "    if False:",
  "test_arama_hata_govdesi_bos_sonuc_sanilmiyor"),

 ("H: tarih dogrulamasini kaldir (SEC sessizce yok sayar)",
  "src/edgar_mcp/server.py",
  "    if not _ISO_TARIH.match(d):",
  "    if False:",
  "test_arama_gecersiz_tarih_sessizce_yok_sayilmiyor"),

 ("H: ticker cozulemeyen vurusu at",
  "src/edgar_mcp/server.py",
  "        kayitlar.append(SearchedDocument(",
  "        if not cik or not cik.startswith(\"000131\"):\n            continue\n        kayitlar.append(SearchedDocument(",
  "test_arama_ticker_cozulemeyen_vurusu_gizlemiyor"),

 ("J: .env okurken BOM'u yutma",
  "arac/ortam.py",
  '        metin = yol.read_text(encoding="utf-8-sig")',
  '        metin = yol.read_text(encoding="utf-8")',
  "test_env_yukleyici_bom_lu_dosyayi_okuyor"),

 ("J: dotenv yoksa yine sessizce gec",
  "arac/ortam.py",
  "    except ImportError:\n        pass\n    else:",
  "    except ImportError:\n        return\n    else:",
  "test_env_yukleyici_bagimlilik_olmadan_da_yukluyor"),

 ("J: .env kabuktaki degiskeni ezsin",
  "arac/ortam.py",
  "            os.environ.setdefault(cift[0], cift[1])",
  "            os.environ[cift[0]] = cift[1]",
  "test_env_yukleyici_mevcut_degiskeni_ezmiyor"),

 ("L: tek tarafli tarih araligini oldugu gibi gonder",
  "src/edgar_mcp/server.py",
  "    return (bas or EDGAR_BASLANGICI), (son or date.today().isoformat())",
  "    return bas, son",
  "test_tek_tarafli_tarih_araligi_tamamlaniyor"),

 ("L: tarih verilmeden de aralik gonder",
  "src/edgar_mcp/server.py",
  "    if not bas and not son:\n        return None, None",
  "    if False:\n        return None, None",
  "test_tarih_verilmediginde_aralik_uydurulmuyor"),

 ("L: uygulanan araligi bildirme",
  "src/edgar_mcp/server.py",
  '        date_range_applied=f"{bas}..{son}" if bas and son else None,',
  "        date_range_applied=None,",
  "test_tek_tarafli_tarih_araligi_tamamlaniyor"),

 ("M: CIK girdisini ticker sayip aramaya git",
  "src/edgar_mcp/client.py",
  '        m = re.fullmatch(r"(?:cik)?[\\s-]*0*(\\d{1,10})", s, re.IGNORECASE)',
  "        m = None",
  "test_cik_ile_adresleme_calisiyor"),

 ("M: CIK ile sorulunca sembolu girdiden uydur",
  "src/edgar_mcp/server.py",
  "        return cik, await c.ticker_for_cik(cik)",
  "        return cik, (deger or \"\").strip().upper()",
  "test_cik_ile_adresleme_calisiyor"),

 ("M: bilinmeyen CIK'te cig HTTP hatasi birak",
  "src/edgar_mcp/client.py",
  "                if e.response.status_code == 404:\n                    raise ValueError(\n                        f\"SEC has no filer with CIK {cik}.",
  "                if False:\n                    raise ValueError(\n                        f\"SEC has no filer with CIK {cik}.",
  "test_bilinmeyen_cik_eyleme_donusturulebilir_hata"),

 ("N: Form 4 kod anlamlarini dusur",
  "src/edgar_mcp/server.py",
  "                code_meaning=ISLEM_KODLARI.get(i.code or \"\"),",
  "                code_meaning=None,",
  "test_form4_islemleri_kod_anlamiyla_donuyor"),

 ("N: turev satirlarini varsayilan olarak da don",
  "src/edgar_mcp/server.py",
  "            if i.is_derivative and not include_derivative:\n                continue",
  "            if False:\n                continue",
  "test_form4_turev_satirlari_varsayilan_olarak_disarida"),

 ("N: pozisyon bildirimini islem say",
  "src/edgar_mcp/server.py",
  "            if i.is_holding and not include_holdings:\n                continue",
  "            if False:\n                continue",
  "test_form4_pozisyon_bildirimi_islem_sanilmiyor"),

 ("N: pozisyon satirini kod toplamina kat",
  "src/edgar_mcp/server.py",
  "        if t.shares is None:\n            continue",
  "        if False:\n            continue",
  "test_form4_pozisyon_bildirimi_islem_sanilmiyor"),

 ("N: stil onekini soyma (styled kopyayi indir)",
  "src/edgar_mcp/server.py",
  "    return _STIL_ONEKI.sub(\"\", birincil or \"\")",
  "    return birincil or \"\"",
  "test_form4_stil_onekli_yol_ham_xml_e_cevriliyor"),

 ("N: Form 4 sarmalayicisini atlayip eleman metnini oku",
  "src/edgar_mcp/sahiplik.py",
  "    v = c.find(\"value\")\n    metin = (v.text if v is not None else c.text) or \"\"",
  "    metin = c.text or \"\"",
  "test_form4_islemleri_kod_anlamiyla_donuyor"),

 ("O: 13F satirlarini birlestirme (ayni ihracci ayri satirlarda kalsin)",
  "src/edgar_mcp/server.py",
  "        mevcut = birlesik.get(anahtar)",
  "        mevcut = None",
  "test_13f_ayni_ihraccinin_satirlari_birlestiriliyor"),

 ("O: 13F birim sinirini yoksay (2023 oncesini de tam dolar say)",
  "src/edgar_mcp/server.py",
  "    bin_mi = kayit[\"filing_date\"] < BIRIM_SINIRI",
  "    bin_mi = False",
  "test_13f_2023_oncesi_deger_bin_dolar_olarak_isaretleniyor"),

 ("O: 13F kapak toplamini dusur",
  "src/edgar_mcp/server.py",
  "        reported_value_total=(kapak.table_value_total * carpan\n                              if kapak.table_value_total is not None else None),",
  "        reported_value_total=None,",
  "test_13f_kapak_sayfasi_ve_tablo_ayri_ayri_bildiriliyor"),

 ("O: 13F bilgi tablosunu adiyla tahmin et",
  "src/edgar_mcp/server.py",
  "    veri = await _c().filing_index(dizin)\n    adaylar = [str(x.get(\"name\", \"\"))",
  "    veri = {}\n    adaylar = [str(x.get(\"name\", \"\"))",
  "test_13f_bilgi_tablosu_dizinden_bulunuyor"),

 ("O: 13F ad alanini yoksay (oneksiz eleman ara)",
  "src/edgar_mcp/sahiplik.py",
  "        c = e.find(f\"{{{BILGI_TABLOSU_NS}}}{ad}\")\n        if c is None:\n            c = e.find(ad)",
  "        c = e.find(ad)",
  "test_13f_ayni_ihraccinin_satirlari_birlestiriliyor"),

 ("K: tablolari her cagride don (parametreyi yoksay)",
  "src/edgar_mcp/server.py",
  "               if offset <= t.baslangic < offset + len(parca)] if tables else []",
  "               if offset <= t.baslangic < offset + len(parca)]",
  "test_tablolar_istenmedikce_donmuyor"),

 ("K: tablo penceresini yoksay (hepsini don)",
  "src/edgar_mcp/server.py",
  "    pencere = [t for t in tum_tablolar\n               if offset <= t.baslangic < offset + len(parca)] if tables else []",
  "    pencere = list(tum_tablolar) if tables else []",
  "test_tablolar_sayfalama_penceresiyle_sinirli"),

 ("K: bolum kesilince tablo konumunu kaydirma",
  "src/edgar_mcp/server.py",
  "        tum_tablolar = [_tabloyu_kaydir(t, vurus[1]) for t in tum_tablolar\n                        if vurus[1] <= t.baslangic < vurus[2]]",
  "        tum_tablolar = [t for t in tum_tablolar\n                        if vurus[1] <= t.baslangic < vurus[2]]",
  "test_bolum_secilince_tablo_konumu_bolume_gore"),

 ("K: yerlesim tablolarini sessizce dusur",
  "src/edgar_mcp/server.py",
  "        layout_tables_skipped=cikti.yerlesim_tablolari if tables else 0,",
  "        layout_tables_skipped=0,",
  "test_yerlesim_tablosu_sessizce_dusurulmuyor"),

 ("K: gizli bloktaki tabloyu da topla",
  "src/edgar_mcp/belge.py",
  "        elif not self._atla:\n            # Gizli bir blogun icindeki tablo toplanmiyor",
  "        elif True:\n            # Gizli bir blogun icindeki tablo toplanmiyor",
  "test_gizli_bloktaki_tablo_yapiya_da_girmiyor"),

 ("K: satir sinirini sessizce uygula",
  "src/edgar_mcp/belge.py",
  "        t.kirpildi = len(dolu) > SATIR_SINIRI",
  "        t.kirpildi = False",
  "test_uzun_tablo_kirpiliyor_ve_bunu_soyluyor"),

 ("K: hucre kirpmasini sessizce uygula",
  "src/edgar_mcp/belge.py",
  "            self.hucre_kirpildi = True",
  "            self.hucre_kirpildi = False",
  "test_uzun_hucre_kirpiliyor_ve_bunu_soyluyor"),

 ("K: ortulu kapanisi tablo sinirini asacak sekilde birak",
  "src/edgar_mcp/belge.py",
  "        alt = self._tablo_kapsami() if tag in (\"tr\", \"td\", \"th\") else 0",
  "        alt = 0",
  "test_ic_ice_tablolar_ayri_ayri_donuyor"),

 ("K: kapanmamis tabloyu dusur",
  "src/edgar_mcp/belge.py",
  "        while self._acik:\n            self._tablo_bitir(self._acik.pop())",
  "        self._acik.clear()",
  "test_kapanmamis_tablo_da_donuyor"),

 ("K: tablo konumlarini sadelestirmeden once dondur",
  "src/edgar_mcp/belge.py",
  "        t.baslangic = esleme.get(t.baslangic, 0)",
  "        pass",
  "test_tablo_konumu_dondurulen_metne_denk_geliyor"),

 ("K: bosluk sadelestirmesinde ucuncu satiri da birak",
  "src/edgar_mcp/belge.py",
  'parca = "\\n" * min(satir, 2) if satir else " "',
  'parca = "\\n" * satir if satir else " "',
  "test_bosluk_sadelestirme_eski_regex_zinciriyle_ayni"),

 ("I: etiket rol sirasinda kisa etiketi one al",
  "src/edgar_mcp/xbrl.py",
  "    \"http://www.xbrl.org/2003/role/label\",\n    \"http://www.xbrl.org/2003/role/terseLabel\",",
  "    \"http://www.xbrl.org/2003/role/terseLabel\",\n    \"http://www.xbrl.org/2003/role/label\",",
  "test_eksen_ve_uye_adlari_insan_okunur_geliyor"),

 ("I: dokumantasyon metnini de etiket say",
  "src/edgar_mcp/xbrl.py",
  "_ROL_ONCELIK = (\n    \"http://www.xbrl.org/2003/role/label\",",
  "_ROL_ONCELIK = (\n    \"http://www.xbrl.org/2003/role/documentation\",\n    \"http://www.xbrl.org/2003/role/label\",",
  "test_fact_etiketleri_dokumantasyon_metnini_kullanmiyor"),

 ("I: yay yerine loc_/lab_ isimlendirmesine guven",
  "src/edgar_mcp/xbrl.py",
  "    for bas, son in yaylar:",
  "    for bas, son in yaylar + [(k, \"lab\" + k[3:]) for k in konumlar]:",
  "test_etiketi_olmayan_ad_uydurulmuyor"),

 ("I: cok anlamli yerel adi da haritaya koy",
  "src/edgar_mcp/xbrl.py",
  "    out.yerel = {k: next(iter(v)) for k, v in adaylar.items() if len(v) == 1}",
  "    out.yerel = {k: sorted(v)[0] for k, v in adaylar.items()}",
  "test_etiket_ayristirici_cok_anlamli_yerel_adi_tahmin_etmiyor"),

 ("I: bozuk linkbase'de cagriyi dusur",
  "src/edgar_mcp/xbrl.py",
  "    except ET.ParseError:\n        return Etiketler()",
  "    except ET.ParseError:\n        raise",
  "test_etiket_ayristirici_bozuk_xml_de_cokmuyor"),

 ("I: etiket istenmese de linkbase'i indir",
  "src/edgar_mcp/server.py",
  "    if etiket_iste:\n        await _ilerleme(ctx, 2, adim_sayisi, \"Downloading the label linkbase\")",
  "    if True:\n        await _ilerleme(ctx, 2, adim_sayisi, \"Downloading the label linkbase\")",
  "test_etiket_istenmediginde_indirilmiyor"),

 ("I: etiket onbellegini kaldir",
  "src/edgar_mcp/server.py",
  "        if url not in _ETIKET:",
  "        if True:",
  "test_etiket_dosyasi_ayni_cagrida_iki_kez_indirilmiyor"),

 ("I: etiket dosyasi yoksa cagriyi dusur",
  "src/edgar_mcp/server.py",
  "    return BOS_ETIKET, None",
  "    raise ValueError(\"This filing carries no label linkbase.\")",
  "test_etiket_dosyasi_yokken_calismaya_devam_ediyor"),

 ("I: cozulemeyen uyeyi bos etiketle doldur",
  "src/edgar_mcp/server.py",
  "                               if etiket_haritasi.bul(u)},",
  "                               },",
  "test_eksen_ve_uye_adlari_insan_okunur_geliyor"),

 ("M: kesim filtresini XBRL satirlarindan kaldir",
  "src/edgar_mcp/server.py",
  '            if _kesimden_sonra(row.get("filed"), as_of):\n                continue',
  '            if False:\n                continue',
  "test_as_of_o_tarihte_bilinen_degeri_donduruyor"),

 ("M: kesimi dosyalama listesine uygulama",
  "src/edgar_mcp/server.py",
  "        return [f for f in liste if not _kesimden_sonra(f.filing_date, as_of)]",
  "        return list(liste)",
  "test_as_of_dosyalama_listesini_o_tarihe_gore_kesiyor"),

 ("M: acikca istenen gec dosyalamayi sessizce ver",
  "src/edgar_mcp/server.py",
  '    if accession and _kesimden_sonra(kayit.get("filing_date"), as_of):',
  "    if False:",
  "test_as_of_acikca_istenen_gec_dosyalamayi_sessizce_vermiyor"),

 ("M: ortam degiskenindeki kesimi yok say",
  "src/edgar_mcp/server.py",
  '    b = _tarih_dogrula((os.environ.get(AS_OF_ORTAM) or "").strip() or None,\n                       AS_OF_ORTAM)',
  "    b = None",
  "test_as_of_ortam_degiskeni_cagri_vermeden_de_uygulaniyor"),

 ("M: carpismada GEC olan kesimi sec",
  "src/edgar_mcp/server.py",
  "        return min(a, b)",
  "        return max(a, b)",
  "test_as_of_cagri_ile_ortamdan_erken_olani_kazaniyor"),

 ("M: tarihi bilinmeyen kaydi kesimin icine al",
  "src/edgar_mcp/server.py",
  "    return not tarih or tarih > as_of",
  "    return bool(tarih) and tarih > as_of",
  "test_as_of_bilinmeyen_tarih_iceri_alinmiyor"),

 ("M: kesimi uygulayamayan araci sessizce calistir",
  "src/edgar_mcp/server.py",
  '    kesim = _as_of_coz(None)\n    if kesim:\n        raise ValueError(\n            f"A point-in-time cutoff is in effect',
  '    kesim = _as_of_coz(None)\n    if False:\n        raise ValueError(\n            f"A point-in-time cutoff is in effect',
  "test_as_of_uygulayamayan_arac_sessizce_gecmiyor"),

 ("M: revizyon gecmisinde kesimi atla",
  "src/edgar_mcp/server.py",
  '                if _kesimden_sonra(row.get("filed"), kesim):\n                    continue',
  "                if False:\n                    continue",
  "test_as_of_revizyon_gecmisini_de_kesiyor"),

 ("M: aramada end_date tavanini uygulama",
  "src/edgar_mcp/server.py",
  "        son = min(son, kesim) if son else kesim",
  "        son = son or kesim",
  "test_as_of_aramanin_ust_sinirini_da_kisiyor"),

 ("M: Form 4 akisinda kesimi atla",
  "src/edgar_mcp/server.py",
  '    kayitlar = [f for f in _akis_kayitlari(\n        sub.get("filings", {}).get("recent", {}), cik, "4")\n        if not _kesimden_sonra(f.filing_date, kesim)]',
  '    kayitlar = _akis_kayitlari(sub.get("filings", {}).get("recent", {}), cik, "4")',
  "test_as_of_sahiplik_araclarini_da_kesiyor"),

 ("M: akis taramasinda kesimi atla (13F)",
  "src/edgar_mcp/server.py",
  "        elif (not _form_uyuyor(al(formlar, i), form_type)\n              or _kesimden_sonra(al(tarihler, i), as_of)):",
  "        elif not _form_uyuyor(al(formlar, i), form_type):",
  "test_as_of_sahiplik_araclarini_da_kesiyor"),

 ("N: seri anahtarindan donem uzunlugunu cikar",
  "src/edgar_mcp/server.py",
  "        k = (pt.period_end, pt.unit, _donem_kovasi(pt.days))",
  "        k = (pt.period_end, pt.unit)",
  "test_ayni_gun_biten_farkli_uzunluktaki_donemler_birbirini_dusurmuyor"),

 ("N: revizyon anahtarindan donem uzunlugunu cikar",
  "src/edgar_mcp/server.py",
  "                gruplar.setdefault(\n                    (tag, end, birim, _donem_kovasi(days)), []\n                ).append(",
  "                gruplar.setdefault(\n                    (tag, end, birim, None), []\n                ).append(",
  "test_farkli_uzunluktaki_donemler_revizyon_sanilmiyor"),

 ("N: donem kovasini ham gun sayisina cevir (52/53 hafta)",
  "src/edgar_mcp/server.py",
  "    return round(days / 30.4)",
  "    return days",
  "test_donem_kovasi_52_haftalik_takvimi_ayni_kovada_tutuyor"),

 ("O: Form 4 tablolarini her sahip icin yeniden oku (ortak dosyalama)",
  "src/edgar_mcp/sahiplik.py",
  "                owner_count=sahip_sayisi,\n            ))\n    return out",
  "                owner_count=sahip_sayisi,\n            ))\n    out.islemler = out.islemler * sahip_sayisi\n    return out",
  "test_ortak_form4_islemleri_sahip_sayisi_kadar_cogaltmiyor"),

 ("O: ortak dosyalamada yalnizca ilk sahibi yaz",
  "src/edgar_mcp/sahiplik.py",
  '    ad = "; ".join(out.owners)',
  '    ad = out.owners[0] if out.owners else ""',
  "test_ortak_form4_islemleri_sahip_sayisi_kadar_cogaltmiyor"),

 ("O: Form 4/A bayragini dusur",
  "src/edgar_mcp/sahiplik.py",
  '    out.amendment = (_deger(kok, "documentType") or "").strip().upper().endswith("/A")',
  "    out.amendment = False",
  "test_form4_duzeltmesi_bildiriliyor"),

 ("O: turev satirlarini kod toplamina kat",
  "src/edgar_mcp/server.py",
  "        if t.is_derivative:\n            turev_disarida += 1\n            continue",
  "        if False:\n            turev_disarida += 1\n            continue",
  "test_turev_satirlari_kod_toplamina_girmiyor"),

 ("O: mutabakat anahtarindan donem uzunlugunu cikar",
  "src/edgar_mcp/server.py",
  "        return (bitis or \"\", birim, _donem_kovasi(gun))",
  "        return (bitis or \"\", birim, None)",
  "test_ayni_gun_biten_iki_donem_mutabakati_tek_satira_yigilmiyor"),

 ("O: mutabakatta uye degerlerini gizle",
  "src/edgar_mcp/server.py",
  "            member_values=dict(sorted(uyeler.get(k, {}).items())),",
  "            member_values={},",
  "test_mutabakat_uye_degerlerini_gosteriyor"),

 ("O: hicbir sey toplanamayinca sessizce bos don",
  "src/edgar_mcp/server.py",
  "    if not out and disarida:",
  "    if False:",
  "test_sayisal_olmayan_ve_nil_fact_sessizce_sayiya_cevrilmiyor"),

 ("P: yil sonu / yil ici ayrimini kaldir (yuvarlama modu)",
  "src/edgar_mcp/server.py",
  "        yil_sonunda = self._yil_sonunda_mi(end)",
  "        yil_sonunda = False",
  "test_etiket_degisiminde_gecmis_kirpilmaz"),

 ("P: capa eslesme toleransini yil boyuna cikar",
  "src/edgar_mcp/server.py",
  "FY_SONU_TOLERANSI = 10",
  "FY_SONU_TOLERANSI = 400",
  "test_takvim_52_53_haftalik_yilda_iki_yil_ayni_etiketi_almiyor"),

 ("P: capa cakismasinda buyuk fy'yi sec",
  "src/edgar_mcp/server.py",
  "        if e not in en_kucuk or fy < en_kucuk[e]:",
  "        if e not in en_kucuk or fy > en_kucuk[e]:",
  "test_donem_yili_bitis_tarihinden_gelir"),

 ("P: tutarsiz capada YANLIS capayi tut (cogunluk kuralini kaldir)",
  "src/edgar_mcp/server.py",
  "            if kayma == cogunluk and (onceki_fy - _yil(onceki_e)) != cogunluk:\n                temiz[-1] = (e, fy)\n            continue",
  "            continue",
  "test_takvim_tutarsiz_capa_dizisi_temizleniyor"),

 ("P: mali yil kaynagini her zaman 'reported' de",
  "src/edgar_mcp/server.py",
  '            return fy - n, ("derived" if n == 0 else "extrapolated")',
  '            return fy - n, "reported"',
  "test_takvim_capa_araligi_disinda_etiket_tahmin_oldugunu_soyluyor"),

 ("P: takvim degisikligi bayragini dusur",
  "src/edgar_mcp/server.py",
  "        self.takvim_degisti = len(aylar) > 1",
  "        self.takvim_degisti = False",
  "test_takvim_mali_yil_sonu_degisince_iki_rejim_de_dogru"),

 ("R: indeks kacirinca govdeye bakmayi kapat (JPM MD&A vakasi)",
  "src/edgar_mcp/server.py",
  "            vurus = bolum_govdede_ara(cikti.metin, section)",
  "            vurus = None",
  "test_bitisik_gercek_basliklar_bulunamadi_diye_reddedilmiyor"),

 ("R: govde aramasinda icindekiler satirini sec (ilk vurus)",
  "src/edgar_mcp/belge.py",
  "        if en_iyi is None or (son - m.start()) > (en_iyi[2] - en_iyi[1]):",
  "        if en_iyi is None:",
  "test_bitisik_gercek_basliklar_bulunamadi_diye_reddedilmiyor"),

 ("R: bolum kaynagini her zaman indeks de",
  "src/edgar_mcp/server.py",
  '                bolum_kaynagi = "search"',
  '                bolum_kaynagi = "index"',
  "test_bitisik_gercek_basliklar_bulunamadi_diye_reddedilmiyor"),

 ("S: 13F duzeltme bayragini dusur",
  "src/edgar_mcp/sahiplik.py",
  "        amendment=(duzeltme_no is not None or duzeltme_tipi is not None\n                   or str(bayrak or \"\").strip().lower() in (\"true\", \"y\", \"1\")),",
  "        amendment=False,",
  "test_13f_duzeltmesi_duzeltme_oldugunu_soyluyor"),

 ("S: 13F duzeltme turunu rapor turuyle karistir",
  "src/edgar_mcp/sahiplik.py",
  '    duzeltme_tipi = bul("amendmentType")',
  '    duzeltme_tipi = bul("reportType")',
  "test_13f_duzeltmesi_duzeltme_oldugunu_soyluyor"),

 ("T: etiket agirligini siralamadan cikar (tek noktali cop kazansin)",
  "src/edgar_mcp/server.py",
  "        return (pt.filed, agirlik.get(pt.source_tag, 0),\n                -oncelik.get(pt.source_tag, 99))",
  "        return (pt.filed, 0, -oncelik.get(pt.source_tag, 99))",
  "test_tek_noktali_ilgisiz_etiket_seriyi_ele_gecirmiyor"),

 ("T: etiket celiskisini bildirme",
  "src/edgar_mcp/server.py",
  "            catismalar.append(TagConflict(",
  "            [] .append(TagConflict(",
  "test_etiketler_celistiginde_celiski_bildiriliyor"),

 ("T: celiskiyi ayni etiketin iki dosyalamasinda da bildir",
  "src/edgar_mcp/server.py",
  "        if (kazanan.source_tag != kaybeden.source_tag\n                and kazanan.value != kaybeden.value):",
  "        if kazanan.value != kaybeden.value:",
  "test_etiketler_celistiginde_celiski_bildiriliyor"),

 ("U: Dockerfile'dan LICENSE kopyalamayi kaldir (imaj derlenmesin)",
  "Dockerfile",
  "COPY pyproject.toml README.md LICENSE ./",
  "COPY pyproject.toml README.md ./",
  "test_dockerfile_pyprojectin_istedigi_dosyalari_kopyaliyor"),

 ("L: OCI sahiplik etiketini baska bir ada cevir",
  "Dockerfile",
  'LABEL io.modelcontextprotocol.server.name="io.github.belermirzaa7-ops/sec-edgar-mcp"',
  'LABEL io.modelcontextprotocol.server.name="io.github.baskasi/sec-edgar-mcp"',
  "test_kayit_defteri_kimligi_uc_dosyada_da_ayni"),
]


def yakalandi(beklenen: str, kirmizi: list[str]) -> bool:
    """Beklenen test kirmiziya dondu mu.

    Parametreli testler pytest ciktisinda `test_x[2025Q1]` diye gorunur; duz
    esitlik arayan bir kontrol bunlari HIC eslestiremez ve gercekte calisan bir
    korumayi "KORUMASIZ" diye raporlar (14 Agu 2026'da bir kez oldu: donem
    yazimi enjeksiyonu alti parametrenin altisini da kirmiziya dondurmustu).
    """
    return any(t == beklenen or t.startswith(beklenen + "[") for t in kirmizi)


def sozdizimi_gecerli(yol: str, kaynak: str) -> bool:
    """Enjekte edilmis metin hala derlenebiliyor mu.

    Neden (14 Agu 2026): bir enjeksiyonun degistirme metni parantezi bozdu.
    Dosya artik import edilemedigi icin ILGISIZ testler kirmiziya dondu ve
    harness bunu "KORUMASIZ" diye raporladi - yani "koruma yok" ile "enjeksiyon
    hatali" ayni gorunuyordu. Ikisi cok farkli sey; ayirt edilmeleri gerekir.
    Python disi dosyalar (orn. Dockerfile) bu kontrolden muaf.
    """
    if not yol.endswith(".py"):
        return True
    try:
        ast.parse(kaynak)
        return True
    except SyntaxError:
        return False


def secilenler(argv: list[str]) -> list[tuple]:
    """`--aday <alt dize>`: yalnizca adi eslesen enjeksiyonlari calistir.

    Neden bu bayrak var (14 Agu 2026, olay - P-24): yeni bir enjeksiyon adayini
    denemek icin dosya ELDE duzenlenmisti; oturum bitmeden geri alinmadi ve iki
    test bir sonraki oturuma kirmizi girdi. Aday deneme isi de yedegi, kilidi ve
    `finally` ile geri almayi kullanmali - tek fark, hangi enjeksiyonlarin
    calistigi. Aday once listeye eklenir, sonra tek basina denenir.
    """
    secili = ENJEKSIYONLAR
    if "--aday" in argv:
        desen = argv[argv.index("--aday") + 1].lower()
        secili = [e for e in secili if desen in e[0].lower()]
    if "--parca" in argv:
        secili = bol(secili, argv[argv.index("--parca") + 1])
    return secili


def bol(liste: list[tuple], ifade: str) -> list[tuple]:
    """`--parca k/n`: listeyi n bitisik parcaya bol, k'inciyi dondur.

    Neden (16 Agu 2026 - KK-41): her enjeksiyon tum test setini kosturuyor ve
    set 163 enjeksiyon tasiyor. Sure makinenin yuku ile cok degisiyor - bos bir
    konteynerde tek kosu 14 sn olculdu (~40 dk toplam), ama ayni gun cokerek
    biten kosuda enjeksiyon basina ~80 sn dusmustu (3 saatin uzerine cikan bir
    projeksiyon). Bu degiskenligin kendisi parcalamanin gerekcesi: surec ne
    kadar uzun yasarsa oldurulme olasiligi o kadar yuksek. Parcali kosuda her
    surec kisa yasiyor ve bir parca coktugunde yalnizca o parca tekrarlanir.

    Bolme BITISIK, atlamali degil: `--parca 2/4` listenin ikinci dortlugudur.
    Cokmeden sonra hangi araligin tekrar kosacagi boylece tek bakista belli.

    UYARI: tek bir parcanin yesil donmesi setin tamamini dogrulamaz. Cagiran,
    n parcanin n'ini de kosturmak ve hepsinin exit 0 dondugunu gormek zorunda.
    """
    try:
        k_s, n_s = ifade.split("/")
        k, n = int(k_s), int(n_s)
    except ValueError:
        raise ValueError("--parca bicimi: k/n (orn. 2/4)") from None
    if n < 1 or not 1 <= k <= n:
        raise ValueError(f"--parca {ifade}: 1 <= k <= n olmali")
    adim = -(-len(liste) // n)  # tavan bolme: son parca kisa kalir, hicbiri dusmez
    return liste[(k - 1) * adim: k * adim]


def git_temiz_mi() -> bool | None:
    """Korunan dosyalar HEAD ile ayni mi. Karar verilemiyorsa None.

    Yedek dizininden BAGIMSIZ ikinci bir kaynak. Neden gerekli (18 Agu 2026,
    denetimde uretildi): `artiklar()` "enjekte kalmis dosya" listesini yalnizca
    `.enjeksiyon_yedek/` VARSA hesapliyor, ve o dizin `.gitignore`'da. Taze bir
    klon, `git clean -fdx` ya da elle temizlik tek kaniti siliyor; kaynak dosya
    enjekte kalsa bile `--kontrol` "TEMIZ" diyordu. Yani KK-41'de kapatilan
    bosluk, kapatan aracin kendisinde geri aciliyordu.
    """
    try:
        r = subprocess.run(
            ["git", "diff", "--quiet", "--", *DOSYALAR],
            cwd=KOK, capture_output=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    return None                      # git yok, depo degil, ya da baska bir hata


def kontrol(sert: bool = False) -> int:
    """Onceki bir calismadan artik kaldi mi. Kirli ise exit 2.

    Onarim YAPMAZ (bkz. `artiklar`): CI'nin ve paketleme adiminin gormesi
    gereken sey durumun kendisi. Sessizce onaran bir kontrol, "cokmeden sonra
    paketlendi" olayini gorunmez kilardi - kapatmaya calistigimiz bosluk tam
    olarak buydu.

    `sert=True` ikinci bir kaynak olarak git'e de bakar ve karar veremezse
    exit 3 doner. Varsayilan olarak KAPALI: normal gelistirmede korunan
    dosyalar zaten HEAD'den farkli olur ve her cagri exit 3 donerdi. Ama
    varsayilan haliyle de "TEMIZ" DEMEZ - yalnizca neye baktigini soyler.
    """
    yedek, kilit, farkli, not_ = artiklar()
    if not (yedek or kilit):
        git = git_temiz_mi()
        if git is True:
            print("  TEMIZ: artik yedek/kilit yok ve korunan dosyalar HEAD ile ayni.")
            return 0
        if sert:
            print("  DOGRULANAMADI: artik yedek/kilit yok, ama korunan dosyalarin")
            print("  HEAD ile ayni oldugu git'ten teyit edilemedi"
                  + (" (git farkli diyor)." if git is False else " (git okunamadi)."))
            print("  Yedek dizini .gitignore'da oldugu icin silinmis bir artik")
            print("  yalnizca git ile gorulebilir.")
            return 3
        print("  ARTIK YOK: yedek dizini ve kilit dosyasi bulunmadi.")
        print("  Kaynak dosyalar KARSILASTIRILMADI - karsilastirilacak yedek yok."
              + ("" if git is not False else " (git korunan dosyalarda fark goruyor.)"))
        print("  Kesin kontrol icin: --kontrol --sert (temiz bir calisma agacinda).")
        return 0
    print("  KIRLI: onceki bir enjeksiyon calismasi tamamlanmamis.")
    if kilit:
        print(f"    kilit dosyasi duruyor: {KILIT}")
    if yedek:
        print(f"    yedek dizini duruyor:  {YEDEK_DIZIN}")
    if not_:
        print(f"    en son uygulanan enjeksiyon: {not_.strip()}")
    for f in farkli:
        print(f"    ENJEKTE HALDE KALMIS: {f}")
    if yedek and not farkli:
        print("    (kaynak dosyalar yedekle ayni - enjeksiyon uygulanmadan cokmus)")
    print("  Onarim: `python arac/enjeksiyon.py` calistir; basta geri yukler.")
    return 2


def main() -> int:
    ciktiyi_utf8_yap()
    if not kilitle():
        return 1
    atexit.register(kilidi_birak)

    try:
        secili = secilenler(sys.argv[1:])
    except (IndexError, ValueError) as e:
        print("  KULLANIM: enjeksiyon.py [--aday <ad parcasi>] [--parca k/n] [--kontrol]")
        if isinstance(e, ValueError):
            print(f"  {e}")
        return 1
    if not secili:
        print("  DURDU: secim bos - hicbir enjeksiyon eslesmedi.")
        return 1

    # Onceki cokmeden artik kalmis olabilir: once onu geri yukle.
    if YEDEK_DIZIN.exists():
        print("Onceki calismadan artik yedek bulundu, geri yukleniyor...")
        _, _, _, not_ = artiklar()
        if not_:
            print(f"  en son uygulanan enjeksiyon: {not_.strip()}")
        geri_al(sessiz=False)

    print("=" * 78 + "\nHATA ENJEKSIYONU\n" + "=" * 78)
    baslangic = {f: hashle(f) for f in DOSYALAR}

    kirmizi = testler()
    if kirmizi is None:
        print(f"  DURDU: temiz durumda test kosusu {SURE_SINIRI} sn'yi asti.")
        return 1
    if kirmizi:
        print("  DURDU: temiz durumda kirmizi test var ->", kirmizi)
        return 1
    parca = ""
    if "--parca" in sys.argv:
        parca = sys.argv[sys.argv.index("--parca") + 1]
        print(f"  PARCALI KOSU: {parca} - bu kosu setin TAMAMINI dogrulamaz.")
    print(f"  Temiz durum yesil. {len(secili)} enjeksiyon calistirilacak.\n")

    yedekle()
    atexit.register(geri_al)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(
            sig, lambda *_: (geri_al(sessiz=False), kilidi_birak(), sys.exit(130))
        )

    sonuc = []
    try:
        for i, (ad, dosya, eski, yeni_metin, beklenen) in enumerate(secili, 1):
            print(f"  [{i}/{len(secili)}] {ad[:60]}", flush=True)
            metin = oku(YEDEK_DIZIN / pathlib.Path(dosya).name)
            if eski not in metin:
                sonuc.append((ad, "ENJEKSIYON UYGULANAMADI", False))
                continue
            bozuk = metin.replace(eski, yeni_metin, 1)
            if not sozdizimi_gecerli(dosya, bozuk):
                # Enjeksiyon dizgisi hatali yazilmis: dosya derlenmiyor.
                # Bu bir koruma eksigi DEGIL, harness hatasidir.
                sonuc.append((ad, "ENJEKSIYON SOZDIZIMI BOZDU", False))
                continue
            # Once "kim uygulandi" diske yazilir, sonra dosya bozulur. Ters
            # sirada yazilsa, tam aradaki sert oldurme izsiz kalirdi.
            UYGULANAN.write_text(f"[{i}/{len(secili)}] {ad} -> {dosya}", encoding="utf-8")
            yaz(KOK / dosya, bozuk)
            k = testler()
            yaz(KOK / dosya, metin)
            UYGULANAN.unlink(missing_ok=True)
            if k is None:
                # Olculemedi: "koruma yok" ile ayni satira yazilmamali.
                sonuc.append((ad, f"TEST ZAMAN ASIMI ({SURE_SINIRI} sn)", False))
                continue
            sonuc.append((ad, ", ".join(k) or "hicbiri", yakalandi(beklenen, k)))
    finally:
        geri_al()

    print("\n" + "=" * 78)
    print(f"{'Bozulan koruma':<58} Sonuc   Yakalayan test")
    print("-" * 78)
    for ad, k, ok in sonuc:
        print(f"{ad[:57]:<58} {'GECERLI' if ok else 'KORUMASIZ':<8} {k[:60]}")

    print("\n" + "=" * 78 + "\nGERI ALMA DOGRULAMASI\n" + "=" * 78)
    tamam = True
    for f in DOSYALAR:
        ayni = hashle(f) == baslangic[f]
        tamam &= ayni
        print(f"  {f}: {'degismedi' if ayni else 'DEGISMIS!'}  ({hashle(f)[:16]})")
    k = testler()
    if k is None:
        print(f"  Testler: OLCULEMEDI (zaman asimi, {SURE_SINIRI} sn)")
    else:
        print(f"  Testler: {'tumu yesil' if not k else 'KIRMIZI: ' + str(k)}")

    kilidi_birak()
    basarili = sum(1 for *_, ok in sonuc if ok)
    print(f"\nSONUC: {basarili}/{len(sonuc)} koruma dogrulandi.")
    if parca:
        print(f"UYARI: bu yalnizca {parca} parcasidir; tum parcalar kosulmadan set")
        print("       dogrulanmis sayilmaz.")
    temizle()
    return 0 if (basarili == len(sonuc) and tamam and k == []) else 1


if __name__ == "__main__":
    if "--kontrol" in sys.argv[1:]:
        sys.exit(kontrol(sert="--sert" in sys.argv[1:]))
    sys.exit(main())
