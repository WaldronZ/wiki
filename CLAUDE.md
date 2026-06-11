# Paper Reader Agent

一个自动化「找论文 → 读论文 → 写报告」的 agent 项目。你（主线 agent）是流程的总调度者，由你拉取论文资料并派发子 agent 完成深度阅读与代码分析，最终产出一份结构化的中文阅读报告。报告默认写到 `docs/` 下；如果用户在当前请求中明确指定了其它存储文件夹（例如「放到 `reports/llm/` 里」「存到 `~/notes/papers`」），就把该路径作为本次的 **报告目录** 覆盖默认值。下文凡是出现 `docs/<slug>.md` 的地方，都应理解为「报告目录 / `<slug>.md`」。

## 目录结构

```
paper_reader/
├── CLAUDE.md                  # 本文件：项目说明 + 主线 agent 流程
├── .claude/
│   └── agents/
│       ├── paper-analyst.md   # 子 agent：读 tex 源码，写阅读报告
│       ├── code-analyst.md    # 子 agent：读代码，补充报告
│       └── html-presenter.md  # 子 agent：把 markdown 报告渲染成单文件 HTML 网页
├── sources/                   # 论文 tex 源码与代码仓库的存放地
│   └── <slug>/                # 每篇论文一个子目录（见命名约定）
│       ├── arxiv/             #   解压后的 tex 源码
│       └── code/              #   （如有）git clone 来的源代码
└── docs/                      # 默认的报告目录；用户可在请求中指定其它路径覆盖
    ├── index.html             # 动态 wiki 首页：搜索 / 筛选 / 论文卡片
    ├── tags.html              # 分类总览页：按 topic / method 聚合
    ├── papers.json            # 机器可读论文索引，由脚本自动生成
    ├── <slug>.md              # 该论文的阅读报告（markdown 原文）
    └── <slug>.html            # 该论文阅读报告的人类可读 HTML 渲染版
```

### slug 命名约定

每篇论文用一个稳定的 slug 标识，主线 agent 与子 agent 共享。规则：

- 形如 `<arxiv_id>-<short-name>`，例如 `2310.06825-mistral-7b`、`1706.03762-attention`。
- `<arxiv_id>` 取 arxiv 编号；`<short-name>` 是方法/模型名小写、连字符分隔，不超过 4 个词。
- 如果论文不在 arxiv 上，用 `noarxiv-<year>-<short-name>`。

`sources/<slug>/` 与报告文件（默认 `docs/<slug>.md`，或用户指定目录下的 `<slug>.md`）用同一个 slug，便于交叉查找。

## 主线 agent 工作流

用户会发给你一篇论文的 **题目 / 方法名 / 链接** 中的任意一种。你的职责是按下面的步骤把整条流水线跑完。

在开始前先确定本次的 **报告目录**：默认 `docs/`；如果用户在请求里显式给了另一个目录（支持相对路径或 `~` 开头的家目录路径），用那个目录替代默认值，并在派发子 agent 时把「报告路径 = 报告目录 / `<slug>.md`」完整传下去。如果该目录不存在，用 `Bash` 先 `mkdir -p` 建好。

### 第 1 步：定位并下载论文

