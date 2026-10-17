/* Sohbet sayfası: akış, kaynaklar, doğrulama, geri bildirim, ses, kalıcı geçmiş. */
(function () {
  "use strict";
  const M = window.MedRAG;
  const $ = (id) => document.getElementById(id);
  const chatEl = $("chat"), appEl = document.querySelector(".chat-app");
  const form = $("form"), input = $("input"), sendBtn = $("send"), micBtn = $("mic"), newBtn = $("new-chat");
  const STORE_KEY = "medrag_chat_v1";
  const MAX_SAVED = 40;
  const HINTS = [
    "Diyabetin belirtileri nelerdir?",
    "Yüksek tansiyon için neler yapılabilir?",
    "Migren ile baş ağrısı arasındaki fark nedir?",
    "Demir eksikliği anemisi nasıl anlaşılır?",
  ];
  const ICON = {
    up: '<path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h6a2 2 0 0 1 2 2.3l-1.2 6.4A2 2 0 0 1 17.8 20H7"/>',
    down: '<path d="M7 13V4H4v9zM7 13l4 8a2 2 0 0 0 2-2v-4h6a2 2 0 0 0 2-2.3L19.8 6.3A2 2 0 0 0 17.8 4H7"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    speak: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
    check: '<path d="M5 12l5 5 9-10"/>',
  };
  const svg = (name) =>
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICON[name] + "</svg>";

  let messages = []; // {role, text, emergency?, sources?, verification?, rating?, error?, question?}
  let busy = false, abortCtl = null;

  // ---- Kalıcılık ----
  function save() {
    const slim = messages.slice(-MAX_SAVED).map((m) => {
      const c = Object.assign({}, m);
      if (c.sources) c.sources = c.sources.map((s) => { const x = Object.assign({}, s); delete x.text; return x; });
      return c;
    });
    M.store.set(STORE_KEY, JSON.stringify(slim));
  }
  function load() {
    try {
      const v = JSON.parse(M.store.get(STORE_KEY) || "[]");
      return Array.isArray(v) ? v.filter((m) => m && (m.role === "user" || m.role === "assistant")) : [];
    } catch (_) { return []; }
  }

  // ---- Doğrulama işaretleri ----
  const MARK_A = "", MARK_B = "";
  function markUnsupported(text, unsupported) {
    let out = text;
    for (const u of unsupported || []) {
      const s = (u.sentence || "").trim();
      if (!s || s.includes("\n")) continue;
      const i = out.indexOf(s);
      if (i >= 0 && !out.slice(0, i).includes(MARK_A + "\u0000")) out = out.slice(0, i) + MARK_A + s + MARK_B + out.slice(i + s.length);
    }
    return out;
  }
  function renderAnswer(m) {
    let html = M.renderMarkdown(markUnsupported(m.text || "", m.verification && m.verification.unsupported));
    html = html.split(MARK_A).join('<span class="unverified" tabindex="0" title="Kaynakta doğrulanamadı">').split(MARK_B).join("</span>");
    return html;
  }

  // ---- Görünüm ----
  function sourceCard(s) {
    const date = s.published || s.updated || s.date;
    const got = s.retrieved || s.retrieved_at || s.fetched;
    const meta = [];
    if (s.source) meta.push('<span class="badge badge-accent">' + M.escapeHtml(s.source) + "</span>");
    if (s.license) meta.push('<span class="badge badge-neutral">' + M.escapeHtml(s.license) + "</span>");
    if (date) meta.push('<span class="badge badge-neutral">Yayın: ' + M.escapeHtml(String(date).slice(0, 10)) + "</span>");
    if (got) meta.push('<span class="badge badge-neutral">Çekilme: ' + M.escapeHtml(String(got).slice(0, 10)) + "</span>");
    const url = /^https?:\/\//.test(s.url || "") ? s.url : "";
    const title = M.escapeHtml(s.title || "Kaynak") + (s.section ? " · " + M.escapeHtml(s.section) : "");
    return (
      '<li class="src-card" data-n="' + Number(s.n) + '"><div class="src-head"><span class="src-n">' + Number(s.n) + "</span>" +
      '<div class="grow"><div class="src-title">' +
      (url ? '<a href="' + M.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' + title + "</a>" : title) +
      '</div><div class="src-meta">' + meta.join("") + "</div></div></div>" +
      (s.snippet ? '<p class="src-snippet">' + M.escapeHtml(s.snippet) + "</p>" : "") + "</li>"
    );
  }

  function actionBtn(act, label, icon, pressed) {
    return (
      '<button type="button" class="btn btn-icon btn-icon-sm" data-act="' + act + '" aria-label="' + label + '" title="' + label + '"' +
      (pressed === undefined ? "" : ' aria-pressed="' + pressed + '"') + ">" + svg(icon) + "</button>"
    );
  }

  function buildMessage(m, i) {
    const el = document.createElement("article");
    el.className = "msg " + (m.role === "user" ? "user" : "bot");
    el.dataset.i = i;
    if (m.role === "user") {
      el.innerHTML = '<div class="bubble"></div>';
      el.querySelector(".bubble").textContent = m.text;
      return el;
    }
    const parts = [];
    if (m.emergency) {
      parts.push(
        '<div class="alert alert-danger emergency-banner" role="alert"><div class="alert-row">' + svg("warn") +
        '<div class="prose">' + M.renderMarkdown(m.emergency) + "</div></div>" +
        '<a class="btn emergency-call btn-block" href="tel:112">' + svg("phone") + "112'yi ara</a></div>"
      );
    }
    parts.push('<div class="bubble prose' + (m.error ? " is-error" : "") + '"></div>');
    parts.push('<div class="verify" hidden></div>');
    parts.push('<details class="sources" hidden></details>');
    parts.push('<div class="msg-actions" hidden></div>');
    el.innerHTML = parts.join("");
    refresh(el, m);
    return el;
  }

  // Bir bot mesajının dinamik parçalarını durumdan yeniden çizer.
  function refresh(el, m, streaming) {
    const bubble = el.querySelector(".bubble");
    if (streaming && !m.text) bubble.innerHTML = '<div class="skeleton-line w-80"></div><div class="skeleton-line w-60"></div>';
    else if (!m.text && m.emergency) bubble.hidden = true;
    else { bubble.hidden = false; bubble.innerHTML = renderAnswer(m); }
    bubble.classList.toggle("is-error", !!m.error);
    bubble.classList.toggle("is-streaming", !!streaming && !!m.text);

    const v = el.querySelector(".verify");
    const ver = m.verification;
    if (ver && !streaming) {
      v.hidden = false;
      if (ver.unsupported && ver.unsupported.length) {
        v.innerHTML =
          '<div class="verify-note alert alert-warn"><strong>Kaynakta doğrulanamadı</strong>' +
          "<ul>" + ver.unsupported.map((u) => "<li>“" + M.escapeHtml(u.sentence || "") + "”" + (u.reason ? " — " + M.escapeHtml(u.reason) : "") + "</li>").join("") +
          "</ul></div>";
      } else if (ver.checked > 0) {
        v.innerHTML = '<span class="badge badge-ok">' + svg("check").replace("<svg", '<svg width="14" height="14"') + "Kaynaklarla kontrol edildi</span>";
      } else v.hidden = true;
    } else v.hidden = true;

    const src = el.querySelector(".sources");
    if (m.sources && m.sources.length) {
      src.hidden = false;
      const wasOpen = src.open;
      src.innerHTML = "<summary>Kaynaklar (" + m.sources.length + ")</summary><ul class=\"source-list\">" + m.sources.map(sourceCard).join("") + "</ul>";
      src.open = wasOpen || matchMedia("(min-width: 1024px)").matches;
    } else src.hidden = true;

    const act = el.querySelector(".msg-actions");
    if (!streaming && m.text && !m.error) {
      act.hidden = false;
      act.innerHTML =
        actionBtn("up", "Yararlı", "up", m.rating === 1) + actionBtn("down", "Yararlı değil", "down", m.rating === -1) +
        actionBtn("copy", "Cevabı kopyala", "copy") +
        ("speechSynthesis" in window ? actionBtn("speak", "Sesli oku", "speak", false) : "");
    } else act.hidden = true;
  }

  function scrollToEnd(smooth) {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }
  function updateChrome() {
    const has = messages.length > 0;
    appEl.classList.toggle("has-messages", has);
    newBtn.hidden = !has;
  }
  function renderAll() {
    chatEl.innerHTML = "";
    messages.forEach((m, i) => chatEl.appendChild(buildMessage(m, i)));
    updateChrome();
  }

  // ---- Soru sorma ----
  function historyForApi() {
    return messages
      .filter((m) => m.text && !m.error)
      .slice(-12)
      .map((m) => ({ role: m.role, content: m.text.slice(0, 4000) }));
  }

  async function ask(question) {
    if (busy) return;
    const history = historyForApi();
    messages.push({ role: "user", text: question });
    const bot = { role: "assistant", text: "", question };
    messages.push(bot);
    chatEl.appendChild(buildMessage(messages[messages.length - 2], messages.length - 2));
    let el = buildMessage(bot, messages.length - 1);
    chatEl.appendChild(el);
    updateChrome();
    setBusy(true);
    refresh(el, bot, true);
    scrollToEnd();
    abortCtl = new AbortController();
    let pending = false, finished = false;
    const paint = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; if (finished) return; refresh(el, bot, true); scrollToEnd(); });
    };
    try {
      await M.streamSSE("/chat", { message: question, history }, (ev) => {
        if (ev.type === "emergency") {
          bot.emergency = ev.text || "Bu belirtiler acil olabilir. Lütfen hemen 112'yi arayın.";
          const fresh = buildMessage(bot, Number(el.dataset.i));
          el.replaceWith(fresh);
          el = fresh;
        } else if (ev.type === "sources") bot.sources = ev.items || [];
        else if (ev.type === "token") bot.text += ev.text || "";
        else if (ev.type === "verification") bot.verification = ev;
        else if (ev.type === "error") { bot.text = ev.text || "Bir sorun oluştu."; bot.error = true; }
        paint();
      }, { signal: abortCtl.signal });
    } catch (err) {
      if (err.name === "AbortError") {
        if (!bot.text) { bot.text = "Yanıt durduruldu."; bot.error = true; }
      } else if (!bot.text) {
        bot.text = err.message && !/^HTTP|Failed to fetch|NetworkError/.test(err.message) ? err.message : "Bağlantı sorunu oluştu, lütfen tekrar deneyin.";
        bot.error = true;
      }
    } finally {
      finished = true;
      if (!bot.text && !bot.emergency) { bot.text = "Cevap alınamadı, lütfen tekrar deneyin."; bot.error = true; }
      refresh(el, bot, false);
      save();
      setBusy(false);
      abortCtl = null;
      scrollToEnd(true);
    }
  }
  function setBusy(b) {
    busy = b;
    chatEl.setAttribute("aria-busy", b ? "true" : "false");
    sendBtn.setAttribute("aria-label", b ? "Durdur" : "Gönder");
    sendBtn.innerHTML = b
      ? svg("stop")
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="22" height="22" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
    sendBtn.disabled = !b && !input.value.trim();
  }

  // ---- Form ----
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
    if (!busy) sendBtn.disabled = !input.value.trim();
  }
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) { if (abortCtl) abortCtl.abort(); return; }
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    autoGrow();
    ask(q);
  });
  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(hover: hover)").matches) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ---- Mesaj eylemleri (olay delegasyonu) ----
  let speaking = null;
  function plainText(md) {
    return md.replace(/\*\*(.+?)\*\*/g, "$1").replace(/(^|\s)_(.+?)_(?=\s|$|[.,;])/g, "$1$2").replace(/\[\d+\]/g, "").replace(/^\s*[-*•]\s+/gm, "");
  }
  function stopSpeaking() {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    if (speaking) { speaking.setAttribute("aria-pressed", "false"); speaking.innerHTML = svg("speak"); speaking.setAttribute("aria-label", "Sesli oku"); }
    speaking = null;
  }
  function speak(text, btn) {
    stopSpeaking();
    speaking = btn;
    btn.setAttribute("aria-pressed", "true");
    btn.innerHTML = svg("stop");
    btn.setAttribute("aria-label", "Okumayı durdur");
    const voice = (speechSynthesis.getVoices() || []).find((v) => /^tr/i.test(v.lang));
    const chunks = plainText(text).match(/[^.!?\n]+[.!?]?\s*/g) || [text];
    chunks.forEach((c, idx) => {
      if (!c.trim()) return;
      const u = new SpeechSynthesisUtterance(c.trim());
      u.lang = "tr-TR";
      if (voice) u.voice = voice;
      if (idx === chunks.length - 1) u.onend = () => { if (speaking === btn) stopSpeaking(); };
      u.onerror = () => { if (speaking === btn) stopSpeaking(); };
      speechSynthesis.speak(u);
    });
  }
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* eski tarayıcı */ }
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { /* yok say */ }
    ta.remove();
    return ok;
  }
  async function sendFeedback(m, rating) {
    try {
      await M.postJSON("/api/feedback", { rating, page: "chat", question: m.question || "", answer: (m.text || "").slice(0, 4000) });
      M.toast("Geri bildiriminiz için teşekkürler");
    } catch (err) {
      if (err.status === 404) M.toast("Teşekkürler");
      else M.toast("Geri bildirim gönderilemedi", { error: true });
    }
  }

  chatEl.addEventListener("click", (e) => {
    const cite = e.target.closest("a.cite");
    if (cite) {
      e.preventDefault();
      const msg = cite.closest(".msg");
      const n = cite.getAttribute("href").replace("#src-", "");
      const card = msg && msg.querySelector('.src-card[data-n="' + n + '"]');
      if (card) {
        card.closest("details").open = true;
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.remove("is-flash"); void card.offsetWidth; card.classList.add("is-flash");
      }
      return;
    }
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const msgEl = btn.closest(".msg");
    const m = messages[Number(msgEl.dataset.i)];
    if (!m) return;
    const act = btn.dataset.act;
    if (act === "up" || act === "down") {
      const rating = act === "up" ? 1 : -1;
      if (m.rating === rating) return;
      m.rating = rating;
      save();
      refresh(msgEl, m, false);
      sendFeedback(m, rating);
    } else if (act === "copy") {
      copyText(m.text).then((ok) => M.toast(ok ? "Kopyalandı" : "Kopyalanamadı", { error: !ok }));
    } else if (act === "speak") {
      if (speaking === btn) stopSpeaking(); else speak(m.text, btn);
    }
  });

  // ---- Yeni sohbet ----
  newBtn.addEventListener("click", async () => {
    if (busy && abortCtl) abortCtl.abort();
    if (!(await M.confirmDialog("Yeni sohbet", "Bu cihazdaki sohbet geçmişi silinecek.", "Sil ve başla"))) return;
    stopSpeaking();
    messages = [];
    M.store.remove(STORE_KEY);
    renderAll();
    input.focus();
  });

  // ---- Ses: kayıt -> /api/speech/transcribe, yoksa Web Speech API ----
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  let useSR = !canRecord && !!SR, recorder = null, recStream = null, recTimer = null, recog = null;

  function putText(t) {
    if (!t) { M.toast("Ses anlaşılamadı, tekrar deneyin", { error: true }); return; }
    input.value = (input.value ? input.value.trim() + " " : "") + t.trim();
    autoGrow();
    input.focus();
  }
  function micState(state) {
    micBtn.classList.toggle("is-recording", state === "rec");
    micBtn.setAttribute("aria-pressed", state === "rec" ? "true" : "false");
    micBtn.disabled = state === "busy";
    micBtn.setAttribute("aria-label", state === "rec" ? "Kaydı bitir" : "Sesle sor");
    micBtn.innerHTML = state === "busy"
      ? '<span class="spinner" aria-hidden="true"></span>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="22" height="22" aria-hidden="true">' +
        (state === "rec" ? '<rect x="7" y="7" width="10" height="10" rx="2"/>' : '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>') + "</svg>";
  }
  function startSR() {
    recog = new SR();
    recog.lang = "tr-TR";
    recog.interimResults = false;
    recog.onresult = (ev) => putText(Array.from(ev.results).map((r) => r[0].transcript).join(" "));
    recog.onerror = (ev) => { M.toast(ev.error === "not-allowed" ? "Mikrofon izni gerekli" : "Ses tanıma çalışmadı", { error: true }); };
    recog.onend = () => { micState("idle"); recog = null; };
    micState("rec");
    recog.start();
  }
  async function startRecording() {
    try {
      recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (_) {
      M.toast("Mikrofon izni verilmedi", { error: true });
      return;
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
    recorder = new MediaRecorder(recStream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = async () => {
      clearTimeout(recTimer);
      recStream.getTracks().forEach((t) => t.stop());
      const type = recorder.mimeType || mime || "audio/webm";
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(chunks, { type });
      recorder = null;
      if (blob.size < 800) { micState("idle"); return; }
      micState("busy");
      try {
        const res = await M.uploadFile("/api/speech/transcribe", new File([blob], "ses." + ext, { type }));
        putText(res && res.text);
      } catch (err) {
        if (SR && err.status !== 401) {
          useSR = true;
          M.toast("Ses servisi kullanılamıyor; tarayıcı tanıması denenecek, tekrar dokunun", { error: true });
        } else M.toast("Ses metne çevrilemedi", { error: true });
      }
      micState("idle");
    };
    recorder.start();
    micState("rec");
    recTimer = setTimeout(() => { if (recorder && recorder.state === "recording") recorder.stop(); }, 60000);
  }
  if (canRecord || SR) {
    micBtn.hidden = false;
    micBtn.addEventListener("click", () => {
      if (recorder && recorder.state === "recording") { recorder.stop(); return; }
      if (recog) { recog.stop(); return; }
      if (useSR && SR) startSR(); else startRecording();
    });
  }

  // ---- Başlangıç ----
  for (const h of HINTS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = h;
    b.addEventListener("click", () => ask(h));
    $("hints").appendChild(b);
  }
  messages = load();
  renderAll();
  setBusy(false);
  const q = new URLSearchParams(location.search).get("q");
  if (q) {
    input.value = q.slice(0, 2000);
    history.replaceState(null, "", location.pathname);
    autoGrow();
    input.focus();
  }
  if (messages.length) requestAnimationFrame(() => scrollToEnd());
})();
