# train_dpo.py
"""
Dependency installation (recommended in a dedicated virtual environment):

pip install "transformers>=4.40.0" "datasets" "accelerate" "trl>=0.9.0" peft bitsandbytes
"""

import os
from pathlib import Path

from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import DPOTrainer, DPOConfig
from peft import LoraConfig


MODEL_NAME = "deepseek-ai/deepseek-coder-1.3b-instruct"
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(f"/scratch/{os.getlogin()}/fixer-dpo-checkpoint")
DATA_FILE = PROJECT_ROOT / "dpo_data.jsonl"

# Reuse the HF cache directory from the pipeline
user = os.getlogin()
cache_dir = os.environ.get("HF_CACHE", f"/scratch/{user}/hf_cache")
os.makedirs(cache_dir, exist_ok=True)
os.environ["HF_HOME"] = cache_dir
os.environ["TRANSFORMERS_CACHE"] = cache_dir
os.environ["HF_HUB_CACHE"] = cache_dir
os.environ["HF_DATASETS_CACHE"] = cache_dir


def main():
    local_only = os.environ.get("HF_LOCAL_ONLY", "0") == "1"

    print(f"[INFO] Loading DPO dataset from {DATA_FILE} ...")
    dataset = load_dataset("json", data_files=str(DATA_FILE), split="train")

    if len(dataset) == 0:
        print("[ERROR] Empty dataset. Please run extract_training_data.py first and check dpo_data.jsonl.")
        return

    print(f"[INFO] Dataset size: {len(dataset)} examples")

    print(f"[INFO] Loading base model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        cache_dir=str(cache_dir),
        local_files_only=local_only,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        load_in_8bit=True,
        device_map="auto",
        trust_remote_code=True,
        cache_dir=str(cache_dir),
        local_files_only=local_only,
    )

    peft_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    dpo_config = DPOConfig(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=5e-6,
        num_train_epochs=2,
        max_length=2048,
        max_prompt_length=1024,
        beta=0.1,
        logging_steps=10,
        save_steps=200,
    )

    print("[INFO] Initializing DPOTrainer ...")
    trainer = DPOTrainer(
    model=model,
    ref_model=None,
    args=dpo_config,
    train_dataset=dataset,
    peft_config=peft_config,
    )




    print("[INFO] Starting DPO training ...")
    trainer.train()

    print(f"[INFO] Saving trained model and tokenizer to {OUTPUT_DIR} ...")
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print("[INFO] Training complete.")


if __name__ == "__main__":
    main()
