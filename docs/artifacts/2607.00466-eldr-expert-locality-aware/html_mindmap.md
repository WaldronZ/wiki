# ELDR
## 问题本质
- MoE decode 延迟由 distinct expert 数主导
- 负载均衡路由忽略 expert 激活模式差异
- 每步 active expert 增至 128 时延迟涨 4.7×
## 关键观察
- Expert 使用呈 domain 结构性（Code/Math/Medical/Legal）
- Prefill 激活可预测 decode expert 选择（ρ=0.70–0.92）
- Same-domain batch 少激活 17–21% distinct expert
## 核心方法
- Expert Signature：离散计数 + IDF 降噪 + 贪心层选择
- Hungarian-balanced K-means 离线聚类保均衡
- Locality-band 在线路由（τ=0.1）平衡 locality 与负载
- Signature cache 与 KV cache 共索引保一致性
## 实验闭环
- 3 模型 × 2 workload 降 median TPOT 5.9–13.9%
- 消融验证每组件边际贡献（signature / balance / τ / cache）
- 扩展至 235B 模型 / 40 GPU 仍有效
## 局限与反思
- 与同期工作 eapatterns 核心洞察高度重合
- Signature ρ 绝对值仅 ~0.68，预测力有限
- 单一硬件平台（MI300X），NVIDIA 生态未验证
- Offline calibration 假设 workload 稳定，缺乏自适应方案
- Lossless 优势未与 lossy 方法做 accuracy-efficiency 对比
