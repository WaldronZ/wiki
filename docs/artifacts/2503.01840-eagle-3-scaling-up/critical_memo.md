## EAGLE-3 批判性分析备忘录

---

**1. 与 HASS 的"训练时模拟推理"高度同构，创新边界需谨慎标注。**
论文自身在 §3.2 承认 "HASS and EAGLE-3 both make similar modifications to the attention mechanism to simulate the testing process during training"。两者都在训练时构造特殊的因果 mask 来模拟多步自回归推理过程。论文试图用"动机不同"来区分（HASS 是缓解特征预测误差累积，EAGLE-3 是去除约束），但从方法机制上看，核心的训练-time test 技术并非 EAGLE-3 首创。**基于本文相关工作判断**，这一区分更像是对同一技术赋予不同的叙事框架。

**2. "Scaling Law" 声名过重：缺少幂律拟合，仅为单调曲线。**
论文标题和贡献列表大写 "Discovery of a scaling law for inference acceleration"，但 Figure 1 (fig:sc) 展示的仅是"更多数据 → 更高加速比"的单调趋势曲线，并未给出幂律公式（如 loss ∝ N^α·D^β 的形式化拟合）、置信区间或理论解释。对比 Chinchilla scaling law (Hoffmann et al., 2022) 或 Kaplan et al. (2020) 的形式化工作，这里的"scaling law"用词过于宽泛，更准确的说法应是"data scaling trend"。

**3. 实验覆盖存在明显缺口：未测试 405B / 671B 模型。**
论文明确承认 "Due to the GPU constraint, we are unable to test EAGLE-3 on the 405B and 671B models"。对于一篇声称发现 "scaling up" 规律的论文，不在更大规模模型上验证恰恰回避了最关键的问题：draft model 的多层特征融合策略在目标模型从 8B → 70B → 405B 时，中间层选择、融合维度、训练数据需求如何变化？没有这些数据，"scaling" 的声称缺乏闭环证据。

**4. EAGLE 本身启发了 DeepSeek-v3 的 multi-token prediction，但 EAGLE-3 反而放弃了特征预测——叙事张力未被正面处理。**
论文在 §3.2 自述 "EAGLE inspired the multi-token prediction technique used in the pre-training of DeepSeek-v3, which in turn inspired new architectural designs in EAGLE-3"。这是一个有趣的双向影响叙事，但论文没有正面讨论一个核心矛盾：DeepSeek-v3 采用了 EAGLE 的特征预测思想并取得成功，而 EAGLE-3 却将特征预测视为"不必要的约束"予以抛弃。论文应更清楚地解释为什么在预训练场景中有价值的机制在 draft model 训练中反而成为瓶颈。

**5. 训练成本完全缺失：8× 数据量 + 模拟多步训练 = 更高的训练开销。**
论文声称使用 "approximately 8x more data than EAGLE"，且 training-time test 要求在训练时模拟 2-3 步推理（Figure 7 展示了多步 attention mask）。但论文未报告任何训练成本数据：GPU 小时数、训练 wall-clock 时间、draft model 训练与目标模型推理的资源比。对于工程落地而言，draft model 的训练成本是决策关键变量——如果 8× 数据 + 模拟训练意味着训练成本从 1 天变成 2 周，很多场景下可能不划算。

**6. 多层特征融合的推理开销未量化。**
EAGLE-3 在推理时需要从目标模型提取低、中、高三个层次的特征，拼接后过 FC 层降维。相比 EAGLE 仅复用 top-layer features（无需额外计算），EAGLE-3 引入了：(a) 三个中间层特征的提取（需要 hook 或修改 forward pass）；(b) 3k → k 的 FC 映射。论文没有分析这一额外计算占 draft model 总推理时间的比例，也没有讨论对 GPU 内存占用的影响。在 latency-critical 的 batch=1 场景下，这部分开销可能不可忽略。

**7. 只测 5 个任务，回避了长序列和多语言场景。**
评测覆盖 MT-bench、HumanEval、GSM8K、Alpaca、CNN/DM，均为英文、相对短序列的任务。缺少：(a) 长上下文任务（如 RULER、∞-Bench）——draft model 的 acceptance rate 在长序列下是否退化？(b) 多语言任务——特征融合策略对中文/日文等语言是否同样有效？(c) 工具调用 / Agent 场景——这些场景的 token 分布与对话/代码差异很大。

