---

# 批判性分析备忘录：ELDR (2607.00466)

## 论文自己声称的贡献 vs. 真实增量

**1. 核心观察——prefill activation 与 decode activation 高度相关——并非 ELDR 首创。** eapatterns (Bambhaniya et al., 2026, arXiv 2604.23150) 在同期工作中独立发现了"strong correlation between prefill and decode expert activations"，并基于此提出 workload-aware micro-batch grouping。ELDR 自己在 §7 承认 eapatterns 是"closest to us"，但区分说 eapatterns 目标是减少 inter-node all-to-all 通信而 ELDR 目标是减少 HBM expert weight loading。这个区分在系统层面成立，但两篇论文的**核心算法洞察**（用 prefill activation 预测 decode expert 使用 → 聚类相似请求 → 降低 active expert count）高度重合。真实增量在于 ELDR 把这个洞察应用到了 PD-disaggregated 的 decode 路由场景，并配套了 signature cache 机制。

**2. 三大贡献中的两项是标准技术的直接应用。** Balanced K-means 引自 Malinen & Fränti 2014；IDF 加权是 NLP/IR 领域的标准去噪手段；cosine similarity 路由是最近邻检索的基本操作。论文的贡献在于把这些组件正确组装到 decode routing 的 pipeline 中，并用 Spearman ρ 作为 signature 质量的统一评估准则。这属于**高质量的系统集成工作**，而非算法层面的突破。

## Signature 设计与质量

**3. Signature 质量指标 ρ 的实际数值未在正文报告，掩盖了 moderate 的预测能力。** 论文用 Spearman ρ 衡量 signature distance 对 decode-time expert overlap 的排序预测能力（Eq. 1），但正文只报告了 IDF 带来的增量（"1.5pt mean, 4.9pt worst case"），从未给出 ρ 的绝对值。从消融实验推断，count·idf 在 GPT-OSS language 上的 ρ 大约只有 0.68（从 "0.63→0.68" 推断）。这个水平的 rank correlation 意味着 signature 对 expert overlap 的预测是 moderate 的——对排序有用的噪声信号，而非强确定性映射。

**4. Layer mask 的 greedy selection 依赖 calibration 数据分布，缺乏泛化保证。** Greedy layer selection（§4.2.3）在 1000 条 calibration prompt 上按 ρ 增益贪心选层。如果 serving 时的流量分布偏离 calibration 分布，选出的层子集可能不再最优。论文没有评估 distribution shift 下的 signature 退化程度。

## 实验覆盖不足

**5. 仅在 AMD MI300X 上评估，NVIDIA GPU 生态完全缺失。** 所有实验在 5-node MI300X 集群上完成（§6）。vLLM 的主力部署平台是 NVIDIA GPU（A100/H100/H200），ELDR 的 signature capture overhead（0.86ms，其中 reduce scatter 0.48ms）和 HBM bandwidth 特性在不同硬件上可能表现不同。论文未讨论硬件迁移的可移植性。

**6. 尾部延迟改善在 language workload 上不一致，暗示 method 对 soft domain boundary 场景的鲁棒性有限。** 论文自己报告：language workload 下 GPT-OSS-120B 的 tail TPOT 回退 1.5%，Gemma-4-26B-A4B 回退 0.2%（§6.1）。虽然论文归因于"noise"，但 task workload 上三个模型的 tail TPOT 全部改善（3.4–6.0%），两个 workload 的系统性差异暗示 expert locality 在 domain boundary 模糊时（language vs task）收益下降。

**7. Prefix cache 合成实验仅在一个模型上验证（GPT-OSS-120B task）。** Figure 15 的 prefix cache ablation 是论文声称"locality benefit and prefix-cache benefit are additive"的唯一证据，但只覆盖了 6 个 (model, dataset) cell 中的 1 个。没有在 Qwen3 或 Gemma 上验证，也没有在 language workload（prefix reuse 更高的场景）上测试。

**8. 无 long-context / 多轮对话场景评估。** 所有实验的 output cap 为 512 tokens，prompt 长度未报告但来自 public benchmarks（通常 < 4K tokens）。在长上下文（32K+）场景下，prefill expert activation 的覆盖范围更大，signature 的维度和稀疏性会改变；多轮对话中同一用户的 expert 使用模式可能随对话推进漂移，对 static offline clustering 构成更大挑战。

## 工程组合与复现风险

**9. Offline calibration 的隐含假设：workload 在 serving 期间稳定。** 论文声称"re-fitting is cheap: under 10s on CPU"（§4.1），但这个 10s 只是 clustering 的计算时间。**重新收集 calibration 数据**（1000 条 prompt 的 prefill pass）需要 4–15 分钟（§6），且需要代表性流量样本。如果 serving 期间流量模式漂移（如白天以 code 为主、晚上以 chat 为主），要么接受次优路由，要么频繁 recalibrate。论文没有评估 workload drift 下的性能退化，也没有提出 adaptive 方案。

**10. τ=0.1 是一个 magic number，缺乏理论依据或自适应机制。** Locality-band routing 的 τ 值在 4 个点（0, 0.1, 0.2, 0.3）上做了 ablation（Figure 14），选了 0.1。但 τ 的最优值理论上应随 signature 分布的方差、decode worker 数量、traffic skew 程度变化。论文没有提供 τ 的选择准则或自适应调整策略。

**11. 与近期强 baseline 的比较缺失。** Related work 列出了 Lynx（batch-aware expert selection）、XShare（in-batch expert sharing）、Opportunistic Expert Activation——三者都通过**修改 expert selection** 来减少 active expert count，与 ELDR 的目标完全一致但手段不同（有损 vs ELDR 的无损）。论文声称 ELDR 是"lossless"而这些方法"approximate"，但没有给出任何实验比较来量化 lossless 带来的收益是否足以抵消 routing-only 优化的收益上限。这使得"lossless"更像是一个 design choice 而非经过验证的优势。

**12. "Lossless"声明缺乏 output 质量验证。** 论文声称"model outputs unchanged"（Abstract）和"outputs match standard top-k gating"（§7），但没有提供任何 output-level 验证（如 exact match rate、BLEU、或 human eval）。在 PD-disaggregated 设置下，KV cache transfer 的精度（bf16 vs mxfp4）、不同 worker 的 numerical precision 差异可能导致微小的 output divergence。虽然理论上 expert selection 不变，但实际验证缺失。

## 实验设计细节

**13. 每个 request rate 固定运行 120s + 30s warmup，采样时间窗口短。** 在 Poisson 到达下，120s 的 steady-state 窗口可能不足以捕捉 tail behavior 的统计显著性，特别是 p99 TPOT 在低 rate（20 qps）下只有约 2000 个样本点。论文未报告 confidence intervals 或 statistical significance tests。

**14. 消融实验的 baseline 不统一。** Signature transform ablation（Figure 12）以 RR 为 baseline 报告 Δ%，而 main results（Figures 8–9）对比的是 best load balancer。Cluster balance ablation（Figure 13）和 τ ablation（Figure 14）又回到 RR baseline。这种不统一使得读者难以跨 ablation 比较各组件的边际贡献大小。

---