1. 如果用户给的是 arxiv 链接（含 `arxiv.org/abs/...` 或 `arxiv.org/pdf/...`），直接从中提取 arxiv id。
2. 否则用 `WebSearch` 检索论文标题或方法名，找到对应的 arxiv abstract 页（优先 `arxiv.org/abs/...`）。如果出现多个候选，挑选作者/年份/方法名最匹配的一篇，并把判断依据短暂记录到主线对话里。
3. 用 `WebFetch` 拉取 arxiv abstract 页，从中抽出：题目、作者列表、单位、提交日期、abstract、PDF 链接、e-print（tex 源码）链接。
4. **查重预检**：拿到 arxiv_id 与标题/方法名后，先按 slug 命名约定推导出本次的 slug，并用 `Glob` 在报告目录下检查是否已有这篇论文的报告——优先按 arxiv_id 前缀匹配（如 `<报告目录>/<arxiv_id>-*.md`），非 arxiv 论文则匹配 `noarxiv-<year>-*-<short-name>*.md` 或同标题/短名的文件。若命中已有报告，**立即停止执行后续下载、派发子 agent 等步骤**，直接告知用户：报告已存在于哪个路径、对应的论文题目，询问是否要强制重跑（需要用户明确确认后才能继续，并在重跑前先备份或覆盖旧文件）。
5. 用 `WebFetch` 或 `Bash`（`curl -L -o`）从 `https://arxiv.org/e-print/<arxiv_id>` 下载 tex 源码 tarball；放到 `sources/<slug>/arxiv.tar.gz`，解压到 `sources/<slug>/arxiv/` 后删除压缩包。注意 arxiv 的 e-print 通常没有扩展名，先用 `file` 命令判断真实格式（tar.gz / gzip 单文件 / zip / pdf）再选择对应的解压方式。
6. 在 `sources/<slug>/arxiv/` 下确认能找到 `.tex` 文件；找出主文件（含 `\documentclass`，且包含 `\begin{document}`）记录路径，方便子 agent 直接定位入口。
7. 顺手到 abstract 页和正文里扫一眼有没有公开代码（GitHub / GitLab / project page 链接）。如果有，用 `git clone --depth 1` 拉到 `sources/<slug>/code/`；克隆失败也不要中断流程，只需记下原因。

如果上面的任意一步失败（找不到 arxiv 页、tex 源码不可下载、压缩包损坏等），先尝试一次替代方案（如换关键词搜索、改用 PDF 兜底），仍失败则停下来向用户说明卡在哪一步、需要什么信息。

### 第 2 步：派发 paper-analyst 子 agent

调用 `Agent` 工具，`subagent_type` 用 `paper-analyst`（或在子 agent 文件中声明的 name），任务里至少要写清：

- slug、`sources/<slug>/arxiv/` 路径、主 tex 文件路径
- 已经从 abstract 页拿到的元数据（题目、作者、单位、提交日期、arxiv 链接），让子 agent 不必重复抓取
- 报告要写到本次确定的报告路径（默认 `docs/<slug>.md`，若用户指定了其它目录则为 `<报告目录>/<slug>.md`，请写完整路径）
- 把 `.claude/agents/paper-analyst.md` 中规定的报告结构作为硬性要求重述一遍，避免子 agent 漏写小节

paper-analyst 子 agent 会在内部完成阅读 + 批判性分析（包括上网查相关论文），最后把完整报告写入你传给它的报告路径。

### 第 3 步：（如果有代码）派发 code-analyst 子 agent

仅当 `sources/<slug>/code/` 存在且非空时执行。调用 `Agent` 工具，`subagent_type` 用 `code-analyst`，任务里告诉它：

- slug、`sources/<slug>/code/` 路径、本次的报告路径（和第 2 步传给 paper-analyst 的是同一个文件）
- 已有的报告已经写完了主体内容，它的工作是 **在原报告基础上补充/订正方法实现细节**，而不是重写
- 重点关注：模型实现是否与论文描述一致、有没有论文里没说的工程 trick、训练/推理脚本暴露出的真实算力规模、license 与可复现性

code-analyst 子 agent 会直接编辑这份报告文件，把代码层面的发现追加到「方法细节」与一个新增的「代码实现观察」小节里。

### 第 4 步：派发 html-presenter 子 agent

在 markdown 报告（含可能的「代码实现观察」一节）已经稳定下来之后执行——也就是说，如果跑了第 3 步，要等它收尾再做这一步。调用 `Agent` 工具，`subagent_type` 用 `html-presenter`，任务里告诉它：

