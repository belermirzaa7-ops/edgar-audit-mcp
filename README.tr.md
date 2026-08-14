# SEC EDGAR MCP Sunucusu

*[English README](README.md)*

Bir dil modelinin finansal veriyi **hafızasından hatırlamak yerine SEC'in resmi
kayıtlarından okumasını** sağlayan bir [Model Context Protocol](https://modelcontextprotocol.io)
sunucusu. Bu araçlar üzerinden dönen her rakam, belirli bir SEC dosyalamasına,
belirli bir US-GAAP etiketine ve belirli bir sunulma tarihine kadar izlenebilir.

**2026-07-28 MCP spesifikasyonuna** göre, Python SDK `v2.0.0` ile yazıldı.

---

## Neden var

Bir dil modeline bir şirketin gelirini sorarsanız hafızasından cevap verir.
Cevap genelde yakın, bazen yanlış ve hiçbir zaman doğrulanabilir değildir.
Finansal işler için bu kullanılamaz.

Bu sunucu hatırlamayı bir sorguyla değiştirir. Ama "SEC API'sini çağır" demek
de yeterli değil — SEC'in XBRL verisi, **sessizce yanlış** cevap üreten birkaç
tuzak barındırıyor. Bu projenin asıl kısmı o tuzakları ele alması.

## Araçlar

| Araç | Ne yapar |
|---|---|
| `sec_edgar_get_company_profile` | Ticker → CIK, resmi unvan, SIC sektörü, mali yıl sonu |
| `sec_edgar_list_filings` | Son dosyalamalar, form türüne göre filtrelenebilir |
| `sec_edgar_get_concept_series` | Tek bir finansal kalemin zaman serisi |
| `sec_edgar_get_fact_revisions` | Bir rakamın dosyalamalar arasında nasıl değiştiği — yeniden düzenlemeler, her değişimin erişim numarasıyla |
| `sec_edgar_read_filing_text` | XBRL'in taşımadığı anlatı: MD&A, risk faktörleri, vergi ve segment dipnotları; 8-K ekleri ve dosyalama içi arama dahil |
| `sec_edgar_list_available_concepts` | Şirketin fiilen raporladığı etiketler, kullandığı her taksonomide |

Her araç Pydantic modeli döndürür; MCP `outputSchema` otomatik üretilir ve
istemci sonuçları tip güvenli tüketir. Liste döndüren araçlar
`total_matching` / `returned` / `has_more` bildirir; böylece model tam bir
cevapla kırpılmış bir cevabı ayırt edebilir.

Kalemler takma adla (`revenue`, `net_income`, `public_float`, ...) ya da ham
etiketle çağrılır. Etiket taksonomisiyle nitelenebilir — `dei:EntityPublicFloat`
— önek yoksa `us-gaap` varsayılır. `sec_edgar_list_available_concepts` şirketin
fiilen kullandığı taksonomileri bildirir, böylece model tahmin etmez: mali
tablolar `us-gaap` içinde, halka açıklık oranı ve hisse adedi `dei` içindedir.

Her araç `readOnlyHint: true` ilan eder. Bu bir **ipucudur**, garanti
değil — garanti, pakette hiçbir yazma yolunun bulunmaması ve bunu bir testin
zorunlu tutmasıdır.

### Dosyalama metnini okumak

XBRL rakamı taşır, gerekçeyi taşımaz. `sec_edgar_read_filing_text` dosyalamanın
kendisini okuyup adlandırılmış bir bölümü döndürür — MD&A, risk faktörleri,
gelir vergisi dipnotu.

Bunu göründüğünden zorlaştıran iki şey var ve ikisi de testle korunuyor:

- **İçindekiler tablosu bölümle aynı şeyi yazar.** "Item 7. Management's
  Discussion and Analysis" bir 10-K'da en az iki kez geçer: bir kez içindekiler
  girişi, bir kez bölümün kendisi. İlk eşleşmeyi almak modele iki satırlık bir
  gezinme listesi verir ve bölüm boş görünür. Bir başlık, ancak ardından
  gerçek metin geliyorsa bölüm sayılır; yine de iki kez geçiyorsa uzun olan
  kazanır.
- **Dosyalamalar milyonlarca karakter.** Metin `offset` / `has_more` ile
  sınırlı parçalar hâlinde döner. Önbellekte ham HTML değil **çevrilmiş metin**
  durur: 2,2 MB HTML'i çevirmek ölçülen 0,61 saniye, yani her sayfa çevirmede
  yeniden ayrıştırmak saniyeleri harcıyordu; ayrıca metin, geldiği işaretlemeden
  yaklaşık yirmi kat küçük.
- **Dosyalamanın işaret ettiği belge, içeriği taşıyan belge olmayabilir.** SEC
  her dosyalama için tek bir birincil belge adlandırır; 8-K'da o belge kapak
  sayfasıdır, içerik ektedir. Tesla'nın 2026 Q2 teslimat bülteninde ölçüldü
  (`0001628280-26-046717`): kapak 26.572 bayt ve hiçbir rakam taşımıyor, ek
  13.243 bayt ve rakamların tamamı orada. Dosyalamadaki okunabilir dosyaların
  tamamı her çağrıda listeleniyor, birincil olan işaretleniyor ve `document`
  ile herhangi biri okunabiliyor.

Araç bölümsüz çağrılırsa dosyalamanın gerçekten sahip olduğu başlıkları
döndürür; ikinci çağrı tahmin etmek yerine birini adıyla ister. Doğru başlığın
ne olduğu belli değilse `search` bir ifadenin kaç kez ve nerede geçtiğini
bildirir; her konum doğrudan `offset` olarak geri verilebilir.

## Ele alınan üç tuzak

### 1. `fy` alanı verinin değil, dosyalamanın yılıdır

SEC'in `companyconcept` API'si her kayda `fy` ve `fp` iliştirir. Bunu değerin
mali yılı sanmak doğal görünüyor. Değil — o, değerin **içinde geçtiği
dosyalamanın** mali yılı. Bir 10-K üç yıllık karşılaştırma içerir ve üçü de
dosyalamanın `fy`'sini taşır.

`fy`'yi doğrudan kullanmak Apple'ın gelir serisini iki yıl kaydırdı ve hiçbir
hata vermedi. Bu sunucuda dönem yalnızca `start`/`end` tarihlerinden
belirlenir: yıllık 300–400 gün, çeyreklik 60–120 gün.

### 2. Mali yıl adlandırmasının evrensel kuralı yok

Walmart'ın 2026-01-31'de biten mali yılı **FY2026**. Target'ın 2026-01-31'de
biten mali yılı **FY2025**. Aynı bitiş tarihi, farklı etiket — Walmart mali
yılı bittiği takvim yılıyla, Target başladığı yılla adlandırıyor. Hiçbir sabit
kural ikisini birden doğru yapamaz.

O yüzden kural kullanılmıyor. `_fy_kaymasi()` kaymayı her şirket için SEC'in
kendi verisinden türetiyor: her `fy` grubunda en geç biten yıllık dönem, o
dosyalamanın kendi dönemidir ve `kayma = fy − bitiş_yılı` çapasını verir. Çapa
bulunamazsa yanıt sessizce tahmin etmek yerine `fiscal_year_derived: false`
döndürür.

### 3. Etiket değişimi geçmişi kırpar

Apple, ASC 606 öncesinde geliri `SalesRevenueNet`, sonrasında
`RevenueFromContractWithCustomerExcludingAssessedTax` ile raporladı. Veri
dönen ilk etikette durmak **on yıllık** geçmişi sessizce siliyordu.

Takma adlar tüm aday etiketleri birleştirir. Dönemler örtüştüğünde en son
sunulan değer kazanır. Her nokta bir `source_tag` taşır; böylece her rakamın
kaynağı görünür kalır — farklı etiketler aynı kalemi birebir aynı tanımla
ölçmeyebilir ve bu fark gizlenmek yerine yüzeye çıkarılır.

## Kullanım

Kavramlar ham XBRL etiketiyle değil, takma adla istenir:

```
sec_edgar_get_concept_series(ticker="MSFT", concept="revenue", limit=5)
```

Mevcut takma adlar: `capex`, `cash`, `eps_diluted`, `gross_profit`,
`net_income`, `operating_cash_flow`, `operating_income`, `revenue`,
`rnd_expense`, `stockholders_equity`, `total_assets`, `total_liabilities`.
Ham US-GAAP etiketleri de kabul edilir. Bir kavram bulunamadığında hata mesajı
geçerli takma adları sayar ve keşif aracını gösterir — hata metinleri sadece
başarısızlığı bildirmek için değil, modelin ona göre hareket edebilmesi için
yazıldı.

## Kurulum

```bash
uv sync                      # veya: pip install -e ".[dev]"
cp .env.example .env         # SEC_USER_AGENT'a adını ve e-postanı yaz
```

SEC, otomatik istemcilerin `User-Agent` başlığında iletişim e-postasıyla
kendilerini tanıtmasını ve saniyede 10 isteği aşmamasını şart koşuyor
([SEC Webmaster FAQ](https://www.sec.gov/os/webmaster-faq#developers)). Bu
sunucu kendini 8 istek/sn'de sınırlar ve `SEC_USER_AGENT` yoksa **başlamayı
reddeder**.

**Değişken nereden geliyor.** MCP sunucusu ortamını kendisini çalıştıran
uygulamadan alır — Claude Desktop config'indeki `env` bloğu, Docker'ın
`--env-file`'ı ya da kabuğun. Çekirdek paket bilerek `.env` okumaz; bu
yollarda hiçbir şey kazandırmayacak bir çalışma-zamanı bağımlılığı olurdu.
Yerel scriptler (`dene.py`, `dogrula.py`) ise `.env` okur — `[dev]`
ekstrasındaki `python-dotenv` üzerinden — böylece her yeni terminalde
değişkeni elle vermek gerekmez.

## Çalıştırma

```bash
uv run mcp dev src/edgar_mcp/server.py    # MCP Inspector
uv run sec-edgar-mcp                      # stdio, Claude Desktop vb. için
docker build -t sec-edgar-mcp . && docker run --env-file .env -p 8000:8000 sec-edgar-mcp
```

Claude Desktop yapılandırması:

```json
{
  "mcpServers": {
    "sec-edgar": {
      "command": "/mutlak/yol/.venv/bin/python",
      "args": ["-m", "edgar_mcp.server"],
      "env": { "SEC_USER_AGENT": "Adin Soyadin sen@ornek.com" }
    }
  }
}
```

## Testler

```bash
pytest -q                  # HTTP katmanı mock'lu; sec.gov'a hiç çıkmaz
python arac/enjeksiyon.py  # hata enjeksiyonu
python arac/sir_tarama.py --gecmis   # sır taraması, çalışma dizini + git geçmişi
python dogrula.py          # canlı SEC verisine karşı doğrulama
python arac/tani.py KO Assets           # tek bir SEC yanıtını ham haliyle incele
python arac/tani.py KO Assets --matris   # aynı veriyi farklı koşullarda iste, sebebi ayır
python arac/tani.py --tarama             # kaç şirket etkileniyor
```

### Hata enjeksiyonu

Hiç kırmızıya döndüğü görülmemiş bir test kanıt değildir.
`arac/enjeksiyon.py` her korumayı sırayla bilerek bozar, ilgili testin
kırmızıya döndüğünü doğrular, sonra dosyayı geri yükler ve geri yüklemeyi
hash ile teyit eder.

Bu süs değil. Bu depoda geçtiği hâlde hiçbir şey korumayan iki test yakaladı —
ikisinde de sahte veri gerçek API'nin sözleşmesini taklit etmiyordu, dolayısıyla
test edilen kod yolu hiç çalışmıyordu. Ayrıca bir refactor sonrası bayatlayan
enjeksiyonları da yakalar; CI'da çalışmasının sebebi bu.

### Sır taraması

`arac/sir_tarama.py` çalışma dizinini tarar; `--gecmis` ek olarak git geçmişini
tarar. Fark önemli: commit'lenip sonra silinen bir sır dosyalardan kaybolur ama
geçmişte okunabilir kalır — yalnızca çalışma dizinini tarayan bir araç "temiz"
der ve sır public durmaya devam eder.

Tarayıcı, geçmişin tamamını göremediğinde temiz demeyi reddeder: sığ klonda
exit code 0 değil 2 döner. CI bu yüzden `fetch-depth: 0` ile klonluyor.
Sessizce hiçbir şey yapmayan bir kontrol, kontrol olmamasından kötüdür.

### Taşıma katmanı doğrulaması

README'nin kendi talimatları test paketinde gerçekten çalıştırılıyor. Bir test
streamable-HTTP taşımasını boş bir portta ayağa kaldırıp `tools/list`'i gerçek
HTTP üzerinden, el sıkışmasız soruyor — 2026-07-28 durumsuz çekirdeğinin
gerektirdiği davranış da bu. Bir diğeri `python -m edgar_mcp.server`'ı stdio
üzerinden, SDK'nın kendi istemcisiyle başlatıyor: masaüstü MCP istemcilerinin
kullandığı yolun aynısı. CI'daki `docker` işi imajı kurup konteyneri
**dışarıdan** sorguluyor.

Bu iş gerçek bir kusur yüzünden var: SDK varsayılan olarak `127.0.0.1`'e
bağlanıyor ve bu, konteyner içinde yayınlanan portu ölü bırakıyor. İmaj hiç
çalıştırılmamıştı, dolayısıyla kimse fark etmemişti.

### Canlı doğrulama

Mock'lar gerçek sisteme karşı davranışı kanıtlayamaz. `dogrula.py`, mali yıl
türetmesini ve etiket birleştirmeyi canlı SEC verisine karşı sınar — takvim
yılı, bitiş yılı ve başlangıç yılı geleneklerini kullanan şirketlerle.

### Değerlendirme seti

[`evaluation/questions.xml`](evaluation/questions.xml), yalnızca araçlar
çağrılarak cevaplanabilecek on soru tutuyor: şirketler arası mali yıl
adlandırması, muhasebe standardı değişiminde etiket birleştirme, iki seri
gerektiren oranlar ve sayfalama alanları. Her cevap araçlar canlı SEC verisine
karşı çalıştırılarak üretildi — hiçbiri ezberden yazılmadı — ve her soru hangi
çağrılarla ölçüldüğünü kaydediyor, böylece ölçüm tekrarlanabilir.

Bir test dosyayı yapısal olarak dürüst tutuyor: on çift, her çiftte soru, cevap
ve ölçüm bloğu, adı geçen her aracın sunucuda gerçekten var olması ve hiçbir
sorunun "en son dönem" gibi bayatlayacak bir ifadeye bağlanmaması.

## Hata patternleri

[`PATTERNS.md`](PATTERNS.md), bu depoda **gerçekten yaşanmış** her hatayı
kataloglar — belirti, kök neden, bugün nasıl tespit edildiği ve onu üreten
olay — ve her birini hangi testin koruduğunu söyler. Otomatik koruması olmayan
kayıtlar bunu hem kontrol listesinde hem kendi gövdesinde açıkça yazar;
boşluğu gizlemek boşluğun kendisinden kötü olurdu.

Dokümanı dürüst tutan ayrı bir test paketi var: adı geçen her test, araç ve CI
işi gerçekten var olmalı, her kayıt dört alanı taşımalı, her olay tarihli
olmalı. Bir test yeniden adlandırılırsa doküman sessizce yalan söylemek yerine
CI'ı kırmızıya çevirir.

## Dizin yapısı

```
src/edgar_mcp/server.py   MCP araçları ve şemalar
src/edgar_mcp/client.py   SEC HTTP istemcisi, hız sınırlayıcı, önbellek
tests/                    mock'lu birim testleri
tests/dil.py              dışa bakan yüzey için dil kontrolü
tests/test_http_tasima.py belgelenen HTTP ve stdio taşımalarını çalıştırır
evaluation/questions.xml  ölçülmüş on soru ve hangi çağrılarla ölçüldükleri
arac/enjeksiyon.py        hata enjeksiyonu harness'ı
arac/sir_tarama.py        sır tarayıcı
arac/tani.py              tek bir SEC yanıtını ham haliyle ölçen tanı aracı
dogrula.py                canlı SEC doğrulaması
CLAUDE.md                 karar kayıtları - neden böyle yapıldı
PATTERNS.md               hata patternleri - neye dikkat edilecek
```

Kod yorumları ve karar kayıtları Türkçe; dışarıya bakan yüzey — araç tanımları,
şemalar, hata mesajları ve İngilizce README — İngilizce.

## Lisans

MIT
