# AutoPaperReader

AutoPaperReader 是一个自动化「找论文 -> 读论文 -> 写报告」的 agent 项目。

它的目标是把一篇论文从检索、下载源码、分析论文、分析配套代码，到最终输出结构化中文阅读报告的流程串起来，并把产物（包括 Markdown 报告和 HTML 展示网页）统一组织到固定目录中。

项目还会把这些逐篇报告汇总成一个轻量动态 wiki：所有汇总页都提供全局快速跳转入口，方便在大量页面、论文、机器数据和治理命令之间切换；`docs/command.html` 提供场景化命令中心，按阅读、导入、分类治理、状态工作流、研究综合和发布开源组织入口；`docs/index.html` 提供全文搜索、研究线、分类、状态体系、代码/重要性/复习筛选、排序、分页和可分享 URL 状态；`docs/library.html` 提供适合大量论文批量管理的密集表格视图；`docs/board.html` 提供可拖拽状态看板，可按 workflow 动态切换状态列并保留 URL 状态；`docs/workflow.html` 提供状态工作流中心，集中对比 active workflow、状态分布和 drift；`docs/status.html` 提供运行时状态选择器，可动态选择 workflow/status/reading stage/review stage 并复制共享视图或配置片段；`docs/views.html` 提供可筛选的视图目录，把 shared views、系统队列、研究线和状态 workflow 入口集中成可复制 JSON，也能按视图直接生成 metadata patch；`docs/presets.html` 提供批量治理 preset 目录，集中展示字段写入、patch columns 和 workflow 兼容性；`docs/curation.html` 提供逐篇分类成熟度清单，按论文打分并定位缺失字段、稀疏标签和补齐队列；`docs/queues.html` 提供运营队列，把缺分类、缺复习、到期复习、代码未检查和高优先级待读变成可执行批量入口；`docs/cohorts.html` 提供分类组合队列，按研究线、主题、方法、状态等交叉维度找过载组合、单例组合和专题候选；`docs/pivot.html` 提供任意两个分类维度的交叉透视表；`docs/compare.html` 提供多论文并排对比；`docs/taxonomy_map.html` 提供分类图谱，审计 domain/track/problem/topic/method 的节点和共现边；`docs/clusters.html` 提供研究簇驾驶舱，按研究线查看簇风险、拆分候选和代表论文；`docs/roadmap.html` 提供研究路线图，按研究线组织阶段覆盖、里程碑、代表论文和下一步计划；`docs/scale.html` 提供规模就绪视图，评估大库容量、索引体量和治理瓶颈；`docs/ownership.html` 提供 owner 工作台，按研究线负责人聚合工作量、风险和治理队列；`docs/routing.html` 提供新论文分类路由器，粘贴标题/摘要即可推荐研究线、标签和相似论文；`docs/onboarding.html` 提供开源上手控制台，集中贡献路径、质量门、数据契约和常用命令；`docs/catalog.html` 提供面向桌面软件、DMG 封装和开源接入的数据/API 目录；`docs/intake.html` 提供批量导入台，可粘贴多条论文链接并先做库内/inbox/批内去重；`docs/inbox.html` 提供候选论文待处理池；`docs/dedupe.html` 提供去重工作台，集中治理库内报告、候选池和导入队列重复项；`docs/registry.html` 提供标签注册表，集中管理分类标签、alias、跨字段复用和 owner 信号；`docs/quality.html` 提供质量治理、标签归一化建议和 taxonomy drift 门禁；`docs/review.html` 提供复习队列和建议复习日期；`docs/freshness.html` 提供报告时效治理、过期分析和研究线维护队列；`docs/dashboard.html` 提供分类覆盖、研究线健康度和待处理队列；`docs/release.html` 提供发布摘要、页面入口、机器可读数据清单、artifact inventory、SHA-256 和治理 playbooks；`docs/snapshot.html` 提供当前发布基线、风险队列、治理策略和 artifact hash 快照；`docs/actions.html` 提供统一行动中心，汇总复习、质量、分类、重复项和 inbox 待办；`docs/collections.html` 提供共享视图、智能队列和研究线集合入口；`docs/balance.html` 提供分类均衡复盘，集中查看分类维度健康度、长尾、过载和空候选；`docs/coverage.html` 提供研究线分类覆盖地图，按研究线定位 domain/track/problem/topic/method 缺口；`docs/facets.html` 提供分类工作台，集中审计标签规模、长尾、过载分类和字段目录；`docs/related.html` 提供标签共现和相似论文关系发现；`docs/gaps.html` 提供研究缺口和下一步行动建议；`docs/taxonomy.html` 提供分类治理、状态矩阵、研究线角色矩阵、浏览器内状态工作流设计器和分类变更 patch 预览；`docs/timeline.html` 提供按年份和研究线浏览的路线时间轴；`docs/matrix.html` 提供研究线 x 年份覆盖矩阵；`docs/lines/index.html` 提供研究线入口；`docs/tags.html` 提供分类总览；`docs/papers.json` 提供机器可读索引；`docs/search_index.json` 提供正文检索索引；`docs/stats.json` 提供机器可读运营指标；`docs/quality.json` 提供元数据质量、标签别名建议与运营队列报告；`docs/curation.json` 提供机器可读逐篇分类成熟度、缺失字段和补齐建议；`docs/queues.json` 提供机器可读运营队列、推荐 preset、样例论文和批量写回入口；`docs/cohorts.json` 提供机器可读分类组合队列、过载组合、单例组合和专题候选；`docs/review.json` 提供机器可读复习计划；`docs/freshness.json` 提供机器可读报告新鲜度和过期队列；`docs/taxonomy_actions.json` 提供可分派的分类治理任务；`docs/actions.json` 提供统一行动队列；`docs/command.json` 提供场景化命令中心的入口、队列、数据和命令契约；`docs/workflow.json` 提供机器可读状态工作流配置、分布和漂移审计；`docs/status.json` 提供运行时状态选择契约、状态字段选项和论文状态快照；`docs/views.json` 提供机器可读共享视图、系统队列、研究线视图和 workflow/status 视图目录；`docs/presets.json` 提供机器可读批量治理 preset、字段契约和 workflow 兼容性；`docs/batch.json` 提供可执行论文批次；`docs/collections.json` 提供共享视图、智能集合和研究线集合的机器可读入口；`docs/coverage.json` 提供机器可读研究线分类覆盖地图；`docs/gaps.json` 提供机器可读研究缺口和下一步行动队列；`docs/pivot.json` 提供机器可读分类透视表维度、论文投影和交叉分布；`docs/compare.json` 提供机器可读论文对比数据和推荐集合；`docs/taxonomy_map.json` 提供分类节点、共现边、研究线簇和治理建议；`docs/clusters.json` 提供研究簇、拆分候选、代表论文和簇风险；`docs/roadmap.json` 提供研究线路线图、阶段覆盖、里程碑和下一步计划；`docs/scale.json` 提供规模就绪评分、容量投影和大库治理风险；`docs/ownership.json` 提供研究线 owner、工作量、风险和队列数据；`docs/routing.json` 提供新论文分类路由画像、推荐权重和相似论文签名；`docs/onboarding.json` 提供开源贡献路径、质量门和数据契约清单；`docs/catalog.json` 提供页面、机器数据、契约字段和集成 recipe 的机器可读目录；`docs/intake.json` 提供批量导入去重索引、默认字段和 inbox CSV 契约；`docs/dedupe.json` 提供重复报告、候选重复项和治理建议；`docs/registry.json` 提供分类标签注册表、alias、字段复用和治理信号；`docs/facets.json` 提供分类字段目录、候选值、样例 slug、治理动作和跳转入口；`docs/snapshot.json` 提供机器可读治理快照；`docs/manifest.json` 提供发布状态、入口清单、数据契约和可校验产物清单。

