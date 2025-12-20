#!/bin/bash
MODELS=(
  "deepseek-ai/deepseek-coder-1.3b-base"
  "codellama/CodeLlama-7b-hf"
  "WizardLM/WizardCoder-Python-7B-V1.0"
  "bigcode/starcoder2"
)

INPUT_FILE="prompts.txt"
mkdir -p results

while IFS= read -r line; do
echo "DEBUG: read line => '$line'"
  # Skip empty lines
  [[ -z "$line" ]] && continue

  for model in "${MODELS[@]}"; do
    echo "🚀 Running: $model on prompt: $line"

    jq --arg m "$model" --arg p "$line" \
      '.MODEL_PATH=$m | .PROMPT=$p' config.json > temp.json && mv temp.json config.json

    ./run_pipeline.sh

    task_name=$(echo "$line" | sed 's/[^a-zA-Z0-9_-]/_/g' | cut -c1-40)
    model_name=$(basename "$model")

    mkdir -p results/${task_name}/${model_name}
    cp generated_code/generated_code.c results/${task_name}/${model_name}/
    cp -r feedback results/${task_name}/${model_name}/ 2>/dev/null
    cp -r klee_output results/${task_name}/${model_name}/ 2>/dev/null
  done
done < "$INPUT_FILE"
