---
slug: 2607.00466-eldr-expert-locality-aware
title: "ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Serving"
title_zh: "ELDR：面向 PD 分离 MoE 服务的专家局部性感知解码路由"
title_en: "ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Serving"
arxiv_id: "2607.00466"
year: 2026
authors:
  - Sangjin Choi
  - Sukmin Cho
  - Yifan Xiong
  - Ziyue Yang
  - Youngjin Kwon
  - Peng Cheng
topics:
  - LLM Serving
  - Mixture-of-Experts
  - PD Disaggregation
  - System Optimization
methods:
  - Expert Locality Routing
  - Balanced K-Means Clustering
  - Prefix Cache Coherence
  - Signature-Based Routing
status: read
importance: 4
has_code: false
research_line: LLM Systems
line_role: core
---

# ELDR：面向 PD 分离 MoE 服务的专家局部性感知解码路由（ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Serving）

## 1. 基本情况

- **题目（中/英）**：ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Serving / ELDR：面向 PD 分离 MoE 服务的专家局部性感知解码路由
- **作者**：Sangjin Choi†, Sukmin Cho†, Yifan Xiong‡, Ziyue Yang§, Youngjin Kwon†✉, Peng Cheng‡（†KAIST, ‡Microsoft Research Beijing, §Shanghai Xingyunzhili AI Institute, ‖Microsoft Research Redmond）
- **单位**：KAIST、Microsoft Research、上海星云智利人工智能研究院
- **arxiv 编号**：2607.00466，提交日期 2026-07-01
- **arxiv 链接**：https://arxiv.org/abs/2607.00466v2
- **代码仓库**：无公开代码仓库

## 2. 核心贡献概述

**中文版**：在 Prefill-Decode（PD）分离的 LLM 服务架构中，现有 decode 路由策略仅做负载均衡，忽略了 MoE 模型中 expert 激活模式对 decode 延迟的主导影响。ELDR 提出 expert-locality-aware decode routing，利用 prefill 阶段的 expert 激活信息构建 expert signature，通过 balanced K-means 离线聚类和 locality-band 在线路由，将 expert 使用模式相似的请求路由到同一 decode worker，从而减少每步激活的 distinct expert 数量，losslessly 降低 median TPOT 5.9–13.9%。

**英文版**（摘自 Abstract）："We present ELDR, an expert-locality-aware decode router for PD-disaggregated MoE serving. From a request's prefill expert activations, ELDR builds an expert signature predicting the experts it will activate during generation. Offline, balanced K-means partitions signature space across decode workers; online, locality-band routing sends each request to the least-loaded worker among those best matching its signature."

## 3. 一句话精髓（写给外行）

MoE 模型像一座大图书馆，每个请求只借几本书；如果把借同类书的人安排在同一个阅览室，管理员每次只需从书架上取少量不同的书，速度自然快了——ELDR 就是那个聪明的前台调度员，通过观察你进门时翻了什么目录（prefill），就预判你在阅览室里会读哪些书（decode），然后把你领到最合适的房间。

## 4. 学术贡献清单

### 4.1 动机的发现与阐明

论文揭示了一个被先前工作忽略的关键事实：**MoE decode 延迟由每步激活的 distinct expert 数量主导，而非 batch size**。在 Qwen3-30B-A3B 上，active experts 从 16 增到 128 时 MoE layer latency 增长 4.7×，而 batch size 在固定 expert count 下几乎无影响（§3.1, fig:moe_latency）。这个观察的系统含义是：decode worker 之间的延迟差异不来自"谁接了多少请求"，而来自"这些请求激活了多少种不同的 expert"——这是 load-based routing 的盲区。

![MoE 层延迟由 active expert 数量主导，而非 batch size](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/03_motivation/moe_latency.pdf)

图解：单个 MoE 层（MI300X）的延迟随 active expert 数量线性增长，而 batch size 在固定 expert count 下几乎无影响。这证明 decode 延迟的 first-order knob 是每步激活的 distinct expert 数量，而非传统的 batch size 视角。

论文进一步发现三个 enabling 属性：

1. **Expert 使用具有 domain 结构性**（§3.2, fig:domain）：Code、Math、Medical、Legal 请求各自过度激活不同 expert 子集，多语言流量也按语言分离。这不是单个 token 层面的 sparse，而是同类请求间的 correlated activation。

![Decode 阶段 per-expert 激活相对于跨域均值的偏差](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/03_motivation/domain_2x3_layer.pdf)

图解：三个 MoE 模型在 task（top）和 language（bottom）维度上的 per-expert 激活热力图。每一行是一个 domain/语言，每一列是一个 expert，颜色表示相对于 cross-domain mean 的激活偏差。Code/Math/Medical/Legal 各自过度激活不同的 expert 子集，多语言流量也按语言分离——expert 使用具有清晰的 domain 结构性，这为 locality-aware routing 提供了基础。

2. **Prefill 可预测 decode 的 expert 选择**（§3.3, fig:pd_scatter）：per-expert 的 normalized prefill activation 与 decode activation 的相关系数达 0.70–0.92，使得 prefill→decode handoff 处的路由决策成为可能。

