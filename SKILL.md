---
name: ieee-research
description: IEEE Xplore 学术论文检索 — 搜索、详情、PDF/图片下载，CDP Chrome 自动化
---

# IEEE Xplore Research

IEEE Xplore 学术检索：搜索、详情（参考文献/关键词/引用格式）、论文 PDF 下载、图表下载。基于 CDP 裸 Chrome（`navigator.webdriver=false`）规避反爬。

结果 **输出到 stdout（JSON）**，同时**落盘到文件**（stdout 有大小上限，需要全文时读落盘文件）。

## 快速开始（首次使用）

前置：**Windows** · **Google Chrome** · **Python 3.9+** · 能访问 `ieeexplore.ieee.org` · （下载类命令还需要**机构订阅**）

```powershell
# 1) 装依赖（requirements.txt 在 scripts/ 下）
pip install -r scripts/requirements.txt

# 2) 搜索不需要登录，可以先跑起来验证环境
python scripts/ieee_search.py --q "deep learning" --rows 5 --parallel 1

# 3) 要下载 PDF / 图表时，先确认机构访问已生效
python scripts/chrome_session.py --start
#    → 用机构 IP 或 CARSI 登录，打开任意 IEEE 页面，顶部出现
#      "Access provided by: <你的机构名>" 即已激活
python scripts/chrome_session.py --status     # 应看到: ✅ CDP 在线: ... (port 9222)

# 4) 下载（--save-dir 必填）
python scripts/ieee_paper_download.py --arnumber 8876906 --save-dir ".\out\papers"

# 5) 用完可关闭 Chrome
python scripts/chrome_session.py --stop
```

三条约定：

- **所有命令都在仓库根目录执行**（脚本路径写成 `scripts/xxx.py`）。
- **日志落在"当前工作目录"的 `logs/`**：在仓库根跑 → `<repo>/logs/`；在 `scripts/` 里跑 → `scripts/logs/`。可用 `IE_LOGS_DIR` 固定。
- `--status` 只证明 **Chrome/CDP 在线**，**不显示机构访问状态**。确认机构访问看 IEEE 页面的 `Access provided by:` 文案。

## 运行前提与约定

| 项 | 说明 |
|---|---|
| Chrome | 按 `Program Files` → `Program Files (x86)` → `%LOCALAPPDATA%` 顺序查找；都没找到会报 `Chrome 未找到` |
| profile / 端口 | profile 在 `%USERPROFILE%\.yzdpw_state\chrome-cdp`；CDP 端口 9222-9299，端口号写在同目录 `.cdp_port` |
| 四个 skill 共用 | xhs / zhihu / ieee / wanfang **共用这一个 Chrome 和 profile**，机构访问/登录一次四个都能用 |
| 自动启动 | 脚本会**自动启动或复用** Chrome（搜索不必先 `--start`）；**下载**需要机构访问，必须先 `--start` 激活 |
| Chrome 启动方式 | 裸启动：`--remote-debugging-port` + `--remote-allow-origins=*`，**不带** `--enable-automation` → `navigator.webdriver=false` |
| 权限边界 | 搜索**无需登录**；PDF/图片下载、引用弹窗需机构访问。`hasInstitutionalAccess` 是**页面级**检测，与 PDF 接口级权限**不一定一致**——以下载实际返回为准 |
| 下载节奏 | 下载任务**顺序执行**（每次间隔 `IE_RATE_LIMIT`），`--parallel` 只影响搜索/详情 |
| 页面较慢 | IEEE 搜索页实测渲染 >8s，所以 `IE_TIMEOUT_PAGE_LOAD` 默认 **20s**；不是卡住，别急着调小 |

## 命令

### ieee_search.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--q` | ✅ | — | 搜索关键词（可重复，1-8 个） |
| `--type` | ❌ | 全部 | 内容类型（可重复）：`Conferences` / `Journals` / `Magazines` |
| `--year` | ❌ | — | 年份 `YYYY` 或 `YYYY-YYYY`（≥1943） |
| `--rows` | ❌ | 25 | 每关键词最大结果数（≤25） |
| `--page` | ❌ | 1 | 页码 |
| `--parallel` | ❌ | 2 | 并行关键词数（1-8） |

**输出：** `{ count, results, logPath }`，每条 result 含 `keyword, totalResults, pageInfo, perPage, items[{ id, arnumber, title, url, snippet }]`。

