"""NLP 解析：从用户消息中提取日期时间、事件内容、项目归类"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from config.config import get_config

CURRENT_YEAR = datetime.now().year


@dataclass
class ParsedEvent:
    """解析结果"""

    date_start: str  # "2025-04-22" 或 "2025-04-22 10:00"
    date_end: Optional[str]  # "2025-04-22 12:00" 或 None
    is_all_day: bool  # 是否全天事件
    content: str  # 事件描述（去除日期前缀）
    raw_content: str  # 原始内容
    project: Optional[str]  # 匹配到的项目名
    project_confidence: float  # 匹配置信度 0-1


def parse_message(text: str) -> ParsedEvent:
    """解析用户消息，提取日期、内容和项目"""
    raw = text.strip()

    # 1. 提取日期时间
    date_start, date_end, is_all_day, rest = _extract_datetime(raw)

    # 2. 剩余文本就是事件内容
    content = rest.strip()

    # 3. 匹配项目
    project, confidence = _match_project(content)

    return ParsedEvent(
        date_start=date_start,
        date_end=date_end,
        is_all_day=is_all_day,
        content=content,
        raw_content=raw,
        project=project,
        project_confidence=confidence,
    )


def parse_timeline_query(text: str) -> Optional[str]:
    """
    判断是否是查询时间线请求。
    返回匹配到的项目名，如果不是查询请求则返回 None。
    """
    text = text.strip()

    # "查一下XX" / "查看XX" / "给出XX" / "展示XX" - 优先检查带前缀的，避免前缀被当成项目名
    m = re.search(r"(?:查[看一]?下?|看看|显示|列出|给出|展示)\s*(.+)", text)
    if m:
        candidate = m.group(1).strip()
        # 去掉尾部的"时间线"等关键词
        candidate = re.sub(r"(?:时间线|时间轴|timeline|历程|时间表)\s*$", "", candidate).strip()
        return candidate if len(candidate) <= 10 else None

    # "XX时间线" / "XX历程" / "XX时间轴" / "XXtimeline"
    m = re.search(r"(.+?)(?:时间线|时间轴|timeline|历程|时间表)", text, re.I)
    if m:
        candidate = m.group(1).strip()
        return candidate if len(candidate) <= 10 else None

    return None


def _extract_datetime(text: str) -> tuple[str, Optional[str], bool, str]:
    """
    从文本中提取日期时间和范围，返回:
    (date_start, date_end, is_all_day, rest_text)
    支持从左到右第一次出现的日期。
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rest = text

    # ── 复合时间范围：今天/昨天/前天 H点到H点 ──
    #    eg: "今天10点到12点做了X" → range 10:00-12:00, today
    m = re.match(
        r"(今天|昨天|前天|今日|昨日)\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?\s*(?:到|-|~|—|,)\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?",
        text,
    )
    if m:
        rel = m.group(1)
        ampm_start = m.group(2) or ""
        h1, mi1 = int(m.group(3)), int(m.group(4) or 0)
        ampm_end = m.group(5) or ""
        h2, mi2 = int(m.group(6)), int(m.group(7) or 0)
        base = _relative_date(rel, today)
        h1 += 12 if ampm_start in ("下午", "晚上") and h1 < 12 else 0
        h2 += 12 if ampm_end in ("下午", "晚上") and h2 < 12 else 0
        start = base.replace(hour=h1, minute=mi1)
        end = base.replace(hour=h2, minute=mi2)
        rest = text[m.end() :]
        return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"), False, rest

    # ── M.D号/月D日 H点-H点 ──
    m = re.match(
        r"(\d{1,2})[.月/](\d{1,2})日?号?\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?\s*(?:到|-|~|—|,)\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?",
        text,
    )
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        ampm_start = m.group(3) or ""
        h1, mi1 = int(m.group(4)), int(m.group(5) or 0)
        ampm_end = m.group(6) or ""
        h2, mi2 = int(m.group(7)), int(m.group(8) or 0)
        dt = datetime(CURRENT_YEAR, month, day)
        h1 += 12 if ampm_start in ("下午", "晚上") and h1 < 12 else 0
        h2 += 12 if ampm_end in ("下午", "晚上") and h2 < 12 else 0
        start = dt.replace(hour=h1, minute=mi1)
        end = dt.replace(hour=h2, minute=mi2)
        rest = text[m.end() :]
        return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"), False, rest

    # ── 今天/昨天/前天 H点 ──
    m = re.match(
        r"(今天|昨天|前天|今日|昨日)\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?",
        text,
    )
    if m:
        rel = m.group(1)
        ampm = m.group(2) or ""
        hour, minute = int(m.group(3)), int(m.group(4) or 0)
        base = _relative_date(rel, today)
        hour += 12 if ampm in ("下午", "晚上") and hour < 12 else 0
        if ampm in ("中午") and hour < 12:
            hour += 12
        dt = base.replace(hour=hour, minute=minute)
        rest = text[m.end() :]
        return dt.strftime("%Y-%m-%d %H:%M"), None, False, rest

    # ── M.D号 H点 ──
    m = re.match(
        r"(\d{1,2})[.月/](\d{1,2})日?号?\s*"
        r"(上午|下午|早上|中午|晚上)?\s*"
        r"(\d{1,2})[点:：](\d{2})?",
        text,
    )
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        ampm = m.group(3) or ""
        hour, minute = int(m.group(4)), int(m.group(5) or 0)
        dt = datetime(CURRENT_YEAR, month, day)
        hour += 12 if ampm in ("下午", "晚上") and hour < 12 else 0
        dt = dt.replace(hour=hour, minute=minute)
        rest = text[m.end() :]
        return dt.strftime("%Y-%m-%d %H:%M"), None, False, rest

    # ── M.D号（纯日期）──
    m = re.match(r"(\d{1,2})[.月/](\d{1,2})日?号?", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        dt = datetime(CURRENT_YEAR, month, day)
        rest = text[m.end() :]
        return dt.strftime("%Y-%m-%d"), None, True, rest

    # ── 今天/昨天/前天（纯日期）──
    m = re.match(r"(今天|昨天|前天|今日|昨日)", text)
    if m:
        rel = m.group(1)
        dt = _relative_date(rel, today)
        rest = text[m.end() :]
        return dt.strftime("%Y-%m-%d"), None, True, rest

    # ── 无日期 → 默认今天 ──
    return today.strftime("%Y-%m-%d"), None, True, text


def _relative_date(rel: str, today: datetime) -> datetime:
    mapping = {"今天": 0, "今日": 0, "昨天": -1, "昨日": -1, "前天": -2}
    return today + timedelta(days=mapping.get(rel, 0))


def _match_project(content: str) -> tuple[Optional[str], float]:
    """
    通过关键词匹配项目。
    返回 (project_name, confidence)，confidence 0-1
    """
    cfg = get_config()
    projects = cfg.get("projects", [])

    best_project = None
    best_score = 0.0

    for proj in projects:
        name = proj["name"]
        keywords = proj.get("keywords", [])
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if kw in content)
        if hits > 0:
            score = hits / len(keywords)
            # 开头/结尾匹配加分
            for kw in keywords:
                if content.strip().startswith(kw) or content.strip().endswith(kw):
                    score += 0.3
            if score > best_score:
                best_score = score
                best_project = name

    return best_project, min(best_score, 1.0)

