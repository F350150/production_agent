import logging

logger = logging.getLogger(__name__)

# Fallback 对于未安装第三方依赖库的容器处理
try:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

class WebTools:
    """
    外界环境感知工具 (Web Search & Extractor)
    
    【设计意图】
    阻止 Agent 遇到未知库的时候出现“幻觉瞎遍”。
    给它上网搜寻 StackOverflow 及阅读最新文档官网的通道，将其认知范围扩展至全量外网数据。
    """
    
    @staticmethod
    def web_search(query: str, max_results: int = 5) -> str:
        """从 DuckDuckGo 搜索隐身网页结果，逃避反爬虫系统"""
        logger.info(f"Tool web_search: {query}")
        if not WEB_AVAILABLE:
            return "Error: Web tools not installed. Please run: pip install duckduckgo-search requests beautifulsoup4"
        
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=max_results)
            
            if results is None:
                return f"Error: Search returned no results (None). DuckDuckGo might be rate-limiting or blocking the request. " \
                       f"Try a different query or wait a moment."
            
            results = list(results) # Ensure it's a list
            if not results:
                return "No search results found."
            
            out = [f"Search Results for '{query}':\n"]
            for i, res in enumerate(results):
                out.append(f"{i+1}. {res.get('title', 'No Title')}")
                out.append(f"   URL: {res.get('href', 'No URL')}")
                out.append(f"   Snippet: {res.get('body', 'No Snippet')}\n")
            return "\n".join(out)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Search failed: {e}. Check your internet connection or try again later."

    @staticmethod
    def fetch_url(url: str) -> str:
        """
        将目标网页进行抓取并在内部净化 HTML/Script 乱码。
        经过预处理提取出的纯文本返回给模型，大幅节约无用的 Token 处理开销。
        """
        logger.info(f"Tool fetch_url: {url}")
        if not WEB_AVAILABLE:
            return "Error: Web tools not installed. Please run: pip install duckduckgo-search requests beautifulsoup4"
        
        try:
            # 伪装成真实的浏览器防屏蔽
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 使用 BS4 清洗 DOM 树
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
                
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # 强硬阻断防止下发高达百万 Token 的单页维基百科导致雪崩
            max_chars = 40000
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... (truncated {len(text) - max_chars} characters) ..."
                
            return text
            
        except Exception as e:
            logger.error(f"Failed to fetch URL: {e}")
            return f"Failed to fetch {url}: {e}"
