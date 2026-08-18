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

### KK-38: Sessizce yok sayilan tarih filtresi, ve CIK ile adresleme

16 Agu 2026. Ikisi de CANLI kullanimda olculdu; ikincisi bir gun once eklenen
aracin kendi ciktisini okunamaz biraktigini gosterdi.

**1. Tek tarafli tarih araligi SESSIZCE dusuyordu.** Olcum (`"lithium iron
phosphate"`, forms=10-K):

| Cagri | Sonuc |
|---|---|
| yalnizca `start_date=2026-01-01` | 162 sonuc, en eskisi **2009** tarihli |
| yalnizca `end_date=2012-12-31` | ayni 162 sonuc |
| ikisi birlikte | 16 sonuc, hepsi 2026-03 |

EDGAR'in ucu `dateRange=custom` icin iki siniri da istiyor; biri eksikse
araligi tumden atiyor. Kod tarih BICIMINI dogruluyordu ama tek tarafli araligi
oldugu gibi gonderiyordu, yani model "2026'da kim bahsetti" diye sorup 2009
sonuclarini 2026 saniyordu. **P-29'un ta kendisi - kendi kodumda, o pattern'i
yazdiktan bir gun sonra.** Eksik uc artik dolduruluyor (baslangic yoksa
`1994-01-01`, EDGAR arsivinin baslangici; bitis yoksa bugun) ve gonderilen
aralik `date_range_applied` alaninda yaziyor. Varsayilan olarak 2001 DEGIL
1994 secildi: indekste 2001 oncesinden de birkac belge OLCULDU (KK-35), ve
varsayilanla onlari elemek yeni bir sessiz filtre olurdu.

**2. Ticker zorunlulugu araci kendi ciktisindan mahrum birakiyordu.** Ayni gun
olculdu: tam metin aramasi ticker'i OLMAYAN dosyalayanlar donduruyor -
`company_tickers.json` yalnizca borsada islem goren sembolleri tasiyor. Arama
"CHINA SUN GROUP HIGH-TECH CO (CIK 0001298195)" buluyor, `ticker: null`
bildiriyor, ve okuma araclari o dosyalamayi acamiyordu. Arac kendi buldugu
belgeye erisemiyorsa arama yarim bir yetenektir.

Artik her `ticker` parametresi **CIK de kabul ediyor** (`320193`,
`0000320193`, `CIK0000320193`). Sayisal girdi CIK sayiliyor; ABD borsalarinda
yalnizca rakamdan olusan sembol yok, dolayisiyla belirsizlik uretmiyor.
Iki incelik testle sabit:
- **Sembol gosterimi girdiye sadik.** Kullanici `GOOGL` yazdiysa yanitta
  `GOOGL` gorunur; ayni CIK'e bagli alfabetik ilk sembol (GOOG) donmez. CIK
  ile soruldugunda sembol SEC'in dosyasindan aranir, bulunamazsa `None` kalir -
  uydurulmaz. `CompanyProfile.ticker` ve `FilingPage.ticker` bu yuzden artik
  opsiyonel.
- **Bilinmeyen CIK eyleme donusturulebilir hata veriyor.** CIK ile adresleme
  acildiktan sonra en olasi kullanici hatasi var olmayan bir numara; cig
  `HTTPStatusError` modele ne yapacagini soylemez (§18/P-13). Donusum
  `client.submissions()` icinde, yani butun cagiranlar icin bir kerede.

Sahte veri de duzeltildi: mock her CIK'e ayni `submissions` yanitini
donduruyordu, yani "bilinmeyen numara" yolu HIC sinanmiyordu (P-4). Artik
`company_tickers.json`'da olmayan CIK'e 404 donuyor.

Alti yeni enjeksiyon dogruluyor.

### KK-39: Dis benchmark - sunucunun neyi degistirdigi olculdu

16 Agu 2026. Bu depo bugune kadar KENDI olcumleriyle konusuyordu: testler,
enjeksiyonlar, kendi degerlendirme seti. Hepsi ic tutarlilik kaniti; hicbiri
"bu sunucu cevabi degistiriyor mu" sorusunu yanitlamiyor. Disaridan, bizim
yazmadigimiz bir soru kumesi gerekiyordu.

Secilen: **Vals AI Finance Agent Benchmark** (CC-BY-4.0), 537 soruluk uzman
yazimi setin acik 50 soruluk dilimi. Secim gerekcesi: acik lisansli, AJANSAL
(araci olan bir model icin yazilmis, bir arama indeksi icin degil), ve bu
depoyla ilgisi olmayan biri tarafindan hazirlanmis. Veri setinin kendi uzman
sure tahmini 631 dakika (10,5 saat).

**Sonuc: araçsiz %24 dogru, bu sunucuyla %82 dogru.** Iki kolda da "kendinden
emin yanlis rakam" yok; fark, kontrol kolunun sorularin %36'sini hic
cevaplayamamasi, arac kolunun ise yalnizca birini cevaplayamamasi. En keskin
ayrim "Beat or Miss" turunde: 7/7'ye karsi 0/7. O sorular, sirketin bir onceki
ceyrekte verdigi kilavuzlukla gerceklesen sonucu karsilastirmayi gerektiriyor,
yani aylar arayla dosyalanmis IKI 8-K ekini bulup icindeki sayilari
karsilastirmayi. Dosyalamaya erisimi olmayan bir model yalnizca YONU
hatirlayabiliyor - nitekim TJX ve Micron icin "beat" dedi ve yonu iki kez de
tutturdu, buyuklugu iki kez de kacirdi (20-30bps'e karsi 70, 40bps'e karsi 140).

**Yontem kararlari, hepsi onyargiyi azaltmak icin:**
- Cevaplayan iki kol da beklenen cevaplari HIC gormedi.
- Notlandirmayi ayri bir ajan yapti; iki cevabi rastgele sirayla gordu ve
  hangisinin hangi koldan geldigi soylenmedi.
- Kontrol kolu "bilmiyorsan bilmedigini soyle, uydurma rakam verme" diye
  talimatlandirildi - yani karsimizdaki kontrol, zayif degil GUCLU surumu.
  Bunun bedeli acik: kontrol kolunun sifir "kendinden emin yanlis"i bu
  talimattan geliyor, olcumden degil, ve rapor bunu boyle yaziyor.
- Ham veri tumuyle depoda (`evaluation/benchmark/`): iki kolun cevaplari,
  notlandiriciya verilen girdi, notlar, kol anahtari. Sayi tartisilabilir
  olmali; tartisilmasi icin verinin gorunmesi gerekiyor.

