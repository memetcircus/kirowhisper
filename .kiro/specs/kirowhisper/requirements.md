# Requirements — KiroWhisper

## Introduction

KiroWhisper, otonom çalışan **Kiro Crew**'i ekrana bakmadan **sesle denetlemeyi**
sağlayan bir katmandır. Bir tarafta Alexa+ (veya simüle edilmiş bir sesli arayüz)
ile konuşur, diğer tarafta Kiro Crew Gateway'in REST API'sini çağırır. Model
Context Protocol (MCP) uyumlu bir server olarak paketlenir (spec 2025-11-25,
Streamable HTTP).

Projenin ayırt edici yeteneği **Ambient Awareness**'tır: Crew'in ürettiği düzinelerce
onay talebini sürekli izler, her birini risk açısından sınıflandırır, düşük riskli
olanları sessizce geçirir, bariz tehlikelileri sessizce engeller, ve **yalnızca
gerçek insan kararı gerektirenleri** sesli olarak kullanıcıya getirir. Bu, sesli
denetimi görme engelli geliştiriciler için **kullanılabilir** kılar (ses, ekran gibi
seri taranamaz; filtre olmadan sesli onay bir işkenceye dönüşür) ve ekrandan uzaktaki
herkes için konfor sağlar (curb-cut etkisi).

**Aktör:** Deniz — görme engelli, home-office geliştirici (ana persona);
curb-cut genişlemesi: ekrandan/masadan uzaktaki her geliştirici.

**Kapsam sınırı:** KiroWhisper bir DENETİM (monitor + approve) katmanıdır, sesle
kod yazma aracı DEĞİLDİR. Yeni görev başlatma v2 kapsamındadır.

**Fizibilite:** Aşağıdaki gereksinimlerin Crew tarafı, canlı bir spike ile
doğrulanmıştır (bkz. `docs/PROJECT_NOTES.md` → "CREW SPIKE SONUÇLARI" ve
`spike/`). Crew Gateway REST uçları, auth (`?token=` + `Origin`), ve programatik
onay (`POST /api/chat/slots/<slot>/approve {action:"approved"}`) çalışır durumda
kanıtlanmıştır.

### Terminoloji
- **Gateway:** Kiro Crew'in yerel REST/WebSocket sunucusu (`http://localhost:5476`).
- **Onay talebi (approval):** Crew'in bir tool'u çalıştırmadan önce durup insan
  kararı beklediği nokta. Ham veri: tool başlığı, amaç (purpose), girdi (diff),
  `is_read_only`, `is_shell`.
- **Risk sınıfı:** LOW (geri alınabilir/salt-okunur), HIGH (geri alınamaz/yıkıcı),
  UNKNOWN (emin olunamayan).
- **Sesli arayüz:** Alexa+ MCP add-on (kimseye açık olmadığından) yerine, kurallara
  uygun **simüle edilmiş sesli deneyim** (kullanıcının kendi sesi + STT + TTS).

---

## Requirement 1 — Ambient Awareness: onay taleplerini sürekli izleme

**User Story:** Bir geliştirici olarak, Crew'in ürettiği tüm onay taleplerinin
arka planda sürekli izlenmesini istiyorum ki hiçbir kararı kaçırmayayım ve her biri
bana tek tek gelmesin.

#### Acceptance Criteria
1. WHEN Crew Gateway'de bir veya daha fazla bekleyen onay bulunduğunda THEN sistem SHALL bunların tümünü periyodik olarak (polling) tespit etsin.
2. WHEN bir onay talebi tespit edildiğinde THEN sistem SHALL o talebin ham verisini (tool başlığı, amaç, girdi/diff, `is_read_only`, `is_shell`) okusun.
3. WHILE Crew çalışırken THE sistem SHALL izlemeyi kesintisiz sürdürsün ve yeni talepleri tespit ettikçe değerlendirsin.
4. IF Gateway'e erişilemezse (bağlantı hatası) THEN sistem SHALL sessizce yeniden denesin ve hiçbir onayı otomatik olarak "geçildi" saymasın.

## Requirement 2 — Risk sınıflandırma (Ambient Awareness'ın zekası)

**User Story:** Bir geliştirici olarak, her onay talebinin riskine göre
sınıflandırılmasını istiyorum ki güvenli işler beni rahatsız etmesin, tehlikeli
işler durdurulsun, sadece gerçek kararlar bana gelsin.

