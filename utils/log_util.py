import logging
from pathlib import Path
from utils.common_util import LOG_DIR


def init_logger(log_file_name: str = "run.log", level=logging.INFO) -> logging.Logger:
    """
    初始化日志：控制台 + 文件双输出
    :param log_file_name: 日志文件名
    :param level: 日志级别
    :return: logger实例
    """
    logger = logging.getLogger("api_auto")
    logger.setLevel(level)
    # 防止重复挂载handler
    if logger.handlers:
        logger.handlers.clear()

    log_path = Path(LOG_DIR) / log_file_name
    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )

    # 文件输出
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def get_logger() -> logging.Logger:
    """
    获取全局日志实例
    :return: logger实例
    """
    return logging.getLogger("api_auto")
