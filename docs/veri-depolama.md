# Ham veri depolama (data/raw büyümesi)

Ölçüm (20.10.2026): `data/raw` çalışma ağacında ~35 MB, `.git` paketi ~20 MB. Haftalık `fetch-data.yml`
her seferinde değişen dosyaları yeniden commit'ler; geçmiş her hafta büyür.

## Seçenekler
| Seçenek | Artı | Eksi |
|---|---|---|
| Olduğu gibi (mevcut) | Dockerfile `COPY data/raw` basit, CI ek adım istemez | `.git` yıllık onlarca MB büyür |
| GitHub Release asset (önerilen) | Geçmiş büyümez; her hafta yeni `data-YYYYMMDD` release | Dockerfile/CI indirme adımı gerekir |
| Git LFS | Kod aynı kalır | Ücretsiz kota (1 GB bant/ay) Docker build'lerinde hızla dolar |

## Önerilen geçiş (kullanıcı onayıyla uygulanmalı; Docker build'i etkilediği için gözetimsiz yapılmadı)
1. `fetch-data.yml`: `git add -f data/raw` yerine `tar -czf raw.tgz data/raw` + `gh release create data-$(date +%F) raw.tgz`.
2. `Dockerfile`: `COPY data/raw` yerine build arg `RAW_URL` ile `curl -L $RAW_URL | tar -xz`.
3. `data/raw` repodan `git rm -r --cached` ile çıkarılır (geçmişi küçültmek isteniyorsa `git filter-repo`, force-push gerektirir).
4. Yedek: son release'ler 4 hafta saklanır.

Geçişe kadar mevcut düzen çalışır; veri değişmediğinde workflow commit atmaz (`git commit || exit 0`).
