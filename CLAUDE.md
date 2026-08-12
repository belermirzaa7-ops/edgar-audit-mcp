# CLAUDE.md — sec-edgar-mcp

## Bu proje ne
MCP 2026-07-28 spesifikasyonuna uygun, SEC EDGAR XBRL verisini deterministik
arac cagrilariyla sunan Python MCP sunucusu.

## Komutlar
```bash
uv sync                        # bagimliliklar
uv run pytest -q               # testler (SEC'e canli cikmaz, HTTP mock'lanir)
uv run mcp dev src/edgar_mcp/server.py   # MCP Inspector ile elle test
uv run ruff check . && uv run mypy src
docker build -t sec-edgar-mcp . && docker run --env-file .env -p 8000:8000 sec-edgar-mcp
```

## Kritik mimari kararlar
- **mcp v2.0.0 kullaniliyor. Giris noktasi `MCPServer`, `FastMCP` DEGIL.**
  v1 ornekleri internette hala baskin; `from mcp.server.fastmcp import FastMCP`
  yazma, v2'de o modul yok.
- Istemci tarafi alan adlari v2'de snake_case: `tool.input_schema`,
  `tool.output_schema`, `result.structured_content`.
- `@mcp.tool()` orijinal fonksiyonu dondurur; testlerde dogrudan cagrilir.
- Her arac Pydantic modeli dondurur -> output_schema otomatik uretilir.
  Donus tipini `dict` yapma, sema kaybolur.

## SEC kurallari (pazarlik yok)
- `SEC_USER_AGENT` ortam degiskeni zorunlu ve e-posta icermeli; yoksa
  `EdgarClient` bilerek hata firlatir.
- 10 istek/sn ust siniri. `RateLimiter` 8/sn'de tutuyor, yukseltme.
- API anahtari yok, .env'e sadece User-Agent girer.

