import logging
import base64
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pyautogui
    from PIL import Image
    import io
    COMPUTER_AVAILABLE = True
except ImportError:
    COMPUTER_AVAILABLE = False

class ComputerTools:
    """
    系统级视觉与模拟操作工具 (Computer Use Tools)
    
    【设计意图】
    允许大模型通过截图感知操作系统界面，并执行鼠标和键盘操作。
    实现 Anthropic 'computer use' 类似的闭环控制流程。
    """

    @staticmethod
    def screenshot() -> dict:
        """截取当前屏幕，返回 base64 图像 Block"""
        logger.info("Tool computer_screenshot")
        if not COMPUTER_AVAILABLE:
            return {"type": "text", "text": "Error: pyautogui or PIL not installed. Run: pip install pyautogui Pillow"}
        
        try:
            # 截取全屏
            img = pyautogui.screenshot()
            
            # 缩放以降低传输开销且符合 API 建议 (推荐视口内缩放或高质量压缩)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70)
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image
                }
            }
        except Exception as e:
            logger.error(f"computer_screenshot failed: {e}")
            return {"type": "text", "text": f"Error taking system screenshot: {e}"}

    @staticmethod
    def mouse_move(x: int, y: int) -> str:
        """移动鼠标到屏幕指定坐标 (x, y)"""
        logger.info(f"Tool mouse_move: {x}, {y}")
        if not COMPUTER_AVAILABLE: return "Error: pyautogui not installed."
        try:
            pyautogui.moveTo(x, y, duration=0.2)
            return f"Moved mouse to ({x}, {y})"
        except Exception as e:
            return f"Mouse move failed: {e}"

    @staticmethod
    def mouse_click(button: str = "left") -> str:
        """点击鼠标（左键或右键）"""
        logger.info(f"Tool mouse_click: {button}")
        if not COMPUTER_AVAILABLE: return "Error: pyautogui not installed."
        try:
            pyautogui.click(button=button)
            return f"Clicked mouse {button} button"
        except Exception as e:
            return f"Mouse click failed: {e}"

    @staticmethod
    def key_type(text: str) -> str:
        """在系统当前焦点处输入文本"""
        logger.info(f"Tool key_type: {text}")
        if not COMPUTER_AVAILABLE: return "Error: pyautogui not installed."
        try:
            pyautogui.write(text, interval=0.05)
            return f"Typed text into system: {text}"
        except Exception as e:
            return f"Key type failed: {e}"
