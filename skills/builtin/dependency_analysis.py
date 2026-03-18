"""
内置技能：依赖分析 (Dependency Analysis Skill)

【设计意图】
分析 Python 文件的依赖关系，包括：
1. 直接 import 的模块
2. from ... import 的具体名称
3. 模块间的调用关系图
4. 潜在的循环依赖检测
5. 未使用或缺失的依赖提示

步骤：
    1. 读取目标文件，解析 AST 获取所有 import 语句
    2. 追踪函数/类间的调用关系
    3. 生成依赖图和调用链
    4. 检测潜在问题并给出建议
"""

import ast
import logging
import re
from pathlib import Path
from collections import defaultdict

from skills.base import Skill

logger = logging.getLogger(__name__)


class DependencyAnalysisSkill(Skill):
    """依赖分析技能：分析模块导入、调用关系、循环依赖检测"""

    name = "dependency_analysis"
    description = (
        "Analyze Python file dependencies: imports, function calls, "
        "dependency graphs, and circular dependency detection. "
        "Helps understand codebase architecture and identify coupling issues."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "File path to analyze (e.g., 'src/main.py')"
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth for call chain analysis",
                "default": 3
            },
            "detect_cycles": {
                "type": "boolean",
                "description": "Enable circular dependency detection",
                "default": True
            }
        },
        "required": ["target"]
    }

    BUILTIN_MODULES = {
        'os', 'sys', 'time', 'datetime', 'json', 're', 'math', 'random',
        'collections', 'itertools', 'functools', 'operator', 'abc', 'copy',
        'io', 'pathlib', 'typing', 'warnings', 'logging', 'traceback',
        'unittest', 'doctest', 'pprint', 'string', 'struct', 'pickle',
        'sqlite3', 'csv', 'configparser', 'argparse', 'shutil', 'glob',
        'tempfile', 'uuid', 'hashlib', 'hmac', 'base64', 'binascii'
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        target = kwargs.get("target", "")
        max_depth = kwargs.get("max_depth", 3)
        detect_cycles = kwargs.get("detect_cycles", True)

        if not target:
            return "Error: 'target' parameter is required for dependency_analysis skill."

        read_file = tool_handlers.get("read_file")
        if not read_file:
            return "Error: read_file tool is not available."

        try:
            content = read_file(file_path=target)
        except Exception as e:
            return f"Error: Failed to read target file '{target}': {e}"

        if not target.endswith('.py'):
            return f"Error: Only Python files (.py) are supported for dependency analysis."

        report_lines = [
            f"# 🔗 Dependency Analysis Report",
            f"",
            f"**File**: `{target}`",
            f"**Max Depth**: {max_depth}",
            f"**Cycle Detection**: {'Enabled' if detect_cycles else 'Disabled'}",
            f""
        ]

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"Error: Cannot parse '{target}' - syntax error at line {e.lineno}: {e.msg}"

        imports = self._extract_imports(tree)
        functions = self._extract_functions(tree)
        calls = self._extract_calls(tree, functions)
        dependencies = self._build_dependency_graph(imports, functions)

        report_lines.append(f"## 📦 Import Summary")
        report_lines.append(f"")

        stdlib_imports = [i for i in imports if i['module'] in self.BUILTIN_MODULES]
        third_party_imports = [i for i in imports if i['module'] and not self._is_stdlib(i['module']) and not i['module'].startswith('.')]
        local_imports = [i for i in imports if i['module'] and (i['module'].startswith('.') or self._is_local(i['module'], target))]

        if stdlib_imports:
            report_lines.append(f"### Standard Library ({len(stdlib_imports)})")
            for imp in stdlib_imports:
                names = f"({', '.join(imp['names'])})" if imp['names'] else ""
                report_lines.append(f"- `{imp['module']}`{names}")
            report_lines.append(f"")

        if third_party_imports:
            report_lines.append(f"### Third-Party ({len(third_party_imports)})")
            for imp in third_party_imports:
                names = f"({', '.join(imp['names'])})" if imp['names'] else ""
                report_lines.append(f"- `{imp['module']}`{names}")
            report_lines.append(f"")

        if local_imports:
            report_lines.append(f"### Local Imports ({len(local_imports)})")
            for imp in local_imports:
                names = f"({', '.join(imp['names'])})" if imp['names'] else ""
                report_lines.append(f"- `{imp['module']}`{names}")
            report_lines.append(f"")

        report_lines.append(f"## � function Calls")
        report_lines.append(f"")

        if functions:
            report_lines.append(f"Found {len(functions)} functions:")
            for func in functions[:20]:
                line_indicator = "📍" if func['calls'] else "  "
                report_lines.append(f"{line_indicator} **L{func['lineno']}** `{func['name']}()` → calls {[c for c in func['calls'] if c not in self.BUILTIN_MODULES][:5]}")
            if len(functions) > 20:
                report_lines.append(f"... and {len(functions) - 20} more functions")
            report_lines.append(f"")

        report_lines.append(f"## 🕸️ Dependency Graph")
        report_lines.append(f"")

        graph_lines = self._render_graph(dependencies, functions)
        report_lines.extend(graph_lines)
        report_lines.append(f"")

        if detect_cycles:
            cycles = self._detect_cycles(dependencies, functions)
            if cycles:
                report_lines.append(f"## ⚠️ Circular Dependencies Detected")
                report_lines.append(f"Found {len(cycles)} potential circular dependency:")
                for cycle in cycles:
                    cycle_str = " → ".join(cycle)
                    report_lines.append(f"- `{cycle_str} → {cycle[0]}`")
                report_lines.append(f"")
            else:
                report_lines.append(f"## ✅ No Circular Dependencies")
                report_lines.append(f"")
        else:
            report_lines.append(f"## ⚠️ Cycle Detection Disabled")
            report_lines.append(f"")

        report_lines.append(f"## 💡 Recommendations")
        recommendations = self._generate_recommendations(imports, functions, third_party_imports)
        for rec in recommendations:
            report_lines.append(f"- {rec}")

        report_lines.append(f"")
        report_lines.append(f"---")
        report_lines.append(f"_Dependency analysis completed by DependencyAnalysisSkill_")

        return "\n".join(report_lines)

    def _extract_imports(self, tree: ast.AST) -> list[dict]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        'module': alias.name,
                        'names': [alias.name],
                        'lineno': node.lineno,
                        'type': 'import'
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                imports.append({
                    'module': module,
                    'names': names,
                    'lineno': node.lineno,
                    'type': 'from'
                })
        return imports

    def _extract_functions(self, tree: ast.AST) -> list[dict]:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_method = any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree) if parent != node)
                functions.append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'is_method': is_method,
                    'is_async': isinstance(node, ast.AsyncFunctionDef),
                    'calls': []
                })
        return functions

    def _extract_calls(self, tree: ast.AST, functions: list[dict]) -> list[tuple]:
        calls = []
        func_names = {f['name'] for f in functions}

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append((node.func.id, node.lineno))
                elif isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr
                    calls.append((attr_name, node.lineno))

        for func in functions:
            func_calls = [c[0] for c in calls if c[1] == func['lineno']]
            func['calls'] = list(set(func_calls))

        return calls

    def _build_dependency_graph(self, imports: list[dict], functions: list[dict]) -> dict:
        graph = defaultdict(list)

        for imp in imports:
            if imp['module']:
                graph[imp['module']] = []

        for func in functions:
            for call in func['calls']:
                if call in [f['name'] for f in functions]:
                    graph[f"local:{func['name']}"].append(f"local:{call}")

        return dict(graph)

    def _render_graph(self, dependencies: dict, functions: list[dict]) -> list[str]:
        lines = []
        lines.append("```")
        lines.append("digraph dependencies {")
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box, style=rounded];")
        lines.append("")

        for dep, targets in dependencies.items():
            dep_label = dep.replace('.', '_').replace(':', '_')
            if targets:
                for target in targets[:5]:
                    target_label = target.replace('.', '_').replace(':', '_')
                    lines.append(f'  "{dep_label}" -> "{target_label}";')
            else:
                lines.append(f'  "{dep_label}";')

        lines.append("}")
        lines.append("```")

        local_funcs = [f['name'] for f in functions if not f['is_method']]
        if local_funcs:
            lines.append(f"\n**Local Functions**: {', '.join(local_funcs[:10])}")
            if len(local_funcs) > 10:
                lines.append(f"... and {len(local_funcs) - 10} more")

        return lines

    def _detect_cycles(self, dependencies: dict, functions: list[dict]) -> list[list[str]]:
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> None:
            if node in rec_stack:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return
            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            if node in dependencies:
                for neighbor in dependencies[node]:
                    if neighbor.startswith('local:'):
                        dfs(neighbor)

            path.pop()
            rec_stack.remove(node)

        for func in functions:
            if not func['is_method']:
                dfs(f"local:{func['name']}")

        return cycles[:5]

    def _is_stdlib(self, module: str) -> bool:
        top_level = module.split('.')[0]
        return top_level in self.BUILTIN_MODULES

    def _is_local(self, module: str, target_file: str) -> bool:
        if not module:
            return False
        module_path = Path(module.replace('.', '/'))
        target_dir = Path(target_file).parent

        for ext in ['.py', '__init__.py']:
            try:
                candidate = module_path.with_suffix(ext)
                if (target_dir / candidate).exists():
                    return True
            except ValueError:
                pass
            try:
                if (target_dir / module_path / f"__init__{ext}").exists():
                    return True
            except ValueError:
                pass

        return False

    def _generate_recommendations(self, imports: list[dict], functions: list[dict], third_party: list[dict]) -> list[str]:
        recs = []

        if len(imports) > 20:
            recs.append("High number of imports detected. Consider consolidating related imports or restructuring the module.")

        if not functions:
            recs.append("No functions found in this file. Consider if this file should be a module with callable logic.")

        if third_party:
            unique_packages = set(imp['module'].split('.')[0] for imp in third_party)
            if len(unique_packages) > 10:
                recs.append(f"Many third-party packages ({len(unique_packages)}). Ensure all dependencies are necessary.")

        unused_imports = self._find_unused_imports(imports, functions)
        if unused_imports:
            recs.append(f"Unused imports detected: {', '.join(unused_imports[:5])}. Remove them to improve readability.")

        if len(functions) > 30:
            recs.append("Large number of functions. Consider splitting into multiple modules by concern.")

        if not recs:
            recs.append("Good dependency structure! Consider adding type hints to improve IDE support and reduce runtime errors.")

        return recs

    def _find_unused_imports(self, imports: list[dict], functions: list[dict]) -> list[str]:
        all_imported_names = set()
        for imp in imports:
            all_imported_names.update(imp['names'])

        all_called_names = set()
        for func in functions:
            all_called_names.update(func['calls'])

        unused = []
        for imp in imports:
            for name in imp['names']:
                if name not in all_called_names and not imp['module'].startswith('_'):
                    unused.append(name)

        return list(set(unused))[:5]
