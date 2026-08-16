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
| `sec_edgar_list_filings` | Şirketin dosyalamaları, form türüne göre filtrelenebilir; `include_older` ile SEC'in ~1000 kayıtlık son dosyalama akışının ötesine geçer |
| `sec_edgar_search_filings` | Tüm dosyalayanlar arasında tam metin arama — bir ifadeyi içeren dosyalamaları, onu taşıyan ekin adına kadar bulur |
| `sec_edgar_get_concept_series` | Tek bir finansal kalemin zaman serisi |
| `sec_edgar_get_fact_revisions` | Bir rakamın dosyalamalar arasında nasıl değiştiği — yeniden düzenlemeler, her değişimin erişim numarasıyla |
| `sec_edgar_read_filing_text` | XBRL'in taşımadığı anlatı: MD&A, risk faktörleri, vergi ve segment dipnotları; 8-K ekleri ve dosyalama içi arama dahil |
| `sec_edgar_list_available_concepts` | Şirketin fiilen raporladığı etiketler, kullandığı her taksonomide |
| `sec_edgar_compare_companies` | Bir kavramın, o dönemde raporlayan tüm şirketlerdeki değeri; sıralı |
| `sec_edgar_list_fact_dimensions` | Dosyalamanın içerdiği kırılımlar — segment, coğrafya, ürün hattı |
| `sec_edgar_get_dimensional_facts` | Konsolide toplamın arkasındaki rakamlar, toplamıyla yan yana |

Her araç Pydantic modeli döndürür; MCP `outputSchema` otomatik üretilir ve
istemci sonuçları tip güvenli tüketir. Liste döndüren araçlar
`total_matching` / `returned` / `has_more` bildirir; böylece model tam bir
cevapla kırpılmış bir cevabı ayırt edebilir.

Kalemler takma adla (`revenue`, `net_income`, `public_float`, ...) ya da ham
etiketle çağrılır. Etiket taksonomisiyle nitelenebilir — `dei:EntityPublicFloat`
— önek yoksa `us-gaap` varsayılır. `sec_edgar_list_available_concepts` şirketin
fiilen kullandığı taksonomileri bildirir, böylece model tahmin etmez: mali
tablolar `us-gaap` içinde, halka açıklık oranı ve hisse adedi `dei` içindedir.

Birkaç saniye sürebilen dört araç — dosyalama okuma, XBRL instance ayrıştırma,
binlerce şirketlik çerçeve sıralama — çalışırken ilerleme bildiriyor; 2026-07-28
spesifikasyonu bu yeteneği tam olarak bu durum için tanımlıyor. Diğerleri
bildirmiyor: milisaniyede dönen bir çağrıda ilerleme gürültüdür. `tools`
dışında başka hiçbir yetenek bilerek uygulanmadı — salt okunur bir veri
sunucusunda `resources`, `prompts` ve `completions` süs olurdu; `logging`,
`sampling` ve `roots` ise zaten bu spesifikasyon revizyonunda kullanımdan
kaldırıldı.

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

### Sembolü olmayan bir dosyalayanı adreslemek

`ticker` alan her araç CIK de kabul ediyor — `320193`, `0000320193` ya da
`CIK0000320193`. Bu bir kolaylık değil: SEC'in ticker dosyası yalnızca işlem
gören sembolleri tutuyor, dolayısıyla fonların ve yabancı ihraççıların sembolü
yok ve tam metin araması onları `ticker: null` ile döndürüyor. CIK adreslemesi
olmadan sunucu, bulduğu belgeyi açamıyordu.

Sorulan sembol sorulduğu gibi geri dönüyor — `GOOGL` yazıldıysa aynı CIK'teki
alfabetik ilk sembole (`GOOG`) dönüşmüyor. CIK ile sorulduğunda sembol SEC'in
dosyasından aranıyor; yoksa uydurulmuyor, boş kalıyor.

### Metnin yanında tabloları da okumak

