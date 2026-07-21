---

## EAGLE-3 阅读札记 / Evidence Map

### 一、问题动机

**核心问题**：EAGLE 系列的 feature prediction 约束导致 scaling 训练数据收益有限。

- EAGLE 在 feature level 做 autoregression，用目标模型 top-layer features 作为 draft model 输入，同时训练目标包含 feature prediction loss $l_{\text{fea}}$ 和 token prediction loss $l_{\text{token}}$。（Section 1，Introduction）
- 作者发现：扩大训练数据后，EAGLE 的加速比提升有限。（Abstract + Introduction）
- 原因分析：feature prediction 是一个**额外约束**（additional constraint），限制了 draft model 的表达能力，使其难以从更多数据中受益。（Section 1，"We identify that this limitation arises from EAGLE's feature prediction constraints"）
- 论文还观察到另一个问题：去除 feature constraint 后，第一步 draft 的 acceptance rate（0-α）确实提升了，但第二步（1-α）仍然很低，因为 Step 1 的输出 $\hat{a}_{t+1}$ 与 ground-truth $f_{t+1}$ 偏差大，导致 Step 2 输入偏离训练分布。（Section 1，Figure fig:sc1 佐证）

**动机的关键推理链**：
1. Scaling data 对 EAGLE 收益有限 → 2. 归因于 feature prediction constraint → 3. 去掉 constraint 后第一步改善但第二步退化 → 4. 需要在训练时模拟多步推理（training-time test）来解决分布偏移

### 二、核心方法

EAGLE-3 有两个核心改进，加上一个技术手段：

**改进 1：去除 feature prediction constraint，改为直接 token prediction**
- EAGLE 的 loss: $l_{\text{fea}} + l_{\text{token}}$
- EAGLE-3 只保留 $l_{\text{token}}$，draft model 输出不再需要拟合目标模型的 top-layer features
- 这给了 draft model 完全自由的输入空间（"complete flexibility in the draft model's input"）（Section 1, Contribution 1）

**改进 2：multi-layer feature fusion 替代 top-layer features**
- EAGLE/EAGLE-2 只用 top-layer features（LM head 之前的 features）
- EAGLE-3 融合 low-level ($l$)、middle-level ($m$)、high-level ($h$) 三层 features
- 融合方式：将 $l, m, h$ 三个 $k$-dim 向量 concatenate 成 $3k$-dim，通过 FC layer 降回 $k$-dim，得到 $g$（Section 3.1, Inference Pipeline）
- 动机：top-layer features 天然对应 next token 的 logits，用它预测 next-next token 很困难；低层 features 包含更丰富的语义信息（Section 1）

**技术手段：Training-Time Test**
- 核心思想：在训练阶段模拟推理时的多步生成过程
- Step 1：正常训练，用 target model 的 $g$ 特征作为输入
- Step 2：把 Step 1 的输出 $a$（draft model 的输出）反馈给 draft model 作为输入，继续训练
- Step 3：类似地，用 Step 2 的输出再反馈
- 关键实现细节：attention mask 需要修改。原始训练数据用标准下三角 mask；反馈回来的 draft 输出之间的 attention 关系是 tree-like 的（Section 3.2, Figure fig:mask）
- 论文明确说："Although the actual input consists of features, for clarity, we describe the process using tokens as input"（Section 3.2）

**与 HASS 的区别**（Section 3.2 末尾）：
- HASS 也做了类似的 attention 修改来模拟测试，但目的不同：HASS 是为了缓解 EAGLE feature prediction 的 error accumulation
- HASS 仍然保留 feature prediction loss $l_{\text{fea}}$，输入必须是 top-layer features
- EAGLE-3 彻底去除 feature prediction，输入完全自由，用多层 feature fusion

**推理流程**（Section 3.1, Figure fig:pipline）：
1. Prefill/上一轮验证：target model forward pass，记录 $l, m, h$，融合得到 $g$
2. Draft model 输入：$g$（target model 的融合特征）+ embedding $e$（采样 token 的 embedding），经 FC 降维后送入单层 Transformer decoder
3. Draft model 输出 $a$，送入 target model 的 LM head 得到 draft token
4. 后续步骤：用上一步的 $a$ 替代无法获取的 $g$（因为 token 尚未被 target model 验证）

