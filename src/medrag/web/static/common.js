/* medrag ortak yardımcıları: window.MedRAG
   Sözleşme (PLAN.md): renderMarkdown, streamSSE, postJSON, escapeHtml; gezinmeyi #app-nav içine çizer. */
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
    { href: "/assess", label: "Değerlendir", icon: "assess" },
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

  // POST + SSE akışı okur; her olay için onEvent(obj) çağrılır.
  async function streamSSE(url, body, onEvent, { signal } = {}) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const raw = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (raw.startsWith("data:")) onEvent(JSON.parse(raw.slice(5)));
      }
    }
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* boş gövde */ }
    if (!res.ok) {
      const msg = (data && (data.detail || data.error)) || "HTTP " + res.status;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  function renderNav() {
    const nav = document.getElementById("app-nav");
    if (!nav) return;
    nav.classList.add("app-nav");
    nav.setAttribute("aria-label", "Sayfalar");
    const here = location.pathname.replace(/\/$/, "") || "/";
    nav.innerHTML =
      "<ul>" +
      PAGES.map((p) => {
        const current = here === p.href || (p.href !== "/" && here.startsWith(p.href));
        return (
          '<li><a href="' + p.href + '"' + (current ? ' aria-current="page"' : "") + ">" +
          '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[p.icon] + "</svg>" +
          "<span>" + escapeHtml(p.label) + "</span></a></li>"
        );
      }).join("") +
      "</ul>";
  }

  window.MedRAG = { escapeHtml, renderMarkdown, streamSSE, postJSON, renderNav, PAGES, DISCLAIMER };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", renderNav);
  else renderNav();
})();