**Rapor edilen sinirlar** (rapora yazildi, dipnot degil govde): n=50; notlandirici
bir dil modeli; kontrol kolunun cevaplari notlandirmadan once olgu iddialarina
INDIRGENDI (arac kolu birebir notlandirildi) - bu asimetri olculemiyor; bes
soruda donem uyusmazligi var (veri seti 2025'te yazildi, kosu 2026'da yapildi -
bunlar dogru sayilsa arac kolu %92); iki beklenen cevap kendi icinde tutarsiz
gorunuyor; ve baska veri setlerinin yayinlanmis skorlariyla (orn. Fin-RATE'in
GPT-5 + web aramasi icin ~%43 baseline'i) YAN YANA KONULAMAZ - farkli sorular,
farkli notlandirma.

Bu sayinin degeri teknik degil ticari: sekiz rakip sunucunun hicbirinde boyle
bir olcum yok (KK-38 oncesi yapilan tarama). Ama abartilmamali - olculen sey
"bu sunucu rakiplerinden iyi" degil, "bu sunucu modelin cevabini degistiriyor".

### KK-40: Sahiplik verisi - Form 4 ve 13F, ve bin katlik sessiz hata

16 Agu 2026 gecesi. Rakip taramasi (KK-39 oncesi) tek bir urun boslugunu net
gosterdi: **sahiplik verisi sekiz rakibin neredeyse hepsinde var, bizde yoktu.**
Iki belge, iki arac, ve ikisi de XBRL DEGIL - bu yuzden ayri bir modul
(`sahiplik.py`).

**Form 4 - `sec_edgar_get_insider_transactions`.** Sirketin yoneticileri,
gorevlileri ve %10 ustu ortaklari kendi hisselerinde islem yapinca iki is gunu
icinde bildirmek zorunda. Olculen yapi (NVDA, iki ayri dosyalama):

- Kok `ownershipDocument`, **ad alani yok**; degerler `<value>` sarmalayicisi
  ICINDE. Eleman metnini dogrudan okuyan kod bos alir - bir enjeksiyon tam
  bunu deniyor.
- Fiyat alani ayrica `<footnoteId>` tasiyabiliyor.
- `nonDerivativeHolding` islem DEGIL, mevcut pozisyon bildirimi.
- Turev tablosu (RSU/opsiyon) ayri: bir RSU vesting'i hem `M` turev satiri hem
  `A` hisse satiri olarak gorunuyor, ikisini birden saymak ayni hisseyi iki kez
  saymak demek. Varsayilan olarak turev satirlari DISARIDA.

**En onemli tasarim karari: tek bir "net iceriden alim" sayisi URETILMIYOR.**
Bu verinin en yaygin yanlis okunmasi, hisse ODULUNU (kod A) ya da vergi icin
KESILEN hisseyi (kod F) piyasadan alim/satim sanmak. Odulun fiyati sifirdir,
kesinti bir karar degil mekanik bir sonuctur; ikisini piyasa islemiyle
toplamak anlamsiz bir sayi uretir. Yanit bu yuzden kod BAZINDA toplam veriyor
ve her kodun anlamini yaninda tasiyor (§18). Ayni ilke KK-31'deki mutabakat
karariyla ayni: arac toplamiyor, ayirip gosteriyor.

Bir ayrinti daha olculdu: `primaryDocument` alani **stil sayfasi yolunu**
gosteriyor (`xslF345X06/wk-form4_....xml`); makine okunur XML oneksiz halidir.
Onek atilamazsa dizin listesine dusuluyor - isimlendirme kalibina korlemesine
guvenmek KK-35'te ayni gun ceza kesilen hatanin ta kendisi.

**13F - `sec_edgar_get_institutional_holdings`.** 100 milyon dolar ustu
yoneticiler ceyrek sonundan itibaren 45 gun icinde ABD borsalarindaki uzun
pozisyonlarini bildiriyor. Olculen yapi (Berkshire Hathaway):

- Bilgi tablosu **ad alanli** (`.../thirteenf/informationtable`) ve dosya adi
  **rastgele** ("56757.xml", "18337.xml", "20651.xml") - tahmin edilemez,
  dizinden bulunuyor.
- Ayni ihracci **birden fazla satirda** geciyor (Berkshire'in Q3 2022
  dosyalamasinda Apple 12 satir). Bunlar mukerrer DEGIL, her alt yonetici icin
  ayri satir. Toplaniyor ve `rows_combined` kac satirdan geldigini soyluyor.
- Yoneticilerin ticker'i yok; CIK ile adresleme (KK-38) tam da bu yuzden
  onkosuldu.

**Bin katlik sessiz hata - olculdu.** SEC 2023'te 13F deger birimini binden tam
dolara cevirdi. Ayni pozisyon, iki ardisik ceyrek:

| Dosyalama | Apple hissesi | Bildirilen deger | Hisse basi |
|---|---|---|---|
| 14 Kas 2022 | 669.429.166 | 92.515.111 | 0,14 $ (tam dolar okunursa) |
| 14 Sub 2023 | 669.429.166 | 86.841.985.318 | 129,72 $ |

Apple 30 Ara 2022'de 129,93 dolardan kapandi, yani ikincisi tam dolar,
birincisi bin dolar. Normalize etmeyen bir arac, iki ceyregi karsilastiran
modele "pozisyon bin katina cikti" dedirtir ve bunu hicbir hata mesaji
durdurmaz. Arac artik ikisini de tam dolara cevirip `value_basis` ile hangi
konvansiyonun kullanildigini soyluyor. Sinir SEC'in kural degisikliginin
yururluk tarihi; iki olcum sinirin iki yanindan alindi.

**Kapak sayfasi ile tablo ayri ayri donuyor** (`reported_value_total` /
`total_value_usd`, `reported_entry_count` / `rows_in_table`): ikisi tutmayabilir
ve tutmadiginda bu dosyalayanin tutarsizligidir, aracin degil. Sessizce birini
secmek KK-31'in yasakladigi sey.

**Kapsam notu her iki aracta da yanitin icinde:** Form 4 yalnizca bildirim
yukumlusu kisileri gosterir ve ne yapildigini soyler, NEDEN yapildigini asla;
13F yalnizca uzun ABD hisse pozisyonlarini, ceyrek sonu itibariyla ve en erken
45 gun sonra gosterir - kisa pozisyon, nakit, tahvil, yurt disi holding ve
ceyrek sonrasi hareket yok.

On dort yeni enjeksiyon dogruluyor. Biri ilk turda "KORUMASIZ" dondu ve yine
ayni dersi verdi (P-30): kod toplamlarinda `is_holding` kontrolu, `shares is
None` kontrolunun yaninda OLU koruma idi - pozisyon satirinin zaten `shares`
alani yok. Birini bozmak otekini devrede biraktigi icin hicbir test kirmiziya
donmuyordu. Olu kontrol kaldirildi.

### KK-41: Harness sert oldurmeye dayanikli DEGILDI - KK-6'nin duzeltmesi

16 Agu 2026. v38 icin baslatilan tam enjeksiyon kosusu 32/163'te oldu: surec
yok, log'un son satiri 43 dakika oncesinden. Ne traceback, ne exit kodu, ne
mesaj. Calisma dizininde `belge.py` enjekte halde kaldi ve testler YESIL
gorunuyordu - o enjeksiyonun kirmiziya dondurdugu tek test, o an kosan test
degildi. Elle tespit edildi (`.enjeksiyon_yedek/` ile diff), tek satir geri
yuklendi, 250 test dogrulandi.

**KK-6 fazla sey iddia ediyordu.** "Cokmeye dayanikli" derken kastedilen sey
istisna, `SIGINT` ve `SIGTERM`'di; ucu de surecin CALISMAYA DEVAM ETMESINI
gerektiriyor. `SIGKILL`, OOM reaper ya da konteynerin geri alinmasi hicbirini
calistirmaz. Iddia yanlis degildi, KAPSAMI yaziya dokulmemisti; simdi dokuldu.

**Asil bosluk geri yuklemede degil, GORUNURLUKTE idi.** Harness artiklari
kendi bir sonraki kosusunun BASINDA geri yukluyordu - ama testleri kosturan,
paketleyen ya da commit eden hicbir adim harness'i calistirmiyor. 32/163'te
olen bir kosunun ardindan repoya dokunan bir sonraki sey, enjekte edilmis bir
kaynak dosyayi hicbir uyari gormeden paketleyebilirdi.

**Uc degisiklik:**

1. **`--kontrol`** - artik var mi diye bakar, varsa exit 2. **Onarim YAPMAZ.**
   Sessizce onaran bir kontrol, gorulmesi gereken olayi gizlerdi; tespit ile
   onarim ayri. CI kosunun ARDINDAN calistiriyor, boylece harness'in kendi
   temizlik iddiasi da varsayim olmaktan cikip olculen bir sey oluyor.
2. **Uygulanan enjeksiyonun adi diske yazilir** - dosya bozulmadan ONCE, geri
   yuklendikten sonra silinir. Artik kalan bir enjeksiyon artik kendini
   soyluyor; yedeklerle diff alarak yeniden kurmak gerekmiyor.
3. **`--parca k/n`** - 163 enjeksiyonun her biri tum test setini kosturuyor.
   Sure makine yukune gore cok oynuyor: bos konteynerde tek kosu **14 sn**
   olculdu (sweep ~40 dk), cokerek biten kosuda ise enjeksiyon basina ~80 sn
   dusuyordu (3 saati asan projeksiyon). Bu degiskenlik parcalamanin
   gerekcesinin kendisi. Dort bitisik parca sureci kisaltiyor ve
   kaybedilen parcayi ucuz kiliyor. CI matrisi artik `os x parca` (8 is).
   Bolmenin TAM ve ORTUSMESIZ oldugu testle sabit: enjeksiyon dusuren bir
   bolme, harness'in iddia ettiginden az sey dogrular - cozulen sorundan
   buyuk bir sorun.

Ayrica test kosusuna sure siniri (`ENJEKSIYON_TEST_SURESI`, varsayilan 900 sn)
eklendi ve zaman asimi AYRI bir sonuc olarak raporlaniyor. `testler()` artik
zaman asiminda bos liste degil `None` donuyor: bos liste "hicbir test kirmiziya
donmedi" (koruma yok) demek, `None` ise "olculemedi" demek. Ikisini ayni degerle
bildirmek calisan bir korumayi KORUMASIZ diye raporlardi - KK-10'daki
`ENJEKSIYON SOZDIZIMI BOZDU` ayriminin aynisi, ve KK-23'un "bos basari gercek
bos cevaptan ayirt edilemez" kuralinin harness'taki karsiligi.

P-31 olarak kayda gecti. Iki yeni test dogruluyor; bunlar enjeksiyonla degil
dogrudan sinaniyor cunku harness'in kendisi enjeksiyon hedefi degil.

### KK-42: Yayin kimligi - isim cakismasi ve sahiplik isaretleri

16 Agu 2026. Dagitim adimi (PUBLISHING.md) yazilmisti ama hicbir adimi
CALISTIRILMAMISTI. Ilk adim ilk gercegi verdi: **PyPI'da `sec-edgar-mcp` adi
alinmis.**

```
$ pip index versions sec-edgar-mcp
sec-edgar-mcp (1.0.8)
```

Sahibi `stefanoamorelli/sec-edgar-mcp` - ayni nisin en gorunur projesi
(AGPL-3.0, 310 yildiz). Yani cakisma terk edilmis bir yer tutucuyla degil,
pazar liderinin ta kendisiyle. Bu bir olcum sonucu; PUBLISHING.md'nin "isim
alinmis olabilir" notu dogru cikti ama tahmin degil artik.

**Dort sey birbirinden BAGIMSIZ, karistirilmamali:** PyPI dagitim adi (sert
blok), konsol script adi (yumusak: iki paket ayni komutu kurarsa son kuran
kazanir, sessizce), kayit defteri sunucu adi (`io.github.<hesap>/...` -
hesapla ad alanina alindigi icin CAKISMIYOR) ve GitHub depo adi (teknik
cakisma yok, kesfedilebilirlik sorunu var).

**Karar verilmedi, bilerek.** Dagitim adi degismek ZORUNDA ama hangisi olacagi
konumlandirma, depo adi ise marka sorusu. Ikisi de bu gece en ucuz haliyle
duruyor ve ilk musteriye link gittikten sonra pahalilasiyor - bu yuzden
secenekler olculmus haliyle PUBLISHING.md'ye yazildi, secim birakildi.

**Kayit defteri sahiplik dogrulamasi - olculdu, hatirlanmadi.** Kayit defteri
paketin gercekten yayinlayana ait oldugunu paket TURUNE gore farkli yollarla
denetliyor:
- PyPI: paket README'sinde `mcp-name: <sunucu adi>` dizgisi (HTML yorumu kabul).
  README zaten PyPI aciklamasi oldugu icin dosyanin ilk satirina kondu.
- OCI: imajda `LABEL io.modelcontextprotocol.server.name="<sunucu adi>"`.

Ucu de (`server.json` → `name`, README isareti, Dockerfile etiketi) birbirine
esit olmak zorunda. Bir yeniden adlandirma ucunden ikisini guncelleyip
ucuncusunu unutursa hata YAYIN aninda cikiyor - geri bildirim dongusunun en
pahali yeri. `test_kayit_defteri_kimligi_uc_dosyada_da_ayni` ucunu birden
sabitliyor, ve Dockerfile enjeksiyon hedefi oldugu icin bu koruma enjeksiyonla
da dogrulaniyor (164. enjeksiyon).

**`server.json` OCI paketiyle yazildi, PyPI ile degil.** Kayit defteri yalnizca
meta veri tutuyor; girdideki paketin gercekten var olmasi gerekiyor. OCI adi
GitHub hesabiyla ad alanina alindigi icin bugun yayinlanabilir; `pypi` girdisi
ise dagitim adi secilip yuklendikten SONRA eklenecek. Baskasinin paketini
gosteren bir `pypi` girdisi, girdisiz olmaktan kotudur.

**Olculemeyen, acikca yaziliyor:** `server.json` semaya karsi MAKINEYLE
dogrulanamadi - bu ortamin proxy'si `static.modelcontextprotocol.io`'yu
reddediyor (`Tunnel connection failed: 403 Forbidden`). Dosya belgelenen zorunlu
alanlara ve yayinlanan ornege gore elle kuruldu. Normal bir agdan tek komutluk
`check-jsonschema` cagrisi PUBLISHING.md'de duruyor; ayrica `mcp-publisher
publish` sunucu tarafinda da dogruluyor.

### KK-43: Kesim tarihi (as_of) - "en guncel"in gizli varsayimi

17 Agu 2026. Degerlendirme kosusunun bes soruluk donem uyusmazligi (zaaf 3) bir
olcum kusuru gibi gorunuyordu; degildi. **Aracin kendisinde bir varsayim
vardi:** "en son dosyalama" ifadesi her zaman SU AN itibariyle en sonu
kastediyordu. Gecmise donuk her soruda bu sessizce yanlis. Finanstaki adi
look-ahead bias.

**Iki secenek vardi, ikisi de ayni sayiyi uretirdi:** (a) sinavi cozen ajana
"su tarihten sonrasini yok say" talimati verip cevaplarda kullanilan
dosyalamalari denetlemek, (b) araca gercek bir kesim parametresi eklemek.
Ikincisi secildi. Gerekce: talimat denetlenebilir ama ENGELLEMIYOR; ve
point-in-time sorgu, sinavdan bagimsiz olarak gercek bir urun ozelligi (backtest
yapan herkesin ihtiyaci, ve taranan sekiz rakibin hicbirinde yok).

**Kesim SUNULMA tarihine gore, doneme gore DEGIL.** En onemli tasarim karari
bu: revize edilmis bir rakamin donem sonu orijinaliyle AYNIDIR. Doneme bakan
bir filtre butun revizyonlari iceri alir ve calisiyormus gibi gorunur. Sahte
veriyle olculuyor: Apple FY2023 geliri 2023 10-K'sinda 383.285, 2024
10-K'sinda 383.290; `as_of=2024-01-01` birincisini donduruyor.

**Kapsam:** guncellige gore secim yapan her arac (`list_filings`,
`read_filing_text`, `get_concept_series`, `get_fact_revisions`,
`list_available_concepts`, iki boyut araci, Form 4, 13F) `as_of` aliyor ve her
yanit `as_of_applied` ile uygulanan kesimi geri veriyor - uygulanip
uygulanmadigini soylemeyen bir kesim, hic uygulanmamis olmakla ayni gorunurdu
(KK-23). Tam metin aramasinda ayri parametre YOK: kesim `end_date`in tavani
oluyor ve gonderilen aralik zaten `date_range_applied`de yaziyor; ayni seyi iki
adla anlatmak yuzeyi bulanik yapardi.

**Dort incelik, dordu de testli:**
1. **Tarihi bilinmeyen kayit kesimden SONRA sayilir.** Iceri almak, "o tarihte
   biliniyordu" sozunu tarihi bilinmeyen bir kayitla doldurmak olurdu.
2. **Acikca istenen dosyalama da reddediliyor.** Tek satirlik bir istisna,
   cagiranin elinde yanlis bir guvence birakir. Hata iki tarihi de veriyor.
3. **Cagri ve ortam carpisirsa ERKEN olan kazanir.** `SEC_AS_OF` oturum capinda
   bir soz; gec olani secmek sozu cagri basina bozardi.
4. **`compare_companies` kesimi UYGULAYAMIYOR ve bunu soyluyor.** SEC'in cerceve
   ucu satir basina sunulma tarihi vermiyor; tarihi ogrenmek cercevedeki her
   sirket icin ayri istek demek (olculdu: 2.543 sirket). Kesim varken cagri
   reddediliyor ve tutan alternatif adres gosteriliyor (§18). Tutamayacagi bir
   sozu tutuyormus gibi yapan bir arac, sozu hic vermeyen bir aractan kotudur.

**Kesim tarihi kaynakla secildi, tahminle degil.** Veri seti Zenodo'da
**16 Mayis 2025**'te yayinlanmis (kayit 15428639, v1, ayni gun olusturulmus ve
degistirilmis). Sorularda gecen en gec tam tarih 10 Mart 2025; vals.ai'nin
liderlik tablosu adresi 30 Mayis 2025 tarihli bir kosuya isaret ediyor; makale
Agustos 2025'te arXiv'e girmis. Dordu de tutarli, celiski yok.

**Henuz OLCULMEDI:** kesimli kosu yapilmadi. Kod kesimi mumkun kiliyor; %92
rakami hala bir PROJEKSIYON ve kosu, sunucunun guncel surumu Mirza'nin
makinesine kurulduktan sonra yapilacak. Ve kosu bes soruyla sinirli
kalmayacak - **elli sorunun hepsi** yeniden kosulacak, cunku yalnizca yanlis
cikan besini yeniden kosmak secmeli olcum olur: kesim, dogru cikmis bir cevabi
da bozabilir ve bunu gormek gerekiyor.

On bir yeni enjeksiyon dogruluyor.

### KK-44: Zaaf 4 - ayni sinavin yayinlanmis skoru bulundu

17 Agu 2026. Zaaf 4 "baska setlerin skorlariyla kiyaslanamiyor" diyordu ve
cozumu icin Fin-RATE'i kendi puanlamasiyla kosmak planlanmisti - bir gunluk is.
Setin kendi makalesi (arXiv 2508.00828) okununca gereksiz oldugu goruldu:
**ayni sinavin yayinlanmis baseline'i var.** En iyi model o3 **%46,8 ± 2,2**,
ve **hicbir model %50'yi gecmemis**. Ustelik o ajanlarin araclari arasinda hem
`GoogleSearch` hem `EdgarSearch` var - yani baseline, aracsiz bir model degil,
SEC dosyalamalarina VE web aramasina erisen bir model.

Makalenin metrigi **sinif-dengeli dogruluk** (her tur esit sayiliyor, her soru
degil). Ayni yontemle bizim yayinlanmis not dosyamizdan hesaplandi:
sunucuyla **%80,6**, aracsiz **%29,6** (ham sayilar %82 ve %24).

**Birebir kiyas DEGIL ve rapor bunu dort maddeyle soyluyor:** farkli sorular
(537'ye karsi acik 50), farkli notlandirma (onlarinki rubrik tabanli, ayrica
bir "celiski rubrigi" var), farkli araclar (onlarda genel web aramasi vardi,
bizde yalnizca on SEC araci), ve farkli model kusagi (onlarinki 2025 modelleri,
bizimki 2026). Sonuncusu en onemlisi: aradaki farkin bir kismi sunucunun degil,
modelin.

**Ne kaniti oluyor:** bu sinavda yayinlanmis en iyi sonuc, EDGAR ve web
erisimiyle bile %50'nin altinda - yani sorularin zorlugu tartismali degil.
**Ne kaniti olmuyor:** bu sunucunun o3'u gectigi. Sunucunun katkisini izole
eden karsilastirma kosunun KENDI ICINDEKI karsilastirmadir (ayni model, ayni
sorular, ayni notlandirici: %24'e karsi %82) ve o karsilastirma bir liderlik
tablosu hakkinda hicbir sey soylemez.

Ayrica bir P-14 temizligi yapildi: vaka calismasi "250 tests" ve "170 fault
injections", iki README de "30 failures" diyordu; gercek sayilar 265, 175 ve 32.
Hicbiri yanlis bir sey ogretmiyor ama hepsi ayni sinif - dokumanda duran, kodun
dogrulamadigi iddia. `test_dokumanlardaki_sayilar_gercekle_ayni` ucunu de
kaynagindan sayiyor (harness listesi, `### P-` basliklari, ve pytest'in kendi
topladigi test sayisi). Sayilar buyudukce test kirmiziya donecek; dogrusu bu.

