#!/usr/bin/env python3
"""ieee_parser.py — IEEE Xplore 提取纯函数（可离线单测）"""
import math
import re

from config import get

TYPE_CHOICES = ["Conferences", "Journals", "Magazines"]
MIN_YEAR = 1943
ARNO_RE = re.compile(r"/document/(\d+)")
SHOWING_RE = re.compile(r"Showing [\d,]+-[\d,]+ of ([\d,]+)")


def parse_year_range(year_arg):
    """'2020' → (2020,2020)；'2020-2025' → (2020,2025)；非法抛 ValueError"""
    if not year_arg:
        return None
    parts = [p.strip() for p in str(year_arg).split("-")]
    if len(parts) not in (1, 2) or not all(p.isdigit() for p in parts):
        raise ValueError(f"year 格式非法: {year_arg}")
    lo, hi = int(parts[0]), int(parts[-1])
    if lo < MIN_YEAR or hi < MIN_YEAR or lo > hi:
        raise ValueError(f"year 需 >= {MIN_YEAR} 且 lo<=hi: {year_arg}")
    return lo, hi


def build_search_url(kw, types, year, rows, page):
    """构造 searchresult.jsp URL（refinements 每 type 一个，ranges 可选）"""
    from urllib.parse import urlencode
    query = [("queryText", kw)]
    for t in types:
        query.append(("refinements", f"ContentType:{t}"))
    if year:
        lo, hi = parse_year_range(year)
        query.append(("ranges", f"{lo}_{hi}_Year"))
    query += [("rowsPerPage", str(rows)), ("pageNumber", str(page))]
    return "https://ieeexplore.ieee.org/search/searchresult.jsp?" + urlencode(query)


def extract_arnumber(href):
    m = ARNO_RE.search(href or "")
    return m.group(1) if m else None


def clean_title(raw):
    return re.sub(r"\s+", " ", (raw or "")).strip()


def extract_snippet(body, title):
    """body innerText 中 title 后 '\nAbstract\nHTML\n' 截到 'Show More'，压空白截 400"""
    idx = body.find(title)
    if idx < 0:
        return ""
    seg = body[idx + len(title):]
    m = re.search(r"\nAbstract\nHTML\n(.*?)(?:Show More)", seg, re.S)
    text = m.group(1) if m else ""
    return re.sub(r"\s+", " ", text).strip()[:get("trunc.snippet")]


def extract_total(body):
    m = SHOWING_RE.search(body or "")
    return int(m.group(1).replace(",", "")) if m else None


def page_info(page, total):
    return f"{page}/{max(1, math.ceil((total or 0) / 25))}"


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name or "").strip()


# ── detail 提取 ────────────────────────────────────────
ABSTRACT_RE = re.compile(r"Abstract:\s*([\s\S]+?)(?:Published in:|Date of Conference:|Date of\b|DOI:|Publisher:|Show More)")
# re.S：期刊详情的 "Published in: X\nPage(s): ...\nDate of Publication: ..." 中间跨行；
# stop 集合含 Page(s):（期刊）与 Date of（会议），截断更干净
PUBLISHED_IN_RE = re.compile(r"Published in:\s*(.+?)(?:\s+Page\(s\):|\s+Date of|\s+DOI:|\s+Publisher:)", re.S)
# 兼容会议 "Date of Conference:" 与期刊 "Date of Publication:"；期刊 ISSN Information 行作 stop
PUBDATE_RE = re.compile(r"Date of (?:Conference|Publication):\s*(.+?)(?:\s+DOI|\s+Date Added|\s+Publisher|\s+INSPEC|\s+ISSN)")
DOI_RE = re.compile(r"DOI:\s*(10\.\d+\/[^\s]+)")
CITED_RE = re.compile(r"(\d+)\s*Cites?\s*in\s*Papers?")
VIEWS_RE = re.compile(r"(\d+)\s*Full\s*Text\s*Views?")
# body 为 innerText 纯文本（无 HTML 标签）：取 "ADVANCED SEARCH" 后第一非空行作 title 兜底
FALLBACK_TITLE_RE = re.compile(r"(?:^|\n)ADVANCED SEARCH\n([^\n]+)")


def extract_detail_fields(body, page_url, title=None):
    """从详情页 body innerText 提取核心字段（元数据走正则，同 Node 版）。

    title 由调用方传入 h1 文本（DOM 提取）；为 None/空或 <10 字符时用 FALLBACK_TITLE_RE
    从 body 兜底，兜底不到则为空字符串。
    """
    arn = ARNO_RE.search(page_url or "")
    if not title or len(title) < 10:
        m = FALLBACK_TITLE_RE.search(body or "")
        title = m.group(1).strip() if m else ""
    return {
        "hasInstitutionalAccess": bool(re.search(r"\bSign Out\b|Access provided by", body or "")),
        "arnumber": arn.group(1) if arn else None,
        "title": title,
        "abstract": _g(ABSTRACT_RE, body),
        "publishedIn": _g(PUBLISHED_IN_RE, body),
        "pubDate": _g(PUBDATE_RE, body),
        "doi": _g(DOI_RE, body),
        "citedBy": _g(CITED_RE, body),
        "fullTextViews": _g(VIEWS_RE, body),
    }


def _g(pat, text):
    m = pat.search(text or "")
    return m.group(1).strip() if m else None


def extract_references(body):
    seg = _after_second(body, "References", r"\n(Citations|Keywords|Metrics|Footnotes|Download PDFs)\n")
    if seg is None:
        return "No references"
    refs = [s for r in re.split(r"\n(?=\d+\.\s)", seg)
            if len(s := r.strip()) > 10 and re.match(r"^\d+\.", s)][:get("caps.refs")]
    return refs or "No references"


def extract_keywords(body):
    m = re.search(r"Index Terms\s*\n([\s\S]*?)(?=\nAuthor Keywords)", body or "")
    if not m:
        return "No keywords"
    kws = [ln.strip() for ln in m.group(1).splitlines()
           if ln.strip() and not ln.strip().startswith(",")]
    return ",".join(kws) or "No keywords"


def extract_footnotes(body):
    if "Sign in to view" in (body or "")[-3000:]:
        return "Sign in required"
    seg = _after_second(body, "Footnotes",
                        r"\n(More Like This|Back to Results|Authors|Figures|References|Citations|Keywords|Metrics)\n")
    if seg is None:
        return None
    notes = [r.strip() for r in re.split(r"\n(?=\d+\.\n)", seg)][:get("caps.refs")]
    notes = [n for n in notes if n and n not in ("Back to Results", "< Previous")]
    return notes or "No footnotes"


def _after_second(body, heading, stop_pat):
    """取 body 中第二个 <heading> 之后、命中 stop_pat 之前的内容。

    真实页面 tab 标题与内容区标题同名会出现两次（取第二个）；
    仅出现一次时退回第一个（离线测试 body 即此类）；均不存在返回 None。
    """
    body = body or ""
    idx = body.find(f"\n{heading}\n")
    if idx < 0:
        return None
    idx2 = body.find(f"\n{heading}\n", idx + 1)
    if idx2 >= 0:
        idx = idx2
    seg = body[idx + len(heading) + 2:]
    m = re.search(stop_pat, seg)
    return seg[:m.start()] if m else seg
