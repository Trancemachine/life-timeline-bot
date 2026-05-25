"""阿里云函数计算 FC2.0 入口（HTTP 触发器）"""

import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.bot import app


def handler(environ, start_response, context):
    """WSGI 风格 handler，Flask 直接适配"""
    return app.wsgi_app(environ, start_response)
