"""
scripts/train_lora.py - LoRA 微调训练脚本 (基于 Unsloth/PEFT)

【设计意图】
提供一个标准的微调模版，使用本项目采集的测试轨迹对本地模型进行微调。
推荐使用 Unsloth 库，因为它在消费级显卡上比原生 HF 训练快 2x，省 70% 显存。
"""

import os
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel

# 1. 配置参数
MODEL_NAME = "unsloth/llama-3-8b-bnb-4bit" # 默认使用 Llama-3 8B 4bit
MAX_SEQ_LENGTH = 2048
DATASET_PATH = ".team/trajectories/dataset_alpaca_latest.json" # 需指向实际导出的数据文件
OUTPUT_DIR = "models/lora_adapters"

def train():
    # 2. 加载模型与分词器
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = MODEL_NAME,
        max_seq_length = MAX_SEQ_LENGTH,
        load_in_4bit = True,
    )

    # 3. 添加 LoRA 适配器
    model = FastLanguageModel.get_peft_model(
        model,
        r = 16, # LoRA 秩
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                         "gate_proj", "up_proj", "down_proj",],
        lora_alpha = 16,
        lora_dropout = 0,
        bias = "none",
        use_gradient_checkpointing = True,
        random_state = 3407,
    )

    # 4. 准备数据集
    def format_prompts(examples):
        instructions = examples["instruction"]
        inputs       = examples["input"]
        outputs      = examples["output"]
        texts = []
        for instruction, input_text, output in zip(instructions, inputs, outputs):
            # 采用 Alpaca 模版
            text = f"### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Response:\n{output}"
            texts.append(text)
        return { "text" : texts, }

    if not os.path.exists(DATASET_PATH):
        print(f"Error: Dataset {DATASET_PATH} not found. Use managers/collector.py to export it first.")
        return

    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
    dataset = dataset.map(format_prompts, batched=True)

    # 5. 训练参数设定
    trainer = SFTTrainer(
        model = model,
        train_dataset = dataset,
        dataset_text_field = "text",
        max_seq_length = MAX_SEQ_LENGTH,
        args = TrainingArguments(
            per_device_train_batch_size = 2,
            gradient_accumulation_steps = 4,
            warmup_steps = 5,
            max_steps = 60, # 演示用，实际可根据数据量调整
            learning_rate = 2e-4,
            fp16 = not torch.cuda.is_bf16_supported(),
            bf16 = torch.cuda.is_bf16_supported(),
            logging_steps = 1,
            optim = "adamw_8bit",
            weight_decay = 0.01,
            lr_scheduler_type = "linear",
            seed = 3407,
            output_dir = OUTPUT_DIR,
        ),
    )

    # 6. 开始训练
    print("--- Starting LoRA Training ---")
    trainer.train()

    # 7. 保存适配器
    model.save_pretrained_lora(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"✅ Training complete. Adapters saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    train()
