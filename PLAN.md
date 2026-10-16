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
- [x] 3. İndeks: qwen3-embedding-8b (API) embedding, BM25 (SQLite yerine düz dosya)
- [x] 4. Arama: hybrid (BM25 + embedding), RRF, recall@k ölçümü
- [x] 5. Sohbet servisi: prompt, acil durum kontrolü, Claude çağrısı, [1] [2] atıfları
- [x] 6. FastAPI (SSE streaming) ve mobil uyumlu web sayfası
- [x] 7. Eval ve güvenlik testleri
- [x] 8. Dockerfile ve README

## Kurallar
- Sadece bulunan kaynaklara dayan, bilmiyorsan söyle.
- Teşhis, reçete, doz yok.
- Acil belirtide 112'ye yönlendir.
- Her yanıtta kısa tıbbi uyarı.
- Testlerde Claude ve embedding mock'lanır.

## Sonraki adımlar (öneriler, öncelik sırasıyla)

Etki ve zahmete göre sıralı. Hepsi mevcut altyapının (Evren API, Actions, değerlendirme düzeni) üstüne kurulur.

1. **Yapılandırılmış belirti değerlendirmesi (triage diyaloğu).** Asistan eksik bilgiyi sorar (ne zamandır, şiddeti,
   eşlik eden belirtiler, yaş, kronik hastalık) ve sonunda seviye verir: 112 / bugün hekime / randevu / evde izle.
   "Doktor gibi" hissin ve güvenliğin en büyük kazancı.
2. **Cevap doğrulama katmanı.** Üretilen cevaptaki her iddiayı atıf yaptığı kaynakla çalışma anında kontrol et;
   desteklenmeyen cümleyi çıkar ya da işaretle. Şu an kaynağa sadakat yalnızca testte ölçülüyor.
3. **Daha güçlü arama.** Yeniden sıralayıcı (reranker), sorgu genişletme, daha iyi parçalama. Hedef: recall@1'i
   0,65'ten yukarı çekmek. Değerlendirme setini 150'den 500+ soruya çıkarmak ve insan onaylı bir altın küme eklemek.
4. **Daha zengin ve güncel bilgi tabanı.** Açık lisanslı ek kaynaklar (PubMed özetleri, openFDA ilaç prospektüsleri,
   uygun lisanslı Türkçe halk sağlığı içeriği), haftalık otomatik yenileme workflow'u.
5. **Fotoğraf ve ses.** İlaç kutusu ya da tahlil sonucu fotoğrafını görsel modelle okuyup açıklama; sesle soru sorma
   ve cevabı sesli dinleme.
6. **Tahlil yorumlama.** Referans aralıklarına dayalı, kural tabanlı ve LLM açıklamalı "değerim normal mi?" aracı.
7. **Üretim hazırlığı.** Hız sınırı, kullanıcı oturumu ve basit giriş, kişisel veri minimizasyonu (KVKK),
   metrikler, önbellek, gerçek PWA, geri bildirim butonları (👍/👎) ve barındırma.
8. **Güvenlik sertleştirme.** Acil durum için kural + LLM sınıflandırıcı ikinci katman, otomatik red-team senaryoları,
   kaynak metnine gömülü talimat (prompt injection) setleri, yazıyla yazılmış dozların yakalanması.
