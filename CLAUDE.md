# CLAUDE.md — sec-edgar-mcp

> **Ise baslamadan once `PATTERNS.md` oku.** Bu depoda gercekten yasanmis her
> hata ve her birinin hangi testle korundugu orada. Bitirmeden once de oradaki
> kontrol listesinden gec. Bu dosya KARARLARI (neden boyle yapildi) tutar;
> PATTERNS.md HATALARI (neye dikkat et) tutar.

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

### KK-16: Annotations ipucudur, garanti testle saglanir
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §19

Araclarin tamami `read_only_hint=True, destructive_hint=False, idempotent_hint=True,
open_world_hint=True` ilan ediyor. Standart §19 acikca soyluyor: bunlar
IPUCUDUR, guvenlik garantisi degil. Istemci bunlara bakip karar vermemeli.

**Karar:** ipucu iki testle kanita cevriliyor.
- `test_tum_araclar_salt_okunur_ilan_ediyor` — ilan var mi
- `test_kodda_hicbir_yazma_yolu_yok` — `src/` icinde hicbir `.post/.put/.patch/
  .delete` cagrisi olmamali. Biri ileride yazma ekleyip hint'i guncellemeyi
  unutursa bu test kirmiziya doner.

Not: v2 SDK'da alan adlari snake_case (`read_only_hint`), spesifikasyondaki
camelCase (`readOnlyHint`) degil.

### KK-17: Liste donduren her arac sayfalama bilgisi verir
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §16

`limit` tek basina yetmiyor: model, gordugu listenin tamami mi yoksa kirpilmis
mi oldugunu bilemiyor ve "sirketin N dosyalamasi var" diye sonuclandirabiliyor.

**Karar:** `list_filings` artik `FilingPage` donuyor (`total_matching`,
`returned`, `has_more`, `filings`); `get_concept_series` yanitina
`total_periods`, `returned`, `has_more` eklendi. Kirici sema degisikligi,
bagli istemci yoktu.

Iki incelik testle sabit:
- `total_matching` FILTRE UYGULANDIKTAN sonraki sayidir; filtresiz toplami
  raporlamak modeli yaniltir (`test_filings_sayfalama_filtreyle_birlikte_dogru`)
- Seri kirpilirken EN YENI donemler kalir, en eskiler degil - trend analizi
  yapan model son donemleri gormeli (`test_seri_kirpmada_EN_YENI_donemler_kalir`)

### KK-18: Enjeksiyon hedefleri benzersiz olmali
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §2, §5

`list_filings` ve `list_available_concepts` ayni yerel degisken adini
(`eslesen`) kullaniyordu, dolayisiyla `has_more=len(eslesen) > limit,` dizgisi
iki yerde geciyordu. Enjeksiyon `replace(..., 1)` kullandigi icin yanlis
fonksiyonu bozuyor ve beklenmeyen test kirmiziya donuyordu - koruma
dogrulanmis GORUNUYOR ama aslinda baska bir sey sinaniyor.

Bu, standart §5'in ("predicate'leri dar ve kesin kur") kod uzerindeki
karsiligi: alt dize eslesmesi tahmin ettiginden genis eslesir.

**Karar:** `list_filings` icindeki degisken `dosyalamalar` olarak yeniden
adlandirildi. Yeni enjeksiyon eklerken hedef dizginin dosyada TEK gectigi
dogrulanmali.

### KK-19: Yerel scriptler de test kapsaminda
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1

`dene.py` test kapsami disindaydi. `ConceptSeries.resolved_concept` alani
`resolved_concepts` olarak degisince script calisma aninda `AttributeError`
veriyordu - ama tum testler yesildi. Kullanici calistirsaydi kirik bir demo
gorurdu.

**Karar:** `tests/test_scriptler.py` scripti sahte veriyle uctan uca calistirir
ve ciktisinda beklenen basliklarin bulundugunu dogrular. Script ciktisina yeni
bir alan eklenirse test de guncellenir; alan silinirse test kirmiziya doner.

### KK-20: `.gitattributes` ile satir sonlari sabit
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte

Windows'ta her `git add` LF/CRLF uyarisi uretiyordu. Bunsuz satir sonlari her
katkida bulunanin `core.autocrlf` ayarina baglidir ve sahte diff'ler gercek
degisiklikleri gurultuye gomer. Depo icinde LF sabit; `.bat/.cmd/.ps1` CRLF.

### KK-21: Disa bakan yuzey semadan sayilir, elle sayilmaz
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §2, §15

`test_arac_tanimlari_ingilizce` yalnizca `t.description`'a bakiyordu ve Turkceyi
elle yazilmis bir alt dize listesiyle ariyordu (" ve ", "dondurur", ...).
Iki bosluk da ayni anda patladi: `concept` parametresinin aciklamasi Turkce
kaldi (canli istemcide goruldu), cunku (a) parametre aciklamalari hic
denetlenmiyordu, (b) dizgedeki hicbir kelime listede yoktu.

**Karar:** yuzey semanin kendisinden sayilir - arac tanimi + tum input
property'leri + output semasindaki `$defs` ve ust duzey property'ler. Sezici
kelime siniri (`\b`) ile calisan bir Turkce islev-kelimesi kumesi ARTI Turkceye
ozgu harfler (ışğçöü). Sezicinin kendisi de olculur:
`test_turkce_sezici_bilinen_ornekleri_ayirt_ediyor` bilinen Turkce ve bilinen
Ingilizce dizgilerle sinanir; ilk fixture 13 Agustos'ta bulunan gercek kacagin
ta kendisidir.

Iki yeni enjeksiyon (input aciklamasi ve donus semasi aciklamasi Turkceye
cevrilir) korumanin iki yonunu de dogruluyor - 31/31.

Bkz. PATTERNS.md P-17.
### KK-22: Dil kontrolu kara listeden pozitif listeye tasindi
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §2, §5, §15

KK-21'de yuzeyi genislettim ama seziciyi kara liste olarak biraktim. Enjeksiyon
harness'i bunun yetmedigini ayni oturumda kanitladi: `"Ticker bulunamadi:
{ticker}"` enjeksiyonu **KORUMASIZ** dondu - dizgede ne Turkceye ozgu harf
vardi ne de listedeki bir kelime. Yani genisletilmis test o kacagi hala
goremiyordu.

**Karar:** iki katli kontrol, `tests/dil.py`:
1. Kara liste (Turkce harfler + sik islev kelimeleri) - ucuz on eleme.
2. **Pozitif liste** - `tests/kelime_dagarcigi.txt`. Disa bakan metindeki her
   kelime bu dosyada olmali. Tanimlayici gorunumlu tokenlar (ilk harften sonra
   buyuk harf: `NetIncomeLoss`, `USD`, `CIK`, `AAPL`) atlanir. Tanimadigi
   kelimede kirmiziya doner; dolayisiyla hangi dil oldugundan bagimsizdir.

Kapsam da genisledi: hata mesajlari semada gorunmedigi icin `src/` agacindaki
her `raise` ifadesi AST ile geziliyor (`test_hata_mesajlari_ingilizce`).

**Kabul edilen bedel:** yeni bir Ingilizce kelime kullanmak dagarcigi
guncellemeyi gerektirir. Bu bilincli - kontrolun "yazarin akil ettigi" kumeye
bagimli olmamasinin bedeli bu. Dagarcigin sunger haline gelmemesi icin
`test_kelime_dagarcigi_kullanilmayan_kelime_biriktirmiyor` olu kelimeleri
kirmiziya donduruyor.

