# Wiki Taxonomy Guide

这个 guide 说明 AutoPaperReader wiki 的管理字段。目标是让论文数量增加后，仍然能按研究线、主题、方法、阅读状态和复习状态稳定管理。

## 字段层级

建议把分类拆成从粗到细的几层：

```yaml
domains:
  - LLM Systems
tracks:
  - Inference Acceleration
problems:
  - Parallel Decoding
topics:
  - LLM Inference
  - Speculative Decoding
methods:
  - block diffusion
  - KV injection
```

- `domains`：最大领域，例如 `LLM Systems`、`Reasoning`、`Multimodal`。
- `tracks`：研究方向，例如 `Inference Acceleration`、`Attention Kernels`。
- `problems`：具体问题，例如 `Parallel Decoding`、`Efficient Exact Attention`。
- `topics`：可交叉筛选的主题。
- `methods`：论文使用的具体机制、算法或工程技巧。

## 研究线

`research_line` 用来把论文串成脉络，而不是只放在标签池里。

```yaml
research_line: Parallel Decoding with Diffusion Models
line_role: foundation
```

推荐的 `line_role`：

- `foundation`：奠基论文或该线的核心起点
- `baseline`：常用对照方法
- `main`：当前最核心论文
- `system`：系统或工程化实现
- `variant`：重要变体
- `followup`：后续推进或补充
- `survey`：综述

运行 `python3 scripts/build_wiki.py docs` 后，wiki 会生成：

- `docs/lines/index.html`
- `docs/lines/<research-line>.html`

## 阅读状态

这些字段会被首页动态聚合成筛选项。你可以自由添加新值，不需要改脚本。

```yaml
status: read
reading_stage: deep_read
review_stage: fresh
last_reviewed: 2026-06-11
next_review: 2026-06-25
importance: 5
confidence: 4
reproducibility: 3
has_code: true
```

建议值：

- `status`: `unread`、`skimmed`、`reading`、`read`、`archived`
- `reading_stage`: `skim`、`normal_read`、`deep_read`、`code_checked`
- `review_stage`: `fresh`、`due`、`reviewed`
- `importance`: 1-5
- `confidence`: 1-5，表示自己理解的把握
- `reproducibility`: 1-5，表示代码/实验可复现程度

## 标签规范

同一概念使用同一种写法。构建脚本会归一化一部分常见别名，例如：

- `Speculative decoding` -> `Speculative Decoding`
- `LLM serving` -> `LLM Serving`
- `KV cache` -> `KV Cache`

如果发现新的重复标签，优先在 `docs/guides/taxonomy.json` 的 `label_aliases` 中加入别名，而不是在每篇报告里临时修。例如：

```json
{
  "label_aliases": {
    "serving systems": "LLM Serving"
  },
  "role_order": ["foundation", "baseline", "main", "system", "variant", "followup", "survey"]
}
```

`docs/quality.json` 会输出 `label_alias_suggestions`，`docs/quality.html` 和 `docs/taxonomy.html` 会展示“标签归一化建议”。这些建议只根据大小写、复数、连字符、斜杠等规范化后相同的标签生成，适合发现 `tiling` / `Tiling`、`KV-cache` / `KV Cache` 这类漂移；最终是否合并仍由你把建议片段写入 `label_aliases` 来确认。

## 标签定义

`label_definitions` 用来把标签变成可维护的受控词表。它按字段分组，每个标签可以写 `description`、`owner`、`status` 和 `note`。构建后这些定义会进入 `docs/registry.html` 和 `docs/registry.json`，供页面、导出脚本、桌面软件或 PR 审查读取。

```json
{
  "label_definitions": {
    "domains": {
      "LLM Systems": {
        "description": "Systems-oriented papers about serving, inference, kernels, memory, and scalability for language models.",
        "owner": "systems",
        "status": "active"
      }
    },
    "topics": {
      "Speculative Decoding": {
        "description": "Draft-and-verify decoding methods that preserve target-model output distribution while improving latency.",
        "owner": "decoding-owner",
        "status": "active"
      }
    }
  }
}
```

