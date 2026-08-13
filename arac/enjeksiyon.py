"""Hata enjeksiyonu (standart §2): her korumayi bilerek boz, testin KIRMIZIYA
dondugunu gor, geri al.

Cokmeye dayanikli: yedekler once diske yazilir, calisma basinda artik yedek
varsa once o geri yuklenir, sinyal ve istisna durumunda finally ile geri alinir.
`git checkout` KULLANILMAZ - commit edilmemis isi silerdi.
"""
import atexit
import hashlib
import os
import pathlib
import signal
import subprocess
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
YEDEK_DIZIN = KOK / ".enjeksiyon_yedek"
DOSYALAR = [
    "src/edgar_mcp/server.py",
    "src/edgar_mcp/client.py",
    "arac/sir_tarama.py",
]

ORTAM = {**os.environ, "SEC_RATE_LIMIT_PER_SEC": "1000"}


def hashle(f):
    return hashlib.sha256((KOK / f).read_bytes()).hexdigest()


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


def temizle():
    geri_al(sessiz=False)
    for x in YEDEK_DIZIN.glob("*"):
        x.unlink()
    if YEDEK_DIZIN.exists():
        YEDEK_DIZIN.rmdir()


def testler():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=KOK, capture_output=True, env=ORTAM,
        encoding="utf-8", errors="replace",
    )
    return [
        satir.split("::")[1].split()[0]
        for satir in (r.stdout or "").splitlines()
        if satir.startswith("FAILED")
    ]


ENJEKSIYONLAR = [
 ("Mali yili SEC'in fy alanindan al (ESKI HATAM)",
  "src/edgar_mcp/server.py",
  "fiscal_year=_yil(end) + kayma,",
  "fiscal_year=row.get('fy') or (_yil(end) + kayma),",
  "test_donem_yili_bitis_tarihinden_gelir"),

 ("Donem uzunlugu filtresini kaldir (ceyreklik sizsin)",
  "src/edgar_mcp/server.py",
  "if period == \"annual\" and not (300 <= days <= 400):",
  "if False:",
  "test_ceyreklik_yillik_seriye_sizmaz"),

 ("Dedup anahtarina source_tag ekle (ayni donem cift sayilsin)",
  "src/edgar_mcp/server.py",
  "        k = (pt.period_end, pt.unit)",
  "        k = (pt.period_end, pt.unit, pt.source_tag)",
  "test_ortusen_donemde_en_son_sunulan_kazanir"),

 ("SEC User-Agent zorunlulugunu kaldir",
  "src/edgar_mcp/client.py",
  'if not ua or "@" not in ua:',
  'if False:',
  "test_ua_zorunlu"),

 ("Form turu filtresini kaldir (10-K istenince hepsi gelsin)",
  "src/edgar_mcp/server.py",
  "if form_type and r[\"form\"][i] != form_type:",
  "if False:",
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

 ("H-1: mali yil kaymasini turetme, eski heuristige don",
  "src/edgar_mcp/server.py",
  "kayma = sorted(set(kaymalar), key=lambda k: (-kaymalar.count(k), k))[0]",
  "kayma = 0",
  "test_kayma_target_tipi_eksi_bir"),

 ("H-1: capa yokken 'turetildi' de (yalan bayrak)",
  "src/edgar_mcp/server.py",
  "    if not capalar:\n        return 0, False",
  "    if not capalar:\n        return 0, True",
  "test_kayma_capa_yoksa_turetilmedi_isaretlenir"),

 ("H-1: ceyreklik satirlari da capa say",
  "src/edgar_mcp/server.py",
  "        if start and not (300 <= _gun_farki(start, end) <= 400):\n            continue",
  "        if False:\n            continue",
  "test_kayma_ceyreklik_satirlari_capa_saymaz"),

 ("H-2: ilk eslesen etikette dur (gecmisi kirp)",
  "src/edgar_mcp/server.py",
  "        v = await _ham_kayitlar(cik, tag)\n        if v is not None:\n            veriler.append((tag, v))",
  "        v = await _ham_kayitlar(cik, tag)\n        if v is not None:\n            veriler.append((tag, v))\n            break",
  "test_etiket_degisiminde_gecmis_kirpilmaz"),

 ("H-2: ortusen donemde eski kaydi tut",
  "src/edgar_mcp/server.py",
  "        if mevcut is None or (pt.filed, -oncelik.get(pt.source_tag, 99)) > (",
  "        if mevcut is None or (pt.filed, -oncelik.get(pt.source_tag, 99)) < (",
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
  '        has_more=len(dosyalamalar) > limit,',
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

 ("CIK sifir dolgusunu kaldir",
  "src/edgar_mcp/client.py",
  'str(row["cik_str"]).zfill(10)',
  'str(row["cik_str"])',
  "test_profile"),
]


def main() -> int:
    # Onceki cokmeden artik kalmis olabilir: once onu geri yukle.
    if YEDEK_DIZIN.exists():
        print("Onceki calismadan artik yedek bulundu, geri yukleniyor...")
        geri_al(sessiz=False)

    print("=" * 78 + "\nHATA ENJEKSIYONU\n" + "=" * 78)
    baslangic = {f: hashle(f) for f in DOSYALAR}

    kirmizi = testler()
    if kirmizi:
        print("  DURDU: temiz durumda kirmizi test var ->", kirmizi)
        return 1
    print(f"  Temiz durum yesil. {len(ENJEKSIYONLAR)} enjeksiyon calistirilacak.\n")

    yedekle()
    atexit.register(geri_al)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (geri_al(sessiz=False), sys.exit(130)))

    sonuc = []
    try:
        for i, (ad, dosya, eski, yeni_metin, beklenen) in enumerate(ENJEKSIYONLAR, 1):
            print(f"  [{i}/{len(ENJEKSIYONLAR)}] {ad[:60]}", flush=True)
            metin = (YEDEK_DIZIN / pathlib.Path(dosya).name).read_text()
            if eski not in metin:
                sonuc.append((ad, "ENJEKSIYON UYGULANAMADI", False))
                continue
            (KOK / dosya).write_text(metin.replace(eski, yeni_metin, 1))
            k = testler()
            (KOK / dosya).write_text(metin)
            sonuc.append((ad, ", ".join(k) or "hicbiri", beklenen in k))
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
    print(f"  Testler: {'tumu yesil' if not k else 'KIRMIZI: ' + str(k)}")

    basarili = sum(1 for *_, ok in sonuc if ok)
    print(f"\nSONUC: {basarili}/{len(sonuc)} koruma dogrulandi.")
    temizle()
    return 0 if (basarili == len(sonuc) and tamam and not k) else 1


if __name__ == "__main__":
    sys.exit(main())
