---
slug: noarxiv-2026-dspark
title: "DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation"
title_zh: "DSpark：基于置信度调度的半自回归 speculative decoding"
title_en: "DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation"
arxiv_id: "noarxiv-2026-dspark"
year: 2026
authors:
  - Xin Cheng
  - Xingkai Yu
  - Chenze Shao
  - Jiashi Li
  - Yunfan Xiong
  - DeepSeek-AI and Peking University team
topics:
  - LLM Inference
  - Speculative Decoding
  - Serving Systems
  - Semi-Autoregressive Generation
domains:
  - LLM Systems
tracks:
  - Inference Acceleration
  - Parallel Decoding
problems:
  - Lossless Speculative Decoding
  - Load-Aware Serving
methods:
  - speculative decoding
  - semi-autoregressive generation
  - confidence-scheduled verification
  - hardware-aware scheduling
  - Markov head
research_line: LLM Serving
line_role: system
status: read
reading_stage: code_checked
importance: 4
confidence: 4
reproducibility: 3
has_code: true
---

# DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation

## 1. 基本情况

- 英文题目：DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation
- 中文题目：DSpark：基于置信度调度的半自回归 speculative decoding
- 作者：Xin Cheng, Xingkai Yu, Chenze Shao, Jiashi Li, Yunfan Xiong, Yi Qian, Jiaqi Zhu, Shirong Ma, Xiaokang Zhang, Jiasheng Ye, Qinyu Chen, Chengqi Deng, Jiping Yu, Damai Dai, Zhengyan Zhang, Yixuan Wei, Yixuan Tan, Wenkai Yang, Runxin Xu, Yu Wu, Zhean Xu, Xuanyu Wang, Muyang Chen, Rui Tian, Xiao Bi, Zhewen Hao, Shaoyuan Chen, Huanqi Cao, Wentao Zhang, Anyi Xu, Huishuai Zhang, Dongyan Zhao, Wenfeng Liang
- 单位：Peking University; DeepSeek-AI
- arXiv 编号：无。本文目前以 DeepSeek-AI/DeepSpec 仓库中的 PDF 形式公开，不应与 DeepSeek-V4 技术报告 arXiv:2606.19348 混填。
- 公开年份：2026；PDF 未在首页标出更细提交日期。
- 论文链接：https://github.com/deepseek-ai/DeepSpec/blob/main/DSpark_paper.pdf
- 代码仓库：https://github.com/deepseek-ai/DeepSpec
- 本地材料：`sources/noarxiv-2026-dspark/arxiv/DSpark_paper.pdf`，抽取文本为 `sources/noarxiv-2026-dspark/arxiv/DSpark_paper.txt`，代码为 `sources/noarxiv-2026-dspark/code/`。

## 2. 核心贡献概述

中文概述：DSpark 面向大模型线上 serving 中的 speculative decoding，把“draft token 怎么生成得更稳”和“target model 该验证多少 token 才划算”两个问题放在同一个框架里解决。它用 DFlash 风格的并行 backbone 负责一次性生成长 draft，再用轻量 Markov/RNN sequential head 引入块内依赖，并用 calibrated confidence head 与 hardware-aware scheduler 按请求、按负载动态裁剪验证长度。

英文原文概述（Abstract）：本文写道，"We introduce DSpark, a speculative decoding framework that unifies high-throughput parallel generation with adaptive, load-aware verification." 它还强调 DSpark "utilizes a semi-autoregressive architecture" 并 "employs confidence-scheduled verification"，对应算法和系统两个贡献。

## 3. 一句话精髓（写给外行）

DSpark 像是在一条很忙的高速收费站前安排一位聪明的领队：先让小车队大胆排出候选路线，再只把最可能一路畅通的车放进昂贵主路验证。

## 4. 学术贡献清单

### 动机的发现与阐明