支持的定义字段和 report frontmatter 一致：`domains`、`tracks`、`problems`、`topics`、`methods`、`research_line`、`line_role`、`status`、`reading_stage`、`review_stage`。`status` 可用 `active`、`watch`、`deprecated`；如果一个 deprecated 标签仍在报告中使用，registry 会把它标成高优先级治理项。

`docs/facets.html` 是日常分类工作台：它会按字段展示每个标签命中的论文数、长尾标签、过载标签和动态状态候选值。论文数量变多后，优先从这里判断哪些标签需要合并、哪些大桶需要拆成更细的 track / problem。页面可以按字段、优先级和动作类型筛选治理项，并把当前筛选复制成 Markdown checklist 或对应的 `scripts/export_taxonomy_actions.py --format project` 命令，方便分派到 issue、项目看板或桌面软件。对应的机器可读任务会写入 `docs/taxonomy_actions.json`；`scripts/export_taxonomy_actions.py --format patch` 还能把合并候选导出成可人工确认目标值的写回模板。决定把某个标签或状态重命名之前，可以到 `docs/taxonomy.html` 的「分类变更预览」选择字段、旧值和新值，先查看受影响论文，再下载 `taxonomy_change_patch.csv`，用 `scripts/apply_library_metadata.py` dry-run 或写回。日常给一批论文补 `topics` / `methods` 时，`docs/library.html` 的批量分类字段支持替换、追加、移除三种写入方式；导出的 CSV 会用 `_list_mode` 记录模式，命令行也可以显式传 `--list-mode append` 或 `--list-mode remove`。

`role_order` 会影响研究线详情页和首页研究线概览中的论文排序。`status_values`、`reading_stage_values` 和 `review_stage_values` 会进入首页和论文库表格的筛选项；其中 `status_values` 还会成为 `docs/board.html` 的状态看板列。即使某个状态当前还没有论文使用，也可以先作为可选管理状态出现。构建后的 `papers.json` 和 `stats.json` 会把这些选项输出到 `controls` 字段，供后续前端、脚本或桌面软件动态读取。新增论文时，`docs/routing.html` 会把现有研究线、标签和相似论文压缩成 `routing.json` 画像，用于给标题/摘要生成初始分类建议。

`research_line_owners` 用来给研究线配置维护责任，不改变论文分类本身。每条线可以设置 `owner`、`team`、`cadence` 和 `note`；构建后会写入 `stats.json`、`ownership.json`、`manifest.json`、`snapshot.json`，并显示在 `docs/dashboard.html`、`docs/coverage.html` 与 `docs/ownership.html` 中。论文多起来后，建议把高风险覆盖缺口按 owner 分派，而不是只按标签本身排队。

```json
{
  "research_line_owners": {
    "Efficient Attention Kernels": {
      "owner": "kernel-owner",
      "team": "systems",
      "cadence": "monthly",
      "note": "Review new GPU kernel and serving papers."
    }
  }
}
```

如果你想在多套状态体系之间切换，可以在 `taxonomy.json` 里使用 `status_workflows` 保存多个命名 workflow，并用 `active_status_workflow` 选择当前启用的一套。构建脚本会优先读取激活 workflow 里的 `status_values`、`reading_stage_values` 和 `review_stage_values`；未配置时仍兼容根层同名字段。

```json
{
  "active_status_workflow": "research",
  "status_workflows": {
    "simple": {
      "status_values": ["unread", "read", "archived"],
      "reading_stage_values": ["skim", "deep_read"],
      "review_stage_values": ["fresh", "reviewed"]
    },
    "research": {
      "status_values": ["inbox", "triaged", "reading", "implemented", "cited", "archived"],
      "reading_stage_values": ["skim", "normal_read", "deep_read", "code_checked", "reproduced"],
      "review_stage_values": ["fresh", "due", "reviewed", "evergreen"]
    }
  }
}
```

如果想试一套新的状态流，不必先改所有报告：可以在 `docs/board.html` 新增临时状态列，把论文拖进去后导出 `status_board_patch.csv`，用 `scripts/apply_library_metadata.py` 预览或写回。确认这套状态值得长期保留后，再用 `docs/taxonomy.html` 的「状态工作流设计器」载入已有 workflow 或命名一套新 workflow；设计器输出的 JSON 会保留其它已配置 workflow，只替换或新增当前命名项，并切换 `active_status_workflow`。下载 `taxonomy_status_workflow.json` 后，先 dry-run 再写回：

