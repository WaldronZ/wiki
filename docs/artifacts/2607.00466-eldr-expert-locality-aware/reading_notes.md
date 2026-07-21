---

## 1. 问题动机

### 1.1 MoE decode 效率瓶颈：active expert count 主导延迟，而非 batch size

- **核心观察**：MoE decode 是 memory-bandwidth bound，每步需要从 HBM 加载所有被激活的 distinct expert 的权重。Dense 模型中一个 batch 所有 token 共享同一 FFN 权重，但 MoE 中 batch 被 expert 瓜分，weight reuse 只发生在共享同一 expert 的 token 之间。
- **量化证据**：Qwen3-30B-A3B 上，active experts 从 16→128 增加时，MoE layer latency 增长 4.7×（batch size 固定在 64），而 batch size 在固定 expert count 下几乎不影响延迟。
- **来源**：`sec:motivation_active_experts`，`fig:moe_latency`（单层 MoE benchmark，MI300X）

### 1.2 Expert 使用具有 domain 结构性

- **核心观察**：MoE gate 是 input-dependent 的，不同 domain（code/math/medical/legal，以及不同语言）的请求激活不同 expert 子集。Expert usage 在同类请求间是 correlated，不仅仅是单个 token 层面的 sparse。
- **量化证据**：图 `fig:domain` 展示了三种模型（Qwen3-30B-A3B、GPT-OSS-120B、Gemma-4-26B-A4B）在 task 和 language 维度的 per-expert activation heatmap，每个 domain 有 distinct expert region。
- **WildChat 语言分布偏斜**：`fig:wildchat` 显示英语+中文占比 ~75%，说明 locality routing 需要处理 skew。
- **来源**：`sec:motivation`，`fig:domain`，`fig:wildchat`

### 1.3 Prefill expert activation 可预测 decode expert activation

- **核心观察**：prefill 阶段已经通过了相同的 MoE gate，因此 prefill 的 expert 选择可以预测 decode 的 expert 选择。这是 ELDR 能在 prefill→decode handoff 做路由的 enabling signal。
- **量化证据**：`fig:pd_scatter` 显示 per-expert 的 normalized prefill activation vs. decode activation 散点图，点接近对角线，表明两阶段高度相关。
- **来源**：`sec:motivation_prefill_decode`，`fig:pd_scatter`

### 1.4 Opportunity：same-domain batches activate fewer distinct experts

- **核心观察**：同 domain 的 batch 每步激活的 distinct expert 数量比混合 domain batch 少 17–21%（task）和 3–10%（language）。
- **来源**：`sec:motivation_opportunity`，`fig:opp_sweep`

### 1.5 三个挑战

| 挑战 | 描述 | 来源 |
|------|------|------|
| **Signature 设计** | 如何将 prefill raw data 转化为能反映 decode expert overlap 的向量？设计空间大（raw counts / gate logits / layer masks / reweighting），需要一个独立于 downstream clustering 的评价标准。 | `sec:motivation_challenges` |
| **Locality vs. Load 平衡** | Locality-only 会 overload 热门 domain worker（WildChat top-2 language 占 75%）；load-only 会 scatter expert-similar requests。两者信息来源不同：locality 是 aggregate 属性，load 是 instantaneous。 | `sec:challenge_load`，`fig:wildchat` |
| **Prefix cache coherence** | Cache hit 时 prefill 被跳过，expert footprint 缺失。Per-request signature cache 只对 full hit 有效，partial hit / eviction / reuse 场景下会 break。 | `sec:challenge_prefix` |

---