### KK-45: Bir donemin kimligi bitis tarihi DEGIL, [baslangic, bitis] araligidir

17 Agu 2026, v39 kurulduktan sonra **canli kullanimda** bulundu - test paketi
bunu gormuyordu. Iki arac da ayni koku paylasiyordu.

**Belirti 1 - seri sessizce satir dusuruyordu.** `sec_edgar_get_concept_series`
dedup anahtari `(donem_sonu, birim)` idi. Bir 10-Q hem CEYREGI hem YIL
BASINDAN BERI toplami raporlar ve ikisi AYNI GUN biter. Olculdu (AAPL,
`period="all"`): 2025-03-29 icin donen deger **219.659** - alti aylik toplam;
o ceyregin kendi rakami **95.359** listede HIC yok. `days` alani uzunlugu
soyluyordu, yani dikkatli bir okuyucu fark edebilirdi; ama kayip rakam icin
hicbir isaret yoktu.

**Belirti 2 - revizyon araci uydurma revizyon uretiyordu.** Ayni sinif hata:
gruplama anahtari `(etiket, bitis, birim)`. Olculdu (AAPL, `period="all"`):
**87 donemin 55'i "revize" gorunuyordu** ve orneklerden birinde 2021-03-27'nin
iki degeri de AYNI erisim numarasindan geliyordu (`0000320193-21-000056`).
Bir revizyon ayni dosyalamanin icinde olamaz; ikisi de dogruydu - 201.023 alti
aylik, 89.584 uc aylik rakamdi.

