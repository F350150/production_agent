"""
技能注册中心 (Skill Registry)

【设计意图】
自动扫描并加载所有继承自 Skill 的子类，将它们暴露为一个统一的 use_skill 工具。
LLM 无需了解每个 Skill 的具体 Python 实现，只需指定 skill_name + 对应参数即可。

自动发现规则：
    1. 扫描 skills/builtin/ 目录（内置技能）
    2. 扫描 SKILLS_PATH 环境变量指向的目录（用户自定义技能）
    3. 对每个 .py 文件，import 并检查所有 Skill 子类，自动注册
"""

import importlib
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Type, Optional, Callable

from skills.base import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    技能注册中心（单例模式）。

    使用方式：
        registry = SkillRegistry()
        registry.initialize()
        schema = registry.get_skill_tool_schema()    # -> Anthropic 工具定义
        handler = registry.get_skill_handler(tool_handlers)  # -> callable
    """

    _instance: Optional["SkillRegistry"] = None
    _skills: dict[str, Skill] = {}
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> "SkillRegistry":
        """扫描并加载所有技能（幂等）"""
        if self._initialized:
            return self

        # 1. 内置技能目录
        builtin_dir = Path(__file__).parent / "builtin"
        
        # 尝试多种可能的包路径，以适应各种运行环境（Standalone / Repository / Installed）
        potential_prefixes = ["skills.builtin", "production_agent.skills.builtin"]
        for prefix in potential_prefixes:
            try:
                # 尝试导入内置技能目录下的一个代表性文件（如 __init__.py 的父模块）
                importlib.import_module(prefix.split(".")[0])
                self._scan_directory(builtin_dir, package_prefix=prefix)
                # 如果成功加载了一些技能，就不再尝试其他前缀
                if self._skills:
                    break
            except ImportError:
                continue

        # 如果通过包导入失败，兜底使用路径动态加载（不带 package_prefix）
        if not self._skills:
            logger.info("[SkillRegistry] Package-style load failed, falling back to file-spec load.")
            self._scan_directory(builtin_dir, package_prefix=None)

        # 2. 用户自定义技能目录（通过环境变量 SKILLS_PATH 配置）
        custom_path = os.getenv("SKILLS_PATH", "").strip()
        if custom_path:
            custom_dir = Path(custom_path).expanduser().resolve()
            if custom_dir.is_dir():
                self._scan_directory(custom_dir, package_prefix=None)
            else:
                logger.warning(f"[SkillRegistry] SKILLS_PATH '{custom_path}' is not a valid directory")

        loaded_names = list(self._skills.keys())
        if loaded_names:
            logger.info(f"[SkillRegistry] Loaded {len(loaded_names)} skill(s): {loaded_names}")
            print(f"\033[32m[SkillRegistry] Loaded {len(loaded_names)} skill(s): {loaded_names}\033[0m")
        else:
            logger.info("[SkillRegistry] No skills found.")

        self._initialized = True
        return self

    def _scan_directory(self, directory: Path, package_prefix: Optional[str]):
        """扫描目录，导入所有 .py 文件并注册 Skill 子类"""
        if not directory.exists():
            return

        for py_file in sorted(directory.glob("*.py")):
            if py_file.stem.startswith("_"):
                continue  # 跳过 __init__.py 和私有文件
            try:
                if package_prefix:
                    # 包内模块，用标准 import 保证 __package__ 正确
                    module_name = f"{package_prefix}.{py_file.stem}"
                    module = importlib.import_module(module_name)
                else:
                    # 外部路径，用 spec_from_file_location 动态加载
                    spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Skill) and obj is not Skill and obj.name:
                        skill_instance = obj()
                        self._skills[skill_instance.name] = skill_instance
                        logger.debug(f"[SkillRegistry] Registered skill: '{skill_instance.name}'")

            except Exception as e:
                logger.error(f"[SkillRegistry] Failed to load '{py_file}': {e}")

    # ──────────────────────────────────────────────
    # 对外接口（供 ToolRegistry 调用）
    # ──────────────────────────────────────────────

    def get_skill_names(self) -> list[str]:
        """返回所有已注册技能的名称列表"""
        return list(self._skills.keys())

    def get_skill_tool_schema(self) -> Optional[dict]:
        """
        生成 use_skill 工具的 Anthropic Schema。
        若没有技能则返回 None（不向 LLM 暴露空工具）。
        """
        names = self.get_skill_names()
        if not names:
            return None

        # 构建每个技能的 parameters 描述，嵌入 skill_name 枚举注释
        skill_docs = "\n".join(
            f"  - {s.name}: {s.description}" for s in self._skills.values()
        )

        return {
            "name": "use_skill",
            "description": (
                "Execute a pre-built multi-step skill that orchestrates multiple tools internally. "
                "Available skills:\n" + skill_docs
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": names,
                        "description": "The skill to invoke."
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Parameters for the skill. Each skill has its own parameter schema.",
                        "additionalProperties": True
                    }
                },
                "required": ["skill_name", "parameters"]
            }
        }

    def get_skill_handler(self, tool_handlers: dict) -> Callable:
        """
        返回 use_skill 工具的执行函数。

        tool_handlers: 基础工具 handler 映射，技能内部将直接调用它们。
        返回的 callable: (skill_name, parameters) -> str
        """
        def _use_skill_handler(**kwargs) -> str:
            skill_name = kwargs.get("skill_name", "")
            params = kwargs.get("parameters", {})
            skill = self._skills.get(skill_name)
            if skill is None:
                return f"Error: Unknown skill '{skill_name}'. Available: {self.get_skill_names()}"
            try:
                logger.info(f"[SkillRegistry] Running skill '{skill_name}' with params: {params}")
                return skill.execute(tool_handlers=tool_handlers, **params)
            except Exception as e:
                logger.error(f"[SkillRegistry] Skill '{skill_name}' raised: {e}")
                return f"Error executing skill '{skill_name}': {e}"

        return _use_skill_handler


# 全局单例访问点
skill_registry = SkillRegistry()