日常维护时可以先打开 `docs/priority.html`：它会把复习到期、缺复习计划、弱元数据、taxonomy drift、分类粒度、代码观察和阅读阶段合成论文级优先级，并同步输出 `docs/priority.json` 供桌面端、DMG 或外部脚本读取。页面还能按当前筛选结果导出 `priority_review_patch.csv`，直接用 `scripts/apply_library_metadata.py` dry-run / writeback 补 `next_review` 和 `review_stage`。

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
│   ├── workflow.html
│   ├── status.html
│   ├── views.html
│   ├── presets.html
│   ├── pivot.html
│   ├── compare.html
│   ├── taxonomy_map.html
│   ├── clusters.html
│   ├── roadmap.html
│   ├── scale.html
│   ├── ownership.html
│   ├── routing.html
│   ├── onboarding.html
│   ├── catalog.html
│   ├── intake.html
│   ├── inbox.html
│   ├── dedupe.html
│   ├── registry.html
│   ├── curation.html
│   ├── queues.html
│   ├── cohorts.html
│   ├── quality.html
│   ├── review.html
│   ├── dashboard.html
│   ├── release.html
│   ├── collections.html
│   ├── facets.html
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
│   ├── curation.json
│   ├── queues.json
│   ├── cohorts.json
│   ├── review.json
│   ├── workflow.json
│   ├── status.json
│   ├── views.json
│   ├── presets.json
│   ├── batch.json
│   ├── collections.json
│   ├── pivot.json
│   ├── compare.json
│   ├── taxonomy_map.json
│   ├── clusters.json
│   ├── roadmap.json
│   ├── scale.json
│   ├── ownership.json
│   ├── routing.json
│   ├── onboarding.json
│   ├── catalog.json
│   ├── intake.json
│   ├── dedupe.json
│   ├── registry.json
│   ├── facets.json
│   ├── manifest.json
│   ├── guides/
│   │   ├── taxonomy.md
│   │   ├── taxonomy.json
│   │   ├── report.template.md
│   │   ├── metadata.schema.json
│   │   ├── inbox.schema.json
│   │   ├── taxonomy.schema.json
│   │   ├── facets.schema.json
│   │   ├── batch.schema.json
│   │   ├── actions.schema.json
│   │   ├── catalog.schema.json
│   │   ├── bootstrap_bundle.schema.json
│   │   ├── manifest.schema.json
│   │   ├── snapshot.schema.json
│   │   ├── workflow.schema.json
│   │   ├── status.schema.json
│   │   ├── views.schema.json
│   │   ├── presets.schema.json
│   │   ├── curation.schema.json
│   │   ├── queues.schema.json
│   │   └── cohorts.schema.json
│   └── .gitkeep
├── scripts/
│   ├── apply_inbox_items.py
│   ├── apply_library_metadata.py
│   ├── apply_review_plan.py
│   ├── apply_shared_views.py
│   ├── apply_status_workflow.py
│   ├── apply_taxonomy_aliases.py
│   ├── build_wiki.py
│   ├── check_quality.py
│   ├── check_wiki_js.js
│   ├── export_actions.py
│   ├── export_queues.py
│   ├── export_cohorts.py
│   ├── export_gaps.py
│   ├── export_library_csv.py
│   ├── export_reading_list.py
│   ├── export_views.py
│   ├── export_taxonomy_actions.py
│   ├── export_taxonomy_load.py
│   ├── export_taxonomy_registry.py
│   ├── validate_wiki.py
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
- `scripts/apply_inbox_items.py` 用于把外部候选论文 CSV 安全合并进 `docs/inbox.csv`，默认只 dry-run
- `scripts/apply_review_plan.py` 用于把 `docs/review.json` 的建议复习日期安全写回报告 frontmatter，默认只 dry-run
- `scripts/apply_shared_views.py` 用于把首页/论文库导出的 saved views 或复制的 shared view JSON 安全合并到 `guides/taxonomy.json`，默认只 dry-run
- `scripts/apply_status_workflow.py` 用于把 `docs/taxonomy.html` 下载的 `taxonomy_status_workflow.json` 安全合并到 `guides/taxonomy.json`，默认只 dry-run
- `scripts/apply_governance_policy.py` 用于把 `docs/taxonomy.html` 下载的 `taxonomy_governance_policy.json` 安全合并到 `guides/taxonomy.json`，默认只 dry-run
- `scripts/export_library_csv.py` 用于把 `papers.json`、`review.json` 和 `quality.json` 合并导出成 CSV，便于用表格工具批量管理
- `scripts/export_reading_list.py` 用于按研究线、状态、方向、主题、方法或重要性导出 Markdown 阅读清单、BibTeX 或链接列表
- `scripts/export_actions.py` 用于把 `actions.json` 导出成统一 checklist、审计 CSV 或可自定义任务状态的项目任务 CSV
- `scripts/export_catalog_bundle.py` 用于按 `catalog.json` 把桌面端/DMG 启动所需核心 JSON 打成单个 bootstrap bundle，也可只导出 hash/shape manifest
- `scripts/validate_catalog_bundle.py` 用于校验 bootstrap bundle 的结构、payload 模式以及与 `docs/` 本地文件匹配的 size/SHA-256
- `scripts/export_queues.py` 用于把 `queues.json` 中的运营队列导出成 checklist、审计 CSV、项目任务 CSV 或可写回 metadata 的 patch CSV
- `scripts/export_cohorts.py` 用于把 `cohorts.json` 中的分类组合队列导出成 checklist、审计 CSV、项目任务 CSV 或可写回 metadata 的 patch CSV
- `scripts/export_batches.py` 用于把 `batch.json` 中的可执行论文批次导出成 checklist、审计 CSV、项目任务 CSV 或可写回的 metadata patch CSV
- `scripts/export_collections.py` 用于把 `collections.json` 中的共享视图、智能队列和研究线集合导出成 checklist、审计 CSV 或项目任务 CSV
- `scripts/export_coverage.py` 用于把 `coverage.json` 中的研究线分类覆盖缺口导出成 checklist、审计 CSV、项目任务 CSV 或可写回的 metadata patch CSV
- `scripts/export_gaps.py` 用于把 `gaps.json` 中的研究缺口和下一步行动导出成 checklist、审计 CSV 或项目任务 CSV
- `scripts/export_views.py` 用于把 `views.json` 中的共享视图、系统队列和状态/研究线入口导出成 checklist、审计 CSV、桌面侧边栏 JSON 或可写回 metadata 的 patch CSV
- `scripts/export_ownership.py` 用于把 `ownership.json` 中的 owner 工作量、风险队列和研究线责任导出成 checklist、审计 CSV 或项目任务 CSV
- `scripts/export_roadmap.py` 用于把 `roadmap.json` 中的研究线风险、角色缺口和下一步行动导出成路线 checklist、审计 CSV 或项目任务 CSV
- `scripts/export_taxonomy_actions.py` 用于把 `taxonomy_actions.json` 导出成 Markdown checklist、审计 CSV 或项目任务 CSV，便于分派分类治理任务
- `scripts/export_taxonomy_change.py` 用于把任意分类/状态字段的旧值改名为新值，导出可审计且可写回的 metadata patch CSV
- `scripts/export_taxonomy_balance.py` 用于把 `stats.json` 中的分类均衡度导出成复盘 checklist、CSV 或项目任务 CSV
- `scripts/export_taxonomy_load.py` 用于把 `quality.json` 中的分类粒度审计导出成 Markdown checklist、审计 CSV 或可写回的分类 patch CSV
- `scripts/export_taxonomy_registry.py` 用于把 `registry.json` 导出成标签治理 checklist、审计 CSV、项目任务 CSV 或可写回的分类 patch CSV
- `scripts/apply_library_metadata.py` 用于把编辑后的 CSV 分类/状态字段安全写回报告 frontmatter，默认只 dry-run
- `scripts/apply_taxonomy_aliases.py` 用于把 `quality.json` 中的标签别名建议安全合并到 `guides/taxonomy.json`，默认只 dry-run
- `scripts/check_quality.py` 是本地一键质量门禁，和 GitHub Actions 使用同一组检查
- `.github/ISSUE_TEMPLATE/` 和 `.github/PULL_REQUEST_TEMPLATE.md` 提供开源协作入口，用于规范论文候选、分类治理、报告质量问题和 PR 检查项

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
- 所有 wiki 汇总页：提供全局快速跳转，可搜索主要页面、机器数据、共享视图、治理 playbook、常用命令和全部单篇报告
- `docs/command.html`：命令中心，按 daily reading、paper intake、taxonomy governance、workflow/status、research synthesis 和 release/open-source 场景组织入口、队列和命令
- `docs/library.html`：论文库表格，适合大量论文的密集筛选、排序、列管理、密度切换、状态体系切换、治理 preset 和批量管理
- `docs/board.html`：状态看板，按自定义 `status` 分列，可动态切换 `status_workflows` 并保留 URL 状态，也可临时新增状态列，拖拽后导出 `status_board_patch.csv`
- `docs/workflow.html`：工作流中心，集中对比多套 `status_workflows`、active workflow 分布、状态定义覆盖、未配置状态 drift、空字段和绑定 workflow 的共享视图
- `docs/status.html`：状态选择器，运行时动态选择 workflow/status/reading stage/review stage，并生成可跳转 URL、共享视图 JSON、workflow 配置片段和可 dry-run 的状态写回 patch
- `docs/views.html`：视图目录，集中筛选 shared views、系统队列、研究线视图和 workflow/status 视图，可复制 shared view JSON，也可按视图命中 slug 生成 metadata patch CSV / 导出命令
- `docs/presets.html`：治理预设目录，集中展示 `bulk_presets` 的字段写入、CSV patch 列和 workflow 兼容性，便于大量论文批量迁移状态或安排复习
- `docs/batch.html`：批次规划页，按分类、状态、阅读阶段和复习缺口切分可执行论文批次；选中批次后可复制任务、导出阅读清单命令，或直接生成 `metadata-patch.csv` 写回状态/复习/分类字段
- `docs/pivot.html`：分类透视表，支持在 research line、domain、track、problem、topic、method、status、year 等维度之间动态交叉分析
- `docs/compare.html`：论文对比页，按搜索、研究线、方向、状态或推荐集合选择论文，并排比较分类、状态、复习计划、评分和代码线索
- `docs/taxonomy_map.html`：分类图谱页，按节点和共现边审计 research line、domain、track、problem、topic 和 method 的连接关系，可筛选并导出边 CSV
- `docs/clusters.html`：研究簇驾驶舱，按研究线聚合簇风险、角色/状态分布、top labels、拆分候选和代表论文，可导出 `research_clusters.csv`
- `docs/roadmap.html`：研究路线图，按研究线汇总角色覆盖、年份里程碑、代表论文、风险和下一步行动，可导出 `research_roadmap.csv`
- `docs/scale.html`：规模就绪页，评估搜索索引、分类图谱、动态状态体系、行动队列和治理风险在 100/500/1000/5000 篇规模下的增长压力
- `docs/ownership.html`：Owner 工作台，按 `research_line_owners` 聚合 owner/team/维护节奏、工作量、风险分和缺分类/复习/代码观察队列，可筛选并导出 `ownership_workload.csv`
- `docs/routing.html`：新论文分类路由器，粘贴标题、摘要或关键词后，根据现有研究线、taxonomy 标签和相似论文推荐 frontmatter 分类 patch
- `docs/onboarding.html`：开源上手控制台，汇总贡献路径、open-source readiness、issue / PR 模板、schema 契约和可复制质量门命令
- `docs/catalog.html`：数据/API 目录页，集中列出页面入口、JSON 数据资源、字段集合、消费者提示、数据契约和集成 recipes
- `docs/intake.html`：批量导入台，粘贴多条 arXiv 链接、id 或标题后，先和当前库、inbox、批内重复项去重，再导出 `candidate_inbox.csv`
- `docs/inbox.csv`：候选论文待处理池源数据，可手动追加 id/title/link/status/priority/tags/note/added_at
- `docs/inbox.html`：候选论文待处理池，支持筛选、去重提示、复制阅读任务、下载当前筛选 CSV 和复制 inbox 模板
- `docs/dedupe.html`：去重工作台，集中治理库内重复报告、候选池撞车和 inbox 内部重复，可导出 `dedupe_review.csv`
- `docs/registry.html`：标签注册表，把所有分类标签、状态值、alias、跨字段复用、owner 和治理信号整理成可筛选字典，可导出 `taxonomy_registry.csv`
- `docs/curation.html`：分类成熟度页，按每篇论文计算研究线、结构分类、topic/method、阅读状态和复习字段完整度，定位缺失字段、稀疏标签和可批量补齐队列
- `docs/queues.html`：运营队列页，把缺分类、缺复习计划、到期复习、有代码未检查和高优先级待读队列整理成可筛选、可跳转、可批量写回的入口
- `docs/cohorts.html`：分类组合页，预计算研究线、结构标签、topic/method 和状态的常见交叉组合，筛出过载拆分候选、单例组合和专题集合候选
- `docs/quality.html`：质量治理页，集中展示弱元数据、分类粒度审计与 CSV 导出、标签归一化建议、taxonomy drift 和库内重复报告
- `docs/review.html`：复习计划页，展示待复习、需建计划、已计划和高优先级队列
- `docs/freshness.html`：时效治理页，展示报告新鲜度分数、过期分析、研究线健康度和可复制治理队列
- `docs/dashboard.html`：管理控制台，展示分类覆盖、分类均衡度、研究线健康度、待复习和待补分类队列
- `docs/release.html`：发布摘要页，集中展示发布状态、页面入口、数据文件、数据契约、artifact inventory、队列规模、推荐命令和治理 playbooks
- `docs/snapshot.html`：治理快照页，记录当前发布基线、风险队列、治理策略、研究线摘要和 artifact hash
- `docs/actions.html`：行动中心，统一筛选、导出和复制复习、质量、分类治理、重复项和 inbox 任务；`scripts/export_actions.py` 可把同一队列导出为 checklist 或带自定义任务状态的项目 CSV
- `docs/priority.html`：优先级决策台，把复习、分类、元数据、代码观察和阅读阶段聚合成论文级排序，可筛选、导出 `priority_queue.csv` / `priority_review_patch.csv` 或复制当前队列
- `docs/collections.html`：集合视图页，集中展示共享筛选视图、分类粒度智能队列和研究线集合入口
- `docs/balance.html`：分类均衡复盘页，按维度展示均衡分、长尾、过载、空候选和可导出的复盘清单
- `docs/coverage.html`：研究线分类覆盖地图，按研究线展示各分类字段覆盖率、缺口、top values 和可导出的治理清单
- `docs/facets.html`：分类工作台，按字段审计标签规模、搜索筛选、优先级筛选，并把长尾标签、过载标签和动态状态候选值导出或复制成治理清单
- `docs/related.html`：关联网络页，展示标签共现、相似论文对和孤岛论文，帮助发现潜在研究簇
- `docs/gaps.html`：研究缺口页，自动诊断研究线缺角色、缺分类、分类粒度、缺复习、缺代码观察和后续工作空档
- `docs/taxonomy.html`：分类治理页，展示 domain/track/problem 层级、状态矩阵、研究线角色矩阵、状态工作流设计器、分类变更预览和治理队列
- `docs/timeline.html`：研究路线时间轴，按年份、研究线、方向、角色、状态体系和重要性筛选论文演进
- `docs/matrix.html`：研究线年份矩阵，按 research line × year 查看覆盖密度，可切换状态体系筛选研究线，点击格子查看论文清单
- `docs/lines/index.html`：研究线总览
- `docs/lines/<research-line>.html`：单条研究线详情页
- `docs/tags.html`：分类总览
- `docs/papers.json`：论文索引数据，包含可供前端动态渲染筛选器的 `controls`
- `docs/search_index.json`：全文搜索索引
- `docs/stats.json`：机器可读统计摘要，包含覆盖率、队列规模、研究线和分类分布
- `docs/inbox.json`：机器可读候选论文队列
- `docs/quality.json`：元数据质量报告，列出缺分类、标签别名建议、taxonomy drift、库内重复报告、缺复习计划、待复习、缺代码观察等队列
- `docs/review.json`：机器可读复习计划，给出 suggested_next_review 和优先级
- `docs/freshness.json`：机器可读时效报告，给出 due / needs_plan / stale / aging 队列和研究线新鲜度
- `docs/taxonomy_actions.json`：机器可读分类治理任务，列出长尾合并候选、过载拆分候选、空候选状态和关注项
- `docs/actions.json`：机器可读统一行动队列，汇总 quality、review、taxonomy、dedupe 和 inbox 来源的任务、优先级、导出列、命令和跳转入口
- `docs/priority.json`：机器可读论文级优先级队列，包含 priority_score、urgency、category、recommended_action、queue_hits、review_patch_columns 和可导出 CSV 列
- `docs/command.json`：机器可读命令中心，按使用场景暴露页面入口、数据文件、推荐命令和 next actions
- `docs/workflow.json`：机器可读状态工作流审计，包含 active workflow、每套 workflow 的字段分布、状态定义、未配置值、共享视图绑定和推荐动作
- `docs/status.json`：机器可读运行时状态选择契约，包含 workflow 选项、论文状态快照、默认选择、跳转链接和写回命令
- `docs/views.json`：机器可读视图目录，包含 shared views、系统队列、研究线入口、workflow/status 入口、命中 slug 和可写回 shared view JSON
- `docs/presets.json`：机器可读批量治理 preset，包含字段契约、候选来源、patch columns、workflow 兼容矩阵和写回命令
- `docs/batch.json`：机器可读批次规划数据，包含每个批次的风险、缺口、完整 slug 范围、跳转链接和可复制导出命令
- `docs/collections.json`：机器可读集合视图数据，包含共享视图、智能队列、研究线集合、命中 slug 和样例论文
- `docs/coverage.json`：机器可读研究线分类覆盖地图，包含每条研究线的字段覆盖率、缺失 slug、owner、风险和跳转入口
- `docs/gaps.json`：机器可读研究缺口报告，包含每条研究线的健康分、缺失角色、待补分类、复习/代码观察队列和下一步行动
- `docs/pivot.json`：机器可读分类透视表，包含可交叉的维度、每篇论文的维度投影和常用预设矩阵
- `docs/compare.json`：机器可读论文对比数据，包含对比字段、论文元数据和高优先级/研究线/方向推荐集合
- `docs/taxonomy_map.json`：机器可读分类图谱，包含分类节点、共现边、研究线簇、孤立节点和治理建议
- `docs/clusters.json`：机器可读研究簇报告，包含研究线簇风险、拆分候选、代表论文、owner 和 top labels
- `docs/roadmap.json`：机器可读研究线路线图，包含阶段覆盖、年份里程碑、代表论文、队列、风险和下一步行动
- `docs/scale.json`：机器可读规模就绪报告，包含 readiness score、资源体量、队列规模、瓶颈、容量投影和扩展阶段
- `docs/ownership.json`：机器可读 owner 工作量报告，包含 owner 聚合、研究线风险、治理队列和跳转入口
- `docs/routing.json`：机器可读分类路由画像，包含 line profiles、label profiles、paper signatures、推荐权重和输入契约
- `docs/onboarding.json`：机器可读开源上手清单，包含 readiness checks、贡献路径、常用命令、契约文件和启动数据
- `docs/catalog.json`：机器可读数据目录，包含页面、JSON 资源、顶层字段、集合规模、契约文件、推荐启动文件和集成 recipes
- `docs/intake.json`：机器可读批量导入契约，包含库内去重索引、inbox 去重索引、CSV 字段、默认值和写回命令
- `docs/dedupe.json`：机器可读去重治理报告，包含重复报告组、候选重复组、CSV 字段、建议动作和治理命令
- `docs/registry.json`：机器可读标签注册表，包含标签字段、alias、代表论文、治理信号、建议动作和写回命令
- `docs/facets.json`：机器可读分类字段目录，包含每个 facet 字段的 query key、多值属性、候选值、样例 slug、治理动作和跳转入口
- `docs/curation.json`：机器可读分类成熟度清单，包含逐篇论文 score、level、missing_fields、weak_fields、patch_columns 和补齐建议
- `docs/queues.json`：机器可读运营队列，包含缺分类、复习、代码检查和高优先级待读队列的 slug、样例论文、推荐 preset 和入口链接
- `docs/cohorts.json`：机器可读分类组合队列，包含组合维度、命中论文、动作建议、严重度、专题候选和写回命令
- `docs/snapshot.json`：机器可读治理快照，包含 snapshot_id、发布检查、风险队列、治理策略、研究线和 artifact hash
- `docs/manifest.json`：机器可读发布清单，包含页面入口、数据文件、质量状态、重复报告发布门禁、队列规模、常用命令、command recipes 和治理 playbooks
- `docs/guides/report.template.md`：标准中文论文阅读报告模板，用于新增报告或开源贡献时保持章节结构一致
- `docs/guides/metadata.schema.json`：报告 frontmatter 字段契约，用于校验类型、日期格式和评分范围
- `docs/guides/inbox.schema.json`：候选论文 `inbox.csv` 字段契约，用于校验批量 intake 的必填列、状态、优先级和日期格式
- `docs/guides/taxonomy.schema.json`：`taxonomy.json` 配置契约，用于编辑器提示和开源协作中的配置审查
- `docs/guides/facets.schema.json`：`facets.json` 字段目录契约，用于桌面端/DMG/外部脚本动态读取可筛选字段、候选值和治理动作
- `docs/guides/batch.schema.json`：`batch.json` 批量规划契约，用于桌面端/DMG/外部脚本读取批次维度、批量任务、样例 slug 和导出命令
- `docs/guides/actions.schema.json`：`actions.json` 统一行动队列契约，用于桌面端/DMG/外部脚本读取待办分组、优先级、来源、命令和相关论文
- `docs/guides/catalog.schema.json`：`catalog.json` 集成目录契约，用于桌面端/DMG/外部脚本发现页面、机器数据、契约文件和 bootstrap recipe
- `docs/guides/bootstrap_bundle.schema.json`：`export_catalog_bundle.py` 导出的 bootstrap bundle 契约，用于桌面端/DMG/外部脚本校验启动包、artifact hash 和可嵌入 payload
- `docs/guides/manifest.schema.json`：`manifest.json` 发布清单契约，用于 CI、桌面端/DMG/外部脚本读取发布状态、artifact hash、命令 recipe 和治理 playbook
- `docs/guides/snapshot.schema.json`：`snapshot.json` 治理快照契约，用于 CI、桌面端/DMG/外部脚本读取 snapshot_id、风险队列、治理策略、研究线和 artifact hash
- `docs/guides/workflow.schema.json`：`workflow.json` 状态工作流审计契约，用于桌面端/DMG/外部脚本读取 workflow 分布、drift、空字段和治理建议
- `docs/guides/status.schema.json`：`status.json` 状态选择器契约，用于桌面端/DMG/外部脚本读取 workflow、状态候选、论文快照和写回命令
- `docs/guides/views.schema.json`：`views.json` 视图目录契约，用于桌面端/DMG/外部脚本读取共享队列、命中 slug 和批量管理入口
- `docs/guides/presets.schema.json`：`presets.json` 批量治理 preset 契约，用于桌面端/DMG/外部脚本读取可用动作、字段写入和 workflow 兼容性
- `docs/guides/curation.schema.json`：`curation.json` 分类成熟度契约，用于桌面端/DMG/外部脚本读取逐篇补齐队列和分类完整度分数
- `docs/guides/queues.schema.json`：`queues.json` 运营队列契约，用于桌面端/DMG/外部脚本读取可执行队列、推荐 preset 和样例论文
- `docs/guides/cohorts.schema.json`：`cohorts.json` 分类组合契约，用于桌面端/DMG/外部脚本读取交叉分类队列、过载拆分候选和专题集合候选

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

