# KiroWhisper — Use Cases

> Bu doküman KiroWhisper'ın kullanım senaryolarını tanımlar. Requirement'lar
> (user story + acceptance criteria) buradan türeyecek. Her use case'te:
> aktör, tetikleyici, akış, **spike-gerçekliği** (canlı testte ne kanıtlandı) ve
> **öncelik** var.
>
> Kaynaklar: PROJECT_NOTES.md (araştırma + Crew spike sonuçları), Emerson Q&A
> (simülasyon), Devpost jüri sinyalleri, accessibility araştırması (MS Research,
> arXiv 2506.13270).

---

## 0. Kimlik: KiroWhisper nedir (tek cümle)

Otonom çalışan Kiro Crew'i, **ekrana bakmadan sesle denetleyen bir meslektaş** —
gürültüyü senin yerine süzer, sadece gerçek kararı getirir, gerisini güvenle halleder.

**Araç değil, meslektaş.** Emir-itaat eden bir asistan değil; yan odanda çalışan,
gerektiğinde sana danışan, danışmadığında güvenle ilerleyen bir ekip arkadaşı.

## Persona
- **Deniz** — görme engelli, home-office geliştirici. Masada sürekli oturmaz.
  Ekran okuyucu kullanıyor ama uzun agent çıktılarını/onaylarını sesle tek tek
  gezmek işkence. Ana kalp.
- **Curb-cut genişlemesi** — ekrandan uzaktaki herkes (kahvaltı, mutfak, eller/gözler meşgul).

## Değer hiyerarşisi (KESİN)
1. TEKNİK: Ambient Awareness (akıllı filtre + risk sınıflandırma) + güvenli onay.
2. DENEYİM: iki yönlü "canlı meslektaş" hissi, ekransız.
3. ASALET: görme engelli geliştirici için gerçek erişilebilirlik (curb-cut).

## Rekabet farkı (net tutulacak)
"Sesle coding" ARTIK COMMODITY (ChatGPT Voice→Codex, Google Antigravity). Bizim
farkımız SESLE KOD YAZMAK DEĞİL. Farkımız:
(a) accessibility-first (görme engelli, gerçek dert — MS Research + arXiv doğruluyor),
(b) ekransız/uzaktan OTONOM DENETİM (masada değilken, Echo ile),
(c) Ambient Awareness: gürültüyü süzen, sadece gerçek kararı getiren güvenli filtre.

---

# ⭐ KESKİN UÇ — Ambient Awareness (projenin kimliği)

> Bu, projeyi "MCP wrapper"dan "creative agentic add-on"a taşıyan yetenek.
> Demo bunun üzerine kurulur, submission başlığı budur. UC-1..12 bunun altyapısı.

## Problem (neden zorunlu)
Otonom agent saatlerce çalışırken DÜZİNELERCE onay noktasına takılır (dosya oluştur,
test çalıştır, paket kur, satır sil...). Hepsi sese gelirse KiroWhisper işkenceye
döner — çünkü SES, EKRAN GİBİ TARANAMAZ. Ekranda 20 onayı gözle 5 sn'de süzersin;
sesle 20 onay = 20 kesinti. Görme engelli için bu, sesli onayı KULLANILAMAZ kılar.

## Çözüm — üç kova
KiroWhisper sürekli konuşmaz. Ortamda sessizce bekler, Crew'in TÜM onay taleplerini
görür (`GET /api/approvals`), her birini risk açısından sınıflandırır, ve:
1. **Sessizce geçir (düşük risk):** dosya okuma, test, geri alınabilir düzenleme →
   otomatik onayla (`action:"approved"`), kullanıcıyı rahatsız etme.
2. **Sessizce engelle/beklet (bariz tehlike):** `rm -rf`, prod push, secret loglama →
   otomatik durdur (`action:"rejected"` veya beklet), sonra "şunu engelledim" özetle.
3. **Kullanıcıya getir (gerçek karar):** geri alınamaz ama meşru olabilecek, niyet
   gerektiren → SADECE bunlar sesli gelir.

Sonra kullanıcı sorunca özet:
> "Son 2 saatte Crew 23 adım yaptı. 19'unu güvenli olduğu için geçtim, 3 tehlikeliyi
> engelledim, 1 tanesi seni bekliyor: auth.js'i siliyor, geri alınamaz, emin olamadım."

## Neden creative (wrapper değil)
Crew tüm onayları EŞİT verir. Zeka BİZİM katmanımızda:
- Her onayı risk sınıflandır (Bedrock + kurallar): geri alınabilir mi? shell mi?
  secret'a mı dokunuyor? kaç satır? (Risk Radarı = bu adım.)
- Karar ver: geçir / engelle / getir.
- Biriktirip özetle: gürültüyü sinyale çevir.

