# Crew Spike — feasibility proof

Kiro Crew Gateway'e programatik erişimi ve **insan-döngüde onay** akışını doğrulayan
tek seferlik keşif scriptleri. Ürün kodu DEĞİL — KiroWhisper'ın teknik olarak
mümkün olduğunu kanıtlamak için yazıldı.

## Ne kanıtlandı
- `test_1_connect.py` — Gateway bağlantısı (auth araştırması).
- `test_2_pull.py` — `spawn` + durum okuma (PULL / "Kiro ne durumda?").
- `test_3_approval.py` / `test_3b_resolve.py` — bekleyen onayı bulma + çözme.
- `test_4_e2e.py` — **UÇTAN UCA:** görev → onay yakala → programatik approve →
  dosya gerçekten oluştu. Projenin kalbinin kanıtı.

## Çalıştırma (yerel Crew Gateway gerektirir)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install aiohttp    # test_1 için; diğerleri sadece stdlib + `kirocrew token`
python3 test_4_e2e.py
```

## Bulgular
Ayrıntılı sonuçlar: `../docs/PROJECT_NOTES.md` → "CREW SPIKE SONUÇLARI" bölümü.
Auth: `kirocrew token` → JWT → istekte `?token=<JWT>` query param + `Origin` header.
Onay çöz: `POST /api/chat/slots/<slot>/approve {"action":"approved","request_id":...}`.
Kritik tuzak: `action` **"approved"** olmalı (geçmiş zaman); "approve" sessizce reddeder.

> Not: Bu scriptler gizli değer İÇERMEZ; token runtime'da `kirocrew token`'dan alınır.