分类建议见 [`docs/guides/taxonomy.md`](docs/guides/taxonomy.md)。核心原则是：`domains/tracks/problems` 管结构层级，`topics/methods` 管交叉筛选，`research_line/line_role` 管研究脉络，`status/reading_stage/review_stage` 管个人阅读状态。刷新后可打开 `docs/registry.html` 把所有标签当作注册表来维护，集中检查 alias、单例长尾、跨字段复用、未分配 owner 和未使用配置值；也可以打开 `docs/curation.html` 按论文逐条查看分类成熟度分数、缺失字段和稀疏标签，把几百篇论文的补分类工作拆成明确队列；再用 `docs/cohorts.html` 查看常见分类组合，判断哪些组合适合拆成更细 topic、哪些单例需要合并，哪些组合可以沉淀成专题集合。

标签别名、标签定义、研究线角色排序、研究线 owner、阅读状态、阅读阶段、复习阶段、批量治理 preset 和治理阈值可在 [`docs/guides/taxonomy.json`](docs/guides/taxonomy.json) 里自定义；修改后运行 `python3 scripts/build_wiki.py docs` 即可刷新筛选项、论文库批量下拉框、状态看板列和质量/分类治理队列。`label_definitions` 可以按字段为 domain、track、problem、topic、method、research_line 或状态值写 description、owner、status 和 note，构建后会进入 `docs/registry.html` / `docs/registry.json`。状态体系既支持根层 `status_values` 这种简单配置，也支持 `status_workflows` 保存多套命名流程，并用 `active_status_workflow` 选择当前默认启用的一套。也就是说，你可以同时保留「个人阅读流」「项目实现流」「复习流」等多套状态语义，页面里按需切换，而不是把 `read/unread` 写死。`bulk_presets` 可以为 `docs/library.html` 定义待分流、深读、代码检查、安排复习、归档或团队自定义队列动作；构建后会进入 `docs/presets.html` / `docs/presets.json`，明确每个 preset 写哪些字段、生成哪些 patch columns、兼容哪些 workflow，并继续作为 `stats.json` / `manifest.json` controls 暴露给后续桌面软件。`docs/curation.html` / `docs/curation.json` 会把每篇论文的分类成熟度、缺失字段、稀疏字段、patch columns 和建议动作集中输出，适合论文规模变大后按分数治理最薄弱的条目；`docs/queues.html` / `docs/queues.json` 会把缺分类、缺复习、到期复习、代码未检查和高优先级待读抽成运营队列，记录命中 slug、样例论文、推荐 preset 和入口链接；`docs/cohorts.html` / `docs/cohorts.json` 会把常见交叉分类组合抽成队列，区分 `split_candidate`、`topic_candidate`、`singleton` 和 `watch`，让大库分类从“逐篇修”扩展到“按组合治理”。`docs/workflow.html` 会把当前 active workflow、所有命名 workflow 的 status / reading_stage / review_stage 分布、未配置值、空字段和绑定 workflow 的共享视图集中展示出来；`docs/status.html` 则是日常状态选择器，可以在浏览器里动态选择 workflow/status/reading stage/review stage，复制对应共享视图或配置片段，并把当前命中论文导出成 `status_patch.csv`，再用 `scripts/apply_library_metadata.py` dry-run / writeback 批量写回。`docs/views.html` 会把 shared views、系统队列、研究线视图和 workflow/status 视图集中成可筛选目录；`docs/workflow.json`、`docs/status.json`、`docs/views.json` 和 `docs/presets.json` 会把同一份状态/视图/批量治理契约暴露给脚本或后续桌面软件。`research_line_owners` 会把每条研究线的 owner、team 和维护节奏写入 `stats.json`、`ownership.json`、`manifest.json` 与 `snapshot.json`，并显示在管理控制台、覆盖地图和 owner 工作台里，方便论文多起来后按责任人分派分类治理任务。`docs/taxonomy.html` 会展示当前状态工作流配置，并提供浏览器内状态工作流设计器，可以载入已有 workflow、编辑候选状态、复制或下载保留全部 workflow 的 `taxonomy_status_workflow.json` 片段；下载后先运行 `python3 scripts/apply_status_workflow.py docs --input ~/Downloads/taxonomy_status_workflow.json` 预览，再加 `--write` 合并回 `taxonomy.json`。`governance_policy` 可调整什么算分类过稀、过密、标签过载、覆盖高风险或均衡风险。`docs/index.html`、`docs/library.html`、`docs/timeline.html`、`docs/matrix.html` 和 `docs/board.html` 会读取全部命名 workflow，允许在不同浏览视图里动态切换状态语义；看板也支持新增临时状态列并导出 CSV，用来试跑一套新流程。`docs/scale.html` 会把 active workflow、workflow 数量和状态候选数纳入规模治理视图，确保状态不是写死在页面里，而是可以随个人/研究/实现流程动态选择。构建后的 `docs/papers.json`、`docs/stats.json`、`docs/workflow.json`、`docs/status.json`、`docs/views.json`、`docs/presets.json`、`docs/curation.json`、`docs/queues.json`、`docs/cohorts.json`、`docs/scale.json`、`docs/ownership.json`、`docs/registry.json`、`docs/facets.json` 和 `docs/manifest.json` 会把当前启用状态、全部状态 workflow、共享视图目录、批量治理 preset、逐篇分类成熟度、运营队列、分类组合队列、研究线 owner、字段目录、标签定义与治理策略写入机器可读数据，方便后续页面或桌面软件动态读取。

