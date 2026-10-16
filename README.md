# medrag

Açık tıbbi dokümanlar üzerinde çalışan, Türkçe sohbet eden bir RAG asistanı.
Cevapları Claude üretir, kaynakları gösterir. Teşhis koymaz, doktorun yerini tutmaz.

## Durum

Yol haritası `PLAN.md` dosyasında. Şu an aşama 1 (iskelet) tamam.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # ANTHROPIC_API_KEY'i doldur
pytest
ruff check .
```
