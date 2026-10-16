import json

import pytest

from medrag.ingest.build import build_chunks

ROW = {
    "id": "1",
    "language": "English",
    "title": "Flu",
    "url": "https://x/flu",
    "summary_html": "<p>Flu is an infection.</p>",
}


def test_build_chunks_from_raw_and_local(tmp_path):
    (tmp_path / "raw" / "medlineplus").mkdir(parents=True)
    (tmp_path / "raw" / "medlineplus" / "topics.jsonl").write_text(json.dumps(ROW))
    (tmp_path / "raw" / "wikipedia").mkdir()
    page = {"pageid": 2, "title": "Grip", "extract": "Grip bir hastalıktır."}
    (tmp_path / "raw" / "wikipedia" / "tr.jsonl").write_text(json.dumps(page, ensure_ascii=False))
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "not.txt").write_text("Kendi notum", encoding="utf-8")

    assert build_chunks(tmp_path) == 3
    rows = [json.loads(x) for x in (tmp_path / "chunks.jsonl").read_text().splitlines()]
    assert {r["source"] for r in rows} == {"medlineplus", "wikipedia", "local"}


def test_build_fails_without_data(tmp_path):
    with pytest.raises(RuntimeError):
        build_chunks(tmp_path)
