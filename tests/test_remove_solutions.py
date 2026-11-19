import argparse
import re

import pytest

import remove_solutions as rs

pymupdf = pytest.importorskip("pymupdf")
Q = re.compile(rs.DEFAULT_QUESTION_PATTERN, re.I)
M = re.compile(r"^Solution\b", re.I)


def page(*lines, height=800):
    return rs.PageLines(600, height, [rs.Line(t, (50, y, 300, y + 12)) for t, y in lines])


def test_answer_between_questions():
    det = rs.find_answer_regions([page(("1. What?", 100), ("Solution: 42", 200), ("2. Why?", 400))], Q, M)
    assert det.questions == ["1", "2"] and det.markers == 1
    assert det.regions == [(0, (0, 199, 600, 398))]


def test_answer_runs_over_page_break_and_keeps_header():
    pages = [page(("1. What?", 100), ("Solution", 500)),
             page(("Header", 10), ("more answer", 100)),
             page(("Header", 10), ("still answer", 80), ("2. Next", 300))]
    det = rs.find_answer_regions(pages, Q, M, top_content=40)
    assert det.regions == [(0, (0, 499, 600, 800)), (1, (0, 40, 600, 800)), (2, (0, 40, 600, 298))]


def test_no_answer_no_regions():
    det = rs.find_answer_regions([page(("1. A", 100), ("2. B", 300))], Q, M)
    assert det.regions == [] and det.markers == 0


def test_parse_color():
    assert rs.parse_color("ff0000") == (1.0, 0.0, 0.0)
    assert rs.parse_color("0,0.5,1") == (0.0, 0.5, 1.0)
    with pytest.raises(argparse.ArgumentTypeError):
        rs.parse_color("1,2")


def make_pdf(path, red_question=False):
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 100), "1. What is 2+2?")
    p.insert_text((50, 150), "Solution", color=(1, 0, 0))
    p.insert_text((50, 170), "The answer is four.", color=(1, 0, 0))
    p.insert_text((50, 300), "2. What is 3+3?", color=(1, 0, 0) if red_question else (0, 0, 0))
    p.insert_text((50, 350), "Solution")
    p.insert_text((50, 370), "Six.")
    doc.save(path)


def text_of(path):
    return "".join(p.get_text() for p in pymupdf.open(path))


def test_make_practice_end_to_end(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src)
    opts = rs.PracticeOptions(marker="Solution", forbid_colors=[(1, 0, 0)], expected_questions=2)
    paths = rs.make_practice(src, tmp_path / "out", "T", opts)
    practice = next(p for p in paths if p.name == "T_Questions_Only.pdf")
    solutions = next(p for p in paths if p.name == "T_With_Solutions.pdf")
    text = text_of(practice)
    assert "1. What is 2+2?" in text and "2. What is 3+3?" in text
    assert "four" not in text and "Six" not in text and "Solution" not in text
    assert "four" in text_of(solutions)
    assert round(pymupdf.open(practice)[0].rect.width) == 595  # A4


def test_forbid_color_catches_leftover(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src, red_question=True)
    opts = rs.PracticeOptions(marker="Solution", forbid_colors=[(1, 0, 0)])
    with pytest.raises(rs.RedactionError, match="answer colour"):
        rs.make_practice(src, tmp_path / "out", "T", opts)


def test_refuses_without_markers(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src)
    with pytest.raises(rs.RedactionError, match="No answer markers"):
        rs.make_practice(src, tmp_path / "out", "T", rs.PracticeOptions(marker="Nope"))


def test_dry_run_writes_previews(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src)
    paths = rs.make_practice(src, tmp_path / "out", "T", rs.PracticeOptions(marker="Solution", dry_run=True))
    assert any(p.suffix == ".png" for p in paths)
    assert not (tmp_path / "out/T_Questions_Only.pdf").exists()
