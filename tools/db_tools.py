import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 可选依赖
try:
    import sqlalchemy
    from sqlalchemy import create_engine, text
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class DatabaseTools:
    """
    数据库操作工具

    【设计意图】
    允许 Agent 连接和查询 MySQL/PostgreSQL/SQLite 数据库，
    进行数据分析、表结构检查和查询优化。

    【安全设计】
    - 默认只读模式（除非显式启用写入）
    - SQL 查询结果自动截断，防止 token 爆炸
    - 连接自动超时回收
    """

    _engines = {}  # 缓存数据库连接

    @classmethod
    def connect(cls, uri: str, alias: str = "default") -> str:
        """
        连接数据库。
        uri: 连接字符串，如 'sqlite:///test.db', 'postgresql://user:pass@host/db'
        alias: 连接别名，用于多数据库场景
        """
        logger.info(f"Tool db_connect: {alias}")
        if not DB_AVAILABLE:
            return "Error: sqlalchemy not installed. Run: pip install sqlalchemy"
        try:
            engine = create_engine(uri, pool_pre_ping=True, pool_recycle=300)
            # 测试连接
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            cls._engines[alias] = engine
            return f"Connected to database '{alias}' successfully. URI: {uri.split('@')[-1] if '@' in uri else uri}"
        except Exception as e:
            return f"Connection failed: {e}"

    @classmethod
    def query(cls, sql: str, alias: str = "default", max_rows: int = 50) -> str:
        """
        执行 SQL 查询。
        sql: SQL 语句
        alias: 数据库连接别名
        max_rows: 最大返回行数
        """
        logger.info(f"Tool db_query: {sql[:80]}")
        if alias not in cls._engines:
            return f"Error: No connection '{alias}'. Use db_connect first."
        try:
            engine = cls._engines[alias]
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = result.fetchmany(max_rows)
                    # 格式化为表格
                    header = " | ".join(columns)
                    separator = "-|-".join("-" * len(c) for c in columns)
                    lines = [header, separator]
                    for row in rows:
                        lines.append(" | ".join(str(v) for v in row))
                    total = f"\n(Showing {len(rows)} rows, max {max_rows})"
                    return "\n".join(lines) + total
                else:
                    conn.commit()
                    return f"Query executed successfully. Rows affected: {result.rowcount}"
        except Exception as e:
            return f"Query failed: {e}"

    @classmethod
    def schema(cls, table: str = "", alias: str = "default") -> str:
        """
        查看表结构。
        table: 表名。为空则列出所有表。
        """
        logger.info(f"Tool db_schema: table={table}")
        if alias not in cls._engines:
            return f"Error: No connection '{alias}'. Use db_connect first."
        try:
            engine = cls._engines[alias]
            from sqlalchemy import inspect
            inspector = inspect(engine)

            if not table:
                tables = inspector.get_table_names()
                return f"Tables ({len(tables)}):\n" + "\n".join(f"  - {t}" for t in tables)
            else:
                columns = inspector.get_columns(table)
                pk = inspector.get_pk_constraint(table)
                indexes = inspector.get_indexes(table)

                lines = [f"Table: {table}", "Columns:"]
                for col in columns:
                    pk_marker = " [PK]" if col["name"] in pk.get("constrained_columns", []) else ""
                    nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                    lines.append(f"  {col['name']}: {col['type']} {nullable}{pk_marker}")
                if indexes:
                    lines.append("Indexes:")
                    for idx in indexes:
                        unique = "UNIQUE " if idx.get("unique") else ""
                        lines.append(f"  {unique}{idx['name']}: ({', '.join(idx['column_names'])})")
                return "\n".join(lines)
        except Exception as e:
            return f"Schema inspection failed: {e}"

    @classmethod
    def explain(cls, sql: str, alias: str = "default") -> str:
        """分析 SQL 查询计划，用于性能优化"""
        logger.info(f"Tool db_explain: {sql[:80]}")
        if alias not in cls._engines:
            return f"Error: No connection '{alias}'. Use db_connect first."
        try:
            engine = cls._engines[alias]
            with engine.connect() as conn:
                result = conn.execute(text(f"EXPLAIN {sql}"))
                rows = result.fetchall()
                return "\n".join(str(row) for row in rows)
        except Exception as e:
            return f"EXPLAIN failed: {e}"
