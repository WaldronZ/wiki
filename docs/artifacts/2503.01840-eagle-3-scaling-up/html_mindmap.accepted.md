# EAGLE-3
## 问题发现
- feature prediction 约束限制数据 scaling
- 0-α 提升但 1-α 仍低
- 误差累积导致分布偏移
## 核心洞察
- 去除 feature prediction loss
- 多层特征融合替代 top-layer
- 训练时模拟多步推理
## 方法架构
- 单层 Transformer decoder
- 融合特征 FC 降维
- Tree-like attention mask
## 实验闭环
- 6.5x 最高加速比
- 大 batch throughput 提升
- 消融证明协同效应
## 局限与争议
- Scaling law 缺幂律拟合
- 未测 405B/671B 模型
- 训练成本未报告
