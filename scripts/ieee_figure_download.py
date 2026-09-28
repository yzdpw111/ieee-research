#!/usr/bin/env python3
"""ieee_figure_download.py — IEEE Xplore 图片下载 CLI

用法:
  python ieee_figure_download.py --arnumber 123 --save-dir ./figures
输出: stdout JSON { count, results: [...] }；进度日志 → stderr
"""
import argparse
import json
import os
import re
import sys
import time

from cdp_base import (CdpError, close_page, create_page, ensure_cdp,  # noqa: E402
                      fetch_binary, setup_stdout, write_log)
from config import get
from ieee_parser import sanitize_filename

MAX_DOWNLOAD = 5
FIGURES_TAB_JS = """() => {
  const els = Array.from(document.querySelectorAll('a.document-tab-link'))
    .filter(e => (e.textContent || '').trim() === 'Figures');
  const el = els[els.length - 1];
  if (el) { el.click(); return true; }
  return false;
}"""
COLLECT_IMAGES_JS = """() => Array.from(
  document.querySelectorAll('img[src*="mediastore/IEEE"], .document-tab-content img'))
  .map(i => i.src || '')
  .filter(s => s.includes('/mediastore/'))"""
# 论文标题（h1）。结果里带上它，调用方才知道 <arnumber>/ 目录是哪篇论文。
H1_TEXT_JS = "(document.querySelector('h1') || {}).textContent || ''"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="IEEE Xplore 图片下载")
    ap.add_argument("--arnumber", action="append", required=True, help="文章编号（可重复，1-5 个）")
    ap.add_argument("--save-dir", required=True, help="保存目录（必填）")
    ap.add_argument("--naming", choices=["arn", "title"], default="arn",
                    help="子目录命名：arn=论文编号（默认，稳定唯一）；"
                         "title=论文标题（可读，重名风险自负）")
    args = ap.parse_args(argv)
    if len(args.arnumber) > MAX_DOWNLOAD:
        ap.error(f"--arnumber 最多 {MAX_DOWNLOAD} 个")
    os.makedirs(args.save_dir, exist_ok=True)
    return args


def normalize_figure_url(u):
    """-small → -large；已含 -large 保留"""
    if "-large" in u:
        return u
    return u.replace("-small", "-large")


def figure_name(u):
    m = re.search(r"/([^/]+)-large\.", u)
    return m.group(1) if m else None


def dir_name(arn, title, naming):
    """子目录名。默认用 arnumber（稳定、唯一，便于与详情脚本的结果对齐）；
    naming="title" 时用清洗并截断的论文标题（可读，但同名论文会互相覆盖）。"""
    if naming != "title":
        return arn
    return sanitize_filename(title)[:70].strip(" ._") or arn


def download_figures(client, arn, save_dir, naming="arn"):
    url = f"https://ieeexplore.ieee.org/document/{arn}/"
    client.navigate(url)
    if not client.wait_for("!!document.querySelector('h1')", timeout=get("timeout.detail_load")):
        head = client.get_body_text()[:500]
        if "could not be found" in head:
            return {"arnumber": arn, "error": "Invalid arnumber - 404"}
        return {"arnumber": arn, "error": "页面加载超时"}
    body = client.get_body_text()
    # 404 页也有 h1（"404: Page Not Found"），h1 出现后再查一次
    if "could not be found" in body[:500]:
        return {"arnumber": arn, "error": "Invalid arnumber - 404"}
    if not re.search(r"\bSign Out\b|Access provided by", body):
        return {"arnumber": arn, "error": "Not logged in"}
    # 标题：结果里带上，调用方才知道 <arnumber>/ 目录是哪篇论文；--naming title 时还用它当目录名
    raw_title = client.evaluate(H1_TEXT_JS)
    title = re.sub(r"\s+", " ", raw_title).strip() if isinstance(raw_title, str) else ""

    if not client.evaluate(f"({FIGURES_TAB_JS})()"):
        return {"arnumber": arn, "error": "No figures"}
    time.sleep(get("timeout.render_wait"))
    if not client.wait_for("!!document.querySelector('img[src*=\"mediastore/IEEE\"], .document-tab-content img')",
                           timeout=get("timeout.detail_load")):
        return {"arnumber": arn, "error": "No figures"}

    srcs = client.evaluate(f"({COLLECT_IMAGES_JS})()") or []
    urls, seen = [], set()
    for s in srcs:
        u = normalize_figure_url(s)
        if u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        return {"arnumber": arn, "error": "No figures"}

    out_dir = os.path.join(save_dir, dir_name(arn, title, naming))
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    failures = []
    for i, u in enumerate(urls, 1):
        name = figure_name(u) or f"fig_{i}"
        ext_m = re.search(r"\.(\w+)(?:\?|$)", u)
        ext = ext_m.group(1) if ext_m else "gif"
        try:
            data = fetch_binary(client, u)
            with open(os.path.join(out_dir, f"{name}.{ext}"), "wb") as f:
                f.write(data)
            n += 1
        except Exception as e:
            failures.append({"name": name, "url": u, "error": str(e)[:200]})
            sys.stderr.write(f"[ieee-figure-download] {arn} 图 {i} 失败: {str(e)[:80]}\n")
    out = {"arnumber": arn, "title": title, "count": n, "total": len(urls), "dir": out_dir}
    if failures:
        out["failures"] = failures
    return out


def main():
    args = parse_args()
    port = ensure_cdp()
    results = []
    for i, arn in enumerate(args.arnumber):
        client = None
        try:
            client = create_page(port)
            if i > 0:
                time.sleep(get("rate.limit")[0])
            results.append(download_figures(client, arn, args.save_dir, args.naming))
        except Exception as e:
            results.append({"arnumber": arn, "error": str(e)[:200]})
        finally:
            close_page(client)
    out = {"count": len(results), "results": results}
    # 先落盘再写 stdout：宿主对 stdout 有大小上限，Agent 拿全文直接读 logPath
    try:
        out["logPath"] = write_log(out, "ieee_figure_download")
        sys.stderr.write(f"[ieee-figure-download] 完整结果已落盘: {out['logPath']}\n")
    except Exception as e:
        sys.stderr.write(f"[ieee-figure-download] 落盘失败: {str(e)[:80]}\n")
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    setup_stdout()
    main()
