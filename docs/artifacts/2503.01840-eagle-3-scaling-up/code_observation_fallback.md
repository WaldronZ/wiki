## 10. 代码实现观察

### 10.1 仓库基本情况

- 代码仓库：https://github.com/SafeAILab/EAGLE
- 本地路径：/Users/waldron/projects/AutoPaperReader/sources/2503.01840-eagle-3-scaling-up/code
- 克隆状态：已浅克隆。
- README：存在
- License：LICENSE
- 文件类型分布：.py: 50, .json: 11, .jsonl: 9, [no extension]: 4, .gif: 2, .png: 2, .md: 1, .yaml: 1
- 可能的训练/推理入口：eagle/train/main.py, eagle/traineagle3/main.py
- 代表性文件：.gitignore, LICENSE, README.md, eagle/__init__.py, eagle/application/__init__.py, eagle/application/webui.py, eagle/data/alpaca/question.jsonl, eagle/data/gsm8k/question.jsonl, eagle/data/humaneval/question.jsonl, eagle/data/judge_prompts.jsonl, eagle/data/mt_bench/model_judgment/gpt-4_single.jsonl, eagle/data/mt_bench/question.jsonl, eagle/data/mt_bench/reference_answer/gpt-4.jsonl, eagle/data/qa/question.jsonl, eagle/data/sum/question.jsonl, eagle/evaluation/__init__.py, eagle/evaluation/alpha.py, eagle/evaluation/gen_baseline_answer_llama2chat.py, eagle/evaluation/gen_baseline_answer_llama3chat.py, eagle/evaluation/gen_baseline_answer_mix.py

### 10.2 方法实现核对

- 实现与论文是否一致：需要后续 code observation 深读确认。
- 论文未提到的工程 trick：需要后续 code observation 深读确认。

### 10.3 真实算力规模

- 真实算力规模：需要从配置、脚本和 README 进一步确认。

### 10.4 可复现性评价

- License 与可复现性：以上 license/README 信号可作为初筛，仍需人工或 LLM 复核。
