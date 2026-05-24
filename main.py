"""飞书记录与时间线 Bot - 入口

使用方式:
  1. 复制 config/config.example.yaml 为 config/config.yaml 并填写配置
  2. pip install -r requirements.txt
  3. python main.py
"""

import os
import sys

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.bot import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
