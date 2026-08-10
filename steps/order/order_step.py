from api.order.order_api import OrderApi
from utils.assert_util import equal


class OrderStep:
    def __init__(self, order_api: OrderApi):
        """
        订单流程类
        :param order_api: 订单API实例
        """
        self.order_api = order_api

    def create_order(self, req_body: dict) -> dict:
        """
        原子步骤：创建订单
        内置硬性断言，失败终止流程
        :param req_body: 创建订单请求体
        :return: order_id 订单编号
        """
        resp = self.order_api.create_order(req_body)
        equal(resp["code"], 200, "创建订单：业务code不等于200")
        return resp

    def distribute_order(self, req_body: dict) -> dict:
        """
        原子步骤：订单分发
        :param req_body: 分发请求体
        :return: distribute_id
        """
        resp = self.order_api.distribute_order(req_body)
        equal(resp["code"], 200, "订单分发：业务code不等于200")
        return resp

    def stash_order(self, req_body: dict) -> dict:
        """
        原子步骤：暂存业务订单
        :param req_body: 提交订单请求体
        :return: 原始响应dict
        """
        resp = self.order_api.stash_order(req_body)
        equal(resp["code"], 200, "暂存订单：业务code不等于200")
        return resp

    def submit_order(self, req_body: dict) -> dict:
        """
        原子步骤：提交订单
        :param req_body: 提交订单请求体
        :return: 原始响应dict
        """
        resp = self.order_api.submit_order(req_body)
        equal(resp["code"], 200, "提交订单：业务code不等于200")
        return resp

    def generate_sub_order(self, req_body: dict) -> dict:
        """
        原子步骤：生成子订单
        :param req_body: 生成子订单请求体
        :return: 原始响应dict
        """
        resp = self.order_api.generate_sub_order(req_body)
        equal(resp["code"], 200, "生成子订单：业务code不等于200")
        return resp

    def fee_add(self, req_body: dict) -> dict:
        """
        原子步骤：录入订舱费用
        :param req_body: 录入费用请求体
        :return: 原始响应dict
        """
        resp = self.order_api.fee_add(req_body)
        equal(resp["code"], 200, "录入订舱费用：业务code不等于200")
        return resp