![Prefill expert 激活预测 decode expert 激活](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/03_motivation/pd_scatter.pdf)

图解：每个点代表一个 expert，横轴为 normalized prefill activation，纵轴为 decode activation，pooled over domains。点越靠近对角线，说明 prefill 和 decode 阶段该 expert 的使用越一致。相关系数 0.70–0.92 表明 prefill 是 decode expert 选择的强预测信号——这是 ELDR 在 handoff 处做路由决策的 enabling observation。

3. **Same-domain batch 比 mixed-domain batch 每步少激活 17–21% 的 distinct expert**（§3.4, fig:opp_sweep），证明 expert locality 是可量化、可利用的优化空间。

![Same-domain batch 比 mixed-domain batch 每步少激活 17–21% 的 distinct expert](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/03_motivation/active_experts_sweep.pdf)

图解：横轴为 batch size，纵轴为 per-step active expert count。蓝色为 same-domain batch，橙色为 mixed-domain batch。在 task（top）和 language（bottom）两个维度、三个 MoE 模型上，same-domain batch 一致地少激活 17–21% 的 distinct expert。这个 gap 就是 ELDR 的优化空间——通过 locality-aware routing 将请求按 expert 使用模式分组，可以逼近 same-domain batch 的 lower bound。

### 4.2 方法的创新

- **Expert Signature 设计**：提出以 prefill 阶段 per-layer per-expert 的 top-k 激活计数为基础，经 IDF 去噪、greedy layer selection、L2 归一化构建 expert signature。用 Spearman ρ（signature distance 与 decode-time expert overlap 的 rank correlation）作为 signature 质量的统一评估准则，独立于下游 clustering/routing（§4.2, eq:rho）。
- **Balanced K-means 离线聚类**：采用 Hungarian-balanced K-means（Malinen & Fränti 2014）替代 vanilla K-means，在 locality 优化的同时保证 cluster size 均衡，避免热点 domain 过载（§4.3.1）。
- **Locality-band routing**：在 cosine similarity band [s* − τ, s*] 内选 least-loaded worker，用参数 τ 在 pure locality（τ=0）和 pure load balancing（τ=1）间插值（§4.3.2）。
- **Prefix-cache-coherent signature cache**：以 KV cache block 粒度存储 expert signature，与 KV cache co-indexed，partial hit / eviction / reuse 场景下自动保持一致性（§4.4）。

### 4.3 实验上的核心结论

- 在 3 个 MoE 模型（Qwen3-30B-A3B, GPT-OSS-120B, Gemma-4-26B-A4B）、2 种 workload（task, language）上，ELDR 相对最强 load-balancing baseline 降低 median TPOT 5.9–13.9%，tail TPOT 3.4–6.0%（task）。
- ELDR 优于 naive Domain-aware routing（基于 oracle domain label）1.4–9.1%，因为 signature clustering 比 4 个 domain label 更细粒度，且 τ-band 允许跨 cluster 的 load spill。
- Signature cache 占 KV cache 不到 1%，per-request overhead 0.86ms（1.2% of median TTFT）。
- 扩展到 235B 模型（EP=4, 40 GPU）仍有效，median TPOT 降低 2.7–4.3%。

## 5. 写作故事线

论文的叙事遵循一条清晰的"问题→观察→信号→设计→验证"链条：

**第一幕（§1–2）：定位被忽略的瓶颈。** 论文从 PD 分离架构的背景出发，指出现有 decode 路由只做 load balancing，对 dense 模型足够（equal load = equal latency），但对 MoE 模型不够——因为 MoE decode 的 HBM 访问成本由 batch 内 distinct expert 的并集决定，而非 token 数。这是一个"被 load balancing 假设遮蔽的第二维度"。

**第二幕（§3 Motivation）：四组实验证明 expert locality 可观测、可预测、可利用。** 这是全文最关键的一节。fig:moe_latency 证明 active expert count 是延迟的 first-order knob；fig:domain 展示 expert 使用的 domain 结构性；fig:pd_scatter 证明 prefill 可预测 decode 的 expert 选择；fig:opp_sweep 量化了 same-domain batch 的 active expert reduction。四个实验依次建立"瓶颈→结构→可预测→可利用"的推理链。§3.5 的三个 challenge（signature design、locality vs. load、prefix cache coherence）把 opportunity 转化为具体的工程问题。

**第三幕（§4 Design）：分层解决三个挑战。** Signature 设计通过 Spearman ρ 做 quality-guided search（§4.2），把离散计数 + IDF + layer selection 三原则逐一用 ρ 验证。Locality vs. load 通过"离线聚类捕获 aggregate locality + 在线路由捕获 instantaneous load"的两阶段分解解决（§4.3）。Prefix cache coherence 通过 KV-block-granular signature cache 解决（§4.4）。

**第四幕（§6 Evaluation）：系统性消融证明每个设计选择的边际贡献。** Main results（fig:main_task, fig:main_language）给出端到端 win；fig:expert_reduction 证明 mechanism 确实是 active expert reduction；fig:transform_ablation / fig:cluster_ablation / fig:tau_ablation / fig:prefix_ablation 分别验证 discrete signature、balanced clustering、τ=0.1、prefix cache composition。

