---
slug: "2503.01840-eagle-3-scaling-up"
title: "EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test"
title_zh: "EAGLE-3：通过训练时测试扩展大语言模型推理加速"
title_en: "EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test"
arxiv_id: "2503.01840"
year: 2025
authors:
  - Yuhui Li
  - Fangyun Wei
  - Chao Zhang
  - Hongyang Zhang
domains:
  - LLM Systems
tracks:
  - Inference Acceleration
problems:
  - Speculative Decoding
topics:
  - Speculative Decoding
  - LLM Inference
  - Draft Model Training
  - Scaling Law
methods:
  - Feature Fusion
  - Training-Time Test
  - Token Prediction
  - Draft Tree
research_line: Speculative Decoding
line_role: main
status: read
reading_stage: deep_read
importance: 4
confidence: 4
reproducibility: 3
has_code: true
---

# EAGLE-3：通过训练时测试扩展大语言模型推理加速

## 1. 基本情况

- **题目**：EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test
- **作者**：Yuhui Li（北京大学 / 滑铁卢大学）、Fangyun Wei（微软亚洲研究院）、Chao Zhang（北京大学）、Hongyang Zhang（滑铁卢大学 / Vector Institute）
- **单位**：北京大学、Microsoft Research、University of Waterloo、Vector Institute
- **arxiv 编号**：2503.01840v3
- **提交日期**：2025 年 3 月 3 日
- **arxiv 链接**：https://arxiv.org/abs/2503.01840v3
- **代码仓库**：https://github.com/SafeAILab/EAGLE

## 2. 核心贡献概述

**中文版**：EAGLE-3 发现 EAGLE 系列方法中 feature prediction 约束是限制训练数据 scaling 的根本瓶颈，通过去除 feature prediction 改为直接 token prediction、引入多层特征融合替代仅复用 top-layer features、以及在训练阶段模拟多步推理的 training-time test 技术，使 draft model 能够从更多训练数据中持续获益，最高实现 6.5x 加速比，较 EAGLE-2 提升约 1.4x。

**英文版**（摘自 Abstract）："EAGLE-3 abandons feature prediction in favor of direct token prediction and replaces reliance on top-layer features with multi-layer feature fusion via a technique named training-time test. These improvements significantly enhance performance and enable the draft model to fully benefit from scaling up training data."

## 3. 一句话精髓

如果把 LLM 推理比作一个翻译官逐字逐句地口译，speculative decoding 就是让一个实习生先猜后面几句，翻译官只需点头或摇头——EAGLE-3 的秘诀是：别让实习生死记硬背翻译官的脑电波（特征），让他直接练口语（token），同时多听几个深度的课堂录音（多层特征），并且在培训时就模拟真实口译场景（training-time test），这样实习生就能从海量练习材料中持续进步。

## 4. 学术贡献清单

### 4.1 动机的发现与阐明

论文揭示了一个此前未被充分讨论的问题：**EAGLE 的 feature prediction 约束导致 scaling 训练数据的收益极为有限**。

具体推理链如下：
1. LLM 社区的趋势是通过扩大训练数据提升模型能力（如 LLaMA 7B 从 1T → 2T → 15T tokens），EAGLE 理应也能通过增加 draft model 训练数据来提升加速效果。
2. 但实验发现，EAGLE 增加数据后加速比提升有限。作者将此归因于 EAGLE 的 loss 函数包含 feature prediction loss $l_{\text{fea}}$ 和 token prediction loss $l_{\text{token}}$ 两部分——feature prediction 作为一个额外约束，限制了 draft model 的表达能力。
3. 去除 feature constraint 后，第一个 draft token 的 acceptance rate（$0$-$\alpha$）显著提升，但第二个 draft token 的 acceptance rate（$1$-$\alpha$）仍然很低，因为 Step 1 的输出 $\hat{a}_{t+1}$ 与 ground-truth $f_{t+1}$ 偏差大，导致 Step 2 输入偏离训练分布。
4. 解决方案：在训练阶段模拟多步推理（training-time test），让 draft model 在训练时就适应自身输出作为输入的场景。

![图解：EAGLE 与 EAGLE-3 的 acceptance rate 对比（$0$-$\alpha$）——去除 feature constraint 后第一个 draft token 的接受率显著提升，证明 feature prediction 是瓶颈。EAGLE-3（绿色线）随数据增加持续上升，而 EAGLE（蓝色线）趋于平坦。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/alpha0.pdf)

