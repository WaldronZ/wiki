# AutoPaperReader

AutoPaperReader 是一个自动化「找论文 -> 读论文 -> 写报告」的 agent 项目。

它的目标是把一篇论文从检索、下载源码、分析论文、分析配套代码，到最终输出结构化中文阅读报告的流程串起来，并把产物（包括 Markdown 报告和 HTML 展示网页）统一组织到固定目录中。

项目还会把这些逐篇报告汇总成一个轻量动态 wiki：`docs/index.html` 提供全文搜索、研究线、分类/状态/代码/重要性/复习筛选、排序、分页和可分享 URL 状态；`docs/library.html` 提供适合大量论文批量管理的密集表格视图；`docs/board.html` 提供可拖拽状态看板；`docs/inbox.html` 提供候选论文待处理池；`docs/quality.html` 提供质量治理和 taxonomy drift 门禁；`docs/review.html` 提供复习队列和建议复习日期；`docs/dashboard.html` 提供分类覆盖、研究线健康度和待处理队列；`docs/collections.html` 提供共享视图、智能队列和研究线集合入口；`docs/related.html` 提供标签共现和相似论文关系发现；`docs/gaps.html` 提供研究缺口和下一步行动建议；`docs/taxonomy.html` 提供分类治理、状态矩阵和研究线角色矩阵；`docs/timeline.html` 提供按年份和研究线浏览的路线时间轴；`docs/matrix.html` 提供研究线 x 年份覆盖矩阵；`docs/lines/index.html` 提供研究线入口；`docs/tags.html` 提供分类总览；`docs/papers.json` 提供机器可读索引；`docs/search_index.json` 提供正文检索索引；`docs/stats.json` 提供机器可读运营指标；`docs/quality.json` 提供元数据质量与运营队列报告；`docs/review.json` 提供机器可读复习计划。

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
├── CONTRIBUTING.md
├── LICENSE
├── CLAUDE.md
├── .claude/
│   └── agents/
│       ├── paper-analyst.md
│       └── code-analyst.md
├── docs/
│   ├── index.html
│   ├── library.html
│   ├── board.html
│   ├── inbox.html
│   ├── quality.html
│   ├── review.html
│   ├── dashboard.html
│   ├── collections.html
│   ├── related.html
│   ├── gaps.html
│   ├── taxonomy.html
│   ├── timeline.html
│   ├── matrix.html
│   ├── lines/
│   │   └── index.html
│   ├── tags.html
│   ├── papers.json
│   ├── search_index.json
│   ├── stats.json
│   ├── inbox.json
│   ├── quality.json
│   ├── review.json
│   ├── guides/
│   │   ├── taxonomy.md
│   │   ├── taxonomy.json
│   │   └── metadata.schema.json
│   └── .gitkeep
├── scripts/
│   ├── apply_library_metadata.py
│   ├── apply_review_plan.py
│   ├── build_wiki.py
│   ├── check_quality.py
│   ├── check_wiki_js.js
│   ├── export_library_csv.py
│   ├── export_reading_list.py
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
- `scripts/export_reading_list.py` 用于按研究线、状态、方向、主题、方法或重要性导出 Markdown 阅读清单、BibTeX 或链接列表
- `scripts/apply_library_metadata.py` 用于把编辑后的 CSV 分类/状态字段安全写回报告 frontmatter，默认只 dry-run
- `scripts/check_quality.py` 是本地一键质量门禁，和 GitHub Actions 使用同一组检查

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
- `docs/board.html`：状态看板，按自定义 `status` 分列，也可临时新增状态列，拖拽后导出 `status_board_patch.csv`
- `docs/inbox.csv`：候选论文待处理池源数据，可手动追加 title/link/status/priority/tags/note
- `docs/inbox.html`：候选论文待处理池，支持筛选、去重提示和复制阅读任务
- `docs/quality.html`：质量治理页，集中展示弱元数据、taxonomy drift 和候选重复项
- `docs/review.html`：复习计划页，展示待复习、需建计划、已计划和高优先级队列
- `docs/dashboard.html`：管理控制台，展示分类覆盖、研究线健康度、待复习和待补分类队列
- `docs/collections.html`：集合视图页，集中展示共享筛选视图、智能队列和研究线集合入口
- `docs/related.html`：关联网络页，展示标签共现、相似论文对和孤岛论文，帮助发现潜在研究簇
- `docs/gaps.html`：研究缺口页，自动诊断研究线缺角色、缺分类、缺复习、缺代码观察和后续工作空档
- `docs/taxonomy.html`：分类治理页，展示 domain/track/problem 层级、状态矩阵、研究线角色矩阵、状态工作流设计器和治理队列
- `docs/timeline.html`：研究路线时间轴，按年份、研究线、方向、角色、状态和重要性筛选论文演进
- `docs/matrix.html`：研究线年份矩阵，按 research line × year 查看覆盖密度，点击格子查看论文清单
- `docs/lines/index.html`：研究线总览
- `docs/lines/<research-line>.html`：单条研究线详情页
- `docs/tags.html`：分类总览
- `docs/papers.json`：论文索引数据，包含可供前端动态渲染筛选器的 `controls`
- `docs/search_index.json`：全文搜索索引
- `docs/stats.json`：机器可读统计摘要，包含覆盖率、队列规模、研究线和分类分布
- `docs/inbox.json`：机器可读候选论文队列
- `docs/quality.json`：元数据质量报告，列出缺分类、taxonomy drift、缺复习计划、待复习、缺代码观察等队列
- `docs/review.json`：机器可读复习计划，给出 suggested_next_review 和优先级
- `docs/guides/metadata.schema.json`：报告 frontmatter 字段契约，用于校验类型、日期格式和评分范围

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

