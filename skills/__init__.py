"""Skills package — 可插拔的高层技能模块"""
from skills.base import Skill
from skills.skill_registry import SkillRegistry, skill_registry

__all__ = ["Skill", "SkillRegistry", "skill_registry"]
