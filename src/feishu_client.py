"""飞书 API 客户端封装"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

from config.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class FeishuClient:
    """统一封装飞书 API 调用"""

    tenant_token: str = ""
    token_expire: float = 0
    _base_url: str = "https://open.feishu.cn/open-apis"

    def __post_init__(self):
        cfg = get_config()
        self._app_id = cfg["app_id"]
        self._app_secret = cfg["app_secret"]
        self._base_token = cfg.get("base_app_token", "")

    # ── Token 管理 ──────────────────────────────────────────

    def _ensure_token(self) -> str:
        """获取或刷新 tenant_access_token"""
        if time.time() < self.token_expire - 60:
            return self.tenant_token

        resp = requests.post(
            f"{self._base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
            timeout=10,
        )
        data = resp.json()
        self.tenant_token = data["tenant_access_token"]
        self.token_expire = time.time() + data.get("expire", 7200)
        return self.tenant_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ── 语音识别 ────────────────────────────────────────────

    def speech_to_text(self, file_key: str, duration: int) -> Optional[str]:
        """飞书语音转文字"""
        url = f"{self._base_url}/speech_to_text/v1/speech/file_recognize"
        payload = {
            "speech": {"file_key": file_key},
            "config": {"file_type": "opus", "duration": duration},
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["text"]
        logger.error("语音识别失败: %s", data)
        return None

    # ── 消息发送 ────────────────────────────────────────────

    def reply_message(self, message_id: str, content: str, msg_type: str = "text"):
        """回复消息"""
        url = f"{self._base_url}/im/v1/messages/{message_id}/reply"
        payload = {
            "content": json.dumps({"text": content} if msg_type == "text" else content, ensure_ascii=False),
            "msg_type": msg_type,
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        return resp.json()

    def send_text(self, open_id: str, text: str):
        """发送文本消息"""
        url = f"{self._base_url}/im/v1/messages?receive_id_type=open_id"
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        return resp.json()

    def send_image(self, open_id: str, image_key: str):
        """发送图片消息"""
        url = f"{self._base_url}/im/v1/messages?receive_id_type=open_id"
        payload = {
            "receive_id": open_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        return resp.json()

    # ── 图片上传 ────────────────────────────────────────────

    def upload_image(self, image_data: bytes) -> Optional[str]:
        """上传图片到飞书，返回 image_key"""
        url = f"{self._base_url}/im/v1/images"
        token = self._ensure_token()
        files = {"image": ("timeline.png", image_data, "image/png")}
        data = {"image_type": "message"}
        resp = requests.post(
            url, headers={"Authorization": f"Bearer {token}"}, files=files, data=data, timeout=30
        )
        result = resp.json()
        if result.get("code") == 0:
            return result["data"]["image_key"]
        logger.error("上传图片失败: %s", result)
        return None

    # ── Base (多维表格) 操作 ─────────────────────────────────

    def base_list_records(self, table_id: str, page_size: int = 500, filter_expr: Optional[str] = None) -> list[dict]:
        """列出 Base 表中的记录"""
        url = f"{self._base_url}/bitable/v1/apps/{self._base_token}/tables/{table_id}/records"
        params = {"page_size": min(page_size, 500)}
        if filter_expr:
            params["filter"] = filter_expr

        all_records = []
        page_token = None
        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, params=params, headers=self._headers(), timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                logger.error("Base 查记录失败: %s", data)
                break
            items = data["data"]["items"]
            all_records.extend(items)
            if not data["data"].get("has_more"):
                break
            page_token = data["data"].get("page_token")

        return all_records

    def base_create_record(self, table_id: str, fields: dict[str, Any]) -> Optional[dict]:
        """在 Base 表中创建记录"""
        url = f"{self._base_url}/bitable/v1/apps/{self._base_token}/tables/{table_id}/records"
        payload = {"fields": fields}
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["record"]
        logger.error("Base 创建记录失败: %s", data)
        return None

    def base_delete_record(self, table_id: str, record_id: str) -> bool:
        """删除 Base 单条记录"""
        url = f"{self._base_url}/bitable/v1/apps/{self._base_token}/tables/{table_id}/records/{record_id}"
        resp = requests.delete(url, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            logger.info("Base 记录已删除: %s", record_id)
            return True
        logger.error("Base 删除记录失败: %s", data)
        return False

    def base_get_record(self, table_id: str, record_id: str) -> Optional[dict]:
        """获取 Base 单条记录"""
        url = f"{self._base_url}/bitable/v1/apps/{self._base_token}/tables/{table_id}/records/{record_id}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["record"]
        return None

    # ── Calendar 操作 ───────────────────────────────────────

    def create_calendar_event(
        self,
        summary: str,
        description: str,
        start_time: str,
        end_time: Optional[str] = None,
        is_all_day: bool = False,
        remind_before: Optional[int] = None,
    ):
        """创建日历事件，可选设置提醒"""
        calendar_id = get_config().get("calendar_id") or ""
        # 如果没有指定 calendar_id，查用户默认日历
        if not calendar_id:
            calendar_id = self._get_primary_calendar()

        url = f"{self._base_url}/calendar/v4/calendars/{calendar_id}/events"
        payload: dict[str, Any] = {
            "summary": summary,
            "description": description,
        }
        if remind_before:
            payload["remind"] = {"minutes": remind_before}
        if is_all_day:
            payload["start"] = {"date": start_time, "timezone": "Asia/Shanghai"}
            payload["end"] = {"date": end_time or start_time, "timezone": "Asia/Shanghai"}
            payload["is_all_day"] = True
        else:
            payload["start"] = {"date": start_time[:10], "timestamp": str(self._to_ts(start_time)), "timezone": "Asia/Shanghai"}
            payload["end"] = {
                "date": (end_time or start_time)[:10],
                "timestamp": str(self._to_ts(end_time or start_time)),
                "timezone": "Asia/Shanghai",
            }

        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]
        logger.error("创建日历事件失败: %s", data)
        return None

    def _get_primary_calendar(self) -> str:
        """获取用户主日历 ID"""
        url = f"{self._base_url}/calendar/v4/calendars/primary"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["calendar"]["calendar_id"]
        logger.error("获取主日历失败: %s", data)
        return ""

    @staticmethod
    def _to_ts(dt_str: str) -> int:
        """将日期时间字符串转为时间戳（UTC+8）"""
        from datetime import datetime, timezone, timedelta

        _tz = timezone(timedelta(hours=8))
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(dt_str, fmt).replace(tzinfo=_tz)
                return int(dt.timestamp())
            except ValueError:
                continue
        # fallback: 默认当天
        return int(datetime.now(_tz).timestamp())
