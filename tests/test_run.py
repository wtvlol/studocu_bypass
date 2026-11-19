import pytest

import run


def test_presets_load():
    for name in ["default", "st2334", "gea1000", "generic-qa"]:
        assert "description" in run.load_preset(name)


def test_unknown_preset_lists_available():
    with pytest.raises(SystemExit, match="generic-qa"):
        run.load_preset("nope")


def test_cli_overrides_preset():
    args = run.parse_args(["c.json", "--marker", "Answer"])
    m = run.merged(args, {"marker": "SOLUTION", "top_content": 5}, {"marker": "X", "top_content": 0, "page_size": "a4"})
    assert m == {"marker": "Answer", "top_content": 5, "page_size": "a4"}


def test_slug():
    assert run.slug("GEA1000 Sample Paper - Studocu") == "GEA1000_Sample_Paper_Studocu"
