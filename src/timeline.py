"""时间线生成：文本格式 + 图片格式"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from typing import Any, Optional, Union

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from matplotlib.patches import FancyBboxPatch

    # 注册中文字体（Noto Sans SC，从项目 assets/ 目录加载）
    _font_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "assets", "NotoSansSC-Regular.ttf",
    )
    if os.path.isfile(_font_path):
        fm.fontManager.addfont(_font_path)
        _CHINESE_FONT = fm.FontProperties(fname=_font_path)
        # 设为默认字体
        plt.rcParams["font.family"] = _CHINESE_FONT.get_name()
        # 对于不支持中文的字符，fallback 到 DejaVu Sans
        plt.rcParams["font.sans-serif"] = [_CHINESE_FONT.get_name(), "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    else:
        _CHINESE_FONT = None

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def format_text_timeline(project: str, records: list[dict]) -> str:
    """
    将记录格式化为文本时间线。
    records: Base 查询结果，每个 record 有 fields 包含 date_time, content 等
    """
    if not records:
        return f"📋 「{project}」还没有记录，快去记录第一条吧！"

    lines = [f"📋 {project} 时间线", "─" * 30]

    # 按时间排序
    sorted_records = sorted(records, key=lambda r: _get_sort_key(r["fields"]))

    for i, rec in enumerate(sorted_records, 1):
        fields = rec["fields"]
        dt_raw = fields.get("开始时间", 0) or 0
        content = fields.get("事件内容", "") or fields.get("content", "")

        dt = _parse_dt(dt_raw)
        if dt:
            display = _format_dt_display(dt.isoformat())
            lines.append(f"  {display}  {content}")
        else:
            lines.append(f"  {content}")

    lines.append("─" * 30)
    lines.append(f"共 {len(records)} 条记录")

    return "\n".join(lines)


def _format_dt_display(dt_str: str) -> str:
    """将 ISO 日期格式转为中文友好显示"""
    try:
        # 尝试带时间解析
        dt = datetime.fromisoformat(dt_str)
        if dt.hour == 0 and dt.minute == 0:
            return f"{dt.month}月{dt.day}日"
        return f"{dt.month}月{dt.day}日 {dt.hour}:{dt.minute:02d}"
    except (ValueError, TypeError):
        # 纯日期
        try:
            dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
            return f"{dt.month}月{dt.day}日"
        except (ValueError, IndexError):
            return dt_str


def _get_sort_key(fields: dict) -> str:
    dt = fields.get("开始时间", 0) or 0
    # 处理飞书日期格式 (int 时间戳或字符串)
    if isinstance(dt, (int, float)):
        return datetime.fromtimestamp(dt / 1000).isoformat()
    return str(dt)


def generate_timeline_image(project: str, records: list[dict]) -> Optional[bytes]:
    """
    生成时间轴图片，返回 PNG bytes。
    如果 matplotlib 不可用则返回 None。
    """
    if not HAS_MATPLOTLIB or not records:
        return None

    # 解析数据
    events = []
    for rec in records:
        fields = rec["fields"]
        dt_raw = fields.get("开始时间", 0) or 0
        content = fields.get("事件内容", "") or fields.get("content", "")
        dt = _parse_dt(dt_raw)
        if dt:
            events.append((dt, content))

    events.sort(key=lambda x: x[0])
    if not events:
        return None

    n = len(events)

    # ── 绘图 ──
    fig, ax = plt.subplots(figsize=(10, 1.5 * n + 2))
    ax.set_xlim(0, 10)
    ax.set_ylim(-1, n + 1)
    ax.axis("off")

    # 标题
    ax.text(
        5,
        n + 0.5,
        f"[ {project} ]",
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
        color="#1a1a2e",
    )

    # 中心竖线
    ax.plot([3, 3], [-0.3, n - 0.7], color="#4a90d9", linewidth=3, zorder=1)

    for i, (dt, content) in enumerate(events):
        y = n - 1 - i

        # 圆点
        ax.scatter(3, y, s=200, color="#4a90d9", zorder=3, edgecolors="white", linewidth=2)

        # 日期标签（左侧）
        date_label = dt.strftime("%m/%d")
        if dt.hour != 0 or dt.minute != 0:
            date_label += f"\n{dt.hour}:{dt.minute:02d}"
        ax.text(
            2.6,
            y,
            date_label,
            ha="right",
            va="center",
            fontsize=11,
            color="#666",
            fontweight="bold",
        )

        # 事件内容（右侧）
        ax.text(
            3.5,
            y,
            content,
            ha="left",
            va="center",
            fontsize=12,
            color="#1a1a2e",
            wrap=True,
        )

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _parse_dt(dt_raw: Optional[Union[str, int, float]]) -> Optional[datetime]:
    if dt_raw is None:
        return None
    if isinstance(dt_raw, (int, float)):
        return datetime.fromtimestamp(dt_raw / 1000)
    try:
        return datetime.fromisoformat(str(dt_raw))
    except (ValueError, TypeError):
        try:
            return datetime.strptime(str(dt_raw)[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            return None
