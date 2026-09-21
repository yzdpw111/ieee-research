import pytest

from ieee_parser import (TYPE_CHOICES, build_search_url, clean_title,
                         extract_arnumber, extract_detail_fields,
                         extract_footnotes, extract_keywords,
                         extract_references, extract_snippet, extract_total,
                         page_info, parse_year_range, sanitize_filename)


class TestParseYearRange:
    def test_single(self):
        assert parse_year_range("2020") == (2020, 2020)

    def test_range(self):
        assert parse_year_range("2020-2025") == (2020, 2025)

    def test_invalid_below_min(self):
        with pytest.raises(ValueError):
            parse_year_range("1900")

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_year_range("abc")


class TestBuildSearchUrl:
    def test_basic(self):
        u = build_search_url("deep learning", ["Conferences"], None, 25, "1")
        assert u.startswith("https://ieeexplore.ieee.org/search/searchresult.jsp?")
        assert "queryText=deep+learning" in u
        assert "refinements=ContentType%3AConferences" in u
        assert "rowsPerPage=25" in u and "pageNumber=1" in u

    def test_multi_type_and_year(self):
        u = build_search_url("ai", TYPE_CHOICES, "2020-2025", 10, "3")
        assert u.count("refinements=") == 3
        assert "ranges=2020_2025_Year" in u


class TestExtract:
    def test_arnumber(self):
        assert extract_arnumber("https://ieeexplore.ieee.org/document/123456/") == "123456"
        assert extract_arnumber("no match") is None

    def test_total(self):
        assert extract_total("Showing 1-25 of 1,234") == 1234
        assert extract_total("nothing") is None

    def test_snippet(self):
        body = ("TitleA\nAbstract\nHTML\nThis is the abstract text. Show More"
                "\nmore stuff")
        s = extract_snippet(body, "TitleA")
        assert "This is the abstract text." in s
        assert "Show More" not in s

    def test_clean_title(self):
        assert clean_title("  A  Title  ") == "A Title"

    def test_sanitize_filename(self):
        assert sanitize_filename('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"


class TestPageInfo:
    def test_math(self):
        assert page_info(1, 50) == "1/2"   # ceil(50/25)
        assert page_info(2, 10) == "2/1"


DETAIL_BODY = """ADVANCED SEARCH
My Paper Title That Is Long Enough
Abstract:
This is the abstract content. 
Published in: 2023 IEEE Conference
Date of Conference: 2023
DOI: 10.1109/ABC.2023.1
Publisher: IEEE
5 Cites in Papers
123 Full Text Views
References
1. First ref
2. Second ref
Citations
Index Terms
keyword one
keyword two
Author Keywords
Footnotes
1. A footnote
More Like This
"""


class TestDetailFields:
    def test_fields(self):
        d = extract_detail_fields(DETAIL_BODY, "https://ieeexplore.ieee.org/document/998877/")
        assert d["title"] == "My Paper Title That Is Long Enough"
        assert d["arnumber"] == "998877"
        assert "abstract content" in d["abstract"]
        assert d["publishedIn"] == "2023 IEEE Conference"
        assert d["pubDate"] == "2023"
        assert d["doi"] == "10.1109/ABC.2023.1"
        assert d["citedBy"] == "5"
        assert d["fullTextViews"] == "123"

    def test_no_cites(self):
        d = extract_detail_fields(DETAIL_BODY.replace("5 Cites in Papers\n", ""),
                                  "https://x/document/1/")
        assert d["citedBy"] is None

    def test_login_detection(self):
        assert extract_detail_fields(DETAIL_BODY, "u")["hasInstitutionalAccess"] is False
        d = extract_detail_fields("Sign Out\n" + DETAIL_BODY, "u")
        assert d["hasInstitutionalAccess"] is True
        d2 = extract_detail_fields("Access provided by SomeOrg\n" + DETAIL_BODY, "u")
        assert d2["hasInstitutionalAccess"] is True


JOURNAL_BODY = (
    "ADVANCED SEARCH\nJournal Title Here\nAbstract:\nJournal abstract text.\n"
    "Published in: IEEE Transactions on Power Delivery ( Volume: 24, Issue: 4, October 2009)\n"
    "Page(s): 1959 - 1967\nDate of Publication: 22 September 2009 \nISSN Information:\n"
    "DOI: 10.1109/TPWRD.2009.2028817\nPublisher: IEEE\n")


class TestJournalLayout:
    def test_journal_published_in(self):
        d = extract_detail_fields(JOURNAL_BODY, "https://ieeexplore.ieee.org/document/5235774/")
        assert d["publishedIn"] == "IEEE Transactions on Power Delivery ( Volume: 24, Issue: 4, October 2009)"

    def test_journal_pubdate(self):
        d = extract_detail_fields(JOURNAL_BODY, "https://ieeexplore.ieee.org/document/5235774/")
        assert d["pubDate"] == "22 September 2009"


class TestRefsKeywordsFootnotes:
    def test_references(self):
        assert extract_references(DETAIL_BODY) == ["1. First ref", "2. Second ref"]

    def test_keywords(self):
        assert extract_keywords(DETAIL_BODY) == "keyword one,keyword two"

    def test_footnotes(self):
        assert extract_footnotes(DETAIL_BODY) == ["1. A footnote"]

    def test_footnotes_signin(self):
        assert extract_footnotes("...Sign in to view...") == "Sign in required"

    def test_footnotes_absent(self):
        assert extract_footnotes("no footnotes here") is None