**Neden testler gormedi:** sahte veri ayni gun biten iki farkli uzunlukta donem
tasimiyordu. P-4'un tekrari - mock gercegin sozlesmesini taklit etmiyorsa test
yazarin varsayimini dogrular, kaynagi degil. `period="annual"` ve
`"quarterly"` modlarinda gun-uzunlugu filtresi kazayla koruyordu; `"all"`
belgelenmis bir secenek ve orada koruma yoktu.

**Karar:** anahtar donem UZUNLUGUNU da tasiyor. Ham gun sayisi degil, AYA
yuvarlanmis kova (`_donem_kovasi`): 52/53 haftalik takvimlerde ayni yillik
donem 363-365 gun surebiliyor ve ham gun sayisi bunlari AYRI donem sayardi -
ayni mali yil listede iki kez cikardi. Kova 363/364/365'i 12'de birlestiriyor,
90 / 181 / 272'yi ayri tutuyor.

**Ayrica kendi dokumantasyon hatam:** README'nin iki dilinde de "Apple'in FY2023
geliriyle **olculdu**: 383.285 -> 383.290" yaziyordu. O sayilar TEST
FIXTURE'INDAN geliyordu, canli bir olcumden degil - yani depo, kendi kural
kitabinin (§1: olc, hatirlama) disina cikmisti. Yerine gercek ve canli
dogrulanmis bir ornek konuldu: **Tesla FY2017 geliri**, `as_of=2019-01-01` ile
`11.758.751.000` (2018-02-23 tarihli dosyalama), kesimsiz `11.759.000.000`
(2020-02-13 tarihli dosyalama). Ayni donem, iki farkli cevap, ayirici tek sey
sunulma tarihi.

