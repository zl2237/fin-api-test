import os
import time
import sys
import pytest
from pathlib import Path
from utils.common_util import get_project_root
from utils.log_util import init_logger


def main(loop_count: int):
    """
    自动化启动入口
    :param loop_count: 循环执行轮次
    """
    env = os.getenv("TEST_ENV", "test")
    os.environ["TEST_ENV"] = env
    print(f"====== 当前执行环境：{env} ======")
    print(f"====== 设置循环执行 {loop_count} 轮 ======\n")

    project_root = get_project_root()

    for round_num in range(1, loop_count + 1):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = f"run_round{round_num}_{timestamp}.log"
        init_logger(log_file_name=log_filename)

        report_filename = f"report_round{round_num}_{timestamp}.html"
        report_path = str(project_root / "report" / report_filename)

        print(f"\n==========【第 {round_num}/{loop_count} 轮开始】==========")
        pytest_args = [
            "-m fee_add",
            "-vs",
            "./testcases",
            f"--html={report_path}",
            "--self-contained-html"
        ]
        # pytest返回值：0=全部成功，非0存在失败
        exit_code = pytest.main(pytest_args)
        print(f"==========【第 {round_num}/{loop_count} 轮结束，退出码：{exit_code}】==========\n")


if __name__ == "__main__":
    # 优先级：命令行参数 > 默认次数
    # 使用示例：python run.py 5  代表循环5轮
    if len(sys.argv) > 1:
        try:
            times = int(sys.argv[1])
        except ValueError:
            print("参数错误！用法：python run.py [循环次数]")
            sys.exit(1)
    else:
        # ========= 在这里直接修改默认循环次数 =========
        times = 1

    main(times)