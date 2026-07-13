"""飞书 Bot 主入口 - Flask Webhook 服务"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from flask import Flask, request, jsonify

from config.config import get_config
from src.feishu_client import FeishuClient
from src.nlp import parse_message, parse_timeline_query, parse_delete_query, llm_parse, _match_project
from src.timeline import format_text_timeline, generate_timeline_image

_UTC8 = timezone(timedelta(hours=8))

# 消息去重池：message_id → 处理时间戳（同一 FC 实例内快速判重）
_processed_ids: dict[str, float] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

app = Flask(__name__)
feishu = FeishuClient()

BASE_EVENT_TABLE = None
BASE_PROJECT_TABLE = None


def _init():
    """启动时初始化 Base 表 ID"""
    global BASE_EVENT_TABLE, BASE_PROJECT_TABLE
    cfg = get_config()
    BASE_EVENT_TABLE = cfg.get("event_table_id")
    BASE_PROJECT_TABLE = cfg.get("project_table_id")


_init()


# ── 卡片/消息验证 ──────────────────────────────────────────

@app.route("/webhook/card", methods=["POST"])
def card_action():
    """处理卡片回调（保留扩展）"""
    return jsonify({"code": 0})


@app.route("/webhook/event", methods=["POST"])
def event_callback():
    """
    飞书事件订阅入口。
    处理：
      - im.message.receive_v1: 接收消息
      - url_verify: 验证
    """
    data = request.get_json(force=True, silent=True) or {}

    # URL 验证
    if data.get("type") == "url_verify":
        challenge = data.get("challenge")
        return jsonify({"challenge": challenge})

    # 消息事件
    if data.get("type") == "event_callback" and "event" in data:
        event = data["event"]
        event_type = event.get("type")

        if event_type == "im.message.receive_v1":
            return _handle_message(event)

    # 新版事件回调（v2.0+）
    header = data.get("header", {})
    if header.get("event_type") == "im.message.receive_v1":
        return _handle_message(data.get("event", {}))

    return jsonify({"code": 0})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ── 消息处理核心逻辑 ────────────────────────────────────────

def _is_duplicate(message_id: str) -> bool:
    """内存级消息去重：同一 FC 实例内 60 秒防重"""
    now = time.time()
    if message_id in _processed_ids:
        if now - _processed_ids[message_id] < 60:
            logger.info("跳过重复消息: %s", message_id)
            return True
    _processed_ids[message_id] = now
    # 定期清理超过 600 秒的旧 ID
    for mid in list(_processed_ids.keys()):
        if now - _processed_ids[mid] > 600:
            del _processed_ids[mid]
    return False


def _is_duplicate_by_content(raw_content: str, date_start: str) -> bool:
    """Base 表级去重：跨 FC 实例，用原始消息+开始时间判断是否已记录（10分钟内）"""
    if not BASE_EVENT_TABLE:
        return False
    try:
        records = feishu.base_list_records(BASE_EVENT_TABLE, page_size=50)
        raw_stripped = raw_content.strip()
        now_ms = time.time() * 1000
        for rec in records:
            fields = rec.get("fields", {})
            existing_raw = (fields.get("原始消息", "") or "").strip()
            if existing_raw == raw_stripped:
                existing_start = fields.get("开始时间", 0) or 0
                if existing_start and (now_ms - existing_start) < 600 * 1000:  # 10分钟内
                    return True
    except Exception as e:
        logger.warning("Base 去重查询失败: %s", e)
    return False


def _handle_message(event: dict) -> tuple:
    """处理收到的消息"""
    try:
        message = event.get("message", {})
        sender_obj = event.get("sender", {})
        sender = sender_obj.get("sender_id", {})
        chat_type = message.get("chat_type", "p2p")
        message_id = message.get("message_id", "")
        # 消息去重（防止 Feishu 超时重试导致重复处理）
        if _is_duplicate(message_id):
            return jsonify({"code": 0})
        message_type = message.get("message_type", "")
        open_id = sender.get("open_id", "")
        content_raw = message.get("content", "{}")

        # 跳过 bot 自己的消息（防止自回复循环）
        sender_type = sender_obj.get("sender_type", "") or ""
        if isinstance(sender_type, dict):
            sender_type = sender_type.get("type", "")
        if sender_type in ("app", "bot"):
            logger.info("跳过 bot 自身的消息")
            return jsonify({"code": 0})

        # 仅处理私聊和 mention 机器人的群聊
        if chat_type != "p2p" and not _is_mention(message, content_raw):
            return jsonify({"code": 0})

        # ── 语音消息 → 转文字 ──
        if message_type == "audio":
            content = json.loads(content_raw)
            file_key = content.get("file_key", "")
            duration = content.get("duration", 0)
            text = feishu.speech_to_text(file_key, duration)
            if not text:
                feishu.reply_message(message_id, "语音识别失败，请重试或输入文字")
                return jsonify({"code": 0})
            logger.info("语音→文字: %s", text)
        else:
            # 文本消息
            content = json.loads(content_raw)
            text = content.get("text", "").strip()
            if not text:
                return jsonify({"code": 0})

        # ── LLM 智能解析（兜底到正则） ──
        llm_result = llm_parse(text)
        if llm_result and llm_result.get("intent"):
            intent = llm_result["intent"]
            if intent == "query":
                project = llm_result.get("project", "")
                if project:
                    return _handle_timeline_query(message_id, open_id, project)
            elif intent == "chat":
                reply = llm_result.get("reply", "嗯？")
                feishu.reply_message(message_id, reply)
                return jsonify({"code": 0})
            elif intent == "help":
                feishu.reply_message(
                    message_id,
                    "发送消息即可自动记录，说「考驾照时间线」查询项目历程。",
                )
                return jsonify({"code": 0})
            elif intent == "record":
                # 使用 LLM 解析的事件数据
                events = llm_result.get("events", [])
                if events:
                    return _handle_record_event(
                        message_id, open_id, text, llm_event=events[0]
                    )

        # ── 判断是否是删除请求 ──
        delete_info = parse_delete_query(text)
        if delete_info is not None:
            return _handle_delete_event(message_id, open_id, delete_info)

        # ── 判断是否是查询时间线 ──
        project_name = parse_timeline_query(text)
        if project_name:
            return _handle_timeline_query(message_id, open_id, project_name)

        # ── 否则当作记录事件 ──
        return _handle_record_event(message_id, open_id, text)

    except Exception as e:
        logger.exception("消息处理异常")
        return jsonify({"code": 0})


def _handle_record_event(
    message_id: str, open_id: str, text: str, llm_event: dict | None = None
):
    """记录一条事件。llm_event 不为空时使用 LLM 解析的数据，否则走正则。"""
    # NLP 解析
    if llm_event:
        ev = llm_event
        from src.nlp import ParsedEvent

        parsed = ParsedEvent(
            date_start=ev.get("date_start", ""),
            date_end=ev.get("date_end"),
            is_all_day=ev.get("is_all_day", True),
            content=ev.get("content", "").strip(),
            raw_content=text,
            project=None,
            project_confidence=0.0,
            remind=ev.get("remind", False),
            remind_before=ev.get("remind_before"),
        )
        # 对 LLM 提取的内容做项目匹配
        if parsed.content:
            proj, conf = _match_project(parsed.content)
            parsed.project = proj
            parsed.project_confidence = conf
    else:
        parsed = parse_message(text)

    # 写 Base
    if BASE_EVENT_TABLE:
        # 跨实例去重：检查 Base 中是否已有相同原始消息（防止 Feishu 重试 + FC 多实例）
        if _is_duplicate_by_content(parsed.raw_content, parsed.date_start):
            logger.info("跳过已记录的重复内容: %s", parsed.raw_content[:50])
            return jsonify({"code": 0})

        fields = {
            "开始时间": _date_to_millis(parsed.date_start),
            "事件内容": parsed.content,
            "原始消息": parsed.raw_content,
        }
        if parsed.date_end:
            fields["结束时间"] = _date_to_millis(parsed.date_end)
        if parsed.remind:
            fields["是否提醒"] = "是"
            if parsed.remind_before:
                remind_ts = _date_to_millis(parsed.date_start) - parsed.remind_before * 60 * 1000
                fields["提醒时间"] = remind_ts

        record = feishu.base_create_record(BASE_EVENT_TABLE, fields)
        if record:
            logger.info("事件已记录: %s", parsed)
        else:
            feishu.reply_message(message_id, "❌ 记录失败，请稍后重试")
            return jsonify({"code": 0})

    # 写入日历
    _create_calendar_event(parsed)

    # 回复确认
    date_display = _format_dt_display(parsed.date_start)
    if parsed.date_end:
        date_display = f"{date_display} 至 {_format_dt_display(parsed.date_end)}"

    reply = (
        f"✅ 已记录\n"
        f"📅 {date_display}\n"
        f"📝 {parsed.content}"
    )
    if parsed.project:
        reply += f"\n🏷 {parsed.project}"

    feishu.reply_message(message_id, reply)
    return jsonify({"code": 0})


def _handle_delete_event(message_id: str, open_id: str, delete_info: dict):
    """处理删除事件请求"""
    if not BASE_EVENT_TABLE:
        feishu.reply_message(message_id, "❌ Base 未配置")
        return jsonify({"code": 0})

    keywords = delete_info.get("keywords", [])
    project = delete_info.get("project")
    delete_date = delete_info.get("date")

    # 查询所有记录
    records = feishu.base_list_records(BASE_EVENT_TABLE, page_size=500)

    if not records:
        feishu.reply_message(message_id, "📋 还没有任何记录呢")
        return jsonify({"code": 0})

    def _ts_to_date(ts):
        """时间戳转日期字符串 YYYY-MM-DD"""
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        return ""

    # 匹配记录
    matched = []
    is_bare_delete = not keywords and not delete_date and not project

    for rec in records:
        fields = rec.get("fields", {})
        content = fields.get("事件内容", "") or fields.get("content", "")
        raw_ts = fields.get("开始时间", 0) or 0
        date_str = _ts_to_date(raw_ts)
        rec_project = fields.get("项目标签", [])

        score = 0

        # 项目匹配
        if project:
            if rec_project:
                score += 2

        # 关键词匹配
        for kw in keywords:
            if kw in content:
                score += 1
            elif kw in date_str:
                score += 0.5

        # 日期匹配
        if delete_date and date_str:
            if date_str.startswith(delete_date[:10]):
                score += 3

        if score > 0:
            matched.append((score, rec))

    # 纯"删除"无参数 → 删最近一条
    if not matched and is_bare_delete and records:
        # 按时间降序取第一条
        sorted_recs = sorted(
            records,
            key=lambda r: r.get("fields", {}).get("开始时间", 0) or 0,
            reverse=True,
        )
        best = sorted_recs[0]
        record_id = best["record_id"]
        fields = best.get("fields", {})
        content = fields.get("事件内容", "") or fields.get("content", "")
        raw_ts = fields.get("开始时间", 0) or 0
        return _do_delete(message_id, record_id, _ts_to_date(raw_ts), content)

    if not matched:
        feishu.reply_message(
            message_id,
            "🔍 没找到匹配的记录，试试说具体点？"
            "例如「删除今天学车的记录」"
        )
        return jsonify({"code": 0})

    # 按分数降序，然后按时间降序（删除最近的优先）
    matched.sort(key=lambda x: (-x[0], -(x[1].get("fields", {}).get("开始时间", 0) or 0)))
    best = matched[0][1]
    record_id = best["record_id"]
    fields = best.get("fields", {})
    content = fields.get("事件内容", "") or fields.get("content", "")
    raw_ts = fields.get("开始时间", 0) or 0

    return _do_delete(message_id, record_id, _ts_to_date(raw_ts), content)


def _do_delete(message_id: str, record_id: str, date_str: str, content: str):
    """执行删除并回复结果"""
    success = feishu.base_delete_record(BASE_EVENT_TABLE, record_id)
    if success:
        date_display = _format_dt_display(date_str)
        feishu.reply_message(
            message_id,
            f"🗑 已删除\n📅 {date_display}\n📝 {content}"
        )
    else:
        feishu.reply_message(message_id, "❌ 删除失败，请稍后重试")

    return jsonify({"code": 0})


def _handle_timeline_query(message_id: str, open_id: str, project_name: str):
    """查询并回复项目时间线（从原始消息关键词匹配，无需项目标签）"""
    if not BASE_EVENT_TABLE:
        feishu.reply_message(message_id, "❌ Base 未配置")
        return jsonify({"code": 0})

    # 获取项目的关键词列表
    cfg = get_config()
    project_keywords: list[str] = []
    for proj in cfg.get("projects", []):
        if proj["name"] == project_name:
            project_keywords = proj.get("keywords", [])
            break

    if not project_keywords:
        project_keywords = [project_name]

    # 查出所有记录，按关键词匹配原始消息
    all_records = feishu.base_list_records(BASE_EVENT_TABLE, page_size=500)

    if not all_records:
        feishu.reply_message(
            message_id, f"📋 「{project_name}」还没有记录呢"
        )
        return jsonify({"code": 0})

    # 按关键词匹配：事件内容 / 原始消息 中包含任意关键词
    matched = []
    for rec in all_records:
        fields = rec.get("fields", {})
        content = (fields.get("事件内容", "") or fields.get("content", "") or "").strip()
        raw_msg = (fields.get("原始消息", "") or "").strip()
        for kw in project_keywords:
            if kw in content or kw in raw_msg:
                matched.append(rec)
                break

    if not matched:
        feishu.reply_message(
            message_id, f"📋 「{project_name}」还没有记录呢"
        )
        return jsonify({"code": 0})

    # 发送文字时间线
    text_timeline = format_text_timeline(project_name, matched)
    feishu.reply_message(message_id, text_timeline)

    # 尝试发送图片时间线
    img_bytes = generate_timeline_image(project_name, matched)
    if img_bytes:
        image_key = feishu.upload_image(img_bytes)
        if image_key:
            feishu.send_image(open_id, image_key)

    return jsonify({"code": 0})


# ── 辅助方法 ────────────────────────────────────────────────

def _find_or_create_project(name: str) -> Optional[str]:
    """查找或创建项目，返回 record_id"""
    if not BASE_PROJECT_TABLE:
        return None

    # 先查找
    records = feishu.base_list_records(
        BASE_PROJECT_TABLE,
        filter_expr=json.dumps(
            {"field_name": "项目名称", "operator": "is", "value": name},
            ensure_ascii=False,
        ),
    )
    if records:
        return records[0]["record_id"]

    # 不存在则创建
    record = feishu.base_create_record(
        BASE_PROJECT_TABLE, {"项目名称": name, "别名": name}
    )
    return record["record_id"] if record else None


def _find_project_record_id(name: str) -> Optional[str]:
    """查找项目记录 ID（精确匹配 + 别名匹配）"""
    if not BASE_PROJECT_TABLE:
        return None

    records = feishu.base_list_records(BASE_PROJECT_TABLE)
    for rec in records:
        fields = rec.get("fields", {})
        if fields.get("项目名称", "") == name:
            return rec["record_id"]
        # 别名匹配
        aliases = fields.get("别名", "")
        if isinstance(aliases, str) and name in aliases:
            return rec["record_id"]
        if isinstance(aliases, list) and name in aliases:
            return rec["record_id"]

    return None


def _create_calendar_event(parsed):
    """将解析结果写入飞书日历"""
    try:
        cfg = get_config()
        if not cfg.get("calendar_id"):
            # 没有配置日历 ID，跳过
            return

        summary = parsed.content[:50]
        description = f"📝 {parsed.raw_content}\n🏷 {parsed.project or '未归类'}"

        feishu.create_calendar_event(
            summary=summary,
            description=description,
            start_time=parsed.date_start,
            end_time=parsed.date_end,
            is_all_day=parsed.is_all_day,
            remind_before=parsed.remind_before if parsed.remind else None,
        )
    except Exception as e:
        logger.warning("创建日历事件失败（跳过）: %s", e)


def _format_dt_display(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.hour == 0 and dt.minute == 0:
            return f"{dt.month}月{dt.day}日"
        return f"{dt.month}月{dt.day}日 {dt.hour}:{dt.minute:02d}"
    except (ValueError, TypeError):
        return dt_str


def _date_to_millis(dt_str: str) -> int:
    """将日期字符串（如 2026-07-12 15:00）转为毫秒时间戳（UTC+8）"""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str, fmt).replace(tzinfo=_UTC8)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return int(datetime.now(_UTC8).timestamp() * 1000)


def _is_mention(message: dict, content_raw: str) -> bool:
    """判断群聊消息是否 mention 了机器人"""
    try:
        content = json.loads(content_raw)
        return "mention" in content or "mentions" in content
    except (json.JSONDecodeError, TypeError):
        return False


# ── 启动入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = get_config()
    host = cfg.get("server", {}).get("host", "0.0.0.0")
    port = cfg.get("server", {}).get("port", 8080)
    debug = os.environ.get("FLASK_ENV") == "development"

    logger.info("启动飞书记录Bot: %s:%s", host, port)
    app.run(host=host, port=port, debug=debug)