![图解：$1$-$\alpha$ 对比——没有 training-time test 时（橙色线），第二个 draft token 的接受率极低且不随数据增长；加入 training-time test 后（绿色线）大幅提升。这是 training-time test 有效性的直接证据。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/alpha1.pdf)

### 4.2 方法的创新

1. **去除 feature prediction constraint**：EAGLE-3 的 loss 只保留 $l_{\text{token}}$，draft model 输出不再需要拟合目标模型的 top-layer features，获得完全自由的输入空间。
2. **多层特征融合**：将目标模型的 low-level ($l$)、middle-level ($m$)、high-level ($h$) 三层特征 concatenate 后经 FC 层降维，替代仅使用 top-layer features。直觉上，top-layer features 天然对应 next token 的 logits，用它预测 next-next token 很困难；低层 features 包含更丰富的语义信息。
3. **Training-time test**：在训练阶段模拟推理时的多步生成过程——Step 1 正常训练，Step 2 把 Step 1 的输出反馈给 draft model 继续训练，Step 3 类似。通过修改 attention mask 来处理 tree-like 的上下文关系。
4. **发现推理加速的 scaling law**：新架构下，增加训练数据导致 speedup ratio 持续上升，这在 EAGLE 原始架构中从未观察到。

### 4.3 实验上的核心结论

- EAGLE-3 在所有任务和目标模型上均取得最高加速比和最长平均接受长度。
- 最高加速比 6.5x（HumanEval，Vicuna 13B），平均加速比 3.0x–5.5x。
- 较 EAGLE-2 提升 20%–40%。
- 在 SGLang 框架下，batch size=64 时仍实现 1.38x throughput 提升（EAGLE 在 batch size=24 时 throughput 已开始下降）。
- 在 vLLM 框架下，batch size=56 时仍实现 1.01x throughput（EAGLE 在 batch size=32 时已降至 0.93x）。
- 消融实验证明两个改进（去除 feature constraint + 多层特征融合）各自都有显著贡献。

## 5. 写作故事线

论文的叙事结构清晰地分为"发现问题 → 分析原因 → 提出方案 → 验证效果"四段：

**第一段（Introduction 前半）**：从 LLM 推理的高成本问题出发，引出 speculative decoding 作为解决方案，再聚焦到 EAGLE 系列的 feature-level autoregression 方法。这段建立了"为什么需要更好的 speculative decoding"的背景——特别是 reasoning models（如 DeepSeek-R1）的出现使得推理成本占比进一步上升。

**第二段（Introduction 中段）**：关键转折——作者发现 scaling 训练数据对 EAGLE 收益有限。通过分析 $0$-$\alpha$ 和 $1$-$\alpha$ 两个 acceptance rate 指标，将问题定位到 feature prediction constraint。去除 constraint 后 $0$-$\alpha$ 提升但 $1$-$\alpha$ 仍然很低，这个反例自然引出了 training-time test 的必要性。

**第三段（Preliminaries + EAGLE-3）**：§2 先铺垫 speculative sampling 和 EAGLE/EAGLE-2 的背景知识。§3 详细描述 EAGLE-3 的推理流程（§3.1）和训练方法（§3.2）。值得注意的是，§3.2 末尾专门用一段区分 EAGLE-3 与 HASS 的异同——两者都修改了 attention mask 来模拟测试过程，但动机、方法和结果"distinctly different"。

**第四段（Experiments + Conclusion）**：用 5 个任务 × 4 个目标模型 × 2 个温度的全面实验矩阵验证效果。特别加入了 SGLang 和 vLLM 两个生产级框架的 throughput 测试，回应了"speculative decoding 在大 batch 下失效"的常见质疑。

整个故事的转折点在于 $0$-$\alpha$ vs $1$-$\alpha$ 的对比：它同时展示了去除 feature constraint 的好处和局限，为 training-time test 的引入提供了精确的动机。

## 6. 核心参考文献

