# AutoPaperReader

AutoPaperReader 是一个自动化「找论文 -> 读论文 -> 写报告」的 agent 项目。

它的目标是把一篇论文从检索、下载源码、分析论文、分析配套代码，到最终输出结构化中文阅读报告的流程串起来，并把产物（包括 Markdown 报告和 HTML 展示网页）统一组织到固定目录中。

项目还会把这些逐篇报告汇总成一个轻量动态 wiki：`docs/index.html` 提供全文搜索、研究线、分类/状态/代码/重要性/复习筛选、排序、分页和可分享 URL 状态；`docs/library.html` 提供适合大量论文批量管理的密集表格视图；`docs/review.html` 提供复习队列和建议复习日期；`docs/dashboard.html` 提供分类覆盖、研究线健康度和待处理队列；`docs/taxonomy.html` 提供分类治理、状态矩阵和研究线角色矩阵；`docs/lines/index.html` 提供研究线入口；`docs/tags.html` 提供分类总览；`docs/papers.json` 提供机器可读索引；`docs/search_index.json` 提供正文检索索引；`docs/stats.json` 提供机器可读运营指标；`docs/quality.json` 提供元数据质量与运营队列报告；`docs/review.json` 提供机器可读复习计划。

**注：建议开启 Agent Teams 特性 `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`**

## 项目目标

- 根据论文标题、方法名或 arXiv 链接定位目标论文
- 下载并解压 arXiv 源码
- 在发现公开代码时自动拉取代码仓库
- 派发子 agent 完成论文阅读和代码分析
- 在 `docs/` 中生成结构化中文报告
- 自动刷新 `docs/index.html` 作为个人论文 wiki 入口

## 目录结构

```text
paper_reader/
├── README.md
├── LICENSE
├── CLAUDE.md
├── .claude/
│   └── agents/
│       ├── paper-analyst.md
│       └── code-analyst.md
├── docs/
│   ├── index.html
│   ├── library.html
│   ├── review.html
│   ├── dashboard.html
│   ├── taxonomy.html
│   ├── lines/
│   │   └── index.html
│   ├── tags.html
│   ├── papers.json
│   ├── search_index.json
│   ├── stats.json
│   ├── quality.json
│   ├── review.json
│   ├── guides/
│   │   ├── taxonomy.md
│   │   └── taxonomy.json
│   └── .gitkeep
├── scripts/
│   ├── apply_library_metadata.py
│   ├── apply_review_plan.py
│   ├── build_wiki.py
│   ├── export_library_csv.py
│   └── render_report_html.py
└── sources/
    └── .gitkeep
```

说明：

- `CLAUDE.md` 是主线 agent 的工作流说明
- `.claude/agents/` 存放子 agent 的执行规范
- `sources/` 用于存放单篇论文的源码与代码仓库
- `docs/` 用于存放论文阅读报告和静态 wiki
- `scripts/build_wiki.py` 用于扫描报告并生成 wiki 汇总页
- `scripts/render_report_html.py` 是稳定 HTML 渲染兜底脚本，用于修复公式裸露、图片破图等展示问题
- `scripts/apply_review_plan.py` 用于把 `docs/review.json` 的建议复习日期安全写回报告 frontmatter，默认只 dry-run
- `scripts/export_library_csv.py` 用于把 `papers.json`、`review.json` 和 `quality.json` 合并导出成 CSV，便于用表格工具批量管理
- `scripts/apply_library_metadata.py` 用于把编辑后的 CSV 分类/状态字段安全写回报告 frontmatter，默认只 dry-run

## 工作流概览

1. 输入论文题目、方法名或 arXiv 链接
2. 主线 agent 定位论文并下载 arXiv 源码
3. 若存在公开代码，则一并拉取代码仓库
4. 派发 `paper-analyst` 生成论文阅读报告
5. 若存在代码，再派发 `code-analyst` 补充实现观察
6. 在 `docs/<slug>.md` 生成最终中文报告
7. 在 `docs/<slug>.html` 生成单篇 HTML 报告
8. 运行 `python3 scripts/build_wiki.py docs` 刷新 wiki 汇总

## 产物约定

每篇论文使用统一 slug 命名：

```text
<arxiv_id>-<short-name>
```

例如：

```text
2310.06825-mistral-7b
1706.03762-attention
```

对应产物位置：

