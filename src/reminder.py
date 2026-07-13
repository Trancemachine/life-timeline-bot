"""定时提醒模块：由 FC 定时触发器调用，检查 Base 中需要提醒的事件并推送消息"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from config.config import get_config
from src.feishu_client import FeishuClient

logger = logging.getLogger("reminder")

_UTC8 = timezone(timedelta(hours=8))


def check_and_send() -> int:
    """检查所有需要提醒的事件，发送 Bot 消息推送，返回已提醒数量"""
    cfg = get_config()
    feishu = FeishuClient()

    table_id = cfg.get("event_table_id")
    if not table_id:
        logger.warning("event_table_id 未配置")
        return 0

    # 查询全部记录
    records = feishu.base_list_records(table_id, page_size=500)
    if not records:
        return 0

    now = datetime.now(_UTC8)
    now_ms = int(now.timestamp() * 1000)
    # 提醒窗口：未来 2 分钟内
    window_end_ms = now_ms + 120 * 1000

    reminded = 0
    for rec in records:
        fields = rec.get("fields", {})
        remind = fields.get("是否提醒", "")
        remind_time = fields.get("提醒时间", 0) or 0
        user_open_id = fields.get("用户", "") or ""

        if remind != "是" or not remind_time or not user_open_id:
            continue

        # 检查是否在提醒窗口内
        if now_ms <= remind_time <= window_end_ms:
            content = fields.get("事件内容", "") or fields.get("content", "")
            start_ts = fields.get("开始时间", 0) or 0

            # 格式化开始时间
            time_str = ""
            if start_ts:
                dt = datetime.fromtimestamp(start_ts / 1000, _UTC8)
                time_str = dt.strftime("%H:%M")

            # 推送提醒消息
            msg = f"⏰ 提醒：{content}"
            if time_str:
                msg += f" 在 {time_str} 即将开始"

            feishu.send_text(user_open_id, msg)
            logger.info("已发送提醒: %s → %s", content, user_open_id)

            # 标记已提醒
            feishu.base_update_record(table_id, rec["record_id"], {"是否提醒": "否"})
            reminded += 1

    if reminded:
        logger.info("本轮共提醒 %d 条", reminded)
    return reminded