| 编号 | 作者 / 年份 | 在本文中的角色 |
|------|-------------|----------------|
| [Leviathan et al., 2023] | Leviathan, Kalman, Matias / 2023 | Speculative decoding 的理论基础之一，本文的验证框架来源 |
| [Chen et al., 2023] | Chen, Borgeaud et al. / 2023 | Speculative sampling 的另一个独立提出者（DeepMind 版本） |
| [Li et al., 2024] (EAGLE) | Yuhui Li et al. / 2024 | 直接前作，提出 feature-level autoregression + top-layer feature reuse |
| [Li et al., 2024] (EAGLE-2) | Yuhui Li et al. / 2024 | 引入 context-aware dynamic draft tree，EAGLE-3 继承该技术 |
| [Cai et al., 2024] (Medusa) | Tianle Cai et al. / 2024 | 同族方法，multi-head parallel prediction，non-greedy 下不保证 lossless |
| [Zhang et al., 2024] (HASS) | Zhang et al. / 2024 | 类似的 training-time attention 修改，但保留 feature prediction，动机不同 |
| [Ankner et al., 2024] (Hydra) | Ankner et al. / 2024 | Sequentially-dependent draft heads for Medusa |
| [Touvron et al., 2023] (LLaMA) | Touvron et al. / 2023 | 目标模型系列，实验中使用 LLaMA-Instruct 3.1/3.3 |
| [DeepSeek-R1] | Guo et al. / 2025 | Reasoning model 代表，推动推理加速需求的关键动机 |
| [Zheng et al., 2024] (SGLang) | Zheng et al. / 2024 | 生产级推理框架，EAGLE-3 的 throughput 实验平台 |

## 7. 批判性分析

### 7.1 与 HASS 的方法高度同构，创新边界需谨慎标注

论文在 §3.2 承认 "HASS and EAGLE-3 both make similar modifications to the attention mechanism to simulate the testing process during training"。两者都在训练时构造特殊的因果 mask 来模拟多步自回归推理过程。论文试图用"动机不同"来区分（HASS 是缓解特征预测误差累积，EAGLE-3 是去除约束），但从方法机制上看，核心的 training-time test 技术并非 EAGLE-3 首创。这一区分更像是对同一技术赋予不同的叙事框架。不过，EAGLE-3 的关键差异在于**同时去除了 feature prediction loss**——这一组合确实产生了新的 scaling 行为，这是 HASS 没有观察到的。

### 7.2 "Scaling Law" 声名过重：缺少幂律拟合，仅为单调曲线

论文标题和贡献列表大写 "Discovery of a scaling law for inference acceleration"，但展示的仅是"更多数据 → 更高加速比"的单调趋势曲线，并未给出幂律公式（如 $\text{loss} \propto N^\alpha \cdot D^\beta$ 的形式化拟合）、置信区间或理论解释。对比 Chinchilla scaling law (Hoffmann et al., 2022) 或 Kaplan et al. (2020) 的形式化工作，这里的"scaling law"用词过于宽泛，更准确的说法应是 "data scaling trend"。

![图解：EAGLE-3 的 speedup ratio scaling 趋势——x 轴为相对于 ShareGPT 的数据规模倍数，y 轴为 speedup ratio。EAGLE-3（绿色线）随数据增加持续上升，而 EAGLE（蓝色线）趋于平坦。但曲线仅 4-5 个数据点且无幂律拟合，"scaling law" 名号有待商榷。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/scaale.pdf)

![图解：Average acceptance length $\tau$ 的 scaling 趋势——EAGLE-3 的 $\tau$ 从约 5.5 提升到约 7.5，而 EAGLE 基本持平在 4.0 左右。两条曲线的对比进一步印证 feature prediction constraint 是 scaling 瓶颈。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/scaletau.pdf)

### 7.3 实验覆盖存在明显缺口：未测试 405B / 671B 模型

论文明确承认 "Due to the GPU constraint, we are unable to test EAGLE-3 on the 405B and 671B models"。对于一篇声称发现 "scaling up" 规律的论文，不在更大规模模型上验证恰恰回避了最关键的问题：draft model 的多层特征融合策略在目标模型从 8B → 70B → 405B 时，中间层选择、融合维度、训练数据需求如何变化？没有这些数据，"scaling" 的声称缺乏闭环证据。

### 7.4 EAGLE 启发了 DeepSeek-V3 的 multi-token prediction，但 EAGLE-3 反而放弃了特征预测

论文在 §2.2 自述 "EAGLE inspired the multi-token prediction technique used in the pre-training of DeepSeek-v3, which in turn inspired new architectural designs in EAGLE-3"。这是一个有趣的双向影响叙事，但论文没有正面讨论一个核心矛盾：DeepSeek-V3 采用了 EAGLE 的特征预测思想并取得成功（用于预训练），而 EAGLE-3 却将特征预测视为"不必要的约束"予以抛弃。论文应更清楚地解释为什么在预训练场景中有价值的机制在 draft model 训练中反而成为瓶颈——可能的解释是 draft model 容量远小于目标模型，feature prediction 对小模型的约束效应更强，但论文没有展开讨论。