**叙事上的关键转折**：§3 的 fig:pd_scatter（prefill predicts decode）是整篇论文的 enabling observation——没有这个信号，后续所有设计都不可能。§4.2 用 ρ 作为 signature 设计的"single criterion"是第二个关键转折，它把一个开放设计空间（raw counts / gate logits / binary / ...）转化为可比较的优化问题。

整体叙事节奏：**问题 → 反直觉发现 → 信号可观测 → 量化机会 → 挑战 → 解法 → 验证 → 泛化**，是一篇结构成熟的系统论文的典型叙事模式。

## 6. 核心参考文献

| 编号 | 作者/年份 | 在本文中的角色 |
|------|-----------|----------------|
| [DistServe] Zhong et al., OSDI'24 | PD 分离架构的开山之作，ELDR 的架构基础。ELDR 在其 decode 路由层上增加 expert locality 维度。 |
| [Splitwise] Patel et al., 2023 | 同期独立提出 prefill/decode 分离，与 DistServe 共同定义了 xPyD 拓扑范式。 |
| [Mooncake] Qin et al., 2025 | KVCache-centric disaggregated architecture，ELDR 的 prefill 路由对齐其 PrefixHash 做法。 |
| [Balanced K-means] Malinen & Fränti, 2014 | Hungarian-balanced K-means 算法来源，ELDR 的离线聚类核心。 |
| [METRO] Yu et al., 2025 | "Balance activated experts, not tokens"——ELDR 的 per-decoder EP load balancing 遵循其思路。 |
| [vLLM] Kwon et al., 2023 | ELDR 的实现平台，约 2000 行 Python 作为 thin layer 叠加。 |
| [eapatterns] Bambhaniya et al., 2026 | 最接近的同期工作：同样用 prefill activation 预测 decode，但目标是减少 inter-node all-to-all 通信而非 HBM expert weight loading。 |
| [Semantic Parallelism] Li et al., 2026 | Co-locate experts with tokens，利用 expert locality 信号但目标是 EP 通信优化。 |
| [Lynx] Gupta et al., 2026 | Batch-aware expert selection，但 lossy（改变 token 的 expert 选择），与 ELDR 的 lossless 路径形成对比。 |
| [WildChat] Zhao et al., 2024 | Language workload 数据来源，其高度偏斜的语言分布（English+Chinese ~75%）既是 ELDR 的机会也是其评估的局限。 |

## 7. 批判性分析

### 7.1 核心观察并非首创

ELDR 的 enabling observation——prefill expert activation 与 decode expert activation 高度相关——与 eapatterns（Bambhaniya et al., 2026, arXiv 2604.23150）独立发现的同一现象高度重合。ELDR 自己在 §7 承认 eapatterns 是"closest to us"，但区分说 eapatterns 目标是减少 inter-node all-to-all 通信而 ELDR 目标是减少 HBM expert weight loading。这个区分在系统层面成立，但两篇论文的**核心算法洞察**（用 prefill activation 预测 decode expert 使用 → 聚类相似请求 → 降低 active expert count）高度重合。ELDR 的真实增量在于把这个洞察应用到 PD-disaggregated 的 decode 路由场景，并配套了 block-granular signature cache 机制。

Semantic Parallelism（Li et al., 2026, arXiv 2503.04398）也利用 expert locality 信号做 model-data co-scheduling，但其目标同样是 EP 通信优化而非 decode bandwidth。三条独立工作在同期收敛到同一个 signal，说明 expert locality 是 MoE serving 中一个被广泛忽视但价值明确的优化维度。

### 7.2 组件技术是标准方法的直接应用

Balanced K-means 引自 Malinen & Fränti 2014；IDF 加权是 NLP/IR 领域从 TF-IDF 时代就有的标准去噪手段；cosine similarity 路由是最近邻检索的基本操作。论文的贡献在于把这些组件正确组装到 decode routing 的 pipeline 中，并用 Spearman ρ 作为 signature 质量的统一评估准则。这属于**高质量的系统集成工作**，而非算法层面的突破。

### 7.3 Signature 质量的实际水平被部分掩盖

论文用 Spearman ρ 衡量 signature distance 对 decode-time expert overlap 的排序预测能力（Eq. 1），但正文只报告了 IDF 带来的增量（"1.5pt mean, 4.9pt worst case"），从未给出 ρ 的绝对值。从消融实验推断，count·idf 在 GPT-OSS language 上的 ρ 大约只有 0.68（从 "0.63→0.68" 推断）。这个水平的 rank correlation 意味着 signature 对 expert overlap 的预测是 moderate 的——对排序有用的噪声信号，而非强确定性映射。论文没有讨论 ρ=0.68 对 routing 质量的上界意味着什么：在 ρ=0.68 的排序空间中做 K-means 聚类，cluster 内部的 expert overlap 一致性有多大保证？

### 7.4 Layer mask 的 greedy selection 依赖 calibration 分布

