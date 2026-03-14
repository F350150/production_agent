import logging
import ast
import re
from pathlib import Path

logger = logging.getLogger(__name__)

class ASTTools:
    """
    抽象语法树工具 (AST Tools)
    
    【设计意图】
    当工程扩展到几万行甚至几十万行时，Agent 不可能一股脑把所有代码吃进上下文（就算吃进去也很容易遗忘或耗尽资金）。
    AST 解析使得 Agent 能够不看“函数内部实现了什么”，只看“工程里声明了哪些类、方法和参数”。
    它能瞬间掌握整个架构的面貌而只用极少量的 Token。
    """
    
    @staticmethod
    def _parse_python(filepath: Path) -> str:
        """基于官方 `ast` 库抽提类的框架与接口"""
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
            out = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    out.append(f"class {node.name}:")
                    for n in node.body:
                        if isinstance(n, ast.FunctionDef):
                            args = [a.arg for a in n.args.args]
                            out.append(f"    def {n.name}({', '.join(args)}): ...")
                elif isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args]
                    out.append(f"def {node.name}({', '.join(args)}): ...")
            return "\n".join(out)
        except Exception as e:
            return f"# Could not parse Python AST: {e}"

    @staticmethod
    def _parse_cpp(filepath: Path) -> str:
        """
        基于正则简易解析 C++ 签名 (只匹配大体框架)。
        针对生产环境下的大量 C/C++ 遗留代码。
        """
        try:
            source = filepath.read_text(encoding="utf-8")
            out = []
            # 匹配类名
            for match in re.finditer(r'class\s+([A-Za-z0-9_]+)', source):
                out.append(f"class {match.group(1)} {{...}};")
            # 简化的匹配方法签名 (不含换行)
            for match in re.finditer(r'([A-Za-z0-9_:]+)\s+([A-Za-z0-9_]+)\s*\((.*?)\)\s*\{', source):
                out.append(f"{match.group(1)} {match.group(2)}({match.group(3)});")
            return "\n".join(out)
        except Exception as e:
            return f"# Could not parse CPP: {e}"

    @classmethod
    def get_repo_map(cls, path: str, workdir: Path) -> str:
        """爬取目录，提取所有源文件的语义签名总览"""
        logger.info(f"Tool get_repo_map: {path}")
        p = workdir / path
        if not p.is_dir():
            return f"Error: {path} is not a directory."
            
        repo_map = []
        files = list(p.rglob("*.py")) + list(p.rglob("*.cpp")) + list(p.rglob("*.h"))
        
        # Token 控制：拒绝爬取超大项目
        if len(files) > 100:
            return "Too many files to generate repo map (>100). Try a sub-directory."
            
        for f in files[:20]: # 强制硬截断前20个，防止超出配额
            if ".venv" in str(f) or "node_modules" in str(f):
                continue
            repo_map.append(f"\n--- {f.relative_to(workdir)} ---")
            if f.suffix == ".py":
                repo_map.append(cls._parse_python(f))
            else:
                repo_map.append(cls._parse_cpp(f))
                
        if len(files) > 20:
            repo_map.append(f"\n... (Truncated. Only showing first 20 out of {len(files)} files)")
            
        return "\n".join(repo_map)
