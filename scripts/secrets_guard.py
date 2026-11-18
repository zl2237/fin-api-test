# -*- coding: utf-8 -*-
"""secrets_guard：已知敏感指纹防复发检查（2026-11-18 泄漏处置配套）。

用法：
  pre-commit 对 staged 文件自动运行；
  手动全量：python scripts/secrets_guard.py --all

黑名单 = 历史泄漏过并已/待轮换的真实值（指纹用拼接写法，避免本文件自命中）。
再次把真实口令/账号/生产地址写回仓库时会 fail；新增指纹直接往 FINGERPRINTS 加。
"""
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台中文防乱码
    sys.stdout.reconfigure(encoding="utf-8")

SELF = os.path.basename(__file__)

FINGERPRINTS = [
    "yhd" + "123456",             # SUT 旧口令（auth_data / codegen 规则，含荣洋账号）
    "182343" + "37456",           # SUT 登录手机号
    "WMzx" + "0532",              # 测试库旧口令（env_test.yaml 历史）
    "Dev%" + "%0532",             # 线上库旧口令（ops 脚本历史）
    "3d6ff" + "002-3d60-47e2",    # 企微 webhook key 前段（env_test.yaml 历史）
    "101.126." + "44.222",        # SUT 公网负载（测试）
    "124.174." + "49.162",        # SUT 公网负载（生产）
    "192.168." + "2.51",          # 线上库内网地址
    "192.168." + "22.106",        # 部署机内网地址
    "fin-tidb.21" + "eflag.com",  # 业务系统域名
]
PATTERNS = [
    # 只命中真实密钥体（PEM 头后紧跟 40+ 位 base64），放过提示文案/placeholder
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/]{40,}"),
]


def scan(path):
    try:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", "ignore")
    except OSError:
        return []
    hits = []
    for fp in FINGERPRINTS:
        if fp in text:
            hits.append("指纹 %r" % fp)
    for pat in PATTERNS:
        if pat.search(text):
            hits.append("模式 %s" % pat.pattern)
    return hits


def main():
    if "--all" in sys.argv:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout
        files = [x for x in out.splitlines() if x]
    else:
        files = sys.argv[1:]
    bad = 0
    for p in files:
        if os.path.basename(p) == SELF or not os.path.isfile(p):
            continue
        for hit in scan(p):
            print("secrets_guard: %s 命中 %s" % (p, hit))
            bad += 1
    if bad:
        print("secrets_guard: %d 处命中——真实凭据/账号/生产地址不得入库" % bad)
        sys.exit(1)
    print("secrets_guard: 通过")


if __name__ == "__main__":
    main()
