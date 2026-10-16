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

## Veri hattı

```bash
python -m medrag.ingest medlineplus              # MedlinePlus XML -> data/raw/medlineplus
python -m medrag.ingest wikipedia --lang tr      # Vikipedi -> data/raw/wikipedia/tr.jsonl
python -m medrag.ingest build                    # -> data/chunks.jsonl
```

Kendi `.txt`/`.md` dosyalarını `data/local/` altına koyarsan onlar da işlenir.
İndirme için `medlineplus.gov` ve `*.wikipedia.org` adreslerine ağ erişimi gerekir.