```bash
python3 scripts/apply_status_workflow.py docs --input ~/Downloads/taxonomy_status_workflow.json
python3 scripts/apply_status_workflow.py docs --input ~/Downloads/taxonomy_status_workflow.json --write
python3 scripts/build_wiki.py docs
```

写回脚本会把 active workflow 同步到根层 `status_values`、`reading_stage_values` 和 `review_stage_values`，同时保留其它命名 workflow。刷新 wiki 后，它就会成为首页、论文库、状态看板和 JSON controls 的正式下拉选项。

`shared_views` 可以把常用筛选队列随仓库同步到首页和论文库表格。最省事的方式是在 `docs/index.html` 或 `docs/library.html` 调好筛选后点击「复制共享视图」，把生成的 JSON 对象保存成文件；浏览器本地保存的视图也可以用「导出视图」下载为 `*_saved_views.json`。确认稳定后用写回脚本合并进 `taxonomy.json`：

```bash
python3 scripts/apply_shared_views.py docs --input ~/Downloads/library_saved_views.json
python3 scripts/apply_shared_views.py docs --input ~/Downloads/library_saved_views.json --write
python3 scripts/build_wiki.py docs
```

`page` 支持 `all`、`index`、`library`；`state` 使用 URL query 里的筛选键，例如 `importance`、`workflow`、`status`、`line`、`track`、`review`、`sort`：

```json
{
  "shared_views": [
    {
      "name": "重点论文",
      "page": "all",
      "state": {
        "importance": "5",
        "sort": "importance"
      }
    }
  ]
}
```

`python3 scripts/validate_wiki.py docs` 会校验 `taxonomy.json` 的基本结构：

- `label_aliases` 必须是 object，key 和 value 都是非空字符串。
- `role_order`、`status_values`、`reading_stage_values`、`review_stage_values` 必须是字符串列表。
- `active_status_workflow` 必须指向 `status_workflows` 中已有的名称；每个 workflow 只允许包含 `status_values`、`reading_stage_values` 和 `review_stage_values`。
- 列表里不能有重复值或空值。
- `shared_views` 必须是对象列表，每个视图都要有非空 `name` 和非空 `state`；`state` 可以保存 `workflow`，用于团队共享某套状态体系下的队列。
- `governance_policy` 可选，用来调整质量治理、分类 action、分类均衡和研究线覆盖地图的阈值；每个阈值必须是非负整数或非负数字。

`governance_policy` 的默认行为适合小到中型个人论文库。论文数量变大后，可以提高 `taxonomy_load.min_tags` 让每篇论文需要更多 topic/method 入口，降低 `taxonomy_actions.split_share` 更早提示大桶拆分，或调高 `coverage.high_score_below` 让研究线分类覆盖更严格。策略会写入 `papers.json`、`stats.json` 和 `manifest.json` 的 `controls.governance_policy`，后续桌面软件可以直接读取同一份契约。

`docs/taxonomy.html` 的「治理策略设计器」可以直接编辑这些阈值并下载 `taxonomy_governance_policy.json`。正式合并前先 dry-run：

```bash
python3 scripts/apply_governance_policy.py docs --input ~/Downloads/taxonomy_governance_policy.json
python3 scripts/apply_governance_policy.py docs --input ~/Downloads/taxonomy_governance_policy.json --write
```

报告 frontmatter 的字段契约写在 `docs/guides/metadata.schema.json`，用于约束必填字段、字符串 / 列表 / 布尔 / 整数类型、`importance` / `confidence` / `reproducibility` 的 1-5 范围，以及 `last_reviewed` / `next_review` 的 `YYYY-MM-DD` 日期格式。这个 schema 是给校验器和后续桌面软件共用的机器可读契约。

报告里的 `status`、`reading_stage`、`review_stage` 和 `line_role` 如果不在 `taxonomy.json` 对应列表中，会被记录到 `docs/quality.json` 的 `taxonomy_drift`，并展示在 `docs/quality.html`。普通校验会给 warning，方便你逐步治理旧报告；发布或团队协作前可以使用严格模式把它升级为 error：

```bash
python3 scripts/validate_wiki.py docs --strict-taxonomy
```