- 论文指出并行 drafter 的主要问题不是第一个 token 不准，而是后缀位置会因为块内 token 独立预测而发生 suffix decay：多种合理续写被混在一起，导致后续 token 虽然各自看似合理，作为一个连续 prefix 却容易被 target 拒绝。
- 论文把 speculative decoding 的低效分成数据侧和系统侧两层：数学/代码这类结构化任务天然 acceptance 更高，开放聊天 acceptance 更低；同时在高并发 serving 中，验证低置信 suffix token 会占用 target batch capacity，直接伤害全局吞吐。
- 这使 DSpark 的目标从“生成更长 draft”转成“高质量生成 + 有负载意识地验证”，比单纯调大 block size 更接近生产系统瓶颈。

### 方法的创新点

- 半自回归生成：用并行 backbone 保持一次 forward 生成整个 block 的速度优势，再追加低成本 sequential head，对块内已采样 token 建模局部 transition bias。
- Markov head：默认实现用低秩 $V \times V$ transition bias $B=W_1W_2$，rank 默认 256，让当前位置 logits 能被前一个采样 token 修正。
- Confidence head：预测每个 draft 位置在前缀已接受条件下继续被接受的概率，并用 target/draft 分布的 total variation 形成 soft label。
- Sequential Temperature Scaling：对累积 prefix survival probability 做逐位置校准，避免 confidence score 只会排序但绝对概率失真。
- Hardware-aware prefix scheduler：把验证长度选择写成 $\Theta=\tau \cdot SPS(B)$ 的系统吞吐最大化问题，使用硬件 profiled step curve 来决定每个 request 保留多长 prefix。

### 实验上得到的核心结论

- 离线 accepted length 上，DSpark 在 Qwen3-4B/8B/14B 相比 Eagle3 macro 平均提升 30.9%/26.7%/30.0%，相比 DFlash 提升 16.3%/18.4%/18.3%。
- 位置级分析显示，DFlash 在第一个位置很强但后缀衰减明显；Eagle3 后缀更稳但第一个位置容量不足；DSpark 试图同时拿到前者的首 token 能力和后者的块内连贯性。
- DeepSeek-V4 线上 serving 中，DSpark 相比 MTP-1 在 matched throughput 下让 V4-Flash 用户侧生成速度提升 60%-85%，V4-Pro 提升 57%-78%，并把严格 SLA 下原本不可用的吞吐区间推到可用。

## 5. 写作故事线

论文的故事从 speculative decoding 的三项速度杠杆开始：降低 draft 时间 $T_{\text{draft}}$、提高每轮接受长度 $\tau$、减少有效 target 验证时间 $T_{\text{verify}}$。作者先承认传统 autoregressive drafter 的优点是块内依赖强，但代价是 $T_{\text{draft}} \propto \gamma$；再指出并行 drafter 让 $T_{\text{draft}}$ 近似与 block size 无关，却牺牲了后缀连贯性。

接着，论文把问题推进到生产 serving：即使能一次生成长 draft，也不该机械地全量验证，因为 target model 的 batch capacity 在高并发时是最贵资源。于是 DSpark 被自然拆成两部分：第 3.1 节解决 draft 质量，用 semi-autoregressive generation 缓解 suffix decay；第 3.2 节解决验证预算，用 confidence-scheduled verification 按实际负载裁剪 prefix。

第 4 节的离线实验先隔离 scheduler，证明 drafter 本身比 DFlash/Eagle3 更会产出可被接受的 prefix；随后用 position-wise conditional acceptance、depth/proposal length ablation 和 confidence threshold sweep 解释“为什么有效”。第 5 节再把 DSpark 放回 DeepSeek-V4 真实流量，展示 scheduler 如何随并发变化调整 verification budget，从而把单点算法收益变成 serving Pareto frontier 的外移。

## 6. 核心参考文献