# ── LLM 意图解析（新增，不干涉现有逻辑） ───────────────

def llm_parse(text: str) -> Optional[dict]:
    """调用 LLM 解析意图，返回结构化结果；LLM 不可用时返回 None"""
    try:
        from src.llm import parse as _llm_parse
        result = _llm_parse(text)
        # query 意图的项目名做关键词匹配（对齐项目配置）
        if result.get("intent") == "query":
            project = result.get("project", "")
            if project:
                cfg = get_config()
                for proj in cfg.get("projects", []):
                    name = proj["name"]
                    if name in project or project in name:
                        result["project"] = name
                        break
                    for kw in proj.get("keywords", []):
                        if kw in project:
                            result["project"] = name
                            break
                    if result.get("project") == name:
                        break
        return result
    except Exception:
        return None

def parse_delete_query(text: str) -> Optional[dict]:
    """
    判断是否是删除请求。
    返回格式:
      {"date": "2026-07-12" | None, "keywords": [...], "project": "..." | None}
    如果不是删除请求则返回 None。
    """
    text = text.strip()

    # 删除关键词
    m = re.match(
        r"(?:删除|删掉|取消|移除|抹掉)\s*(.+)?", text
    )
    if not m:
        # "把X删掉" / "把X删除" 格式
        m = re.match(r"把\s*(.+?)\s*(?:删除|删掉|移除|取消)", text)
    if not m:
        return None

    target = (m.group(1) or "").strip()
    if not target:
        # 纯"删除"不带关键词 → 删除最近一条
        return {"date": None, "keywords": [], "project": None}

    # 尝试提取日期
    date_start, _, _, rest = _extract_datetime(target)
    keywords_raw = rest.strip()

    # 清理关键词：去掉 "的记录" "记录" "的东西" 等后缀
    keywords_raw = re.sub(r"的(?:记录|事件|东西|那个|这个)?$", "", keywords_raw).strip()

    # 尝试匹配项目
    project_name = None
    project_keywords = []
    cfg = get_config()
    for proj in cfg.get("projects", []):
        name = proj["name"]
        kws = proj.get("keywords", [])
        for kw in kws:
            if kw in target:
                project_name = name
                project_keywords = kws
                break
        if project_name:
            break

    # 如果提取日期后没剩有效关键词，用原目标
    if not keywords_raw:
        keywords_raw = target

    # 生成搜索关键词：用户输入的关键词 + 项目关键词
    search_kws = []
    for kw in re.split(r'[,，、\s]+', keywords_raw):
        kw = kw.strip()
        if kw and len(kw) >= 2:
            search_kws.append(kw)
    # 补充项目关键词（如果项目已匹配且用户输入较短）
    if project_name and len(search_kws) <= 1:
        for pk in project_keywords:
            if pk not in search_kws:
                search_kws.append(pk)

    return {
        "date": date_start if date_start else None,
        "keywords": search_kws,
        "project": project_name,
    }