Greedy layer selection（§4.2.3）在 1000 条 calibration prompt 上按 ρ 增益贪心选层。如果 serving 时的流量分布偏离 calibration 分布，选出的层子集可能不再最优。论文没有评估 distribution shift 下的 signature 退化程度。例如，如果 calibration 以 code 为主但 serving 时 legal 请求激增，code-optimized layer mask 可能遗漏了 legal domain 最有区分度的层。

### 7.5 实验平台单一

所有实验在 5-node AMD MI300X 集群上完成（§6），NVIDIA GPU 生态（A100/H100/H200）完全缺失。vLLM 的主力部署平台是 NVIDIA GPU，ELDR 的 signature capture overhead（0.86ms，其中 reduce scatter 0.48ms）和 HBM bandwidth 特性在不同硬件上可能表现不同。MI300X 的 HBM3 带宽（5.3 TB/s）与 H100 的 HBM3（3.35 TB/s）差异显著，MoE decode 的 memory-bandwidth-bound 特性意味着 expert weight loading 的相对成本在不同硬件上会变化。论文未讨论硬件可移植性。

### 7.6 Tail latency 改善在 soft domain boundary 场景下不一致

论文自己报告：language workload 下 GPT-OSS-120B 的 tail TPOT 回退 1.5%，Gemma-4-26B-A4B 回退 0.2%（§6.1）。虽然论文归因于"noise"，但 task workload 上三个模型的 tail TPOT 全部改善（3.4–6.0%），两个 workload 的系统性差异暗示 expert locality 在 domain boundary 模糊时收益下降。Task workload 的四个 domain（code/math/medical/legal）边界清晰、expert 分化程度高；language workload 的语言间 expert overlap 更大，signature cluster 的 purity 更低，导致 locality routing 的 tail latency 收益被 cluster 内部的 variance 抵消。

### 7.7 Prefix cache 合成验证不充分

Figure 15 的 prefix cache ablation 是论文声称"locality benefit and prefix-cache benefit are additive"的唯一证据，但只覆盖了 6 个 (model, dataset) cell 中的 1 个（GPT-OSS-120B task）。没有在 Qwen3 或 Gemma 上验证，也没有在 language workload（prefix reuse 更高的场景）上测试。

### 7.8 Offline calibration 对 workload 稳定性的隐含假设

论文声称"re-fitting is cheap: under 10s on CPU"（§4.1），但这个 10s 只是 clustering 的计算时间。**重新收集 calibration 数据**（1000 条 prompt 的 prefill pass）需要 4–15 分钟（§6），且需要代表性流量样本。如果 serving 期间流量模式漂移（如白天以 code 为主、晚上以 chat 为主），要么接受次优路由，要么频繁 recalibrate。论文没有评估 workload drift 下的性能退化，也没有提出 adaptive 方案。

### 7.9 与 lossy 方法的比较缺失

Related work 列出了 Lynx（batch-aware expert selection）、XShare（in-batch expert sharing）、Opportunistic Expert Activation——三者都通过**修改 expert selection** 来减少 active expert count，与 ELDR 的目标完全一致但手段不同（有损 vs ELDR 的无损）。论文声称 ELDR 是"lossless"而这些方法"approximate"，但没有给出任何实验比较来量化 lossless 带来的收益是否足以抵消 routing-only 优化的收益上限。如果 Lynx 在相同 active expert 减少量下 TPOT 改善更大（以微小精度损失为代价），ELDR 的"lossless"特性在实际部署中是否值得，需要至少一个 accuracy-efficiency frontier 的对比。这使得"lossless"更像是一个 design choice 而非经过验证的优势。

### 7.10 "Lossless"声明缺乏 output 质量验证

论文声称"model outputs unchanged"（Abstract）和"outputs match standard top-k gating"（§7），但没有提供任何 output-level 验证（如 exact match rate、BLEU、或 human eval）。在 PD-disaggregated 设置下，KV cache transfer 的精度（bf16 vs mxfp4）、不同 worker 的 numerical precision 差异可能导致微小的 output divergence。虽然理论上 expert selection 不变，但实际验证缺失。

### 7.11 τ=0.1 是 magic number

Locality-band routing 的 τ 值在 4 个点（0, 0.1, 0.2, 0.3）上做了 ablation（fig:tau_ablation），选了 0.1。但 τ 的最优值理论上应随 signature 分布的方差、decode worker 数量、traffic skew 程度变化。论文没有提供 τ 的选择准则或自适应调整策略。

### 7.12 消融实验的 baseline 不统一

Signature transform ablation（fig:transform_ablation）以 RR 为 baseline 报告 Δ%，而 main results（fig:main_task, fig:main_language）对比的是 best load balancer。Cluster balance ablation（fig:cluster_ablation）和 τ ablation（fig:tau_ablation）又回到 RR baseline。这种不统一使得读者难以跨 ablation 比较各组件的边际贡献大小。

## 8. 方法细节

### 8.1 架构总览

ELDR 作为 vLLM 之上的 thin layer 集成到 PD 分离式服务栈中，由三个组件构成：routing proxy、engine-side hooks、offline pipeline（约 2,000 行 Python）。不修改模型、gate 决策、kernel、batching。

![ELDR 系统架构总览](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/04_design/fig_overview.pdf)

