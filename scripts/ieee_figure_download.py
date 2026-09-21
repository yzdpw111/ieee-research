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


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="IEEE Xplore 图片下载")
    ap.add_argument("--arnumber", action="append", required=True, help="文章编号（可重复，1-5 个）")
    ap.add_argument("--save-dir", required=True, help="保存目录（必填）")
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


def download_figures(client, arn, save_dir):
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

    out_dir = os.path.join(save_dir, arn)
    os.makedirs(out_dir, exist_ok=True)
    n = 0
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
            sys.stderr.write(f"[ieee-figure-download] {arn} 图 {i} 失败: {str(e)[:80]}\n")
    return {"arnumber": arn, "count": n, "dir": out_dir}


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
            results.append(download_figures(client, arn, args.save_dir))
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
