import logging
import subprocess
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 可选依赖
try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class NotifyTools:
    """
    通知推送工具

    【设计意图】
    任务完成后通过多种渠道通知用户：
    - macOS 原生通知（osascript）
    - 邮件通知（SMTP）
    - Webhook（Slack / Discord / 企业微信 / 飞书等）
    """

    @staticmethod
    def notify_macos(title: str, message: str, sound: str = "Glass") -> str:
        """
        发送 macOS 系统通知。
        title: 通知标题
        message: 通知内容
        sound: 提示音名称 (Glass, Ping, Pop, Purr 等)
        """
        logger.info(f"Tool notify_macos: {title}")
        try:
            script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return f"macOS notification failed: {result.stderr.strip()}"
            return f"macOS notification sent: [{title}] {message}"
        except Exception as e:
            return f"Notification failed: {e}"

    @staticmethod
    def notify_email(
        to: str,
        subject: str,
        body: str,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> str:
        """
        发送邮件通知。
        优先读取环境变量: SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS
        """
        logger.info(f"Tool notify_email: to={to}, subject={subject}")
        if not EMAIL_AVAILABLE:
            return "Error: email modules not available."

        server = smtp_server or os.getenv("SMTP_SERVER", "")
        port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        user = username or os.getenv("SMTP_USER", "")
        pwd = password or os.getenv("SMTP_PASS", "")

        if not server or not user:
            return "Error: SMTP not configured. Set SMTP_SERVER, SMTP_USER, SMTP_PASS environment variables."

        try:
            msg = MIMEMultipart()
            msg["From"] = user
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(server, port) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
            return f"Email sent to {to}: [{subject}]"
        except Exception as e:
            return f"Email failed: {e}"

    @staticmethod
    def notify_webhook(url: str, payload: Optional[str] = None, message: str = "") -> str:
        """
        发送 Webhook 通知（支持 Slack / Discord / 企业微信 / 飞书等）。
        url: Webhook URL
        payload: 自定义 JSON payload（字符串格式）
        message: 简单文本消息（如果未指定 payload，自动封装为 Slack 格式）
        """
        logger.info(f"Tool notify_webhook: {url[:50]}")
        if not REQUESTS_AVAILABLE:
            return "Error: requests not installed. Run: pip install requests"

        try:
            import json

            if payload:
                data = json.loads(payload)
            elif message:
                # 自动适配常见 Webhook 格式
                data = {
                    "text": message,        # Slack
                    "content": message,     # Discord
                    "msg_type": "text",     # 飞书
                    "content": {"text": message},  # 飞书嵌套格式
                }
            else:
                return "Error: either payload or message is required."

            resp = requests.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code in (200, 204):
                return f"Webhook sent successfully (HTTP {resp.status_code})"
            else:
                return f"Webhook response: HTTP {resp.status_code} - {resp.text[:200]}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON payload: {e}"
        except Exception as e:
            return f"Webhook failed: {e}"

    @staticmethod
    def notify_say(message: str, voice: str = "Samantha") -> str:
        """
        macOS 文字转语音播报（使用 say 命令）。
        voice: 语音名称，如 Samantha(英), Ting-Ting(中), Alex(英)
        """
        logger.info(f"Tool notify_say: {message[:30]}")
        try:
            result = subprocess.run(
                ["say", "-v", voice, message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return f"Say failed: {result.stderr.strip()}"
            return f"Spoken: {message} (voice: {voice})"
        except Exception as e:
            return f"Say failed: {e}"
