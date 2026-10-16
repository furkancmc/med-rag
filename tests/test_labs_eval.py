import argparse

import pytest

from medrag.eval import labs_cli


def test_sanity_cases_pass(capsys):
    labs_cli.cmd_sanity(argparse.Namespace())
    assert "14/14" in capsys.readouterr().out


def test_score_counts_correct_values():
    rows = [{"test_id": "hemoglobin", "value": "11.2", "unit": "g/dL"},
            {"test_id": "tsh", "value": "9", "unit": "mIU/L"}]
    ok_v, ok_u, n = labs_cli.score(rows)
    assert (ok_v, ok_u, n) == (1, 2, 2)


def test_registered():
    p = argparse.ArgumentParser()
    labs_cli.register(p.add_subparsers())
    assert p.parse_args(["labs-ocr"]).models.startswith("deepseek-ocr-2")


def test_make_report_needs_pillow():
    pytest.importorskip("PIL")
    assert labs_cli.make_report("noisy")[:8] == b"\x89PNG\r\n\x1a\n"
