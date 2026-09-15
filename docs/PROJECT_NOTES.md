# KiroWhisper — Proje Notları (Şu ana kadar konuştuklarımız)

> Bu doküman, Kiro Web'de yaptığımız beyin fırtınasının özetidir. Amaç: evde
> Kiro IDE'den açıp kaldığımız yerden devam edebilmek.

---

## 🎯 Proje Özeti

**İsim:** KiroWhisper (şimdilik — değiştirebiliriz)

**Ne:** Amazon "Build, Ship, Shape" Hackathon'unun **Alexa+ track**'i için bir
**MCP server**. Bir **Echo Dot 5** üzerinden **Alexa+**'a bağlanıp, arka planda
otonom çalışan **Kiro Crew**'i sesle denetlemeyi sağlayan bir "sesli komuta
merkezi".

**Track:** Alexa+ (ana) + **AWS Builder** mini-challenge (Kiro Crew kullanımı
sayesinde otomatik uygun — ekstra ödül potansiyeli).

---

## 👥 Hedef Kitle (Karar: Seçenek A — accessibility-first, ama herkese fayda)

- **Ana kitle / kalp:** Görme engelli geliştiriciler. Ekran okuyucuyla uzun
  agent çıktılarını, diff'leri, onay dialoglarını tek tek gezmek çok yorucu.
  Sesle özet + onay çok daha akıcı.
- **Genişleme / bonus:** Ekrandan uzaktaki herkes (kahvaltı masası, mutfak,
  eller/gözler meşgul). "Curb-cut effect": erişilebilirlik için tasarla,
  herkes faydalansın.