Uc yeni enjeksiyon dogruluyor. P-33 olarak kayda gecti.

### KK-46: Kesimli kosu olculdu - %82 -> %90, ve notlandiricinin kendi gurultusu

17 Agu 2026. KK-43'te "%92 hala bir PROJEKSIYON" yazmistim. Olculdu:
**%90 ham, %91,9 sinif-dengeli** (kontrol kolu %26 / %32,6). Projeksiyon iki
varsayima dayaniyordu ve **ikisi de yanlis cikti**: bes donem uyusmazliginin
hepsinin duzelecegi (ucu duzeldi, ucu kaldi - id 10, 11, 49) ve hicbir cevabin
ters yone gitmeyecegi (id 49 dogru'dan kismen'e dustu). Net +4, +5 degil.

**Elli sorunun hepsi yeniden kosuldu.** Yalnizca yanlis cikan besini kosmak
secmeli olcum olurdu ve tam da kacinilan sey basimiza gelirdi: kesim, dogru
cikmis bir cevabi bozabiliyor ve bozdu.

**Kesim gercekten tutuldu mu - denetlendi, varsayilmadi.** Arac kolunun
okudugunu bildirdigi 64 farkli erisim numarasinin 2025 yili kodlu 37'si tek tek
SEC'e karsi tarihlendirildi: **kesimden sonra tek dosyalama yok**, en gec
kullanilan dosyalama 2025-05-09. Ham denetim
`evaluation/benchmark/kesimli_denetim.json`.

**Beklenmedik ve degerli bir olcum: notlandirici gurultusu.** Ikinci kosuda
kontrol kolunun cevaplari YENIDEN KOSULMADI - ayni metin yeniden notlandirildi.
Bu bir deney olarak tasarlanmamisti ama bir deney: ayni elli cevap, iki ayri
notlandirici.

| | uyum |
|---|---|
| birebir not (dogru/kismen/yanlis/cevapyok) | 43/50 - **%86** |
| ikili (dogru mu, degil mi) | 47/50 - **%94** |
| basliga etkisi | 12 dogru -> 13 dogru |

Yani kontrol kolunun %24'u ile %26'si ayni olcumun iki kez notlandirilmis
hali; kontrol degismedi. **Her rakam, baska hicbir hata kaynagi olmadan once
yaklasik ±2 puan notlandirici gurultusu tasiyor.** 64 puanlik farkin yaninda
kucuk; iki arac kosusu arasindaki 8 puanin yaninda degil - donem
uyusmazliklarinin notlandirmada tartisilmak yerine ARACTA duzeltilip yeniden
olculmesinin sebebi tam olarak bu.

Bu ayni zamanda zaaf 2'nin (notlandirici bir dil modeli) ilk gercek olcumu:
artik "notlandirici belirsizligi var" demiyoruz, ne kadar oldugunu soyluyoruz.

Maliyet de dustu: 202 arac cagrisi (soru basina 4,0), ilk kosuda 239 (4,8).
Kesim aramayi genisletmedi, daralttti.

### KK-47: Kapsamli dusman denetimi - yedi goz, sekiz gercek hata, ucu kritik

18 Agu 2026. Piyasaya cikmadan once repo yedi ayri "dusman gozle" denetimden
gecirildi; hepsi SALT OKUNUR calisti, duzeltmeleri ben yaptim ve her bulguyu
kendim yeniden uretmeden hicbirine dokunmadim. Denetim eksenleri: en taze kod,
dokuman-kod uyumu, testlerin ve mock'larin sadakati, olcum makinesi (harness +
benchmark), ve UC AYRI canli veri turu (XBRL serileri, metin/tablo/arama,
sahiplik/boyutlar).

**Toplam 81 bulgu raporlandi.** Hepsi gecerli degil - bir kismi zaten
belgelenmis sinirlar, bir kismi tekrar. Asagidakiler DOGRULANMIS ve
DUZELTILMIS olanlar.