### 7.5 训练成本完全缺失

论文声称使用 "approximately 8x more data than EAGLE"，且 training-time test 要求在训练时模拟 2-3 步推理。但论文未报告任何训练成本数据：GPU 小时数、训练 wall-clock 时间、draft model 训练与目标模型推理的资源比。对于工程落地而言，draft model 的训练成本是决策关键变量。论文在 §4 的 Implementation 部分给出了优化器设置（AdamW, lr=5e-5）和数据来源（ShareGPT + UltraChat-200K），但缺少训练时长和 GPU 数量。

### 7.6 多层特征融合的推理开销未量化

EAGLE-3 在推理时需要从目标模型提取低、中、高三个层次的特征，拼接后过 FC 层降维。相比 EAGLE 仅复用 top-layer features（无需额外计算），EAGLE-3 引入了：(a) 三个中间层特征的提取（需要 hook 或修改 forward pass）；(b) $3k \to k$ 的 FC 映射。论文没有分析这一额外计算占 draft model 总推理时间的比例，也没有讨论对 GPU 内存占用的影响。

### 7.7 只测 5 个任务，回避了长序列和多语言场景

评测覆盖 MT-bench、HumanEval、GSM8K、Alpaca、CNN/DM，均为英文、相对短序列的任务。缺少：(a) 长上下文任务（如 RULER、∞-Bench）；(b) 多语言任务；(c) 工具调用 / Agent 场景——这些场景的 token 分布与对话/代码差异很大。

### 7.8 Draft model 架构极度精简（单层 Transformer decoder），可能掩盖了方法的真实上限

论文 §3.2 明确 "The core of the draft model in EAGLE-3 is a Transformer decoder layer"。单层 decoder 的表达能力非常有限。论文没有尝试 2 层、4 层等不同深度的 draft model，因此无法判断：(a) scaling law 的瓶颈究竟来自数据还是模型容量？(b) 多层特征融合在更深 draft model 上是否收益递减？

### 7.9 "Up to 6.5x" 的 headline 数字来自最有利的任务×模型组合

Abstract 声称 "speedup ratio up to 6.5x"，但 mean speedup 在 3.5x–5.5x 范围内。6.5x 来自 HumanEval 上 Vicuna 13B 的单一数据点（代码生成任务模板化程度高，acceptance rate 天然偏高）。用 "up to" 而非 "on average" 描述容易误导读者对实际加速效果的预期。

### 7.10 temperature=1 条件下不与 Medusa 对比，理由不充分

Table 1 注释称 Medusa 在 non-greedy 下 "relax acceptance conditions, which do not guarantee lossless acceleration"，因此 temperature=1 时不比较。然而 Medusa 的 relaxed acceptance 是有理论保证的（distributional equivalence under relaxed conditions），且实际使用中 temperature=1 是 chat 模型的默认设置。回避这一对比可能是因为 EAGLE-3 在非 greedy 场景下的优势不如 greedy 场景显著。

### 7.11 特征层选择策略缺乏讨论

论文多次提到使用 low/mid/high-level features，但未具体指定选取哪几层（如第 1/16/32 层？第 1/中间/倒数第二层？）。不同目标模型的层数不同，最优的特征层组合可能完全不同。论文没有给出层选择的敏感性分析或选择标准。

### 7.12 复现风险：训练数据配比未公开

论文提到使用 ShareGPT 和 UltraChat-200K 作为训练数据，对 reasoning model 还使用了 OpenThoughts-114k-math，但未说明：(a) training-time test 中原始训练步与模拟步的数据配比；(b) 训练超参的完整列表。代码开源（GitHub: SafeAILab/EAGLE），但训练脚本和数据管道往往是"代码可用"与"可复现"之间的鸿沟。

## 8. 方法细节

### 8.1 算法流程

EAGLE-3 的推理流程与标准 speculative sampling 一致，交替执行 drafting 和 verification 两个阶段。区别在于 drafting 阶段的实现：

**推理流程**（§3.1）：

