"""pre-commit 前端类型检查运行器（跨平台）。

pre-commit 的 local hook entry 需要可执行命令；bash 在 Windows 不可用，
故用 Python 切目录后调 npx vue-tsc --noEmit，与 CI frontend-lint 完全同口径。
"""
import subprocess
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "platform" / "frontend"

if __name__ == "__main__":
    ret = subprocess.call(
        ["npx", "vue-tsc", "--noEmit"],
        cwd=str(FRONTEND_DIR),
        shell=False if sys.platform != "win32" else True,  # Windows 下 npx 是 .cmd，需 shell
    )
    sys.exit(ret)
