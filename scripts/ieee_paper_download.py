#!/usr/bin/env python3
"""ieee_paper_download.py — IEEE Xplore 论文 PDF 下载 CLI

用法:
  python ieee_paper_download.py --arnumber 123 --save-dir ./papers
输出: stdout JSON { count, results: [...] }；进度日志 → stderr
"""
import argparse
import json
import os
import re
import sys
import time

from cdp_base import (CdpError, close_page, create_page, ensure_cdp,  # noqa: E402
                      fetch_binary_diag, setup_stdout, write_log)
from config import get
from ieee_parser import sanitize_filename

MAX_DOWNLOAD = 5


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="IEEE Xplore 论文 PDF 下载")
    ap.add_argument("--arnumber", action="append", required=True, help="文章编号（可重复，1-5 个）")
    ap.add_argument("--save-dir", required=True, help="保存目录（必填）")
    args = ap.parse_args(argv)
    if len(args.arnumber) > MAX_DOWNLOAD:
        ap.error(f"--arnumber 最多 {MAX_DOWNLOAD} 个")
    os.makedirs(args.save_dir, exist_ok=True)
    return args


def build_pdf_url(arn):
    return f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arn}"


def looks_like_pdf(data):
    """PDF 文件头 %PDF- 校验；HTML/错误页返回 False"""
    return data[:5] == b"%PDF-"


def _page_title(client):
    return client.evaluate("(document.querySelector('h1') || {}).textContent || ''") or ""


def download_one(client, arn, save_dir):
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

    title = sanitize_filename(_page_title(client))[:get("trunc.filename")] or arn
    diag = fetch_binary_diag(client, build_pdf_url(arn))
    data = diag["data"]
    if not data:
        return {"arnumber": arn, "error": "PDF 下载为空"}
    if diag["status"] != 200:
        return {"arnumber": arn, "error": (
            f"stampPDF HTTP {diag['status']}（最终 URL: {diag['finalUrl']}）"
            f" — 可能是 302 到登录页 / 403 / 机构订阅缺失，请确认机构访问权限")}
    if not looks_like_pdf(data):
        return {"arnumber": arn, "error": (
            f"下载内容非 PDF：HTTP {diag['status']}，Content-Type: {diag['contentType'] or '未知'}，"
            f"{len(data)} B（可能是登录/权限页 HTML 或订阅缺失）")}
    path = os.path.join(save_dir, f"{title}.pdf")
    with open(path, "wb") as f:
        f.write(data)
    sys.stderr.write(f"[ieee-paper-download] {arn} 已保存 {len(data)} bytes\n")
    return {"arnumber": arn, "download": {"name": os.path.basename(path), "path": path,
                                          "size": len(data)}}


def main():
    args = parse_args()
    port = ensure_cdp()
    results = []
    for i, arn in enumerate(args.arnumber):
        # 顺序下载（防 rate-limit）
        client = None
        try:
            client = create_page(port)
            if i > 0:
                time.sleep(get("rate.limit")[0])
            results.append(download_one(client, arn, args.save_dir))
        except Exception as e:
            results.append({"arnumber": arn, "error": str(e)[:200]})
        finally:
            close_page(client)
    out = {"count": len(results), "results": results}
    # 先落盘再写 stdout：宿主对 stdout 有大小上限，Agent 拿全文直接读 logPath
    try:
        out["logPath"] = write_log(out, "ieee_paper_download")
        sys.stderr.write(f"[ieee-paper-download] 完整结果已落盘: {out['logPath']}\n")
    except Exception as e:
        sys.stderr.write(f"[ieee-paper-download] 落盘失败: {str(e)[:80]}\n")
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    setup_stdout()
    main()