**Kritik 1 - mali yil etiketi 52/53 haftalik takvimde bozuk.** Canli olcum
(US Foods, bagimsiz olarak Kraft Heinz'de de dogrulandi): `fiscal_year` 2016
IKI KEZ cikiyordu - 2016-01-02 ve 2016-12-31'de biten iki AYRI mali yil icin -
ve FY2015 ile FY2020 seriden tumuyle kayboluyordu. Ayni kok neden, mali yil
sonunu degistiren sirkette (Perrigo, Haziran -> Aralik) bir rejimin BUTUN
etiketlerini bir yil kaydiriyordu; ustelik hangi rejimin kaydigi hangi
etiketlerin cekildigine bagliydi, yani ayni sirketin ayni donemi sorgu
`revenue` mi ham etiket mi diye soruldugu icin farkli yil aliyordu - **arac
kendi kendisiyle celisiyordu.**

Kok neden: tum gecmis icin TEK bir kayma ve TEK bir (ay, gun) turetiliyordu.
Yerine `Takvim` sinifi geldi: SEC'in kendi `fy` alanindan cikan (donem_sonu,
mali_yil) capalari tutuluyor ve bir donem, KENDISINDEN SONRAKI ilk capanin
mali yilina ait sayiliyor. Rejim degisikligi kendiliginden dogru sonuc veriyor,
cunku her donem kendi rejimindeki capaya bakiyor. Uc incelik: yil sonunda biten
donem ile yil ICINDE biten donem farkli yuvarlaniyor (biri tam sayida yil
uzakta, oteki bir sonraki yil sonuna ait); ayni bitise dusen birden fazla `fy`
varsa EN KUCUGU dogru olandir (buyugu bir karsilastirma satiri artigidir);
capa dizisi tutarsizsa cogunluk kaymasina uymayan dusuyor.
Ve yeni `fiscal_year_source` alani, etiketin SEC'in soyledigi bir yil mi
(`reported`) yoksa bizim saydigimiz bir yil mi (`derived`/`extrapolated`)
oldugunu ayirt ediyor - ikisi ayni alanda dururken susmak, dogrulanmis bir
etiketle tahmini ayirt edilemez birakiyordu.

**Kritik 2 - ortak Form 4 dosyalamasi sahip sayisi kadar cogaltiliyordu.**
Islem tablolari SAHIP dongusunun icinde okunuyordu; oysa tablolar BELGEYE ait,
sahibe degil. Olculdu (CoreWeave, dort sahipli bir Magnetar dosyalamasi):
belgede 24 satir / 307.131 hisse, arac 96 satir / 1.228.524 hisse. "Iceriden
alim" diye okunacak bir sayi tam dort katina cikiyordu. Ortak dosyalamada islem
tek bir kisiye atfedilemedigi icin artik imzalayanlarin hepsi yaziyor ve
`owner_count` kac kisi oldugunu soyluyor.

**Kritik 3 - `code_totals` turev ve turev-olmayan satirlari topluyordu.** Bir
opsiyon kullanimi AYNI dosyalamada iki satir uretir (turev tarafinda `M`, hisse
tarafinda `A`); ikisini toplamak ayni hisseyi iki kez sayar. Olculdu (TSLA):
608.022.232'ye karsi gercek 304.011.116. **Aracin kendi arac aciklamasi bu cift
sayimi zaten UYARIYORDU ve kod tam da onu yapiyordu** - dokumanin kodu
denetlemedigi bir yer daha (P-14).

**Ciddi 4 - mutabakat donem uzunlugunu yok sayiyordu.** KK-45'te iki REST
aracinda duzeltilen hata, boyutlu aracin mutabakatinda KALMISTI. Bir 10-Q hem
uc aylik hem yil basindan beri rakamlari tasir ve ikisi ayni gun biter; iki
tutarli kirilim tek satira yigiliyor ve konsolide deger sessizce uzerine
yaziliyordu - "fark" rakami dosyalamadaki eleman SIRASINA bagli hale
geliyordu. Bir duzeltmenin kardes cagri yerini atlamasi bu depoda ucuncu kez
oluyor (P-27, P-33).

**Ciddi 5 - eksende ic ice kirilim duzeyleri.** Olculdu (AAPL
`srt:ProductOrServiceAxis`): uye toplami konsolidenin TAM iki kati, cunku
Urun/Hizmet ile bes yollu urun kirilimi AYNI eksende duruyor. Arac
`agrees:false` deyip dosyalayani sucluyordu; oysa 10-K'da mutabakat tam
tutuyor. Hangi uyenin hangisinin ustu oldugu TANIM LINKBASE'inde ve bu arac onu
okumuyor - dolayisiyla karar verilmiyor, `member_values` ile her uye tek tek
gosteriliyor ve alan aciklamasi bu sinirin adini koyuyor. **Bilinen ve
kapanmamis sinir olarak kayitli.**

**Ciddi 6 - mutabakat sessizce bos donuyordu.** Modern segment dipnotlarinin
neredeyse tamaminda her fact ikinci bir eksen de tasiyor
(`ConsolidationItemsAxis`), dolayisiyla hepsi `multi_axis` diye eleniyor ve
liste bos kaliyordu - belgelenen ozellik hic calismiyormus gibi. Bos liste
"mutabakat yapilamadi" ile "her sey tuttu"yu ayirt edilemez birakir; artik
satir kaliyor, sebebi yaninda.

**Ciddi 7 - bolum indeksi gercek basliklari eliyordu.** Olculdu (JPMorgan
10-K): Item 7 (MD&A) ve Item 8 `available_sections` icinde YOK ve isimle
istenince "bu dosyalamada bulunamadi" hatasi doniyordu - metinde apacik
dururken. Sebep: bir aday ancak KENDISINDEN SONRAKI ilk adaya olan mesafe
esigi asiyorsa bolum sayiliyor ve banka MD&A'yi sayfa referansiyla dahil
ettigi icin Item 7/7A/8 pesi sira duruyor. Var olan bir seyin YOKLUGUNU iddia
etmek, bulamamaktan kotudur: indeks kacirdiginda govde araniyor ve bulunan
`section_source="search"` diye isaretleniyor.

**Ciddi 8 - tek noktali ilgisiz etiket seriyi ele geciriyordu.** Olculdu
(Perrigo): `Revenues` etiketinde SEC'te TEK bir veri noktasi var, 800.000
dolar; `SalesRevenueNet`'te 42 nokta ve ayni donem icin 3.539.800.000. Ikisi
de ayni gun dosyalandigi icin `filed` esit cikiyor ve siralama alias sirasina
dusup copu seciyordu. Seri "3,17 mlr -> 0,8 mn -> 3,91 mlr" okunuyordu.
Esitlik bozucu artik etiketin AGIRLIGI (sirketin fiilen kullandigi etiket), ve
iki etiket ayni donem icin celistiginde `tag_conflicts` bunu bildiriyor -
dogru secilse bile cagirani olculmemis bir kesinlikle birakmamak icin.

