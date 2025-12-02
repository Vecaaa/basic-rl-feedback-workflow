#!/bin/bash
# wait_for_gpu.sh
# 自动检测 GPU 显存是否低于某阈值后再启动任务

THRESHOLD=2000  # 单位 MiB，可自行调整
echo "⏳ Waiting for GPU memory < $THRESHOLD MiB ..."

while true; do
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    if [ "$USED" -lt "$THRESHOLD" ]; then
        echo "✅ GPU free enough ($USED MiB used). Starting job..."
        ./run_pipeline.sh
        break
    else
        echo "🚧 GPU busy ($USED MiB used). Rechecking in 60s..."
        sleep 60
    fi
done