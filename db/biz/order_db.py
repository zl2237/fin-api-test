from db.base_db import BaseDB


class OrderDB(BaseDB):
    def query_by_bl_no(self, bl_no: str) -> dict | None:
        """
        根据提单号查询单条订单
        :param order_id: 订单编号
        :return: 订单字典，无数据返回None
        """
        sql = """
            SELECT *
            FROM sys_order WHERE bl_no = %s
        """
        return self.db.query_one(sql, args=[bl_no])

    def insert_order(self, order_data: dict) -> int:
        """
        新增订单
        :param order_data: 订单字段数据
        :return: mysql影响行数
        """
        sql = """
            INSERT INTO t_order(order_id, amount, biz_type, status, tenant_id)
            VALUES (%s, %s, %s, %s, %s)
        """
        args = [
            order_data["order_id"],
            order_data["amount"],
            order_data["biz_type"],
            order_data["status"],
            order_data["tenant_id"]
        ]
        return self.db.execute(sql, args)

    def update_status(self, order_id: str, status: int) -> int:
        """
        更新订单状态
        :param order_id: 订单编号
        :param status: 目标状态值
        :return: mysql影响行数
        """
        sql = "UPDATE t_order SET status=%s WHERE order_id=%s"
        return self.db.execute(sql, args=[status, order_id])

    def delete_order(self, order_id: str) -> int:
        """
        删除订单
        :param order_id: 订单编号
        :return: mysql影响行数
        """
        sql = "DELETE FROM t_order WHERE orderId=%s"
        return self.db.execute(sql, args=[order_id])