- `sources/<slug>/arxiv/`：论文源码
- `sources/<slug>/code/`：配套代码仓库
- `docs/<slug>.md`：阅读报告
- `docs/<slug>.html`：单篇阅读报告 HTML
- `docs/index.html`：wiki 首页
- `docs/library.html`：论文库表格，适合大量论文的密集筛选、排序和批量管理
- `docs/review.html`：复习计划页，展示待复习、需建计划、已计划和高优先级队列
- `docs/dashboard.html`：管理控制台，展示分类覆盖、研究线健康度、待复习和待补分类队列
- `docs/taxonomy.html`：分类治理页，展示 domain/track/problem 层级、状态矩阵、研究线角色矩阵和治理队列
- `docs/lines/index.html`：研究线总览
- `docs/lines/<research-line>.html`：单条研究线详情页
- `docs/tags.html`：分类总览
- `docs/papers.json`：论文索引数据，包含可供前端动态渲染筛选器的 `controls`
- `docs/search_index.json`：全文搜索索引
- `docs/stats.json`：机器可读统计摘要，包含覆盖率、队列规模、研究线和分类分布
- `docs/quality.json`：元数据质量报告，列出缺分类、缺复习计划、待复习、缺代码观察等队列
- `docs/review.json`：机器可读复习计划，给出 suggested_next_review 和优先级

## Wiki 分类

每篇 `docs/<slug>.md` 建议以 YAML frontmatter 开头，便于 wiki 分类和筛选：

```yaml
---
slug: 1706.03762-attention
title: Attention Is All You Need
title_zh: 注意力就是你所需要的一切
title_en: Attention Is All You Need
arxiv_id: "1706.03762"
year: 2017
authors:
  - Vaswani et al.
domains:
  - LLM Systems
tracks:
  - Attention Kernels
problems:
  - Efficient Sequence Modeling
topics:
  - Transformer
methods:
  - self-attention
research_line: Transformer Architecture
line_role: foundation
status: read
reading_stage: deep_read
importance: 5
confidence: 5
reproducibility: 4
has_code: true
---
```

如果报告缺少 frontmatter，`scripts/build_wiki.py` 会从标题、正文、arxiv id 和关键词中做兜底推断。

分类建议见 [`docs/guides/taxonomy.md`](docs/guides/taxonomy.md)。核心原则是：`domains/tracks/problems` 管结构层级，`topics/methods` 管交叉筛选，`research_line/line_role` 管研究脉络，`status/reading_stage/review_stage` 管个人阅读状态。

标签别名、研究线角色排序、阅读状态、阅读阶段和复习阶段可在 [`docs/guides/taxonomy.json`](docs/guides/taxonomy.json) 里自定义；修改后运行 `python3 scripts/build_wiki.py docs` 即可刷新筛选项。构建后的 `docs/papers.json` 和 `docs/stats.json` 会把这些可选状态写入 `controls`，方便后续页面或桌面软件动态读取。

首页和论文库表格的筛选、排序、分页状态会写入 URL query string。比如按研究线、重要性排序后复制浏览器地址，即可分享同一个论文列表视图。常用状态组合也可以保存为浏览器本地视图；团队共用队列可以写进 `docs/guides/taxonomy.json` 的 `shared_views`，随仓库同步到所有人的 wiki 下拉框里。

手动刷新 wiki：

```bash
python3 scripts/build_wiki.py docs
```

检查已提交的 wiki 生成物是否为最新：

```bash
python3 scripts/build_wiki.py docs --check
```

验证 wiki 元数据、生成索引和内部链接：

```bash
python3 scripts/validate_wiki.py docs
python3 scripts/validate_wiki.py docs --strict-taxonomy
```

运行脚本工作流测试：

```bash
python3 -m unittest discover -s tests
```

导出论文库管理表：

```bash
python3 scripts/export_library_csv.py docs --output docs/library.csv
```

把表格里编辑过的分类和状态字段写回报告 frontmatter：

```bash
python3 scripts/apply_library_metadata.py docs --input docs/library.csv
python3 scripts/apply_library_metadata.py docs --input docs/library.csv --write
python3 scripts/build_wiki.py docs
```

支持 `--field status --field topics` 限定字段，支持 `--slug <slug>` 限定论文；空单元格默认不会清空原值，需要显式加 `--clear-empty`。

预览并写入复习计划建议：

```bash
python3 scripts/apply_review_plan.py docs
python3 scripts/apply_review_plan.py docs --write
python3 scripts/build_wiki.py docs
```

仓库也提供 GitHub Actions workflow：每次 push / pull request 会检查脚本语法、确认 wiki 生成物已更新并运行验证脚本。

手动重建某篇报告 HTML：

```bash
python3 scripts/render_report_html.py docs/<slug>.md docs/<slug>.html --slug <slug>
```

这个渲染器会把多行 `$$...$$` 公式转成显式 KaTeX block，并把本地论文图复制到 `docs/assets/<slug>/`，避免公式裸露或图片在 wiki 中破图。

## License

本项目使用 [MIT License](./LICENSE)。
