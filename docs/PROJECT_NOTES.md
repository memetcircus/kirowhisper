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
