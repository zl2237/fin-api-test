def equal(actual, expect, msg: str = ""):
    """相等断言"""
    assert actual == expect, f"{msg}\n【期望值】{expect}\n【实际值】{actual}"


def not_equal(actual, expect, msg: str = ""):
    """不相等断言"""
    assert actual != expect, f"{msg}\n【禁止等于的值】{expect}\n【实际值】{actual}"


def is_not_empty(val, msg: str = ""):
    """非空校验：不为None、非空白字符串、非空列表/字典"""
    assert val is not None and str(val).strip() != "" and val != [] and val != {}, f"{msg} 值为空\n【实际值】{val}"


def is_empty(val, msg: str = ""):
    """为空校验：None / 空字符串 / 空列表 / 空字典"""
    assert val is None or str(val).strip() == "" or val == [] or val == {}, f"{msg} 预期为空\n【实际值】{val}"


def greater(actual, expect, msg: str = ""):
    """大于 actual > expect"""
    assert actual > expect, f"{msg}\n【预期大于】{expect}\n【实际值】{actual}"


def greater_or_equal(actual, expect, msg: str = ""):
    """大于等于 actual >= expect"""
    assert actual >= expect, f"{msg}\n【预期大于等于】{expect}\n【实际值】{actual}"


def less(actual, expect, msg: str = ""):
    """小于 actual < expect"""
    assert actual < expect, f"{msg}\n【预期小于】{expect}\n【实际值】{actual}"


def less_or_equal(actual, expect, msg: str = ""):
    """小于等于 actual <= expect"""
    assert actual <= expect, f"{msg}\n【预期小于等于】{expect}\n【实际值】{actual}"


def contains(actual, expect, msg: str = ""):
    """包含：字符串包含子串 / 列表包含元素"""
    assert expect in actual, f"{msg}\n【预期包含内容】{expect}\n【实际内容】{actual}"


def not_contains(actual, expect, msg: str = ""):
    """不包含"""
    assert expect not in actual, f"{msg}\n【预期不包含内容】{expect}\n【实际内容】{actual}"


def is_true(actual, msg: str = ""):
    """断言为True"""
    assert actual is True, f"{msg}\n【预期】True\n【实际值】{actual}"


def is_false(actual, msg: str = ""):
    """断言为False"""
    assert actual is False, f"{msg}\n【预期】False\n【实际值】{actual}"


def is_none(val, msg: str = ""):
    """断言为None"""
    assert val is None, f"{msg}\n【预期】None\n【实际值】{val}"


def is_not_none(val, msg: str = ""):
    """断言不为None"""
    assert val is not None, f"{msg}\n【预期不为None】\n【实际值】{val}"


def in_list(actual, expect_list: list, msg: str = ""):
    """实际值存在于预期列表中"""
    assert actual in expect_list, f"{msg}\n【预期可选范围】{expect_list}\n【实际值】{actual}"


def not_in_list(actual, expect_list: list, msg: str = ""):
    """实际值不在预期列表中"""
    assert actual not in expect_list, f"{msg}\n【禁止取值范围】{expect_list}\n【实际值】{actual}"


def key_exists(data: dict, key: str, msg: str = ""):
    """字典存在指定key"""
    assert key in data, f"{msg}\n【预期存在key】{key}\n【现有keys】{list(data.keys())}"


def key_not_exists(data: dict, key: str, msg: str = ""):
    """字典不存在指定key"""
    assert key not in data, f"{msg}\n【预期不存在key】{key}\n【现有keys】{list(data.keys())}"