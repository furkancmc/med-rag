(function () {
  "use strict";
  const M = window.MedRAG, esc = M.escapeHtml;
  document.getElementById("disclaimer").textContent = M.DISCLAIMER;

  const FALLBACK = [
    { source: "MedlinePlus", license: "Kamu malı (ABD Ulusal Tıp Kütüphanesi)" },
    { source: "Vikipedi", license: "CC BY-SA 4.0" },
  ];
  function renderSources(list, withCounts) {
    const rows = list.map((s) => {
      const counts = withCounts && s.documents != null
        ? s.documents + " belge" + (s.chunks != null ? " · " + s.chunks + " parça" : "") : "";
      return '<li class="list-row"><div class="list-row-main"><div class="list-row-title">' + esc(s.source) +
        '</div><div class="list-row-sub">' + esc(s.license || "") + "</div></div>" +
        (counts ? '<div class="list-row-end">' + esc(counts) + "</div>" : "") + "</li>";
    });
    document.getElementById("sources-box").innerHTML = '<ul class="list">' + rows.join("") + "</ul>";
  }

  const LABELS = { recall_at_1: "Recall@1", recall_at_5: "Recall@5", mrr: "MRR", queries: "Soru sayısı", safety: "Güvenlik senaryosu", safety_passed: "Geçen senaryo", questions: "Soru sayısı" };
  function fmt(v) { return typeof v === "number" && v <= 1 && v >= 0 && !Number.isInteger(v) ? (v * 100).toFixed(1) + "%" : String(v); }
  function renderEval(ev) {
    const items = Object.entries(ev || {}).filter(([, v]) => ["number", "string"].includes(typeof v));
    if (!items.length) return;
    document.getElementById("eval-box").innerHTML = '<div class="stat-row">' + items.slice(0, 8).map(([k, v]) =>
      '<div class="stat"><b>' + esc(fmt(v)) + '</b><span class="muted small">' + esc(LABELS[k] || k.replace(/_/g, " ")) + "</span></div>").join("") + "</div>";
    document.getElementById("eval-section").hidden = false;
  }

  M.getJSON("/api/meta/info").then((info) => {
    const src = info && Array.isArray(info.sources) && info.sources.length ? info.sources : null;
    if (src) renderSources(src, true); else renderSources(FALLBACK, false);
    if (info && info.version) document.getElementById("version").textContent = info.version;
    if (info && info.eval) renderEval(info.eval);
  }).catch(() => renderSources(FALLBACK, false));

  document.getElementById("clear-local").addEventListener("click", async () => {
    if (!(await M.confirmDialog("Sohbeti sil", "Bu cihazdaki sohbet geçmişi silinecek.", "Sil"))) return;
    M.store.remove("medrag_chat_v1");
    M.toast("Sohbet geçmişi silindi");
  });
})();
