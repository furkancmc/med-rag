"""Kaynak indirme sonuç raporu: günlükten sorun ayıklanabilsin diye ayrıntılı ve tek biçimli."""

from dataclasses import dataclass, field
from pathlib import Path

from .rawstore import MergeStats

MAX_LISTED = 25  # günlüğü şişirmemek için listelerde en fazla bu kadar öğe gösterilir


@dataclass
class SourceReport:
    source: str  # örn. "wikipedia-tr", "europepmc", "openfda"
    path: Path | None = None
    requested: int = 0  # istenen öğe sayısı (başlık, ilaç, konu, bilgi sayfası)
    fetched: int = 0  # belge üreten, başarıyla alınan öğe sayısı
    documents: int = 0  # ham dosyaya yazılan toplam satır (öncekilerle birlikte)
    missing: list[str] = field(default_factory=list)  # kaynakta bulunamayan (hata değil)
    skipped: list[str] = field(default_factory=list)  # süzülen (lisans, kısa özet vb.) ve nedeni
    failed: list[tuple[str, str]] = field(default_factory=list)  # (öğe, hata özeti)
    samples: list[str] = field(default_factory=list)  # örnek başlıklar
    stats: MergeStats | None = None
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0
    fatal: str = ""  # kaynağın tamamını durduran hata

    @property
    def ok(self) -> bool:
        """En az bir belge alındıysa ve kaynak topyekûn çökmediyse başarılı."""
        return not self.fatal and self.fetched > 0

    def render(self) -> str:
        status = "TAMAM" if self.ok else "HATA"
        head = (
            f"== {self.source}: {status} == "
            f"istenen {self.requested}, alınan {self.fetched}, ham dosyadaki belge {self.documents}, "
            f"bulunamayan {len(self.missing)}, süzülen {len(self.skipped)}, hata {len(self.failed)} "
            f"({self.seconds:.0f} sn)"
        )
        lines = [head]
        if self.stats:
            lines.append("  dosya: " + self.stats.summary() + (", YAZILDI" if self.stats.written else ", değişmedi"))
        if self.fatal:
            lines.append(f"  KRİTİK HATA: {self.fatal}")
        lines += [f"  not: {n}" for n in self.notes]
        for label, items in (
            ("bulunamayanlar", [str(m) for m in self.missing]),
            ("süzülenler", [str(s) for s in self.skipped]),
            ("hatalar", [f"{item} -> {err}" for item, err in self.failed]),
            ("örnek başlıklar", self.samples),
        ):
            if items:
                more = f" (+{len(items) - MAX_LISTED} daha)" if len(items) > MAX_LISTED else ""
                lines.append(f"  {label}: " + "; ".join(items[:MAX_LISTED]) + more)
        return "\n".join(lines)
