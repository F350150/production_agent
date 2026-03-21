import logging
import base64
import os
import time
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    import pyautogui
    from PIL import Image
    import io
    COMPUTER_AVAILABLE = True
except ImportError:
    COMPUTER_AVAILABLE = False

# OCR 可选依赖
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

_NOT_INSTALLED = "Error: pyautogui or PIL not installed. Run: pip install pyautogui Pillow"


def _img_to_base64(img: "Image.Image", max_width: int = 1280, quality: int = 70) -> str:
    """通用图像 → base64 JPEG 转换器"""
    if img.mode == "RGBA":
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class ComputerTools:
    """
    系统级视觉与模拟操作工具 (Computer Use Tools)

    【设计意图】
    允许大模型通过截图感知操作系统界面，并执行鼠标和键盘操作。
    实现 Anthropic 'computer use' 类似的闭环控制流程。

    【能力矩阵】
    - 截图：全屏、区域、OCR 识别、屏幕录制
    - 鼠标：移动、单击、双击、拖拽、滚轮
    - 键盘：文本输入、快捷键组合
    """

    # ========== 截图类 ==========

    @staticmethod
    def screenshot() -> dict:
        """截取当前全屏，返回 base64 图像 Block"""
        logger.info("Tool computer_screenshot")
        if not COMPUTER_AVAILABLE:
            return {"type": "text", "text": _NOT_INSTALLED}
        try:
            img = pyautogui.screenshot()
            base64_image = _img_to_base64(img)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image,
                },
            }
        except Exception as e:
            logger.error(f"computer_screenshot failed: {e}")
            return {"type": "text", "text": f"Error taking system screenshot: {e}"}

    @staticmethod
    def screenshot_region(x: int, y: int, width: int, height: int) -> dict:
        """截取屏幕指定区域 (x, y, width, height)，降低 Token 开销"""
        logger.info(f"Tool screenshot_region: ({x},{y},{width},{height})")
        if not COMPUTER_AVAILABLE:
            return {"type": "text", "text": _NOT_INSTALLED}
        try:
            img = pyautogui.screenshot(region=(x, y, width, height))
            base64_image = _img_to_base64(img, max_width=width)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image,
                },
            }
        except Exception as e:
            logger.error(f"screenshot_region failed: {e}")
            return {"type": "text", "text": f"Error: {e}"}

    @staticmethod
    def ocr_screen(region: Optional[str] = None) -> str:
        """
        截取屏幕并用 OCR 提取文字内容。
        region: 可选，格式 'x,y,w,h'，为空则全屏。
        即使 LLM 不支持视觉也能获取屏幕文字。
        """
        logger.info(f"Tool ocr_screen: region={region}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        if not OCR_AVAILABLE:
            return "Error: pytesseract not installed. Run: pip install pytesseract\nAlso need Tesseract binary: brew install tesseract"
        try:
            if region:
                parts = [int(p.strip()) for p in region.split(",")]
                img = pyautogui.screenshot(region=tuple(parts))
            else:
                img = pyautogui.screenshot()

            if img.mode == "RGBA":
                img = img.convert("RGB")
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            if not text.strip():
                return "OCR completed but no text was detected in the screenshot."
            return f"OCR Result:\n{text.strip()}"
        except Exception as e:
            logger.error(f"ocr_screen failed: {e}")
            return f"OCR failed: {e}"

    @staticmethod
    def screen_record(duration: int = 3, fps: int = 4) -> str:
        """
        录制屏幕为 GIF 动画。
        duration: 录制秒数 (默认 3 秒，最大 10 秒)
        fps: 帧率 (默认 4 fps)
        返回: 保存的 GIF 文件路径
        """
        logger.info(f"Tool screen_record: {duration}s @ {fps}fps")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        duration = min(duration, 10)  # 安全上限
        fps = min(fps, 8)
        try:
            frames = []
            interval = 1.0 / fps
            total_frames = duration * fps

            for i in range(total_frames):
                img = pyautogui.screenshot()
                if img.mode == "RGBA":
                    img = img.convert("RGB")
                # 缩放以控制 GIF 体积
                max_w = 640
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
                frames.append(img)
                time.sleep(interval)

            # 保存为 GIF
            output_path = f"/tmp/screen_record_{int(time.time())}.gif"
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=int(1000 / fps),
                loop=0,
                optimize=True,
            )
            file_size = os.path.getsize(output_path) / 1024
            return f"Screen recorded: {output_path} ({len(frames)} frames, {file_size:.0f} KB)"
        except Exception as e:
            logger.error(f"screen_record failed: {e}")
            return f"Screen recording failed: {e}"

    # ========== 鼠标类 ==========

    @staticmethod
    def mouse_move(x: int, y: int) -> str:
        """移动鼠标到屏幕指定坐标 (x, y)"""
        logger.info(f"Tool mouse_move: {x}, {y}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            pyautogui.moveTo(x, y, duration=0.2)
            return f"Moved mouse to ({x}, {y})"
        except Exception as e:
            return f"Mouse move failed: {e}"

    @staticmethod
    def mouse_click(button: str = "left") -> str:
        """点击鼠标（left / right / middle）"""
        logger.info(f"Tool mouse_click: {button}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            pyautogui.click(button=button)
            return f"Clicked mouse {button} button"
        except Exception as e:
            return f"Mouse click failed: {e}"

    @staticmethod
    def mouse_double_click(x: Optional[int] = None, y: Optional[int] = None) -> str:
        """双击鼠标。可选指定坐标 (x, y)，不指定则在当前位置双击。"""
        logger.info(f"Tool mouse_double_click: ({x}, {y})")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y)
                return f"Double-clicked at ({x}, {y})"
            else:
                pyautogui.doubleClick()
                return "Double-clicked at current position"
        except Exception as e:
            return f"Double click failed: {e}"

    @staticmethod
    def mouse_drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
        """从 (x1, y1) 拖拽到 (x2, y2)。用于拖拽文件、调整窗口大小等。"""
        logger.info(f"Tool mouse_drag: ({x1},{y1}) -> ({x2},{y2})")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            pyautogui.moveTo(x1, y1, duration=0.1)
            pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
            return f"Dragged from ({x1},{y1}) to ({x2},{y2})"
        except Exception as e:
            return f"Mouse drag failed: {e}"

    @staticmethod
    def mouse_scroll(clicks: int = -3) -> str:
        """滚动鼠标滚轮。正数向上滚动，负数向下滚动。"""
        logger.info(f"Tool mouse_scroll: {clicks}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            pyautogui.scroll(clicks)
            direction = "up" if clicks > 0 else "down"
            return f"Scrolled {direction} by {abs(clicks)} clicks"
        except Exception as e:
            return f"Mouse scroll failed: {e}"

    # ========== 键盘类 ==========

    @staticmethod
    def key_type(text: str) -> str:
        """在系统当前焦点处输入文本（逐字符打字）"""
        logger.info(f"Tool key_type: {text}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            pyautogui.write(text, interval=0.05)
            return f"Typed text into system: {text}"
        except Exception as e:
            return f"Key type failed: {e}"

    @staticmethod
    def key_combo(keys: str) -> str:
        """
        执行键盘快捷键组合。
        keys: 用 '+' 连接的按键组合，如 'cmd+c', 'ctrl+shift+f', 'alt+tab'
        支持的修饰键: cmd/command, ctrl/control, alt/option, shift
        """
        logger.info(f"Tool key_combo: {keys}")
        if not COMPUTER_AVAILABLE:
            return _NOT_INSTALLED
        try:
            # 解析按键组合
            key_list = [k.strip().lower() for k in keys.split("+")]

            # 映射常见别名到 pyautogui 按键名
            KEY_MAP = {
                "cmd": "command",
                "ctrl": "ctrl",
                "control": "ctrl",
                "alt": "alt",
                "option": "alt",
                "shift": "shift",
                "enter": "return",
                "return": "return",
                "esc": "escape",
                "escape": "escape",
                "tab": "tab",
                "space": "space",
                "delete": "delete",
                "backspace": "backspace",
                "up": "up",
                "down": "down",
                "left": "left",
                "right": "right",
            }

            mapped_keys = [KEY_MAP.get(k, k) for k in key_list]
            pyautogui.hotkey(*mapped_keys)
            return f"Executed hotkey: {keys} (mapped: {'+'.join(mapped_keys)})"
        except Exception as e:
            return f"Key combo failed: {e}"