- Chen et al., 2023 / Leviathan et al., 2023，speculative decoding：提供 lossless target-distribution-preserving rejection sampling 基础，DSpark 的 scheduler 也必须维护 non-anticipating property。
- DeepSeek-AI, 2024，MTP：作为 DeepSeek 既有生产 baseline，论文用 MTP-1 代表此前线上可稳定部署的单 token speculative setup。
- Chen et al., 2026，DFlash：DSpark 的并行 backbone 直接以 DFlash 为主要实例，继承 KV/hidden-state feature injection 与 parallel block prediction。
- Li et al., 2026b，Eagle3：作为 autoregressive drafter baseline，体现块内依赖强但 draft latency 随 horizon 增长的问题。
- Cai et al., 2024 / Medusa：代表多 token head 与并行 draft 思路，说明 speculative drafter 可以嵌入 target model 附近而不是独立小模型。
- Miao et al., 2024，SpecInfer：代表 tree-based speculative verification 系统，强调验证更多候选路径会换来吞吐压力。
- Kwon et al., 2023，vLLM：代表连续 batching 与 KV cache 资源管理背景，支撑论文关于 per-user latency 与 aggregate throughput 共同优化的 serving 叙事。
- Hu et al., 2026 / Wu et al., 2025 等 system-aware scheduling 工作：与 DSpark 的硬件感知验证预算最接近，区别在于 DSpark 把 calibrated prefix survival 和 production SPS curve 绑定。
- Gu et al., 2018，non-autoregressive generation：提供 multi-modal collision / fertility 类问题的早期背景，DSpark 借这个视角解释并行 drafter 后缀衰减。

## 7. 批判性分析

DSpark 最重要的原创性不在“发现 speculative decoding 可以动态裁剪长度”，也不在“并行 drafter 后面加一点序列依赖”这两个单点。前者在 confidence threshold、adaptive speculation、system-aware goodput 调度里已有不少影子；后者也能在半自回归 NMT、CRF/NAT、DFlash 后续 CausalEncoder 类工作中找到相近直觉。DSpark 的贡献更像一次工程化的统一：把可训练的 confidence、概率校准、硬件 SPS 曲线、lossless causality 约束和 DeepSeek-V4 serving 内核改造接到一起，并用线上真实流量证明它能改变可运营区间。

相对 DFlash，DSpark 是很直接的增量：并行 backbone 仍是 DFlash 式的 block drafter，创新集中在 sequential head 和调度器。论文承认“we make only a minor modification to the original DFlash backbone”，这意味着如果只看离线 accepted length，DSpark 更像 DFlash 的增强版而不是从零开始的新 drafter。但这个增强很关键，因为 DFlash 的错误模式正是 suffix decay；Markov head 用极低开销补上局部条件依赖，性能差距随 proposal length 变大，说明它确实命中 DFlash 的弱点。

相对 Eagle/Eagle3，DSpark 的优势来自计算形态而非纯语言建模能力。Eagle3 逐步 draft，后缀 conditional acceptance 更稳；但为了 latency 只能浅、短。DSpark 先用并行深 backbone 在第一个 token 获得容量优势，再用 Markov head 防止后缀散掉。这不是证明 parallel 一般优于 autoregressive，而是证明在 speculative decoding 的 prefix survival 目标下，第一个 token 的权重太大，深并行模型的首 token 优势能压过后缀不足。

相对 Medusa/SpecInfer/tree speculative decoding，DSpark 明显更关注生产 batch capacity。Tree 方法可能提高候选覆盖率，但验证 token 数和 attention 结构会更重；DSpark 的 scheduler 则主动把低回报 suffix 剪掉。这个取向很“服务系统优先”：它愿意不验证已生成的 draft token，只要这些 token 在当前负载下期望收益低。

论文的主要局限是线上部分不可完全复现。DeepSeek-V4-Flash/Pro、HAI-LLM、ZOS、index-attention/compress kernel 修改、真实流量分布都不是公开环境；开源 DeepSpec 主要覆盖 Qwen3/Gemma 的训练和评测，不能复现第 5 节中最有说服力的 production Pareto frontier。另一个风险是 scheduler 的收益高度依赖 SPS curve、并发分布和 KV-cache 约束；在小 batch、单用户或离线评测环境中，confidence scheduler 的系统收益可能远小于论文线上图。