Bkz. PATTERNS.md P-17.

### KK-23: Bos ust-kaynak yaniti basari sayilmaz, ikinci uca dusulur
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §3, §12

KO (CIK 0000021344) icin `companyconcept` ucu HTTP 200 + dogru `label` +
**bos `units.USD`** donduruyordu (346 bayt). Ham govdede `"units":{"USD":{}}` -
yani dizi beklenen yerde bos SOZLUK; bu, uretici tarafli bir artiga isaret
ediyor (bayat onbellek eski nesnenin tamamini dondururdu). Ayni etiket `companyfacts`
ucunda 144 satir. Arac bunu sessizce basari sayip `total_periods: 0`
donduruyordu - model bunu "sirket bunu raporlamiyor" diye okur.

**Olculdu, varsayilmadi** (`arac/tani.py --matris`): temel istek, tekrar,
onbellek-bypass (sorgu parametresi), farkli User-Agent, sikistirmasiz - besi de
bos. Ayni adres baska bir agdan dolu geldi. Yanitlarda `age`/`x-cache`/`etag`
basliklarinin hicbiri yok, yani mekanizma isimlendirilemiyor; kesin olan sey
sorunun BIZDE olmadigi ve konuma bagli oldugu.

**Karar:**
1. `companyconcept` sifir satir dondurdugunde `companyfacts` okunur (satir
   yapisi ayni: start/end/val/form/filed).
2. Hangi ucun cevapladigi yanitta yazar: `source_endpoint`. Gizli fallback
   olmaz - cagirici neyi okudugunu bilir.
3. Ikisi de bossa **hata firlatilir**. Bos bir basari, gercek "veri yok"
   cevabindan ayirt edilemez; asil sorun buydu.
4. Yedek yol yalnizca sifir satirda acilir - `companyfacts` birkac MB.

Uc enjeksiyon dogruluyor: yedege dusmeyi kaldir, yedegi her cagride calistir,
bos durumda hata yerine bos basari don.

Bkz. PATTERNS.md P-19.
### KK-24: Belgelenen dagitim yolu CI'da gercekten calistirilir
**Tarih:** 13 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §3, §9

README Docker + streamable-HTTP kullanimini vaat ediyordu; o yol hic
calistirilmamisti. SDK'nin `run_streamable_http_async` varsayilani
`host="127.0.0.1"` (imzadan olculdu, belgeden degil) - konteyner icinde bu,
yayinlanan portu olu birakir. Testler de yardim etmiyordu: arac fonksiyonlarini
dogrudan cagiriyorlar, HTTP tasimasina hic dokunmuyorlardi.

**Karar:**
- `Dockerfile` host'u ACIKCA verir: `host='0.0.0.0', stateless_http=True`.
- `tests/test_http_tasima.py` tasimayi bos bir portta ayaga kaldirir ve
  `tools/list`'i gercek HTTP uzerinden, el sikismasiz sorar. Bu ayni zamanda
  2026-07-28 spesifikasyonunun durumsuz cekirdegini kanitlar.
- CI'da `docker` isi imaji kurar ve konteyneri DISARIDAN sorgular.
- `test_sdk_varsayilani_hala_loopback` varsayimin kendisini sabitler: SDK
  varsayilani degisirse test kirmiziya doner ve Dockerfile yorumu gozden
  gecirilir.
- Enjeksiyon: Dockerfile'dan acik host kaldirilir, ilgili test kirmiziya doner.

Bkz. PATTERNS.md P-20.

### KK-25: Revizyon gecmisi ayri bir arac, ve revizyon "farkli deger" demektir
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §12

Tesla analizinde soyle bir sinir yazildi: "tum degerler en son sunulan
halleriyle alindi; SEC'e duzeltme sunulursa rakamlar degisir." Bu bilgi zaten
elimizdeydi - seri araci ayni donemin farkli dosyalamalardaki degerlerini
cekiyor, sonra dedup edip ATIYORDU. `sec_edgar_get_fact_revisions` artik onu
atmiyor.

**Iki ayrim testle sabit:**
1. **Tekrar revizyon degildir.** Bir 10-K uc yillik karsilastirma tasir; ayni
   deger her dosyalamada tekrar raporlanir. Tekrari revizyon saymak her donemi
   "revize" gosterir ve arac ise yaramaz olur. Sayilan sey FARKLI degerlerdir;
   tekrar sayisi `times_repeated` alaninda ayrica durur.
2. **Etiket farki revizyon degildir.** Ayni donem iki US-GAAP etiketinde farkli
   degerle gecebilir (takma ad birlestirmesi yuzunden gorunur olur). Ilk
   surumde bunlar revizyon sayiliyordu; test yakaladi. Gruplama artik
   `(etiket, donem_sonu, birim)`.

Her satir `accession_number` tasir - degisimin hangi dosyalamada oldugu
tiklanabilir.

### KK-26: Taksonomi onekli etiketler; `dei` erisimi
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §12

Rapordaki "piyasa verisi SEC'de yok" cumlesi tam dogru degildi. Olculdu
(`arac/tani.py TSLA --envanter`): companyfacts uc taksonomi tasiyor - `dei`,
`us-gaap`, `ffd`. `dei` icinde `EntityPublicFloat` (halka acik kismin piyasa
degeri, 10-K kapak sayfasi) ve `EntityCommonStockSharesOutstanding` var.
Sunucu her istegi `us-gaap` yoluyla kurdugu icin bunlara erisemiyordu.

**Karar:** etiketler `taksonomi:Etiket` seklinde nitelenebilir
(`dei:EntityPublicFloat`); onek yoksa `us-gaap` varsayilir, yani mevcut tum
cagrilar aynen calisir. Uc yeni takma ad: `public_float`, `shares_outstanding`,
`shares_diluted`. `list_available_concepts` artik `taxonomy` parametresi aliyor
ve yanitta **sirketin fiilen kullandigi taksonomileri** bildiriyor - model
tahmin etmek zorunda kalmasin. Olmayan taksonomi istenirse hata mevcutlari
listeler (§18/P-13).

**Olculdu ve CURUTULDU:** envanterde `SalesRevenueEnergyServices` gorununce
"kismi segment gorunurlugu var" denecekti; canli sorgu etiketin
**2018-01-31'de emekliye ayrildigini** ve verinin 2014-2018 arasinda bittigini
gosterdi. Guncel donem icin segment kirilimi companyfacts'te YOK; sirkete ozel
taksonomi de yok. Rapordaki "segment gorulemiyor" sinirlamasi gecerli.

### KK-27: Dosyalama metni ayri bir modul, ve icindekiler tablosu ilk tuzak
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §3, §16

Tesla raporunda dort ve besinci bosluk metinden geliyordu: kilavuzluk ve 2023
vergi kaleminin gerekcesi XBRL'de yok, dosyalamanin METNINDE var.
`sec_edgar_read_filing_text` bunu aciyor.

**Bagimlilik eklenmedi.** HTML->metin donusumu stdlib `html.parser` ile
(`src/edgar_mcp/belge.py`); BeautifulSoup cekirdek bagimliligini birkac satir
icin buyuturdu (KK-3).

