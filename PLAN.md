# Yol haritası

Tıbbi dokümanlar üzerinde RAG ile Türkçe sohbet asistanı. GPU gerekmez.
Cevaplar Claude API ile üretilir, kaynak gösterilir.

## Veri kaynakları
- MedlinePlus sağlık konuları (kamu malı, İngilizce/İspanyolca XML)
- Vikipedi tıp makaleleri, tr ve en (CC BY-SA, kaynak ve lisans metadata'da tutulur)
- `data/` klasörüne konan kendi PDF/TXT dosyaları
- WHO sayfaları lisansı (CC BY-NC-SA) yüzünden şimdilik dışarıda

## Aşamalar
- [x] 1. İskelet: pyproject, ayarlar, CI, README
- [x] 2. Veri hattı: indirme, parse, chunk (kod hazır; gerçek veri ağ erişimi gelince indirilecek)
- [ ] 3. İndeks: multilingual-e5-small embedding, BM25, SQLite
- [ ] 4. Arama: hybrid (BM25 + embedding), RRF, recall@k ölçümü
- [ ] 5. Sohbet servisi: prompt, acil durum kontrolü, Claude çağrısı, [1] [2] atıfları
- [ ] 6. FastAPI (SSE streaming) ve mobil uyumlu web sayfası
- [ ] 7. Eval ve güvenlik testleri
- [ ] 8. Dockerfile ve README

## Kurallar
- Sadece bulunan kaynaklara dayan, bilmiyorsan söyle.
- Teşhis, reçete, doz yok.
- Acil belirtide 112'ye yönlendir.
- Her yanıtta kısa tıbbi uyarı.
- Testlerde Claude ve embedding mock'lanır.
