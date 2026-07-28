from api.base_api import BaseApi


class AuthApi(BaseApi):
    def login(self, req_body: dict) -> dict:
        """
        用户登录接口
        :param req_body: 登录账号密码等参数
        :return: 原始接口响应
        """
        return self.http.post("/api/home/login/userLogin", json=req_body)