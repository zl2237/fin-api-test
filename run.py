import os
import time
import sys
import pytest
from utils.common_util import get_project_root
from utils.log_util import init_logger


# 支持的 marker 列表（与 pytest.ini 中注册的一致）
_VALID_MARKERS = ["create", "distribute", "stash", "submit", "generate_sub_order", "fee_add"]


def main(marker: str = "", loop_count: int = 1):
    """
    自动化启动入口
    :param marker: 用例 marker，空字符串表示跑全部用例
    :param loop_count: 循环执行轮次
    """
    env = os.getenv("TEST_ENV", "test")
    os.environ["TEST_ENV"] = env
    scope = f"marker={marker}" if marker else "全部用例"
    print(f"====== 当前执行环境：{env} ======")
    print(f"====== 执行范围：{scope} ======")
    print(f"====== 设置循环执行 {loop_count} 轮 ======\n")

    project_root = get_project_root()

    for round_num in range(1, loop_count + 1):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = f"run_round{round_num}_{timestamp}.log"
        init_logger(log_file_name=log_filename)

        report_filename = f"report_round{round_num}_{timestamp}.html"
        report_path = str(project_root / "report" / report_filename)

        print(f"\n==========【第 {round_num}/{loop_count} 轮开始】==========")
        pytest_args = ["-vs", "./testcases", f"--html={report_path}", "--self-contained-html"]
        if marker:
            pytest_args.insert(0, f"-m {marker}")
        # pytest返回值：0=全部成功，非0存在失败
        exit_code = pytest.main(pytest_args)
        print(f"==========【第 {round_num}/{loop_count} 轮结束，退出码：{exit_code}】==========\n")


if __name__ == "__main__":
    # 使用示例：
    #   python run.py                    # 跑全部用例 1 轮
    #   python run.py fee_add            # 只跑 fee_add 用例 1 轮
    #   python run.py fee_add 5          # 只跑 fee_add 用例 5 轮
    #   python run.py "" 3               # 跑全部用例 3 轮
    marker = ""
    times = 1

    args = sys.argv[1:]
    if args:
        first = args[0]
        # 第一个参数是 marker（非数字）或循环次数（数字）
        if first.isdigit():
            times = int(first)
        elif first == '""' or first == "''":
            # 显式传空字符串表示跑全部
            pass
        else:
            if first not in _VALID_MARKERS:
                print(f"参数错误！未知 marker：{first}")
                print(f"支持的 marker：{', '.join(_VALID_MARKERS)}")
                print("用法：python run.py [marker] [循环次数]")
                sys.exit(1)
            marker = first

        # 第二个参数是循环次数
        if len(args) > 1:
            try:
                times = int(args[1])
            except ValueError:
                print("参数错误！循环次数必须为整数")
                print("用法：python run.py [marker] [循环次数]")
                sys.exit(1)

    main(marker, times)
