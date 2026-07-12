"""阿里云函数计算 FC2.0 入口（HTTP 触发器）"""

import sys
import os

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
