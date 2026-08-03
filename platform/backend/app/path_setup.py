"""
统一把项目根目录加入 sys.path，使 platform 后端可复用现有 api/db/utils/steps 模块。

平台后端代码位置：fin-api-test/platform/backend/app/
项目根目录位置：fin-api-test/   (= 本文件向上 4 级)
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 平台后端目录也加入，便于直接以 app.* 方式 import
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
