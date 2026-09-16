# Implementation Plan — KiroWhisper

> Kiro spec-driven development. Her görev artımlı, test edilebilir ve bir önceki
> üstüne kurulur. Requirement referansları `requirements.md`'ye işaret eder.
> İnşa sırası: önce Crew köprüsü (kanıtlı), sonra zeka (Ambient), sonra yüz (MCP+ses).
>
> Kapsam etiketi: [ÇEKİRDEK] önce ve kusursuz; [FARK] çekirdek çalışınca;
> [v2] submission'da "future work".

## Faz 0 — Proje iskeleti ve ortam

- [ ] 0.1 Python 3.12 proje iskeletini kur (`src/kirowhisper/`, `pyproject.toml`,
  venv, `pytest`, `ruff`). Bağımlılıklar: `httpx`, MCP Python SDK, `boto3` (Bedrock).
  - _Design: Teknik kararlar / Yapı_

- [ ] 0.2 Yapılandırma katmanı: Gateway URL, token kaynağı (`kirocrew token`),
  Bedrock region (us-east-1) ve model id'lerini merkezi bir config'ten oku.
  - _Requirements: NFR-5; Design: Teknik kararlar_

## Faz 1 — Crew Gateway İstemcisi  [ÇEKİRDEK]

- [ ] 1.1 `gateway_client.py`: `?token=` + `Origin` auth ile ince REST istemcisi.
  `get_status`, `list_pending_approvals`, `get_slot`, `resolve`, `send_message`,
  `spawn`, `get_task_result`. Token'ı `kirocrew token`'dan al, süre bitince yenile.
  - _Requirements: R1, R4, R5, R12.2; Design: Bileşen 1_
  - _Not: spike/ script'lerinden türet; auth ve action="approved" tuzağı kanıtlı._

- [ ] 1.2 `gateway_client` için birim testleri (sahte HTTP): auth header/param
  doğru mu, `resolve` gövdesi `{"action":"approved","request_id":...}` mı, hata
  durumunda exception mı.
  - _Requirements: R5.3, R5.4_