**Demo kurgusu (3 dk):**
- İlk ~2 dk: Görme engelli geliştirici hikayesi (gözler kapalı, sadece sesle
  Crew'i yönetiyor) — duygusal, ana mesaj.
- Son ~30 sn: "Bu sadece görme engelliler için değil — ekrandan uzaktaki
  herkes için" (curb-cut mesajı).

**Altın demo anı (kahvaltı senaryosu):**
> Kahvaltı masasındasın. Crew gece boyu çalışmış. "Alexa, Kiro ne durumda?"
> dersin → Echo özet geçer: "3 task bitti, biri onayını bekliyor." → "Alexa,
> onayla" → Crew devam eder → biter → "Task tamamlandı." Ekrana hiç bakmadan.

---

## 🧩 Ne Yapar (3 Çekirdek Yetenek)

1. **🗣️ Durum sor** — "Kiro ne durumda?" → Echo sesli özet: kaç task bitti,
   hangisi bekliyor, hangisi hata verdi.
2. **✅ Sesli onay** — "Alexa, onayla" / "reddet" → Crew'in beklediği onayı
   ver, task devam etsin (veya dursun).
3. **🔔 Sonuç dinle** — "Task bitti, 3 dosya değişti, testler geçti" gibi
   sonucu sesle al.

---

## 🏗️ Mimari

```
Echo Dot 5  →  Alexa+  →  [KiroWhisper MCP server]  →  Kiro Crew Gateway
   (ses)      (agent)      (Streamable HTTP)            (REST + WebSocket,
                                                         localhost:5476)
```

- MCP server = **köprü**. Bir tarafta Alexa+ ile MCP konuşur, diğer tarafta
  Crew Gateway'in API'sini çağırır.
- **MCP spec:** 2025-11-25, **Streamable HTTP** üzerinden (Alexa+ zorunluluğu).

### Neden IDE değil de Crew?
- Kiro **IDE** interaktiftir; sen kapatınca durur, dışarıdan kontrol edilecek
  genel bir API'si **yok**.
- Kiro **Crew** arka planda 7/24 otonom çalışır ve **Gateway API'si** ile
  dışarıdan kontrol edilebilir (task başlat / durum sor / onayla).
- **"Kiro Cloud" diye bir ürün yok.** Benzer isimli **"Cloud sessions"** var
  ama o sadece IDE/CLI/Web/Mobile arasında oturum paylaşır — **Crew'i
  kapsamaz** ve IDE↔Crew arası canlı köprü sağlamaz. Tek ortak nokta `.kiro/`
  proje ayarları (dosya paylaşımı, canlı kontrol değil).

### Crew'in doğruladığımız programatik yetenekleri (bize lazım olanlar)
- **Task başlat:** `task_run` (MCP tool), `dispatch_agent(_async)`, CLI
  `kirocrew run TASK.md`.
- **Durum sor:** `get_task_result(task_id)`; WebSocket event'leri:
  `task_update`, `task_complete`, `notification`.
- **Onay:** `approve_action` / `reject_action`, `resolve_approval(id, ok)`;
  WebSocket `approval` event'i input gerektiğinde tetiklenir; Task Runner
  pause/resume; `force_approval` gate'leri (tehlikeli işler için).
- **Erişim:** Gateway REST + WebSocket (`localhost:5476`), Python client
  (`pip install kirocrew-client`), CLI, Slack/Discord vb.

---

## 🔍 KiroCan Bağlantısı (senin portföyünle uyum)

- **KiroCan** (2. lik): fiziksel donanımı (MX Console) Kiro IDE'ye bağlayıp
  IDE durumunu telemetriyle yansıtıyordu — ama **interaktif** (sen başındaydın).
- **KiroWhisper** = aynı fikrin **otonom + uzaktan + sesli** versiyonu: sen
  IDE'nin başında DEĞİLKEN (kahvaltıda), Crew arka planda çalışırken sesle
  denetim. Crew'in `task_complete` / `approval` event'leri = o telemetrinin
  ses versiyonu.
- Marka bağı: 1. olan projen **Whisper**, bu da **KiroWhisper**.

---

## 💎 Eklenebilecek "Derinlik Katmanları" (senin çıtana yakışması için — TARTIŞILACAK)

1. **Sesli özet zekası:** Crew'in ham çıktısını (uzun diff/log) kısa, sesle
   dinlenebilir anlamlı özete indirgeyen katman. (Aslında zor bir problem.)
2. **Güvenli sesli onay:** Sesle "sil" tehlikeli — niyet doğrulama / onay
   güvenlik katmanı (Whisper'daki güvenlik hassasiyetin gibi).
3. **Bağlam farkındalığı:** Birden fazla task varken Echo hangi task'tan
   bahsettiğini takip etsin (state across sessions).

---

## ❓ Bekleyen Kararlar (evde devam ederken bunları netleştirelim)

1. **Crew: gerçek mi, simülasyon mu başlayalım?**
   - (a) Gerçek Kiro Crew kur (öğrenme yükü var, ama AWS Builder mini-challenge
     için de sayılır).
   - (b) Crew Gateway'i taklit eden **mock/simülasyon** server yaz (hızlı
     prototip; Alexa+ track simülasyona izin veriyor).
   - Öneri: **(b) ile başla, çalışınca (a)'ya geç.**
2. **Bildirim yönü:**
   - "Sen sor" modeli ("Alexa, Kiro ne durumda?") → **garantili çalışır**.
   - Proactive (Echo kendi kendine haber verir) → daha zor/riskli.
   - Öneri: **"sen sor" ile başla** (kahvaltı senaryosuna da uyuyor).
3. **Requirement doküman formatı:** basit `REQUIREMENTS.md` mi, yoksa
   user story + acceptance criteria'lı yapılandırılmış spec mi?

---

## ✅ Şu Ana Kadar Yapılanlar (repo durumu)

- `memetcircus/kirowhisper` reposu klonlandı (şu an **private**).
- `docs/rules.txt` eklendi (hackathon resmi kuralları) — PR #1 merge edildi.
- `docs/PROJECT_NOTES.md` (bu dosya) eklendi.
- **Henüz kod YAZILMADI.** (Yerel `/kirowhisper` klasöründe eski bir MCP
  iskeleti taslağı var ama repoya push edilmedi ve fikir değiştiği için
  yeniden ele alınacak.)

## ⚠️ Hackathon Zorunlulukları (unutmayalım)
- Repo **public** + **open source** (görünür LICENSE dosyası) olmalı. Şu an
  private → düzeltilecek.
- Alexa+ için: kodda MCP teknolojisinin **runtime'da gerçekten çağrıldığı**
  gösterilmeli (sadece README'de bahsetmek yetmez).
- 3 dk'dan kısa demo videosu (YouTube/Vimeo), Echo/Alexa+ simülatöründe
  çalıştığını göstermeli.
- Her tool/SDK için **Product Feedback**.
- (Opsiyonel ama +%10 bonus) **Friction Log** girişleri.

---

## ▶️ Sıradaki Adım
Yukarıdaki 3 bekleyen kararı ver → **requirement dokümanını yaz** → mimariyi
kur → MCP server + Crew köprüsünü (önce mock) yaz.

---
---

# 📌 GÜNCELLEME — Fizibilite Araştırması + UX Kararları (Kiro IDE, evde)

> Bu bölüm, evde Kiro IDE'de yaptığımız araştırma ve UX tasarımı oturumunun
> sonuçlarıdır. Yukarıdaki ilk notlar (Kiro Web brainstorm) hâlâ geçerli ama
> **bazı teknik varsayımlar burada DÜZELTİLDİ.** Çelişki olursa bu bölüm önceliklidir.

## ✅ Fizibilite: Doğrulananlar (kaynaklarıyla)

### Alexa+ MCP tarafı — GERÇEK ve mimarimizle uyumlu
Kaynak: Amazon resmi docs (developer.amazon.com/docs/alexaplus/add-ons/)
- Alexa+ **MCP client** rolünde; biz **MCP server** yazıyoruz. Alexa+ natural
  language understanding + response generation + UI rendering'i kendisi yapıyor.
- **MCP spec 2025-11-25**, **Streamable HTTP** zorunlu (eski HTTP+SSE deprecated).
- MCP server **remote URL** ile erişilebilir olmalı; local geliştirmede
  `cloudflared` gibi bir tünel öneriliyor.
- Deploy: **Alexa AI CLI** (`alexa-ai`) ile bir "MCP add-on" oluşturuluyor; bu
  add-on = Alexa+ ile bizim MCP server arasında köprü (tool discovery + protocol
  translation). Değişiklikte `alexa-ai deploy` ile yeniden deploy.
- **BONUS:** Alexa+ **MCP Apps** uzantısını destekliyor → konuşma içinde
  interaktif görsel UI (kart, dashboard, çok adımlı akış) render edilebiliyor.
  Kurallar bunu tam da "creative" örnek sayıyor. Bizde opsiyonel cila.

### Kiro Crew tarafı — GERÇEK
Kaynak: github.com/kirodotdev/KiroCrew (Apache-2.0, ~3.8k yıldız, Python)
+ kiro.dev/docs/crew
- Crew = arka planda otonom çalışan, kalıcı, kendini geliştiren agent. Task
  Runner markdown spec alıp adımlara böler, her adımı ayrı session'da çalıştırır,
  test eder, hata olunca retry eder — 10+ saat gözetimsiz çalışacak şekilde.
- Gateway `localhost:5476`, app-token auth (per-app `.app_secret` → token
  exchange), REST + WebSocket, resmi Python client `kirocrew-client-py` (aiohttp).

## ⚠️ DÜZELTME: Crew client'ın GERÇEK API yüzeyi (notlardaki isimler yanlıştı)

Kaynak: `packages/kirocrew-client-py/kirocrew_client/client.py`

İlk notlarda geçen `task_run`, `approve_action`, `reject_action`,
`resolve_approval(id, ok)`, task `pause`/`resume` **client'ta YOK** (uydurma çıktı).
Gerçek public metodlar:
- **Task başlat:** `spawn(task, agent="")` → task_id  |  `spawn_many(...)`  |
  `dispatch_agent(agent, prompt)` / `dispatch_agent_async(...)`
- **Durum/sonuç:** `get_task_result(task_id)`, `get_status()`, `get_system_info()`,
  `list_subagents()`, `get_subagent_status(agent_id)`, `ping()`
- **Sohbet:** `create_slot(name)`, `send_message(slot_id, message)`, `list_slots()`
- **Bildirim:** `send_notification(text, **opts)`  ← proaktif ses için aday
- **MCP:** `register_mcp_server(...)`, `list_mcp_servers()`, `remove_mcp_server(name)`
- **Diğer:** cron (`add/pause/resume_cron`), lessons (öğrenme), `memory_search`,
  context injection.

> NOT: `pause_cron`/`resume_cron` cron job'ları içindir, task approval için DEĞİL.

## ⭐ DÜZELTME: Onay (approval) mekanizmasının GERÇEK şekli

Kaynak: `.kiro/specs/tool-approval-layer/requirements.md` +
`src/kiro_crew/messaging/approval.py`, `teams/approvals.py`

Bu bizim için KRİTİK ve İYİ haber — tasarladığımız güvenli onay Crew'de zaten var:
- Crew **her tool call'ı çalışmadan ÖNCE** yakalıyor: backend
  `HookManager.on_tool_call` gate → `TOOL_DENY` / `TOOL_AUTO_APPROVE` /
  `TOOL_ALLOW` (insan kararı gerekli).
- `TOOL_ALLOW` olunca turn **duraklıyor**, bir **ApprovalCard** (tool + purpose/
  title + input) render ediliyor. Operatör onaylıyor/reddediyor. Karar
  `approveChatSlot(slot, action, extra)` yoluyla geri akıp duraklamış turn'ü
  **resume** ediyor.
- **Reddet:** tool çalışmaz, agent turn "rejection recorded" ile devam eder.
- **Güvenlik:** enforcement authority `on_tool_call` gate'te; frontend override
  edemez; SEL audit trail her deny'ı kaydeder. (Whisper markamızla birebir örtüşür.)

**Anlamı:** KiroWhisper = bu mevcut approval checkpoint'inin **sesli + proaktif
yüzeyi.** Slack'in `approveChatSlot` üzerinden yaptığını biz sesle yapıyoruz.
"MCP wrapper değil, gerçek agentic katman" iddiamız repo kanıtıyla destekleniyor.

## 🎯 Kesinleşen UX Kararları

1. **Proaktif model (Echo kendi seslenir):** İstenen deneyim bu. ANCAK MCP
   request-response doğası gereği server kendiliğinden konuşamaz. Plan:
   - Çekirdek (gerçek): kullanıcı sorar → Echo cevaplar (garantili). Crew takılınca
     `send_notification` ile bir uyarı tetiklenir (ışık/kısa ton), sonra kullanıcı sorar.
   - Demo büyüsü: "müzik kısılır, Alexa kendi konuşur" bir Alexa Routine +
     zamanlama ile SAHNELENİR. Kurallar simülasyona izin veriyor; friction log'a
     "proaktif ses MCP ile native değil, şu workaround" diye yazılacak (+puan).
2. **Akıllı özet (Bedrock):** Ham diff/log değil, karar verdirecek kadarını sese
   uygun özetle. Girdi hazır: ApprovalCard zaten tool+purpose+input veriyor.
   → AWS Builder mini-challenge buradan doğal doğuyor.
3. **Güvenli onay:** Yıkıcı/geri-alınamaz aksiyonda **çift-kademeli** teyit
   (risk söylenir + sadece net "evet" kabul). Düşük riskte tek onay.
4. **Reddetme akışı:** "Hayır" tek anlama gelmez. Echo önce güven verir
   ("silmedim"), sonra **3 alt seçenek sesli sunar: ATLA / DURDUR / İPTAL**
   (hep aynı sıra/kelime). Güvenli varsayılan + timeout = **DURDUR**. "İptal"
   ayrıca teyit ister. Crew native modeli ikili (approve / reject-and-continue)
   olduğu için 3'lüyü bu ikiliye map'leyeceğiz — **projenin zekası burada.**
5. **Gözler-serbest:** Echo Dot Max ekransız (LED ışık halkası var). Ana deneyim
   %100 ses + ışık. Görsel (MCP Apps) sadece ekranlı cihaz/Alexa+ telefon app'inde
   opsiyonel bonus. Curb-cut hikayesiyle örtüşüyor.

**Persona:** Deniz — görme engelli + home-office, masada durmayan geliştirici.
Altın demo anı: kahvaltıda, gözler kapalı, Crew gece çalışmış, bir onay bekliyor.

## 🖥️ Alexa+ Geliştirme Ortamı — Ön Koşullar (checklist)

Kaynak: developer.amazon.com/docs/alexaplus/add-ons/set-up-your-development-environment.html
- [ ] macOS (var) — Node.js **24+** (kontrol: `node --version`)
- [ ] Alexa developer account (ücretsiz): profil + telefon + adres tamam,
      preferred marketplace **Alexa+ destekli** (US), cihaz dili Alexa+ locale.
- [ ] AWS account (free tier).
- [ ] AWS IAM user (programatik) + `sts:AssumeRole` inline policy
      (`arn:aws:iam::372468808636:role/AddOn3PDeveloperToolsRead`).
- [ ] İki AWS profili: `alexa-ai-user` (base) + `alexa-ai` (role assumption).
      Doğrula: `aws sts get-caller-identity --profile alexa-ai`.
- [ ] Git CodeCommit credential helper (template klonu için).
- [ ] npm → private CodeArtifact registry (`@alexa-ai/*`) login.
- [ ] `npm install -g @alexa-ai/cli` → `alexa-ai --version` → `alexa-ai configure`
      (LWA OAuth; creds `~/.alexa-ai/credentials`).
- [ ] (Sadece Category Action için) AWS CDK — bizim MCP yolunda muhtemelen gerekmez.

## 📦 Donanım / Hesap Durumu (GÜNCEL — kullanıcı teyidi)
- ✅ **Amazon Echo Dot Max satın alındı, yolda.** (voice-only, ekransız — hikayeye uygun.)
- ✅ **US Amazon hesabı alındı; telefonda Amazon Alexa app'te Alexa+ ÇALIŞIYOR.**
  → En büyük belirsizliklerden biri (Alexa+ erişimi + destekli marketplace/locale)
  büyük ölçüde KAPANDI. Gerçek Alexa+ deneyimi elimizde.
- ⚠️ Hâlâ doğrulanacak: `AddOn3PDeveloperToolsRead` rolüne / private CodeArtifact
  registry'sine developer erişimi (whitelisting gerekebilir). Bu, gerçek
  `alexa-ai deploy` mümkün mü sorusudur. Sigorta: kurallardaki **"simulated
  Alexa+ experience"** yolu (gerçek deploy bloke olursa track'e yine uygunuz).

## 🔬 Kalan İki Bağımsız Spike (kod öncesi)
1. **Crew spike:** Crew'i local kur → `spawn()` ile bir task başlat → yıkıcı bir
   tool call ile approval tetikle → **sesli 'onayla' kararını duraklamış turn'e
   nasıl geri iletiriz?** (`approveChatSlot` client SDK'da doğrudan expose DEĞİL;
   REST endpoint'i mi çağıracağız, mesaj kanalı gibi mi ele alacağız?) ← tek kalan
   gerçek teknik risk.
2. **Alexa+ spike:** developer account + `alexa-ai` CLI kurulumu → basit bir MCP
   add-on deploy edilebiliyor mu? (private registry erişimini test eder.)

## ▶️ Sıradaki Adım (güncel)
İki spike'ı yukarıdaki checklist'lerle yap → sonuçlara göre requirement dokümanı
(user story + acceptance criteria) → mimari → MCP server + Crew köprüsü (önce dar
ama gerçek bir task tipiyle uçtan uca).

---
---

# 🚨 KESİN NETLEŞME — Alexa+ Erişimi (Discord'dan resmi cevap)

> Kaynak: Hackathon Discord'u. İki resmi ağızdan cevap: biri Amazon tarafı,
> biri Devpost (Janet). Bu, önceki tüm "deploy erişimi gated mı?" belirsizliğini
> KAPATIYOR ve stratejiyi sadeleştiriyor. Çelişkide bu bölüm önceliklidir.

## Ne öğrendik
- **Alexa+ MCP toolkit / Alexa Add-ons HENÜZ GENEL KULLANIMA AÇIK DEĞİL** ("not
  generally available yet"). Hackathon'un Alexa kategorisi, bunlara HAZIRLIK
  olarak, **açık kaynak standartlara dayalı bir MCP** inşa etmeye odaklı.
- **Özel partner erişimi GEREKMİYOR.** Devpost 3 kabul edilebilir yol saydı:
  1. Çalışan bir **Agent Skill**, veya
  2. **Self-hosted MCP server** (spec **2025-11-25+**), açık `modelcontextprotocol.io`
     dokümanlarıyla, veya
  3. Kendi agentic araçlarınla **simüle edilmiş Alexa+ deneyimi**.
- `developer.amazon.com`'daki "Select Partners Only" sayfaları (Alexa AI CLI,
  private CodeArtifact/CodeCommit, `AddOn3PDeveloperToolsRead` rolü) bizim için
  GEREKLİ DEĞİL ve zaten erişilemez olabilir.

## Bunun proje için anlamı (LEHİMİZE — risk büyük düştü)
- Değer eksenimiz zaten Alexa+'ın kendisinde değildi; **self-hosted MCP + Crew
  köprüsü + Bedrock özet + güvenli onay**taydı. Bu yol #2'ye BİREBİR uyuyor.
- **KiroWhisper'ın hiçbir parçası artık gated bir Amazon altyapısına bağlı değil.**
  Tüm proje kendi makinede, açık standartlarla, uçtan uca GERÇEK çalışabilir.
- Alexa+ tarafı = MCP **client** olarak SİMÜLE edilecek (yol #3, kurallara uygun).

## ❌ İPTAL EDİLEN İŞLER (bunlara vakit harcama)
- `alexa-ai` CLI kurulumu, private CodeArtifact/CodeCommit login, IAM role
  assumption (`AddOn3PDeveloperToolsRead`) — hepsi İPTAL. Beklenen yol bu değil,
  hatta erişilemez.
- **Alexa+ spike İPTAL.** Artık tek kalan spike = **Crew spike**.

## 🔊 Echo Dot Max'in YENİ rolü (boşa alınmadı)
- Deploy HEDEFİ değil (gerçek Alexa+ MCP deploy henüz kimseye açık değil).
- AMA hâlâ değerli:
  1. **Demo videosu inandırıcılığı:** gerçek cihazın ışık halkası + sesi,
     ekranda log akıtmaktan kat kat güçlü. Jüri Design/Impact/Idea'yı videodan
     okuyor. Rakipler simülasyonu ekranda gösterecek; biz fiziksel cihazda.
  2. **UX'i gerçek cihazda test etmek:** sesli deneyim ekranda hayal edilerek
     tasarlanamaz; cümle uzunluğu/onay hızı ancak cihazda hissedilir.
  3. **Alexa Routines ile proaktif sahneleme** ("müzik kısılır, Alexa konuşur").
- Ayrıca "not generally available **yet**" → ileride toolkit açılırsa cihaz
  gerçek deploy hedefine döner. Erken alınmış, geç değil.

## ✅ Güncel Strateji Özeti
| Bileşen | Karar |
|---|---|
| MCP server | Self-hosted, GERÇEK (spec 2025-11-25, Streamable HTTP) |
| Alexa+ bağlantısı | SİMÜLE (kendi agentic aracımızla; kurallara uygun) |
| Kiro Crew entegrasyonu | GERÇEK (Crew spike'ı ile doğrulanacak) |
| Bedrock akıllı özet | GERÇEK (AWS Builder mini-challenge) |
| Echo Dot Max | Demo sahnesi + UX testi (deploy hedefi değil) |
| Kalan spike | Sadece 1: Crew (sesli onayı çalışan turn'e geri iletme) |

---
---

# 🎬 Demo & Ses Mimarisi (netleşti)

> Simülasyonun ne demek olduğu ve sesin nereden geldiği burada sabitlendi.
> Çelişkide bu bölüm önceliklidir.

## "Simülasyon" ne demek (Dot Max'e gerçek bağlanamıyoruz)
- Alexa+ MCP toolkit kimseye açık olmadığı için **Echo Dot Max'e KiroWhisper'ı
  gerçekten bağlayıp konuşturamayız.** Bu kapı herkese kapalı.
- Simülasyon = **Alexa+'ın yerine kendi ses arayüzümüzü koymak.** Konuşma yine
  olur, ama muhatap Echo değil, bizim kurduğumuz katman. Kurallar buna açıkça
  izin veriyor ("simulated Alexa+ experience with your own agentic tools").
- **Beyin her zaman GERÇEK:** MCP server + Crew köprüsü + Bedrock özet + güvenli
  onay. Sadece iki uçtaki "ses" simüle ediliyor.

## Canlı ürün akışı (demoda gerçekten çalışır)
```
Senin sesin (mikrofon)
  → speech-to-text
  → MCP server + Crew köprüsü + Bedrock akıllı özet   ← projenin KALBİ, gerçek
  → text-to-speech (DÜŞÜK GECİKMELİ, canlı)            ← sistemin cevap sesi
  → hoparlör / Echo Dot Max (sahne)
```

## Ses kararları (KESİN)
- **Girdi sesi = kullanıcının (senin) canlı sesin.** Ürün komutları böyle verilir.
- **Video anlatımı (voice-over) = yine tamamen SENİN sesin.** ElevenLabs YOK.
  Gerekçe: baştan sona gerçek insan sesi → "önceden kaydedilmiş tiyatro mu?"
  şüphesini sıfırlar, accessibility ruhuna uyar, tutarlı ve zahmetsiz.
- **Sistemin cevap sesi = düşük gecikmeli, gerçek-zamanlı bir TTS.** (Sistemin
  "ağzı" — ayrı bir bileşen; sistem sana cevap vermek zorunda.) Cilalı ama yavaş
  bir ses (ör. cloud TTS) sesli-onay akışında latency ile demoyu öldürür; hız
  gerçeklikten önce gelir. Gerçeklik için cevabın metni ekranda anlık belirebilir.
- **ElevenLabs kullanılmıyor** → stack sadeleşti, bir bağımlılık/friction eksildi.

## Echo Dot Max'in demo rolü (tekrar)
- (a) **Dürüst sahne dekoru:** videoda cihaz masada, ışık halkası yanar, sen
  konuşursun; cevabı arka planda simülasyon katmanı üretir. Videoda "Alexa+
  simulated; real MCP+Crew backend" diye DÜRÜSTÇE belirtilir (yalan = jüri cezası).
- (b) **Gerçek Alexa Routines ile proaktif sahneleme:** "müzik kısılır + Echo
  anons/uyarı verir" gibi anlar gerçek cihaz davranışıyla tetiklenebilir; arkasındaki
  "task 3 onay bekliyor" zekası bizden gelir.

## Not: STT ayrı bir bileşen
"Gerçekten sesle çalışıyor" iddiasının teknik ayağı speech-to-text. Simülasyon
katmanına dahil edilecek; hangi STT (local/cloud) kullanılacağı ileride kararlaştırılacak.

---
---

# 🌉 Kay'in Bridge Bulgusu — Alexa+ taşıma problemi çözülmüş olabilir

> Kaynak: Discord (Kay) + repo incelemesi. Repo SADECE OKUNDU, hiçbir şey
> kurulmadı/çalıştırılmadı. Kurulum öncesi mutlaka kullanıcı onayı alınacak
> (AWS credential + deploy söz konusu).

## Ne bulundu
- **github.com/KayLerch/alexa-skill-mcp-bridge** — Apache-2.0, TypeScript.
- Alexa+ MCP add-on toolkit invite-only olduğu için, Kay **sıradan bir Alexa
  Skill'i** add-on'un yerine koyuyor. Skill senin MCP server'ını sarmalıyor;
  arkasında **Bedrock AgentCore Runtime** üstünde **Strands + Nova 2 Lite** ile
  bir agent, Alexa+ orchestrator'ı TAKLİT ediyor: tool seçer, argüman doldurur,
  elicitation'ı yönetir, sonucu kısa sözlü cevaba çevirir, turlar arası bağlamı taşır.
- **Mimari:** Alexa+ device ↔ Alexa Skill (ince Lambda, SSML) ↔ Bedrock agent
  (MCP client, Streamable HTTP, spec 2025-11-25) ↔ senin MCP server'ın.
- **Kademeli kullanım:**
  - Track A (local): AWS deploy YOK, sadece Bedrock model erişimi. `npm run chat`
    ile terminalde gerçek agent üzerinden MCP server'ınla konuşuyorsun. Örnek
    server dahil. `--record` ile söylediklerin kaydedilip interaction model'e ekleniyor.
  - Track B (cloud): AgentCore Runtime + CDK + Docker + (localhost için) cloudflared.
  - Track C (skill): gerçek Alexa Skill, ASK CLI, tarayıcı simülatörü VEYA gerçek cihaz.
- **Elicitation'ı çözmüş:** MCP "cevap aynı çağrıda gelmeli" ister, Alexa turu
  saniyeler içinde biter. Bridge açık çağrıyı microVM'de PARK edip sonraki turda
  resume ediyor. → **Bu tam bizim sesli-onay akışımızın ihtiyacı** ("onaylıyor
  musun?" bir elicitation'dır).

## Değerlendirme
- ✅ Gerçek, profesyonel: CI, testler (vitest), `npm run doctor` ön-koşul denetimi,
  docs/, pre-commit hook'lar (ARN/URL sızmasını engelliyor).
- ✅ Tam bizim en büyük engelimizi (Dot Max'e ulaşamama) çözüyor → gerçek Echo'da
  gerçek demo mümkün olabilir, simülasyona mecbur değiliz.
- ⚠️ ÇOK YENİ: 2026-09-05 oluşturulmuş, ~2 yıldız, 0 fork. Bizden başka ciddi
  test eden olmamış olabilir. "Çalışıyor" iddiası inandırıcı ama BİZ görmedik.
- ⚠️ AWS maliyeti/karmaşıklığı (Track B/C): AgentCore + CDK + Docker + Nova 2 Lite
  erişimi. Idle birkaç sent/ay deniyor.
- ⚠️ Üçüncü parti bağımlılık: repo bozulur/değişirse demomuz etkilenir.

## Kay bunu NEDEN yayınladı (rakibe silah değil)
1. Bu onun submission'ı DEĞİL, altyapı/enabler. Kendi başına bir "MCP deneyimi"
   sunmuyor, sadece herhangi bir MCP server'ı Alexa'ya bağlıyor.
2. Muhtemelen **Open Source mini-challenge** stratejisi (yeni açık kaynak proje +
   bir primary track submission). Yayılması/yıldızlanması ONA yarıyor.
3. Engel herkesi vuruyordu; kaldırmak onu geri götürmüyor, görünürlük + iyi niyet +
   Amazon radarı kazandırıyor.
4. Farklı kulvar: biz Alexa+ track'inde bir UYGULAMA ile yarışıyoruz; o enabler/OSS ile.

## ⭐ STRATEJİ: "Transport = Kay, Intelligence = biz"
- **Kay'in bridge'i = sadece TAŞIMA teli** (MCP server'ımızı gerçek Echo'da
  duyulabilir kılar). Herkes bunu kullanacak → bridge FARK DEĞİL, ortak zemin.
- **Bizim farkımız MCP server'ımızın İÇİNDE:** Kiro Crew entegrasyonu + güvenli
  onay niyet-ayrıştırma (atla/durdur/iptal) + accessibility UX + Crew çıktısını
  Bedrock ile akıllı özetleme.
- **KRİTİK sınır:** Bizim Bedrock katkımız (Crew'in ham diff/log'unu özetleme)
  **kendi MCP server'ımızın içinde** olur — Kay'in Nova agent'ında DEĞİL. Böylece
  AWS Builder katkımız net BİZİM olur, Kay'in orchestrator taklidiyle karışmaz.
- Kay'in Nova agent'ı bizim yerimize orchestration yapsın diye değil, sadece
  "sesi server'a taşısın" diye kullanılır.

## ⚠️ Dürüstlük / kurallar
- Kay'in bridge'ini kullanırsak kaynağını AÇIKÇA belirtmeliyiz (kurallar üçüncü
  parti kullanımında bunu istiyor). Jüri bridge'i tanıyabilir (Discord'da popüler).
- Alexa+ runtime-technology-hook kuralı: bizim submission'ımızın KENDİ MCP
  teknolojisini runtime'da gerçekten çağırdığını göstermeliyiz — bridge bu şartı
  bizim yerimize karşılamaz, kendi MCP server'ımız karşılar.

## Açık Tutulan Seçenek (şimdi DEĞİL)
- Demolar çok benzeşirse / daha çok farklılaşmak istersek: Kay'in FİKRİNDEN ilham
  alıp **kendi minimal bridge'imizi** yazıp onu da Open Source mini-challenge'a
  sunmak (ikinci ödül kapısı). Emek ister. Şimdilik Kay'inkiyle başla, gerekirse geç.

## Crew Spike'a Etkisi (ileride)
- Kay'in **Track A (local, `npm run chat`)** modu, Crew spike'ını hızlandırabilir:
  kendi MCP server'ımızı (Crew'e bağlı) yazıp AWS'ye hiçbir şey kurmadan sesli/
  yazılı test edebiliriz. (Sadece Bedrock model erişimi gerekiyor.)
- NOT: Crew spike'a HENÜZ GEÇİLMEDİ (kullanıcı talebi). Bu sadece ileriye not.

---
---

# 📺 Devpost/Amazon Canlı Oturum Transkripti — Çıkarımlar (jüri sinyalleri)

> Kaynak: Devpost "Build, Ship, Shape" bilgilendirme oturumu (Darliss/Devpost +
> Chris & Moses/Amazon Developer). Kuralların YAZMADIĞI, ekibin ağzından çıkan
> sinyaller. Stratejimizi doğruluyor + keskinleştiriyor.

## Bizim projeyi doğrudan etkileyen çıkarımlar
1. **Alexa+ track resmen "ideation / MCP prize".** Add-on toolkit canlı değil;
   "SDK ile Echo Show kontrol edilemez." Amazon iç hackathon'da "simüle Echo +
   web view mockup", "Build me a mockup of Alexa+" yaklaşımlarını TEŞVİK ediyor.
   → Bizim SİMÜLASYON kararımız Amazon'un ağzından onaylandı; beklenen yol bu.
   Kay'in bridge'i ile GERÇEK Echo'da göstermek bizi çoğunluğun önüne geçirir.
2. **"Rich cards + in-place purchase" = frontrunner sinyali.** Chris: product
   feedback'te "zengin kartlar / yerinde satın alma istiyorum" demek ödüle
   frontrunner yapar. → MCP Apps görsel katmanı artık "opsiyonel cila" DEĞİL,
   PUAN GETİREN farklılaştırıcı. Echo Dot Max ekransız ama Alexa+ telefon app /
   simülasyonda zengin kart gösterebiliriz. (Değerlendir: en azından mockup düzeyinde.)
3. **Jüri "slop" avında.** Cilalı ama çalışmayan "vapor" demolar eleniyor.
   "Outsource your work, don't outsource your understanding." → Demo videosunda
   sistemin GERÇEKTEN çalıştığı gösterilmeli (Kay local mode + gerçek Crew bunu sağlar).
4. **"Kendi derdini çöz" (start with your complaint).** İnsan hikayesi çok
   önemseniyor. Accessibility/Deniz personası buna uyuyor. AÇIK SORU: Bu senin
   kendi günlük derdin mi, empati kurduğun kullanıcının mı? Video anlatısı buna göre.
5. **AWS Builder'da Kiro AÇIKÇA sayıldı** ("Kiro", "Cloud Code/Codex on Bedrock",
   Bedrock, AgentCore, Strands, Recognition, voice). → Kiro Crew + Bedrock özet
   kullanımımız doğal oturuyor. **Herkese 150$ AWS kredi** (form, 21 Ekim'e kadar,
   kişi başı; takımdaki herkes ayrı alabilir). MUTLAKA doldur.
6. **Ödül önceliği: Alexa+ ve Fire TV "priority prizes."** Bizim track (Alexa+)
   Amazon'un en çok önemsediği ikiden biri (25.000$ + yüksek ilgi → yüksek rekabet).
7. **Judging = tech (nasıl implement edildi, hangi API/SDK) + design/UX +
   creativity/imaginative use case** + **friction log/feature request = ÇARPAN**
   (multiplier). Baştan friction log tut.
8. **Submission mekaniği:** kod herkese açık olmak zorunda değil AMA jüri çalışır
   halde görmeli; <3dk video; test yolu; IP sende kalır. Judging ~Kasım ilk 2 hafta,
   kazananlar re:Invent civarı (~20 Kasım sonrası).

## Aksiyon Listesi (transkriptten türeyen)
- [ ] 150$ AWS kredi formunu doldur (21 Ekim'e kadar; kredileri gerçekten kullan).
- [ ] Discord "Amazon developer check-in" kanalına gir (duyurular + SDK/API
      güncellemeleri 8 hafta boyunca oradan gelecek; Emerson = Alexa+ uzmanı).
- [ ] Friction log + feature request dosyasını İLK GÜNDEN aç (çarpan puanı).
- [ ] Rich card / MCP Apps mockup'ını en azından değerlendir (frontrunner sinyali).
- [ ] Video anlatısında "insan hikayesi + gerçekten çalışıyor" ikisini birden ver.

## Stratejiye Etki
- Simülasyon yolu = güvenli VE beklenen. Kay bridge'i ile gerçek cihaz = bonus fark.
- MCP Apps (zengin kart) yükseltildi: cila değil, hedef. Ama çekirdek DEĞİL —
  önce ses+onay+Crew çalışsın, sonra kart. (Kapsam önceliği korunuyor.)
- "Transport=Kay, Intelligence=biz" + accessibility insan hikayesi + gerçekten
  çalışan demo + friction log = jürinin aradığı profilin tam ortası.

---
---

# 💡 Proje Motivasyonu & Anlatı (KESİN — hikayenin kalbi)

> Kullanıcının (Akif) gerçek motivasyonu. Video anlatısı ve konumlandırma bundan
> türeyecek. Bu, jürinin aradığı "insan hikayesi / kendi derdini çöz" kriterinin
> tam karşılığı — UYDURMA DEĞİL, yaşanmış.

## Gerçek complaint (hikayenin başlangıcı — otantik)
"Aynı anda 3 projede IDE'de çalışırken, Kiro bana sürekli durup 'devam edeyim mi /
onaylıyor musun?' diye soruyor. Ekrana dönüp tek tek cevap vermek en büyük engelimdi."
→ Bu Akif'in KENDİ derdi. Darliss'in "start with the thing that annoys you most"u.

## Çözüm zinciri (organik)
1. Kiro Crew = işi otonom yapıyor (sen başında olmadan çalışıyor).
2. Ama otonom çalışırken de onay/devam anları var — aynı dert, üstelik artık
   ekranda bile değilsin.
3. Echo Dot Max = ekrana hiç dönmeden, sesle bu onayları vermek + durum sormak.
4. SONRA fark: bu "cool"un ötesinde — görme engelli geliştiriciler için HAYATİ.
   Sıra önemli: ÖNCE kendi derdi (otantik) → SONRA sosyal fayda (curb-cut). Tersi
   olsa "samimi mi?" sorusu doğardı.

## ⭐ Çekirdek çerçeve: "araç" değil "MESLEKTAŞ" (colleague metaforu)
- Çoğu sesli asistan ARAÇTIR: emir-itaat, tek yönlü (ışığı aç).
- KiroWhisper MESLEKTAŞTIR: Crew kendi işini yapar, gerektiğinde SANA döner —
  "şunu böyle mi yapayım?", "bunu onaylıyor musun?". Yan odada çalışan ekip
  arkadaşının kafa uzatıp sorması / telefonla araması gibi.
- Bu metafor kuralların "creative, agentic, maintains state across sessions"
  tanımının kalbi: meslektaş durumu hatırlar (state), iki yönlü konuşur, karar
  için danışır (onay), ham log değil ÖZET geçer.
- "MCP wrapper vs creative agentic add-on" farkı = "araç vs meslektaş" farkı.

## İki etkileşim yönü (teknik olarak AYRI — demoda dürüst ayrılacak)
1. **PULL — sen sorarsın:** "Kiro ne durumdasın?" → özet verir. GERÇEK, kolay,
   MCP request-response'a uyar, garantili.
2. **PUSH — o sana döner:** Crew onaya takılınca KENDİSİ seni "arıyor" gibi
   konuşur. "Telefonla arayan meslektaş" hissinin kalbi BU. AMA teknik olarak
   zor: MCP server kendiliğinden konuşamaz, Alexa+ proaktif ses native değil.
   → SAHNELENECEK (Alexa Routine + zamanlama / notification tetikleme). Demoda
   "bu kısım sahnelendi" diye dürüst olunacak.

## 🎯 Değer Hiyerarşisi (KESİN öncelik)
1. **Esas TEKNİK değer:** akıllı özet (Bedrock) + güvenli onay (niyet-ayrıştırma).
   Projenin beyni; "wrapper değil" kanıtı. → EN ÖNEMLİ.
2. **Esas DENEYİM değeri:** iki yönlü "canlı meslektaş" hissi, ekransız. Projenin
   ruhu; jüriyi büyüleyecek şey.
3. **ASİL amaç:** görme engelli geliştiriciler için gerçek erişilebilirlik (curb-cut).
- Üçü birbirini besler: meslektaş hissi (2), akıllı özet+güvenli onay (1) sayesinde
  mümkün (meslektaş ham log okumaz, özetler ve güvenle sorar); bu deneyim (2),
  ekrana bakamayan biri için (3) hayati.

## 🔗 KiroCan bağlantısı (portföy çizgisi — mxkiro-mac reposu)
- KiroCan: Logitech MX Creative Console → Kiro IDE (fiziksel arayüz → INTERAKTİF
  IDE, sen başındayken).
- KiroWhisper: ses/Echo → Kiro Crew (→ OTONOM Crew, sen başında değilken / ekrana
  bakamazken). Aynı çizginin doğal evrimi.
- Video'da: "bu işi zaten yapıyorum (KiroCan), bu bir sonraki adım" → jüriye
  gerçek bir yolculuk/uzmanlık hissi verir (kuralların "genuine understanding of
  the developer ecosystem" kriteri).
- NOT: mxkiro-mac reposu şu an private/erişilemez göründü (API meta null). Sorun
  değil, koduna ihtiyaç yok; anlatı bağlantısı yeterli.

## 🎬 Video iskeleti (3 dk, öneri — persona: SEN kendin anlatırsın)
1. 0-30sn HOOK: kendi derdin (3 proje, sürekli onay, ekrana dönme yorgunluğu).
2. 30-90sn ÇÖZÜM + CANLI DEMO: Crew otonom çalışıyor, sen ekrandan uzaktasın,
   "meslektaş" seninle konuşuyor, sesle yönetiyorsun. GERÇEKTEN çalıştığını göster.
3. 90-150sn DERİNLİK: akıllı özet + güvenli onay nasıl çalışıyor (kısa teknik).
4. 150-180sn CURB-CUT/ASALET: "benim için kolaylık; görme engelli geliştirici için
   ekrana hiç bağımlı olmadan kod yazabilmek."
- Persona kararı: SEN kendin (otantik). "Deniz" (görme engelli geliştirici) ikinci
  perdede "ve şunu düşün..." diye gelir. (Kullanıcı onayı bekliyor — aşağı bkz.)

---
---

# ✅ Emerson (Alexa+ Evangelism Head) Q&A — Simülasyon KESİN Netleşti

> Kaynak: Devpost hackathon forumu, Emerson Sklar'ın resmi cevapları (2 ayrı
> thread). Simülasyonla ilgili TÜM belirsizlikleri kapatıyor. Çelişkide öncelikli.

## Simülasyon kuralları (Emerson'ın madde madde cevabı)
1. Alexa+ arayüzüne benzemek ZORUNLU DEĞİL (ama benzerlik Design puanına yardım eder).
2. Dinamik/gerçek agent cevabı GEREKMİYOR — simüle edilebilir (Alexa+'ı çağırmak
   zaten imkansız).
3. Sesli giriş/çıkış ZORUNLU DEĞİL — metin de olur. (BİZ sesli yapacağız = ruh + artı puan.)
4. Kendi custom UI (kart, görselleştirme) TAMAMEN SERBEST.
5. "Bu bir simülasyondur" demek ZORUNLU DEĞİL (biz dürüstlük için yine de diyebiliriz).
6. **⭐ Backend + agentic workflow'lar TAMAMEN GERÇEK olabilir; SADECE Alexa+
   etkileşim katmanı simüle.** Emerson net "Yes". → BİZİM MİMARİMİZİN AYNISI:
   MCP + Kiro Crew + Bedrock özet = GERÇEK; sadece "Alexa+" yüzü simüle. RESMİ ONAY.
7. Resmi mock örnekleri: add-on design guide (mcp-addon-design-guide-overview) +
   **apl.ninja** (APL ile UI mockup). Rich card istersek buradan.
8. **⭐ Demo ölçütü:** "gerçekten çalışıyormuş gibi GÖRÜNMELİ/HİSSETTİRMELİ ve
   Alexa'da makul bir kullanım senaryosu olmalı." Emerson: jüri gerçek cihaz
   videosuyla tam simülasyonu ZATEN ayırt edemez. "Arkada gizlice Kiro kullanan,
   Alexa'ya benzemeyen ama kaliteli web app" bile kabul.

## İkinci thread: proaktif "arama" (bizim PUSH sorunumuzu çözüyor)
- Silvia: Add-on Alexa-to-Alexa arama / Drop In tetikleyebilir mi?
- Emerson: Bugün add-on ile tetiklenemez, AMA **submission'da DEMO EDİLEBİLİR**
  ("submission ve judging kriterleri publicly documented add-on yeteneklerine
  BAĞLI DEĞİL"). Alexa Smart Properties hackathon kapsamı dışı (sadece ASP partnerleri).
- → BİZİM İÇİN: "telefonla arayan meslektaş" (PUSH) anını simülasyonda göstermek
  TAMAMEN MEŞRU; gerçek altyapıda mümkün olması GEREKMİYOR. Push endişesi bitti.

## 🎯 Stratejiye Net Etki (güncelleme)
- **"Transport = Kay" artık OPSİYONEL.** Backend gerçek + Alexa yüzü simüle =
  yeterli (Emerson #6). Kendi web tabanlı sesli simülasyonumuz (senin sesin →
  gerçek MCP+Crew+Bedrock → sesli cevap) track'e TAM uygun. Kay'in bridge'i =
  "gerçek Echo'da ekstra inandırıcılık" için BONUS seçenek, zorunluluk değil.
- **Push/proaktif sahneleme MEŞRULAŞTI** (Emerson, ikinci thread). Endişe kalktı.
- **Rich card yolu açık:** apl.ninja / kendi UI → Design puanı.
- **ODAK:** Enerji Alexa entegrasyonuna DEĞİL, GERÇEK BEYNE (Crew + akıllı özet +
  güvenli onay) + KALİTELİ DEMOYA. Emerson #8 tam bunu diyor: kalite + makul senaryo.

## Güncel Karar: Simülasyon Yaklaşımı
- Birincil: **Kendi web tabanlı sesli simülasyon** (tam kontrol, gerçek beyin,
  senin sesin). Track'e yeter, Emerson onaylı.
- İkincil/bonus: Kay'in bridge'i ile gerçek Echo Dot Max'te de göster (ekstra "wow").
- Görsel: kendi UI (meslektaş konuşma + task kartları); istenirse apl.ninja mock.

---
---

# 🧾 Kurulum İlerlemesi (hassas olmayan özet)

> Hassas bilgiler (Account ID, kredi kodu, kart, TCKN, telefon) BURADA DEĞİL →
> docs/PRIVATE_NOTES.md içinde (.gitignore'da, push edilmez).

## Donanım / Hesaplar
- ✅ Echo Dot Max geldi; US Amazon hesabında Alexa+ çalışıyor.
- ✅ AWS hesabı açıldı (bireysel, Türkiye faturalama, paid plan).
- ✅ AWS region us-east-1 (N. Virginia) "Enabled by default" — kullanıma hazır.
- ✅ 150$ AWS hackathon kredisi redeem edildi, durum Active (2028'e kadar geçerli).

## Hesap İlişkileri (özet)
- AWS (TR) = Bedrock / Crew / kredi.  Alexa+/Echo (US) = ayrı.  Developer hesabı =
  sadece Kay bridge (Track C) kullanılırsa, Echo'nun US hesabıyla aynı olmalı.
- AWS'nin TR olması Alexa+'ı etkilemez; Bedrock us-east-1'den kullanılır.

## Güvenlik Kararı
- docs/PRIVATE_NOTES.md + .gitignore eklendi. Kritik/kişisel bilgiler asla remote'a
  push EDİLMEYECEK. Repo public olsa bile private not paylaşılmaz.
- Ekran görüntülerinde Account ID / kart / TCKN karartılacak; açık kanallara (repo,
  Discord) yazılmayacak.

## Bekleyen (hassas olmayan)
- [ ] Billing budget/alarm kur (maliyet güvenliği).
- [ ] Bedrock model access (us-east-1, Nova 2 Lite) — Bedrock'a başlarken.
- [ ] Crew spike (projenin beyni) — henüz başlanmadı.