#### Acceptance Criteria
1. WHEN bir onay talebi değerlendirilir THEN sistem SHALL onu LOW, HIGH veya UNKNOWN risk sınıfına atasın.
2. WHERE bir talep salt-okunur (`is_read_only`) veya açıkça geri alınabilir bir düzenleme ise THE sistem SHALL onu LOW olarak sınıflasın.
3. WHERE bir talep yıkıcı/geri-alınamaz bir işlem içeriyorsa (ör. dosya/dizin silme, `rm -rf`, force push, prod'a dokunma) veya bir shell komutu (`is_shell`) ise THE sistem SHALL onu en az HIGH olarak sınıflasın.
4. WHERE bir talep bir kimlik bilgisi/secret'ı açığa çıkarıyor gibi görünüyorsa (ör. bir anahtarı log'a yazma) THE sistem SHALL onu HIGH olarak sınıflasın.
5. IF sistem bir talebin riskini güvenle belirleyemiyorsa THEN sistem SHALL onu UNKNOWN olarak sınıflasın (asla varsayılan olarak LOW kabul etmesin).
6. WHEN risk sınıflandırma için ham diff/tool verisi özetlenir THEN sistem SHALL bir dil modeli (Amazon Bedrock) kullanarak sese uygun, karar verdirici bir özet üretsin.

## Requirement 3 — Filtreleme kararı (üç kova)

**User Story:** Bir geliştirici olarak, sınıflandırılan taleplerin risklerine göre
otomatik işlenmesini istiyorum ki sadece gerçek kararlar bana ulaşsın.

#### Acceptance Criteria
1. WHEN bir talep LOW olarak sınıflandığında AND kullanıcı bu oturumda bu tür işlere güven verdiğinde (veya varsayılan güven politikası izin verdiğinde) THEN sistem SHALL onu otomatik onaylasın (`action:"approved"`) ve kullanıcıyı rahatsız etmesin.
2. WHEN bir talep HIGH olarak sınıflandığında AND açıkça yıkıcı/tehlikeli ise THEN sistem SHALL onu kullanıcıya getirsin (asla sessizce onaylamasın); bir talebi sessizce engellemesi YALNIZCA açık bir deny-kuralına uyduğunda olur.
3. WHEN bir talep UNKNOWN olarak sınıflandığında THEN sistem SHALL onu HER ZAMAN kullanıcıya getirsin (muhafazakâr varsayılan).
4. WHEN sistem bir talebi sessizce işlediğinde (geçir veya engelle) THEN sistem SHALL bu kararı denetim kaydına (audit) yazsın.
5. IF hiçbir güven politikası veya sınıflandırma güvenle uygulanamıyorsa THEN sistem SHALL talebi kullanıcıya getirsin (fail-safe).

## Requirement 4 — Durum sorma (PULL / özet)  [UC-1, UC-10]

**User Story:** Bir geliştirici olarak, "Kiro ne durumda?" diye sorabilmek istiyorum
ki ekrana bakmadan sesli, öz bir durum özeti alayım.

#### Acceptance Criteria
1. WHEN kullanıcı durum sorduğunda THEN sistem SHALL Crew'in genel durumunu ve bekleyen onayları çekip sese uygun bir özet üretsin.
2. WHERE birden fazla görev/onay varsa THE özet SHALL kaç görev bittiğini, kaçının beklediğini ve kaçının hata verdiğini içersin (standup özeti).
3. WHEN Ambient Awareness bazı talepleri sessizce işlediyse THEN özet SHALL kaçının otomatik geçildiğini ve kaçının engellendiğini de belirtsin (ör. "19'unu geçtim, 3'ünü engelledim, 1'i seni bekliyor").
4. WHEN özet üretildiğinde THEN o SHALL ham log/diff değil, karar verdirici bir dille ifade edilsin (sese uygunluk).

## Requirement 5 — Onaylama (yüksek riskte çift-teyit)  [UC-2]

**User Story:** Bir geliştirici olarak, bana gelen bir onayı sesle onaylayabilmek
istiyorum, ve yıkıcı bir işlemse yanlış anlamadan korunmak istiyorum.

#### Acceptance Criteria
1. WHEN kullanıcıya bir onay talebi sunulduğunda THEN sistem SHALL o talebin ne yaptığını (özet + risk) sesli açıklasın.
2. WHERE talep HIGH risk (yıkıcı/geri-alınamaz) ise THE sistem SHALL onaylamadan önce niyeti yeniden doğrulasın (ör. "42 satır siliniyor, geri alınamaz, emin misin?") ve YALNIZCA net bir olumlu yanıtı ("evet", "onaylıyorum") kabul etsin.
3. WHEN kullanıcı bir talebi onayladığında THEN sistem SHALL Crew'e onayı iletsin (`POST /api/chat/slots/<slot>/approve` gövde `{"action":"approved","request_id":<id>}`).
4. IF onay iletimi başarısız olursa THEN sistem SHALL kullanıcıyı bilgilendirsin ve talebi çözülmemiş saysın (yanlışlıkla "onaylandı" dememeli).
5. WHERE ses tanıma güveni düşükse veya yanıt belirsizse THE sistem SHALL yıkıcı bir işlemi onaylamak yerine tekrar sorsun.

