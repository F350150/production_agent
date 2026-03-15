import logging
import base64
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class PlaywrightTools:
    """
    基于 Playwright 的浏览器感知工具 (Multimodal Browser Navigator)
    
    【设计意图】
    提供比单纯 fetch_url 更有深度的交互能力。
    支持截图返回、点击、输入等操作，配合多模态模型（如 Claude 3.5 Sonnet）实现视觉驱动的网页操作。
    """
    
    _browser = None
    _context = None
    _page = None
    _playwright = None

    @classmethod
    def _ensure_browser(cls):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        
        if cls._browser is None:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=True)
            cls._context = cls._browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            cls._page = cls._context.new_page()

    @staticmethod
    def browser_open(url: str) -> str:
        """打开指定 URL 并等待加载完成"""
        logger.info(f"Tool browser_open: {url}")
        try:
            PlaywrightTools._ensure_browser()
            PlaywrightTools._page.goto(url, wait_until="networkidle", timeout=30000)
            return f"Successfully opened {url}. Page title: {PlaywrightTools._page.title()}"
        except Exception as e:
            logger.error(f"browser_open failed: {e}")
            return f"Error opening URL: {e}"

    @staticmethod
    def browser_screenshot() -> dict:
        """获取当前网页的截图并返回 base64 格式，用于模型视觉算法"""
        logger.info("Tool browser_screenshot")
        try:
            PlaywrightTools._ensure_browser()
            # 截取当前视口
            screenshot_bytes = PlaywrightTools._page.screenshot(type="jpeg", quality=80)
            base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # 返回符合 Anthropic 视觉 Block 要求的格式
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image
                }
            }
        except Exception as e:
            logger.error(f"browser_screenshot failed: {e}")
            return {"type": "text", "text": f"Error taking screenshot: {e}"}

    @staticmethod
    def browser_click(selector: str) -> str:
        """点击网页上的指定元素（使用 CSS 选择器）"""
        logger.info(f"Tool browser_click: {selector}")
        try:
            PlaywrightTools._ensure_browser()
            PlaywrightTools._page.click(selector, timeout=5000)
            return f"Clicked element: {selector}"
        except Exception as e:
            return f"Failed to click {selector}: {e}"

    @staticmethod
    def browser_type(selector: str, text: str) -> str:
        """在指定输入框中输入文本"""
        logger.info(f"Tool browser_type: {selector}")
        try:
            PlaywrightTools._ensure_browser()
            PlaywrightTools._page.fill(selector, text, timeout=5000)
            return f"Typed into {selector}"
        except Exception as e:
            return f"Failed to type into {selector}: {e}"

    @staticmethod
    def browser_scroll(direction: str = "down") -> str:
        """向下或向上滚动页面内容"""
        try:
            PlaywrightTools._ensure_browser()
            if direction == "down":
                PlaywrightTools._page.evaluate("window.scrollBy(0, 500)")
            else:
                PlaywrightTools._page.evaluate("window.scrollBy(0, -500)")
            return f"Scrolled {direction}"
        except Exception as e:
            return f"Scroll failed: {e}"

    @classmethod
    def shutdown(cls):
        """关闭浏览器引擎，释放资源"""
        if cls._browser:
            cls._browser.close()
            cls._playwright.stop()
            cls._browser = None
            cls._playwright = None
