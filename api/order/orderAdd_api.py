from api.base_api import BaseApi


class OrderApi(BaseApi):
    def create_order(self, req_body: dict) -> dict:
        """
        创建订单接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/orderEntrust/orderAdd", json=req_body)

    def distribute_order(self, req_body: dict) -> dict:
        """
        订单分发接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/orderEntrust/orderAdd", json=req_body)

    def stash_order(self, req_body: dict) -> dict:
        """
        暂存订单接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/order/orderAdd", json=req_body)

    def submit_order(self, req_body: dict) -> dict:
        """
        提交订单接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/order/orderAdd", json=req_body)
