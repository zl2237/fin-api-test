"""
订单链路编排器：封装 创建→分发→暂存→提交→生成子订单→录入费用 完整链路。

设计目标：
1. 消除 test_order.py 中 6 个用例对前置链路的重复代码（每个用例都从创建写起）
2. 每个方法内部完成：读yaml → 深拷贝 → 注入order_id/bl_no → 调OrderStep → DB断言
3. 用例只需调用某个阶段方法，前置链路自动复用 OrderFlow 已有状态
4. 暴露 order_id / bl_no 等状态字段，供用例做额外断言

用例改造后示例：
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.create()       # 创建订单（test_create 终态）
    flow.distribute()   # 自动复用 create 产生的 bl_no/order_id（test_distribute 终态）
    flow.stash()        # 自动复用前置链路（test_stash 终态）
    flow.submit()       # ...
    flow.generate_sub_order()
    flow.fee_add()
"""
import copy
import logging
from typing import Optional

from api.order.order_api import OrderApi
from db.biz.order_db import OrderDB
from steps.order.order_step import OrderStep
from utils.assert_util import equal, is_not_empty, not_equal
from utils.common_util import get_project_root
from utils.generator_util import generate_bl_no, generate_unique_id
from utils.yaml_util import read_yaml


class OrderFlow:
    """订单链路编排器，按阶段顺序推进订单生命周期。

    每个阶段方法会自动执行其前置阶段（幂等：已执行过则直接返回），
    用例可按需调用任意阶段，无需手写前置链路。
    """

    def __init__(self, api_factory, db_factory, env_config: dict):
        """
        :param api_factory: pytest fixture，提供 OrderApi 实例
        :param db_factory: pytest fixture，提供 OrderDB 实例
        :param env_config: pytest fixture，包含 env_name 等环境信息
        """
        self.order_api: OrderApi = api_factory.get_api(OrderApi)
        self.order_db: OrderDB = db_factory.get_db(OrderDB)
        self.order_step = OrderStep(self.order_api)
        self.env_name: str = env_config.get("env_name", "test")

        # 链路状态：随着阶段推进逐步填充
        self.bl_no: Optional[str] = None
        self.order_id: Optional[int] = None

        # 阶段执行标记（幂等控制）
        self._create_done = False
        self._distribute_done = False
        self._stash_done = False
        self._submit_done = False
        self._generate_sub_order_done = False
        self._fee_add_done = False

    # ---------- 数据加载辅助 ----------
    def _load_yaml(self, filename: str) -> dict:
        """读取当前环境下的订单 yaml 数据，返回深拷贝模板"""
        data_path = get_project_root() / f"data/{self.env_name}/order/{filename}"
        return copy.deepcopy(read_yaml(data_path))

    # ---------- 阶段1：创建订单 ----------
    def create(self) -> dict:
        """创建订单，校验落库与初始状态。已执行过则跳过。

        :return: 创建接口响应
        """
        if self._create_done:
            return {}

        create_body = self._load_yaml("create.yaml")
        if create_body["bl_no"] is None:
            create_body["bl_no"] = generate_bl_no(prefix="smoke")
        self.bl_no = create_body["bl_no"]

        resp = self.order_step.create_order(create_body)

        record = self.order_db.query_by_bl_no(self.bl_no)
        is_not_empty(record, f"数据库未查询到提单号：{self.bl_no}")
        self.order_id = record["order_id"]

        equal(record["entrust_status"], 1, "订单分发状态不一致")
        equal(record["status"], 1, "订单生效状态不一致")
        logging.info("新建成功")

        self._create_done = True
        return resp

    # ---------- 阶段2：分发订单 ----------
    def distribute(self) -> dict:
        """分发订单，自动执行 create 前置。已执行过则跳过。

        :return: 分发接口响应
        """
        self.create()
        if self._distribute_done:
            return {}

        logging.info("新建完成，开始分发")
        distribute_body = self._load_yaml("distribute.yaml")
        distribute_body["order_id"] = self.order_id
        distribute_body["bl_no"] = self.bl_no

        resp = self.order_step.distribute_order(distribute_body)

        record = self.order_db.query_by_bl_no(self.bl_no)
        equal(record["entrust_status"], 2, "订单分发状态不一致")
        equal(record["status"], 1, "订单生效状态不一致")
        logging.info("新建并分发成功")

        self._distribute_done = True
        return resp

    # ---------- 阶段3：暂存订单 ----------
    def stash(self) -> dict:
        """暂存订单，自动执行 create+distribute 前置。已执行过则跳过。

        :return: 暂存接口响应
        """
        self.distribute()
        if self._stash_done:
            return {}

        logging.info("分发完成，开始暂存")
        stash_body = self._load_yaml("stash.yaml")
        stash_body["order_id"] = self.order_id
        stash_body["bl_no"] = self.bl_no

        resp = self.order_step.stash_order(stash_body)
        logging.info("暂存成功")

        self._stash_done = True
        return resp

    # ---------- 阶段4：提交订单 ----------
    def submit(self) -> dict:
        """提交订单，自动执行 create+distribute+stash 前置。已执行过则跳过。

        :return: 提交接口响应
        """
        self.stash()
        if self._submit_done:
            return {}

        logging.info("暂存完成，开始提交")
        submit_body = self._load_yaml("submit.yaml")
        submit_body["order_id"] = self.order_id
        submit_body["bl_no"] = self.bl_no

        resp = self.order_step.submit_order(submit_body)

        record = self.order_db.query_by_bl_no(self.bl_no)
        equal(record["entrust_status"], 2, "订单分发状态不一致")
        equal(record["status"], 2, "订单生效状态不一致")
        not_equal(record["effective_time"], 0, "订单生效时间为0")
        equal(record["business_time"], record["effective_time"], "业务发生不等于订单生效时间")
        logging.info("提交成功")

        self._submit_done = True
        return resp

    # ---------- 阶段5：生成子订单 ----------
    def generate_sub_order(self) -> dict:
        """生成子订单，自动执行 create+distribute+stash+submit 前置。已执行过则跳过。

        :return: 生成子订单接口响应
        """
        self.submit()
        if self._generate_sub_order_done:
            return {}

        logging.info("提交完成，开始生成子订单")
        body = {"order_id": self.order_id}
        resp = self.order_step.generate_sub_order(body)

        record = self.order_db.query_by_bl_no(self.bl_no)
        equal(record["is_traverse"], 1, "子订单状态为未生成")
        logging.info("生成子订单成功")

        self._generate_sub_order_done = True
        return resp

    # ---------- 阶段6：录入费用 ----------
    def fee_add(self) -> dict:
        """录入订舱费用，自动执行 create+...+generate_sub_order 前置。已执行过则跳过。

        :return: 录入费用接口响应
        """
        self.generate_sub_order()
        if self._fee_add_done:
            return {}

        logging.info("生成子订单完成，开始录入订舱费用")
        fee_add_body = self._load_yaml("fee.yaml")
        fee_add_body["order_id"] = self.order_id

        # 处理对客对商费用，生成 unique_id 进行费用关联
        customer_list = fee_add_body["to_customer"]["put_amount"]["standard_list"]
        supplier_list = fee_add_body["to_supplier"]["pay_amount"]["standard_list"]
        for idx, cust_row in enumerate(customer_list):
            uid = generate_unique_id()
            cust_row["unique_id"] = uid
            if idx < len(supplier_list):
                supplier_list[idx]["unique_id"] = uid

        resp = self.order_step.fee_add(fee_add_body)

        # 校验穿行：订单费用记录应为 16 条
        rows = self.order_db.query_fee_by_order_id(self.order_id)
        equal(len(rows), 16, "订单穿行异常")
        logging.info("录入订舱费用成功")

        self._fee_add_done = True
        return resp
