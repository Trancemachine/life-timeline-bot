"""阿里云函数计算 FC2.0 入口
  - HTTP 触发器 → handler(environ, start_response)  WSGI
  - 定时触发器 → reminder_handler(event, context)
"""

import sys
import os
import json
import logging

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 加载本地依赖（_deps 目录由 s.yaml pre-deploy action 生成）
_deps_path = os.path.join(_root, "_deps")
if os.path.isdir(_deps_path) and _deps_path not in sys.path:
    sys.path.insert(0, _deps_path)

from src.bot import app


def handler(environ, start_response, context=None):
    """WSGI 风格 handler，Flask 直接适配"""
    return app.wsgi_app(environ, start_response)


def reminder_handler(event, context):
    """定时触发器：检查并发送事件提醒"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        from src.reminder import check_and_send
        count = check_and_send()
        return json.dumps({"code": 0, "reminded": count})
    except Exception as e:
        logging.exception("Reminder handler error")
        return json.dumps({"code": 1, "error": str(e)})