1. **特征提取**：目标模型执行 forward pass 后，记录 low-level ($l$)、middle-level ($m$)、high-level ($h$) 三层特征序列。
2. **特征融合**：将 $l, m, h$ 三个 $k$-dim 向量 concatenate 成 $3k$-dim，通过 FC 层降回 $k$-dim，得到融合特征 $g$：
$$g = \text{FC}(\text{concat}(l, m, h)) \in \mathbb{R}^k$$
3. **Draft model 输入**：将 $g$ 与采样 token 的 embedding $e$ concatenate 后经 FC 层降维，送入单层 Transformer decoder：
$$a = \text{DecoderLayer}(\text{FC}(\text{concat}(g, e)))$$
4. **生成 draft token**：将 draft model 输出 $a$ 送入目标模型的 LM head，采样得到 draft token。
5. **后续步骤**：对于 Step 2+，由于新 token 尚未被目标模型验证，无法获取对应的 $g$，因此用上一步的输出 $a$ 替代。

**训练流程**（§3.2）：

Training-time test 的核心是在训练时模拟推理时的多步生成：

- **Step 1**（Native training step）：使用目标模型的真实特征 $g$ 作为输入，标准下三角 attention mask。输出 "are", "we", "do"。
- **Step 2**（Simulated step 1）：将 Step 1 的输出反馈给 draft model 作为输入。此时 attention mask 需要修改——draft 输出之间是 tree-like 的上下文关系，只有当 key 来自原始训练数据时才使用完整的 attention，否则使用对角 attention。
- **Step 3**（Simulated step 2）：将 Step 2 的输出再次反馈，类似地调整 mask。

关键实现优化：当原始训练数据作为 key 时，所有其他位置的 attention score 只有对角线上非零，可以用向量点积替代矩阵乘法以避免计算浪费。

![图解：EAGLE-3 推理流程的三步 draft 过程。左图（Step 1）：从目标模型获取 $l, m, h$ 特征融合为 $g$，加上 embedding $e$ 送入 draft model。中图（Step 2）：用上一步输出 $a$ 替代无法获取的 $g$，继续生成。右图（Step 3）：同理。$g$ 来自目标模型（蓝色），$a$ 来自 draft model（黄色）。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/method.pdf)

![图解：EAGLE、去除 feature constraint、EAGLE-3 三种方法的对比。上部（EAGLE）：draft model 预测 feature $f$，受限于 feature prediction loss。中部：去除 constraint 后，draft model 输出 unconstrained vector $a$，$\hat{a}$ 与 ground-truth $f$ 偏差大。底部（EAGLE-3）：去除 constraint + training-time test，解决分布偏移。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/nofe.pdf)

![图解：Training-time test 的 attention mask 变化。三个子图分别展示 native training step（标准下三角 mask）、simulated step 1（tree-like mask）、simulated step 2（进一步嵌套的 tree-like 结构）。灰色 token 是训练数据，蓝色是第一轮预测，黄色是第二轮预测。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/train.pdf)

### 8.2 关键公式

**Speculative sampling 的接受概率**（§2.1）：对于 draft token $\hat{t}_{j+i}$，接受概率为：
$$\min\left(1, \frac{p_{j+i}(\hat{t}_{j+i})}{\hat{p}_{j+i}(\hat{t}_{j+i})}\right)$$

**特征融合**（§3.1）：
$$g = \text{FC}(\text{concat}(l, m, h))$$
其中 $l, m, h \in \mathbb{R}^k$，$g \in \mathbb{R}^k$，FC 层将 $3k$ 维映射到 $k$ 维。

**Draft model 输入**（§3.1）：
$$\text{input} = \text{FC}(\text{concat}(g \text{ or } a, e))$$
其中 $e$ 是采样 token 的 embedding，$a$ 是 draft model 上一步的输出。

### 8.3 模型与数据流

- **目标模型**：Vicuna 13B、LLaMA-Instruct 3.1 8B、LLaMA-Instruct 3.3 70B、DeepSeek-R1-Distill-LLaMA 8B
- **Draft model**：单层 Transformer decoder layer，参数量远小于目标模型
- **输入**：$g$（目标模型的多层融合特征）或 $a$（draft model 自身输出）+ $e$（token embedding）
- **输出**：$a$（unconstrained vector），送入目标模型 LM head 得到 token 分布
- **与 EAGLE-2 的兼容性**：EAGLE-3 完全兼容 EAGLE-2 的 context-aware dynamic draft tree（§1: "parallelized and fully compatible with the drafting tree technique from EAGLE-2"）

