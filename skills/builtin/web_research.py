"""
内置技能：深度网络调研 (Web Research Skill)

【设计意图】
将常见的"搜索 → 抓取 → 汇总"三步流程固化为一个原子操作。
LLM 只需调用一次 use_skill(skill_name="web_research", parameters={query: "..."})，
即可获得比直接调用 web_search 更丰富的信息（包含页面正文）。

步骤：
    1. web_search(query, max_results=5)    → 取得搜索结果列表（标题 + URL + 摘要）
    2. fetch_url(url)                      → 抓取 TOP 2 结果的页面正文（并行策略）
    3. 将所有信息结构化后拼接成最终报告返回

注意：此 Skill 不依赖 LLM，全程同步执行，零额外 Token 消耗。
"""

import logging

from skills.base import Skill

logger = logging.getLogger(__name__)


class WebResearchSkill(Skill):
    """深度网络调研技能：搜索 → 抓取页面 → 汇总结果"""

    name = "web_research"
    description = (
        "Perform deep web research on a topic: search DuckDuckGo, "
        "fetch the top pages' full content, and return a comprehensive report. "
        "Saves multiple tool-call round trips compared to doing it step by step."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The research topic or question to investigate."
            },
            "max_results": {
                "type": "integer",
                "description": "Number of search results to retrieve (default: 5).",
                "default": 5
            },
            "fetch_pages": {
                "type": "integer",
                "description": "How many top pages to deep-fetch for full text (default: 2).",
                "default": 2
            }
        },
        "required": ["query"]
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 5))
        fetch_pages = int(kwargs.get("fetch_pages", 2))

        if not query:
            return "Error: 'query' parameter is required for web_research skill."

        report_lines = [
            f"# 🔍 Web Research Report",
            f"**Query**: {query}",
            "",
            "## Search Results",
        ]

        # ── Step 1: 搜索 ──────────────────────────────────────────
        web_search = tool_handlers.get("web_search")
        if not web_search:
            return "Error: web_search tool is not available in this environment."

        try:
            search_output = web_search(query=query, max_results=max_results)
        except Exception as e:
            return f"Error: web_search failed — {e}"

        report_lines.append(search_output)
        report_lines.append("")

        # ── Step 2: 从搜索结果中提取 URL ────────────────────────
        # web_search 返回纯文本，调用 fetch_url 抓取正文
        fetch_url = tool_handlers.get("fetch_url")
        if fetch_url and fetch_pages > 0:
            report_lines.append("## Deep Fetched Pages")

            # 简单提取：找出 search_output 中以 http 开头的 token
            import re
            urls_found = re.findall(r'https?://[^\s\)\]\'\"]+', str(search_output))
            unique_urls = list(dict.fromkeys(urls_found))[:fetch_pages]  # 去重并限量

            for i, url in enumerate(unique_urls, 1):
                try:
                    page_content = fetch_url(url=url)
                    # 截断超长页面（避免正文过大）
                    snippet = str(page_content)[:3000]
                    report_lines.append(f"### Page {i}: {url}")
                    report_lines.append(snippet)
                    if len(str(page_content)) > 3000:
                        report_lines.append("_[content truncated at 3000 chars]_")
                    report_lines.append("")
                except Exception as e:
                    logger.warning(f"[WebResearchSkill] Failed to fetch {url}: {e}")
                    report_lines.append(f"### Page {i}: {url}")
                    report_lines.append(f"_Fetch failed: {e}_")
                    report_lines.append("")

        report_lines.append("---")
        report_lines.append("_Research completed by WebResearchSkill_")

        return "\n".join(report_lines)