新增报告时可以从 [`docs/guides/report.template.md`](docs/guides/report.template.md) 复制章节骨架；报告 frontmatter 的字段类型、必填项、评分范围和日期格式由 [`docs/guides/metadata.schema.json`](docs/guides/metadata.schema.json) 描述；候选论文 CSV 的字段契约由 [`docs/guides/inbox.schema.json`](docs/guides/inbox.schema.json) 描述；分类配置字段由 [`docs/guides/taxonomy.schema.json`](docs/guides/taxonomy.schema.json) 描述，当前 `taxonomy.json` 已带 `$schema` 引用，支持编辑器自动提示。`python3 scripts/validate_wiki.py docs --strict-taxonomy` 会同时校验 schema、报告元数据、inbox CSV、分类漂移和生成页面，适合作为发布或开源协作前的质量门禁。

首页和论文库表格的筛选、排序、分页状态会写入 URL query string。比如按研究线、重要性排序后复制浏览器地址，即可分享同一个论文列表视图。常用状态组合也可以保存为浏览器本地视图，并用「导出视图」/「导入视图」在浏览器、设备或团队成员之间迁移；需要团队共用时，点击「复制共享视图」即可把当前筛选生成 shared view JSON，或用「导出视图」拿到 saved views 包，再用 `scripts/apply_shared_views.py` dry-run / write 合并进 `docs/guides/taxonomy.json`，它会随仓库同步到所有人的 wiki 下拉框里。新增论文时，可以先在 `docs/intake.html` 批量粘贴链接或标题，去重后导出 `candidate_inbox.csv`，再到 `docs/routing.html` 粘贴标题/摘要，让页面基于现有库的 line profiles、label profiles 和相似论文签名生成研究线与标签建议，最后把建议 patch 带入报告 frontmatter 或批量 metadata CSV。