## Requirement 6 — Reddetme ve alt seçenekler  [UC-3]

**User Story:** Bir geliştirici olarak, "hayır" dediğimde ne olacağını kontrol
edebilmek istiyorum ki yanlış bir aksiyon oluşmasın.

#### Acceptance Criteria
1. WHEN kullanıcı bir talebi reddettiğinde THEN sistem SHALL önce işlemin yapılmadığına dair güvence versin ("yapmadım").
2. WHEN reddetme sonrası THEN sistem SHALL üç seçeneği sabit sırayla ve net fiillerle sunsun: ATLA / DURDUR / İPTAL.
3. WHERE kullanıcı ATLA seçtiğinde THE sistem SHALL o adımı reddedip görevin devamına izin versin (`action:"rejected"`).
4. WHERE kullanıcı DURDUR seçtiğinde THE sistem SHALL görevi duraklatsın ve yeni bir talimat gelene kadar ilerletmesin.
5. WHERE kullanıcı İPTAL seçtiğinde THE sistem SHALL yıkıcı olduğu için ek bir teyit istesin, sonra görevi tümüyle durdursun.
6. IF kullanıcı reddetme sonrası belirsiz yanıt verirse veya yanıt vermezse (timeout) THEN sistem SHALL en güvenli seçeneğe (DURDUR) düşsün.

## Requirement 7 — Proaktif bildirim (meslektaş seni arar)  [UC-5]

**User Story:** Bir geliştirici olarak, ekrandan uzaktayken KiroWhisper'ın gerçek
bir karar gerektiğinde bana kendiliğinden seslenmesini istiyorum ki sürekli sormak
zorunda kalmayayım.

#### Acceptance Criteria
1. WHEN Ambient Awareness filtresinden kullanıcıya getirilmesi gereken bir talep geçtiğinde THEN sistem SHALL kullanıcıya proaktif bir sesli/işitsel uyarı üretsin.
2. WHEN proaktif uyarı tetiklendiğinde THEN o SHALL yalnızca gerçek karar gerektiren talepler için olsun (LOW/sessiz işlenenler için uyarı üretilmez).
3. WHERE gerçek Alexa+ proaktif ses native olarak mümkün olmadığında THE sistem SHALL bunu simülasyon/sahneleme ile gerçekleştirsin ve demoda bu durumu dürüstçe belirtsin (yanıltıcı sunum yapmasın).
4. WHEN bir görev başarısız olduğunda THEN sistem SHALL bunu (kullanıcı bir sonraki sorduğunda veya proaktif olarak) bildirsin.

## Requirement 8 — Oturum güveni ("artık hep onayla")  [UC-6]

**User Story:** Bir geliştirici olarak, güvendiğim bir görev için tekrar tekrar
sorulmak istemem; kalan düşük riskli adımların otomatik onaylanmasını isteyebilmeliyim.

#### Acceptance Criteria
1. WHEN kullanıcı bir oturum/görev için güven verdiğinde THEN sistem SHALL o kapsamdaki kalan LOW riskli adımları otomatik onaylasın (`action:"trust"`).
2. WHERE bir adım HIGH veya UNKNOWN risk taşıyorsa THE sistem SHALL oturum güvenine rağmen onu yine de kullanıcıya getirsin (güven, güvenliği geçersiz kılmaz).
3. WHEN oturum güveni etkinleştirildiğinde THEN sistem SHALL bunu kullanıcıya açıkça bildirsin ve neyi kapsadığını belirtsin.

## Requirement 9 — Bağlam takibi  [UC-7, UC-9]

**User Story:** Bir geliştirici olarak, birden fazla görev varken hangisinden
bahsettiğimi sistemin takip etmesini istiyorum ve gerektiğinde bana açık uçlu soru
sorabilmesini isterim.

#### Acceptance Criteria
1. WHERE birden fazla aktif görev/onay varsa THE sistem SHALL kullanıcının atıflarını ("hata vereni aç", "ikincisini onayla") doğru göreve eşlesin.
2. WHEN Crew açık uçlu bir seçim beklediğinde (`waiting_for_input`/`has_options`) THEN sistem SHALL seçenekleri sesli sunup kullanıcının seçimini iletsin.
3. WHEN oturum boyunca kararlar verildiğinde THEN sistem SHALL yakın bağlamı (son bahsedilen görev vb.) koruyarak takip soruları desteklesin.

## Requirement 10 — Denetim kaydı (audit)  [UC-11]

**User Story:** Bir sistem sahibi olarak, tüm onay/red/filtre kararlarının
kaydedilmesini istiyorum ki güvenlik ve sorumluluk sağlanabilsin.

