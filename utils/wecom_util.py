import requests
from utils.log_util import get_logger

logger = get_logger()


class WeComRobot:
    def __init__(self, webhook: str):
        self.webhook = webhook

    def send_markdown(self, title: str, content: str):
        """发送markdown消息"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "content": content
            }
        }
        try:
            resp = requests.post(self.webhook, json=payload, timeout=10)
            logger.info(f"企微推送响应：{resp.text}")
            return resp.json()
        except Exception as e:
            logger.error(f"企微消息推送失败：{str(e)}")