### 三、图表含义

**Figure fig:pipline**（figs/method.pdf）— 方法架构图
- 展示 EAGLE-3 推理流程的三步。$l, m, h$ 分别代表 low/middle/high-level features，$e$ 代表 embedding
- **应放在报告的「方法细节」章节**

**Figure fig:nofe**（figs/nofe.pdf）— Training-time test 示意图
- 对比三种方法：上部=EAGLE（feature prediction）、中部=去除 feature constraint 但无 training-time test、底部=EAGLE-3（去除 constraint + training-time test）
- $f$ = feature, $t$ = token, $a$ = unconstrained vectors, hat 表示模型预测
- **应放在报告的「方法细节」或「核心贡献概述」章节**

**Figure fig:mask**（figs/train.pdf）— Attention mask 示意图
- 展示 training-time test 过程中的 causal attention mask 变化
- 三个子图：native training step（第一步）、两个 simulated training steps（第二、三步）
- 灰色 token = 训练数据，蓝色 = 第一轮预测，黄色 = 第二轮预测
- 箭头表示 token 间的上下文关系
- **应放在报告的「方法细节」章节**

**Figure fig:sc**（figs/scaale.pdf + figs/scaletau.pdf）— Scaling law 曲线
- x 轴：相对于 ShareGPT 的数据规模倍数
- 上图：speedup ratio；下图：average acceptance length
- 目标模型：LLaMA-Instruct 3.1 8B，评测：MT-bench
- **关键发现**：EAGLE-3 展示了随数据增加 speedup 持续上升的 scaling curve，这在 EAGLE 中从未观察到
- **应放在报告的「核心贡献概述」和「实验」章节**

**Figure fig:sc1**（figs/alpha0.pdf + figs/alpha1.pdf）— Acceptance rate 对比
- 上图：0-α（第一个 draft token 的 acceptance rate）随数据规模变化
- 下图：1-α（第二个 draft token 的 acceptance rate）随数据规模变化
- **关键证据**：去除 feature constraint 后 0-α 显著提升，但 1-α 仍然很低 → 需要 training-time test
- **应放在报告的「核心贡献概述」或「方法细节」章节**

**Figure fig:speedup**（figs/r1.pdf）— 不同方法的 speedup 对比（temperature=0）
- 包含 chat model（MT-bench）和 reasoning model（GSM8K）两个场景
- 标注了 standard speculative sampling（Vicuna-13B + Vicuna-68M）作为 baseline
- **应放在报告的「实验」章节**

**Figure fig:alpha**（figs/alpha.pdf）— EAGLE vs EAGLE-3 的 acceptance rate 逐位置对比
- 目标模型：LLaMA-Instruct 3.1 8B，数据集：MT-bench
- $n$-$\alpha$ 表示在前 $n$ 个 estimated features 都被接受条件下的 acceptance rate
- **应放在报告的「实验」章节**

**Table tab:experiments** — 主实验结果表
- Speedup ratios 和 average acceptance lengths $\tau$
- 模型：Vicuna 13B, LLaMA-Instruct 3.1 8B, LLaMA-Instruct 3.3 70B, DeepSeek-R1-Distill-LLaMA 8B
- 任务：MT-bench, HumanEval, GSM8K, Alpaca, CNN/DM
- 方法：SpS, PLD, Medusa, Lookahead, Hydra, EAGLE, EAGLE-2, EAGLE-3
- 温度：0 和 1 两组
- 注：Medusa 在非 greedy 下放松了接受条件，不保证 lossless，因此 temperature=1 时不比较
- **应放在报告的「实验」章节**

**Table tab:aba** — 消融实验
- 目标模型：LLaMA-Instruct 3.1 8B
- "Remove fea con" = 第一个改进（去除 feature prediction constraint）
- "Fused features" = 第二个改进（多层 feature fusion）
- **应放在报告的「实验」章节**

**Table tab:sglang** — SGLang 框架下的 throughput 改善
- 不同 batch size（1 到 64）下的 throughput improvement
- 硬件：H100，目标模型：LLaMA-Instruct 3.1 8B，数据集：MT-Bench
- Baseline：SGLang without speculative sampling = 1.00x
- **关键数字**：batch size 64 时 throughput 提升 1.38x（与 abstract 对应）
- 由 SGLang 团队执行的实验
- **应放在报告的「实验」章节**

