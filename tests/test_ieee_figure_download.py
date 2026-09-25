# tests/test_ieee_figure_download.py
"""download_figures 的单张图失败必须落盘，不能只留一个 count。

背景：此前单张图下载失败只写 stderr，返回里只有 count（成功数）——既不知道
页面上一共有几张图，也不知道哪几张、为什么挂。一篇论文 10 张图挂 4 张，
调用方只会看到 count: 6，缺口是静默的。

修复后：``total`` 给页面收集到的张数，``count < total`` 即为缺口；
失败时另附 ``failures[{ name, url, error }]``（error 截断到 200 字符）。
"""
import ieee_figure_download as mod

FIG1 = "https://ieeexplore.ieee.org/mediastore/IEEE/content/media/1/2/3/fig1-large.gif"
FIG2 = "https://ieeexplore.ieee.org/mediastore/IEEE/content/media/1/2/3/fig2-large.png"


class _FakeClient:
    """够 download_figures 走完「导航 → 点 Figures tab → 收集图片」三步。"""

    def __init__(self, srcs):
        self._srcs = srcs

    def navigate(self, url):
        self._url = url

    def wait_for(self, expr, timeout=None, interval=None):
        return True

    def get_body_text(self):
        return "Sign Out  Access provided by: TEST UNIVERSITY"

    def evaluate(self, expr, **kw):
        if "mediastore" in expr:  # COLLECT_IMAGES_JS
            return list(self._srcs)
        return True  # FIGURES_TAB_JS


def _no_sleep(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)


def _raises(exc):
    def _fetch(client, url):
        raise exc
    return _fetch


class TestFigureFailures:
    def test_all_success_reports_count_and_total(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        monkeypatch.setattr(mod, "fetch_binary", lambda c, u: b"img")

        r = mod.download_figures(_FakeClient([FIG1, FIG2]), "123", str(tmp_path))

        assert r["count"] == 2
        assert r["total"] == 2
        assert "failures" not in r
        assert (tmp_path / "123" / "fig1.gif").read_bytes() == b"img"
        assert (tmp_path / "123" / "fig2.png").read_bytes() == b"img"

    def test_partial_failure_records_name_url_error(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)

        def fake_fetch(client, url):
            if url == FIG2:
                raise RuntimeError("连接被重置")
            return b"img"

        monkeypatch.setattr(mod, "fetch_binary", fake_fetch)

        r = mod.download_figures(_FakeClient([FIG1, FIG2]), "123", str(tmp_path))

        assert r["count"] == 1  # 成功张数
        assert r["total"] == 2  # 页面上一共几张 → 缺口可见
        assert len(r["failures"]) == 1
        f = r["failures"][0]
        assert f["name"] == "fig2"
        assert f["url"] == FIG2
        assert "连接被重置" in f["error"]

    def test_all_failed_still_reports_total(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        monkeypatch.setattr(mod, "fetch_binary", _raises(OSError("下载超时")))

        r = mod.download_figures(_FakeClient([FIG1, FIG2]), "123", str(tmp_path))

        assert r["count"] == 0
        assert r["total"] == 2
        assert [f["name"] for f in r["failures"]] == ["fig1", "fig2"]

    def test_failure_error_is_truncated(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        monkeypatch.setattr(mod, "fetch_binary", _raises(RuntimeError("x" * 500)))

        r = mod.download_figures(_FakeClient([FIG1]), "123", str(tmp_path))

        assert r["failures"][0]["error"] == "x" * 200

    def test_failure_also_written_to_stderr(self, monkeypatch, tmp_path, capsys):
        _no_sleep(monkeypatch)
        monkeypatch.setattr(mod, "fetch_binary", _raises(RuntimeError("图 2 挂了")))

        mod.download_figures(_FakeClient([FIG1, FIG2]), "123", str(tmp_path))

        err = capsys.readouterr().err
        assert "失败" in err
