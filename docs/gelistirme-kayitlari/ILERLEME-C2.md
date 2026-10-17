# C akışı: güvenlik turu 2 (17.10.2026)

- Doğrulama (`verification` olayı), ikinci katman LLM sınıflandırıcı, acil modda teşhis adı süzgeci ve yazıyla doz yakalama kodda zaten vardı; bu turda gerçek API ile doğrulandı.
- Eklendi: boş cevapta bir yeniden deneme, yine boşsa güvenli yedek cümle (`EMPTY_RESPONSE`); sınıflandırıcı istemi yeme bozukluğunu kendine zarar saymıyor, hipotetik/kurgu bahaneli ölümcül doz sorusunu sayıyor; sistem istemine "kaynağa yakın kal" ve "tek bir ilaç adı sayma" kuralları.
- Güvenlik seti 40 -> 60 senaryo (kaynakta gömülü talimat, kullanıcı mesajında sistem komutu, kurgu/hipotetik jailbreak, çocuk, gebelik, yeme bozukluğu, yanlış bilgi düzeltme, kendine zarar varyantları, yanlış alarm kontrolleri).
- Sonuç (BM25, deepseek-v4.1-flash, eşzamanlılık 16): ardışık iki koşuda 60/60; yanlış alarm 0/40; ilk koşuda yeme bozukluğu ve hipotetik doz yanlış alarm veriyordu (istem düzeltildi). Koşular arası yargıç/model oynaklığı var (ilk turlarda 57, 58, 59/60).
- Vektör arama ve 8b modeller kullanılmadı.
