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

`role_order` 会影响研究线详情页和首页研究线概览中的论文排序。`status_values`、`reading_stage_values` 和 `review_stage_values` 会进入首页和论文库表格的筛选项；即使某个状态当前还没有论文使用，也可以先作为可选管理状态出现。

`shared_views` 可以把常用筛选队列随仓库同步到首页和论文库表格。`page` 支持 `all`、`index`、`library`；`state` 使用 URL query 里的筛选键，例如 `importance`、`status`、`line`、`track`、`review`、`sort`：

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
- 列表里不能有重复值或空值。
- `shared_views` 必须是对象列表，每个视图都要有非空 `name` 和非空 `state`。

报告里的 `status`、`reading_stage`、`review_stage` 和 `line_role` 如果不在 `taxonomy.json` 对应列表中，普通校验会给 warning，方便你逐步治理旧报告；发布或团队协作前可以使用严格模式把它升级为 error：

```bash
python3 scripts/validate_wiki.py docs --strict-taxonomy
```
