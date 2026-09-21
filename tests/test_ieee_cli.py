import pytest

from ieee_parser import TYPE_CHOICES
from ieee_search import parse_args


def test_defaults():
    a = parse_args(["--q", "ai"])
    assert a.rows == 25 and a.page == "1" and a.type == TYPE_CHOICES
    assert a.parallel == 2


def test_type_filter():
    a = parse_args(["--q", "ai", "--type", "Journals"])
    assert a.type == ["Journals"]


def test_bad_type_exits():
    with pytest.raises(SystemExit) as e:
        parse_args(["--q", "ai", "--type", "Books"])
    assert e.value.code == 1


def test_bad_year_exits():
    with pytest.raises(SystemExit) as e:
        parse_args(["--q", "ai", "--year", "1900"])
    assert e.value.code == 1


def test_rows_capped():
    a = parse_args(["--q", "ai", "--rows", "999"])
    assert a.rows == 25


def test_parallel_capped():
    a = parse_args(["--q", "ai", "--parallel", "99"])
    assert a.parallel == 8


def test_detail_arnumber_required():
    with pytest.raises(SystemExit):
        from ieee_detail import parse_args
        parse_args([])


def test_detail_arnumber_multi():
    from ieee_detail import parse_args
    a = parse_args(["--arnumber", "1", "--arnumber", "2"])
    assert a.arnumber == ["1", "2"]


def test_detail_parallel_cap():
    from ieee_detail import parse_args
    a = parse_args(["--arnumber", "1", "--parallel", "99"])
    assert a.parallel == 8


from ieee_figure_download import normalize_figure_url, figure_name
from ieee_paper_download import build_pdf_url, looks_like_pdf, parse_args as dl_parse_args


def test_pdf_url():
    assert build_pdf_url("123") == "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=123"


def test_download_save_dir_required():
    with pytest.raises(SystemExit):
        dl_parse_args(["--arnumber", "1"])


class TestFigureUrl:
    def test_small_to_large(self):
        assert normalize_figure_url("https://x/mediastore/abc-small.jpg") == \
               "https://x/mediastore/abc-large.jpg"

    def test_large_kept(self):
        u = "https://x/mediastore/abc-large.png"
        assert normalize_figure_url(u) == u

    def test_name(self):
        assert figure_name("https://x/mediastore/abc-large.jpg") == "abc"
        assert figure_name("https://x/mediastore/zzz-large.png?a=1") == "zzz"


def test_looks_like_pdf():
    assert looks_like_pdf(b"%PDF-1.4\n%..") is True
    assert looks_like_pdf(b"<html><body>login</body></html>") is False
    assert looks_like_pdf(b"") is False
