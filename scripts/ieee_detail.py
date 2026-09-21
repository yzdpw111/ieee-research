#!/usr/bin/env python3
"""ieee_detail.py — IEEE Xplore 详情 CLI（Python 重构版）

用法:
  python ieee_detail.py --arnumber 123456 --arnumber 789012
输出: stdout JSON { count, results: [...] }；进度日志 → stderr
"""
import argparse
import json
import re
import sys
import time

from cdp_base import close_page, create_page, ensure_cdp, setup_stdout, write_log
from config import get
from ieee_parser import (extract_detail_fields, extract_footnotes,
                         extract_keywords, extract_references)

MAX_DETAIL = 8


def _body(client):
    """innerText（块级元素间带换行，正则依赖 \n 边界；textContent 无换行会导致正则错乱）"""
    return client.evaluate("document.body ? document.body.innerText : ''") or ""


TAB_TEXT_JS = """(text) => {
  const els = Array.from(document.querySelectorAll('button, a, [role=tab]'))
    .filter(e => (e.textContent || '').trim() === text && e.offsetParent !== null);
  const el = els[els.length - 1];
  if (el) { el.click(); return true; }
  return false;
}"""

# 模板占位符 {n} 由调用处 .format 注入 caps.authors（JS 内无其他花括号，format 安全）
AUTHORS_JS = """() => Array.from(document.querySelectorAll('a[href*="/author/"]'))
  .map(a => (a.textContent || '').trim())
  .filter(t => t.length > 2).slice(0, {n})"""

CITE_OPEN_JS = """() => {
  const b = Array.from(document.querySelectorAll('button'))
    .find(e => (e.textContent || '').trim() === 'Cite This');
  if (b) { b.click(); return true; }
  return false;
}"""

CITE_TAB_JS = """(label) => {
  const links = Array.from(document.querySelectorAll('ngb-modal-window a.document-tab-link'));
  const el = links.find(a => (a.textContent || '').trim() === label);
  if (el) { el.click(); return true; }
  return false;
}"""

CITE_CLOSE_JS = """() => {
  const b = document.querySelector('ngb-modal-window button.modal-close-container');
  if (b) { b.click(); return true; }
  return false;
}"""


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="IEEE Xplore 详情")
    ap.add_argument("--arnumber", action="append", required=True, help="文章编号（可重复，1-8 个）")
    ap.add_argument("--parallel", type=int, default=None, help="并行任务数（默认 2，最大 8）")
    args = ap.parse_args(argv)
    if len(args.arnumber) > MAX_DETAIL:
        ap.error(f"--arnumber 最多 {MAX_DETAIL} 个")
    args.parallel = args.parallel if args.parallel is not None else get("parallel.limit")
    args.parallel = max(1, min(args.parallel, 8))
    return args


