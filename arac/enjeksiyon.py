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
DOSYALAR = [
    "src/edgar_mcp/server.py",
    "src/edgar_mcp/client.py",
    "arac/sir_tarama.py",
    "src/edgar_mcp/belge.py",
    "src/edgar_mcp/xbrl.py",
    "Dockerfile",
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
  "fiscal_year=temel + kayma,",
  "fiscal_year=row.get('fy') or (temel + kayma),",
  "test_donem_yili_bitis_tarihinden_gelir"),

 ("Donem uzunlugu filtresini kaldir (ceyreklik sizsin)",
  "src/edgar_mcp/server.py",
  "        return 300 <= days <= 400",
  "        return True",
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
  '        has_more=len(dosyalamalar) > limit or daha_eski,',
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
  "                gruplar.setdefault((tag, end, birim), []).append(",
  "                gruplar.__setitem__((tag, end, birim), []) or gruplar[(tag, end, birim)].append(",
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
  '    ad = document or kayit["primary_document"]',
  '    ad = kayit["primary_document"]',
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
  "            istenen.setdefault(await _c().cik_for_ticker(t), []).append(t.upper())",
  "            istenen[await _c().cik_for_ticker(t)] = [t.upper()]",
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
  "        elif self._atla:\n            pass\n        elif tag in (\"td\", \"th\"):",
  "        elif tag in (\"td\", \"th\"):",
  "test_gizli_blok_icinde_ayirici_uretilmiyor"),

 ("F: anlik sinirini yine takvim yilinda kur",
  "src/edgar_mcp/server.py",
  "            sinir = date(_fy_sonuna_gore_yil(end, ay_gun), ay, gun)",
  "            sinir = date(_yil(end), ay, gun)",
  "test_yil_sonu_aralik_ocak_arasinda_oynayan_takvim"),

 ("F: yillik satirda yine bitis yilini kullan",
  "src/edgar_mcp/server.py",
  "            temel = _yil(end) if ay_gun is None else _fy_sonuna_gore_yil(end, ay_gun)",
  "            temel = _yil(end)",
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
    if "--aday" not in argv:
        return ENJEKSIYONLAR
    desen = argv[argv.index("--aday") + 1].lower()
    return [e for e in ENJEKSIYONLAR if desen in e[0].lower()]


def main() -> int:
    if not kilitle():
        return 1
    atexit.register(kilidi_birak)

    try:
        secili = secilenler(sys.argv[1:])
    except IndexError:
        print("  KULLANIM: enjeksiyon.py [--aday <ad parcasi>]")
        return 1
    if not secili:
        print("  DURDU: --aday hicbir enjeksiyonla eslesmedi.")
        return 1

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
            metin = (YEDEK_DIZIN / pathlib.Path(dosya).name).read_text()
            if eski not in metin:
                sonuc.append((ad, "ENJEKSIYON UYGULANAMADI", False))
                continue
            bozuk = metin.replace(eski, yeni_metin, 1)
            if not sozdizimi_gecerli(dosya, bozuk):
                # Enjeksiyon dizgisi hatali yazilmis: dosya derlenmiyor.
                # Bu bir koruma eksigi DEGIL, harness hatasidir.
                sonuc.append((ad, "ENJEKSIYON SOZDIZIMI BOZDU", False))
                continue
            (KOK / dosya).write_text(bozuk)
            k = testler()
            (KOK / dosya).write_text(metin)
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
    print(f"  Testler: {'tumu yesil' if not k else 'KIRMIZI: ' + str(k)}")

    kilidi_birak()
    basarili = sum(1 for *_, ok in sonuc if ok)
    print(f"\nSONUC: {basarili}/{len(sonuc)} koruma dogrulandi.")
    temizle()
    return 0 if (basarili == len(sonuc) and tamam and not k) else 1


if __name__ == "__main__":
    sys.exit(main())