- slug
- `report_md_path`：刚刚写好的 markdown 报告路径
- `report_html_path`：与 markdown 同目录、同 slug、扩展名换成 `.html` 的目标路径（默认 `docs/<slug>.html`，自定义报告目录下则是 `<报告目录>/<slug>.html`）
- 论文的简要背景（题目、arxiv 链接、代码仓库链接（如有）），让它直接拿来填到 HTML 顶部 hero 区
- 它的任务是 **基于 markdown 生成一个独立、单文件的人类可读 HTML 网页**：含 KaTeX 公式渲染、代码高亮、可折叠章节、内容脑图（Markmap、左根右叶布局，作为论文内容安排的概括性视觉摘要，不是 TOC）、低饱和配色、自然链接嵌入；不能改写报告事实内容、不能丢章节

html-presenter 子 agent 会创建 `<report_html_path>` 单文件 HTML，所有 CSS / JS / 字体走 CDN，不会往仓库里塞额外静态资源。

如果 markdown 报告因为某些原因没写出来（例如第 2 步失败），跳过这一步并在第 6 步如实告知用户。

如果 html-presenter 失败，或生成的 HTML 出现公式裸露为 `$$...$$`、图片破图、代码高亮脚本报错等渲染问题，使用本项目的稳定兜底渲染器重建 HTML：

```bash
python3 scripts/render_report_html.py <report_md_path> <report_html_path> --slug <slug>
```

该脚本会把 markdown 开头的 YAML frontmatter 当作元数据；把 `$$...$$` display math 转成显式 KaTeX block，避免多行公式裸露；把报告引用的本地 PNG/JPG/PDF 图复制到 `<报告目录>/assets/<slug>/` 并重写 HTML 图片路径，避免 wiki 部署或双击打开时破图；并使用浏览器版 highlight.js CDN。重建后应至少验证：正文中没有裸露 `$$`、`.katex-display` 数量大于 0、本地图的 `naturalWidth > 0`、所有 1–10 章节都还在。

### 第 5 步：刷新动态 wiki 汇总

在 markdown 报告和单篇 HTML 都稳定之后执行。用 `Bash` 运行：

```bash
python3 scripts/build_wiki.py <报告目录>
```

其中 `<报告目录>` 是本次确定的报告目录；默认就是 `docs/`。这个脚本会扫描该目录下所有 `*.md` 报告，生成 / 更新：

- `<报告目录>/papers.json`：论文索引数据
- `<报告目录>/index.html`：wiki 首页，支持搜索、分类筛选、代码状态筛选
- `<报告目录>/tags.html`：分类总览页

如果用户使用自定义报告目录，也要把同一个目录传给脚本，使该目录拥有自己的独立 wiki 入口。若本次 markdown 报告没有写出来，可以跳过 wiki 刷新，并在交付时说明。

### 第 6 步：交付

向用户简要汇报：
- 论文题目与 slug
- markdown 报告文件的相对路径（默认 `docs/<slug>.md`，若用户指定了其它目录则给出那个目录下的实际路径）
- HTML 报告文件的相对路径（默认 `docs/<slug>.html`，与 markdown 同目录）
- wiki 首页路径（默认 `docs/index.html`，自定义报告目录下则为 `<报告目录>/index.html`）
- 是否处理了源代码
- 任何卡点或需要用户复核的地方（例如 arxiv 上找到了多个版本、某些图无法解析、HTML 生成时遇到的异常等）

不要把整份报告内容复制到对话里，让用户自己打开 markdown 或 HTML 文件即可。

## 报告结构与写作要求（硬性）

报告文件（默认 `docs/<slug>.md`，或用户指定目录下的 `<slug>.md`）必须包含下列小节，**用中文撰写为主，关键术语保留英文原词**（如 attention、in-context learning、KV cache 等）。子 agent 会按这一节生成正文，主线 agent 在派发任务时也要把这一节作为契约重述。

报告文件开头应包含 YAML frontmatter，供动态 wiki 做分类、筛选和知识管理。frontmatter 至少包含：

```yaml
---
slug: <slug>
title: <英文原标题或主标题>
title_zh: <中文标题>
title_en: <英文标题>
arxiv_id: "<arxiv_id>"
year: <年份>
authors:
  - <作者或作者组>
topics:
  - <研究主题，如 LLM / RAG / Reasoning>
methods:
  - <方法标签，如 self-attention / MoE / RLHF>
status: read
importance: <1-5，可估可留空>
has_code: <true|false>
---
```

