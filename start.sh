#!/bin/bash

# RAG 搜索服务启动脚本

echo "=========================================="
echo "RAG 搜索服务 - 改进版 v2.0"
echo "=========================================="

# 检查配置文件
if [ ! -f "config.yaml" ]; then
    echo "❌ 错误: 配置文件 config.yaml 不存在"
    exit 1
fi

# 检查 Python 依赖
echo "检查 Python 环境..."
python3 -c "import yaml" 2>/dev/null
if [ $# -ne 0 ]; then
    echo "❌ 错误: 缺少 PyYAML，请安装: pip install pyyaml"
    exit 1
fi

# 创建日志目录
mkdir -p logs

echo "✓ 环境检查完成"
echo "=========================================="

# 启动服务
echo "启动服务..."
python3 search_service_improved.py

# 如果需要后台运行，使用:
# nohup python3 search_service_improved.py > logs/service.log 2>&1 &
# echo $! > service.pid
# echo "✓ 服务已后台启动，PID: $(cat service.pid)"
# echo "日志文件: logs/service.log"
