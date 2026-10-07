---
name: ieee-research
description: 从 IEEE Xplore 抓取学术论文数据。当用户需要检索 IEEE 论文（可按内容类型/年份筛选），或抓取论文详情（摘要、参考文献、关键词、引用格式），或下载论文 PDF、图表图片时使用。基于 CDP 裸 Chrome 自动化，需 Google Chrome；检索无需登录，下载全文需机构访问权限——在校园网内直接生效，校外网络需先通过 CARSI 登录学校账号。
---

# IEEE Xplore Research

IEEE Xplore 学术检索：搜索、详情（参考文献/关键词/引用格式）、论文 PDF 下载、图表下载。基于 CDP 裸 Chrome（`navigator.webdriver=false`）规避反爬。

结果 **输出到 stdout（JSON）**，同时**落盘到文件**（stdout 有大小上限，需要全文时读落盘文件）。

## 快速开始（首次使用）

前置：**Windows** / **Google Chrome** / **Python 3.9+** / 能访问 `ieeexplore.ieee.org` / （下载类命令还需要**机构订阅**）

```powershell
# 1) 装依赖（requirements.txt 在 scripts/ 下）
pip install -r scripts/requirements.txt

# 2) 搜索不需要登录，可以先跑起来验证环境
python scripts/ieee_search.py --q "deep learning" --rows 5 --parallel 1

# 3) 要下载 PDF / 图表时，先确认机构访问已生效
#    → 打开任意论文详情页，顶部出现 "Access provided by: <你的机构名>" 即已生效
#    校园网内通常免登录；校外需用 CARSI 登录学校账号
#    若访问没生效，可检查是否开着梯子/代理 —— 它会改掉出口 IP，可能导致机构识别失败
python scripts/chrome_session.py --start
python scripts/chrome_session.py --status     # 应看到: CDP 在线: ... (port 9222)

# 4) 下载（--save-dir 必填）
python scripts/ieee_paper_download.py --arnumber 8876906 --save-dir ".\out\papers"

# 5) 用完可关闭 Chrome
python scripts/chrome_session.py --stop
```

三条约定：

- **所有命令都在仓库根目录执行**（脚本路径写成 `scripts/xxx.py`）。
- **日志落在"当前工作目录"的 `logs/`**：在仓库根跑 → `<repo>/logs/`；在 `scripts/` 里跑 → `scripts/logs/`。可用 `IE_LOGS_DIR` 固定。
- `--status` 只证明 **Chrome/CDP 在线**，**不显示机构访问状态**。确认机构访问看 IEEE 页面的 `Access provided by:` 文案。

## 运行环境（重要：DSH 沙箱下必须先放行沙箱启动 Chrome）

Chrome 的多进程通信依赖 crashpad 崩溃处理器和 mojo 命名管道。**在 DSH 的受限沙箱（read-only / workspace-write）里这两者都被拒绝**，Chrome 会启动即自杀、调试端口永不监听——表现就是"等 30 秒后报 `Chrome 30 秒内未就绪`"。这与本 skill 的代码/依赖/启动参数都无关：`--no-sandbox`、`--disable-crash-reporter`、`--headless=new` 实测全部无效。

**沙箱内连 Chrome 没有任何问题**（TCP 127.0.0.1、HTTP `/json`、WebSocket CDP 均实测可用）；**只有"启动 Chrome"这一件事必须放行沙箱**。所以固定用法是两步：

```powershell
# ① 放行沙箱（danger-full-access）或 DSH 之外：启动 Chrome 并完成机构访问认证（只需一次）
python scripts/chrome_session.py --start

# ② 回到沙箱内正常跑抓取脚本：ensure_cdp() 会自动复用 9222-9299 上的在线实例
python scripts/ieee_search.py --q "machine learning" --rows 5
```

- 第 ② 步不需要放行沙箱，也不会再尝试启动 Chrome。
- Chrome 启动失败时它的 stderr 会落盘到 `logs/chrome-launch.log`，错误信息里直接带出来；日志目录都不可写时会明说。
- `chrome_session.py --stop` 靠进程查询，沙箱内可能查不到 PID（`Get-CimInstance` 被拒）；沙箱内要关 Chrome 请用 CDP 的 `Browser.close`，或在放行沙箱下执行 `--stop`。

