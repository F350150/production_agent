# LoRA 微调与持续学习指南 (LoRA Fine-Tuning) 🧬

本项目支持通过 LoRA（Low-Rank Adaptation）技术对本地大模型进行轻量化微调，使智能体能够针对特定工作流或专家角色进行“深度进化”。

---

## 1. 核心流程 (Core Flow)

本系统的 LoRA 闭环由三个核心环节组成：

1.  **轨迹收集 (Collection)**：`managers/collector.py` 自动监听 Swarm 状态，将每一次成功的任务执行记录为 `.json` 轨迹。
2.  **数据转换 (Export)**：通过收集器的一键导出功能，将原始轨迹转换为标准的 Alpaca 或 ShareGPT 微调格式。
3.  **模型训练 (Training)**：使用 `scripts/train_lora.py` 在本地显卡（推荐 NVIDIA 3090+）上利用 Unsloth/PEFT 进行训练。
4.  **动态加载 (Serving)**：在 `.env` 中指定适配器路径，`core/llm.py` 将在运行时自动挂载微调后的“专家插件”。

---

## 2. 轨迹收集器 (Trajectory Collector)

收集器默认在以下路径工作：
- **存储路径**：`.team/trajectories/`

### 自动收集
每一轮对话结束后，`SwarmOrchestrator` 会自动调用 `collector.record_session()`。

### 手动导出训练集
你可以运行以下代码将所有轨迹打包导出一个训练文件：
```python
from managers.collector import collector
export_path = collector.export_for_finetune(format="alpaca")
print(f"Dataset ready at: {export_path}")
```

---

## 3. 训练指南 (Training Guide)

我们推荐使用 [Unsloth](https://github.com/unslothai/unsloth) 库，因为它在保证效果的同时能节省极大显存。

### 运行训练脚本
```bash
# 确保已安装 unsloth 和 peft
python scripts/train_lora.py
```

### 关键超参数建议
- **r (Rank)**: 16 (推荐)。过小模型学不到复杂指令，过大则容易过拟合。
- **lora_alpha**: 16 或 32。
- **learning_rate**: 2e-4 (适配 Llama-3/Qwen2.5)。

---

## 4. 如何启用微调后的模型 (Configuration)

训练完成后，在你的 `.env` 文件中开启本地模型支持：

```env
# 启用本地后端
USE_LOCAL_LLM=true

# 本地服务地址 (如 vLLM 或 Ollama)
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL_ID=your-finetuned-model-name

# (可选) 适配器路径说明
LORA_ADAPTER_PATH=./models/lora_adapters
```

---

## 5. 什么时候需要微调？

- **格式控制**：当 Agent 总是无法正确输出某种特定格式的 JSON 或 Tool 调用时。
- **角色对齐**：当 PM 角色的回复过于啰唆，或 Coder 经常忘记写注释时。
- **领域知识**：当 Agent 需要学习公司内部私有的 API 调用约定或代码规范时。

> [!TIP]
> **冷启动建议**：先使用云端模型（如 Claude 3.5）运行一段时间，积累大约 100-200 条高质量轨迹后再进行首次微调。
