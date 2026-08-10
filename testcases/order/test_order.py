import pytest

from flows.order.order_flow import OrderFlow


@pytest.mark.create
def test_create(api_factory, db_factory, env_config):
    """创建订单"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.create()


@pytest.mark.distribute
def test_distribute(api_factory, db_factory, env_config):
    """创建订单 → 分发"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.distribute()


@pytest.mark.stash
def test_stash(api_factory, db_factory, env_config):
    """创建订单 → 分发 → 暂存"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.stash()


@pytest.mark.submit
def test_submit(api_factory, db_factory, env_config):
    """创建订单 → 分发 → 暂存 → 提交"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.submit()


@pytest.mark.generate_sub_order
def test_generate_sub_order(api_factory, db_factory, env_config):
    """创建订单 → 分发 → 暂存 → 提交 → 生成子订单"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.generate_sub_order()


@pytest.mark.fee_add
def test_fee_add(api_factory, db_factory, env_config):
    """创建订单 → 分发 → 暂存 → 提交 → 生成子订单 → 录入费用"""
    flow = OrderFlow(api_factory, db_factory, env_config)
    flow.fee_add()