## chrome_session.py（Chrome 会话管理）

管理专用 CDP Chrome 的生命周期（登录 / 查看状态 / 关闭）。抓取脚本会**自动启动或复用** Chrome，**不需要先跑这个脚本**；只有在需要**登录**或想手动关掉 Chrome 时才用它。

| 参数 | 说明 |
|------|------|
| `--start` | 启动专用 Chrome 并打开默认站点（见下）。已在运行则**直接复用**（幂等） |
| `--status` | 查看 CDP 是否在线 + 端口 + 当前打开的页面列表 |
| `--stop` | 关闭专用 Chrome |
| `--url` | 自定义 `--start` 时打开的 URL（**只开这一个，替代默认站点**） |

不传任何参数 → 打印帮助。

`--start` 会打开 **IEEE Xplore** 首页，方便确认机构访问是否已生效。

```powershell
# 激活机构访问（首次/过期后；登录态持久保存在 profile 里）
python scripts/chrome_session.py --start
# → 在弹出的 Chrome 窗口里完成机构认证 —— **校园网内通常免登录**，校外需用机构 IP 或 CARSI 登录学校账号

# 查看状态（CDP 是否在线 + 打开的页面）
python scripts/chrome_session.py --status
# → CDP 在线: Chrome/xxx (port 9222)

# 只打开某个特定 URL（替代默认站点）
python scripts/chrome_session.py --start --url "https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=power+integrity"

# 关闭
python scripts/chrome_session.py --stop
```

注意事项：

- **`--stop` 只关本 profile 的 Chrome，不碰你日常用的 Chrome** —— 按 `--user-data-dir` 精准匹配进程，不会误杀主浏览器。
- **`--stop` 后机构访问认证不丢**（存在 profile 里），下次 `--start` 无需重新认证。
- **`--status` 只证明 CDP 在线，不显示机构访问状态**。确认机构访问看页面是否出现 `Access provided by:` 或 `Sign Out`。
- 脚本会顺带清理历史遗留的 `ChromeCDP-Shared` 计划任务；没建过也无害。

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
| `--q` | 必填 | — | 搜索关键词（可重复，1-8 个） |
| `--type` | 可选 | 全部 | 内容类型（可重复）：`Conferences` / `Journals` / `Magazines` |
| `--year` | 可选 | — | 年份 `YYYY` 或 `YYYY-YYYY`（≥1943） |
| `--rows` | 可选 | 25 | 每关键词最大结果数（≤25） |
| `--page` | 可选 | 1 | 页码 |
| `--parallel` | 可选 | 2 | 并行关键词数（1-8） |

**输出：** `{ count, results, logPath }`，每条 result 含 `keyword, totalResults, pageInfo, perPage, items[{ id, arnumber, title, url, snippet }]`。

- 无结果 → `notice`；404 / 超时 → `error`（加载超时先看是否 `IE_TIMEOUT_PAGE_LOAD` 偏小）
- **同词异义召回很正常，结果必须人工筛**：`power integrity` 会召回到"电力系统的数据完整性 / 配电网"，
  `signal integrity` 会召回通信与医学语境，`tutorial` / `review` 还会召回**会议日程与征稿通知**
  （题名如 "Call for Workshop Papers"）。这类噪音**无法从检索侧根治**，只能按题名 + 摘要人工剔除，
  别把 `totalResults` 直接当成"相关文献数"。

### ieee_detail.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | 必填 | — | 文章编号（可重复，1-8 个） |
| `--parallel` | 可选 | 2 | 并行任务数（1-8） |

**输出：** `{ count, results, logPath }`，每条 result 含 `arnumber, hasInstitutionalAccess, title, authors[], abstract, publishedIn, pubDate, doi, citedBy, fullTextViews, references[], keywords, footnotes[], citations{ plain, bibtex, ris }`。

- 无内容字段用 `"No ..."` 占位；无效编号 → `"Invalid arnumber - 404 page not found"`

### ieee_paper_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | 必填 | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | 必填 | — | 保存目录（不存在会自动创建） |

**输出：** `{ count, results, logPath }`，每条含 `download: { name, path, size }`（文件名为清洗后的论文标题）。

