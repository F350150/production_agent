"""
Skill 抽象基类 (Skill Base Class)

【设计意图】
Skill 是对多个基础工具调用的高层封装——LLM 只需发出一个 use_skill 指令，
即可触发一系列经过精心编排的子步骤，拿到一份结构化的最终报告。

这大幅减少了 LLM 多轮 Round-Trip 的时间与 Token 开销，  
同时也让代码的维护者能在一个地方集中管理"固化的最佳工作流"。

如何自定义新技能：
    1. 继承 Skill 并实现 execute() 方法
    2. 设置 name / description / parameters 三个类属性
    3. 将文件放入 skills/builtin/ 或 SKILLS_PATH 指向的目录
    4. SkillRegistry 会在启动时自动发现并注册它
"""

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """
    所有技能的抽象基类。

    子类必须定义：
        name        (str)  — 技能的唯一标识符，如 "web_research"
        description (str)  — 给 LLM 看的自然语言功能描述
        parameters  (dict) — JSON Schema 格式的入参定义

    子类必须实现：
        execute(tool_handlers, **kwargs) -> str
            tool_handlers: 工具名 -> 可调用函数的映射表（直接来自 ToolRegistry）
            kwargs:        用户传入的参数（由 parameters schema 约束）
            返回值:        面向 LLM 的文本结果报告
    """

    #: 技能唯一 ID，用于 use_skill 工具中 skill_name 字段的枚举值
    name: str = ""

    #: 功能描述，展示给 LLM 用于理解何时使用此技能
    description: str = ""

    #: 入参的 JSON Schema，嵌套在 use_skill 工具的 parameters 字段中
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": []
    }

    @abstractmethod
    def execute(self, tool_handlers: dict, **kwargs) -> str:
        """
        执行技能的核心逻辑。

        在此方法内：
        - 直接调用 tool_handlers["web_search"](query=...) 等，无需经由 LLM
        - 聚合多个工具输出，返回结构化的汇总文本
        - 任何异常都应被捕获并以可读的错误信息返回（避免中断 Agent 主循环）
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Skill name={self.name!r}>"