## 8. 方法细节

![DSpark 架构与解码循环](../sources/noarxiv-2026-dspark/arxiv/figures/page-05.png)

图解：PDF 第 5 页的 Figure 1 展示 DSpark 的一轮 decoding cycle。给定 prompt `ABC`，target 先生成 anchor token `D`，DSpark 用 parallel block 生成 `EFGH` 和 confidence score，再由 hardware-aware prefix scheduler 丢弃低置信的 `H`，只把 `EFG` 交给 target 验证。这个图支撑论文的核心 claim：DSpark 同时优化“draft 怎么来”和“verify 验多少”。

### 8.1 Speculative decoding 目标

标准 speculative decoding 每轮由 draft model 给出 $\gamma$ 个候选 token，target model 一次 forward 验证整段候选，并按 rejection sampling 接受最长 prefix。论文用平均每 token latency 表示核心目标：

$$
L=\frac{T_{\text{draft}}+T_{\text{verify}}}{\tau}
$$

其中 $\tau$ 是每轮接受 token 数。DSpark 分别攻击三个变量：并行 backbone 控制 $T_{\text{draft}}$，semi-autoregressive head 提高 $\tau$，confidence scheduler 降低无效 $T_{\text{verify}}$。

### 8.2 Semi-autoregressive generation

DSpark 的 parallel stage 使用 DFlash 作为实例：target model 的多层 hidden states 被拼接并投影成 context feature，再注入 draft transformer。与 DFlash 原设定不同，DSpark 把 anchor token 本身作为第一个预测位置：输入是 anchor + $\gamma-1$ 个 mask，输出 $\gamma$ 个 draft logits，从而减少一部分 draft 计算。

Sequential stage 在每个位置的 base logits $U_k$ 上加一个依赖前缀的 transition bias：

$$
p_k(v|x_0,x_{<k})=
\frac{\exp(U_k(v)+B_k(x_0,x_{<k},v))}
{\sum_{u\in V}\exp(U_k(u)+B_k(x_0,x_{<k},u))}
$$

默认 Markov head 只依赖前一个 token：

$$
B(x_{k-1},\cdot)=W_1[x_{k-1}]W_2
$$

代码中 `deepspec/modeling/dspark/markov_head.py` 的 `VanillaMarkov` 正是这个低秩矩阵：`markov_w1` 是 vocab 到 rank 的 embedding，`markov_w2` 是 rank 到 vocab 的无 bias linear projection；`sample_block_tokens` 逐位置采样，并把前一步采样 token 作为下一步 bias 输入。`RNNHead` 也存在，但论文和公开配置默认使用 Markov head，因为 RNN head 的增益主要出现在更长 proposal length，部署复杂度更高。

### 8.3 Confidence head 与校准

Confidence head 对每个 draft 位置输出 $c_k\in(0,1)$，它不是无条件“这个 token 对不对”，而是条件概率：在前面 token 已经被 target 接受的前提下，第 $k$ 个 token 继续被接受的概率。公式为：

$$
c_k=\sigma(w^\top[h_k;W_1[x_{k-1}]])
$$

训练标签来自 draft/target 分布的 total variation：

$$
c^*_k=1-\frac{1}{2}\|p^d_k-p^t_k\|_1
$$

因为 scheduler 要用绝对概率计算期望吞吐，排序正确还不够。论文用 Sequential Temperature Scaling 按位置校准累积概率 $\prod_{i\le k}c_i$，使 prefix survival probability 与经验接受率对齐。

### 8.4 Hardware-aware prefix scheduler

对一个 batch 中的 $R$ 个请求，请求 $r$ 在位置 $j$ 的 prefix survival 是：

$$
a_{r,j}=\prod_{i\le j}c_{r,i}
$$

如果每个请求保留长度 $\ell_r$，target 验证 batch size 是：

$$
B=\sum_{r=1}^{R}(1+\ell_r)
$$