手动刷新 wiki：

```bash
python3 scripts/build_wiki.py docs
```

批量收集候选论文时，推荐先打开 `docs/intake.html` 粘贴多条 arXiv 链接、id 或标题；页面会先和当前报告库、`docs/inbox.csv` 以及本次粘贴内容去重，只把新候选导出为 `candidate_inbox.csv`。如果你偏好手工维护，也可以直接编辑 `docs/inbox.csv`：

```csv
id,title,link,status,priority,tags,note,added_at
paper-1,Example Paper,https://arxiv.org/abs/2601.00001,queued,high,LLM Serving;Batching,先读方法,
```

从 intake 或外部表格批量导入时，输入 CSV 支持 `name/url/topics/notes/created_at` 这些别名列；脚本会规范化字段，并按 id/link/title 更新已有候选，避免重复追加：

```bash
python3 scripts/apply_inbox_items.py docs --input ~/Downloads/candidate_papers.csv
python3 scripts/apply_inbox_items.py docs --input ~/Downloads/candidate_papers.csv --write
python3 scripts/build_wiki.py docs
```

刷新后打开 `docs/inbox.html`，可以筛选候选论文、查看疑似重复项，复制单篇论文或当前筛选结果的阅读任务给 agent 流程，也可以下载当前筛选 CSV 或复制标准 `inbox.csv` 模板。论文多起来后，打开 `docs/dedupe.html` 可以把库内重复报告、候选池撞车和 inbox 内部重复一起复核，再导出 `dedupe_review.csv` 或复制治理 checklist。

