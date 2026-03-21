import logging
import base64
import os
import json
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

_NOT_INSTALLED = "Error: Playwright not installed. Run: pip install playwright && playwright install chromium"


class PlaywrightTools:
    """
    基于 Playwright 的浏览器感知工具 (Multimodal Browser Navigator)

    【设计意图】
    提供比单纯 fetch_url 更有深度的交互能力。
    支持截图、点击、输入、多标签、Cookie 管理、PDF 解析等操作，
    配合多模态模型实现视觉驱动的网页自动化。

    【能力矩阵】
    - 导航: 打开 URL, 多标签管理
    - 视觉: 截图, 全页截图
    - 交互: 点击, 输入, 滚动, 表单填充
    - 状态: Cookie 保存/加载, 登录态保持
    - 数据: PDF 提取, 下载文件, 获取页面文本
    """

    _browser = None
    _context = None
    _page = None
    _pages = []  # 多标签管理
    _active_tab = 0
    _playwright = None

    @classmethod
    def _ensure_browser(cls):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(_NOT_INSTALLED)

        if cls._browser is None:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=True)
            cls._context = cls._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                accept_downloads=True,
            )
            cls._page = cls._context.new_page()
            cls._pages = [cls._page]
            cls._active_tab = 0

    # ========== 导航 ==========

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
    def browser_new_tab(url: str = "") -> str:
        """在新标签页中打开 URL"""
        logger.info(f"Tool browser_new_tab: {url}")
        try:
            PlaywrightTools._ensure_browser()
            new_page = PlaywrightTools._context.new_page()
            PlaywrightTools._pages.append(new_page)
            PlaywrightTools._active_tab = len(PlaywrightTools._pages) - 1
            PlaywrightTools._page = new_page
            if url:
                new_page.goto(url, wait_until="networkidle", timeout=30000)
                return f"Opened new tab #{PlaywrightTools._active_tab} with {url}. Title: {new_page.title()}"
            return f"Opened new empty tab #{PlaywrightTools._active_tab}"
        except Exception as e:
            return f"New tab failed: {e}"

    @staticmethod
    def browser_switch_tab(index: int) -> str:
        """切换到指定标签页（0-indexed）"""
        logger.info(f"Tool browser_switch_tab: {index}")
        try:
            PlaywrightTools._ensure_browser()
            if 0 <= index < len(PlaywrightTools._pages):
                PlaywrightTools._active_tab = index
                PlaywrightTools._page = PlaywrightTools._pages[index]
                title = PlaywrightTools._page.title()
                return f"Switched to tab #{index}: {title}"
            return f"Error: Tab #{index} not found. Available: 0-{len(PlaywrightTools._pages)-1}"
        except Exception as e:
            return f"Switch tab failed: {e}"

    @staticmethod
    def browser_close_tab(index: int = -1) -> str:
        """关闭标签页。-1 关闭当前标签。"""
        logger.info(f"Tool browser_close_tab: {index}")
        try:
            PlaywrightTools._ensure_browser()
            idx = index if index >= 0 else PlaywrightTools._active_tab
            if len(PlaywrightTools._pages) <= 1:
                return "Cannot close the last tab."
            page = PlaywrightTools._pages.pop(idx)
            page.close()
            PlaywrightTools._active_tab = min(PlaywrightTools._active_tab, len(PlaywrightTools._pages) - 1)
            PlaywrightTools._page = PlaywrightTools._pages[PlaywrightTools._active_tab]
            return f"Closed tab #{idx}. Active tab: #{PlaywrightTools._active_tab}"
        except Exception as e:
            return f"Close tab failed: {e}"

    @staticmethod
    def browser_list_tabs() -> str:
        """列出所有打开的标签页"""
        try:
            PlaywrightTools._ensure_browser()
            lines = []
            for i, page in enumerate(PlaywrightTools._pages):
                marker = "→" if i == PlaywrightTools._active_tab else " "
                title = page.title() or "(no title)"
                url = page.url
                lines.append(f"{marker} Tab #{i}: {title} | {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"List tabs failed: {e}"

    # ========== 视觉 ==========

    @staticmethod
    def browser_screenshot() -> dict:
        """获取当前网页的截图并返回 base64 格式"""
        logger.info("Tool browser_screenshot")
        try:
            PlaywrightTools._ensure_browser()
            screenshot_bytes = PlaywrightTools._page.screenshot(type="jpeg", quality=80)
            base64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image,
                },
            }
        except Exception as e:
            logger.error(f"browser_screenshot failed: {e}")
            return {"type": "text", "text": f"Error taking screenshot: {e}"}

    @staticmethod
    def browser_full_screenshot() -> dict:
        """获取当前网页的完整页面截图（包括滚动区域）"""
        logger.info("Tool browser_full_screenshot")
        try:
            PlaywrightTools._ensure_browser()
            screenshot_bytes = PlaywrightTools._page.screenshot(
                type="jpeg", quality=70, full_page=True
            )
            base64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image,
                },
            }
        except Exception as e:
            return {"type": "text", "text": f"Full page screenshot error: {e}"}

    # ========== 交互 ==========

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

    @staticmethod
    def browser_fill_form(fields_json: str) -> str:
        """
        自动填充表单（批量）。
        fields_json: JSON 格式，如 '{"#username": "admin", "#password": "123", "#email": "a@b.com"}'
        键为 CSS selector，值为要填入的文本。
        """
        logger.info("Tool browser_fill_form")
        try:
            PlaywrightTools._ensure_browser()
            fields = json.loads(fields_json)
            results = []
            for selector, value in fields.items():
                try:
                    PlaywrightTools._page.fill(selector, str(value), timeout=3000)
                    results.append(f"✅ {selector}: filled")
                except Exception as e:
                    results.append(f"❌ {selector}: {e}")
            return "Form fill results:\n" + "\n".join(results)
        except json.JSONDecodeError:
            return "Error: Invalid JSON format for fields."
        except Exception as e:
            return f"Form fill failed: {e}"

    @staticmethod
    def browser_get_text(selector: str = "body") -> str:
        """获取页面或指定元素的纯文本内容"""
        logger.info(f"Tool browser_get_text: {selector}")
        try:
            PlaywrightTools._ensure_browser()
            text = PlaywrightTools._page.inner_text(selector, timeout=5000)
            if len(text) > 5000:
                text = text[:5000] + f"\n\n... (truncated, total {len(text)} chars)"
            return text
        except Exception as e:
            return f"Get text failed: {e}"

    # ========== Cookie / 状态管理 ==========

    @staticmethod
    def browser_save_cookies(path: str = "/tmp/browser_cookies.json") -> str:
        """保存当前浏览器 Cookie 到文件，用于保持登录态"""
        logger.info(f"Tool browser_save_cookies: {path}")
        try:
            PlaywrightTools._ensure_browser()
            cookies = PlaywrightTools._context.cookies()
            with open(path, "w") as f:
                json.dump(cookies, f, indent=2)
            return f"Saved {len(cookies)} cookies to {path}"
        except Exception as e:
            return f"Save cookies failed: {e}"

    @staticmethod
    def browser_load_cookies(path: str = "/tmp/browser_cookies.json") -> str:
        """从文件加载 Cookie，恢复登录态"""
        logger.info(f"Tool browser_load_cookies: {path}")
        try:
            PlaywrightTools._ensure_browser()
            if not os.path.exists(path):
                return f"Cookie file not found: {path}"
            with open(path, "r") as f:
                cookies = json.load(f)
            PlaywrightTools._context.add_cookies(cookies)
            return f"Loaded {len(cookies)} cookies from {path}"
        except Exception as e:
            return f"Load cookies failed: {e}"

    # ========== 数据提取 ==========

    @staticmethod
    def browser_download(url: str, save_path: str = "/tmp/") -> str:
        """下载文件到指定路径"""
        logger.info(f"Tool browser_download: {url}")
        try:
            PlaywrightTools._ensure_browser()
            with PlaywrightTools._page.expect_download(timeout=30000) as dl_info:
                PlaywrightTools._page.goto(url)
            download = dl_info.value
            filename = download.suggested_filename
            full_path = os.path.join(save_path, filename)
            download.save_as(full_path)
            file_size = os.path.getsize(full_path) / 1024
            return f"Downloaded: {full_path} ({file_size:.0f} KB)"
        except Exception as e:
            return f"Download failed: {e}"

    @staticmethod
    def browser_pdf_extract(url: str) -> str:
        """
        打开 PDF URL 并提取文本内容（通过 Playwright + PDF.js 渲染）。
        对于复杂 PDF，建议先 browser_download 然后用其他工具处理。
        """
        logger.info(f"Tool browser_pdf_extract: {url}")
        try:
            PlaywrightTools._ensure_browser()
            # 尝试用 fetch_url 风格的文本提取
            PlaywrightTools._page.goto(url, wait_until="networkidle", timeout=30000)
            # 如果浏览器直接渲染了 PDF（Chrome 内置 PDF viewer），尝试获取文本
            text = PlaywrightTools._page.evaluate("""
                () => {
                    const body = document.body;
                    if (body) return body.innerText;
                    return '';
                }
            """)
            if text and len(text.strip()) > 50:
                if len(text) > 5000:
                    text = text[:5000] + f"\n\n... (truncated, total {len(text)} chars)"
                return f"PDF text extracted:\n{text}"
            return "PDF loaded but could not extract text. Try browser_download to save it locally."
        except Exception as e:
            return f"PDF extraction failed: {e}"

    # ========== 生命周期 ==========

    @classmethod
    def shutdown(cls):
        """关闭浏览器引擎，释放资源"""
        if cls._browser:
            cls._browser.close()
            cls._playwright.stop()
            cls._browser = None
            cls._playwright = None
            cls._pages = []
            cls._active_tab = 0
