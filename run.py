import os
import time
import pytest
from pathlib import Path
from utils.common_util import get_project_root
from utils.log_util import init_logger


def main():
    """
    自动化启动入口
    1. 生成时间戳日志、报告
    2. 初始化日志
    3. 环境变量传递
    4. 拉起pytest执行用例
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_filename = f"run_{timestamp}.log"
    # 优先初始化日志
    init_logger(log_file_name=log_filename)

    env = os.getenv("TEST_ENV", "test")
    os.environ["TEST_ENV"] = env
    print(f"====== 当前执行环境：{env} ======")

    report_filename = f"report_{timestamp}.html"
    project_root = get_project_root()
    report_path = str(project_root / "report" / report_filename)

    pytest_args = [
        "-m create",
        "-vs",
        "./testcases",
        f"--html={report_path}",
        "--self-contained-html"
    ]
    pytest.main(pytest_args)


if __name__ == "__main__":
    main()