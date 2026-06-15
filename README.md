# AutoPaperReader

AutoPaperReader 是一个自动化「找论文 -> 读论文 -> 写报告 -> 生成 wiki」的开源项目。你给 agent 一篇论文的标题、方法名或 arXiv 链接，它会下载论文源码，阅读正文和公式，必要时拉取配套代码，最后生成结构化中文阅读报告和可浏览的静态 wiki。

在线示例：<https://waldronz.github.io/wiki/>

## 它适合谁

- 想把论文阅读流程标准化的人：每篇论文都有统一章节、frontmatter 和 HTML 展示页。
- 想维护个人或团队论文库的人：`docs/` 会生成搜索、筛选、标签、复习计划、状态看板和质量治理页面。
- 想让 AI agent 深读论文的人：仓库内置主线流程说明和子 agent 规范，可直接交给 Codex / Claude 这类 coding agent 执行。
- 想二次开发论文 wiki 工具的人：所有核心脚本只依赖 Python 标准库，生成物是普通静态 HTML / JSON / Markdown。

## 核心能力

- 根据论文标题、方法名或 arXiv 链接定位论文。
- 下载并解压 arXiv e-print 源码，识别主 `.tex` 文件。
- 自动查重，避免覆盖已有报告。
- 发现公开代码仓库时拉取代码并补充实现观察。
- 生成中文 Markdown 报告和单文件 HTML 报告。
- 构建静态 wiki：全文搜索、分类筛选、论文库表格、状态看板、复习队列、标签注册表、质量检查和批量治理入口。
- 输出机器可读 JSON，方便桌面端、脚本或其它工具集成。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/WaldronZ/wiki.git
cd wiki
```

### 2. 准备环境

基础 wiki 构建只需要 Python 3.9+：

```bash
python3 --version
```

如果要运行完整质量门禁，还需要 Node.js，用来检查页面内联 JavaScript：

```bash
node --version
```

论文下载和代码拉取会用到常见命令行工具：

```bash
git --version
curl --version
```

### 3. 打开已有 wiki

本仓库已经带有示例报告和生成好的页面。可以直接打开：

```bash
open docs/index.html
```

常用入口：

- `docs/index.html`：wiki 首页，适合搜索和按分类筛选。
- `docs/library.html`：密集论文表格，适合批量管理。
- `docs/priority.html`：把复习、分类、代码观察和重要性合成优先级队列。
- `docs/command.html`：按使用场景整理常用页面和脚本命令。
- `docs/onboarding.html`：开源贡献、数据契约和质量门入口。

### 4. 刷新 wiki

当你新增或修改 `docs/*.md` 报告后，运行：

```bash
python3 scripts/build_wiki.py docs
```

它会重新生成 `docs/index.html`、`docs/library.html`、`docs/papers.json`、`docs/search_index.json` 以及一组治理页面和机器可读数据。

### 5. 检查质量

提交前建议运行：

```bash
python3 scripts/check_quality.py docs
```

这个命令会检查生成物是否最新、frontmatter 和 taxonomy 是否有效、内部链接是否正常、页面脚本能否解析，并运行单元测试。

## 用 agent 阅读一篇新论文

AutoPaperReader 的完整自动化流程写在 `AGENTS.md`，子 agent 规范在 `.codex/agents/` 和 `.claude/agents/`。在 Codex / Claude Code 这类 agent 环境里，打开仓库后直接发类似请求：

```text
阅读这篇论文并生成报告：https://arxiv.org/abs/1706.03762
```

或者：

```text
阅读 FlashAttention-2，报告放到 docs/
```

agent 应按以下流程执行：

1. 定位 arXiv 页面，抽取题目、作者、提交日期、摘要和源码链接。
2. 根据 arXiv id 和方法名生成稳定 slug，例如 `1706.03762-attention`。
3. 在报告目录里查重；已有报告时先停止并询问是否强制重跑。
4. 下载 `https://arxiv.org/e-print/<arxiv_id>` 到 `sources/<slug>/arxiv/`。
5. 找到主 `.tex` 文件，派发 `paper-analyst` 写中文阅读报告。
6. 如果论文公开了代码仓库，克隆到 `sources/<slug>/code/` 并派发 `code-analyst` 补充实现观察。
7. 派发 `html-presenter` 或使用兜底脚本生成 `docs/<slug>.html`。
8. 运行 `python3 scripts/build_wiki.py docs` 刷新首页、索引和治理页面。

完成后你会得到：

```text
docs/<slug>.md      # 中文阅读报告
docs/<slug>.html    # 单篇 HTML 阅读页
docs/index.html     # 更新后的 wiki 首页
sources/<slug>/     # 本地论文源码和可能的代码仓库，默认不提交
```

## 手动新增报告

如果你暂时不使用 agent，也可以手动添加报告。

### 1. 复制模板

```bash
cp docs/guides/report.template.md docs/1706.03762-attention.md
```

### 2. 补齐 frontmatter

每篇报告建议以 YAML frontmatter 开头：

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

核心约定：

- `slug` 使用 `<arxiv_id>-<short-name>`，例如 `2310.06825-mistral-7b`。
- 非 arXiv 论文使用 `noarxiv-<year>-<short-name>`。
- `domains/tracks/problems` 用来描述结构层级。
- `topics/methods` 用来做交叉筛选。
- `research_line/line_role` 用来组织研究脉络。
- `status/reading_stage/review_stage` 用来管理阅读和复习状态。

### 3. 生成单篇 HTML

```bash
python3 scripts/render_report_html.py docs/1706.03762-attention.md docs/1706.03762-attention.html --slug 1706.03762-attention
```

### 4. 重建 wiki

```bash
python3 scripts/build_wiki.py docs
```

## 常用页面

| 页面 | 用途 |
| --- | --- |
| `docs/index.html` | 全文搜索、分类筛选、论文卡片浏览 |
| `docs/library.html` | 密集表格、批量筛选、批量 metadata patch |
| `docs/board.html` | 按状态拖拽论文卡片，导出状态 patch |
| `docs/priority.html` | 论文级优先级排序和复习计划 patch |
| `docs/review.html` | 待复习、缺复习计划和建议复习日期 |
| `docs/quality.html` | 弱元数据、标签别名、taxonomy drift 和重复报告 |
| `docs/taxonomy.html` | 分类体系、状态 workflow 和治理策略设计 |
| `docs/registry.html` | 标签注册表、alias、owner 和跨字段复用审计 |
| `docs/intake.html` | 批量粘贴候选论文并去重 |
| `docs/routing.html` | 根据标题/摘要推荐研究线和标签 |
| `docs/compare.html` | 多篇论文并排对比 |
| `docs/command.html` | 按场景组织常用命令 |
| `docs/onboarding.html` | 开源协作上手、schema、质量门 |

所有页面都是静态文件，可以直接双击打开，也可以托管到 GitHub Pages、Netlify、Vercel 或任意静态文件服务。

## 常用命令

刷新 wiki：

```bash
python3 scripts/build_wiki.py docs
```

检查生成物是否已经是最新：

```bash
python3 scripts/build_wiki.py docs --check
```

验证元数据、taxonomy 和内部链接：

```bash
python3 scripts/validate_wiki.py docs --strict-taxonomy
```

运行完整质量门禁：

```bash
python3 scripts/check_quality.py docs
```

导出论文库 CSV：

```bash
python3 scripts/export_library_csv.py docs --output docs/library.csv
```

导出阅读清单：

```bash
python3 scripts/export_reading_list.py docs --line "Attention Kernels" --min-importance 4 --output docs/exports/attention-kernels.md
```

把浏览器导出的 metadata patch 写回报告 frontmatter。先 dry-run：

```bash
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv
```

确认无误后写入：

```bash
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv --write
python3 scripts/build_wiki.py docs
```

重建某篇报告 HTML：

```bash
python3 scripts/render_report_html.py docs/<slug>.md docs/<slug>.html --slug <slug>
```

## 目录结构

```text
.
├── AGENTS.md                 # 主线 agent 工作流
├── CLAUDE.md                 # Claude Code 使用说明
├── .claude/agents/           # Claude 子 agent 规范
├── .codex/agents/            # Codex 子 agent 规范
├── docs/                     # 报告、静态 wiki、JSON 数据和 schema
├── scripts/                  # 构建、校验、导出和写回脚本
├── sources/                  # 本地论文源码和代码仓库，默认被 .gitignore 忽略
├── tests/                    # 脚本工作流测试
└── .github/                  # CI、issue 模板和 PR 模板
```

`docs/` 里最重要的文件：

- `docs/<slug>.md`：论文阅读报告源文件。
- `docs/<slug>.html`：单篇论文 HTML 阅读页。
- `docs/papers.json`：论文索引。
- `docs/search_index.json`：全文搜索索引。
- `docs/stats.json`：分类覆盖、研究线和队列统计。
- `docs/manifest.json`：发布清单和数据契约摘要。
- `docs/guides/taxonomy.json`：分类、状态 workflow、标签定义和批量 preset 配置。
- `docs/guides/*.schema.json`：面向编辑器、CI 和外部工具的数据契约。

## 配置分类和状态

分类和状态配置主要写在：

```text
docs/guides/taxonomy.json
```

你可以在这里维护：

- 标签别名和标签定义。
- `domain / track / problem / topic / method` 等分类字段。
- `research_line` 和 `line_role`。
- 多套 `status_workflows`，例如个人阅读流、项目实现流、复习流。
- 批量治理 preset，例如深读、安排复习、归档、代码检查。
- 分类过稀、过密、过载等治理阈值。

修改后运行：

```bash
python3 scripts/build_wiki.py docs
```

然后打开 `docs/taxonomy.html`、`docs/registry.html`、`docs/quality.html` 或 `docs/library.html` 检查效果。

## 候选论文和批量导入

推荐从浏览器页面开始：

1. 打开 `docs/intake.html`。
2. 粘贴多条 arXiv 链接、arXiv id 或论文标题。
3. 页面会和当前报告库、`docs/inbox.csv`、本次粘贴内容做去重。
4. 导出 `candidate_inbox.csv`。
5. 使用脚本预览并写入：

```bash
python3 scripts/apply_inbox_items.py docs --input ~/Downloads/candidate_inbox.csv
python3 scripts/apply_inbox_items.py docs --input ~/Downloads/candidate_inbox.csv --write
python3 scripts/build_wiki.py docs
```

也可以手动维护 `docs/inbox.csv`：

```csv
id,title,link,status,priority,tags,note,added_at
paper-1,Example Paper,https://arxiv.org/abs/2601.00001,queued,high,LLM Serving;Batching,先读方法,
```

## 发布到 GitHub Pages

本项目的静态站点在 `docs/` 目录下。上传到 GitHub 后，可以在仓库设置里启用 Pages：

1. 打开 `Settings -> Pages`。
2. Source 选择 `Deploy from a branch`。
3. Branch 选择 `main`，目录选择 `/docs`。
4. 保存后等待 GitHub Pages 构建完成。

如果使用 GitHub CLI：

```bash
gh repo create <owner>/<repo> --public --source=. --remote=origin --push
gh api --method POST repos/<owner>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/docs'
```

## 开源协作

- 新增候选论文：使用 GitHub issue 表单 `Paper intake`，或直接提交 `docs/inbox.csv` / 报告 PR。
- 修报告质量：使用 `Report quality issue`，说明具体 slug、页面或字段。
- 调整分类体系：使用 `Taxonomy governance`，说明要合并、拆分或新增的标签和原因。
- 提交 PR 前运行 `python3 scripts/check_quality.py docs`。
- 如果改动了 `docs/*.md`、`docs/guides/taxonomy.json` 或 `docs/inbox.csv`，通常也需要提交重新生成后的 `docs/*.html` 和 `docs/*.json`。

## 数据和隐私说明

- `sources/` 默认在 `.gitignore` 中，不会把下载的论文源码和克隆的代码仓库提交到 Git。
- `docs/` 是发布目录。放进 `docs/` 的 Markdown、HTML、JSON 和图片资产会被视为可公开内容。
- 上传公开仓库前，请确认报告中没有私人笔记、访问 token、内部链接或未授权材料。

## License

本项目使用 [MIT License](./LICENSE)。
