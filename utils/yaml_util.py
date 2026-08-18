from pathlib import Path
import yaml
from utils.log_util import get_logger

logger = get_logger()


def read_yaml(file_path: str | Path):
    """
    读取YAML文件
    :param file_path: yaml文件路径
    :return: dict / list
    """
    path = Path(file_path)
    if not path.exists():
        msg = f"YAML文件不存在：{path}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        logger.error(f"读取YAML失败，文件:{path}, error:{str(e)}")
        raise


def write_yaml(file_path: str | Path, data):
    """
    写入YAML文件，父目录不存在自动创建
    :param file_path: yaml保存路径
    :param data: 需要写入的dict/list数据
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        logger.info(f"写入YAML成功：{path}")
    except Exception as e:
        logger.error(f"写入YAML失败，文件:{path}, error:{str(e)}")
        raise