期望接受 token 数为：

$$
\tau=\sum_{r=1}^{R}\left(1+\sum_{j=1}^{\ell_r}a_{r,j}\right)
$$

硬件 profile 给出 batch size 为 $B$ 时的 step per second 曲线 $SPS(B)$，scheduler 最大化：

$$
\Theta=\tau\cdot SPS(B)
$$

理论算法沿所有候选 prefix extension 的 $a_{r,j}$ 降序贪心加入 token，并在吞吐不再提升时 early stop。early stop 的作用不仅是省计算，也用于维持 lossless speculative decoding 的 non-anticipating property：不能让是否验证第 $k$ 个 token 依赖未来 token 的 realization。

### 8.5 Training objective 与算力资源需求

训练时 target model 冻结，draft model 共享并冻结 target embedding 与 LM head，只更新 backbone drafter、sequential head 和 confidence head。总体 loss 是：

$$
L=\alpha_{\text{ce}}L_{\text{ce}}+\alpha_{\text{tv}}L_{\text{tv}}+\alpha_{\text{conf}}L_{\text{conf}}
$$

其中默认 $\alpha_{\text{ce}}=0.1,\alpha_{\text{tv}}=0.9,\alpha_{\text{conf}}=1.0$。位置权重使用指数衰减，强调更早位置，因为 prefix verification 中前面 token 的拒绝会使后面 token 全部失效。

公开 DeepSpec 代码的默认 Qwen3-4B 配置为：`block_size=7`，`num_draft_layers=5`，`target_layer_ids=[1,9,17,25,33]`，`num_anchors=512`，`markov_rank=256`，`global_batch_size=512`，`local_batch_size=1`，训练 10 epochs，bf16，`torch_compile=True`。README 明确默认脚本假设单机 8 GPU；数据准备阶段为 Qwen3-4B 的 target cache 可能达到约 38 TB。论文线上 DeepSeek-V4 版本则使用 3 个 MoE draft layers、mHC、sliding window attention 128、最大 block size $\gamma=5$，并依赖内部 HAI-LLM、ZOS 和 kernel 修改。

算力需求估算：公开 Qwen3/Gemma 复现实验至少需要一台 8 GPU 机器和数十 TB target-cache 存储，若按默认 local batch size 1 与 global batch size 512，需要跨 GPU/梯度累积支撑 512 全局 batch。线上 DeepSeek-V4 部署的真实训练与 serving 算力远超公开配置，论文未披露 GPU 型号、训练时长或总 token 数；只能确认它面向生产级高并发 serving，并修改了 index-attention 与 compress kernels。

## 9. 实验

### 9.1 评测数据集

论文用 Open-PerfectBlend 的 130 万 prompt 训练 drafter，响应由各 target model 重新生成，非 thinking mode。离线评测覆盖三类任务：

- 数学推理：GSM8K、MATH500、AIME25。
- 代码生成：MBPP、HumanEval、LiveCodeBench。
- 日常聊天：MT-Bench、Alpaca、Arena-Hard v2。

target model 包括 Qwen3-4B、Qwen3-8B、Qwen3-14B、Gemma4-12B。baseline 包括 parallel drafter DFlash 和 autoregressive drafter Eagle3。为了公平，作者在同一训练框架和同一数据上重训所有 drafters，并把 Eagle3 的 horizon 与 DSpark/DFlash 的 block size 对齐为 7。

### 9.2 评测指标

- accepted length $\tau$：每轮 speculative decoding 接受的 token 数，包含 target 生成的 bonus token。它直接决定 $L=(T_{\text{draft}}+T_{\text{verify}})/\tau$ 中的分母。
- conditional acceptance by position：只在前面位置已被接受的条件下，统计第 $k$ 位继续被接受的概率，用来剥离前缀失败对后缀位置的污染。
- acceptance rate under threshold：随着 confidence threshold 增大，观察验证 token 数和被接受比例变化，用来验证 confidence head 是否能识别低价值 suffix。
- ECE/AUC：用于 confidence calibration，AUC 看排序能力，ECE 看概率校准。
- production throughput 与 tok/s/user：线上同时看 aggregate output token throughput 和每用户生成速度，衡量 serving Pareto frontier。