- 404 → `"Invalid arnumber - 404"`；未登录 → `"Not logged in"`
- 未订阅/权限缺失 → 报错含 **HTTP 状态码 + 最终 URL + Content-Type**（例如 `stampPDF HTTP 403（最终 URL: ...）`），**不会**把 HTML 权限页当 PDF 存下来

### ieee_figure_download.py

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `--arnumber` | 必填 | — | 文章编号（可重复，1-5 个，顺序执行） |
| `--save-dir` | 必填 | — | 保存目录（图片存入 `<save-dir>/<arnumber>/`） |
| `--naming` | 可选 | `arn` | 子目录命名：`arn` = `<save-dir>/<arnumber>/`（稳定唯一，与详情结果对齐）；`title` = `<save-dir>/<清洗后的标题>/`（可读，同名论文会互相覆盖） |

**输出：** `{ count, results, logPath }`，每条含 `arnumber`、`title`、`count`（成功张数）、`total`（页面收集到的张数）、`dir`；单张图下载失败时另含 `failures[{ name, url, error }]`——**`count < total` 即表示有缺口**。无图 → `"No figures"`。

- 目录名默认是编号（稳定、唯一，便于和 `ieee_detail.py` 的结果对上）；想"一眼看出是哪篇"就用 `--naming title`。
  无论用哪种，结果里的 `title` 都能把目录和论文对应起来——**别靠文件名猜内容**。

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

### `meta` 与 `.jsonl` 镜像（2026-10 新增）

每次落盘**同时**产出两份，**主 `.json` 的契约不变**：

| 文件 | 角色 | 说明 |
|---|---|---|
| `<脚本名>-<时间戳>.json` | **权威契约** | 字段布局与从前**完全一致**，只在末尾**追加** `meta` |
| `<脚本名>-<时间戳>.jsonl` | **等价镜像** | 首行 `{"__meta__":…,"__count__":…}`，之后**一行一条记录** |

`meta` 形如：

```json
{"skill": "ieee-research", "script": "ieee_search",
 "time": "2026-10-07T10:50:58+08:00", "argv": ["--q", "关键词", "--rows", "5"]}
```

**为什么要 `.jsonl`**：不是为防"文件被截断"（文件是脚本自己完整写出的，**不会**截断），
而是因为**一行一条记录**——agent 可以**直接按行**检索、分页、`head`/`tail`，
**不必每次写解析器**：

```powershell
Get-Content .\logs\ieee_search-*.jsonl -TotalCount 1                  # 首行 = meta
Select-String -Path .\logs\ieee_search-*.jsonl -Pattern '"id"' | Select-Object -First 5
```

**没有 `.tsv`**：一行一篇的表格是**派生视图**，列集合会随记录字段漂移（检索日志与详情日志的列完全不同），
应由**下游分析层**生成，不属于日志本身。

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
| `"Not logged in"` / 页面没有 `Access provided by:` | 机构访问没生效 → `python scripts/chrome_session.py --start` 后确认页面出现 `Access provided by:`。**若确认校园网下仍不生效**，可检查是否开着梯子/代理（它会改掉出口 IP）→ 关掉后重新 `--start` |
| 搜索返回 `totalResults=0` 且无 `error`/`notice` | 偶发：`items` 为空时可能同时没有 `totalResults`（页面未渲染完 → 解析落空），与"真的没有匹配"无法区分 → **重试通常会恢复**。以落盘日志为准 |
| `"Invalid arnumber - 404 page not found"` | 编号不存在 → 用 `ieee_search` 拿正确的 `arnumber` |
| `Chrome 未找到` | Chrome 没装或装在别处 → 安装 Chrome，或在 `scripts/cdp_base.py` 的 `CHROME_PATHS` 里加路径 |
| `Chrome 30 秒内未就绪` | 启动超时 → 先看 `logs/chrome-launch.log`（Chrome 自己的 stderr 就在里面）；有 Chrome 弹窗/杀软拦截就重试，或调高 `IE_TIMEOUT_CHROME_START` |
| `Chrome 启动即退出`，日志里有 `crashpad` / `OpenProcess` / `platform_channel` 加 `拒绝访问` | **受限沙箱拒绝了 Chrome 的进程与命名管道权限**（不是 skill 的问题）→ 在放行沙箱或 DSH 之外先 `python scripts/chrome_session.py --start`，再回沙箱内跑抓取脚本；详见「运行环境」 |
| 报「日志目录不可写，未能落盘」 | Chrome 日志无处可写 → 用 `IE_LOGS_DIR` 指到工作区内的目录 |
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
  chrome_session.py        机构访问会话管理（--start/--status/--stop/--url）
  config.py                集中配置（可用 IE_* 覆盖）
  requirements.txt         依赖清单

  tests/
  test_*.py                离线单测（不需要 Chrome / 网络 / 机构权限）