### 8.4 算力资源需求

论文未明确报告训练算力。根据已有信息估算：

- **训练数据**：ShareGPT（~68K 条）+ UltraChat-200K（~464K 条），总计约 532K 条对话数据，约为 EAGLE 的 8x
- **推理生成**：使用目标模型生成回复而非固定数据集，意味着需要额外的目标模型推理成本
- **Training-time test 开销**：每次训练需要模拟 2-3 步推理，attention mask 的修改增加了计算量，但论文提到可以用向量点积优化
- **Optimizer**：AdamW, $(\beta_1, \beta_2) = (0.9, 0.95)$, gradient clipping = 0.5, lr = 5e-5
- **GPU**：论文未说明训练所用 GPU 数量和时长（估算：单卡 A100 训练 8B 目标模型的 draft model 可能在数小时到数天量级，但缺少确切数据）

## 9. 实验

### 9.1 评测数据集

| 数据集 | 任务类型 | 规模 | 说明 |
|--------|----------|------|------|
| MT-bench | 多轮对话 | 80 个问题 | 主要评测数据集，LLM-as-judge 评估 |
| HumanEval | 代码生成 | 164 个问题 | 函数级代码生成，模板化程度高 |
| GSM8K | 数学推理 | 1319 个问题 | 小学数学应用题 |
| Alpaca | 指令遵循 | 805 个问题 | 多样化指令跟随 |
| CNN/Daily Mail | 摘要生成 | ~11K 条 | 新闻摘要 |

所有任务使用相同权重，不做任务特定微调。

### 9.2 评测指标

- **Speedup Ratio**：相对于 vanilla autoregressive decoding 的实际加速比。baseline 为 1.00x。
- **Average Acceptance Length $\tau$**：每个 drafting-verification 循环中平均生成的 token 数，即被接受的 draft token 数量。$\tau$ 越大说明 draft model 的预测越准确。
- **Acceptance Rate $n$-$\alpha$**：当输入包含 $n$ 个估计特征（而非目标模型的真实特征）时的 acceptance rate，反映 draft model 在误差累积下的鲁棒性。

### 9.3 主实验结果

![图解：不同方法在 temperature=0 下的 speedup 对比。EAGLE-3（深蓝色）在所有模型和任务上一致领先。DeepSeek-R1-Distill-LLaMA 8B 在 GSM8K 上表现突出（reasoning model 在数学推理上重复模式多，acceptance rate 天然偏高）。EAGLE-3 因去除 feature prediction 显著优于 HASS。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/r1.pdf)

**主实验关键数据（temperature=0）**：

| 模型 | 方法 | MT-bench | HumanEval | GSM8K | Alpaca | CNN/DM | Mean |
|------|------|----------|-----------|-------|--------|--------|------|
| Vicuna 13B | SpS | 1.93x | 2.23x | 1.77x | 1.76x | 1.93x | 1.92x |
| Vicuna 13B | EAGLE | 3.07x | 3.58x | 3.08x | 3.03x | 2.49x | 3.05x |
| Vicuna 13B | EAGLE-2 | 4.26x | 4.96x | 4.22x | 4.25x | 3.40x | 4.22x |
| Vicuna 13B | **EAGLE-3** | **5.58x** | **6.47x** | **5.32x** | **5.16x** | **5.01x** | **5.51x** |
| L31 8B | EAGLE-2 | 3.16x | 3.66x | 3.39x | 3.28x | 2.65x | 3.23x |
| L31 8B | **EAGLE-3** | **4.40x** | **4.85x** | **4.48x** | **4.82x** | **3.65x** | **4.44x** |
| L33 70B | EAGLE-2 | 2.83x | 3.12x | 2.83x | 3.03x | 2.44x | 2.85x |
| L33 70B | **EAGLE-3** | **4.11x** | **4.79x** | **4.34x** | **4.30x** | **3.27x** | **4.12x** |
| DSL 8B | EAGLE-2 | 2.92x | 3.42x | 3.40x | 3.01x | 3.53x | 3.26x |
| DSL 8B | **EAGLE-3** | **4.05x** | **4.59x** | **5.01x** | **3.65x** | **3.52x** | **4.16x** |

EAGLE-3 在所有模型×任务组合上均优于 EAGLE-2，平均提升约 28%–43%。

**Acceptance rate 逐位置对比**：