## Repo etigi
- `.env` asla commit edilmez.
- stdio transport'ta `print()` KULLANMA — JSON-RPC akisini bozar. Log stderr'e.
- Yeni arac eklerken once testi yaz (HTTP mock'lu), sonra araci.

## Dogrulama dongusu
Kod degisikliginden sonra: `uv run pytest -q` calistir, kirmizi ise duzelt.
"Tamamlandi" demeden once testlerin gectigini goster.

## Karar kayitlari (neden boyle yapildi)

### KK-1: Mali yil, SEC'in `fy` alanindan DEGIL, donem bitis tarihinden turetilir
**Tarih:** 12  Agustos 2026 · **Durum:** yururlukte

SEC companyconcept API'sinde her kaydin `fy`/`fp` alanlari, o degerin **icinde
gectigi dosyalamanin** donemini gosterir; degerin kendi donemini degil. Bir 10-K
uc yillik karsilastirmali veri icerir ve ucunun de `fy`'si dosyalama yilidir.

`fy` kullanan ilk surum, Apple'in gelir serisini **iki yil kaydirdi** ve hata
vermedi — sessizce yanlis cevap verdi. Mevcut testler bunu yakalamadi cunku
sahte veri SEC'in bu davranisini taklit etmiyordu.

**Karar:** donem yalnizca `start`/`end` tarihlerinden belirlenir.
Yillik = 300-400 gun, ceyreklik = 60-120 gun.

**GUNCELLEME (KK-7):** bu kararin "mali yil `end` tarihinden okunur" kismi
yetersiz cikti ve degistirildi. Bkz. KK-7.

### KK-2: Testler hata enjeksiyonuyla dogrulanir
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte

Her koruma icin, korunan davranis bilerek bozulur ve ilgili testin kirmiziya
donmesi gorulur. Bu uygulanmadan once `test_filings_filter` hicbir sey
korumuyordu: sahte veride tek bir dosyalama vardi ve o da 10-K'ydi, dolayisiyla
filtre kaldirilinca sizacak veri yoktu. Sahte veri gercegin sozlesmesini
(karisik form turleri) taklit edecek sekilde duzeltildi.

Enjeksiyon harness'i: `arac/enjeksiyon.py`. Anlamli her degisiklikten sonra
calistirilir. Geri alma programatiktir, `git checkout` KULLANILMAZ; dosya
hash'leri baslangic/bitis karsilastirilir.

### KK-3: Bagimliliklar
`mcp` tam sabit (`==2.0.0`) — v1/v2 arasi API kirilmasi var, surpriz istenmiyor.
`httpx` ve `pydantic` ust sinirli (`<1.0`, `<3.0`) — major surum kirilmasina karsi.

### KK-4: Kavramlar takma adla verilir, ham XBRL etiketiyle degil
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §15, §18

Sirketler ayni finansal kalemi farkli US-GAAP etiketleriyle raporlar. Apple
geliri `Revenues` ile DEGIL
`RevenueFromContractWithCustomerExcludingAssessedTax` ile bildirir. Ilk surumde
modele "orn. Revenues, Assets, NetIncomeLoss" denilip dogru etiketi tahmin
etmesi bekleniyordu; bu 404 uretir ve model bos tur atar.

**Karar:** `CONCEPT_ALIASES` haritasi (revenue, net_income, total_assets, ...).
Takma ad verilirse aday etiketler sirayla denenir. Ham etiket de kabul edilir.
Bulunamazsa hata mesaji gecerli takma adlari listeler ve kesif aracini onerir.

Ek olarak `sec_edgar_list_available_concepts`: sirketin fiilen raporladigi
etiketleri arama ve sayfalama ile dondurur. companyfacts yaniti birkac MB
oldugundan CIK basina onbelleklenir.

### KK-5: Arac isimleri `sec_edgar_` onekli
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §15, §10

`get_company_profile` gibi jenerik isimler, baska MCP sunucularla ayni anda
yuklendiginde cakisir ve model yanlis araca gider. Isimler kirici bicimde
degistirildi (henuz hicbir istemciye bagli degildi, bedeli sifirdi).
`test_arac_isimleri_servis_onekli` bunu yapisal olarak sabitler.

### KK-6: Enjeksiyon harness'i cokmeye dayanikli olmali
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §2

Ilk harness zaman asimina ugradiginda enjeksiyon geri alinmadan kaldi ve
`sec_edgar_` oneki dusmus haliyle dosyada birakti. Yapisal regresyon testi
yakaladi, ama harness'in kendisi kusurluydu.

**Karar:** yedekler once diske (`.enjeksiyon_yedek/`), calisma basinda artik
yedek varsa once geri yuklenir, `finally` + SIGINT/SIGTERM isleyicisi + atexit.
Testlerde HTTP beklemesi olmamasi icin `SEC_RATE_LIMIT_PER_SEC=1000`;
sinirlayicinin kendisi `test_hiz_sinirlayici_gercekten_bekletir` ile ayrica
korunur, yani koruma kaldirilmadi.


### KK-7: Mali yil ADI heuristikle degil, SEC verisinden turetilir
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §12

KK-1'de gecici olarak `_mali_yil()` heuristigi kullanildi: "Ocak-Haziran'da
biten donem onceki yila sayilir". Kor nokta olarak isaretlenmisti; canli
olcum onu HATA olarak dogruladi:

| Ticker | Donem sonu | Heuristik | Sirketin kendi adi |
|---|---|---|---|
| AAPL | 2025-09-27 | FY2025 | FY2025 (dogru) |
| WMT  | 2026-01-31 | FY2025 | FY2026 (bir yil geride) |
| NKE  | 2026-05-31 | FY2025 | FY2026 (bir yil geride) |
| MSFT | 2026-06-30 | FY2025 | FY2026 (bir yil geride) |

Ters kural ("her zaman bitis yili") da guvenli degil: Target ve Gap, Subat'ta
biten yili BASLADIGI yilla adlandirir. Evrensel bir kural YOK.

**Karar:** `_fy_kaymasi()` kaymayi veriden turetir. SEC'in `fy` alani bir
10-K'nin KENDI donemi icin dogrudur (DEI DocumentFiscalYearFocus); yanlis olan
sadece ayni dosyalamadaki karsilastirma yillaridir. Her `fy` grubunda en gec
biten yillik donem o dosyalamanin kendi donemidir -> capa.
`kayma = fy - bitis_yili`, mod alinir, tum donemlere uygulanir.

Capa bulunamazsa kayma 0 kullanilir ama `fiscal_year_derived=False` doner —
istemci bu degerin daha az guvenilir oldugunu bilir. Uydurma yapilmaz.

### KK-8: Takma ad tum aday etiketleri BIRLESTIRIR, ilk eslesende durmaz
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §12

Kesif aracinin ciktisinda `SalesRevenueNet` (210 veri noktasi) modern etiketten
(117) fazla veri noktasina sahipti. Hipotez kuruldu ve canli olculdu:

```
takma ad 'revenue'   ->  9 donem, FY2017 - FY2025
ham SalesRevenueNet  -> 11 donem, FY2007 - FY2017
```

Apple 2018'de ASC 606'ya gecerken etiket degistirdi. "Ilk eslesen etikette dur"
mantigi 10 yillik gecmisi SESSIZCE kirpiyordu.

**Karar:** tum aday etiketler cekilir ve birlestirilir. Dedup anahtari
`(donem_sonu, birim)`; ayni donem birden fazla etikette varsa en son SUNULAN
(`filed`) kazanir, esitlikte takma ad sirasi belirler. Her `FactPoint` artik
`source_tag` tasir — hangi rakamin hangi etiketten geldigi izlenebilir.

**Kabul edilen sinir:** farkli etiketler ayni kalemi birebir ayni tanimla
olcmeyebilir (orn. ASC 606 oncesi/sonrasi net satis tanimi). `source_tag`
bu farki gizlemiyor, gorunur kiliyor; yorum cagiriya birakiliyor.

### KK-9: Disariya bakan yuzey Ingilizce, ic belgelendirme Turkce
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §15

Hedef musteri ABD/AB. Modelin ve musterinin gordugu her sey Ingilizce:
arac tanimlari, sema aciklamalari, hata mesajlari, README.
Kod yorumlari ve bu karar kayitlari Turkce kalir - ic belgelendirme.

`test_arac_tanimlari_ingilizce` bunu yapisal olarak sabitler (Turkce ipucu
kelimeleri arar). `test_her_arac_ve_parametre_aciklamali` ise aciklamasiz
arac/parametre eklenmesini engeller - ilk calistirmada uc `limit` parametresinin
aciklamasiz oldugunu yakaladi.

### KK-10: Enjeksiyon dizgileri bayatlar, CI bunu yakalamali
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §2

Kod her degistiginde enjeksiyon hedef dizgileri kirilabiliyor ve o koruma
o turda hic sinanmamis oluyor. Bu oturumda dort kez oldu (son seferinde
hata mesajlari Ingilizceye cevrilince).

Harness bunu "ENJEKSIYON UYGULANAMADI" diye raporluyor VE exit 1 donuyor,
bu yuzden CI isi kirmiziya donuyor. Sessiz gecmiyor. Kod degistirdikten sonra
`arac/enjeksiyon.py` calistirilmadan is bitmis sayilmaz.

### KK-11: `.env` yalnizca yerel scriptler icin, cekirdek okumaz
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §9

`.env.example` "bu dosyayi olustur" diyordu ama hicbir kod `.env` okumuyordu;
sadece Docker `--env-file` ile kullaniyordu. Dokuman olmayan bir davranis
vaat ediyordu.

**Karar:** MCP sunucusu ortamini kendisini calistiran uygulamadan alir
(Claude Desktop config'i, Docker, kabuk). Cekirdege `.env` okuma eklemek o
yollarda hicbir sey kazandirmaz, sadece calisma-zamani bagimliligi ekler.
Bu yuzden `python-dotenv` **yalnizca `[dev]` ekstrasinda** ve `.env` sadece
`arac/ortam.py` uzerinden yerel scriptlerde yukleniyor.

Iki test sabitliyor: `test_cekirdek_dotenv_bagimliligi_tasimaz` (src/ icinde
dotenv gecmemeli) ve `test_env_example_gercekten_okunan_degiskeni_belgeler`
(belgelenen her degisken kodda gercekten okunmali).

### KK-12: README iki dilli
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte

`README.md` Ingilizce (GitHub varsayilan olarak bunu gosterir), `README.tr.md`
Turkce, ikisinin basinda karsilikli link. Hedef musteri ABD/AB oldugu icin
varsayilan Ingilizce; Turkce surum Turkiye'deki degerlendiriciler icin.

Iki dosya da ayni ucu anlatiyor (fy tuzagi, mali yil adlandirmasi, etiket
degisimi). Birini guncellerken otekini de guncelle - bu su an elle
korunuyor, testle degil. Bilinen bakim yuku.

### KK-13: Sir taramasi git gecmisini de kapsar
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §8, §2

Ilk tarayici yalnizca calisma dizinini tariyordu. Gercek bir kacak bu yuzden
gozden kacti: bir commit'te dosyaya gercek e-posta eklendi, sonraki commit'te
geri alindi. Dosyanin son hali temizdi, tarayici "temiz" dedi, ama adres
`5198c97` commit'inde public olarak okunabilir kaldi.

**Karar:** `--gecmis` bayragi `git log --all -p` ciktisindaki EKLENEN satirlari
tarar. Uc davranis testle sabit:
- temiz gecmis -> bulgu yok
- eklenip silinen sir -> yakalanir (calisma dizini taramasi ayni durumda temiz der)
- sig (shallow) klon -> "temiz" DEMEZ, exit 2 ile basarisizlik bildirir

Ucuncusu en onemlisi: GitHub Actions varsayilan olarak sig klonluyor. Tarayici
bunu fark etmeseydi CI'da her zaman "temiz" yazar ve hicbir sey korumazdi.
`ci.yml` bu yuzden `fetch-depth: 0` kullaniyor.

### KK-14: CI matrisinde Windows zorunlu
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §3, §9

Iki hata yalnizca Windows'ta ortaya cikti ve Linux'ta yapisal olarak
gorunmezdi:

1. `subprocess.run(..., text=True)` Windows'ta yerel kod sayfasini kullanir
   (Turkce kurulumda cp1254). git'in UTF-8 ciktisinda `UnicodeDecodeError`
   firlatir, okuyucu is parcacigi olur, `stdout` None doner ve cagiran
   `AttributeError` alir. Duzeltme: `encoding="utf-8", errors="replace"`
   acikca verilir; `stdout` None olabilir varsayilir.
2. Bir test temizlik icin `rm -rf` cagiriyordu. Windows'ta boyle bir komut yok.
   Duzeltme: gecici dosyalar `tmp_path` ICINE alinir, pytest kendisi temizler;
   elle silme yok. Ayrica `file://` URI'si elle kurulmaz, `Path.as_uri()`
   kullanilir.

**Karar:** `test` ve `fault-injection` isleri hem ubuntu hem windows uzerinde
kosar. Lint/tip kontrolu tek kombinasyonda (ubuntu + 3.12) yeter - platformdan
bagimsizlar. Python 3.14 matriste, cunku gelistirme makinesi onu kullaniyor.

### KK-15: Sir tarayicinin sinirlari (ve kabul edilen bir risk)
**Tarih:** 12 Agustos 2026 · **Durum:** yururlukte · **Standart:** §11, §12

Tarayici iki seyi YAPAMAZ. Ikisi de olculdu, varsayilmadi:

**1. Uzaktaki geçmişi göremez.** `git log --all` yalnizca yerel referanslari
tarar. GitHub web arayuzunde yapilan ve hic `pull` edilmemis bir commit yerel
taramada gorunmez. Bu proje tam olarak boyle bir kacak yasadi: `5198c97`
commit'i web'de olusturuldu, yerelde hic bulunmadi, yerel tarama "temiz" dedi
ve dedigi dogruydu. CI'daki tarama (uzaktan klonladigi icin) gorurdu.
**Sonuc: yetkili kontrol CI'daki taramadir, yereldeki degil.**

**2. Sahipsiz (unreachable) commit'leri goremez.** Force push sonrasi eski
commit'ler hicbir dala bagli kalmaz, dolayisiyla `--all` kapsamina girmez -
ama GitHub'da SHA ile erisilebilir durumda kalirlar; cop toplama belirsiz
zamanda calisir, cogu zaman hic calismaz. **"Gecmisi temizledim" demek, o
commit'in gittigi anlamina gelmez.** Kesin yol: GitHub destegine purge talebi
ya da depoyu silip yeniden olusturmak.

**Kabul edilen risk:** `5198c97` commit'inde bir kisisel Gmail adresi duruyor
ve SHA ile okunabilir. Kimlik bilgisi degil; maruziyet yalnizca adresin
toplanabilmesi. Depoyu yeniden olusturma secenegi degerlendirildi ve maliyeti
faydasina degmedigi icin risk BILINCLI OLARAK kabul edildi. Yeni commit'ler
`@users.noreply.github.com` adresiyle atiliyor, yani tekrari yok.
