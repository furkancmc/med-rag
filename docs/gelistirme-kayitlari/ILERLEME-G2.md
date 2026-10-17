# G2: Masaüstü arayüzü

- Kenar çubuğu: `common.js` `renderNav` marka, bağlantılar, tema düğmesi (`data-theme-label`) ve uyarı notunu çizer;
  mobilde `.nav-brand`/`.nav-foot` gizli, alt gezinme aynen duruyor. "Değerlendir" etiketi "Belirti" oldu.
- CSS: `@media (min-width: 1024px)` blokları `base.css` (kabuk, belirti, tahlil, hakkında), `chat.css`, `about.css`.
- HTML: `index.html` (iki bölüm başlığı), `about.html` (`about-page`, `col-half`), `assess.html`/`labs.html` yalnızca sınıf
  (`app-assess`, `app-labs`, `pane-in`, `pane-out`). JS mantığı ve metinlere dokunulmadı; `chat.js`te tek satır:
  masaüstünde kaynak listesi açık gelir.
- Doğrulama: Edge, 1440x900 / 1024x768 / 390x844, açık+koyu, 5 sayfa akışı: konsol hatası ve yatay kaydırma yok.
  Belirti API yanıtı Playwright ile sahtelendi (dev sunucu `/api/assess/*` sahte vermiyor). 421 test, ruff temiz.
- Görüntüler: `docs/screens/ui-pc/`.
- Bilinen: 1024 px'te yazma kutusu kısa yükseklikte içeriğin üstüne biner (kaydırınca görünür); assess.html'in satır içi
  `.list` kuralı mobilde de iç içe kenarlık üretiyor, yalnızca masaüstünde düzeltildi.