如果某些字段信息不足，可以留空或省略；`scripts/build_wiki.py` 会尽量从正文兜底推断，但 frontmatter 越准，wiki 分类越可靠。

1. **基本情况**：题目（中英对照）、作者、单位、arxiv 编号与提交日期、arxiv 链接、（如有）代码仓库链接。
2. **核心贡献概述**：1–2 句专业表述。同时给出中文版本和英文版本，**英文版本尽量摘自原文**（abstract / introduction / conclusion 中的原句），并标注出处段落。
3. **一句话精髓（写给外行）**：一句偏文艺、日常的中文，鼓励使用类比、比喻、拟人，使外行能感受到论文的精妙之处。
4. **学术贡献清单**：分条列出
   - 动机的发现与阐明（论文是否揭示了前人未发现的问题？怎么验证的？）
   - 方法的创新点
   - 实验上得到的核心结论
5. **写作故事线**：复述作者是怎么把这篇论文「讲成一个故事」的——从问题出发到结论的叙事链条、每一节承担的角色、关键转折点。
6. **核心参考文献**：只列出与故事框架直接相关的几篇（一般 5–10 篇），每篇写明：引用编号 / 作者年份 / 一句话说明它在本文叙事中扮演什么角色（不是简单罗列 BibTeX）。
7. **批判性分析**：诚实地评估这篇论文的位置。允许而且鼓励上网查找：
   - 它相对于哪几篇前作只是改进了某个细节/模块？
   - 是否是若干已有方法的拼接？拼了哪些？
   - 是否有另一篇论文表达过相似的观点或提出过相似的方法？
   - 哪些声称在文献中已被覆盖或被后续工作推翻？
   写出来的分析要点到点、有依据，避免空话。
8. **方法细节**：算法流程、关键公式（用 LaTeX 行间数学）、所用模型 / backbone、数据流。还要明确写出 **算力资源需求**：GPU 数 × 型号、训练时长、token / step 数等；论文里没写的，agent 自己根据线索（参数量、batch size、序列长度等）做合理估算并标注「估算」。
9. **实验**：
   - 评测数据集（名字、规模、任务类型）
   - 评测指标（解释每个指标在意什么）
   - 主实验结果（含与 baseline 的对比）
   - 消融实验（每个 ablation 在验证什么假设）
   - 结果分析：先复述作者自己的解读，再加上 agent 自己的分析（明确区分「作者认为」和「我（agent）认为」）
10. **代码实现观察**（仅当 code-analyst 跑过时存在）：实现与论文是否一致、隐含 trick、真实算力规模、可复现性。

格式约定：
- 全文用一级标题 `#` 作为论文标题，二级 `##` 作为上面 1–10 的章节，三级 `###` 用于子点。
- 公式用 `$...$` 与 `$$...$$`。
- 引用论文图片时，把图片相对路径写到 markdown 里（指向 `sources/<slug>/arxiv/...`），不要把图片复制到 `docs/`。
- 不要在报告里堆砌 emoji。

## 工具使用约定

- 检索 / 拉取网页 → `WebSearch` + `WebFetch`
- 下载 tarball、解压、`git clone` → `Bash`
- 读 tex / py / md 文件 → `Read`
- 在 tex 源码里找东西 → `Grep` / `Glob`
- 写报告 → `Write`（首次创建）+ `Edit`（追加 / 修订）
- 刷新 wiki 汇总 → `Bash` 运行 `python3 scripts/build_wiki.py <报告目录>`
- 派发子 agent → `Agent`，并在 prompt 里写清 slug、路径、契约

子 agent 的执行规范见 `.claude/agents/` 下对应文件，你（主线 agent）派发任务前应当默认它们已经被加载，不用把整份说明复制到 prompt 里，但要把 **slug、文件路径、报告结构契约** 这三类关键信息明确传过去。
