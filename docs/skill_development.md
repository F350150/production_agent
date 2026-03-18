# 技能开发与范式转移 (Skill Development)

在 **Production Agent** 中，“技能（Skill）”不只是简单的代码片段，它是智能体与物理世界交互的**语义化接口**。本指南将帮助开发者理解如何将传统的 Python 工程逻辑转化为智能体可调用的原子能力。

---

## 🚀 从“确定性调用”到“语义化推理”的范式转移

传统开发中，你通过函数签名明确调用逻辑；而在智能体开发中，你向模型提供**描述性 Schema**。

| 维度 | 传统函数 (Function) | 智能体技能 (Skill) |
| :--- | :--- | :--- |
| **触发方式** | 代码显式调用 | 模型根据描述意图自主触发 |
| **输入容错** | 严格类型匹配 | LLM 进行模糊匹配与参数纠错 |
| **输出处理** | 程序逻辑处理 | 转化为 Observation 供模型思考 |
| **核心挑战** | 算法复杂度 | 描述的语义清晰度与幻觉控制 |

---

## 🛠 开发一个生产级 Skill

所有的 Skill 都继承自 `skills.skill_registry.Skill` 基类。

### 1. 结构化描述 (Input Schema)
Skill 的核心不在于 `execute` 里的 Python 代码，而在于 `input_schema`。这是模型推理的唯一依据。
-   **原则**：描述越清晰，模型调用的准确率越高。
-   **技巧**：通过 `enum` 限制可选值，通过 `description` 告知参数的业务边界。

### 2. 代码实现示例：`CodeReviewSkill`
```python
class CodeReviewSkill(Skill):
    """
    提供静态代码扫描与逻辑审查功能。
    """
    @property
    def name(self) -> str:
        return "code_review"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "待审查的文件绝对路径"},
                "focus_area": {"type": "string", "enum": ["security", "performance", "style"], "description": "侧重的审查领域"}
            },
            "required": ["file_path"]
        }

    def execute(self, **kwargs) -> str:
        # 在这里实现确定性的工程逻辑
        path = kwargs.get("file_path")
        # ... 进行 linting 或 AST 分析
        return "发现 2 个性能瓶颈点：..."
```

---

## 🧩 技能发现与动态注册 (Autodiscovery)

项目采用了**反射机制**实现解耦：
1.  **扫描**：`SkillRegistry` 在启动时会自动递归扫描 `skills/builtin/` 目录。
2.  **验证**：自动检测所有继承自 `Skill` 且非抽象的类。
3.  **对齐**：将 `input_schema` 自动转化为符合 Anthropic Tool Use 规范的 JSON 定义。

这种设计意味着开发者只需将新的 `.py` 文件丢进目录，重启智能体即可获得新能力。

---

## 📦 内置技能 (Built-in Skills)

项目内置了 5 个实用技能：

| 技能名称 | 功能 | 主要参数 |
|----------|------|----------|
| `debug_explain` | 解析错误堆栈，提供修复建议 | `error_traceback`: 错误堆栈 |
| `generate_test` | 生成 pytest 测试用例 | `target`: 文件路径或代码 |
| `api_design_review` | 评估 API 设计质量 | `target`: 文件路径 |
| `dependency_analysis` | 分析导入/调用图 | `target`: 项目路径 |
| `code_migration` | 代码框架迁移 | `target`: 文件路径, `migration_type`: 迁移类型 |

### 使用示例
```python
# 通过 use_skill 工具调用
use_skill(
    skill_name="debug_explain",
    parameters={"error_traceback": "NameError: name 'x' is not defined"}
)

use_skill(
    skill_name="generate_test",
    parameters={"target": "path/to/module.py"}
)

use_skill(
    skill_name="code_migration",
    parameters={"target": "app.py", "migration_type": "flask_to_fastapi"}
)
```

---

## 💡 开发者的深度建议：什么时候该写 Skill？

并不是所有逻辑都应该交给智能体思考。以下场景必须通过 Skill 封装：
-   **长路径逻辑**：如递归遍历数千个文件。
-   **高精度计算/转换**：如 Markdown 到 PDF 的转换，或复杂的正则替换。
-   **权限限制操作**：封装敏感的 API 调用，仅暴露受控的参数给 AI。

> [!IMPORTANT]
> **Tool Hallucination (工具幻觉) 防御**：如果模型总是错误调用你的工具，大概率是因为你的 `description` 指向模糊。请尝试像给新入职的初级开发写注释一样清晰地描述你的 Skill。