**Uc karar, ucu de testle sabit:**
1. **Icindekiler tablosu bolum degildir.** "Item 7. ..." bir 10-K'da en az iki
   kez gecer. Bir baslik adayi, ancak ardindan `BOLUM_ESIGI` (400) karakterden
   fazla metin geliyorsa gercek bolumdur. Esik yetmediginde -- bazi
   dosyalamalarda icindekiler girisleri uzun aciklamalar tasir -- ikinci kural
   devreye girer: ayni baslik birden fazla kez geciyorsa EN UZUN blok secilir.
2. **Tablolar duz atilmaz.** Mali tablolar HTML tablosudur; hucreler ` | ` ile
   ayrilmazsa sayilar birbirine yapisir ve okunamaz.
3. **Sayfalama zorunlu.** Bir 10-K milyonlarca karakter; `max_characters` +
   `offset` + `has_more` ile parca parca verilir. Indirilen belge istemcide
   FIFO onbellege alinir (en fazla 3 belge) - sayfalama ayni belgeyi tekrar
   tekrar ister, her seferinde birkac MB indirmek SEC hiz sinirini yer.

Bes enjeksiyon dogruluyor: esigi kaldir, ilk eslesmeyi al, script atlamayi
kapat, sayfalamayi kaldir, onbellegi kapat.

**Dorduncu karar (ayni gun eklendi):** basliklar gercek dosyalamalarda HTML
TABLOSU icinde durur; metne cevrilince satir " | " ile baslar ve satir-basi
capasi tutmaz - o dosyalamalar "bolumsuz" gorunur. Regex satir basinda
`| > * - .` gibi isaretlere izin veriyor.
### KK-28: Bakim turu - onbellek katmani, bolum tekillestirme, eval set kapsami
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §2, §11

Uc kusur, ucu de canli kullanimda goruldu ya da olculdu:

**1. Ayristirma her cagride tekrarlaniyordu.** Istemci ham HTML'i onbellege
aliyordu ama metne cevirme her sayfa cevirmede yeniden yapiliyordu. Olculdu:
2,2 MB HTML -> **0,61 saniye**. Bir bolumu bes parcada okumak saniyeleri bosa
harciyordu.

**Karar:** onbellek istemciden sunucuya tasindi ve **cevrilmis metni** tutuyor
(`server._BELGE_METNI`, FIFO, 3 belge). Ham HTML artik hic saklanmiyor - metin
ondan ~20 kat kucuk. `srv` fixture'i onbellegi temizliyor: modul duzeyinde
durum testler arasi sizarsa "indirildi mi" olcumu anlamsizlasir.

**2. Bolum listesinde ayni kod iki kez cikiyordu.** Canli olcumde (TSLA FY2023
10-K) esikten gecen ikinci bir "Item 16" listenin BASINDA, ITEM 1'den once
goruldu - kapak sayfasindaki bir referans bolum sanilmisti.

**Karar:** liste kod bazinda tekillestiriliyor (`item 7`, `note 12`), ayni kod
birden fazla gecerse **en uzun blok** kaliyor. Alt dize aramasinda (farkli
kodlar ayni ifadeyi tasiyabilir) yine en uzun blok kazaniyor; ikisi ayri
testlerle korunuyor.

**3. Degerlendirme seti uc yeni araci kapsamiyordu.** Kendi kuralimiz "API'yi
genisletmek eval set bir bosluk gosterince acilir" diyordu; tersi de gecerli.
Set 15 soruya cikti ve `test_her_arac_degerlendirme_setinde_temsil_ediliyor`
artik kapsanmayan bir arac eklenmesini kirmiziya donduruyor.

### KK-29: 8-K govdesi ekte; ve iki hatam - olculmemis bir siralama kurali, elde birakilan bir prova
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §2, §4, §11

Tesla raporunun kapanmayan bosluklarindan biri teslimat adetleriydi: XBRL'de
yok, 10-K/10-Q metninde yok, **8-K'nin ekinde** var. `read_filing_text` iki
parametre kazandi:

- `document`: dosyalamadaki baska bir dosyayi oku. Yanit her cagride
  `available_documents` listesini tasiyor, boylece "bu dosyalama bos" sonucuna
  varmadan once nerede olduguna bakilabiliyor.
- `search`: bolum adini bilmeden metin icinde konum bulma. `search_hits[].position`
  dogrudan `offset` olarak geri verilebiliyor; `search_total_matches` kirpmadan
  bagimsiz gercek sayiyi bildiriyor.

**Hata 1 - olcmeden kural yazdim.** Ilk tasarim "en buyuk okunabilir dosya
aranan metindir" diyordu ve mock'u ben bu varsayima gore yazdigim icin test
kurala katildi. Gercek dosyalamayi (TSLA 8-K `0001628280-26-046717`) okuyunca
varsayim iki kez cokuyor: kapak sayfasi **26.572** bayt, icerigi tasiyan ek
**13.243** bayt (kapak satir ici XBRL isaretlemesiyle sisiyor), ve dizindeki en
buyuk `.htm` dosyasi **38.047** baytlik `R1.htm` - SEC'in XBRL
goruntuleyicisinin urettigi bir rapor, basvuru sahibinin yazdigi bir belge
degil. `index.json`'in `type` alani da yardimci olmuyor: her satirda
`"text.gif"`, yani belge turu degil ikon adi.

**Karar:** boyut siralamasi bir ipucu olarak kaldi ama karar sinyali olmaktan
cikti. Uretilen rapor dosyalari (`R\d+.htm`) ve gezinme sayfalari eleniyor,
ve modelin gercekten ihtiyaci olan sinyal ayri bir alan oldu:
`FilingDocument.is_primary`. Mock artik gercek `index.json`'un kopyasi -
boyutlar dahil. Ders P-4'un tekrari: mock'u varsayimina gore yazarsan test
varsayimini dogrular, kaynagi degil.