**Table tab:sglang latency** — SGLang 单请求延迟
- batch size = 1，H100，LLaMA-Instruct 3.1 8B，MT-bench
- **应放在报告的「实验」章节**

**Table tab:vllm** — vLLM 框架下的 throughput 改善
- 不同 batch size，A100，LLaMA-Instruct 3.1 8B，MT-Bench
- Baseline：vLLM without speculative sampling = 1.00x
- **应放在报告的「实验」章节**

### 四、实验设计

**目标模型**（Section 4）：
- Vicuna 13B
- LLaMA-Instruct 3.1 8B
- LLaMA-Instruct 3.3 70B
- DeepSeek-R1-Distill-LLaMA 8B（reasoning model）
- 注：由于 GPU 限制，无法测试 405B 和 671B 模型

**评测任务**（5 个，Section 4）：
- MT-bench：多轮对话（multi-turn conversation）
- HumanEval：代码生成（code generation）
- GSM8K：数学推理（mathematical reasoning）
- Alpaca：指令遵循（instruction following）
- CNN/Daily Mail：摘要（summarization）
- 所有任务使用相同权重，不做任务特定微调

**Baseline 方法**：
- Standard speculative sampling (SpS)：draft model = Vicuna-68M
- PLD (Parallel Decoding)
- Medusa
- Lookahead
- Hydra
- EAGLE
- EAGLE-2
- HASS（在 Figure fig:speedup 中出现）

**评测指标**：
- Speedup ratio（相对于 autoregressive decoding 的加速比）
- Average acceptance length $\tau$（平均接受长度）

**温度设置**：temperature=0（greedy）和 temperature=1 两组

### 五、主要结果

从 tex 源码中可以提取的关键数字（部分表格被截断，以下为可见部分）：

- **EAGLE-3 最高加速比**：6.5x（Abstract）
- **相对 EAGLE-2 的提升**：约 1.4x（Abstract，"about 1.4x improvement over EAGLE-2"）
- **SGLang throughput**：batch size 64 时提升 1.38x（Abstract + Table tab:sglang）
- **Vicuna 13B baseline 数据**（Table tab:experiments, temperature=0）：
  - SpS: MT-bench 1.93x, HumanEval 2.23x, GSM8K 1.77x, Alpaca 1.76x, CNN/DM 1.93x, Mean 1.92x
  - EAGLE: MT-bench 3.07x, HumanEval 3.58x, GSM8K 3.08x, Alpaca 3.03x, CNN/DM 2.49x, Mean 3.05x
  - EAGLE-2: MT-bench 4.26x, HumanEval 4.96x, GSM8K 4.22x（后续数据被截断）
  - EAGLE-3 的数据在截断部分，但从趋势看应显著高于 EAGLE-2
- **Scaling law 发现**：随训练数据增加，EAGLE-3 的 speedup ratio 持续上升（Figure fig:sc），这在 EAGLE 中不存在

### 六、相关工作关系

**直接前作**：
- **EAGLE** (Li et al., 2024, ICML)：提出 feature-level autoregression + top-layer feature reuse，是 EAGLE-3 的直接前身
- **EAGLE-2** (Li et al., 2024)：引入 context-aware dynamic draft tree，EAGLE-3 继承了这一技术

**同族方法**：
- **Medusa** (Cai et al., 2024)：加多个 decoding heads 并行预测，不保证 lossless（non-greedy 下放松接受条件）
- **HASS** (Zhang et al., 2024)：类似的 training-time attention 修改，但保留 feature prediction，动机和结果不同
- **Hydra** (Ankner et al., 2024)：sequential-dependent draft heads for Medusa
- **Falcon** (Gao et al., 2024)：也采用 feature-level prediction

**Speculative decoding 基础**：
- **Leviathan et al., 2023**：Fast inference from transformers via speculative decoding（理论基础）
- **Chen et al., 2023**：Accelerating LLM decoding with speculative sampling（DeepMind 版本）
- **Sequoia** (Chen et al., 2024)：scalable + hardware-aware speculative decoding

