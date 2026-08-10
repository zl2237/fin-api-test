from api.base_api import BaseApi


class OrderApi(BaseApi):
    def create_order(self, req_body: dict) -> dict:
        """
        创建订单接口
        注意：与 distribute_order 共用同一 URL，通过请求体区分业务语义
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/orderEntrust/orderAdd", json=req_body)

    def distribute_order(self, req_body: dict) -> dict:
        """
        订单分发接口
        注意：与 create_order 共用同一 URL，通过请求体区分业务语义
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/orderEntrust/orderAdd", json=req_body)

    def stash_order(self, req_body: dict) -> dict:
        """
        暂存订单接口
        注意：与 submit_order 共用同一 URL，通过请求体区分业务语义
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/order/orderAdd", json=req_body)

    def submit_order(self, req_body: dict) -> dict:
        """
        提交订单接口
        注意：与 stash_order 共用同一 URL，通过请求体区分业务语义
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/order/orderAdd", json=req_body)

    def generate_sub_order(self, req_body: dict) -> dict:
        """
        生成子订单接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/order/generateOrderSub", json=req_body)

    def fee_add(self, req_body: dict) -> dict:
        """
        编辑订舱费用接口
        :param req_body: 请求体字典
        :return: 接口原始响应dict
        """
        return self.http.post("/api/order/orderFee/bookRealAmountEdit", json=req_body)
