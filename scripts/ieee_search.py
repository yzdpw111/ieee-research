#!/usr/bin/env python3
"""ieee_search.py — IEEE Xplore 搜索 CLI（Python 重构版）

用法:
  python ieee_search.py --q "deep learning" --type Conferences --year 2020-2025 --rows 25
输出: stdout JSON { count, results: [...] }；进度日志 → stderr
"""
import argparse
import json
import sys
import time

from cdp_base import close_page, create_page, ensure_cdp, setup_stdout, write_log
from config import get
from ieee_parser import (TYPE_CHOICES, build_search_url, clean_title,
                         extract_arnumber, extract_snippet, extract_total,
                         page_info, parse_year_range)

MAX_ROWS = 25


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="IEEE Xplore 搜索")
    ap.add_argument("--q", action="append", required=True, help="搜索关键词（可重复，1-8 个）")
    ap.add_argument("--type", action="append", help="内容类型（可重复）")
    ap.add_argument("--year", default=None, help="年份 YYYY 或 YYYY-YYYY（>=1943）")
    ap.add_argument("--rows", type=int, default=25, help=f"每关键词最大结果数（默认 25，最大 {MAX_ROWS}）")
    ap.add_argument("--page", default="1", help="页码（默认 1）")
    ap.add_argument("--parallel", type=int, default=None, help="并行任务数（默认 2，最大 8）")
    args = ap.parse_args(argv)
    if len(args.q) > 8:
        sys.stderr.write("--q 最多 8 个\n")
        sys.exit(1)
    if args.type:
        for t in args.type:
            if t not in TYPE_CHOICES:
                sys.stderr.write(f"--type 非法值: {t}（可选: {', '.join(TYPE_CHOICES)}）\n")
                sys.exit(1)
    if args.year is not None:
        try:
            parse_year_range(args.year)
        except ValueError as e:
            sys.stderr.write(f"--year 非法值: {e}\n")
            sys.exit(1)
    args.type = args.type or list(TYPE_CHOICES)
    args.rows = max(1, min(args.rows, MAX_ROWS))
    args.parallel = args.parallel if args.parallel is not None else get("parallel.limit")
    args.parallel = max(1, min(args.parallel, 8))
    return args


EXPAND_ABSTRACT_JS = """() => {
  document.querySelectorAll('.abstract-control .fa-angle-down')
    .forEach(el => el.click());
  return true;
}"""


def detect_state(client):
    """normal / noresult / 404 / timeout"""
    for _ in range(int(get("timeout.page_load") / 0.5)):
        try:
            head = client.get_body_text()[:500]
        except Exception:
            time.sleep(0.5)
            continue
        if "The page you were looking for could not be found" in head:
            return "404"
        if client.evaluate("!!document.querySelector('a[href*=\"/document/\"]')"):
            return "normal"
        if client.evaluate("!!document.querySelector('.List-results-none')"):
            return "noresult"
        time.sleep(0.5)
    return "timeout"


def search_one(client, kw, args):
    url = build_search_url(kw, args.type, args.year, args.rows, args.page)
    client.navigate(url)
    state = detect_state(client)
    if state == "noresult":
        return {"keyword": kw, "totalResults": 0, "items": [],
                "notice": "无搜索结果，可能是搜索条件太苛刻或关键词有误"}
    if state == "404":
        return {"keyword": kw, "totalResults": 0, "items": [], "error": "无效 URL（404）"}
    if state == "timeout":
        return {"keyword": kw, "totalResults": 0, "items": [], "error": "页面加载超时"}
    try:
        client.evaluate(f"({EXPAND_ABSTRACT_JS})()")
        time.sleep(get("human.pause")[0])
    except Exception:
        pass

    body = client.get_body_text()
    links = client.evaluate(
        "Array.from(document.querySelectorAll('a[href*=\"/document/\"]'))"
        ".map(a => ({href: a.href, title: (a.textContent || '').trim()}))") or []
    seen, items = set(), []
    for i, l in enumerate(links, 1):
        arn = extract_arnumber(l.get("href") or "")
        title = clean_title(l.get("title"))
        if not arn or len(title) < 20 or arn in seen:
            continue
        seen.add(arn)
        items.append({"id": i, "arnumber": arn, "title": title,
                      "url": l["href"], "snippet": extract_snippet(body, title)})
        if len(items) >= args.rows:
            break
    total = extract_total(body)
    return {"keyword": kw, "totalResults": total if total is not None else 0,
            "pageInfo": page_info(args.page, total if total is not None else 0),
            "perPage": f"{len(items)}/{len(items)}", "items": items}


def _search_in_tab(port, kw, args):
    client = None
    try:
        client = create_page(port)
        return kw, search_one(client, kw, args)
    except Exception as e:
        return kw, e
    finally:
        close_page(client)


def main():
    from concurrent.futures import ThreadPoolExecutor
    args = parse_args()
    port = ensure_cdp()
    limit = min(len(args.q), args.parallel)
    results = []
    with ThreadPoolExecutor(max_workers=limit) as ex:
        for kw, r in ex.map(_search_in_tab, [port] * len(args.q), args.q, [args] * len(args.q)):
            if isinstance(r, Exception):
                results.append({"keyword": kw, "totalResults": 0, "items": [],
                                "error": str(r)[:200]})
                sys.stderr.write(f"[ieee-search] {kw} 失败: {str(r)[:120]}\n")
            else:
                results.append(r)
                sys.stderr.write(f"[ieee-search] {kw}: {r.get('totalResults', 0)} 条\n")
            sys.stderr.flush()
    out = {"count": len(results), "results": results}
    # 先落盘再写 stdout：宿主对 stdout 有大小上限，Agent 拿全文直接读 logPath
    try:
        out["logPath"] = write_log(out, "ieee_search")
        sys.stderr.write(f"[ieee-search] 完整结果已落盘: {out['logPath']}\n")
    except Exception as e:
        sys.stderr.write(f"[ieee-search] 落盘失败: {str(e)[:80]}\n")
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    setup_stdout()
    main()