- [ ] 1.3 Entegrasyon dumanı testi: gerçek yerel Gateway'e karşı `get_status` +
  `list_pending_approvals` çalışıyor mu (spike'ın ürünleşmiş hali).
  - _Requirements: R1.1, R1.2_

## Faz 2 — Veri modelleri ve Audit  [ÇEKİRDEK]

- [ ] 2.1 Veri modelleri: `Approval`, `RiskAssessment`, `Decision`,
  `PendingDecision`, `AuditEntry` (dataclass/pydantic).
  - _Design: Veri modelleri_

- [ ] 2.2 `audit.py`: append-only yerel kayıt (ts, id, risk, karar, gerekçe).
  Secret maskeleme. Özet için okuma API'si.
  - _Requirements: R10, NFR-1; Design: Bileşen 7_

## Faz 3 — Risk Sınıflandırıcı  [ÇEKİRDEK — projenin zekası]

- [ ] 3.1 `risk.py` (a) deterministik kural katmanı: `is_read_only`→LOW,
  `is_shell`→≥HIGH, yıkıcı desenler (`rm -rf`, `DROP`, `force`, `.env`/secret,
  geniş silme)→HIGH, net değilse→devret. Kurallar güvenlik yönünde tek-yönlü sıkı.
  - _Requirements: R2.2, R2.3, R2.4, R2.5_

- [ ] 3.2 `risk.py` (b) Bedrock katmanı: ham tool+purpose+diff → yapılandırılmış
  risk + gerekçe. Hata/emin-değil → UNKNOWN. Sadece kural "net değil" derse çağrılır.
  - _Requirements: R2.1, R2.6; Design: Bileşen 3_

- [ ] 3.3 Risk sınıflandırıcı birim testleri: bilinen tehlikeli/güvenli diff
  örnek seti; kural katmanı deterministik olarak doğru sınıflıyor mu; Bedrock
  hatasında UNKNOWN'a düşüyor mu (fail-safe).
  - _Requirements: R2.5, NFR-1_

## Faz 4 — Özetleyici  [ÇEKİRDEK]

- [ ] 4.1 `summarizer.py`: Bedrock ile sese uygun özet — onay özeti, durum özeti,
  ambient özeti. Kısa, öncelik sıralı, ham diff değil, ≤2-3 seçenek.
  - _Requirements: R4.4, NFR-3; Design: Bileşen 4_

- [ ] 4.2 Özetleyici testleri: uzun diff → kısa sese uygun metin; secret sızıntısı yok.
  - _Requirements: NFR-1, NFR-3_

## Faz 5 — Ambient Awareness Motoru  [ÇEKİRDEK — projenin kalbi]

- [ ] 5.1 `ambient.py` polling döngüsü (asyncio, ~2-3sn): yeni approval'leri
  idempotent tespit et (görülenleri hatırla). Gateway down → retry, oto-onay YOK.
  - _Requirements: R1.1, R1.3, R1.4_

- [ ] 5.2 Karar politikası (`policy.decide`): LOW+trust→AUTO_APPROVE,
  açık-deny→AUTO_BLOCK, HIGH/UNKNOWN→SURFACE. Muhafazakâr: emin değilse SURFACE.
  Kararı audit'e yaz, gateway.resolve ile uygula.
  - _Requirements: R3.1, R3.2, R3.3, R3.4, R3.5_

- [ ] 5.3 SURFACE kuyruğu + snapshot API'si (kaç AUTO/BLOCK/SURFACE) — durum
  özetinin ("19'unu geçtim...") kaynağı.
  - _Requirements: R4.3_

- [ ] 5.4 Ambient motoru testleri (sahte Gateway): üç kova kararı doğru mu;
  idempotentlik; fail-safe (Gateway/Bedrock hatası → SURFACE, asla sessiz onay).
  - _Requirements: R1.4, R3.3, R3.5, NFR-1_

## Faz 6 — MCP Server  [ÇEKİRDEK — Alexa+ runtime şartı]

- [ ] 6.1 `mcp_server.py`: MCP Python SDK, **Streamable HTTP**. Tool'lar:
  `get_status`, `get_pending_decisions`, `approve`, `reject`, `trust_session`,
  `summarize`. Her tool ilgili çekirdek servisi çağırır (runtime'da gerçek MCP).
  - _Requirements: R12.1, R12.2; Design: Bileşen 5_

- [ ] 6.2 `approve` tool: HIGH risk ise çift-teyit bilgisi döndür; net onayla
  gateway.resolve("approved"). `reject` tool: atla/durdur/iptal yönetimi.
  - _Requirements: R5.1, R5.2, R6.1, R6.2, R6.3, R6.4, R6.5_

- [ ] 6.3 MCP server'ı MCP Inspector veya test client ile doğrula (tool discovery
  + çağrı + spec 2025-11-25 uyumu).
  - _Requirements: R12.2_

## Faz 7 — Ses Arayüzü (simülasyon)  [ÇEKİRDEK]

- [ ] 7.1 `voice_sim/` web arayüzü: mikrofon → STT → MCP tool çağrısı → yanıt → TTS.
  Düşük gecikmeli STT/TTS. Kullanıcının kendi sesi. ElevenLabs yok.
  - _Requirements: R11.1, R11.3, NFR-2_

- [ ] 7.2 Proaktif bildirim: ambient SURFACE ürettiğinde arayüz sesli anons
  tetikler. Demoda simülasyon dürüstçe etiketli.
  - _Requirements: R7.1, R7.2, R7.3, R11.4_

- [ ] 7.3 Uçtan uca akış provası: kahvaltı senaryosu (Crew otonom → ambient süzer
  → 1 gerçek karar proaktif gelir → sesle onayla → dosya değişir).
  - _Requirements: R4, R5, R7; Design: Akış B_

## Faz 8 — Farklılaştırıcılar  [FARK — çekirdek çalışınca]

- [ ] 8.1 Oturum güveni (`trust_session`): LOW oto-onay; HIGH/UNKNOWN yine SURFACE.
  - _Requirements: R8_

- [ ] 8.2 Bağlam takibi + clarifying question: çoklu görev atıf eşleme;
  `waiting_for_input`/`has_options` → sesli seçenek sunma.
  - _Requirements: R9_

- [ ] 8.3 Standup özeti + hata bildirimi: çoklu görev durumu + başarısızlık.
  - _Requirements: R4.2, R7.4 (UC-10, UC-12)_

## Faz 9 — Hackathon teslim gereksinimleri  [ÇEKİRDEK — puan]

- [ ] 9.1 README: net kurulum + çalıştırma talimatları; mimari; simülasyon dürüst
  açıklaması. Görünür açık kaynak LICENSE (About'ta görünsün).
  - _Requirements: NFR-5, R12.3_

- [ ] 9.2 Product Feedback dokümanı: kullanılan her tool/SDK (Kiro Crew, MCP SDK,
  Bedrock, STT/TTS) için ne işe yaradı / neyi zorladı / onboarding / tekrar kullanır mıydım.
  - _Requirements: NFR-5_

- [ ] 9.3 Friction Log: geliştirme boyunca yaşanan sürtünmeler (auth tuzağı,
  action="approved", proaktif ses kısıtı vb.) — %10 bonus.
  - _Requirements: NFR-5_

- [ ] 9.4 <3 dk demo videosu: kahvaltı senaryosu; insan hikayesi + gerçekten
  çalışan sistem; curb-cut mesajı. Simülasyon dürüstçe belirtilir.
  - _Requirements: NFR-5, R11.4_

## Faz 10 — Gelecek (v2)  [v2]

- [ ] 10.1 Mid-task redirect (UC-8): çalışan slot'a müdahale.
- [ ] 10.2 Sesle yeni görev başlatma (kapsam dışı — commodity riski).
- [ ] 10.3 Gerçek Alexa+ MCP add-on (toolkit açılırsa) / Kay bridge ile gerçek Echo.

---

## İnşa sırası özeti
Faz 0 → 1 (köprü, kanıtlı) → 2 (model/audit) → 3 (risk = zeka) → 4 (özet) →
5 (Ambient = kalp) → 6 (MCP = Alexa şartı) → 7 (ses = yüz) → 9 (teslim, sürekli) →
8 (fark) → 10 (v2).

## Çekirdek "bitti" tanımı (minimum kazanabilir ürün)
Faz 1-7 + 9 tamam: Crew'e bağlı, onayları risk'e göre süzen, sadece gerçek kararı
sesle getiren, gerçek sesle onaylanıp Crew'de işlemi tetikleyen, MCP server olarak
paketlenmiş, simülasyonla demo edilebilir bir sistem. Fark = Ambient Awareness.