开源协作时，可以先打开 `docs/onboarding.html` 选择贡献路径：新增候选论文走 intake，元数据或渲染问题走 report quality，标签合并/拆分/状态 workflow 调整走 taxonomy governance，发布前检查走 release readiness。也可以直接用 GitHub issue forms 收集输入：`Paper intake` 对应新增候选论文，`Taxonomy governance` 对应标签合并、拆分、状态 workflow 调整，`Report quality issue` 对应元数据、渲染、重复报告或过期分析问题。PR 模板会要求说明是否更新生成物、是否影响当前 active workflow，以及是否通过质量门禁。

提交前运行完整质量门禁：

```bash
python3 scripts/check_quality.py docs
```

这会依次检查脚本语法、已提交 wiki 生成物是否最新、验证 metadata / inbox / taxonomy 配置契约、严格验证 taxonomy drift 和内部链接、解析 wiki 页面内联 JavaScript，并运行单元测试。开源协作时，`.github/workflows/wiki-quality.yml` 会在 push / pull request 中自动运行同一组门禁。

`docs/quality.html` 的「治理命令」区域可以直接复制常用修复命令，例如质量门禁、严格校验、标签别名写入预览、taxonomy action / balance / load 导出和可写回 patch 模板，适合发布前逐项处理队列。

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

