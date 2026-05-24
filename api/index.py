"""Vercel 无服务器函数入口"""

import sys
import os

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.bot import app

# Vercel 需要 WSGI 处理器
handler = app