### 9.3 主实验结果

![主结果表](../sources/noarxiv-2026-dspark/arxiv/figures/page-11.png)

图解：PDF 第 11 页 Table 1 汇总 accepted length。DSpark 在 Qwen3-4B/8B/14B/Gemma4-12B 的数学、代码、聊天任务上几乎全面高于 DFlash 和 Eagle3。值得注意的是 chat 的绝对 accepted length 明显低于 math/code，这支持作者后续引入动态验证预算的动机。

论文给出的宏平均提升是：Qwen3-4B/8B/14B 上，DSpark 相比 Eagle3 提升 30.9%/26.7%/30.0%，相比 DFlash 提升 16.3%/18.4%/18.3%。Gemma4-12B 上也有一致提升，说明方法不只绑定 Qwen3。

作者认为：DSpark 的提升来自把并行 drafter 的高首 token 容量与自回归的后缀依赖结合起来。我认为：这个结论是可信的，因为论文没有只报平均值，还用 position-wise conditional acceptance 展示了 DFlash/Eagle3 的互补错误模式。

### 9.4 位置级分析与消融

![位置级 conditional acceptance](../sources/noarxiv-2026-dspark/arxiv/figures/page-12.png)

图解：PDF 第 12 页 Figure 2 显示 DFlash 在首 token 很强，但 code/chat 后缀接受率下降；Eagle3 后缀稳定甚至上升，但首 token 起点低；DSpark 在首 token 和后缀稳定性之间取得折中。这个图是论文解释“为什么半自回归有效”的关键证据。

![Confidence sweep 与校准图](../sources/noarxiv-2026-dspark/arxiv/figures/page-15.png)

图解：PDF 第 15 页 Figure 5/6 说明 confidence head 能过滤高拒绝风险 suffix。threshold 提升时，Chat 的 acceptance rate 从 45.7% 升到 95.7%，Math 从 76.9% 到 92.5%，Code 从 67.6% 到 92.0%；Reliability Diagram 则显示 STS 能把 ECE 从 3%-8% 降到约 1%。

Drafter depth 消融显示，DSpark 从 1 层到 5 层性能单调增长，而且 2-layer DSpark 就能超过 5-layer DFlash，说明 sequential head 的参数效率高于简单加深并行层。Proposal length 消融显示，block 越长 DSpark 相比 DFlash 的优势越大：$\gamma=7$ 时 math/code/chat 提升 16%/15%/18%，$\gamma=15$ 时扩大到 30%/26%/22%。Latency 消融显示在 batch size 128、context length 512/1024/2048/4096 平均下，sequential loop 只给每轮 latency 增加 0.2%-1.3%。

作者认为：一点点 autoregression 就足以补并行生成的后缀短板。我认为：这个判断依赖 Markov transition 在 LLM token 层确实能捕捉局部搭配，比如 “of course” 这种邻接关系；但它不一定能解决更长距离一致性，因此 RNN head 长 proposal 下略有增益也符合直觉。

### 9.5 线上 serving 结果

![线上 Pareto frontier](../sources/noarxiv-2026-dspark/arxiv/figures/page-18.png)

图解：PDF 第 18 页 Figure 7 比较 DeepSeek-V4-Flash/Pro 线上流量下的 aggregate throughput 与 tok/s/user。DSpark 的曲线相对 MTP-1 外移：在 matched practical throughput 下，V4-Flash 用户速度提升 60%-85%，V4-Pro 提升 57%-78%。高 SLA 点的 661%/406% throughput 更应理解为“baseline 已接近不可运营边界，DSpark 仍可支撑”，不是普通场景的稳定倍数。

![负载自适应验证预算](../sources/noarxiv-2026-dspark/arxiv/figures/page-19.png)

