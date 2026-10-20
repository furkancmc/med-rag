# medrag — Türkçe Sağlık Bilgi Asistanı

Sağlıkla ilgili sorularına **güvenilir, açık tıbbi kaynaklara dayanarak** Türkçe cevap veren bir asistan. Her cevapta
hangi kaynaktan geldiği gösterilir; kaynakta olmayan bir şey söylenmez.

> **Bu bir doktor değildir.** Teşhis koymaz, ilaç ya da doz önermez. Acil bir belirti varsa önce 112'ye yönlendirir.
> Verdiği bilgiler genel bilgilendirme amaçlıdır.

<table>
  <tr>
    <td align="center"><img src="docs/screens/ui/sohbet-kaynakli-cevap.png" width="200"><br><sub>Kaynaklı cevap</sub></td>
    <td align="center"><img src="docs/screens/ui/sohbet-acil.png" width="200"><br><sub>Acil durum</sub></td>
    <td align="center"><img src="docs/screens/ui/belirti-2-soru.png" width="200"><br><sub>Belirti değerlendirme</sub></td>
    <td align="center"><img src="docs/screens/ui/tahlil-1-giris.png" width="200"><br><sub>Tahlil yorumu</sub></td>
  </tr>
</table>

<sub>Görüntüler arayüzü göstermek için sahte servisle alındı; gerçek cevap kalitesini yansıtmaz.</sub>

## Ne yapar?

- **Sohbet:** Soruyu anlar, ilgili kaynak parçalarını bulur, cevabı `[1] [2]` atıflarıyla yazar ve yayınlamadan
  önce kaynaklarla yeniden kontrol eder. Desteklenmeyen cümleleri işaretler.
- **Belirti değerlendirme:** Şikâyetini yazarsın, birkaç kısa soru sorar, ne kadar acil olduğunu söyler
  (112 / bugün hekim / birkaç gün içinde randevu / evde izle).
- **Tahlil yorumu:** Tahlil değerlerini girersin ya da sonuç kâğıdının fotoğrafını çekersin; hangi değerin düşük,
  normal ya da yüksek olduğunu kaynaklı açıklamayla gösterir.
- **Telefona uygun:** Ana ekrana eklenebilir (PWA), koyu/açık tema, hesap gerekmez.

## Güvenlik ilkeleri

- Yalnızca kaynaktaki bilgiye dayanır; bilgi yoksa "bulamadım" der.
- Teşhis, reçete ve doz yok (kaynakta yazsa bile doz cümleleri çıkarılır).
- Acil belirtide model çağrılmadan önce 112 uyarısı verilir. Kural tabanlı güvenlik kararını LLM yalnızca
  yukarı çekebilir, aşağı indiremez.
- Görseller ve sesler saklanmaz; sohbet geçmişi yalnızca kendi tarayıcında durur.

## Veri kaynakları

MedlinePlus, Vikipedi, Europe PMC, openFDA ve CDC gibi açık lisanslı kaynaklardan derlenen yaklaşık 33 bin
metin parçası. Her cevapta kaynağın adı, lisansı ve bağlantısı görünür.

## Nasıl çalışır?

Soru → arama (yerel BGE-M3 vektör araması) → bulunan kaynaklarla cevap üretimi (Evren API) → kaynaklarla doğrulama.
Python 3.11 ve FastAPI ile yazıldı.

## Kurulum

Gerekenler: Python 3.11+ ve bir Evren API anahtarı.

```bash
git clone https://github.com/furkancmc/med-rag && cd med-rag
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env    # içine EVREN_API_KEY yaz
python -m medrag.index embed --backend local           # arama indeksi, ilk seferde ~6 dk (GPU)
python -m medrag.api                                   # http://localhost:8000
```

API anahtarı olmadan arayüzü denemek için: `python scripts/dev_server.py` (sahte servis, gerçek çağrı yapmaz).
Docker ile çalıştırmak için `docker compose up`.

Testler: `PYTHONPATH=src python -m pytest -q`

## Durum

Çalışan bir ilk sürüm: sohbet, belirti değerlendirme, tahlil yorumu, arayüz ve Docker hazır; 490 birim testi ve
60 güvenlik senaryosu geçiyor. Henüz yapılmayanlar:

- **Hekim incelemesi:** Tahlil aralıkları ve belirti kuralları internetteki otoriter kaynaklarla karşılaştırıldı
  ama bir hekim tarafından onaylanmadı.
- Fotoğraftan tahlil okuma ve sesli soru, gerçek telefon fotoğrafı/sesi ile yeterince denenmedi.

## Daha fazlası

Ölçümler, mimari, model seçimleri ve bilinen sınırlar: [docs/teknik-detaylar.md](docs/teknik-detaylar.md)

## Lisans

Kod lisansı için [LICENSE](LICENSE); veri kaynaklarının lisansları cevaplardaki kaynak kartlarında yazar.