图解：三阶段架构。(1) Prefill 阶段捕获 per-block expert signature 并与 KV cache 共存；(2) 离线阶段用 balanced K-means 在 calibration signature 上聚类，每个 decode worker 对应一个 centroid；(3) 在线阶段在 handoff 时计算请求 signature 与 centroid 的 cosine similarity，在 locality band 内选负载最低的 worker。整个系统作为 thin layer 叠加在 vLLM 的 PD 分离栈之上，不修改 model、kernel、batching。

### 8.2 Expert Signature 设计

**目标函数：** Signature 的质量用 Spearman rank correlation 衡量（Eq. eq:rho）：

$$\rho = \mathrm{Spearman}\big(\mathrm{cos\text{-}dist}(s_i, s_j),\;\mathrm{cos\text{-}dist}(p_i, p_j)\big)$$

其中 $p_i \in \mathbb{R}^{LE}$ 是 request $i$ 的 decode-time per-(layer, expert) 激活概率向量（L2 归一化后）。$\rho$ 衡量 signature 距离能否忠实地排序 decode-time expert overlap——使用 Spearman 而非 Pearson，因为两个距离空间维度不同，只有排序顺序对 clustering 有意义。

**三条设计原则：**

1. **离散而非连续：** 只计 top-k expert 的选择次数，不用连续 gate score。理由：sub-threshold expert 不会 load 权重，连续 softmax score 给这些专家分配了不该有的质量，稀释了区分度。

2. **IDF 降噪：** 乘以逆文档频率权重 $w(\ell,e) = \log\!\big((|\mathcal{C}|+1)/(\mathrm{df}(\ell,e)+1)\big)$，压制几乎每个请求都激活的 generalist expert，放大区分度高的 specialist expert。

3. **贪心层选择：** 每次加入最能提升 cumulative $\rho$ 的层，直到 $\rho$ 峰值。每个 cell 在 $N^* < L$ 处达到峰值，比全层 $\rho(L)$ 高 0.005–0.032。

**构建步骤：**

1. **Count**：每个 layer $\ell$ 统计 prefill token 被路由到各 expert 的次数，得到 $c_r(\ell) \in \mathbb{N}^E$。
2. **IDF reweight**：$\tilde{c}_r(\ell,e) = c_r(\ell,e) \cdot w(\ell,e)$。
3. **Layer mask**：用贪心选择的 layer subset $\mathcal{S}$，stack 为 $x_r = [\tilde{c}_r(\ell)]_{\ell \in \mathcal{S}} \in \mathbb{R}^{N^* \cdot E}$。
4. **L2 normalize**：$s_r = x_r / \|x_r\|_2$，使相似度反映 expert usage 的形状而非请求的 token 数。

### 8.3 Signature 设计验证

![六种 candidate transformation 的 ρ 值对比](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/04_design/sig_transform.pdf)

图解：横轴为 6 种候选变换（count, count·idf, √count, gate-prob, gate-logit, binary），纵轴为 Spearman ρ。Bars 是 6 个 cell（3 models × 2 workloads）的均值，whiskers 为 min/max。三个离散变体系统性地优于两个连续变体（mean ρ 差距 > 0.035），count·idf 在均值和 worst-case 上均领先——在 GPT-OSS task 上比 plain count 高 8.9pt，因为 IDF 成功压制了少数 generalist expert 的主导效应。

![Greedy layer selection 下 cumulative ρ 随层数保留数的变化](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/04_design/sig_layers.pdf)

图解：每个 panel 为一个模型，蓝色为 task、橙色为 language。星号标记 ρ 峰值处的 N*。额外层增加不分离请求的维度，稀释 signature 方向——layer mask 压缩是有必要的。ELDR 采用每个 cell 的 peak N* 作为 layer mask 大小。

### 8.4 离线聚类：Hungarian-balanced K-means

标准 K-means 无 size 约束，在偏斜数据上产生不均匀 cluster，直接导致 decoder load 不均。ELDR 使用 Hungarian-balanced K-means（引自 Malinen & Fränti, 2014），用 Hungarian algorithm 做全局最优分配，每个 centroid 最多取 $\lceil N/K \rceil$ 个点，最小化总 cosine distance。

![PCA of calibration signatures with balanced centroids](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/04_design/cluster_pca.pdf)

图解：校准 signature 的前两个主成分投影，K=8 个 centroid 叠加，按 task domain（top）和 WildChat top-4 language（bottom）着色。Task domain（Code/Math/Medical/Legal）和不同语言在 signature space 形成可分离的聚类结构。Centroid 分散覆盖各语义区域而非挤在最密集处——这正是 balance 约束的效果：vanilla K-means 会将 centroid 拉向最密集模式，而 balanced K-means 向外拉以吸收各自的 ≈N/K 份额。一些 centroid 落在投影的稀疏区域，但这是保证 equal cluster size 的必要代价。

### 8.5 在线路由：Locality-band routing