标签别名、研究线角色排序、阅读状态、阅读阶段和复习阶段可在 [`docs/guides/taxonomy.json`](docs/guides/taxonomy.json) 里自定义；修改后运行 `python3 scripts/build_wiki.py docs` 即可刷新筛选项、论文库批量下拉框和状态看板列。`docs/taxonomy.html` 会展示当前状态工作流配置，并提供浏览器内状态工作流设计器，可以先编辑候选状态、复制或下载 `taxonomy_status_workflow.json` 片段，再合并回 `taxonomy.json`；`docs/board.html` 还支持先新增临时状态列并导出 CSV，用来试跑一套新流程。构建后的 `docs/papers.json` 和 `docs/stats.json` 会把这些可选状态写入 `controls`，方便后续页面或桌面软件动态读取。

报告 frontmatter 的字段类型、必填项、评分范围和日期格式由 [`docs/guides/metadata.schema.json`](docs/guides/metadata.schema.json) 描述。`python3 scripts/validate_wiki.py docs --strict-taxonomy` 会同时校验 schema、报告元数据、分类漂移和生成页面，适合作为发布或开源协作前的质量门禁。

首页和论文库表格的筛选、排序、分页状态会写入 URL query string。比如按研究线、重要性排序后复制浏览器地址，即可分享同一个论文列表视图。常用状态组合也可以保存为浏览器本地视图；团队共用队列可以写进 `docs/guides/taxonomy.json` 的 `shared_views`，随仓库同步到所有人的 wiki 下拉框里。

手动刷新 wiki：

```bash
python3 scripts/build_wiki.py docs
```

批量收集候选论文时，可以先维护 `docs/inbox.csv`：

```csv
title,link,status,priority,tags,note
Example Paper,https://arxiv.org/abs/2601.00001,queued,high,LLM Serving;Batching,先读方法
```

刷新后打开 `docs/inbox.html`，可以筛选候选论文、查看疑似重复项，并复制单篇论文的阅读任务给 agent 流程。

提交前运行完整质量门禁：

```bash
python3 scripts/check_quality.py docs
```

这会依次检查脚本语法、已提交 wiki 生成物是否最新、严格验证 metadata / taxonomy / 内部链接、解析 wiki 页面内联 JavaScript，并运行单元测试。开源协作时，`.github/workflows/wiki-quality.yml` 会在 push / pull request 中自动运行同一组门禁。

单独检查已提交的 wiki 生成物是否为最新：

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
node scripts/check_wiki_js.js docs
python3 -m unittest discover -s tests
```

导出论文库管理表：

```bash
python3 scripts/export_library_csv.py docs --output docs/library.csv
```

导出可分享阅读清单或引用清单：

```bash
python3 scripts/export_reading_list.py docs --line "Parallel Decoding with Diffusion Models" --min-importance 4 --output docs/exports/parallel-decoding-reading-list.md
python3 scripts/export_reading_list.py docs --format bibtex --track "Attention Kernels" --output docs/exports/attention-kernels.bib
python3 scripts/export_reading_list.py docs --format links --status read
```

把表格里编辑过的分类和状态字段写回报告 frontmatter：

```bash
python3 scripts/apply_library_metadata.py docs --input docs/library.csv
python3 scripts/apply_library_metadata.py docs --input docs/library.csv --write
python3 scripts/build_wiki.py docs
```

`docs/library.html` 也支持先筛选论文、勾选当前页或指定行、批量选择 `status` / `reading_stage` / `review_stage` / `next_review`，再下载 `metadata_patch.csv`；也可以把当前筛选和排序结果直接导出为 `reading_list.md` 或 `library.bib`。`docs/board.html` 支持把论文卡片拖到新的状态列，然后下载 `status_board_patch.csv`。下载后用同一个写回脚本预览和应用：

```bash
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv --write
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/status_board_patch.csv --write
python3 scripts/build_wiki.py docs
```

支持 `--field status --field topics` 限定字段，支持 `--slug <slug>` 限定论文；空单元格默认不会清空原值，需要显式加 `--clear-empty`。

预览并写入复习计划建议：

```bash
python3 scripts/apply_review_plan.py docs
python3 scripts/apply_review_plan.py docs --write
python3 scripts/build_wiki.py docs
```

手动重建某篇报告 HTML：

```bash
python3 scripts/render_report_html.py docs/<slug>.md docs/<slug>.html --slug <slug>
```

这个渲染器会把多行 `$$...$$` 公式转成显式 KaTeX block，并把本地论文图复制到 `docs/assets/<slug>/`，避免公式裸露或图片在 wiki 中破图。

## License

本项目使用 [MIT License](./LICENSE)。