Dosyalamaların en çok alıntılanan rakamları tablolarda duruyor — mali tablolar,
vergi mutabakatı, XBRL'in hiç etiketlemediği üretim/teslimat bülteni. Düz metne
çevrildiğinde tablo ` | ` ile birleştirilmiş hücrelere dönüşüyor ve sütunları
göz kararı hizalamak okuyana kalıyor.

`sec_edgar_read_filing_text`'e `tables` verildiğinde, döndürülen metnin içinde
**başlayan** tablolar satır/hücre olarak geliyor. Dikkat edilen noktalar:

- Tablonun `text_offset` değeri `offset` ile aynı koordinatta; böylece tablo
  belgenin tamamına değil, ait olduğu pasaja bağlanabiliyor. Bölüm seçilirse
  konumlar bölümle birlikte kayıyor.
- EDGAR dosyalamaları tabloyu veri kadar sayfa yerleşimi için de kullanıyor.
  Tek satırlık ya da tek sütunluk tablolar dışarıda bırakılıyor — ve
  `layout_tables_skipped` ile sayılıyor, çünkü hiç söylememek "bu dosyalamada
  tablo yok" diye okunur.
- İç içe tablolar birleştirilmeden ayrı ayrı dönüyor ve iç tablonun metni dış
  hücreye kopyalanmıyor: aynı rakamları iki kez döndürmek, toplam alan bir
  modele veriyi iki kez saydırır.
- Satır ve hücre sınırları var ve her biri kendini söylüyor: `row_count`
  yanında `total_rows`, ayrıca `rows_truncated` ve `cells_truncated`.

Burada yeni bir veri yok — aynı sayılar metinde de var. Dönen şey yapı; model
onu yeniden kurmak zorunda kalmıyor.

### Şirketler arası karşılaştırma

Diğer araçlar tek şirket hakkında konuşur. `sec_edgar_compare_companies` SEC'in
`frames` ucunu okur: bir etiketi o dönemde raporlayan **tüm** şirketlerin değeri
— ölçüldü, CY2025Q1 gelir çerçevesinde 2.543 şirket.

Çerçeve, eşdeğer bir sıralama gibi görünür ama tam olarak değildir; yanıt bunu
dipnotta değil veride söylüyor:

- **Bir çerçevedeki dönemler aynı dönem değildir.** SEC her şirketin en yakın
  mali dönemini takvim çerçevesine yerleştirir. CY2025Q1'de dönem bitişleri
  2025-02-23 ile 2025-05-04 arasında değişiyor — yetmiş gün. Apple orada kendi
  mali ikinci çeyreğiyle var: 2024-12-29 / 2025-03-29. Her satır kendi
  `period_end`'ini taşıyor, yanıt da tüm çerçevenin aralığını bildiriyor.
- **Çerçevede olmayan şirket, kavramı raporlamamış demek değildir.** Farklı bir
  etiketle raporlamış ya da mali dönemi çerçeveye oturmamış olabilir. İstenen
  ticker çerçevede yoksa sessizce düşürülmüyor, `missing_tickers` içinde dönüyor.
- **Bilanço kaleminin süresel çerçevesi yoktur.** `Assets` için `CY2025Q1` 404
  verir, var olan çerçeve `CY2025Q1I`'dir. İkisi de deneniyor ve cevaplayan
  yanıtta yazıyor.

Sıra her zaman tüm çerçeveye göre hesaplanır; üç şirket sorulunca biri sırf o
üçün içinde "birinci" olmaz.

### Segment verisi, ve REST API'sinde neden yok