对于每个请求，计算其 signature 与 K 个 centroid 的 cosine similarity，设 $s^* = \max_k s_k$。在满足 $s_k \ge s^* - \tau$ 的 worker（locality band）中，选择负载最低的（即 in-flight decode 请求数最少）。参数 $\tau \in [0,1]$ 在 pure top-1（$\tau=0$）和 pure JSQ（$\tau=1$）之间插值。

自适应性：signature 置信度高时，band 中 worker 少（保持 locality）；signature 模糊时，band 中 worker 多（偏向 load balance）。全文使用 $\tau=0.1$。

### 8.6 Prefix Cache Coherence

Prefix caching 重用共享前缀的 KV blocks，跳过 prefill——此时 gate 不运行，signature 不完整。ELDR 将 expert signature cache 与 KV cache 以 block 粒度共索引：

![Signature cache 与 KV cache 共享 block id 索引](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/04_design/fig_prefix_coherence.pdf)

图解：每个 KV block 对应一行 signature（int8 per (block, layer, expert)）。请求的总 signature 是其所有 block 的 signature 之和：$s_r = \sum_{b \in \mathcal{B}(r)} \mathrm{sig}[b]$。Partial hit 时，cached block 贡献先前请求的行，fresh block 贡献当前请求的行，总和等于 cold prefill 的结果。Signature cache 继承 KV cache 的生命周期——eviction、reuse 均自动同步，无需额外的 prefix-tree 或 eviction state。

存储开销：对评估模型（$L \le 48$, $E=128$），每 block 最多 6 KiB，总 cache < KV cache 的 1%。每请求 signature 为 12 KiB。每 forward pass 在一个 GPU pass 中将新 token 的 expert picks 累积到匹配行；signature retrieval 将 block rows batched 到 post-step D2H copy。

### 8.7 算力资源需求

- **实验集群**：5-node AMD MI300X（8 GPU/node, 192 GB HBM/GPU），400 Gbps NDR InfiniBand，8 ConnectX-7 HCAs per node
- **Calibration 收集**：1000 条 prompt × 每条 ~0.25–0.9s prefill ≈ 4–15 分钟（per model/dataset）
- **Offline fit**：greedy mask selection + balanced K-means < 10s on CPU
- **Per-request overhead**：0.86ms（1.2% of median TTFT 69ms），其中 prefill GPU reduce scatter 0.48ms + D2H 0.21ms、scheduler fetch 7μs、routing 0.15ms
- **Signature cache 内存**：$\text{num\_gpu\_blocks} \times L \times E$ bytes，对评估模型（$L \le 48, E=128$）每个 block ≤ 6 KiB，总 cache < 1% of KV cache

## 9. 实验

### 9.1 评测数据集

**Task workload**：11,668 条 prompt，混合四个 domain——legal 3,600 条（LexGLUE）、code 2,779 条（HumanEval, BigCodeBench, DS1000, MBPP）、math 2,744 条（GSM8K, MATH, MATH500, OlympiadBench, AQuA-RAT）、medical 2,545 条（MedQA, PubMedQA, MMLU professional-medicine subset）。Domain 比例不均匀（largest/smallest ratio = 1.41×），对 load balance 构成压力。

**Language workload**：14,000 条 prompt，来自 WildChat 的子集，继承 heavy language skew——English + Chinese 占 ~75%。使用 English、Chinese、Russian、French 四种主要语言，合计占 87.6%。

![WildChat 请求量的语言偏斜分布](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/03_motivation/wc_langdist.pdf)

图解：WildChat 的请求量高度集中在 English 和 Chinese 上（合计 ~75%），这种极端偏斜既是 expert locality 信号天然强烈的条件，也是 Domain baseline 在 language workload 上过载的根源——静态按语言分配 worker 时，hot language 的 worker 会严重过载。

每个数据集的 1,000 条 calibration split 与 serving evaluation set 不重叠。

### 9.2 评测指标

- **TPOT P50 / P99**（Time-per-Output-Token）：衡量 decode 阶段每生成一个 token 的中位/尾部延迟，是 ELDR 直接优化的目标
- **TTFT P50**（Time-to-First-Token）：衡量 prefill→decode 整体响应速度，ELDR 应保持 baseline 水平
- **Active experts per step**：每步 distinct expert 激活数，ELDR 降低此值的 mechanism evidence

所有指标以 request rate 为自变量 sweep（20–100 qps），每 rate 持续 120s，30s warmup。Output cap 为 512 tokens，enforce ignore_eos。

### 9.3 主实验结果

#### 9.3.1 Task workload

![Task workload 主实验结果](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_main_task.pdf)

图解：三个模型在 task workload 上的 TPOT（P50, P99）和 TTFT P50 随 request rate 的变化（8P16D）。ELDR（红色）在所有 rate 下均低于所有 load-balancing baseline。Domain-aware routing（基于 oracle label）是较强的 baseline（6.8–9.7% median TPOT improvement over load balancers），但 ELDR 仍以 1.4–6.9% 的优势胜出，因为 K=16 的 signature clusters 比 4 个 domain label 更细粒度，且 τ-band 允许跨 cluster 的 load spill。

ELDR 降低 median TPOT 7.0–13.9%（vs. best load balancer），tail TPOT 3.4–6.0%。Median TTFT 与 baseline 持平，接近饱和时 ELDR 略优（更快的 decode worker 缓解了 prefill back-pressure）。