#### Acceptance Criteria
1. WHEN sistem bir karar verdiğinde (onayla/reddet/otomatik-geçir/otomatik-engelle) THEN o SHALL zaman damgası, talep kimliği, risk sınıfı ve karar ile kaydedilsin.
2. WHEN kullanıcı isterse THEN sistem SHALL geçmiş kararların özetini sesli sunabilsin (ör. "bugün 3 tehlikeli işlemi engelledim").
3. WHEN yıkıcı bir işlem onaylandığında/reddedildiğinde THEN kayıt SHALL bu kararı kalıcı olarak tutsun.

## Requirement 11 — Ses arayüzü ve simülasyon  [UC genel]

**User Story:** Bir geliştirici olarak, sistemle kendi sesimle konuşabilmek istiyorum
ve gerçek Alexa+ deploy'a erişim olmadan da bunun çalışmasını isterim.

#### Acceptance Criteria
1. WHEN kullanıcı sesle komut verdiğinde THEN sistem SHALL konuşmayı metne çevirsin (STT) ve yanıtı sesle üretsin (düşük gecikmeli TTS).
2. WHERE gerçek Alexa+ MCP add-on erişimi yoksa THE sistem SHALL kurallara uygun bir simüle edilmiş Alexa+ deneyimi sunsun; arka uç (MCP + Crew + Bedrock) tamamen gerçek olsun, yalnızca Alexa+ etkileşim katmanı simüle edilsin.
3. WHEN sistem bir onay/özet ürettiğinde THEN yanıt SHALL sese uygun kısalıkta ve netlikte olsun (ekran metni değil).
4. WHERE demo sunulurken THE simülasyon dürüstçe belirtilsin (gerçek Alexa+'a bağlı gibi yanıltıcı sunum yapılmaz).

## Requirement 12 — MCP server paketlemesi

**User Story:** Bir hackathon katılımcısı olarak, KiroWhisper'ın çekirdeğinin
gerçek bir MCP server olarak paketlenmesini istiyorum ki Alexa+ track'inin runtime
teknoloji şartını karşılasın.

#### Acceptance Criteria
1. WHEN KiroWhisper çekirdek yetenekleri sunulduğunda THEN bunlar SHALL bir MCP server olarak (spec 2025-11-25, Streamable HTTP) tool'lar biçiminde açığa çıkarılsın (ör. get_status, get_pending_decisions, approve, reject, summarize).
2. WHEN MCP server bir tool çağrısı aldığında THEN o SHALL ilgili Crew Gateway REST çağrısını yapıp sonucu MCP yanıtı olarak dönsün — yani MCP teknolojisi runtime'da gerçekten çağrılsın (yalnızca README'de anılmasın).
3. WHERE kod deposu sunulduğunda THE MCP server kaynağı ve çalıştırma talimatları dahil olsun.

---

## Non-Functional Requirements

### NFR-1 — Güvenlik (fail-safe)
- Emin olunamayan hiçbir talep sessizce onaylanmaz (muhafazakâr varsayılan).
- Yıkıcı işlemler yalnızca açık kullanıcı onayı veya açık deny-kuralıyla işlenir.
- Sesli komutlarda gizli değerler (secret/token) yanıtlarda tekrarlanmaz.

### NFR-2 — Gecikme (demo akıcılığı)
- Onay yanıtından sonra sesli geri bildirim düşük gecikmeli olmalı; onay akışını
  bozacak uzun sessizlikler olmamalı (TTS hızı > cila).

### NFR-3 — Sese uygunluk
- Tüm çıktı işitsel tüketime uygun: kısa, öncelik sıralı, ham diff/log değil.
- Aynı anda en fazla 2-3 seçenek sesli sunulur (kulak sınırı).

### NFR-4 — Erişilebilirlik
- Gözler-serbest tam işlevsellik: hiçbir kritik akış ekran görmeye bağlı olmamalı.
- Tutarlılık: seçenekler hep aynı sıra/kelimelerle (öğrenilebilirlik).

### NFR-5 — Kurallara uygunluk (hackathon)
- Repo public + açık kaynak lisans (görünür LICENSE).
- <3 dk demo videosu; simülasyon dürüstçe etiketli.
- Her tool/SDK için Product Feedback; Friction Log tutulur (bonus).

---

## Öncelik (kapsam)
- **ÇEKİRDEK:** R1, R2, R3 (Ambient Awareness) + R4, R5, R6, R7, R11, R12 + NFR-1..5
- **FARKLILAŞTIRICI:** R8, R9, R10
- **GELECEK (v2):** mid-task redirect (UC-8), sesle yeni görev başlatma

## İzlenebilirlik (use case → requirement)
- Ambient Awareness → R1, R2, R3
- UC-1/UC-10 → R4 | UC-2 → R5 | UC-3 → R6 | UC-4/UC-12 → R4/R7
- UC-5 → R7 | UC-6 → R8 | UC-7/UC-9 → R9 | UC-11 → R10
- Tüm UC → R11 (ses), R12 (MCP paketleme)