导出可分派的分类治理清单：

```bash
python3 scripts/export_actions.py docs --output docs/exports/actions.md
python3 scripts/export_actions.py docs --format project --group review --severity high --assignee wiki-owner --task-status ready --output docs/exports/actions-project.csv
python3 scripts/export_catalog_bundle.py docs --output docs/exports/bootstrap-bundle.json
python3 scripts/export_catalog_bundle.py docs --no-payloads --output docs/exports/bootstrap-manifest.json
python3 scripts/validate_catalog_bundle.py docs/exports/bootstrap-bundle.json --report-dir docs --require-payloads
python3 scripts/export_queues.py docs --output docs/exports/queues.md
python3 scripts/export_queues.py docs --format project --severity high --assignee queue-owner --output docs/exports/queues-project.csv
python3 scripts/export_queues.py docs --format patch --queue missing-review-plan --field review_stage --set-value due --output docs/exports/queues-review-patch.csv
python3 scripts/export_cohorts.py docs --output docs/exports/cohorts.md
python3 scripts/export_cohorts.py docs --format project --action singleton --assignee taxonomy-owner --output docs/exports/cohorts-project.csv
python3 scripts/export_cohorts.py docs --format patch --action topic_candidate --field topics --set-value "New Topic" --list-mode append --output docs/exports/cohorts-topic-patch.csv
python3 scripts/export_batches.py docs --output docs/exports/batches.md
python3 scripts/export_batches.py docs --format project --severity high --assignee batch-owner --output docs/exports/batches-project.csv
python3 scripts/export_batches.py docs --format patch --gap review --field review_stage --set-value due --output docs/exports/batches-review-patch.csv
python3 scripts/export_coverage.py docs --output docs/exports/coverage.md
python3 scripts/export_coverage.py docs --format project --risk high --risk medium --output docs/exports/coverage-project.csv
python3 scripts/export_coverage.py docs --format patch --field topics --set-value "New Topic" --output docs/exports/coverage-topic-patch.csv
python3 scripts/export_gaps.py docs --output docs/exports/gaps.md
python3 scripts/export_gaps.py docs --format project --min-priority 20 --assignee research-owner --output docs/exports/gaps-project.csv
python3 scripts/export_views.py docs --output docs/exports/views.md
python3 scripts/export_views.py docs --format sidebar --min-count 1 --output docs/exports/views-sidebar.json
python3 scripts/export_views.py docs --format patch --view "Attention Kernels" --field status --set-value reading --output docs/exports/views-status-patch.csv
python3 scripts/export_collections.py docs --output docs/exports/collections.md
python3 scripts/export_collections.py docs --format project --type smart --min-count 1 --assignee wiki-owner --output docs/exports/collections-project.csv
python3 scripts/export_ownership.py docs --output docs/exports/ownership.md
python3 scripts/export_ownership.py docs --format project --only-open-queues --team systems --output docs/exports/ownership-project.csv
python3 scripts/export_roadmap.py docs --output docs/exports/roadmap.md
python3 scripts/export_roadmap.py docs --format project --risk medium --role-gap yes --assignee roadmap-owner --output docs/exports/roadmap-project.csv
python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md
python3 scripts/export_taxonomy_actions.py docs --format csv --severity high --output docs/exports/taxonomy-actions.csv
python3 scripts/export_taxonomy_actions.py docs --format csv --field topics --severity high --output docs/exports/topic-actions.csv
python3 scripts/export_taxonomy_actions.py docs --format project --assignee taxonomy-owner --task-status ready --output docs/exports/taxonomy-project.csv
python3 scripts/export_taxonomy_actions.py docs --format patch --action merge_candidate --target-value "Unified Label" --output docs/exports/taxonomy-action-patch.csv
python3 scripts/export_taxonomy_change.py docs --field topics --from-value "Old Topic" --to-value "New Topic" --output docs/exports/taxonomy-change-patch.csv
python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --assignee taxonomy-owner --output docs/exports/taxonomy-balance-project.csv
python3 scripts/export_taxonomy_load.py docs --format csv --signal dense_tags --output docs/exports/taxonomy-load.csv
python3 scripts/export_taxonomy_load.py docs --format patch --signal sparse_tags --output docs/exports/taxonomy-load-patch.csv
python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md
python3 scripts/export_taxonomy_registry.py docs --format project --severity high --severity medium --assignee taxonomy-owner --output docs/exports/taxonomy-registry-project.csv
python3 scripts/export_taxonomy_registry.py docs --format patch --signal singleton --target-value "Unified Label" --output docs/exports/taxonomy-registry-patch.csv
```

