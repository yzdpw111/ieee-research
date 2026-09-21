---
name: ieee-research
description: IEEE Xplore 学术论文检索 — 搜索、详情、PDF/图片下载，CDP Chrome 自动化
---

# IEEE Xplore Research

IEEE Xplore 学术检索：搜索、详情（参考文献/关键词/引用格式）、论文 PDF 下载、图表下载。基于 CDP 裸 Chrome（`navigator.webdriver=false`）规避反爬，输出 stdout JSON。

## 安装

1. 确认 Chrome 已安装（`C:\Program Files\Google\Chrome\Application\chrome.exe`）
2. 安装依赖：`pip install -r requirements.txt`（仅 `websocket-client`）
3. 启动 Chrome 会话：`python chrome_session.py --start`，在 Chrome 中通过机构 IP / CARSI 登录；登录态持久保存，`--status` 查看、`--stop` 关闭

profile 位于 `%USERPROFILE%\.yzdpw_state\chrome-cdp`，CDP 端口记录于同目录 `.cdp_port`。

**权限说明**：搜索无需登录；PDF/图片下载、引用弹窗需机构访问权限。注意 `hasInstitutionalAccess` 是页面级检测，与 PDF 接口级权限**不一定一致**——下载以 `stampPDF` 接口实际返回为准，失败时报错含 HTTP 状态码/最终 URL/Content-Type（可区分 302 到登录页 / 403 / 订阅缺失）。下载任务顺序执行（防 rate-limit），`--parallel` 只影响搜索/详情。

**输出落盘**：所有脚本 stdout 输出完整 JSON 的同时，把**同一份完整结果**写入 `<IE_LOGS_DIR>/<脚本名>-<时间戳>.json`（默认 `logs/`，即脚本启动时的工作目录；可用 `IE_LOGS_DIR` 覆盖），并在 stderr 与 stdout 的 `logPath` 字段给出绝对路径。落盘发生在写 stdout **之前**，stdout 被截断或失败也不丢结果；需要全文时直接读该文件（多对话接力同理）。

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

**输出：** `{ count, results, logPath }`，每条 result 含 `keyword, totalResults, pageInfo, perPage, items[{ id, arnumber, title, url, snippet }]`。无结果 `notice`；404/超时 `error`。

### ieee_detail.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-8 个） |
| `--parallel` | ❌ | 2 | 并行任务数（1-8） |

**输出：** `{ count, results, logPath }`，每条 result 含 `arnumber, hasInstitutionalAccess, title, authors[], abstract, publishedIn, pubDate, doi, citedBy, fullTextViews, references[], keywords, footnotes[], citations{ plain, bibtex, ris }`。无内容字段为 `"No ..."` 占位；无效编号 → `"Invalid arnumber - 404 page not found"`。

### ieee_paper_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | ✅ | — | 保存目录 |

**输出：** `{ count, results, logPath }`，每条含 `download: { name, path, size }`（文件名=清洗后的论文标题）；404 → `"Invalid arnumber - 404"`；未登录 → `"Not logged in"`；接口返回非 PDF（如 HTML 权限页）→ 报错含 HTTP 状态码。

### ieee_figure_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | ✅ | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | ✅ | — | 保存目录（图片存入 `<save-dir>/<arnumber>/`） |

**输出：** `{ count, results, logPath }`，每条含 `count, dir`；无图 → `"No figures"`。

**用法：**
```powershell
python ieee_search.py --q "deep learning" --type Conferences --year 2020-2025 --rows 10
python ieee_detail.py --arnumber 8876906
python ieee_paper_download.py --arnumber 8876906 --save-dir "D:\papers"
python ieee_figure_download.py --arnumber 5235774 --save-dir "D:\figures"
```

## 配置（环境变量，前缀 `IE_`）

调优参数集中在 `config.py`，用 `IE_*` 环境变量覆盖（键名 `IE_` + 点号转下划线大写，如 `timeout.detail_tab` → `IE_TIMEOUT_DETAIL_TAB`）：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `IE_TIMEOUT_PAGE_LOAD` | `20` | 搜索页加载判定总时长(s)（IEEE 页面实测渲染 >8s，原来 8 会误判超时） |
| `IE_TIMEOUT_DETAIL_LOAD` | `30` | 详情页元素出现等待(s) |
| `IE_TIMEOUT_DETAIL_TAB` | `3` | References/Keywords/Footnotes tab 切换等待(s) |
| `IE_TIMEOUT_CITE_MODAL` | `5` | 引用弹窗出现/内容就绪等待(s) |
| `IE_TIMEOUT_RENDER_WAIT` | `2` | 渲染等待默认(s) |
| `IE_TIMEOUT_DOWNLOAD` | `60` | 单次 PDF/图片请求超时(s) |
| `IE_TIMEOUT_CDP` | `30` | CDP WebSocket 超时(s) |
| `IE_RATE_LIMIT` | `8,18` | 下载任务间隔范围(s) |
| `IE_PARALLEL_LIMIT` | `2` | 并行上限 |
| `IE_CAPS_REFS` | `20` | 参考文献/脚注最多条数 |
| `IE_CAPS_AUTHORS` | `20` | 作者最多人数 |
| `IE_TRUNC_SNIPPET` | `400` | 搜索摘要截断 |
| `IE_TRUNC_FILENAME` | `100` | 下载文件名截断 |
| `IE_HUMAN_SCROLL_DELTA` / `IE_HUMAN_PAUSE` / `IE_HUMAN_MOUSE_PROB` | — | 人类行为模拟 |
| `IE_TABS_MAX` | `30` | tab 数上限，达到即**只告警**（不自动关 tab；0=不启用） |
| `IE_LOGS_DIR` | `<运行目录>/logs` | 完整结果落盘目录（默认 = 脚本启动时的工作目录） |

示例：`set IE_TIMEOUT_DETAIL_TAB=5` 后运行，tab 切换等待变为 5s。

## 已知限制

- 每个关键词/编号用一个 tab，用完即关（`close_page`）；tab 总数达 `IE_TABS_MAX` 时**只告警不自动关** —— 四个 skill 共用一个 Chrome，自动关"空 tab"会误伤其他任务刚建好、还没 navigate 的 tab
- 若只剩最后一个 tab：`close_page` 会先建一个空白页（about:blank）占位再关它 —— 直接关会让整个共享 Chrome 退出，不关又会留下上次的搜索结果/详情页
- 搜索摘要（snippet）依赖页面 innerText 布局，页面改版时可能为空
- 详情元数据从页面文本正则提取，字段缺失时返回 `"No ..."` 占位或 null
- 下载需机构访问权限；机构未订阅该文献时 `stampPDF` 可能返回 302/403/HTML 页，脚本报错（含 HTTP 状态码）而非静默存 HTML
- 并行搜索/详情提升请求频率，风控风险上升；下载始终顺序执行

## 脚本清单

```
scripts/
  ieee_search.py           搜索（SSR HTML 提取，type/year/rows/page）
  ieee_detail.py           详情 + References/Keywords/Footnotes + Cite This 弹窗
  ieee_paper_download.py   论文 PDF 下载（页面上下文 fetch，带 cookie）
  ieee_figure_download.py  图表下载（Figures tab → mediastore 图）
  ieee_parser.py           提取纯函数（URL 构造/正则/清洗）
  cdp_base.py              CDP 客户端 + Chrome 裸启动 + 人类行为模拟 + 下载能力
  chrome_session.py        登录会话管理（--start/--status/--stop）
```
