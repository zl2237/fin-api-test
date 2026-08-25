# -*- coding: utf-8 -*-
"""数据驱动测试 · 接口层自测脚本（WF-01 T10b）。

打点覆盖 spec「七、自测计划-接口层」：
datasets CRUD+导入全打、绑定执行展开、记录含 dataset_row、跨项目绑定拒、0 行拒执行。

运行：python scripts/selftest_datasets.py（需后端已启动于 127.0.0.1:8765）
"""
import sys

import requests

BASE = "http://127.0.0.1:8765/api"
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'✓' if cond else '✗'} {name}" + ("" if cond else f"  ← {detail}"))


def login():
    r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main():
    H = login()
    print("== 登录成功，开始打点 ==\n")

    # ---------- 准备：项目 ----------
    r = requests.get(f"{BASE}/projects", headers=H).json()
    proj = r[0] if r else requests.post(
        f"{BASE}/projects", json={"name": "自测项目-DDT"}, headers=H).json()
    pid = proj["id"]
    proj2 = next((p for p in requests.get(f"{BASE}/projects", headers=H).json() if p["id"] != pid), None)

    # ---------- D1 建数据集 ----------
    r = requests.post(f"{BASE}/datasets", json={
        "project_id": pid, "name": "接口自测数据集",
        "columns": [{"key": "bl_no", "label": "运单号", "type": "string"},
                    {"key": "put_amount", "type": "int"}],
    }, headers=H)
    ds = r.json()
    check("D1 建数据集 200+列定义回显", r.status_code == 200 and len(ds["columns"]) == 2, r.text)

    # D2 空列拒
    r = requests.post(f"{BASE}/datasets", json={
        "project_id": pid, "name": "坏", "columns": []}, headers=H)
    check("D2 空列定义拒 400", r.status_code == 400, r.text)

    # D3 非法列名拒
    r = requests.post(f"{BASE}/datasets", json={
        "project_id": pid, "name": "坏2", "columns": [{"key": "a.b", "type": "string"}]}, headers=H)
    check("D3 非法列名（含点）拒 400", r.status_code == 400, r.text)

    # ---------- D4-D6 行操作 ----------
    r = requests.post(f"{BASE}/datasets/{ds['id']}/rows", json={"data": {"bl_no": "BL001", "put_amount": 100}}, headers=H)
    row1 = r.json()
    check("D4 增行 200 row_index=1", r.status_code == 200 and row1["row_index"] == 1, r.text)
    requests.post(f"{BASE}/datasets/{ds['id']}/rows", json={"data": {"bl_no": "BL002", "put_amount": 200}}, headers=H)
    r = requests.post(f"{BASE}/datasets/{ds['id']}/rows", json={"data": {"bl_no": "BL003", "put_amount": 300}}, headers=H)
    check("D5 增行续号=3", r.json()["row_index"] == 3, r.text)
    r = requests.post(f"{BASE}/datasets/{ds['id']}/rows", json={"data": {"unknown_col": "x"}}, headers=H)
    check("D6 行数据未定义列拒 400", r.status_code == 400, r.text)

    # D7 改行
    r = requests.put(f"{BASE}/datasets/{ds['id']}/rows/{row1['id']}", json={"data": {"bl_no": "BL001X", "put_amount": 111}}, headers=H)
    check("D7 改行生效", r.status_code == 200 and r.json()["data"]["bl_no"] == "BL001X", r.text)

    # D8 删行重排
    r = requests.delete(f"{BASE}/datasets/{ds['id']}/rows/{row1['id']}", headers=H)
    rows = requests.get(f"{BASE}/datasets/{ds['id']}/rows", headers=H).json()
    check("D8 删行后重排 1..2", [x["row_index"] for x in rows] == [1, 2], str(rows))

    # ---------- D9-D11 导入 ----------
    csv_bytes = "bl_no,put_amount\r\nIMP001,10\r\nIMP002,20\r\nIMP003,30\r\n".encode("utf-8")
    r = requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                      params={"preview": "true"}, files={"file": ("data.csv", csv_bytes, "text/csv")})
    pv = r.json()
    check("D9 CSV 导入预览 3 行", r.status_code == 200 and pv["count"] == 3 and pv["preview"] is True, r.text)
    r = requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                      files={"file": ("data.csv", csv_bytes, "text/csv")})
    rows = requests.get(f"{BASE}/datasets/{ds['id']}/rows", headers=H).json()
    check("D10 导入落库整体替换 3 行", len(rows) == 3 and rows[0]["data"]["bl_no"] == "IMP001", str(rows))
    bom_bytes = "bl_no,put_amount\r\nBOM001,1\r\n".encode("utf-8-sig")
    r = requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                      files={"file": ("bom.csv", bom_bytes, "text/csv")})
    rows = requests.get(f"{BASE}/datasets/{ds['id']}/rows", headers=H).json()
    check("D11 BOM CSV 兼容导入", r.status_code == 200 and rows[0]["data"]["bl_no"] == "BOM001", r.text)
    r = requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                      files={"file": ("bad.json", b"{}", "application/json")})
    check("D12 不支持格式拒 400", r.status_code == 400, r.text)

    # 恢复 3 行数据（导入 BOM 后只剩 1 行）
    requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                  files={"file": ("data.csv", csv_bytes, "text/csv")})

    # ---------- D13-D15 用例绑定 ----------
    r = requests.get(f"{BASE}/environments", params={"project_id": pid}, headers=H)
    envs = r.json() if r.status_code == 200 else []
    if not envs:
        # 项目无环境则自建（空配置即可触发展开链路，执行失败不影响展开断言）
        envs = [requests.post(f"{BASE}/environments", json={
            "project_id": pid, "name": "自测环境-DDT", "base_url": "http://127.0.0.1:1"}, headers=H).json()]
    env_id = envs[0]["id"]

    groups = requests.get(f"{BASE}/case-groups", params={"project_id": pid}, headers=H).json() \
        if True else []
    group_id = groups[0]["id"] if groups else None
    r = requests.post(f"{BASE}/testcases", json={
        "project_id": pid, "group_id": group_id, "name": "数据驱动接口自测用例",
        "dag_config": {"nodes": [], "edges": []}, "node_configs": [],
    }, headers=H)
    case = r.json()
    check("D13 建空用例", r.status_code == 200, r.text)

    r = requests.put(f"{BASE}/testcases/{case['id']}", json={"dataset_id": ds["id"]}, headers=H)
    check("D14 绑定数据集 200", r.status_code == 200 and r.json()["dataset_id"] == ds["id"], r.text)

    if proj2:
        r2 = requests.post(f"{BASE}/datasets", json={
            "project_id": proj2["id"], "name": "他项目数据集",
            "columns": [{"key": "x", "type": "string"}]}, headers=H)
        ds2 = r2.json()
        r = requests.put(f"{BASE}/testcases/{case['id']}", json={"dataset_id": ds2["id"]}, headers=H)
        check("D15 跨项目绑定拒 400", r.status_code == 400, r.text)
        requests.delete(f"{BASE}/datasets/{ds2['id']}", headers=H)
    else:
        print("- D15 跳过（仅一个项目）")

    # ---------- D16-D18 执行展开 ----------
    if env_id:
        r = requests.post(f"{BASE}/testcases/{case['id']}/execute",
                          json={"case_id": case["id"], "env_id": env_id}, headers=H)
        check("D16 前置 execute 200", r.status_code == 200, r.text)
        recs = requests.get(f"{BASE}/executions", params={"case_id": case["id"], "limit": 10}, headers=H).json()
        ddt_recs = [x for x in recs if x.get("dataset_id") == ds["id"]]
        check("D16 绑定执行展开 3 条记录", len(ddt_recs) == 3, f"实际 {len(ddt_recs)} 条")
        check("D17 记录含 dataset_row 快照", all(x.get("dataset_row", {}).get("row_index") in (1, 2, 3) for x in ddt_recs), str(ddt_recs[:1]))
        labels = sorted(x["dataset_row"]["label"] for x in ddt_recs)
        check("D18 label=首列值", labels == ["IMP001", "IMP002", "IMP003"], str(labels))

        # D19 单行执行（row_ids）
        rows = requests.get(f"{BASE}/datasets/{ds['id']}/rows", headers=H).json()
        r = requests.post(f"{BASE}/testcases/{case['id']}/execute",
                          json={"case_id": case["id"], "env_id": env_id, "row_ids": [rows[0]["id"]]}, headers=H)
        check("D19 选单行执行 200（row_ids 过滤）", r.status_code == 200, r.text)
    else:
        print("- D16~D19 跳过（项目无环境）")

    # D20 0 行拒
    requests.post(f"{BASE}/datasets/{ds['id']}/import", headers=H,
                  files={"file": ("one.csv", "bl_no\r\nONLY1\r\n".encode(), "text/csv")})
    requests.delete(f"{BASE}/datasets/{ds['id']}/rows", headers=H)  # 全清 → 0 行
    if env_id:
        r = requests.post(f"{BASE}/testcases/{case['id']}/execute",
                          json={"case_id": case["id"], "env_id": env_id}, headers=H)
        check("D20 数据集 0 行拒执行 400", r.status_code == 400, r.text)

    # ---------- D21-D23 列变更保护 + 删除保护 ----------
    r = requests.put(f"{BASE}/datasets/{ds['id']}", json={
        "columns": [{"key": "a", "type": "string"}]}, headers=H)
    requests.post(f"{BASE}/datasets/{ds['id']}/rows", json={"data": {"a": "1"}}, headers=H)
    r = requests.put(f"{BASE}/datasets/{ds['id']}", json={
        "columns": [{"key": "b", "type": "string"}]}, headers=H)
    check("D21 改列删列但行数据仍用 → 拒 400", r.status_code == 400, r.text)

    r = requests.delete(f"{BASE}/datasets/{ds['id']}", headers=H)
    check("D22 被用例绑定的数据集删除拒 400", r.status_code == 400, r.text)

    # 解绑后可删，级联删行
    requests.put(f"{BASE}/testcases/{case['id']}", json={"dataset_id": None}, headers=H)
    r = requests.delete(f"{BASE}/datasets/{ds['id']}", headers=H)
    check("D23 解绑后删除 200", r.status_code == 200, r.text)
    requests.delete(f"{BASE}/testcases/{case['id']}", headers=H)

    # ---------- 收尾 ----------
    print(f"\n== 结果：{len(PASSED)} passed / {len(FAILED)} failed ==")
    if FAILED:
        print("失败项：", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
