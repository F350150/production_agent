#!/bin/bash

# =================================================================
# Production Agent 自动化测试与覆盖率脚本
# =================================================================

# 获取脚本所在目录的上一级目录作为项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "\033[1;34m[TestRunner] 正在初始化环境...\033[0m"
export PYTHONPATH="$PROJECT_ROOT"

# 检查是否安装了必要依赖
if ! python -c "import pytest_cov" &> /dev/null; then
    echo -e "\033[1;33m[TestRunner] 正在安装 pytest-cov...\033[0m"
    pip install pytest-cov
fi

echo -e "\033[1;34m[TestRunner] 开始执行单元测试并计算覆盖率...\033[0m"

# 执行 pytest
# 由于代码内部使用非 package-absolute 导入，我们需要直接指定子目录进行覆盖率跟踪
pytest --cov=core --cov=managers --cov=tools --cov=utils --cov=skills --cov=main --cov-branch --cov-report=term-missing --cov-report=html tests/

if [ $? -eq 0 ]; then
    echo -e "\n\033[1;32m[TestRunner] ✅ 所有测试已通过！\033[0m"
    REPORT_PATH="$PROJECT_ROOT/htmlcov/index.html"
    echo -e "\033[1;36m[TestRunner] 📊 覆盖率 HTML 报告已生成，绝对路径如下：\033[0m"
    echo -e "\033[4;36mfile://$REPORT_PATH\033[0m"
    echo -e "\n(你可以直接在支持终端点击此路径，或手动复制到浏览器打开。)"
else
    echo -e "\n\033[1;31m[TestRunner] ❌ 测试执行失败，请检查上方错误输出。\033[0m"
    exit 1
fi