- 无结果 → `notice`；404 / 超时 → `error`（加载超时先看是否 `IE_TIMEOUT_PAGE_LOAD` 偏小）

### ieee_detail.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-8 个） |
| `--parallel` | ❌ | 2 | 并行任务数（1-8） |

**输出：** `{ count, results, logPath }`，每条 result 含 `arnumber, hasInstitutionalAccess, title, authors[], abstract, publishedIn, pubDate, doi, citedBy, fullTextViews, references[], keywords, footnotes[], citations{ plain, bibtex, ris }`。

- 无内容字段用 `"No ..."` 占位；无效编号 → `"Invalid arnumber - 404 page not found"`

### ieee_paper_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | ✅ | — | 保存目录（不存在会自动创建） |

**输出：** `{ count, results, logPath }`，每条含 `download: { name, path, size }`（文件名为清洗后的论文标题）。

- 404 → `"Invalid arnumber - 404"`；未登录 → `"Not logged in"`
- 未订阅/权限缺失 → 报错含 **HTTP 状态码 + 最终 URL + Content-Type**（例如 `stampPDF HTTP 403（最终 URL: ...）`），**不会**把 HTML 权限页当 PDF 存下来

### ieee_figure_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | ✅ | — | 保存目录（图片存入 `<save-dir>/<arnumber>/`） |

**输出：** `{ count, results, logPath }`，每条含 `count, dir`；无图 → `"No figures"`。

**用法：**

```powershell
python scripts/ieee_search.py --q "deep learning" --type Conferences --year 2020-2025 --rows 10
python scripts/ieee_detail.py --arnumber 8876906
python scripts/ieee_paper_download.py --arnumber 8876906 --save-dir ".\out\papers"
python scripts/ieee_figure_download.py --arnumber 5235774 --save-dir ".\out\figures"
# 多篇（1-5 个，顺序下载）
python scripts/ieee_paper_download.py --arnumber 8876906 --arnumber 9672674 --save-dir ".\out\papers"
```

## 输出落盘

所有脚本在写 stdout 的**同时**，把**同一份完整结果**写入：

```
<IE_LOGS_DIR>/<脚本名>-<时间戳>.json      # 默认 <运行目录>/logs/
```

绝对路径会同时出现在 **stderr** 和 **stdout 的 `logPath` 字段**。

- 文件里**不含** `logPath`，是纯结果。
- **落盘发生在写 stdout 之前** → stdout 被截断或失败也不丢结果。
- 读取方式：

```powershell
$f = (Get-Content .\logs\ieee_search-*.json | Select-Object -Last 1)   # 或直接用 logPath
Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json | Select-Object count
```

## 配置（环境变量，前缀 `IE_`）

`scripts/config.py` 集中配置，`IE_*` 覆盖（键名 = `IE_` + 点号转下划线大写，如 `timeout.detail_tab` → `IE_TIMEOUT_DETAIL_TAB`）。

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `IE_TIMEOUT_PAGE_LOAD` | `20` | 搜索页加载判定总时长(s)（IEEE 渲染 >8s，调小会误判超时） |
| `IE_TIMEOUT_DETAIL_LOAD` | `30` | 详情页元素出现等待(s) |
| `IE_TIMEOUT_DETAIL_TAB` | `3` | References/Keywords/Footnotes tab 切换等待(s) |
| `IE_TIMEOUT_CITE_MODAL` | `5` | 引用弹窗出现/内容就绪等待(s) |
| `IE_TIMEOUT_RENDER_WAIT` | `2` | 渲染等待默认(s) |
| `IE_TIMEOUT_DOWNLOAD` | `60` | 单次 PDF/图片请求超时(s) |
| `IE_TIMEOUT_CDP` | `30` | CDP WebSocket 超时(s) |
| `IE_RATE_LIMIT` | `8,18` | 下载任务间隔范围(s) |
| `IE_PARALLEL_LIMIT` | `2` | `--parallel` 的默认值 |
| `IE_CAPS_REFS` | `20` | 参考文献/脚注最多条数 |
| `IE_CAPS_AUTHORS` | `20` | 作者最多人数 |
| `IE_TRUNC_SNIPPET` | `400` | 搜索摘要截断 |
| `IE_TRUNC_FILENAME` | `100` | 下载文件名截断 |
| `IE_HUMAN_SCROLL_DELTA` / `IE_HUMAN_PAUSE` / `IE_HUMAN_MOUSE_PROB` | — | 人类行为模拟 |
| `IE_TABS_MAX` | `30` | tab 数上限，达到即**只告警**（不自动关 tab；`0`=不启用） |
| `IE_LOGS_DIR` | `<运行目录>/logs` | 结果落盘目录（可设成固定路径） |