def scrape_detail(client, arn):
    url = f"https://ieeexplore.ieee.org/document/{arn}/"
    client.navigate(url)
    if not client.wait_for("!!document.querySelector('h1')", timeout=get("timeout.detail_load")):
        head = _body(client)[:500]
        if "could not be found" in head:
            return {"arnumber": arn, "error": "Invalid arnumber - 404 page not found"}
        return {"arnumber": arn, "error": "页面加载超时"}
    # 404 页也有 h1（"404: Page Not Found"），h1 出现后再查一次
    if "could not be found" in _body(client)[:500]:
        return {"arnumber": arn, "error": "Invalid arnumber - 404 page not found"}

    # 展开摘要
    try:
        client.evaluate("document.querySelectorAll('[class*=abstract] button, .show-more')"
                        ".forEach(el => { if (/show more/i.test(el.textContent || '')) el.click(); })")
        time.sleep(1)
    except Exception:
        pass

    h1 = client.evaluate("(document.querySelector('h1') || {}).textContent || ''") or ""
    body = _body(client)
    d = extract_detail_fields(body, url, title=re.sub(r"\s+", " ", h1).strip())
    # author 链接渲染慢于展开摘要后的 1s，先等其出现再提取；
    # 复用 cite_modal 作为渲染等待上限（默认同为 5s，行为不变）
    client.wait_for("!!document.querySelector('a[href*=\"/author/\"]')",
                    timeout=get("timeout.cite_modal"))
    d["authors"] = client.evaluate(f"({AUTHORS_JS.format(n=get('caps.authors'))})()") or []

    # References tab
    if client.evaluate(f"({TAB_TEXT_JS})({json.dumps('References')})"):
        time.sleep(get("timeout.detail_tab"))
        d["references"] = extract_references(_body(client))
    else:
        d["references"] = "No references"

    # Keywords tab
    if client.evaluate(f"({TAB_TEXT_JS})({json.dumps('Keywords')})"):
        time.sleep(get("timeout.detail_tab"))
        d["keywords"] = extract_keywords(_body(client))
    else:
        d["keywords"] = "No keywords"

    # Footnotes tab
    has_fn = client.evaluate(f"({TAB_TEXT_JS})({json.dumps('Footnotes')})")
    if has_fn:
        time.sleep(get("timeout.detail_tab"))
        d["footnotes"] = extract_footnotes(_body(client))
    else:
        d["footnotes"] = None

    # Citations 弹窗
    d["citations"] = None
    if client.evaluate(f"({CITE_OPEN_JS})()"):
        if client.wait_for("!!document.querySelector('ngb-modal-window')",
                           timeout=get("timeout.cite_modal")):
            # 弹窗先出现但内容异步加载（.text 初始为 "Getting results..."），等正文就绪再读
            client.wait_for("(() => { const t = document.querySelector('ngb-modal-window .text'); "
                            "return t && (t.textContent||'').trim().length > 20; })()",
                            timeout=get("timeout.cite_modal"))
            out = {}
            for key, label in [("plain", "Plain Text"), ("bibtex", "BibTeX"), ("ris", "RIS")]:
                client.evaluate(f"({CITE_TAB_JS})({json.dumps(label)})")
                time.sleep(get("timeout.render_wait"))
                out[key] = client.evaluate(
                    "(document.querySelector('ngb-modal-window .text') || {}).textContent || ''") or ""
            d["citations"] = out
            client.evaluate(f"({CITE_CLOSE_JS})()")

    for k in ("authors",):
        if not d.get(k):
            d[k] = "No authors"
    return d


def _detail_in_tab(port, arn, args):
    client = None
    try:
        client = create_page(port)
        return arn, scrape_detail(client, arn)
    except Exception as e:
        return arn, e
    finally:
        close_page(client)


def main():
    from concurrent.futures import ThreadPoolExecutor
    args = parse_args()
    port = ensure_cdp()
    limit = min(len(args.arnumber), args.parallel)
    results = []
    with ThreadPoolExecutor(max_workers=limit) as ex:
        for arn, r in ex.map(_detail_in_tab, [port] * len(args.arnumber), args.arnumber, [args] * len(args.arnumber)):
            if isinstance(r, Exception):
                results.append({"arnumber": arn, "error": str(r)[:200]})
                sys.stderr.write(f"[ieee-detail] {arn} 失败: {str(r)[:120]}\n")
            else:
                results.append(r)
                sys.stderr.write(f"[ieee-detail] {arn} 完成\n")
            sys.stderr.flush()
    out = {"count": len(results), "results": results}
    # 先落盘再写 stdout：宿主对 stdout 有大小上限，Agent 拿全文直接读 logPath
    try:
        out["logPath"] = write_log(out, "ieee_detail")
        sys.stderr.write(f"[ieee-detail] 完整结果已落盘: {out['logPath']}\n")
    except Exception as e:
        sys.stderr.write(f"[ieee-detail] 落盘失败: {str(e)[:80]}\n")
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    setup_stdout()
    main()