![图解：EAGLE vs EAGLE-3 在 MT-bench 上（LLaMA-Instruct 3.1 8B）的 acceptance rate 随估计特征数量 $n$ 的变化。EAGLE 的 acceptance rate 随 $n$ 增加急剧下降（误差累积效应），而 EAGLE-3 几乎保持不变——直接证明 training-time test 在缓解误差累积方面的有效性。](sources/2503.01840-eagle-3-scaling-up/arxiv/figs/alpha.pdf)

### 9.4 消融实验

**消融实验结果**（LLaMA-Instruct 3.1 8B, temperature=0）：

| 方法 | MT-bench Speedup | MT-bench $\tau$ | GSM8K Speedup | GSM8K $\tau$ |
|------|------------------|-----------------|---------------|-------------|
| EAGLE-2 (baseline) | 3.16x | 4.05 | 3.39x | 4.24 |
| + Remove fea con | 3.82x | 5.37 | 3.77x | 5.22 |
| + Fused features (EAGLE-3) | **4.40x** | **6.13** | **4.48x** | **6.23** |

消融实验证明两个改进各自都有显著贡献：
- **去除 feature constraint**：MT-bench 上 speedup 从 3.16x → 3.82x（+21%），$\tau$ 从 4.05 → 5.37（+33%）
- **多层特征融合**：进一步从 3.82x → 4.40x（+15%），$\tau$ 从 5.37 → 6.13（+14%）

（agent 评论）两个改进的叠加效果（+39% speedup）大于各自单独效果之和（21% + 15%），暗示两者之间存在协同效应——去除 feature constraint 释放了输入空间的自由度，使得多层特征融合能够充分发挥作用。

### 9.5 结果分析

**作者的分析**：
- 不同任务影响 draft model 的 acceptance rate，因此加速比是任务相关的。HumanEval 因代码模板化程度高而最容易生成 draft，EAGLE-3 在此达到最高 6.5x 加速。
- DeepSeek-R1-Distill-LLaMA 8B 在 GSM8K 上表现最好，可能是因为使用了 OpenThoughts-114k-math 数据集训练 draft model。
- EAGLE-3 在大 batch size 下仍能提升 throughput（SGLang batch=64 时 1.38x），而 EAGLE 在 batch=24 时 throughput 已开始下降。

**SGLang 框架下的 throughput 测试**：

| Batch size | 2 | 4 | 8 | 16 | 24 | 32 | 48 | 56 | 64 |
|------------|---|---|---|----|----|----|----|----|----|
| EAGLE | 1.40x | 1.38x | 1.23x | 1.02x | 0.93x | 0.94x | 0.88x | 0.99x | 0.99x |
| EAGLE-3 | 1.81x | 1.82x | 1.62x | 1.48x | 1.39x | 1.32x | 1.38x | 1.34x | 1.38x |

**SGLang 单请求延迟**（H100, batch=1）：

| 方法 | Throughput |
|------|-----------|
| SGLang (w/o speculative) | 158.34 tokens/s |
| SGLang + EAGLE-2 | 244.10 tokens/s |
| SGLang + EAGLE-3 | 373.25 tokens/s |

EAGLE-3 在 batch=1 时的 throughput 是 baseline 的 2.36x，是 EAGLE-2 的 1.53x。

**vLLM 框架下的 throughput 测试**（A100）：

| Batch size | 2 | 4 | 8 | 16 | 24 | 32 | 48 | 56 |
|------------|---|---|---|----|----|----|----|----|
| EAGLE | 1.30x | 1.25x | 1.21x | 1.10x | 1.03x | 0.93x | 0.82x | 0.71x |
| EAGLE-3 | 1.75x | 1.68x | 1.58x | 1.49x | 1.42x | 1.36x | 1.21x | 1.01x |

（agent 评论）EAGLE-3 在两个主流框架（SGLang 和 vLLM）上的表现一致优于 EAGLE，且在更大 batch size 下仍保持正向 throughput 提升。但需注意：(a) SGLang 实验由 SGLang 团队执行，baseline 是 "SGLang without speculative sampling"，throughput 提升可能部分来自框架对 speculative decoding 的工程优化（如 KV cache 管理）而非纯粹的 draft 质量提升；(b) vLLM 实验在 A100 上进行（而非 H100），且 chain length 设为 2（而非 SGLang 的 3），使得两组实验不完全可比；(c) vLLM 在 batch=56 时 EAGLE-3 的 throughput 已降至 1.01x，接近无增益。