图解：PDF 第 19 页 Figure 8 展示 scheduler 的机制：中低并发时，DSpark 把每请求 verification budget 从 MTP-1 的静态 2 token 扩到约 4-6 token；并发升高后，它平滑压缩验证长度，避免低置信 draft token 占用 target batch capacity。这个图支撑“load-aware verification”不是离线阈值 trick，而是线上系统策略。

作者认为：DSpark 在 moderate SLA 下提升吞吐，在 strict SLA 下避免吞吐坍塌，从而外移 serving Pareto frontier。我认为：这部分是论文最有产业价值的结果，但也是最难外部复现的部分；读者应把它看作 DeepSeek 内部系统中的强证据，而不是直接保证开源 DeepSpec 在任意 vLLM/SGLang 部署中获得同等收益。

## 10. 代码实现观察

公开代码仓库 DeepSpec 是一个训练和评测 speculative decoding draft models 的完整框架，MIT license。README 明确支持 DSpark、DFlash、Eagle3 三类 draft models，并提供 data preparation、training、evaluation 三阶段。

### 10.1 实现与论文描述的一致性

- `config/dspark/dspark_qwen3_4b.py` 与论文公开实验一致：默认 Qwen3-4B、block size 7、5 层 draft layers、Markov rank 256、confidence head 开启、loss 权重 CE 0.1 / L1 0.9 / confidence 1.0。
- `deepspec/modeling/dspark/markov_head.py` 直接实现论文中的 Markov head：`markov_w1` 查前一 token embedding，`markov_w2` 投影为 vocab bias，采样循环逐位置执行。
- `RNNHead` 也在代码中实现，使用 GRU-like gate/candidate/output projection，但公开默认配置使用 `markov_head_type='vanilla'`。
- `deepspec/modeling/dspark/loss.py` 使用 draft/target softmax 的 L1 distance 计算 accept-rate proxy，并用 BCE-with-logits 训练 confidence head；这与论文中的 total variation soft label 一致。
- `deepspec/eval/dspark/evaluator.py` 的公开评测实现提供 `--confidence-threshold` 的静态阈值路径和 reliability recorder，但没有公开 DeepSeek-V4 线上 hardware-aware scheduler 的生产实现。

### 10.2 隐含工程 trick

- 训练前需要 target cache。README 和 `scripts/data/README.md` 明确 Qwen3-4B 默认 target cache 约 38 TB，这是论文主体里容易被“训练数据 130 万样本”掩盖的真实复现门槛。
- 训练脚本不是标准 `torchrun` 语义，`train.py` 会按 visible GPUs 自己 spawn worker；`RANK/WORLD_SIZE` 在脚本里表示 node rank/node count。
- 代码把 DFlash 也配置为 `Qwen3DSparkTrainer`，通过关闭 confidence head、使用 CE-only loss 等配置复用同一训练器。这说明开源框架更像“统一 draft training harness”，而不是每篇论文独立代码。
- 线上 scheduler、ZOS 对接、variable-length kernel routing、DeepSeek-V4 MoE draft layers 都没有完全开源；公开代码主要能复现 Qwen3/Gemma 上的 DSpark/DFlash/Eagle3 离线训练和评测。

### 10.3 真实算力规模与可复现性

公开路径可复现性中等：有配置、数据处理、训练、评测脚本，也有 evaluation datasets；但硬件门槛高，尤其是 target cache 存储。单机 8 GPU 是默认假设，少 GPU 需要降低 `CUDA_VISIBLE_DEVICES` 和 batch 配置。论文最强的生产 claim 依赖私有 DeepSeek-V4 serving 系统，因此外部只能复现离线 accepted length 与 confidence threshold sweep 这类算法指标，不能完整复现第 5 节线上 Pareto frontier。

License 方面仓库是 MIT，但 NOTICE 说明部分代码改编自 SpecForge、DFlash、Qwen3、Gemma 等项目，实际复现实验时还要分别遵守模型权重、数据集和第三方代码许可证。
