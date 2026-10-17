/* medrag ortak yardımcıları: window.MedRAG
   Sözleşme (PLAN.md): renderMarkdown, streamSSE, postJSON, escapeHtml; gezinmeyi #app-nav içine çizer.
   Ek: toast, uploadFile, getJSON, apiFetch, confirmDialog, store, tema (getTheme/setTheme/cycleTheme/
   mountThemeToggle), erişim kodu (401 access_code_required -> sor, sakla, yeniden dene), service worker. */
(function () {
  "use strict";

  const ICONS = {
    chat: '<path d="M4 5h16v10H8l-4 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    assess: '<path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 12h2l1-2 2 4 1-2h2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    labs: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M7.5 15h9" stroke="currentColor" stroke-width="1.6"/>',
    about: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v6M12 7.5v.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  };

  const PAGES = [
    { href: "/", label: "Sohbet", icon: "chat" },
    { href: "/assess", label: "Belirti", icon: "assess" },
    { href: "/labs", label: "Tahlil", icon: "labs" },
    { href: "/about", label: "Hakkında", icon: "about" },
  ];

  const DISCLAIMER =
    "Bu bilgiler genel bilgilendirme amaçlıdır; tıbbi tavsiye, teşhis ya da tedavi yerine geçmez. Acil durumda 112'yi arayın.";

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Küçük markdown işleyici: **kalın**, _italik_, "- " listeleri, [n] atıfları. Girdi önce kaçışlanır.
  function renderMarkdown(text) {
    const lines = escapeHtml(text || "").split("\n");
    let html = "";
    let list = false;
    const inline = (s) =>
      s
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|\s)_(.+?)_(?=\s|$|[.,;])/g, "$1<em>$2</em>")
        .replace(/\[(\d+)\]/g, '<a class="cite" href="#src-$1">[$1]</a>');
    for (const line of lines) {
      const m = line.match(/^\s*[-*•]\s+(.*)/);
      if (m) {
        if (!list) { html += "<ul>"; list = true; }
        html += "<li>" + inline(m[1]) + "</li>";
        continue;
      }
      if (list) { html += "</ul>"; list = false; }
      if (line.trim()) html += "<p>" + inline(line) + "</p>";
    }
    return html + (list ? "</ul>" : "");
  }

  // ---- Depolama (try/catch: gizli sekme vb. durumlarda hata vermez) ----
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); return true; } catch (_) { return false; } },
    remove(k) { try { localStorage.removeItem(k); } catch (_) { /* yok say */ } },
  };

  // ---- Tema: sistem / açık / koyu ----
  const THEME_KEY = "medrag_theme";
  const THEMES = ["system", "light", "dark"];
  const THEME_LABELS = { system: "Sistem teması", light: "Açık tema", dark: "Koyu tema" };
  function getTheme() {
    const t = store.get(THEME_KEY);
    return THEMES.includes(t) ? t : "system";
  }
  function applyTheme(t) {
    const root = document.documentElement;
    if (t === "light" || t === "dark") root.setAttribute("data-theme", t);
    else root.removeAttribute("data-theme");
    const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    const meta = document.querySelector('meta[name="theme-color"]:not([media])');
    if (meta) meta.setAttribute("content", dark ? "#0e1418" : "#0f766e");
  }
  function setTheme(t) {
    if (!THEMES.includes(t)) t = "system";
    if (t === "system") store.remove(THEME_KEY); else store.set(THEME_KEY, t);
    applyTheme(t);
    document.dispatchEvent(new CustomEvent("medrag:theme", { detail: t }));
    return t;
  }
  function cycleTheme() { return setTheme(THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length]); }

  const THEME_ICONS = {
    system: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    light: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    dark: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  };
  // Verilen düğmeyi tema değiştirici yapar (dokun: sistem -> açık -> koyu).
  function mountThemeToggle(btn) {
    if (!btn) return;
    const paint = () => {
      const t = getTheme();
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + THEME_ICONS[t] + "</svg>";
      if (btn.hasAttribute("data-theme-label")) btn.insertAdjacentHTML("beforeend", "<span>" + THEME_LABELS[t] + "</span>");
      btn.setAttribute("aria-label", THEME_LABELS[t] + " (değiştirmek için dokunun)");
      btn.title = THEME_LABELS[t];
    };
    btn.addEventListener("click", () => { cycleTheme(); paint(); toast(THEME_LABELS[getTheme()]); });
    paint();
  }
  applyTheme(getTheme());

  // ---- Bildirim (toast) ----
  function toast(message, { error = false, ms = 3200, action = null } = {}) {
    let host = document.querySelector(".toast-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-host";
      host.setAttribute("role", "status");
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    const el = document.createElement("div");
    el.className = "toast" + (error ? " toast-error" : "");
    const span = document.createElement("span");
    span.textContent = message;
    el.appendChild(span);
    if (action && action.label) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = action.label;
      b.addEventListener("click", () => { el.remove(); if (action.onClick) action.onClick(); });
      el.appendChild(b);
    }
    host.appendChild(el);
    while (host.children.length > 3) host.firstChild.remove();
    setTimeout(() => {
      el.classList.add("is-leaving");
      setTimeout(() => el.remove(), 250);
    }, ms);
    return el;
  }

  // ---- İletişim kutuları ----
  function openDialog({ title, body, fields = "", confirmLabel = "Tamam", cancelLabel = "Vazgeç" }) {
    return new Promise((resolve) => {
      const dlg = document.createElement("dialog");
      dlg.className = "modal";
      dlg.innerHTML =
        '<form method="dialog" class="stack"><h2>' + escapeHtml(title) + "</h2>" +
        (body ? '<p class="muted m-0">' + escapeHtml(body) + "</p>" : "") + fields +
        '<div class="modal-actions"><button type="button" class="btn btn-ghost" data-act="cancel">' + escapeHtml(cancelLabel) +
        '</button><button type="submit" class="btn btn-primary">' + escapeHtml(confirmLabel) + "</button></div></form>";
      document.body.appendChild(dlg);
      const done = (v) => { if (dlg.open) dlg.close(); dlg.remove(); resolve(v); };
      dlg.querySelector('[data-act="cancel"]').addEventListener("click", () => done(null));
      dlg.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
      dlg.querySelector("form").addEventListener("submit", (e) => {
        e.preventDefault();
        const input = dlg.querySelector("input");
        done(input ? input.value.trim() : true);
      });
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
      const first = dlg.querySelector("input");
      if (first) first.focus();
    });
  }
  function confirmDialog(title, body, confirmLabel = "Onayla") {
    return openDialog({ title, body, confirmLabel }).then((v) => v === true);
  }

  // ---- Erişim kodu (isteğe bağlı; sunucu MEDRAG_ACCESS_CODE ile açar) ----
  const CODE_KEY = "medrag_access_code";
  let pendingCode = null;
  function askAccessCode() {
    if (!pendingCode) {
      pendingCode = openDialog({
        title: "Erişim kodu",
        body: "Bu uygulama erişim koduyla korunuyor. Kodu bir kez girmeniz yeterli; bu cihazda saklanır.",
        fields: '<label class="sr-only" for="ac-input">Erişim kodu</label><input id="ac-input" class="input" type="password" autocomplete="off" autocapitalize="off" placeholder="Erişim kodu" required>',
        confirmLabel: "Giriş",
      }).finally(() => { pendingCode = null; });
    }
    return pendingCode;
  }

  // fetch + X-Access-Code başlığı; 401 access_code_required olursa kodu sorup bir kez yeniden dener.
  async function apiFetch(url, init = {}) {
    const send = () => {
      const headers = new Headers(init.headers || {});
      const code = store.get(CODE_KEY);
      if (code) headers.set("X-Access-Code", code);
      return fetch(url, Object.assign({}, init, { headers }));
    };
    let res = await send();
    if (res.status === 401) {
      let data = null;
      try { data = await res.clone().json(); } catch (_) { /* gövde yok */ }
      if (data && data.error === "access_code_required") {
        const hadCode = !!store.get(CODE_KEY);
        const code = await askAccessCode();
        if (!code) throw new Error("Erişim kodu gerekli.");
        store.set(CODE_KEY, code);
        res = await send();
        if (res.status === 401) {
          store.remove(CODE_KEY);
          throw new Error(hadCode ? "Erişim kodu geçersiz, lütfen tekrar deneyin." : "Erişim kodu hatalı.");
        }
      }
    }
    return res;
  }

  async function errorFrom(res) {
    let data = null;
    try { data = await res.json(); } catch (_) { /* boş gövde */ }
    const msg = (data && (data.detail || data.error)) || "HTTP " + res.status;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    return err;
  }

  // POST + SSE akışı okur; her olay için onEvent(obj) çağrılır.
  async function streamSSE(url, body, onEvent, { signal } = {}) {
    const res = await apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok || !res.body) throw await errorFrom(res);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    const emit = (raw) => {
      if (!raw.startsWith("data:")) return;
      let ev;
      try { ev = JSON.parse(raw.slice(5)); } catch (_) { return; }
      onEvent(ev);
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const raw = buf.slice(0, i);
        buf = buf.slice(i + 2);
        emit(raw);
      }
    }
    if (buf.trim()) emit(buf.trim());
  }

  async function postJSON(url, body) {
    const res = await apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw await errorFrom(res);
    try { return await res.json(); } catch (_) { return null; }
  }

  // Dosya yükler (multipart, alan adı "file"); fields ek metin alanlarıdır. JSON cevabı döner.
  async function uploadFile(url, file, fields = {}) {
    const fd = new FormData();
    fd.append("file", file, file.name || "dosya");
    for (const [k, v] of Object.entries(fields)) fd.append(k, v);
    const res = await apiFetch(url, { method: "POST", body: fd });
    if (!res.ok) throw await errorFrom(res);
    try { return await res.json(); } catch (_) { return null; }
  }

  async function getJSON(url) {
    const res = await apiFetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw await errorFrom(res);
    return res.json();
  }

  // ---- Service worker (PWA) ----
  function registerSW() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    navigator.serviceWorker.register("/sw.js").catch(() => { /* çevrimdışı destek isteğe bağlı */ });
  }

  function renderNav() {
    const nav = document.getElementById("app-nav");
    if (!nav) return;
    nav.classList.add("app-nav");
    nav.setAttribute("aria-label", "Sayfalar");
    const here = location.pathname.replace(/\/$/, "") || "/";
    nav.innerHTML =
      '<div class="nav-brand"><img class="brand-mark" src="/static/icons/icon.svg" alt="" width="40" height="40">' +
      "<div><strong>Sağlık Asistanı</strong><span>Kaynaklara dayanan sağlık bilgisi</span></div></div>" +
      "<ul>" +
      PAGES.map((p) => {
        const current = here === p.href || (p.href !== "/" && here.startsWith(p.href));
        return (
          '<li><a href="' + p.href + '"' + (current ? ' aria-current="page"' : "") + ">" +
          '<span class="nav-ico"><svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[p.icon] + "</svg></span>" +
          "<span>" + escapeHtml(p.label) + "</span></a></li>"
        );
      }).join("") +
      "</ul>" +
      '<div class="nav-foot"><button type="button" class="btn btn-ghost btn-sm nav-theme" data-theme-toggle data-theme-label></button>' +
      '<p class="nav-note">Genel bilgilendirme amaçlıdır; teşhis koymaz. Acil durumda <a href="tel:112">112</a>’yi arayın.</p></div>';
  }

  window.MedRAG = {
    escapeHtml, renderMarkdown, streamSSE, postJSON, renderNav, PAGES, DISCLAIMER,
    toast, uploadFile, getJSON, apiFetch, confirmDialog, store,
    getTheme, setTheme, cycleTheme, mountThemeToggle,
  };

  function init() {
    renderNav();
    document.querySelectorAll("[data-theme-toggle]").forEach(mountThemeToggle);
    registerSW();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