#### 9.3.2 Language workload

![Language workload 主实验结果](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_main_lang.pdf)

图解：language workload 下 ELDR 的 median TPOT 改善 5.9–10.0%。但 tail TPOT 改善不一致：Qwen3-30B-A3B 降低 6.2%，GPT-OSS-120B 回退 1.5%，Gemma-4-26B-A4B 回退 0.2%（per-cell peak 下三者均改善）。Domain-aware routing 在此 workload 上表现退化：language label 是 expert activation 的粗糙 proxy，WildChat 的语言偏斜导致 hot block 过载，tail TPOT 回退最多 6.1%。ELDR vs Domain: median TPOT 降低 5.7–9.1%, tail TPOT 降低 7.0–9.5%。

#### 9.3.3 关键数据汇总（ELDR vs 最佳 load-balancing baseline，mean across rates）

| 模型 | Workload | Median TPOT 降低 | Tail TPOT 降低 |
|------|----------|-----------------|---------------|
| Qwen3-30B-A3B | Task | 13.9% | 6.0% |
| GPT-OSS-120B | Task | 7.0% | 3.4% |
| Gemma-4-26B-A4B | Task | 9.4% | 5.2% |
| Qwen3-30B-A3B | Language | 10.0% | 6.2% |
| GPT-OSS-120B | Language | 7.3% | −1.5% |
| Gemma-4-26B-A4B | Language | 5.9% | −0.2% |

### 9.4 消融实验

#### 9.4.1 Active-Expert Reduction 验证

![Mean active experts per decode step: ELDR vs RR](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_expert_reduction.pdf)

图解：Qwen3-30B-A3B task workload 8P16D，横轴为 decode batch size，纵轴为 per-step active expert count（聚合 ~50K decode steps）。ELDR 在所有 batch size 上均低于 RR，平均减少 22.0%——这直接验证了 TPOT 改善来自 active expert reduction 这一 mechanism，而非其他因素。

#### 9.4.2 Signature Transform 消融

![Signature transform ablation: count·idf vs gate-prob](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_transform_ablation.pdf)

图解：count·idf vs. gate-prob 的 TPOT P50/P99 相对 RR 的 Δ%（6 个 model×dataset cell，rate=60 qps）。count·idf 在 P50 上平均额外降低 3pp，最高 14pp，验证了 discrete signature 的设计选择——ρ 指标忠实排序 signature 质量，discrete prefill count 是正确的基元。

#### 9.4.3 Cluster Balance 消融

![Cluster balance ablation: vanilla K-means vs balanced K-means](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_cluster_ablation.pdf)

图解：τ=0.1, 8P16D。Vanilla K-means 在 median TPOT 上最多降低 9.8%，但 tail TPOT 回退最多 17.4%——per-decoder locality win 被 load imbalance 抵消。Hungarian-balanced K-means 同时降低 P50（最多 12.6%）和 P99（最多 6.8%），证明 balance constraint 是 tail latency 的必要条件。没有 balance 的 locality routing 反而比 round-robin 更差。

#### 9.4.4 Locality Band Width (τ) 消融

![τ ablation across 6 cells and 4 τ values](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_tau_ablation.pdf)

图解：τ ∈ {0, 0.1, 0.2, 0.3} 下 mean Δ% vs. RR（6 个 cell = 3 models × 2 workloads）。Pure top-1（τ=0）在 4/6 workload 上 tail TPOT 回退（Gemma language 最多 7.9%，Gemma task 6.7%），因为 burst 请求聚集到同一 decoder。τ=0.1 消除所有回退，同时 median TPOT 降低 5.2–12.7%。τ > 0.1 后 tail 改善饱和且 median 开始恶化（过多请求 spill 出 locality band），因此选择 τ=0.1。

#### 9.4.5 Prefix Cache Composition

![Prefix cache composition on GPT-OSS-120B](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_prefix_cache_gptoss_task.pdf)

图解：GPT-OSS-120B task workload 上 prefix cache on/off 对 ELDR vs. RR 的影响（rate=100 qps, 8P16D）。Cache on 对两个 router 都大幅降低 TTFT 且不改变 TPOT。ELDR 的 TPOT 优势（P50 ~13%, P99 ~5%）在两种 cache 状态下保持——locality benefit 和 prefix-cache benefit 是 additive 的。Secondary effect：ELDR 的更快 decode worker 提前 drain 请求，缩短 prefill queue，cache off 时 TTFT 也更低。注意此消融仅覆盖 6 个 cell 中的 1 个。

#### 9.4.6 运行时开销

| 组件 | 位置 | P50 延迟 | 占 TTFT % |
|------|------|---------|-----------|
| record() hook | prefill host | 0.02ms | < 0.1% |
| reduce() scatter | prefill GPU | 0.48ms | 0.7% |
| stage_sigs() D2H | prefill GPU | 0.21ms | 0.3% |
| pop_sig fetch | scheduler | 7μs | < 0.1% |
| Route (τ-JSQ) | proxy | 0.15ms | 0.2% |
| **合计** | | **0.86ms** | **1.2%** |

