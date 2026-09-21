# tests/test_ieee_download_errors.py
"""覆盖"机构订阅缺失/权限页"这条错误分支。

实测：本机构 IEEE 订阅覆盖很广（IET / CSEE / Bell Labs / Magazines / 会议 / 标准关键词
共 10+ 篇全部可下载），**构造不出真实的 403/302 场景**，所以用单测把这条路径锁住。
"""
import ieee_paper_download as mod


class _FakeClient:
    def __init__(self, body="Access provided by: NANJING UNIVERSITY OF SCIENCE AND TECHNOLOGY",
                 title="My Paper"):
        self._body = body
        self._title = title

    def navigate(self, url):
        self._url = url

    def wait_for(self, expr, timeout=None, interval=None):
        return True

    def get_body_text(self):
        return self._body

    def evaluate(self, expr, **kw):
        return self._title


def _patch(monkeypatch, diag):
    monkeypatch.setattr(mod, "fetch_binary_diag", lambda c, u, timeout=None: diag)


class TestDownloadErrorPaths:
    def test_reports_http_status_when_not_200(self, monkeypatch, tmp_path):
        _patch(monkeypatch, {"data": b"<html>Access Denied</html>", "status": 403,
                             "contentType": "text/html",
                             "finalUrl": "https://ieeexplore.ieee.org/login"})
        r = mod.download_one(_FakeClient(), "123", str(tmp_path))
        assert "403" in r["error"]
        assert "login" in r["error"]              # 报出最终 URL
        assert "机构订阅缺失" in r["error"]
        assert not list(tmp_path.iterdir())       # 不能落非 PDF 内容

    def test_reports_non_pdf_content_type(self, monkeypatch, tmp_path):
        """302 到登录页时 status 可能仍是 200，但内容是 HTML。"""
        _patch(monkeypatch, {"data": b"<html>Please sign in</html>", "status": 200,
                             "contentType": "text/html",
                             "finalUrl": "https://ieeexplore.ieee.org/signin"})
        r = mod.download_one(_FakeClient(), "123", str(tmp_path))
        assert "非 PDF" in r["error"]
        assert "text/html" in r["error"]
        assert not list(tmp_path.iterdir())

    def test_not_logged_in(self, monkeypatch, tmp_path):
        r = mod.download_one(_FakeClient(body="nothing useful here"), "123", str(tmp_path))
        assert r["error"] == "Not logged in"

    def test_saves_pdf_on_success(self, monkeypatch, tmp_path):
        payload = b"%PDF-1.4\nfake pdf body"
        _patch(monkeypatch, {"data": payload, "status": 200,
                             "contentType": "application/pdf",
                             "finalUrl": "https://ieeexplore.ieee.org/stamp/stamp.jsp"})
        r = mod.download_one(_FakeClient(title="My Paper"), "123", str(tmp_path))
        assert r["download"]["size"] == len(payload)
        assert (tmp_path / "My Paper.pdf").read_bytes() == payload