**Hata 2 - enjeksiyon adayini elde denedim.** Bir aday enjeksiyonu ("arama
toplam sayacini durdur") dosyaya elle uygulayip birakmisim; oturum bitti, iki
test bir sonraki oturuma kirmizi girdi. Harness yedek + kilit + `finally` ile
korunuyor, elle yapilan duzenleme hicbiriyle korunmuyor.

**Karar:** aday deneme isi de harness'tan geciyor - `enjeksiyon.py --aday <ad
parcasi>` yalnizca eslesen enjeksiyonlari calistirir, ayni yedek/kilit/geri
alma yolunu kullanir. Aday once listeye eklenir, sonra tek basina denenir.
Pattern olarak P-24.

Sekiz yeni enjeksiyon dogruluyor: uzanti filtresi, gezinme sayfasi elemesi,
uretilen rapor elemesi, siralama yonu, `is_primary` bayragi, `document`
parametresi, belge adi dogrulamasi + hata mesajinin dosya listesi, arama toplam
sayaci ve vurgu kirpmasi.

### KK-30: Cerceve (frames) araci - "ayni donem" bir varsayimdir, veriyle yalanlanir
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §12, §16, §18

`sec_edgar_compare_companies`, SEC'in `frames` ucunu kullanarak bir kavramin
BIR donemdeki tum sirketlerdeki degerini dondurur. Diger araclar tek sirket
hakkinda konusur; bu arac bir populasyon hakkinda konusur.

**Dort olcum, dordu de tasarimi belirledi (14 Agu 2026):**

1. **Cerceve "ayni donem" degil, "ayni takvim kovasi".**
   `us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2025Q1`
   cercevesinde Apple'in satiri **2024-12-29 / 2025-03-29** (kendi mali ikinci
   ceyregi). Ayni cercevede en erken bitis 2025-02-23, en gec 2025-05-04 -
   **yetmis gun**. Sirala-ve-karsilastir yapan bir model bunu gormezse
   esdeger olmayan donemleri esdeger sanar. Karar: her satir kendi
   `period_end`'ini tasir, ve yanit tum cercevenin
   `period_end_earliest`/`period_end_latest` araligini bildirir.

2. **Bilanco kalemi suresel cercevede YOK.** Olculdu:
   `us-gaap/Assets/USD/CY2025Q1` -> 404, `.../CY2025Q1I` -> dolu. Modelin bu
   ayrimi bilmesini beklemek P-12'dir; ikisi de deneniyor ve hangisinin
   cevapladigi `frame` alaninda yaziyor (KK-23'teki `source_endpoint` ile ayni
   ilke: gizli fallback yok).

3. **Cercevede olmamak "raporlamiyor" demek degil.** Bir sirket kavrami baska
   bir etiketle taglemis ya da mali donemi kovaya oturmamis olabilir. Istenen
   ticker cercevede yoksa sessizce dusurulmuyor, `missing_tickers` icinde
   sebebiyle birlikte donuyor.

4. **Sira, filtreden ONCE hesaplanir.** Uc sirket istendiginde "birinci olmak"
   o ucun icinde birinci olmak degildir; `rank` her zaman **tum cerceveye**
   gore verilir. Yoksa rakam gercekte olmayan bir liderlik anlatir.

**Takma ad birlestirmesi burada YAPILMAZ** (KK-8'in bilincli istisnasi): bir
cerceve tek etiket altinda kurulur, iki etiketin cercevelerini birlestirmek
farkli sirket kumelerini ayni listeye karistirirdi. Aday etiketler sirayla
denenir, cevaplayan `resolved_tag` olarak yaziliyor.

Cerceve yaniti buyuk (olculdu: 2.543 sirket), bu yuzden FIFO onbellek
(`_CERCEVE`, 3 cerceve). On enjeksiyon dogruluyor.

**Harness'ta bulunan kusur:** bu araca eklenen ilk PARAMETRELI test, enjeksiyon
harness'inin gozunden kacti - pytest `test_x[2025Q1]` yazar, harness duz
esitlik ariyordu ve calisan bir korumayi "KORUMASIZ" diye raporladi. Duzeltildi
(`yakalandi()`), testle sabit. Pattern olarak P-25.

### KK-31: Boyutlu XBRL - segment verisi, ve "toplam" diye bir kesinlik yok
**Tarih:** 14 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §3, §12, §18

Tesla raporunun kapanmayan iki boslugu (segment kirilimi, birim satis) XBRL
REST API'sinde yok cunku o uclar boyutlu fact tasimiyor. SEC kendi API sayfasi
bu uclari "aggregate facts that ... **apply to the entire filing entity**" diye
tarif ediyor; segment fact'i tuzel kisinin bir PARCASINA ait. SEC "dimensional"
demiyor - bu alintiyla desteklenen bir cikarim, birebir teyit degil, ve
dokumantasyonda boyle yaziyor.

Iki yeni arac: `sec_edgar_list_fact_dimensions` (kesif - hangi eksen, hangi
uyeler) ve `sec_edgar_get_dimensional_facts` (veri). Kesif AYRI arac, cunku
"hangi eksenler var" ile "su etiketi su eksende getir" farkli anlarda sorulur
ve kesif cagrisi ucuz olmali (`list_available_concepts` ile ayni kalip).

**Kaynak: `<mnemonic>-<tarih>_htm.xml`.** Ilk cerceveme gore bu "dosyalayanin
kendi XBRL'i" idi; **yanlisti.** SEC'in dagitim spesifikasyonu (PDS Technical
Specification, Mart 2025, "DRAFT") bu dosyayi `FilingSummary.xml`, `R*.htm` ve
`MetaLinks.json` ile AYNI listede - "EDGAR-generated" ciktilar arasinda -
sayiyor: "{name}_htm.xml — Only when Inline XBRL .htm document present". Fark
gercek ama kucuk: degerler ve context'ler dosyalayanin, kabuk SEC'in. R-dosyasi
ise bir RENDER (yerlesim, olcek basligi, cozulmus etiket). Dokumantasyon artik
bunu boyle soyluyor.

`<accession>-xbrl.zip` "does not contain any processing outputs" diyor, yani
`_htm.xml`'i ICERMEZ - "tek istekte hepsini al" fikri bu yuzden dustu.

**Geriye donuk kapsam:** inline XBRL zorunlulugu kademeli geldi (SEC Release
33-10514): buyuk hizlandirilmis dosyalayanlar 2019-06-15, hizlandirilmis
2020-06-15, digerleri 2021-06-15 sonrasi biten donemler. Oncesinde `_htm.xml`
yok; instance'i dosyalayan sunuyordu. Yedek yol var ve linkbase'leri
(`_cal/_def/_lab/_pre`) eliyor.

**En tehlikeli tuzak: mukerrer sayim.** "Boyutsuz fact = toplam, boyutlu
fact'ler = kirilim" kurali gercek dosyalamalarda TUTMUYOR. Bazi dosyalamalarda
toplam fact'i hic yok; bazilarinda toplam KENDISI boyutlu (domain/parent uyeye
isaretlenmis - XBRL US'in gelir rehberi bu yapiyi acikca oneriyor: "This
structure ... prevents double counting"). XBRL US Data Quality Committee'nin
**DQC_0150** kurali tam olarak uye toplamlarinin raporlanan toplamla tutup
tutmadigini denetliyor; boyle bir kural varsa gercek dosyalamalar bunu ihlal
ediyor demektir.

**Karar:** arac sessizce toplama YAPMAZ ve hangisinin dogru oldugunu SECMEZ.
Tek eksen istendiginde uye toplami ile tuzel kisi geneli toplami yan yana
donuyor (`reconciliation`), fark gorunur. Uc incelik testle sabit:
1. Cok boyutlu fact (segment VE cografya) toplama GIRMEZ - o bir kirilim
   parcasi degil kesisimdir.
2. `xsi:nil` toplam **0 degildir**; `consolidated_value` None doner. "Toplam
   raporlanmadi" ile "toplam sifir" ayri seyler.
3. Toplanacak sayisal uye kalmadiginda mutabakat satiri hic uretilmez;
   "members_sum = 0" demek sifirlarin toplandigini soylerdi.

**Diger olculmus/kaynakli tuzaklar:** `decimals` bir CARPAN degil hassasiyettir
(deger zaten tam olcekli); boyutlar `entity/segment` ICINDE ya da `scenario`
icinde durabilir (yalnizca birine bakmak bazi dosyalamalarda tum kirilimi
gorunmez yapar); `typedMember` explicit'ten ayri kod yolu ister; bir context
birden fazla boyut tasiyabilir.

**Bagimlilik eklenmedi** (KK-3): stdlib `xml.etree.ElementTree`, tek gecis
`iterparse`. `lxml`'in kazandirdigi hiz; darbogaz 2,7 MB'i INDIRMEK.
Ad alani onekleri `start-ns` olaylarindan okunuyor ki QName'ler dosyalamada
gorulen haliyle (`us-gaap:Revenues`) donsun - uydurma onek uretilmiyor.

**OLCULDU (14 Agu 2026 aksami) - zincir kapali.** Soru suydu: `id="f-1663"`
degerleri dosyalayanin inline belgesindeki `ix:` eleman id'leriyle ayni mi?
`arac/tani.py TSLA --ixbrl` TSLA FY2025 10-K'sinda olctu: instance'tan alinan
ilk 200 fact id'sinin **200'u de** 2,39 MB'lik inline belgede birebir bulundu
(%100). Yani `fact_id` SEC'in ayiklamasina ozgu bir sayac degil; dosyalayanin
kendi belgesindeki isaretli parcanin kimligi. Dondugumuz her rakam oraya kadar
izlenebilir ve sema aciklamasi artik bunu soyluyor.

**Ilk calistirmada olcum aracinin kendisi kusurluydu:** id'ler regex ile
toplaniyordu ve `id=` niteligi birimlerde de var - `fsdsubscription` fact
sanildi. Sonucu degistirmedi ama arac, olctugunu iddia ettigi seyi tam
olcmuyordu. Artik instance ayristirilip yalnizca `fact_id` tasiyan olgular
sayiliyor: olculen sey, aracin GERCEKTEN dondurdugu id'ler.

### KK-32: Dusman gozle denetim - dokuz kusur, ikisi kritik
**Tarih:** 15 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §2, §3, §11

Loom videosundan once repo, "musterinin kidemli muhendisi" rolunde bir ajana
okutuldu: iddia edilen ozeni cürüten seyler bul. Dokuz gecerli kusur cikti,
ikisi kritik, ve hicbiri sema/tip/lint duzeyinde gorunur degildi. Hepsi
duzeltildi, hepsi testli, hepsi enjeksiyonla dogrulandi (17 yeni enjeksiyon).

**Kritik 1 - gizli blok filtresi belgeyi yutuyordu.** `belge.py` gizli
elemanlari bir yigina koyuyor ve kapanis etiketini YALNIZCA yiginin tepesiyle
esleserse cikariyordu. Gercek EDGAR HTML'inde `<td>`/`<tr>` kapanislari
atlanir ve `<img>` gibi kapanmayan elemanlar vardir; ikisinde de sayac bir daha
sifirlanmiyor ve belgenin GERI KALANI gizli sayiliyordu. Uretildi: 2,4 MB'lik
bir belge **3 karaktere** dusuyor, arac HTTP 200 ile `available_sections: []`
donduruyordu - "bu dosyalama bos". Bu tam olarak P-19. Ic ice ayni ad
(`<div><div>`) ise ters yonde caliyordu: yigin erken bosaliyor ve gizli iXBRL
basligi metne SIZIYORDU.
**Karar:** tarayicilarin yaptigi - yigin (ad, gizli) ciftleri tutar, kapanis
geriye dogru aranir, kapanmayan elemanlar yigina hic girmez, `<td>a<td>b` gibi
ortulu kapanislar uygulanir. Ustune bir emniyet agi: filtre belgenin 1/200'unden
azini birakiyorsa filtre yaniliyordur, metin FILTRESIZ yeniden uretilir.
Gurultulu ama dolu metin, sessizce bos metinden iyidir.

**Kritik 2 - sayfalama siniri mutabakata sizmisti (P-27).** Uye toplami
dondurulen SAYFA uzerinden, konsolide deger dosyalamanin TAMAMI uzerinden
hesaplaniyordu. `limit=1` ile ayni dosyalama "20,7 milyar dolarlik fark var"
diyordu; varsayilan 40 satir gercek bir 10-K segment sorgusu icin zaten yetmez,
yani bu uydurma fark sahada gorulurdu. Hesaplanan her sey artik TUM eslesen
kume uzerinden; sayfa siniri yalnizca gosterimi etkiliyor.

**Yedi kusur daha:**
1. **Ceyreklik mali yil etiketi bir yil kayiyordu.** Kayma yillik capalardan
   turetilip her satira uygulaniyordu; Ocak/Subat'ta biten mali yillarda
   ceyrekler onceki takvim yilinda biter. WMT'nin FY2026'si icin arac yila
   FY2026, KENDI ilk ceyregine FY2025 diyordu. Artik donem sonu, sirketin yil
   sonu tarihine gore hangi mali yila dustugu hesaplanarak etiketleniyor
   (52/53 haftalik takvimler icin ±10 gun tolerans).
2. **Anlik (bilanco) kayitlar donem filtresinden yanlis geciyordu.**
   `total_assets` + `annual` her CEYREK sonu bakiyeyi donduruyor, ayni mali yil
   dort kez tekrarlaniyordu; `public_float` + `quarterly` ise HTTP 200 ile BOS
   liste donduruyordu - KK-23'un tam olarak yasaklandigi durum.
3. **Revizyonda "en son deger" yanlisti.** Farkli degerlerin ILK GORULME
   sirasindaki sonuncusu aliniyordu; 100 -> 90 -> 100 gibi geri alinan bir
   revizyonda arac "en son 90" derken seri araci 100 gosteriyordu. Iki arac,
   ayni gercek, iki cevap. Artik en son DOSYALANAN satirdan okunuyor.
4. **Boyutlu fact'lerde takma ad cift sayiyordu.** Aday etiketlerin hepsi kabul
   ediliyordu; bir dosyalama ayni segmenti iki etiket altinda tasirsa uye
   toplami konsolidenin iki katina cikiyordu. Seri aracinda birlestirme DOGRU
   (KK-8), burada cift sayim; tek etikete kilitlendi.
5. **Ust-kaynak hatalari cig gidiyordu.** Yalnizca 404 ele aliniyordu; SEC'in
   gercek kisitlama yaniti (HTTP 403 + HTML govde) `HTTPStatusError` ya da
   `JSONDecodeError` olarak modele ulasiyordu. Artik ne yapilacagini soyleyen
   mesajlar var (§18/P-13). Dil kapisi bunlari GORMUYORDU - mesajlar bir
   yardimci fonksiyona tasininca `raise` dugumunu gezen tarayicinin disinda
   kaldilar; tarayici bir seviye dolayli cagriyi da kapsayacak sekilde
   genisletildi (P-17'nin ucuncu tekrari).
6. **`companyfacts` onbellegi sinirsizdi.** Olculdu: 11 MB JSON -> 45 MB
   yerlesik. Diger her onbellek gerekcesiyle sinirliydi; en buyugu tek sinirsiz
   olandi. `submissions` ise hic onbelleklenmiyor, her cagride yeniden
   iniyordu; `index.json` cagri basina IKI kez isteniyordu. Ucu de duzeltildi.
7. **Uc dokuman iddiasi kodda yoktu:** "refuses to start without
   SEC_USER_AGENT" (istemci TEMBEL kuruluyordu - konteyner ortam degiskeni
   olmadan aciliyor ve dokuz araci ilan ediyordu), "says which facts it
   excluded" (hicbir alan soylemiyordu), ve iki README de "on soru" diyordu
   (on sekiz). Ilki kodla, ikincisi alanlarla, ucuncusu iki yeni testle
   kapatildi - README artik soru sayisi ve takma ad listesi icin testli.

**Ders:** bunlarin hicbiri yeni bir sinif degil; hepsi kendi `PATTERNS.md`
listemizdeki bir maddenin tekrari (P-4 fixture'lar, P-19 bos basari, P-14
dokuman, P-17 yuzey). Kontrol listesini yazmis olmak, ona uymak degil - ve
denetimi bir baskasina yaptirmak, listeyi kendi kendine okumaktan daha etkili
oldu.

### KK-33: Ilerleme bildirimi - yalnizca bekleten araclarda
**Tarih:** 15 Agustos 2026 · **Durum:** yururlukte · **Standart:** §16, §19

Spesifikasyon yuzeyi tarandi (2026-07-28): sunucunun `tools` disinda
sunabilecegi her yetenek tek tek degerlendirildi ve **yalnizca biri** bu
sunucuya uygun cikti.

**Eklenen: progress.** `read_filing_text`, `compare_companies`,
`list_fact_dimensions` ve `get_dimensional_facts` artik `ctx.report_progress`
cagiriyor. Gerekce bu araclarin GERCEKTEN bekletmesi: 2,7 MB'lik bir XBRL
instance'i indirip ayristirmak, 2,4 MB'lik bir dosyalamayi metne cevirmek,
2.543 satirlik bir cerceve indirmek. Spesifikasyon bunu MAY diyor ve yalnizca
istemci `progressToken` yolladiysa gonderiliyor; token yoksa SDK'nin
`report_progress`'i sessizce hicbir sey yapmiyor.

**Eklenmeyenler ve neden:** `resources`, `prompts`, `completions`,
`elicitation`, `resource subscriptions`, `tools/list` sayfalamasi - dokuz araci
olan salt-okunur bir veri sunucusu icin gosteris olurdu. Sayfalama icin
spesifikasyonda esik yok, dokuz arac tek yanitta doner. Daha onemlisi:
**`logging`, `sampling` ve `roots` bu spesifikasyon revizyonunda DEPRECATE
edildi** (SEP-2577); simdi eklemek "degisiklik gunlugunu okumadim" sinyali
verirdi.

**Iki olcum, ikisi de kod yazmadan once yapildi:**
1. **Iki ayri `Context` sinifi var.** Arac katmani yalnizca
   `mcp.server.mcpserver.context.Context`'i taniyor;
   `mcp.server.context.Context` ile yazilinca sunucu ACILMIYOR - sema uretimi
   `PydanticInvalidForJsonSchema` ile patliyor. Ikisi de "Context" adinda ve
   ikisinde de `report_progress` var.
2. **`ctx` parametresi input semasina GIRMIYOR** (olculdu): SDK tur ipucundan
   buluyor ve `skip_names` ile semadan cikariyor. `Context | None = None`
   yazimi da taniniyor - testler arac fonksiyonlarini dogrudan cagirdigi icin
   opsiyonel olmasi sart.

Ucuncu bir sey de teyit edildi: `ValueError` firlatmak DOGRU yol. SDK v2
istisnayi yakalayip `isError=True` + `str(e)` olarak donduruyor, yani modele
ulasip duzeltme sansi veriyor. `MCPError` ise protokol hatasi olur ve model
onu HIC gormez - bu depoda hicbir yerde kullanilmiyor, kullanilmamali.

Uc test sabitliyor: ilerleme gercekten bildiriliyor mu, baglam yokken arac
calisiyor mu, ve `ctx` hicbir aracin semasinda gorunuyor mu.

### KK-34: Ikinci denetim turu - dun geceki duzeltmelerin ICINDE dort kusur
**Tarih:** 15 Agustos 2026 · **Durum:** yururlukte · **Standart:** §1, §2, §3

KK-32'deki denetim dokuz kusur bulmustu ve hepsi ayni gece duzeltilmisti.
Videodan once ikinci bir denetim yapildi, bu kez **yalnizca o duzeltmelere**
bakildi. Dort kusur daha cikti, ikisi kritik - yani duzeltmelerin kendisi yeni
hata uretmisti. Ders acik: en taze kod en riskli koddur, ve bir duzeltmeyi
"bitti" saymak icin ayrica denetlemek gerekiyor.

**Kritik 1 - metin cikarimi SURECTEN SURECE farkli sonuc veriyordu (P-28).**
`_ORTULU_KAPANIS` degerleri kume yazilmisti ve dongu ilk eslesmede duruyordu.
CPython string hash'ini surec basina rastgelelestirdigi icin kumenin iterasyon
sirasi her calistirmada degisiyor: `<tr>` bir `<td>` aciken geldiginde
tarayici IKISINI de kapatir, kod hangisi once gelirse onu kapatiyordu. `td`
once gelirse disaridaki gizli `tr` yiginda asili kaliyor ve tablonun geri
kalani yutuluyordu. **Olculdu: PYTHONHASHSEED 0/2'de mali tablo geliyor, 1/3'te
bos.** Ustelik ikinci bir hata bunu gizliyordu: baslangic etiketleri gizli blok
ICINDE de ayirici yaziyordu, cikti uzun kaliyor ve dun gece eklenen "yutma
emniyet agi" HIC devreye girmiyordu. Sunucunun kendi tanimi "deterministic tool
calls" diyor; dort surecten birinde dogru degildi.

**Kritik 2 - 52/53 haftalik takvimlerde yil sonu Aralik/Ocak arasinda oynar.**
Dun eklenen `_fy_sonuna_gore_yil` dogruydu ama iki cagri yeri onu kullanmiyordu:
sinir donemin KENDI takvim yilinda kuruluyordu. Aralik'ta biten bir yil, Ocak'a
turetilmis bir yil sonuna ~360 gun uzak dusuyor, tolerans hic tutmuyor. Sonuc
(Kellanova'nin gercek donem sonlariyla uretildi): iki ardisik mali yil AYNI
etiketi aliyor (`fiscal_year=2021` iki kez) ve yil sonu bilancolarinin yarisi
sessizce eleniyordu - `total_periods: 3, has_more: false`, yani KK-23'un
yasakladigi "kirpilmis basari".

**Iki kusur daha:**
1. **`member` filtresi mutabakata siziyordu** - P-27 `limit` icin
   duzeltilmisti, kardes parametre ayni yoldan giriyordu. Tek bir uye
   istendiginde o uyenin degeri tuzel kisi geneli toplamiyla karsilastiriliyor
   ve tam tutan bir dosyalama "20,7 milyar dolarlik fark" bildiriyordu - ayni
   sayi, ayni buyukluk, farkli yol. Artik iki liste var: cagirana donen
   (axis+member filtreli) ve mutabakata giren (yalnizca axis filtreli).
2. **`filing_document` yeni hata yolunu ATLIYORDU.** KK-32 §5'te `_get`
   duzeltilmisti ama `www.sec.gov/Archives`'e giden tek metot bu ve SEC'in
   "Undeclared Automated Tool" engel sayfasini gorecek en olasi yer orasi.
   Model cig `HTTPStatusError` aliyordu. Durum kontrolu ortak bir metoda
   tasindi. Ayrica SEC kisitlamayi bazen HTTP **200** ile de yapiyor; engel
   sayfasini metne cevirip dondurmek "dosyalama bu kadarmis" demek olurdu, o da
   ayri bir kontrolle yakalaniyor.

Yedi yeni enjeksiyon dogruluyor. Determinizm testi digerlerinden farkli
calisiyor: bes ayri ALT SUREC baslatip farkli `PYTHONHASHSEED` degerleriyle
ayni girdiyi cevirtiyor ve bes ciktinin ayni olmasini sart kosuyor - bu hata
sinifi tek surecin icinden gorunmuyor.

### KK-35: Uc kor nokta kapatildi - tam metin arama, eski dosyalama akislari, etiketler

15 Agu 2026. Aracin yapabildikleri sayilirken yedi sinir yazilmisti; bunlarin
uc tanesi ayni gun kapatildi. Ucu de "veri yok" degil "veriye giden yol yok"
sinifindaydi.

**1. Tam metin arama (`sec_edgar_search_filings`).** Sunucu bir sirketi
ADIYLA sorabiliyordu ama bir IFADEYI soramiyordu: "hangi sirketler gumruk
tarifesinden bahsetti" cevapsizdi. EDGAR'in tam metin ucu
(`efts.sec.gov/LATEST/search-index`) bunu veriyor. Olculen sozlesme:

- Yanit Elasticsearch bicimli. Bir vurusun `_id` alani
  `0001193125-12-081990:d279413dex1050.htm` - yani **erisim numarasi ve belge
  adi birlikte**. Ikisi de `read_filing_text`'in parametreleri; ayirmadan
  dondurmek modele islenmemis bir dizge birakirdi.
- **Vurus dosyalama degil BELGEDIR.** Olculen ornekte Tesla'nin en eski
  "tariff" esleşmesi 10-K'nin kendisi degil, icindeki bir EK ("SUPPLY
  AGREEMENT"). Bunu soylemeyen bir arac aciklamasi, modeli yillik raporda
  olmayan bir cumleyi aramaya gonderirdi.
- `hits.total.relation` `eq` degil `gte` olabiliyor: sayi bir ALT SINIR.
  `total_is_exact` alani bu ayrimi tasiyor.
- `from + size <= 10000`. Asildiginda SEC sonuc degil hata GOVDESI donuyor
  ("Result window is too large..."). Bu yuzden `offset` semada 9900'de
  sinirli ve `hits` icermeyen govde bos sonuc degil hata sayiliyor.

**Kaynaklar arasi celiski, kayda geciriliyor.** SEC kendi sayfasinda
(sec.gov/edgar/search/, 15 Agu 2026) "the full text of electronic filings since
2001" diyor. Olcum bunu tam dogrulamiyor: 1996-2000 araligindaki 10-K'larda
"revenue" aramasi 14 sonuc dondu (en eskisi 1999-03-31). Yani 2001 oncesinden
de birkac belge indekste var, ama sayi bir taramayi tasiyacak buyuklukte degil.
Dogru ifade "2001 oncesi yok" degil, "2001 oncesi icin SIFIR SONUC hicbir sey
kanitlamaz". Bu, sonucu bos donen ya da 2001 oncesine uzanan her cagrida
`coverage_note` olarak yanitin icinde gidiyor - README'de degil, cunku modelin
okudugu yer yanit.

**2. Eski dosyalama akislari (`include_older`).** SEC `filings.recent` alanini
~1000 dosyalamada kesip gerisini `filings.files[]` altindaki ayri JSON'lara
koyuyor. Olculdu: TSLA'nin recent akisi 1.053 kayitla ancak 2018-05-07'ye
iniyor, tek ek dosyasi 1.096 kayitla 2005-02-17'ye. Yani "son dosyalamalar"
aktif bir dosyalayanda son BIRKAC YIL demek. Onceki surum bu akislarin
varligini bildiriyordu ama okuyamiyordu.

Olculen ve koda giren ayrintilar:
- Ek dosyalar ust duzeyde `recent` ile **ayni paralel dizi bicimini** tasiyor,
  saran nesne yok.
- `primaryDocument` anahtari bulunmayabiliyor. Bu yuzden `Filing.
  primary_document_url` artik `None` olabiliyor ve `read_filing_text` birincil
  belge adini bilmedigi dosyalamada en buyuk okunabilir dosyayi seciyor -
  **ve bunu `primary_document_known: false` ile soyluyor.** 14 Agu 2026'da
  "en buyuk dosya icerigi tasir" varsayimini olcup yanlislamistim; ayni
  varsayimi sessizce geri getirmemek icin isaret alani sart.
- En fazla dort ek dosya okunuyor (~5000 dosyalama). Sinir SESSIZ DEGIL:
  `older_feeds_skipped` okunmayanlari sayiyor.
- Birlesik liste tarihe gore siralaniyor; iki akisin kendi ic sirasi
  birlestirildiginde dogru sirayi vermez.
- `_dosyalama_bul` da eski akislari tariyor. Aksi halde arac kendi
  dondurdugu erisim numarasini okumayi reddederdi.
- Ek akislar AYRI onbellekte (`_extra_cache`). Paylasilan onbellekte dort ek
  dosya, 1-2 MB'lik ana submissions kaydini disari atiyordu.
- Form turu karsilastirmasi artik buyuk/kucuk harf duyarsiz: `10-k` yazan bir
  cagri eskiden bos liste donuyordu, yani "bu sirket hic 10-K vermemis".

**3. Insan okunur adlar (etiket linkbase'i).** `tsla:OperatingLeaseVehicles
Member` gibi QName'ler dosyalamanin kendi etiket linkbase'inde
(`*_lab.xml`) insan okunur karsiliklariyla duruyor. Olculen yapi (TSLA FY2025,
1.211.922 bayt): `link:loc` QName'i, `link:label` metni tasiyor, ikisini
`link:labelArc` **bagliyor**. Kod bu yayi okuyor; `loc_`/`lab_`
isimlendirmesine GUVENMIYOR - o bir uretici aliskanligi, spesifikasyon kurali
degil (bir enjeksiyon tam bu kestirmeyi deniyor ve test kirmizi donuyor).

- Ayni eleman birden fazla rolde etiketli olabiliyor; standart rol tercih
  ediliyor, `documentation` rolu (tanim paragrafi) bilincli olarak disarida.
- Onek uyusmazligina karsi yalnizca TEK ANLAMLI yerel adlar yedek olarak
  kullaniliyor. Iki farkli QName ayni yerel adi farkli etiketle tasiyorsa
  hicbir sey secilmiyor: yanlis etiket, etiketsizlikten kotudur.
- Etiket bir SUS PAYIDIR: linkbase yoksa ya da bozuksa adlar QName olarak
  donmeye devam ediyor, cagri dusmuyor. `label_source` etiketlerin hangi
  dosyadan geldigini (ya da gelmedigini) soyluyor.
- Maliyet gercek: olculen dosyada instance 2,68 MB, linkbase 1,21 MB - yani
  yaklasik yarim kat. Bu yuzden `include_labels` kapatilabilir.

**Olculmemis olan, acikca:** ayristirici GERCEK bir linkbase dosyasina karsi
bu makinede calistirilamadi (konteynerden sec.gov'a dogrudan cikis yok; yapisi
canli olctugum ORNEKLERDEN turetildi). Bunun icin `arac/tani.py TICKER
--etiket` modu eklendi: dosyanin tamamini indirip kac QName cozuldugunu ve
dosyalamada fiilen kullanilan eksen/uyelerin kacinin etiketlendigini sayiyor.
Oran dusuk cikarsa duzeltilecek yer ayristiricidir - ve `include_labels`
varsayilani yeniden dusunulmelidir.

Yirmi iki yeni enjeksiyon bu uc grubun korumalarini dogruluyor.

### KK-36: `.env` yuklemesi sessizce hicbir sey yapabiliyordu

15 Agu 2026, v33 kurulumu sirasinda. Iki ayri kusur ust uste bindi ve
kullaniciya tek bir yanlis belirti gosterdi: "SEC_USER_AGENT ... is required".

**1. Guncelleme komutu `.env`i sildi.** Verdigim `robocopy ... /MIR /XD .git
.venv __pycache__ ...` satiri klasorleri hariç tutuyordu ama dosyalari degil.
`/MIR` hedefte fazladan duran her dosyayi siler; `.env` gitignore'da oldugu icin
kaynakta yoktu. Cikti bunu `*EXTRA File 449 ...\.env` diye yazmisti, yani
sessiz bile degildi - okunmadi. Duzeltme komut tarafinda: `/XF .env`.

**2. Dosya geri konunca da okunmadi.** `arac/ortam.py` `python-dotenv` yoksa
`return` ediyordu. Bagimlilik gercekten opsiyonel (sunucu ortami kendisini
calistiran uygulamadan alir - KK-11), ama opsiyonel olan sey bagimliliktir,
YUKLEMENIN KENDISI degil. Iki bagimsiz durum ayni sessiz yola cikiyor:
sanal ortam disindaki Python ile calistirmak, ve PowerShell'in
`Out-File -Encoding utf8` komutunun dosya basina BOM koymasi (ilk anahtar
`﻿SEC_USER_AGENT` olarak okunur ve hicbir zaman eslesmez).

Yukleyici artik kendi bagimliliksiz ayristiricisini tasiyor, `utf-8-sig` ile
cozuyor ve `setdefault` semantigi kullaniyor - kabukta elle verilmis bir
degisken dosyadaki eski degerle ezilmiyor.

**Ic denetimden cikan ayrica bir ders.** Ilk yazimda BOM'u IKI yerde ele
almistim: hem `utf-8-sig` ile hem satir ayristiricisinda `lstrip`. Enjeksiyon
harness'i encoding korumasini `KORUMASIZ` diye raporladi - cunku birini bozmak
otekini devrede biraktigi icin hicbir test kirmiziya donmuyordu. Yedeklilik
burada guvenlik degil, olculemezlik uretiyor. `lstrip` kaldirildi; BOM tek
yerde, ve o yer artik sinaniyor.

P-30 olarak kayda gecti. Uc yeni enjeksiyon dogruluyor.

### KK-37: Tablo yapisi (madde 2) ve 2019 oncesi olcumu (madde 6)

15 Agu 2026. Yedi sinirdan ikisi daha kapandi; biri kod, oteki yalnizca olcum
isiydi ve ikisi de "veri yok" degil "veriye giden yol dolambacli" sinifindaydi.

**Madde 2 - `read_filing_text(tables=true)`.** Adetler (teslimat, uretim, ASP)
XBRL'de yok, metinde var; ama metinde tablo ` | ` ile birlestirilmis hucrelere
donusuyor ve sutunlari hizalamak modele kaliyordu. Sirkete ozel bir ayristirici
yazmak yerine YAPI donduruluyor, yorum modele birakiliyor - EDGAR'da tablo
bicimi dosyalayandan dosyalayana degistigi icin bu daha az kirilgan.

Tasarim kararlari ve sebepleri:
- **Tek gecis.** Tablolar metinle ayni ayristirmada toplaniyor. Ikinci bir
  gecis daha basit olurdu ama tablonun metindeki KONUMU kaybolurdu; o konum
  olmadan "su an okudugun parcanin tablolari" sorusu sorulamaz ve model
  ilgisiz bir tabloyu okudugu pasaja ait sanar.
- **Bosluk sadelestirmesi regex zincirinden tek gecise tasindi.** Konumlar ham
  metinde olculuyor, sadelestirme karakter siliyor; iki ayri uygulama zamanla
  birbirinden ayrilir. Simdi tek uygulama var ve konumlar onunla tasiniyor.
  Davranisin BIREBIR ayni kaldigini bir test her fixture uzerinde eski regex
  zinciriyle karsilastirarak sabitliyor.
- **Yerlesim tablolari elenir ama SAYILIR.** EDGAR sayfa duzeni icin de tablo
  kullaniyor; tek satir/tek sutun olanlar veri tasimiyor. Elemek dogru, sessiz
  elemek degil - `layout_tables_skipped` var.
- **Ic ice tablolar ayri ayri doner ve ic tablonun metni dis hucreye
  KOPYALANMAZ.** Ayni rakamlari iki tabloda birden dondurmek, toplam alan bir
  modele veriyi iki kez saydirirdi.
- Satir/hucre sinirlari kendilerini soyluyor (`total_rows`, `rows_truncated`,
  `cells_truncated`).

**Bu is sirasinda ONCEDEN VAR OLAN bir hata bulundu.** Ortulu kapanis kurali
(`<td>a<td>b`) tablo sinirini asiyordu: ic tablonun `<tr>`'si DIS tablonun acik
`<td>`'sini kapatiyordu. Tarayicilar bunu yapmaz - ic tablo yeni bir baglam
acar. Sonuc olculdu: dis tablonun satirlari tumden kayboluyor ve METIN de
bozuluyor. Tablo modu yazilmasaydi bu hata gorunmezdi; yeni bir yuzey acmak,
eski yuzeydeki hatayi gorunur kildi.

**Madde 6 - 2019 oncesi: sinir varsayimdi, olculdu.** Dokumantasyon "2009-2019
arasi dosyalayanin instance'i okunuyor ama bu hic sinanmadi" diyordu. TSLA'nin
Subat 2012'de dosyaladigi FY2011 10-K'si uzerinden olculdu:
- `_htm.xml` YOK (inline XBRL oncesi), dosyalayanin sundugu `tsla-20111231.xml`
  **768.935 bayt** var - yani yedek yolun aradigi dosya gercekten orada.
- Instance boyutlu gercekleri MODERN dosyalamayla ayni yapida tasiyor:
  `entity/segment` icinde `xbrldi:explicitMember`, ve ayni anda iki eksene
  bagli context'ler.
- Etiket linkbase'i (208.484 bayt) da var ve bir tasarim kararini dogruladi:
  2011 dosyasi **hic onek bildirmiyor** (`<loc>`, `<label>`, `<labelArc>`
  varsayilan ad alaninda) ve konumlarini `us-gaap_Assets`, etiket kaynaklarini
  `us-gaap_Assets_lbl` diye adlandiriyor. Yani `loc_`/`lab_` kalibina bakan bir
  okuyucu bu dosyada HICBIR etiket cozemezdi; yayi takip etme karari (KK-35)
  burada tek calisan yol.

Asil sinir daha geride ve kaldirilamaz: XBRL 15 Haziran 2009'dan sonra biten
donemlerden itibaren kademeli zorunlu oldu; oncesinde etiketli veri hic yok.
O dosyalamalarda cevap tumuyle metin araclarinda.

**Arac katmani olcumu hala eksik:** kullanicinin masaustundeki MCP sunucusu
guncellenmeden eski surumu calistiriyor ve eski surum `recent` akisinin
disindaki bir erisim numarasini acamiyor. v34 acabiliyor (KK-35 madde 2);
Claude Desktop yeniden baslatildiginda `sec_edgar_list_fact_dimensions(ticker=
"TSLA", accession_number="0001193125-12-081990")` cagrisi bunu uctan uca
gosterecek. Veri tarafi olculdu, arac tarafi olculmedi - ikisi ayri ayri
yaziliyor.

On bir yeni enjeksiyon tablo korumalarini dogruluyor. Ucu ilk turda
"KORUMASIZ" dondu ve ucu de testin ne olctugunu duzeltti: bolum kaydirmasi
sifirdan baslayan bir bolumde kimlik islemiydi, gizli tablo zaten bos
kaliyordu, kapanmamis tablo `</body>` sayesinde baska bir yoldan bitiyordu.
Harness bir kez daha testin kendisini denetledi.