**启发来源**（有趣的一点）：
- EAGLE 启发了 DeepSeek-V3 的 multi-token prediction 技术，而 DeepSeek-V3 又反过来启发了 EAGLE-3 的新架构设计（Section 2.2："EAGLE inspired the multi-token prediction technique used in the pre-training of DeepSeek-v3, which in turn inspired new architectural designs in EAGLE-3"）

**推理模型动机**：
- ChatGPT o1、DeepSeek-R1 等 reasoning models 推动了对推理加速的需求（Section 1: "these models often require lengthy reasoning processes, making them extremely costly"）

### 七、可能局限

**论文自述的局限**：
- GPU 限制无法测试 405B 和 671B 模型（Section 4: "Due to the GPU constraint, we are unable to test EAGLE-3 on the 405B and 671B models"）

**推断的局限**：
1. **Draft model 仍需训练**：EAGLE-3 需要为目标模型专门训练 draft model，且训练数据量约为 EAGLE 的 8x，训练成本不低
2. **单层 decoder**：draft model 核心只有一层 Transformer decoder layer，表达能力上限可能受限于这一设计选择
3. **Feature fusion 的层选择**：论文说用 low/middle/high 三层 fusion，但没有讨论如何选择具体哪几层、不同选择的影响
4. **吞吐量与延迟的权衡**：Speculative decoding 通常在低 batch size 下延迟改善明显，但高 batch size 下 throughput 改善有限（论文在 batch size 64 下仅 1.38x，相对 batch size 1 的 latency improvement 小很多）
5. **仅在 temperature=0 和 1 下测试**：没有讨论中间温度或 top-k/top-p 采样的影响
6. **与 Medusa 的比较不完整**：temperature=1 时因为 Medusa 不保证 lossless 而不比较，但实际使用中很多人会用 temperature>0

### 八、算力与实现线索

**训练规模**：
- EAGLE-3 训练数据约为 EAGLE 的 8x（Section 1: "trained with approximately 8x more data than EAGLE"）
- 具体 GPU 数量和训练时长论文未明确给出

**Draft model 架构**：
- 核心：单层 Transformer decoder layer（Section 3.2: "The core of the draft model in EAGLE-3 is a Transformer decoder layer"）
- 输入处理：$l, m, h$ 三个 $k$-dim 向量 concatenate → FC layer → $k$-dim → 加上 embedding → FC layer → $k$-dim → decoder layer
- 输出：送入 target model 的 LM head

**推理框架集成**：
- SGLang 框架：H100 上测试，batch size 1-64（Table tab:sglang, tab:sglang latency）
- vLLM 框架：A100 上测试（Table tab:vllm）
- 与 EAGLE-2 的 drafting tree 技术完全兼容（Section 1: "parallelized and fully compatible with the drafting tree technique from EAGLE-2"）

**代码**：https://github.com/SafeAILab/EAGLE

**实现注意点**：
- Training-time test 的 attention mask 需要特殊处理：原始训练数据用标准下三角 mask，draft 输出之间的关系是 tree-like 的，需要调整 mask
- 论文提到可以用 vector dot products 替代 matrix multiplication 来避免计算浪费（Section 3.2: "we can use vector dot products to calculate the attention score only for the corresponding positions"）

### 九、关键引用线索（用于报告的「核心参考文献」章节）

| 引用 | 角色 |
|------|------|
| Leviathan et al., 2023 / Chen et al., 2023 | Speculative decoding 理论基础 |
| Li et al., 2024 (EAGLE) | 直接前作，feature-level autoregression |
| Li et al., 2024 (EAGLE-2) | Context-aware dynamic draft tree，EAGLE-3 继承 |
| Cai et al., 2024 (Medusa) | 同族方法，multi-head parallel prediction |
| DeepSeek-V3 | 启发了 EAGLE-3 的架构设计（双向启发关系） |
| Zhang et al., 2024 (HASS) | 类似 training-time attention 修改但动机不同 |
| Touvron et al., 2023 (LLaMA) | 目标模型系列 |
| DeepSeek-R1 | Reasoning model 代表，推动推理加速需求 |
| Zheng et al., 2023 (MT-bench) | 主要评测数据集 |
| Zheng et al., 2024 (SGLang) | 生产级推理框架集成 |

---