设置方式（两种 shell 都给，别混用）：

```powershell
# PowerShell
$env:IE_TIMEOUT_DETAIL_TAB = "5"; python scripts/ieee_detail.py --arnumber 8876906
```
```cmd
:: CMD
set IE_TIMEOUT_DETAIL_TAB=5
python scripts\ieee_detail.py --arnumber 8876906
```

## 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `error` 提示 `页面加载超时` | 页面渲染慢 → 确认 `IE_TIMEOUT_PAGE_LOAD` ≥ 20；网络慢可再调大 |
| 下载报 `stampPDF HTTP 403/302` | 机构**未订阅**该文献（或机构访问失效）→ 重新 `--start` 激活机构访问；仍失败说明未订阅 |
| 下载报 `下载内容非 PDF：...Content-Type: text/html` | 返回的是登录/权限页 → 同上 |
| `"Not logged in"` | 机构访问没生效 → `python scripts/chrome_session.py --start` 后确认页面出现 `Access provided by:` |
| `"Invalid arnumber - 404 page not found"` | 编号不存在 → 用 `ieee_search` 拿正确的 `arnumber` |
| `Chrome 未找到` | Chrome 没装或装在别处 → 安装 Chrome，或在 `scripts/cdp_base.py` 的 `CHROME_PATHS` 里加路径 |
| `Chrome 30 秒内未就绪` | 启动超时 → 检查 Chrome 弹窗/杀软拦截，重试 |
| `9222-9299 端口全部被占` | 端口耗尽 → 关掉多余的调试用 Chrome |
| 搜索结果 `snippet` 为空 | 页面布局变化导致文本提取不到（元数据仍正常） |
| 结果被截断（stdout 只看到一部分） | 宿主对 stdout 有大小上限 → 读 `logPath` 指向的文件 |

## 已知限制

- **搜索摘要**（`snippet`）依赖页面 `innerText` 布局，IEEE 改版时可能为空。
- **详情元数据**从页面文本正则提取，字段缺失时返回 `"No ..."` 占位或 `null`。
- **下载需机构访问**；未订阅时 `stampPDF` 可能返回 302/403/HTML 页，脚本**报错并带 HTTP 状态码**，不会静默存下 HTML。
- **机构访问判定**：`hasInstitutionalAccess` 是页面级检测，与 PDF 接口级权限不一定一致——以实际下载结果为准。
- **tab 管理**：每个关键词/编号用一个 tab，用完即关（`close_page`）。tab 总数达 `IE_TABS_MAX` 时**只告警不自动关**——四个 skill 共用一个 Chrome，自动关"空 tab"会误伤其他任务刚建好、还没 navigate 的 tab。
- **最后一个 tab**：`close_page` 会先建一个 `about:blank` 占位页再关它（直接关会让整个共享 Chrome 退出，不关又会留下上次的页面）；占位建不出来时保留该 tab。
- **并发风险**：并行搜索/详情会提升请求频率，风控风险上升；下载始终顺序执行。
- **依赖站点结构**：选择器依赖 IEEE 当前页面结构，站点改版可能让某条路径静默失效。

## 脚本与测试

```
scripts/
  ieee_search.py           搜索（SSR HTML 提取，type/year/rows/page）
  ieee_detail.py           详情 + References/Keywords/Footnotes + Cite This 弹窗
  ieee_paper_download.py   论文 PDF 下载（页面上下文 fetch，带 cookie）
  ieee_figure_download.py  图表下载（Figures tab → mediastore 图）
  ieee_parser.py           提取纯函数（URL 构造/正则/清洗）
  cdp_base.py              CDP 客户端 + Chrome 启动 + 人类行为模拟 + tab 生命周期 + 下载能力
  chrome_session.py        登录会话管理（--start/--status/--stop）
  config.py                集中配置（可用 IE_* 覆盖）
  requirements.txt         依赖清单

tests/                     离线单测（不需要 Chrome / 网络 / 机构权限）
```

跑测试（不需要登录、不需要机构权限）：

```powershell
pip install pytest
python -m pytest tests -q
```
