import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 全局目录常量
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "report"
ASSETS_UPLOAD_DIR = PROJECT_ROOT / "assets" / "upload"
DOWNLOAD_TMP_DIR = PROJECT_ROOT / "assets" / "download_tmp"

# 需要自动创建的目录列表
DIR_LIST = [LOG_DIR, REPORT_DIR, ASSETS_UPLOAD_DIR, DOWNLOAD_TMP_DIR]


def get_project_root() -> Path:
    """
    获取项目根路径
    :return: 项目根路径Path对象
    """
    return PROJECT_ROOT


def init_project_dir():
    """
    初始化所有定义目录，目录不存在自动创建
    """
    for dir_path in DIR_LIST:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)


# 模块加载时自动初始化目录
init_project_dir()