SEC `companyconcept`, `companyfacts` ve `frames` uçlarını "tüzel kişinin
**tamamına** ait fact'leri toplayan" uçlar diye tarif ediyor. Segment rakamı
tüzel kişinin bir **parçasına** ait; o yüzden bu uçlarda kırılım yok. (SEC
"dimensional" kelimesini kullanmıyor; cümleden çıkarılan bu okuma bir çıkarım —
ve ölçüm onu destekliyor: Tesla'nın segment kırılımı `companyfacts`'te yok,
dosyalamanın XBRL'inde var.)

`sec_edgar_list_fact_dimensions` dosyalamanın XBRL instance'ını okuyup gerçekten
içerdiği eksen ve üyeleri bildiriyor; ikinci çağrı tahmin etmek yerine onları
adıyla istiyor. `sec_edgar_get_dimensional_facts` fact'leri döndürüyor — her
biri context id'si, birimi, dönemi ve kendisini niteleyen eksenlerle birlikte.

**İki kez okunmayı hak eden kısım.** Bir kırılım ile onun toplamı **iki ayrı
iddiadır**, ve bu araç ikisini tek denkleme çevirmeyi reddediyor:

- Bazı dosyalamalar o kavram için hiç tüzel kişi geneli toplamı raporlamıyor;
  bazıları toplamı bir üst üyeye işaretliyor, yani toplamın kendisi boyutlu.
- Üyeler her zaman toplamı vermiyor. XBRL US bunun için ayrı bir veri kalitesi
  kuralı yayımlıyor (DQC_0150) — yani vermeyen dosyalamalar var.
- İki ekseni birden taşıyan bir rakam (segment **ve** coğrafya) bir kesişimdir,
  bir segmentin payı değil. Segment toplamına katmak işin bir kısmını iki kez
  sayar.
- `xsi:nil` işaretli bir toplam sıfır değildir.

Bu yüzden sessizce toplama yapılmıyor. Tek eksen istendiğinde yanıt üye
toplamını ve tüzel kişi geneli toplamı farkıyla birlikte yan yana veriyor;
neyi neden dışarıda bıraktığını `members_counted` ve `excluded_from_sum`
alanlarında sayıyla söylüyor. Toplam, dönen SAYFA üzerinden değil dosyalamadaki
TÜM eşleşen fact'ler üzerinden hesaplanıyor — `limit` değiştirmek toplamı
oynatmıyor. Hangi rakamın doğru
olduğuna karar vermek okuyucuya bırakılıyor — buna karar verebilecek tek kişi o.

Kaynak hakkında bir not: okunan dosya `<ad>_htm.xml`, SEC'in dosyalayanın
inline XBRL belgesinden yaptığı **ayıklamadır** — SEC'in kendi dağıtım
spesifikasyonu onu EDGAR üretimi çıktılar arasında sayıyor. Değerler ve
context'ler dosyalayanın, kabuk SEC'in. Zincir bundan daha ileri gidiyor ve bu
varsayılmadı, ölçüldü: Tesla'nın FY2025 instance'ından alınan ilk 200 fact
id'sinin 200'ü de şirketin dosyaladığı 2,4 MB'lık inline belgede bulundu. Yani
dönen bir rakamın `fact_id` değeri, dosyalayanın kendi belgesindeki işaretli
parçayı gösteriyor — SEC'in ayıklamasındaki bir satırı değil. Inline XBRL kademeli olarak zorunlu
oldu (büyük hızlandırılmış dosyalayanlar için 2019-06-15, diğerleri için 2020
ve 2021'de biten dönemler); öncesindeki dosyalamalarda dosyalayanın sunduğu
instance okunuyor.

Bu yedek yol burada bir süre "sınanmadı" diye yazıyordu — dürüsttü ama eksikti.
15 Ağu 2026'da ölçüldü: Tesla'nın Şubat 2012'de dosyaladığı FY2011 10-K'sında
`_htm.xml` hiç yok, şirketin kendi sunduğu 769 KB'lık instance var ve o
instance boyutlu gerçekleri modern bir dosyalamayla **aynı yapıda** taşıyor —
`entity/segment` içinde `xbrldi:explicitMember`, hatta aynı anda iki eksene
bağlı context'ler. Etiket linkbase'i de çözüldü ve bu bir tasarım kararını
doğruladı: 2011 dosyası hiç önek bildirmiyor ve konumlarını `us-gaap_Assets`,
etiket kaynaklarını `us-gaap_Assets_lbl` diye adlandırıyor. Yani etiketi yay
yerine isimlendirme kalıbıyla eşleştiren bir okuyucu, o dosyalamada hiçbir şey
bulamazdı.

Asıl sınır daha geride ve bizim kaldırabileceğimiz bir sınır değil: XBRL,
15 Haziran 2009'dan sonra biten dönemlerden itibaren kademeli olarak zorunlu
oldu; öncesinde hiçbir dosyalama etiketli veri taşımıyor. O dosyalamalarda
rakamlar yalnızca metinde var ve cevap tümüyle metin araçları.

### Tüm dosyalayanların metninde arama

`sec_edgar_search_filings` yukarıdaki araçların tersi yönde çalışır: şirketten
değil, ifadeden başlar. EDGAR'ın tam metin indeksini sorgular; böylece "hangi
şirketler yıllık raporunda gümrük tarifesinden bahsetti" sorusunun, şirketi
önceden bilmeyi gerektirmeyen bir cevabı olur.

Üç noktayı açıkça yazmak gerekiyor, çünkü üçü de sonucun nasıl okunacağını
değiştirir:

- **Bir vuruş dosyalama değil, belgedir.** 15 Ağu 2026'da ölçüldü: Tesla'nın
  yıllık raporlarında *tariff* kelimesinin en eski eşleşmesi 10-K'nin kendisi
  değil, içindeki bir ek — bir tedarik sözleşmesi. Bu yüzden sonuçlar hem
  erişim numarasını hem dosya adını taşıyor; ikisi de doğrudan
  `sec_edgar_read_filing_text`'e girer.
- **Toplam sayı bir alt sınır olabilir.** SEC büyük sonuç kümelerini sayı
  yerine `gte` ilişkisiyle bildiriyor; hangisinin geldiğini `total_is_exact`
  söylüyor.
- **Kapsam 2001 civarında başlıyor ve öncesi için sıfır sonuç bir şey
  kanıtlamıyor.** SEC kendi sayfasında indeksin "2001'den beri" dosyalamaları
  tuttuğunu yazıyor. 1996-2000 arası yıllık raporlarda *revenue* kadar yaygın
  bir kelimenin araması 14 dosyalama döndürdü, en eskisi 1999-03-31 tarihli —
  yani 2001 öncesinden birkaç belge indekste var, çoğu yok. Yanıt bunu kendisi
  söylüyor: boş dönen ya da 2001 öncesine uzanan bir arama, çıplak bir sıfır
  yerine `coverage_note` ile geri geliyor.

Uç, 10000 sıralı sonucun ötesine sayfalamayı reddediyor; şema bunu `offset`
üst sınırı olarak ilan ediyor, modelin hatayla öğrenmesine bırakmıyor.

Ölçülen bir tuhaflık daha, araç yayına girdikten bir gün sonra canlı kullanımda
bulundu: SEC tek taraflı tarih aralığını **sessizce** düşürüyor. "2026'dan
itibaren" diye sorulduğunda 162 sonuç dönüyordu ve en eskisi 2009 tarihliydi —
filtrelenmiş görünen, filtrelenmemiş bir cevap. Eksik uç artık dolduruluyor
(EDGAR'ın kendi başlangıcı ya da bugün) ve gönderilen aralık
`date_range_applied` ile geri dönüyor.

### Son dosyalama akışının ötesindeki dosyalamalar

SEC'in `submissions` ucu son dosyalama akışını yaklaşık bin kayıtta kesip
gerisini ayrı dosyalara taşıyor. Aktif bir dosyalayanda bu, uzun bir geçmiş
değil: Tesla'nın son dosyalama akışı 1.053 kayıtla ancak Mayıs 2018'e iniyor,
tek ek dosyası ise 1.096 kayıtla Şubat 2005'e (15 Ağu 2026'da ölçüldü).

`sec_edgar_list_filings` varsayılan olarak son akışı okur ve daha fazlasının
olup olmadığını söyler. `include_older` verilirse eski akışları da okur,
birleştirir ve tarihe göre sıralar. En fazla dördünü okur ve kaçını atladığını
bildirir; söylenmeyen bir sınır "hepsini gördüm" diye okunur. Eski akışlar
birincil belge adını her zaman taşımıyor, bu yüzden `primary_document_url`
boş olabiliyor; dosyalama erişim numarasıyla açıldığında araç en büyük
okunabilir dosyayı seçiyor ve bu seçimi SEC'in tayini gibi sunmak yerine
`primary_document_known: false` ile tahmin olarak işaretliyor.

### Etiketler ve üyeler için insan okunur adlar

`tsla:OperatingLeaseVehiclesMember` bir dosyalamanın kullandığı addır, bir
insanın yazacağı ad değil. Çevirisi dosyalamanın kendisinde, etiket
linkbase'inde (`*_lab.xml`) duruyor ve boyut araçları onu okuyor: eksenler,
üyeler ve etiketler `axis_label`, `member_label`, `tag_label` alanlarıyla
birlikte dönüyor.

Linkbase adı etikete bir *yay* üzerinden bağlar; kod bu yayı takip ediyor,
üreticilerin kullandığı `loc_`/`lab_` isimlendirmesini değil — bir hata
enjeksiyonu tam bu kestirmeyi deniyor ve test kırmızıya dönüyor. Bir eleman
birden fazla rolde etiketliyse standart rol kazanıyor; ad değil tanım paragrafı
olan `documentation` rolü hiçbir zaman ad olarak kullanılmıyor. Hiçbir şey
uydurulmuyor: dosyalamanın etiketlemediği eleman kendi etiketiyle dönüyor ve
`label_source` etiketlerin hangi dosyadan geldiğini söylüyor, dosya yoksa boş
kalıyor.

Etiketler bir ek indirme demek — Tesla'nın FY2025 yıllık raporunda 2,68 MB'lık
instance'a karşılık 1,21 MB — bu yüzden `include_labels` ile kapatılabiliyor.

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
python arac/tani.py TSLA --etiket        # etiket ayrıştırıcısı gerçek linkbase'de çözüyor mu
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

### Benchmark

[`evaluation/benchmark.md`](evaluation/benchmark.md) bu sunucunun neyi
değiştirdiğini ölçüyor: aynı model,
[Vals AI Finance Agent Benchmark](https://huggingface.co/datasets/vals-ai/finance_agent_benchmark)
setinin açık 50 sorusunu iki kez cevapladı — bir kez hiçbir araç olmadan, bir
kez yalnızca bu on araçla.

| | doğru | kısmen | yanlış | cevap yok |
|---|---|---|---|---|
| **Bu sunucuyla** | **41 (%82)** | 8 | 0 | 1 |
| Araçsız | 12 (%24) | 20 | 0 | 18 |

Cevaplayan kolların hiçbiri beklenen cevabı görmedi; notlandırmayı, iki cevabı
rastgele sırayla ve hangisinin hangi koldan geldiğini bilmeden gören ayrı bir
değerlendirici yaptı. Bütün ham veri — iki kolun cevapları, notlandırma girdisi,
notlar, kol anahtarı — `evaluation/benchmark/` altında, ve sayının sınırları
raporun içinde yazılı.

### Değerlendirme seti

[`evaluation/questions.xml`](evaluation/questions.xml), yalnızca araçlar
çağrılarak cevaplanabilecek yirmi soru tutuyor: şirketler arası mali yıl
adlandırması, muhasebe standardı değişiminde etiket birleştirme, iki seri
gerektiren oranlar ve sayfalama alanları. Her cevap araçlar canlı SEC verisine
karşı çalıştırılarak üretildi — hiçbiri ezberden yazılmadı — ve her soru hangi
çağrılarla ölçüldüğünü kaydediyor, böylece ölçüm tekrarlanabilir.

Bir test dosyayı yapısal olarak dürüst tutuyor: yirmi çift, her çiftte soru, cevap
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
evaluation/questions.xml  ölçülmüş yirmi soru ve hangi çağrılarla ölçüldükleri
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