为批量元数据或分类 CSV 生成审计 JSON，方便在 PR 中复核受影响 slug、字段和 before/after：

```bash
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv --audit-output docs/exports/metadata-audit.json
```

应用状态工作流设计器导出的配置：

```bash
python3 scripts/apply_status_workflow.py docs --input ~/Downloads/taxonomy_status_workflow.json
python3 scripts/apply_status_workflow.py docs --input ~/Downloads/taxonomy_status_workflow.json --write
python3 scripts/build_wiki.py docs
```

应用治理策略设计器导出的阈值：

```bash
python3 scripts/apply_governance_policy.py docs --input ~/Downloads/taxonomy_governance_policy.json
python3 scripts/apply_governance_policy.py docs --input ~/Downloads/taxonomy_governance_policy.json --write
python3 scripts/build_wiki.py docs
```

应用浏览器里保存或复制的共享视图：

```bash
python3 scripts/apply_shared_views.py docs --input ~/Downloads/library_saved_views.json
python3 scripts/apply_shared_views.py docs --input ~/Downloads/library_saved_views.json --write
python3 scripts/build_wiki.py docs
```

`taxonomy-action-patch.csv` 会保留 `source_value` / `action` / `severity` 等审计列，同时把目标字段填成可写回的列；正式应用前建议先人工确认目标值并 dry-run。把表格里编辑过的分类和状态字段写回报告 frontmatter：

```bash
python3 scripts/apply_library_metadata.py docs --input docs/library.csv
python3 scripts/apply_library_metadata.py docs --input docs/library.csv --write
python3 scripts/build_wiki.py docs
```

`docs/library.html` 也支持先按 `domains` / `tracks` / `problems` / `topics` / `methods` 等分类维度筛选论文、在多套 `status_workflows` 间动态切换 `status` / `reading_stage` / `review_stage` 的候选项，并按到期复习、未设置复习或已设置复习直接筛出维护队列；它会实时显示当前筛选结果的状态分布、研究线分布、topic/method 热点、代码覆盖、taxonomy 覆盖和复习计划缺口。页面还会基于当前筛选结果生成智能队列建议，自动找出缺分类、缺复习计划、到期复习、有代码未检查和高优先级待读等队列，并可一键选中对应论文、套用匹配的 `bulk_presets` 生成写回 patch。批量面板会显示当前启用的 workflow、可选 status / reading / review 数量，以及当前 preset 有多少与这套 workflow 兼容；切换 workflow 后，筛选下拉、批量写回下拉、preset 兼容提示和 patch 预览都会同步更新。当前筛选条件会显示成可逐个移除的 chips，方便从复杂队列中快速放宽某个约束。它还支持复制当前筛选/排序链接、按场景隐藏/显示列、切换紧凑/标准/舒适密度、保存并导入/导出常用队列、勾选当前页或一键选中全部筛选结果，把已选论文复制成 Markdown 清单或纯 slug 列表，批量选择 `status` / `reading_stage` / `review_stage` / `next_review` / `importance`，或套用 `taxonomy.json` 的 `bulk_presets`；preset 会尊重当前 workflow 已配置的候选值，只填入可用字段。也可以展开「批量分类字段」为所选论文设置 `research_line` / `line_role` / `domains` / `tracks` / `problems` / `topics` / `methods`，并为多值分类选择替换、追加或移除写入方式。页面会在下载 `metadata_patch.csv` 前显示 patch 摘要、影响字段、当前 workflow、preset 兼容说明和样例 slug，并可直接复制 dry-run / writeback 命令；列设置和密度偏好会保存在浏览器本地。也可以把当前筛选和排序结果直接导出为 `reading_list.md`、`library_filtered.csv` 或 `library.bib`。`docs/board.html` 支持把论文卡片拖到新的状态列，然后下载 `status_board_patch.csv`。下载后用同一个写回脚本预览和应用：

```bash
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv --write
python3 scripts/apply_library_metadata.py docs --input ~/Downloads/status_board_patch.csv --write
python3 scripts/build_wiki.py docs
```

支持 `--field status --field topics` 限定字段，支持 `--slug <slug>` 限定论文；空单元格默认不会清空原值，需要显式加 `--clear-empty`。批量分类 patch 默认会替换列表字段；如果只想给现有 `topics` / `methods` 等字段追加或移除少量标签，可以让 CSV 带 `_list_mode` 列，或在命令行加 `--list-mode append` / `--list-mode remove`。

预览并写入复习计划建议：

```bash
python3 scripts/apply_review_plan.py docs
python3 scripts/apply_review_plan.py docs --write
python3 scripts/build_wiki.py docs
```

也可以在 `docs/review.html` 直接下载 `review_plan_patch.csv`，只包含当前缺少 `next_review` 的论文建议日期；下载后用 `scripts/apply_library_metadata.py` 先 dry-run，再 `--write` 写回。

预览并写入标签别名建议：

```bash
python3 scripts/apply_taxonomy_aliases.py docs
python3 scripts/apply_taxonomy_aliases.py docs --write
python3 scripts/build_wiki.py docs
```

手动重建某篇报告 HTML：

```bash
python3 scripts/render_report_html.py docs/<slug>.md docs/<slug>.html --slug <slug>
```

这个渲染器会把多行 `$$...$$` 公式转成显式 KaTeX block，并把本地论文图复制到 `docs/assets/<slug>/`，避免公式裸露或图片在 wiki 中破图。

## License

本项目使用 [MIT License](./LICENSE)。
