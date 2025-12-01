#!/bin/bash

# 半导体专家级多跳QA生成器 - 集成版测试脚本

echo "========================================"
echo "  集成版测试脚本"
echo "========================================"

# 检查必要文件
echo ""
echo "[1/5] 检查文件..."
if [ ! -f "expert_qa_integrated.py" ]; then
    echo "❌ 错误: expert_qa_integrated.py 不存在"
    exit 1
fi

if [ ! -f "example_input.jsonl" ]; then
    echo "❌ 错误: example_input.jsonl 不存在"
    exit 1
fi

echo "✅ 文件检查通过"

# 检查Python环境
echo ""
echo "[2/5] 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: Python3 未安装"
    exit 1
fi

echo "Python版本: $(python3 --version)"

# 检查依赖
echo ""
echo "[3/5] 检查依赖包..."
python3 -c "import asyncio, aiohttp, json" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 错误: 缺少依赖包（asyncio, aiohttp）"
    echo "请运行: pip install aiohttp"
    exit 1
fi

echo "✅ 依赖检查通过"

# 配置LLM参数（需要用户修改）
echo ""
echo "[4/5] 配置LLM参数..."
echo "⚠️  请确保LLM服务正在运行！"
echo ""
read -p "LLM API地址 [http://localhost:8000/v1/completions]: " LLM_URL
LLM_URL=${LLM_URL:-http://localhost:8000/v1/completions}

read -p "模型名称 [Qwen2.5-72B-Instruct]: " MODEL
MODEL=${MODEL:-Qwen2.5-72B-Instruct}

echo ""
echo "配置信息:"
echo "  LLM URL: $LLM_URL"
echo "  Model: $MODEL"

# 运行测试
echo ""
echo "[5/5] 运行测试生成（2个样本）..."
echo ""

python3 expert_qa_integrated.py \
    --input_file example_input.jsonl \
    --output_file test_output.jsonl \
    --llm_url "$LLM_URL" \
    --model "$MODEL" \
    --num_samples 2 \
    --quality_filter all \
    --output_format both

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "✅ 测试成功！"
    echo "========================================"
    echo ""
    echo "生成文件:"
    echo "  - test_output.jsonl"
    echo "  - test_output.json"
    echo "  - test_output_report.json"
    echo ""
    echo "查看结果:"
    echo "  cat test_output_report.json | python3 -m json.tool"
    echo ""
    
    # 显示质量报告
    if [ -f "test_output_report.json" ]; then
        echo "质量报告摘要:"
        python3 -c "
import json
with open('test_output_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)
    print(f\"  总数: {report.get('total', 0)}\")
    print(f\"  质量分布: {report.get('quality_distribution', {})}\")
    print(f\"  最终验证通过率: {report.get('final_validation', {}).get('rate', 0)*100:.1f}%\")
    print(f\"  增强检查通过率: {report.get('enhanced_checks', {}).get('rate', 0)*100:.1f}%\")
    print(f\"  平均得分: {report.get('average_score', 0):.1f}/25\")
" 2>/dev/null
    fi
else
    echo ""
    echo "========================================"
    echo "❌ 测试失败"
    echo "========================================"
    echo ""
    echo "可能的原因:"
    echo "  1. LLM服务未启动或地址错误"
    echo "  2. 模型名称不正确"
    echo "  3. 输入数据格式错误"
    echo ""
    echo "请检查错误信息并重试"
    exit 1
fi
