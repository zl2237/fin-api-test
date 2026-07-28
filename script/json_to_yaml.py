import json
import yaml


def json_to_yaml(json_data, sort_keys: bool = False) -> str:
    """
    json 对象 -> yaml 字符串
    :param json_data: dict/list 字典或列表
    :param sort_keys: 是否对key排序
    :return: yaml文本
    """
    return yaml.dump(
        json_data,
        allow_unicode=True,   # 正常显示中文，不转\uxxxx
        sort_keys=sort_keys,
        default_flow_style=False
    )


def json_file_to_yaml_file(json_path: str, yaml_path: str):
    """json文件 转为 yaml文件"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    yaml_str = json_to_yaml(data)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_str)


if __name__ == "__main__":
    # # 示例1：字典转换
    # json_obj = {
    #     "client_expand_name":"李明丹tidb","client_expand_id":"40","m_delivery_type":"","customer_id":"60934","customer_name":"","receive_time_limit":"7","deposit_refund_day":"60","deposit_settlement_date":"30","service_id":"40","service_name":"李明丹tidb","sale_id":"41","sale_name":"孙奉盛","operator_id":"40","operator_name":"","customer_contact_id":"","customer_contact_name":"","main_sort":"易航道-易汇联-青岛易汇航-上海一帜","policy_id":"294732401957928960","policy_name":"陆旭阳多主体服务策略-手动选择","policy_type":"JSZX","settle_type":"1","settle_type_name":"月结","product_id":"2","product_name":"月结-延长-无保证金","deposit_type":"2","deposit_type_name":"无","period_delay_type":"1","period_delay_type_name":"延长","service_items":["booking_space"],"business_type":"1","trade_term":"","carrier":"","carrier_id":"","bl_no":"lele0727001","track_bl_no":"lele0727001","etd":"","atd":"","ship_name":"","voy":"","pol":"","pot":"","pod":"","del":"","country_name":"","airline_type":"","ocean_type":"","terms_payment":"T/T","terms_transport":"CY/CY","pay_type":"","customer_order_sn":"","terms_shipment":"","shipper":"","consignee":"","notifier":"","ship_mark":"","commodity":"","notes":"","cargo_type":"","packer":"","num":"","gross_weight":'',"bulk":'',"sea_trans_cost":"","teu":"","volume":"","volume_desc":"","order_sn":"","status":"1","sea_trans_currency":"USD","container":[],"message_board":[],"customer_file_list":[],"supplier":[{"is_manual":"","is_primary":"1","isset_fee":"0","isset_supplier":"1","order_id":"","order_supplier_id":"","service_item":"booking_space","service_item_name":"订舱","settle_object_id":"92102","settlement_date":'',"pay_time_limit":"6","supplier_id":"61224","supplier_name":"芜湖长信科技股份有限公司","supplier_pay_date":'',"supplier_period":'',"user_id":"16","user_name":"荣洋","settle_type":"1","supplier_name_clean":"芜湖长信科技股份有限公司","supplier_name_en":"test","tax_number":"913400007199042708","settle_object":"芜湖长信科技股份有限公司","settle_object_clean":"芜湖长信科技股份有限公司","settle_type_name":"月结"}],"remark":"","payment_type_name":"非确定性付款","payment_type":"2","policy_type_name":"","main_ids":"1,3,2,6","action":"submit","entrust_status":1,"order_file":[]
    # }
    # yaml_result = json_to_yaml(json_obj)
    # print(yaml_result)

    # 示例2：文件转换
    json_file_to_yaml_file("input.json", "output.yaml")