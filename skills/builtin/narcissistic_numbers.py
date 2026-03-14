"""
内置技能：水仙花数/自恋数 (Narcissistic Numbers Skill)

【设计意图】
将"查找 → 验证 → 格式化输出"的数学计算流程封装为一个原子操作。
LLM 只需调用一次 use_skill(skill_name="narcissistic_numbers", parameters={...})，
即可获得完整的水仙花数报告，包含详细的计算分解。

水仙花数（Narcissistic Numbers / Armstrong Numbers / Daffodil Numbers）：
定义：n位数等于其各位数字的n次幂之和
例如：153 = 1³ + 5³ + 3³ = 1 + 125 + 27 = 153

性能优化：
- 预计算 0-9 的各次幂（支持最多 6-7 位数字）
- 纯整数运算，避免字符串转换（仅输出时使用）
- 提前终止（部分和超过原数时）
- 结果缓存

注意：此 Skill 不依赖 LLM，全程同步执行，零额外 Token 消耗。
"""

import logging
from typing import List

from skills.base import Skill

logger = logging.getLogger(__name__)


class NarcissisticNumberSkill(Skill):
    """水仙花数查找技能：在指定范围内查找自恋数并生成详细报告"""

    name = "narcissistic_numbers"
    description = (
        "Find and display narcissistic numbers (also called Armstrong numbers or daffodil numbers) "
        "in a specified range. Narcissistic numbers are numbers equal to the sum of their own digits "
        "each raised to the power of the number of digits. "
        "Example: 153 = 1³ + 5³ + 3³ = 1 + 125 + 27 = 153"
    )
    parameters = {
        "type": "object",
        "properties": {
            "start": {
                "type": "integer",
                "description": "Start of range (inclusive, default: 100)",
                "default": 100
            },
            "end": {
                "type": "integer",
                "description": "End of range (inclusive, default: 999)",
                "default": 999
            },
            "interactive": {
                "type": "boolean",
                "description": "Run in interactive mode with menu-driven interface (default: false)",
                "default": False
            },
            "show_details": {
                "type": "boolean",
                "description": "Show detailed calculation breakdown for each number (default: false)",
                "default": False
            }
        },
        "required": []
    }

    # 类级别的幂缓存 {digit: {power: value}}
    _power_cache: dict[int, dict[int, int]] = {}
    # 结果缓存 {(start, end): [list of numbers]}
    _result_cache: dict[tuple[int, int], List[int]] = {}

    @classmethod
    def _precompute_powers(cls, max_digits: int = 7) -> None:
        """预计算 0-9 的各次幂，缓存到类级别"""
        for digit in range(10):
            cls._power_cache[digit] = {}
            for power in range(1, max_digits + 1):
                cls._power_cache[digit][power] = digit ** power

    @classmethod
    def _get_power(cls, digit: int, power: int) -> int:
        """从缓存中获取 digit 的 power 次幂"""
        if not cls._power_cache:
            cls._precompute_powers()
        return cls._power_cache.get(digit, {}).get(power, digit ** power)

    @classmethod
    def _count_digits(cls, num: int) -> int:
        """计算数字的位数（纯整数运算）"""
        if num == 0:
            return 1
        count = 0
        while num > 0:
            num //= 10
            count += 1
        return count

    @classmethod
    def is_narcissistic(cls, num: int) -> bool:
        """
        检查一个数是否为水仙花数

        Args:
            num: 要检查的正整数

        Returns:
            bool: 如果是水仙花数返回 True，否则返回 False
        """
        if num < 0:
            return False

        original = num
        num_digits = cls._count_digits(num)
        power_sum = 0

        while num > 0:
            digit = num % 10
            power_sum += cls._get_power(digit, num_digits)

            # 提前终止优化：如果部分和已经超过原数
            if power_sum > original:
                return False

            num //= 10

        return power_sum == original

    @classmethod
    def find_narcissistic_range(cls, start: int, end: int) -> List[int]:
        """
        在指定范围内查找所有水仙花数

        Args:
            start: 起始值（包含）
            end: 结束值（包含）

        Returns:
            List[int]: 水仙花数列表
        """
        if start > end:
            return []

        # 检查缓存
        cache_key = (start, end)
        if cache_key in cls._result_cache:
            return cls._result_cache[cache_key]

        result = []
        for num in range(max(0, start), end + 1):
            if cls.is_narcissistic(num):
                result.append(num)

        # 缓存结果
        cls._result_cache[cache_key] = result
        return result

    @classmethod
    def format_breakdown(cls, num: int) -> str:
        """
        生成水仙花数的详细计算分解

        Args:
            num: 水仙花数

        Returns:
            str: 格式化的计算分解字符串
        """
        if not cls.is_narcissistic(num):
            return f"{num} is not a narcissistic number"

        original = num
        num_digits = cls._count_digits(num)

        # 提取各位数字
        digits = []
        temp = num
        while temp > 0:
            digits.append(temp % 10)
            temp //= 10
        digits.reverse()  # 从高位到低位

        # 生成格式化的幂符号
        power_symbols = {
            1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹"
        }
        power_symbol = power_symbols.get(num_digits, str(num_digits))

        # 构建表达式
        parts = []
        calc_parts = []
        sum_values = []

        for digit in digits:
            parts.append(f"{digit}{power_symbol}")
            calc_parts.append(f"{digit}{power_symbol}")
            sum_values.append(str(cls._get_power(digit, num_digits)))

        expression = " + ".join(parts)
        calc_expression = " + ".join(calc_parts)
        sum_expression = " + ".join(sum_values)

        return (
            f"**{num}** = {expression} = {calc_expression} = {sum_expression} = {num}"
        )

    def interactive_session(self) -> str:
        """
        交互式会话：通过菜单驱动的方式与用户交互

        Returns:
            str: 交互式会话的结果报告
        """
        lines = [
            "# 🔢 Narcissistic Numbers - Interactive Mode",
            "",
            "Welcome to the interactive narcissistic number finder!",
            "",
        ]

        # 模拟交互式会话（实际场景中可能需要更复杂的输入处理）
        lines += [
            "Menu:",
            "1. Find narcissistic numbers in a custom range",
            "2. Show known narcissistic numbers (1-7 digits)",
            "3. Check if a specific number is narcissistic",
            "4. Exit",
            "",
        ]

        # 预定义一些已知的交互结果
        lines += [
            "## Quick Reference: Known Narcissistic Numbers",
            "",
            "**1-digit:** 1, 2, 3, 4, 5, 6, 7, 8, 9",
            "**3-digit:** 153, 370, 371, 407",
            "**4-digit:** 1634, 8208, 9474",
            "**5-digit:** 54748, 92727, 93084",
            "**6-digit:** 548834",
            "**7-digit:** 1741725, 4210818, 9800817, 9926315",
            "",
            "---",
            "_Interactive mode completed by NarcissisticNumberSkill_",
        ]

        return "\n".join(lines)

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        """
        执行水仙花数查找技能

        Args:
            tool_handlers: 工具处理器映射（本技能不需要）
            **kwargs: 参数包括 start, end, interactive, show_details

        Returns:
            str: 格式化的 Markdown 报告
        """
        start = kwargs.get("start", 100)
        end = kwargs.get("end", 999)
        interactive = kwargs.get("interactive", False)
        show_details = kwargs.get("show_details", False)

        # 参数验证
        try:
            start = int(start)
            end = int(end)
        except (ValueError, TypeError):
            return "Error: 'start' and 'end' must be valid integers."

        if interactive:
            return self.interactive_session()

        if start < 0 or end < 0:
            return "Error: Range values must be non-negative."

        if start > end:
            return f"Error: Start value ({start}) cannot be greater than end value ({end})."

        # 查找水仙花数
        numbers = self.find_narcissistic_range(start, end)

        # 构建报告
        report_lines = [
            "# 🔢 Narcissistic Numbers Report",
            f"**Range**: {start} to {end}",
            "",
        ]

        if not numbers:
            report_lines += [
                "No narcissistic numbers found in this range.",
                "",
                "---",
                "_Report completed by NarcissisticNumberSkill_",
            ]
            return "\n".join(report_lines)

        report_lines += [
            f"Found {len(numbers)} narcissistic number(s):",
            "",
        ]

        # 输出每个水仙花数
        for i, num in enumerate(numbers, 1):
            if show_details:
                report_lines.append(f"{i}. {self.format_breakdown(num)}")
            else:
                report_lines.append(f"{i}. **{num}**")

        report_lines += [
            "",
            "---",
            "_Report completed by NarcissisticNumberSkill_",
        ]

        return "\n".join(report_lines)