**8. Draft model 架构极度精简（单层 Transformer decoder），可能掩盖了方法的真实上限。**
论文 §3.2 明确 "The core of the draft model in EAGLE-3 is a Transformer decoder layer"。单层 decoder 的表达能力非常有限。论文没有尝试 2 层、4 层等不同深度的 draft model，因此无法判断：(a) scaling law 的瓶颈究竟来自数据还是模型容量？(b) 多层特征融合在更深 draft model 上是否收益递减？这使得 scaling law 的声称更加脆弱——它可能只是在特定超参配置下的经验观察。

**9. 与 Sequoia、EAGLE-2 的关系仅限于"采用其动态树"，未做消融。**
论文 §3.2 末尾仅一句 "EAGLE-3 also adopts the context-aware dynamic draft tree proposed in EAGLE-2"。Sequoia (arXiv:2402.12374) 提出了硬件感知的最优树结构搜索，是更先进的树构建方案。论文未比较 EAGLE-3 + Sequoia 树 vs. EAGLE-3 + EAGLE-2 树的效果差异，也未讨论 EAGLE-3 的改进与动态树技术的正交性/可组合性。

**10. 通过 SGLang/vLLM 的 throughput 提升可能部分归功于框架优化而非方法本身。**
Table 5 (tab:sglang) 的实验标注 "The experiments were conducted by the SGLang team"，baseline 是 "SGLang without speculative sampling"。SGLang 框架的 continuous batching、PagedAttention 等优化本身就能提升 throughput，而 speculative sampling 在 batch size=64 时的 40% 提升是否全部来自 EAGLE-3 的 draft 质量，还是部分来自 SGLang 对 speculative decoding 的工程优化（如 KV cache 管理、batch 内 draft 长度自适应），论文没有做控制实验来分离这两个因素。

**11. 特征层选择策略缺乏讨论：哪三层？为什么？是否 target-model-dependent？**
论文多次提到使用 low/mid/high-level features，但 tex 源码中未找到具体指定选取哪几层（如第 1/16/32 层？第 1/中间/倒数第二层？）。不同目标模型（LLaMA 8B vs. 70B vs. Vicuna 13B）的层数不同，最优的特征层组合可能完全不同。论文没有给出层选择的敏感性分析或选择标准，这给复现者留下了显著的调参空间。

**12. temperature=1 条件下不与 Medusa 等方法对比，理由不充分。**
论文 Table 2 注释称 "Methods like Medusa relax acceptance conditions under non-greedy settings, which do not guarantee lossless acceleration. Therefore, we do not compare EAGLE-3 with these methods when temperature=1"。然而 Medusa 在 temperature>0 时的 relaxed acceptance 是有理论保证的（distributional equivalence under relaxed conditions），且实际使用中 temperature=1 是主流场景（chat 模型默认）。回避这一对比可能是因为 EAGLE-3 在非 greedy 场景下的优势不如 greedy 场景显著。

**13. "Up to 6.5x" 的 headline 数字来自最有利的任务×模型组合，而非平均值。**
Abstract 声称 "speedup ratio up to 6.5x"，但 Table 2 显示的 mean speedup 在 3.5x–5.2x 范围内（具体取决于模型和温度）。6.5x 很可能来自 DeepSeek-R1-Distill-LLaMA 8B 在 GSM8K 上的单一数据点（reasoning model 在数学推理任务上重复模式多，acceptance rate 天然偏高）。用 "up to" 而非 "on average" 来描述，容易误导读者对实际加速效果的预期。

**14. 复现风险：训练数据来源和配比未公开。**
论文提到使用 "approximately 8x more data than EAGLE"，但未说明：(a) 这 8× 数据的具体来源（ShareGPT 扩展？合成数据？其他对话数据集？）；(b) training-time test 中原始训练步与模拟步的数据配比；(c) 训练超参（learning rate schedule、warmup、batch size）。Without these details, independent reproduction of the claimed scaling trend is essentially impossible. The code is open-source (GitHub: SafeAILab/EAGLE), but training scripts and data pipelines are often the gap between "code available" and "reproducible."
