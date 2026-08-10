from db.base_db import BaseDB


class OrderDB(BaseDB):
    def query_by_bl_no(self, bl_no: str) -> dict | None:
        """
        根据提单号查询单条订单
        :param bl_no: 提单号
        :return: 订单字典，无数据返回None
        """
        sql = """
            SELECT *
            FROM sys_order WHERE bl_no = %s
        """
        return self.db.query_one(sql, args=[bl_no])

    def query_fee_by_order_id(self, order_id: int) -> list:
        """
        根据订单ID查询费用记录列表
        :param order_id: 订单ID
        :return: 费用记录列表，无数据返回空列表
        """
        sql = """
               SELECT *
               FROM sys_order_fee_real WHERE order_id = %s
           """
        return self.db.query(sql, args=[order_id])