**Ayrica:** 13F-HR/A duzeltmesi hicbir isaret olmadan tam portfoy gibi
donuyordu (olculdu: Berkshire'in bir duzeltmesi "1,7 milyar dolar, tek
pozisyon" gibi gorunuyordu; gercek portfoy ~313 milyar). `RESTATEMENT`
orijinalin YERINE gecer, `NEW HOLDINGS` ona EKLENIR - simdi ikisi de yanitta.
Form 4/A da ayni sekilde bildiriliyor.

**Denetimin kendi dersi:** bulgularin cogu CANLI kullanimdan geldi, test
paketinden degil. Test paketi 268 yesildi ve bu sekiz hatanin hicbirini
gormuyordu - cunku sahte veri gercegin sozlesmesindeki bu durumlari
tasimiyordu (ayni gun biten iki donem, cok sahipli Form 4, arka arkaya duran
basliklar, tek noktali etiket, duzeltme kutulari). **P-4, dorduncu kez.** Her
duzeltme once fixture'a girdi, sonra koda.

Yirmi dokuz yeni enjeksiyon dogruluyor. Ikisi ilk turda "KORUMASIZ" dondu ve
ikisi de testin ne olctugunu duzeltti - biri fixture'in senaryoyu hic
uretmedigini, oteki kuralin yanlis capayi tuttugunu gosterdi.

### KK-48: Denetimin ikinci yarisi - olcum makinesi ve dokumanlar

18 Agu 2026, ayni denetim turu. Kodun disindaki bulgular.

**`--kontrol` kendi kapatmasi gereken bosluga acikti (P-36).** KK-41'de
"cokmeden sonra paketlenmesin" diye yazilan kontrol, kaynak dosyalari YALNIZCA
`.enjeksiyon_yedek/` varsa karsilastiriyordu - ve o dizin `.gitignore`'da. Taze
klon, `git clean -fdx` ya da elle temizlik tek kaniti siliyor; enjekte kalmis
dosya duruyorken cikti "TEMIZ" diyor ve exit 0 donuyordu. Denetci bunu depo
kopyasinda ELLE URETTI. Ikinci yarisi CI'daydi: kontrol adiminda `if: always()`
yoktu, yani yalnizca sweep ZATEN basarili oldugunda kosuyordu - bulunacak bir
sey olmayan tek durumda.

Duzeltme uc parcali: (1) karsilastiracak yedek yokken cikti artik "TEMIZ"
DEMIYOR, neye bakip neye bakmadigini soyluyor; (2) `--sert` ikinci ve bagimsiz
bir kaynak olarak `git diff`e bakiyor, teyit edemezse exit 3; (3) CI
`--kontrol --sert` ve `if: always()`. `--sert` varsayilan DEGIL cunku calisma
kopyasinda korunan dosyalar HEAD'den zaten farkli olur ve her seferinde
basarisiz olan bir kontrol, gormezden gelinmeyi ogretir.

**Docker imaji DERLENMIYORDU (P-20'nin tekrari).** `Dockerfile` yalnizca
`pyproject.toml README.md src/` kopyaliyor, ama `pyproject.toml`
`license = { file = "LICENSE" }` diyor. `pip install .` build aninda
`OSError: License file does not exist: LICENSE` veriyor. Iki README, PUBLISHING
ve vaka calismasi calismayan bir komut gosteriyordu. Kopyalanan dosya kumesi
bos bir dizine cikarilip ayni backend calistirilarak uretildi; `LICENSE`
eklenince build gecti. **`tests/test_http_tasima.py` Dockerfile'in yalnizca
METNINI greplediği icin bunu goremiyor** - imaji derlemiyor. CI'daki `docker`
isi yakalardi; yani hata "CI hic kosmamis" degil, "CI'nin yakaladigi bir sey
belgede aylardir yanlis duruyordu".

**`server.json` imajin konusmadigi tasimayi ilan ediyordu:** `stdio`, oysa
Dockerfile'in tek `CMD`'si streamable-HTTP. Kayit defterinden bu girdiyi okuyup
imaji stdio bekleyerek baslatan istemci hicbir zaman cevap alamazdi. Mevcut
kimlik testi yalnizca ADI karsilastiriyordu; tasima da ayni dosyada duran bir
vaat ve artik o da testli.

**Benchmark raporunda uc hucre yanlisti.** Tur bazli tablonun "Without"
sutununda uc satir ILK kosunun rakamlarini tasiyordu (Numerical Reasoning 2/8
yerine 3/8, Qualitative 2/9 yerine 1/9, Adjustments 4/4 yerine 3/4). Elle
kopyalanmis, yeniden hesaplanmamis. Tablo artik ham JSON'dan uretildi. Ayni
bolumdeki "sifir yanlis, on sekiz cekimser" cumlesi de ilk kosuya aitti; ikinci
kosuda kontrol kolu UC yanlis rakam veriyor ve 17 soruyu cevaplamiyor - manset
"araci kol hic yanlis rakam vermedi" derken kontrol kolu icin de ayni seyi ima
ediyordu. Duzeltildi.

**`.env.example` iki degiskeni belgelemiyordu** (`SEC_RATE_LIMIT_PER_SEC`,
`SEC_AS_OF`) ve bekci test TEK YONLUYDU: belgelenen her degiskenin kodda
gectigini kontrol ediyor, kodun okudugu her degiskenin belgelendigini degil.
P-14'un bekcisi P-14'e acikti. Test iki yonlu yapildi; ayrica degisken adi bir
SABIT uzerinden okundugu icin (`AS_OF_ORTAM`) `os.environ.get("...")` kalibini
aramak yetmiyor - kaynaklardaki her `SEC_*` dizgesi taraniyor.

**Bayat dokuman sayilari:** "dort arac ilerleme bildiriyor" (sekiz bildiriyor),
Turkce README'de 12 takma ad (15 var), "ten measured questions" (22 var).
Vaka calismasindaki bir "Measured" blogu ise DUZELTILMIS degil DUZELTILMEMIS
davranisi gosteriyordu ve dosyanin basligi "her sayi bir testle yeniden
uretiliyor" diyordu - ikisi birlikte, artik yeniden uretilemeyen bir rakami
uretilebilir gibi sunuyordu. Blok "duzeltmeden onceki surumde olculdu" diye
etiketlendi ve baslik daraltildi.

**Kapanmamis olarak kayda geciyor:** notlandirici tam anlamiyla "kor" degil -
araci kolun cevaplari erisim numarasi tasiyor, kontrol kolununkiler tasimiyor,
yani bicim tek basina hangi kolun hangisi oldugunu ele veriyor olabilir. Rapor
"blind" diyor; dogrusu "hangi sistemin hangisi oldugu SOYLENMEDI" ve bu ikisi
ayni sey degil. Bir sonraki olcum turunda cevaplar notlamadan once
normalize edilecek. Bugun rapora yazildi, duzeltilmedi.

### KK-49: CI dort gundur kirmiziydi - olcen aracin kendi encoding hatasi

18 Agu 2026. Mirza CI'nin kirmizi oldugunu ve Carsambadan beri hata maili
geldigini bildirdi. Ilk hatali kosu **CI #15** (commit `d90f98f`, "Add filing
text reader with section extraction"); ondan sonraki **17 kosunun hepsi**
kirmizi. README'de CI rozeti duruyor ve depo public - yani "failing" yazisi
dort gundur potansiyel musterinin gordugu ilk seylerden biriydi.

**Iki ayri sebep vardi ve karistirilmamali.**

**1. `docker` isi (12 saniyede dusuyordu).** `Dockerfile` yalnizca
`pyproject.toml README.md src/` kopyaliyordu, ama `pyproject.toml`
`license = { file = "LICENSE" }` diyor: `pip install .` build aninda
`OSError: License file does not exist: LICENSE` veriyor. **Bu zaten KK-48'de
bulunmus ve v41'de duzeltilmisti**; CI #31'de `docker` isi yesil dondu, yani o
taraf kapali.

**2. `fault-injection (windows-latest, 1/4)` (54 dakikada 44/45).** Kalan tek
satir:

```
Belge: satir basi isaretlerine izni kaldir (tablo yerlesi   KORUMASIZ   ENJEKSIYON UYGULANAMADI
```

Butun Linux parcalari ve Windows'un 2/3/4 parcalari yesildi.

**Kok neden.** `arac/enjeksiyon.py` enjeksiyonu uygularken kaynagi
`Path.read_text()` ile okuyordu - `encoding` verilmeden. O cagri yerel kod
sayfasini kullanir; Windows runner'inda cp1252. `src/edgar_mcp/belge.py`
icindeki `_ONEK` duzenli ifadesi bir **en dash** ve bir **em dash**
tasiyor (bir bolum basligi HTML tablo hucresi icinde baslayabilsin diye -
KK-27'nin dorduncu karari). cp1252 ile cozulunce o iki karakter baska
karakterlere donuyor, enjeksiyon dizgisi metinde artik gecmiyor, harness
uygulayamiyor.

**Harness DOGRU davrandi.** Durumu tespit etti, adini koydu ve exit 1 dondu
(KK-10). Yanlis olan raporlama degil, OLCEN ARACIN kaynagi yanlis decoder'dan
okumasiydi. Hata korunan kodda degil, korumayi olcen aracta.

**Ayni ihmalin iki sonucu daha** (gozlenmedi ama artik korunuyor):
`write_text()` de ayni kod sayfasindan geri kodlar, ve metin modu satir sonu
cevirisi yapar - yani Windows'ta geri yukleme adimi korunan dosyalarin hepsini
CRLF ile yeniden yazardi. Harness'in "hicbir dosyayi degistirmedim" iddiasi
bayt duzeyinde yanlis olurdu. Bu yuzden duzeltme `encoding="utf-8"` eklemek
DEGIL, `oku`/`yaz` yardimcilariyla **bayt duzeyinde** okuyup yazmak oldu:
`read_bytes().decode("utf-8")` ve `encode("utf-8")` hem kod sayfasini sabitler
hem satir sonu cevrimini kapatir. `yedekle`/`geri_al` zaten boyle calisiyordu;
enjeksiyon dongusu bu disiplinin disinda kalmisti.

**Ucuncu ornek, tekrar uretim sirasinda cikti.** Bir test fonksiyonunun adinda
Turkce `ı` vardi (`aramasi`'nin son `i`'si). pytest her testin adini
`PYTEST_CURRENT_TEST` ortam degiskenine yaziyor ve `os.putenv` degeri yerel kod
sayfasina ceviriyor; ASCII yerel ayarda bu `UnicodeEncodeError` ile TOPLAMA
asamasinda patliyor - test ne kosuyor ne atlaniyor. KK-9 "disariya bakan yuzey
Ingilizce" diyordu ama YORUMLAR icin; tanimlayicilar hic denetlenmemisti.

**Hata Linux'ta URETILDI, varsayilmadi.** `LC_ALL=C PYTHONUTF8=0 python -X
utf8=0` ile `locale.getpreferredencoding(False)` `ANSI_X3.4-1968` donuyor ve
`read_text()` `belge.py`'de `UnicodeDecodeError` firlatiyor. Bu, Windows
cp1252'sinin birebir ayni yolu (hata degil MOJIBAKE) degil ama ayni koku olcen
en yakin yerel kosum. Uc dogrulama yapildi:
- Duzeltme geri alinip test kirmiziya dondurulduу (iki yonde de: `oku` ve `yaz`).
- Tum test paketi ASCII yerel ayar altinda yesil (289/289).
- 1/4 parcasi (hatanin ciktigi parca) ASCII yerel ayar altinda kosuldu.

**Kendi hatam, kayda geciyor.** Tekrar uretim testinin ilk yazimi "her
enjeksiyon hedefi dosyasinda bulunuyor mu" diye soruyordu. O test HERHANGI bir
enjeksiyon uygulanmisken kirmiziya doner - yani harness'in gozunde **evrensel
bir yakalayici**. Nitekim ilk kosuda belge enjeksiyonunun "yakalayan test"i
olarak kendisi gorundu. Boyle bir test, gercekten korumasiz bir enjeksiyonu
"yakalandi" diye gosterir ve olcum makinesini korlestirir - KK-41'de `None` ile
bos listeyi ayirma sebebinin aynisi. Test, hedef listesini degil OKUYUCUYU
olcecek sekilde yeniden yazildi. Hedeflerin dosyada bulunmasi zaten harness'in
kendi isi (KK-10) ve pytest'te tekrarlanmamali.

**Uc test sabitliyor**, ucu de enjeksiyonla DEGIL dogrudan sinaniyor - KK-41'de
oldugu gibi, harness'in kendisi enjeksiyon hedefi degil:
- `test_harness_kaynagi_yerel_kod_sayfasindan_bagimsiz_okuyup_yaziyor` - ASCII
  yerel ayarli alt surec; platformda kod sayfasi zaten UTF-8 ise SESSIZ
  gecmiyor, `skip` ediyor.
- `test_hicbir_metin_dosyasi_okumasi_yerel_kod_sayfasina_birakilmiyor` - AST
  taramasi; `encoding`siz `read_text`/`write_text`/`open` yasak. On cagri
  bulundu ve duzeltildi (dokuzu testlerde, biri harness'ta).
- `test_hicbir_tanimlayici_ascii_disi_karakter_tasimiyor` - AST taramasi.

**Kayda gecen, duzeltilmeyen bulgu.** KK-18 "enjeksiyon hedefi dosyada TEK
gecmeli" diyor ama bunu hicbir test zorlamiyor ve iki hedef kurali ihlal
ediyor: takma ad fallback'i (2 eslesme) ve `read_only_hint` (12 eslesme).
Ikisi de su an GECERLI donuyor, cunku `replace(..., 1)` ilk eslesmeyi bozuyor
ve dogru testi kirmiziya ceviriyor. Yani bugun yanlis bir sey olculmuyor;
kirilganlik, kodun ilerideki bir duzenlemesinde ilk eslesmenin baska bir yere
kaymasi. Bu turda DOKUNULMADI - CI'yi yesile dondurmek disinda bir degisiklik
yapmamak icin. Ayri bir is olarak duruyor.

P-37 olarak kayda gecti.
