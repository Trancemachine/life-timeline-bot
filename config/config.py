"""配置管理"""

import os
import yaml
from typing import Any


def load_config(path: str | None = None) -> dict[str, Any]:
    """加载配置，优先加载 config.yaml，fallback 到环境变量"""
    if path is None:
        path = os.environ.get(
            "TIMELINE_BOT_CONFIG",
            os.path.join(os.path.dirname(__file__), "config.yaml"),
        )

    config: dict[str, Any] = {}

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # 环境变量覆盖（适用于云函数/容器部署）
    env_overrides = {
        "app_id": "FEISHU_APP_ID",
        "app_secret": "FEISHU_APP_SECRET",
        "base_app_token": "FEISHU_BASE_TOKEN",
        "event_table_id": "FEISHU_EVENT_TABLE_ID",
        "project_table_id": "FEISHU_PROJECT_TABLE_ID",
        "calendar_id": "FEISHU_CALENDAR_ID",
    }
    for key, env_key in env_overrides.items():
        if env_val := os.environ.get(env_key):
            # 支持嵌套 key（如 server.host）
            if "." in key:
                parts = key.split(".")
                d = config
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = env_val
            else:
                config[key] = env_val

    return config


# 全局单例（惰性加载）
_config: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config
