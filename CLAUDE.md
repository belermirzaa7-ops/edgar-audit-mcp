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

Dort arac da `read_only_hint=True, destructive_hint=False, idempotent_hint=True,
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
