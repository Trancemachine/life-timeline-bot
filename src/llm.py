"""大模型 (DeepSeek) 统一意图理解 — Anthropic Messages API 格式"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger("llm")

_UTC8 = timezone(timedelta(hours=8))


def _system_prompt() -> str:
    today = datetime.now(_UTC8).strftime("%Y-%m-%d")
    yesterday = (datetime.now(_UTC8) - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before = (datetime.now(_UTC8) - timedelta(days=2)).strftime("%Y-%m-%d")
    year = datetime.now(_UTC8).year
    return f"""你是一个生活记录助手「时间线 Bot」。用户会发各种消息，你需要理解意图并返回 JSON。

核心判断规则：
- **用户说自己干了什么**（主语是"我"，描述行为）→ record
- **用户让 bot 给出/展示/查询什么**（主语是 bot，要求提供信息）→ query

【意图类型】

1. record - 记录事件
   返回格式: {{"intent":"record","events":[{{"date_start":"...","date_end":null,"is_all_day":true,"content":"...","remind":false}}]}}
   - 1.7/1月7日/1月7号 = 当年 {year}-01-07
   - 今天={today} 昨天={yesterday} 前天={day_before}
   - 下午3点=15:00 早上9点=09:00 9点半=09:30
   - 没有日期的事件默认日期为今天

2. query - 查询时间线
   关键信号词：给出、展示、查、查询、看看、时间线、历程、进度
   返回格式: {{"intent":"query","project":"..."}}
   例如 "给出考驾照的时间线" → project="考驾照"
   例如 "查一下我最近学车的记录" → project="学车"

3. delete - 删除
   返回格式: {{"intent":"delete"}} 或 {{"intent":"delete","delete_target":"..."}}

4. help - 帮助
   返回格式: {{"intent":"help"}}

5. chat - 闲聊
   返回格式: {{"intent":"chat","reply":"简短友好的回复"}}

重要：只返回 JSON，不要任何其他文字。"""


def _call_llm(text: str, max_tokens: int = 4096, timeout: int = 30, system: str = None):
    api_key = (os.environ.get("ANTHROPIC_API_KEY")
               or os.environ.get("ANRHROPIC_API_KEY")
               or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 未设置")
        return None

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": text}],
        "temperature": 0.05,
    }
    if system is not None:
        payload["system"] = system
    else:
        payload["system"] = _system_prompt()

    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json=payload,
            timeout=timeout,
        )
        data = resp.json()

        raw_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                raw_text = block.get("text", "")
                break
        return raw_text

    except requests.Timeout:
        logger.warning("LLM 调用超时")
        return None
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        return None


def _extract_json(text: str):
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", text)
    if m:
        return m.group(1)
    m = re.search(r"^[\s\S]*?(\{[\s\S]*\})[\s\S]*$", text)
    if m:
        return m.group(1)
    m = re.search(r"^[\s\S]*?(\[[\s\S]*\])[\s\S]*$", text)
    if m:
        return m.group(1)
    return text


def parse(text: str) -> dict:
    if not text or not text.strip():
        return {"intent": "chat", "reply": "嗯？"}

    raw = _call_llm(text)
    if not raw:
        return {"intent": None, "_fallback": True}

    json_str = _extract_json(raw)
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        return {"intent": None, "_fallback": True}

    intent = result.get("intent", "")

    if intent == "record":
        events = result.get("events", [])
        if not isinstance(events, list):
            events = []
        valid = []
        for ev in events:
            if isinstance(ev, dict) and ev.get("date_start") and ev.get("content"):
                content = str(ev.get("content", "")).strip()
                if content:
                    valid.append({
                        "date_start": _fix_year(str(ev["date_start"])),
                        "date_end": _fix_year(str(ev["date_end"])) if ev.get("date_end") else None,
                        "is_all_day": bool(ev.get("is_all_day", True)),
                        "content": content,
                        "remind": bool(ev.get("remind", False)),
                        "remind_before": ev.get("remind_before"),
                    })
        return {"intent": "record", "events": valid}

    if intent == "query":
        project = result.get("project", "")
        if project:
            return {"intent": "query", "project": project.strip()}

    if intent == "delete":
        delete_target = result.get("delete_target", "")
        if delete_target and isinstance(delete_target, str) and delete_target.strip():
            return {"intent": "delete", "delete_target": delete_target.strip()}
        return {"intent": "delete"}

    if intent == "help":
        return {"intent": "help"}

    if intent == "chat":
        reply = result.get("reply", "")
        if reply:
            return {"intent": "chat", "reply": reply}
        return {"intent": "chat", "reply": "嗯？有什么可以帮你的吗？"}

    return {"intent": "chat", "reply": "嗯？有什么可以帮你的吗？"}


def _fix_year(dt_str: str) -> str:
    if not dt_str:
        return dt_str
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            if dt.year <= 1971 or dt.year == 1900:
                dt = dt.replace(year=datetime.now(_UTC8).year)
                return dt.strftime(fmt)
        except ValueError:
            continue
    return dt_str
