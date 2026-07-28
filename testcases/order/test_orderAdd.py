import copy
import logging
import pytest

from utils.yaml_util import read_yaml
from utils.common_util import get_project_root
from api.order.orderAdd_api import OrderApi
from db.biz.order_db import OrderDB
from steps.order.orderAdd_step import OrderStep
from utils.assert_util import equal, is_not_empty, not_equal
from utils.generator_util import generate_bl_no


@pytest.mark.create
def test_create(api_factory, db_factory, env_config):
    """
        创建订单
    """
    # 获取实例
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    order_step = OrderStep(order_api)

    # 读取当前环境yaml数据
    env_name = env_config.get("env_name", "test")
    data_path = get_project_root() / f"data/{env_name}/order/create.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    create_body = copy.deepcopy(data_template)
    # 如果未配置提单号，就动态生成唯一提单号
    if create_body["bl_no"] is None:
        create_body["bl_no"] = generate_bl_no(prefix="smoke")
    bl_no = create_body["bl_no"]

    # 调用创建订单接口，返回响应
    resp = order_step.create_order_step(create_body)

    # 查询数据库，校验是否落库、提取order_id
    record = order_db.query_by_bl_no(bl_no)
    is_not_empty(record, f"数据库未查询到提单号：{bl_no}")
    # 仅新建无需查询order_id
    # order_id = record["order_id"]

    # 业务断言
    equal(record["entrust_status"], 1, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")
    logging.info("新建成功")

@pytest.mark.distribute
def test_ditribute(api_factory, db_factory, env_config):
    """
        一、创建订单
    """
    # 获取实例
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    order_step = OrderStep(order_api)

    # 读取当前环境yaml数据
    env_name = env_config.get("env_name", "test")
    data_path = get_project_root() / f"data/{env_name}/order/create.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    create_body = copy.deepcopy(data_template)
    # 如果未配置提单号，就动态生成唯一提单号
    if create_body["bl_no"] is None:
        create_body["bl_no"] = generate_bl_no(prefix="smoke")
    bl_no = create_body["bl_no"]

    # 调用创建订单接口，返回响应
    resp = order_step.create_order_step(create_body)

    # 查询数据库，校验是否落库、提取order_id
    record = order_db.query_by_bl_no(bl_no)
    is_not_empty(record, f"数据库未查询到提单号：{bl_no}")
    order_id = record["order_id"]

    # 业务断言
    equal(record["entrust_status"], 1, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 二、使用order_id分发订单
    logging.info("新建完成，开始分发")
    data_path = get_project_root() / f"data/{env_name}/order/distribute.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    distribute_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    distribute_body["order_id"] = order_id
    distribute_body["bl_no"] = bl_no

    # 调用创建订单接口，返回响应
    resp = order_step.distribute_order_step(distribute_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")
    logging.info("新建并分发成功")


@pytest.mark.stash
def test_stash(api_factory, db_factory, env_config):
    """
        一、创建订单
    """
    # 获取实例
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    order_step = OrderStep(order_api)

    # 读取当前环境yaml数据
    env_name = env_config.get("env_name", "test")
    data_path = get_project_root() / f"data/{env_name}/order/create.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    create_body = copy.deepcopy(data_template)
    # 如果未配置提单号，就动态生成唯一提单号
    if create_body["bl_no"] is None:
        create_body["bl_no"] = generate_bl_no(prefix="smoke")
    bl_no = create_body["bl_no"]

    # 调用创建订单接口，返回响应
    resp = order_step.create_order_step(create_body)

    # 查询数据库，校验是否落库、提取order_id
    record = order_db.query_by_bl_no(bl_no)
    is_not_empty(record, f"数据库未查询到提单号：{bl_no}")
    order_id = record["order_id"]

    # 业务断言
    equal(record["entrust_status"], 1, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 二、使用order_id分发订单
    logging.info("新建完成，开始分发")
    data_path = get_project_root() / f"data/{env_name}/order/distribute.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    distribute_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    distribute_body["order_id"] = order_id
    distribute_body["bl_no"] = bl_no

    # 调用创建订单接口，返回响应
    resp = order_step.distribute_order_step(distribute_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 三、暂存订单
    logging.info("分发完成，开始暂存")
    data_path = get_project_root() / f"data/{env_name}/order/stash.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    stash_boody = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    stash_boody["order_id"] = order_id
    stash_boody["bl_no"] = bl_no

    # 调用暂存订单接口，返回响应
    resp = order_step.stash_order_step(stash_boody)
    logging.info("暂存成功")

@pytest.mark.submit
def test_submit(api_factory, db_factory, env_config):
    """
        一、创建订单
    """
    # 获取实例
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    order_step = OrderStep(order_api)

    # 读取当前环境yaml数据
    env_name = env_config.get("env_name", "test")
    data_path = get_project_root() / f"data/{env_name}/order/create.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    create_body = copy.deepcopy(data_template)
    # 如果未配置提单号，就动态生成唯一提单号
    if create_body["bl_no"] is None:
        create_body["bl_no"] = generate_bl_no(prefix="smoke")
    bl_no = create_body["bl_no"]

    # 调用创建订单接口，返回响应
    resp = order_step.create_order_step(create_body)

    # 查询数据库，校验是否落库、提取order_id
    record = order_db.query_by_bl_no(bl_no)
    is_not_empty(record, f"数据库未查询到提单号：{bl_no}")
    order_id = record["order_id"]

    # 业务断言
    equal(record["entrust_status"], 1, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 二、使用order_id分发订单
    logging.info("新建完成，开始分发")
    data_path = get_project_root() / f"data/{env_name}/order/distribute.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    distribute_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    distribute_body["order_id"] = order_id
    distribute_body["bl_no"] = bl_no

    # 调用创建订单接口，返回响应
    resp = order_step.distribute_order_step(distribute_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 三、暂存订单
    logging.info("分发完成，开始暂存")
    data_path = get_project_root() / f"data/{env_name}/order/stash.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    stash_boody = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    stash_boody["order_id"] = order_id
    stash_boody["bl_no"] = bl_no

    # 调用暂存订单接口，返回响应
    resp = order_step.stash_order_step(stash_boody)

    logging.info("暂存完成，开始提交")
    data_path = get_project_root() / f"data/{env_name}/order/submit.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    submit_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    submit_body["order_id"] = order_id
    submit_body["bl_no"] = bl_no

    # 调用暂存订单接口，返回响应
    resp = order_step.submit_order_step(submit_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 2, "订单生效状态不一致")
    not_equal(record["effective_time"], 0, "订单生效时间为0")
    equal(record["business_time"], record["effective_time"], "业务发生不等于订单生效时间")
    logging.info("提交成功")

@pytest.mark.generate_sub_order
def test_generate_sub_order(api_factory, db_factory, env_config):
    """
        一、创建订单
    """
    # 获取实例
    order_api = api_factory.get_api(OrderApi)
    order_db = db_factory.get_db(OrderDB)
    order_step = OrderStep(order_api)

    # 读取当前环境yaml数据
    env_name = env_config.get("env_name", "test")
    data_path = get_project_root() / f"data/{env_name}/order/create.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    create_body = copy.deepcopy(data_template)
    # 如果未配置提单号，就动态生成唯一提单号
    if create_body["bl_no"] is None:
        create_body["bl_no"] = generate_bl_no(prefix="smoke")
    bl_no = create_body["bl_no"]

    # 调用创建订单接口，返回响应
    resp = order_step.create_order_step(create_body)

    # 查询数据库，校验是否落库、提取order_id
    record = order_db.query_by_bl_no(bl_no)
    is_not_empty(record, f"数据库未查询到提单号：{bl_no}")
    order_id = record["order_id"]

    # 业务断言
    equal(record["entrust_status"], 1, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 二、使用order_id分发订单
    logging.info("新建完成，开始分发")
    data_path = get_project_root() / f"data/{env_name}/order/distribute.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    distribute_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    distribute_body["order_id"] = order_id
    distribute_body["bl_no"] = bl_no

    # 调用创建订单接口，返回响应
    resp = order_step.distribute_order_step(distribute_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 1, "订单生效状态不一致")

    # 三、暂存订单
    logging.info("分发完成，开始暂存")
    data_path = get_project_root() / f"data/{env_name}/order/stash.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    stash_boody = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    stash_boody["order_id"] = order_id
    stash_boody["bl_no"] = bl_no

    # 调用暂存订单接口，返回响应
    resp = order_step.stash_order_step(stash_boody)

    logging.info("暂存完成，开始提交")
    data_path = get_project_root() / f"data/{env_name}/order/submit.yaml"
    data_template = read_yaml(data_path)

    # 深拷贝请求模板，防止原始yaml被篡改
    submit_body = copy.deepcopy(data_template)
    # 使用新建产生的order_id分发
    submit_body["order_id"] = order_id
    submit_body["bl_no"] = bl_no

    # 调用暂存订单接口，返回响应
    resp = order_step.submit_order_step(submit_body)

    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["entrust_status"], 2, "订单分发状态不一致")
    equal(record["status"], 2, "订单生效状态不一致")
    not_equal(record["effective_time"], 0, "订单生效时间为0")
    equal(record["business_time"], record["effective_time"], "业务发生不等于订单生效时间")
    logging.info("提交完成，开始生成子订单")

    generate_sub_order_body = {}
    generate_sub_order_body["order_id"] = order_id
    resp = order_step.generate_sub_order_step(generate_sub_order_body)
    # 查询数据库，校验是否落库
    record = order_db.query_by_bl_no(bl_no)

    # 业务断言
    equal(record["is_traverse"], 1, "子订单状态为未生成")
    logging.info("生成子订单成功")