## Güvenlik ilkesi (kritik)
- MUHAFAZAKAR filtre: emin değilse HER ZAMAN kullanıcıya getir (güvenli varsayılan;
  Crew'in "deny on silence" ruhuyla aynı).
- Kullanıcı HER ZAMAN ne geçtiğini görebilmeli ("19'unu geçtim, duymak ister misin?").
- Yıkıcı hiçbir şey sessizce geçmez — sadece açıkça düşük-riskli/geri-alınabilir olanlar.
- Her karar loglanır (audit; sorumlu-AI).

## Spike-gerçekliği: KANITLANDI ✅
- `GET /api/approvals` → tüm bekleyen onaylar (tool, purpose, input). ✅
- permission meta: `is_read_only`, `is_shell`, diff → risk sınıflandırmasının HAM VERİSİ hazır. ✅
- `action:"approved"` (geçir) / `"rejected"` (engelle) / kullanıcıya getir. ✅
- `action:"trust"` → "bu tip işleri hep geçir" (öğrenen filtre). ✅
- Bedrock (AWS Builder): ham diff/tool → risk sınıfı + sese uygun özet.

## Öncelik: ÇEKİRDEK (projenin kimliği — demo bunun üstüne kurulur)

---

# TEMEL ALTYAPI USE CASE'LERİ (UC-1 .. UC-12)

> Bunlar "meslektaş" deneyiminin altyapısı. Gerekli ama TEK BAŞINA fark değil.
> Ambient Awareness bunların üstünde çalışır.

## UC-1 — Durum sor (PULL / özet)
- **Aktör:** Deniz. **Tetikleyici:** "Kiro, ne durumda?"
- **Akış:** Sistem Crew durumunu + bekleyen onayları çekip sese uygun özetler.
  "Bir işi var: auth.js'de eski login'i silmek için onayını bekliyor. Başka bekleyen yok."
- **Spike:** ✅ `GET /api/status` + `GET /api/approvals`. Özet Bedrock ile.
- **Öncelik:** ÇEKİRDEK

## UC-2 — Onayla (yüksek riskli → çift-teyit)
- **Aktör:** Deniz. **Tetikleyici:** "Onayla."
- **Akış:** Yıkıcı/geri-alınamaz ise sistem niyet doğrular ("42 satırı siliyor,
  geri alınamaz, emin misin?") → net "evet" → onayla.
- **Spike:** ✅ `POST /api/chat/slots/<slot>/approve {action:"approved", request_id}`
  → `{"ok":true}`, dosya GERÇEKTEN değişti. Risk verisi: is_shell/is_read_only/diff.
- **Öncelik:** ÇEKİRDEK
- **TUZAK:** action="approved" (geçmiş zaman!) — "approve" sessizce rejected'e düşer.

## UC-3 — Reddet → alt seçenekler
- **Aktör:** Deniz. **Tetikleyici:** "Hayır."
- **Akış:** Önce güven ver ("yapmadım"), sonra sesli 3 seçenek: ATLA / DURDUR / İPTAL
  (hep aynı sıra/kelime). Güvenli varsayılan + timeout = DURDUR. İptal ayrıca teyit ister.
- **Spike:** ⚠️ `action:"rejected"` = atla/devam (native, ✅). "Durdur" = reddet+yeni
  mesaj gönderme (bizim map). "İptal" = slot durdur. Native ikili modeli 3'e biz açıyoruz.
- **Öncelik:** ÇEKİRDEK

## UC-4 — Sonuç dinle (görev bitti)
- **Aktör:** sistem→Deniz. **Tetikleyici:** görev tamamlandı.
- **Akış:** "İş bitti. 3 dosya değişti, testler geçti." (sese uygun özet)
- **Spike:** ✅ `GET /api/spawn/<id>` → done, turns, sonuç mesajları.
- **Öncelik:** ÇEKİRDEK

## UC-5 — Meslektaş seni arar (PUSH / proaktif) ⭐
- **Aktör:** sistem→Deniz. **Tetikleyici:** yeni onay/olay çıktı, kullanıcı ekranda değil.
- **Akış:** Sistem kendiliğinden araya girer: "KiroWhisper: 3. görev onayını bekliyorum."
  (müzik kısılır / ışık / kısa anons) → kullanıcı "ne var?" → akış.
- **Spike/kural:** ⚠️ SAHNELENECEK (Emerson: simülasyonda meşru). Teknik ayak:
  arka planda `GET /api/approvals` POLLING → yeni onayda sesli anons tetikle.
  Gerçek veri gerçek; "kendiliğinden konuşma" sahnelenir.
- **Öncelik:** ÇEKİRDEK (ruh) — ama Ambient Awareness ile birlikte: sadece FİLTREDEN
  geçen "gerçek karar" proaktif gelir, gürültü değil.

## UC-6 — "Artık hep onayla" (trust / oturum güveni)
- **Aktör:** Deniz. **Tetikleyici:** "Bu görev için hep onayla."
- **Akış:** Sistem oturumda kalan (düşük riskli) adımları oto-onaylar.
- **Spike:** ✅ `action:"trust"`. DİKKAT: sadece düşük-riskli çerçevesiyle sunulur.
- **Öncelik:** FARKLILAŞTIRICI

## UC-7 — Bağlam takibi (state across sessions)
- **Aktör:** Deniz. **Tetikleyici:** "Hangisi hata verdi?"
- **Akış:** Sistem birden fazla görev arasında hangisinden bahsettiğini takip eder.
  "2. görev — testler kırmızı. Onu mu açayım?"
- **Spike:** ✅ `GET /api/spawn` (liste + durumlar). "Hangisi" çözümü bizde (kısa hafıza).
- **Öncelik:** FARKLILAŞTIRICI (kurallar bunu "creative" sayıyor)

## UC-8 — Mid-task yönlendirme (redirect)
- **Aktör:** Deniz. **Tetikleyici:** agent çalışırken "Dur, o dosyaya dokunma, önce testler."
- **Akış:** Çalışan slot'a müdahale, yönü değiştir.
- **Spike:** ⚠️ `POST /api/chat {slot,message}` ile çalışan slot'a mesaj (test edilecek).
  ChatGPT Voice'un öne çıkardığı yetenek; bizde "meslektaşa araya girme".
- **Öncelik:** GELECEK (v2)

## UC-9 — Clarifying question (agent SANA sorar)
- **Aktör:** sistem→Deniz. **Tetikleyici:** agent açık uçlu bir seçim gerektiriyor.
- **Akış:** "İki yol var: token-tabanlı mı, session-tabanlı mı? Hangisini istersin?"
  → sesli seçim. Sadece onay değil, GERÇEK DİYALOG → "meslektaş" metaforunu tamamlar.
- **Spike:** ✅ (veri var) slot alanları: `waiting_for_input`, `needs_input`,
  `has_options`, `options` (spike'ta görüldü). Teknik olarak mümkün.
- **Öncelik:** FARKLILAŞTIRICI (meslektaş metaforunu tamamlar)

## UC-10 — Çoklu görev "standup" özeti
- **Aktör:** Deniz. **Tetikleyici:** "Genel durum ne?" / sabah briefing.
- **Akış:** "3 görevden 2'si bitti, biri onay bekliyor, biri hata verdi." (paralel özet)
- **Spike:** ✅ `GET /api/spawn` + `/api/status`. Bedrock özet.
- **Öncelik:** FARKLILAŞTIRICI

## UC-11 — Güvenli karar kaydı (audit)
- **Aktör:** sistem. **Tetikleyici:** her onay/red/filtre kararı.
- **Akış:** "Deniz 08:16'da silme onayını reddetti / KiroWhisper 3 tehlikeli işlemi
  engelledi" → loglanır, sorulunca özetlenebilir.
- **Spike:** ✅ kararlar bizde üretiliyor; loglama bizim katman. (Crew'de security_events da var.)
- **Öncelik:** FARKLILAŞTIRICI (sorumlu-AI puanı; HITL "delivery guarantee" ilkesi)

## UC-12 — Hata/başarısızlık bildirimi
- **Aktör:** sistem→Deniz. **Tetikleyici:** görev başarısız oldu.
- **Akış:** "2. görev başarısız oldu, testler kırmızı. Detay ister misin?"
- **Spike:** ✅ `task_complete` başarısızlıkla da gelir; `GET /api/spawn/<id>` durum.
- **Öncelik:** ÇEKİRDEK (sonuç döngüsünün parçası)

---

# Yeni görev başlatma — kapsam kararı
- KiroWhisper ODAK = DENETİM (monitor + approve), yeni iş başlatma DEĞİL.
- Sesle yeni görev başlatmak (`POST /api/spawn`) teknik olarak mümkün (spike ✅) ama
  bu bizi "sesle coding" commodity'sine yaklaştırır → kapsam DIŞI (v2). Fark denetimde.

---

# Kapsam özeti (requirement önceliği)
- **ÇEKİRDEK (olmazsa olmaz):** Ambient Awareness + UC-1,2,3,4,5,12
- **FARKLILAŞTIRICI (çekirdek çalışınca):** UC-6,7,9,10,11
- **GELECEK (v2, submission'da "future work"):** UC-8, sesle yeni görev başlatma

# Demo kurgusu (bu use case'lerden)
1. HOOK (0-30sn): Akif'in kendi derdi (3 proje, sürekli onay, ekrana dönme yorgunluğu).
2. AMBIENT AWARENESS (30-100sn): Crew otonom çalışıyor, KiroWhisper sessizce süzüyor;
   sadece 1 gerçek kararı sesle getiriyor (UC-5→UC-1→UC-2 çift-teyit). "19'unu geçtim."
3. DERİNLİK (100-150sn): risk sınıflandırma + güvenli onay nasıl çalışıyor (Bedrock).
4. CURB-CUT (150-180sn): "benim için konfor; görme engelli geliştirici için, ekrana
   hiç bağımlı olmadan otonom agent'ı yönetebilmek — çünkü ses tek başına taranamaz,
   filtre olmadan kullanılamaz."