表解：ELDR 的 per-request 开销（Qwen3-30B-A3B, task, 8P16D, 60 qps, median TTFT 69ms）。Prefill GPU 端的 reduce scatter（0.48ms）和 D2H copy（0.21ms）占总开销的 80%，scheduler 和 proxy 端开销可忽略。Signature cache 占 HBM 0.24%，每个请求的 signature 12 KiB。

### 9.5 结果分析

#### 作者的分析

作者将 ELDR 的改善归因于三个机制的组合：(1) expert signature 捕获了 prefill→decode 的 expert 激活相关性，使 locality-aware routing 可行；(2) balanced K-means 确保 cluster 大小均匀，避免 load imbalance 抵消 locality 收益；(3) locality-band routing 在 signature 置信度低时回退到 load balance，吸收实时 skew。作者强调 ELDR 是 lossless 的——它只改变 request 被分配到哪个 worker，不改变 token 的 expert selection，因此 outputs 与标准 top-k gating 完全一致。

作者还指出，ELDR 与 intra-worker balancing（如 EPLB）正交：每个 decode worker 可以在内部独立运行 EPLB 来平衡 EP rank 间的 expert load，而 ELDR 在 worker 间做 locality-aware routing。两者可以组合使用。ELDR 的 improvement 随 decode worker pool 扩大而增长（8P8D: 8.0% → 8P16D: 9.8% → 8P24D: 10.2%），因为更多 workers 意味着更细的 signature clusters 和更小的 per-worker expert coverage。

#### Agent 的分析

**改善幅度的天花板值得关注。** Fig:expert_reduction 显示 active expert count 减少 22%，但 median TPOT 仅改善 ~10%——这意味着非 MoE 组件（attention、QKV projection、normalization）在总 decode 延迟中占比不小，限制了专家局部性优化的天花板。论文自身在 §3.1 承认"non-MoE compute scales with active requests"，但未量化这个天花板有多低。一个简单的 Amdahl-style 分析——MoE layer latency 占 total decode latency 的比例 × expert count reduction 带来的 MoE layer speedup——可以帮助读者理解 22% expert reduction 如何 translate 到 5.9–13.9% 的 TPOT reduction。

**Language workload 上 tail latency 的不一致改善暗示 method 对 soft domain boundary 的鲁棒性有限。** GPT-OSS-120B 和 Gemma-4-26B-A4B 在 language workload 上 tail TPOT 微弱回退，而 Qwen3-30B-A3B 改善 6.2%。三个模型在 task workload 上全部改善的 pattern 说明这不是纯 noise。更可能的解释是 language workload 的 domain boundary 更模糊（同一种语言内的请求可能有 code、chat、translation 等不同子任务），导致 expert signature 的 cluster 纯度降低。

**GPT-OSS-120B 的 mxfp4 量化可能影响 prefill→decode correlation。** GPT-OSS 使用 mxfp4 量化（其他两个用 bf16），且 top-4（vs. 其他模型的 top-8）。fig:pd_scatter 显示 GPT-OSS 的 scatter 更分散，暗示量化噪声和更稀疏的 gate 可能降低了 prefill→decode 的 expert correlation，进而降低 signature 的预测力。

**235B 扩展实验的改善幅度明显缩小。** Qwen3-235B-A22B（TP=4, EP=4, 40 GPU）的 median TPOT 仅降 2.7–4.3%，明显小于 TP=1 场景。可能因为 EP rank 内的 expert 并行已经稀释了 locality 的边际收益——当每个 EP rank 只持有 E/EP 个 expert 时，跨 worker 的 expert 重叠被 EP 分片所掩盖。

### 9.6 拓扑泛化与大模型扩展

**拓扑泛化**（Qwen3-30B-A3B language workload, TP=1）：

| 拓扑 | GPU 数 | TPOT P50 Δ | TPOT P99 Δ |
|------|--------|-----------|-----------|
| 8P8D | 16 | −8.0% | −2.5% |
| 8P16D | 24 | −9.8% | −0.8% |
| 8P24D | 32 | −10.2% | −1.1% |

表解：ELDR 的 median TPOT 改善随 decode pool 扩大单调增长，符合机制预期（更多 workers → 更细 clusters → 更小 per-worker expert union）。Tail TPOT 在所有拓扑下保持 baseline 水平。

![Qwen3-235B-A22B 大模型扩展实验](sources/2607.00466-eldr-expert-locality-aware/arxiv/figure/06_evaluation/fig_qwen235_2p8d.pdf)

图解：40 GPU, 5 nodes, TP=4, EP=4, language workload, 24–56 qps。ELDR 在每个 rate 上均低于 RR，median TPOT 降低 2.7–4.3%，tail TPOT 降低 0.6–2.0%。论文额外启用了 per-cluster per-layer expert-rank permutation（基于 METRO 的思路）来平衡 EP rank 间的 expert load，将 cluster 内的 hot expert 均匀分配到 4 个 GPUs，避免单 rank 瓶颈。改善幅度明显小于 TP=1 场景，可能因为 EP 分片已稀释了 locality 的边际收益。
---
