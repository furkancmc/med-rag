"""Platform tanı komutu: ses tanıma (qwen3-asr) ham cevabını yazdırır. Gerçek API anahtarı gerekir.

Kullanım: python -m medrag.eval platform [--wav ses.wav] [--text "Başım ağrıyor"]
`--wav` verilmezse `espeak-ng` ile kısa bir Türkçe konuşma üretilir (CI'da apt ile kurulur).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from medrag.config import get_settings
from medrag.speech import SpeechClient, parse_transcript


def register(sub) -> None:
    p = sub.add_parser("platform", help="ses tanıma uç noktasını gerçek API ile dene")
    p.add_argument("--wav", type=Path, help="hazır WAV/MP3/OGG dosyası")
    p.add_argument("--text", default="Merhaba, bugün başım ağrıyor ve ateşim var.")
    p.set_defaults(func=cmd_platform)


def synthesize(text: str, out: Path) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    subprocess.run([exe, "-v", "tr", "-w", str(out), text], check=True, capture_output=True)
    return out.is_file() and out.stat().st_size > 44


def cmd_platform(args) -> None:
    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        wav = args.wav or Path(tmp) / "ses.wav"
        if not args.wav and not synthesize(args.text, wav):
            raise SystemExit("espeak-ng bulunamadı; --wav ile bir ses dosyası verin.")
        data = wav.read_bytes()
    ctype = "audio/wav" if data[:4] == b"RIFF" else "audio/mpeg"
    print(f"ses boyutu: {len(data)} bayt, model: {settings.speech_model}")
    failed = True
    for mode in ("transcriptions", "chat"):
        client = SpeechClient(
            settings.speech_api_url, settings.speech_model, settings.speech_language, mode,
            settings.speech_timeout,
        )
        try:
            if mode == "transcriptions":
                raw = client._transcriptions(data, ctype)
            else:
                raw = client._chat(data, ctype)
            print(f"[{mode}] ham cevap: {raw[:500]!r}")
            print(f"[{mode}] ayrıştırılan metin: {parse_transcript(raw)!r}")
            failed = False
        except Exception as e:  # noqa: BLE001 - her yolun sonucunu raporla
            kind = type(e).__name__
            print(f"[{mode}] başarısız: {kind}: {e!r}")
    raise SystemExit(1 if failed else 0)