```

跑测试（离线单测，不需要机构权限/网络）：

```powershell
pip install pytest
python -m pytest tests -q
```

## 做论文调研时的用法（与 wanfang-research 配合）

> 这一节是写给"新会话里的 agent"的：读到这里，就够照着做完一个完整的论文调研任务。
> 本 skill 只负责检索与下载。

### 环境自检（新电脑 / 新会话第一步）

1. `pip install -r scripts/requirements.txt`
2. `python scripts/chrome_session.py --status` → 应显示 `CDP 在线: ... (port 9222)`
3. **跑一次最轻的搜索**验证整条链路通（不需要登录）：
   `python scripts/ieee_search.py --q "power integrity" --rows 3`
4. 下载 / 详情需要机构访问：`python scripts/chrome_session.py --start`，然后确认机构访问已生效。
   判定依据（与脚本实现一致）：页面出现 **`Sign Out`** 或 **`Access provided by: <机构名>`**。
   详情结果里的 `hasInstitutionalAccess` 字段用同一判据（页面级检测，与 PDF 接口权限
   **不一定一致**，以下载实际返回为准）。**`--status` 只证明 CDP 在线，不显示机构访问状态。**

### 目录组织约定（调研任务请照这个建）

```
<工作目录>/
├── README.md          # 目标、进度、产出清单
├── 01_摘要库/          # 原始 JSON（skill 落盘）+ 人读版汇总 .md
├── 02_精读论文/        # PDF + 精读笔记 .md + figures/（图表）
├── 03_引用文献/        # 下载到的引用 PDF + 引用清单.md（含失败原因）
├── 04_综述/            # 综述提纲 + 最终 docx
└── logs/              # 落盘日志（建议把 IE_LOGS_DIR 固定指到这里）
```

把 `IE_LOGS_DIR` 指到 `logs/`，避免日志散落在各处的 `logs/` 子目录里。

### 四步工作流

1. **搜索 + 抓摘要**：多个关键词并行搜（`--parallel 2`，一次 1-8 个关键词），
   拿到 `arnumber` / `url` 后**批量**抓详情（一次 1-8 个，最划算）。总量按"关键词数 × rows"控制。
2. **选精读**：优先挑 review / tutorial / 入门介绍性质的；下载 PDF 与图表
   （图表用专门的 download 脚本，图片存到该论文同名目录下）。
3. **解析引用**：详情输出里的 `references[]` 是**纯文本**（IEEE 形如 `[1] A. Author, "Title," …`；
   万方是 GB/T 7714 文本）。用**题名**去搜索定位，再下载；下不到的把原因记进清单。
4. **写综述**：把前面的摘要与精读笔记汇总成中文综述，产出 .docx。

### 注意事项（这些会真实咬人）

- **下载是顺序执行、每条间隔 8-18 s**（防限流）。几百条引用要跑几小时 → **必须分批 + 记录进度**，
  按"精读论文自己的 PDF → 引用文献"的优先级来，别一次性跑到底。
- **引用文献大量下不到是常态**（书 / 标准 / 其它出版社 / 机构未订阅）。
  一份**写清失败原因的清单**比"下到了几篇"更有价值。
- 详情页慢（20-30 s/次），所以**一次传满 8 个编号**；`--parallel` 别调太高（提升风控风险）。
- tab 总数到上限时**只告警不自动关**（四个 skill 共用一个 Chrome，别乱关别人的 tab）。
- 所有命令都**在 skill 仓库根目录**执行（脚本路径写成 `scripts/xxx.py`）。
