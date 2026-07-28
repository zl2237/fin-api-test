import os
import pytest
from threading import Lock
from utils.common_util import get_project_root, init_project_dir
from utils.yaml_util import read_yaml
from utils.api_factory import ApiFactory
from utils.db_factory import DbFactory
from utils.log_util import get_logger
from api.auth_api import AuthApi
from utils.assert_util import equal, is_not_empty

logger = get_logger()
token_refresh_lock = Lock()

# 全局缓存环境配置
global_env_config = None


def pytest_configure(config):
    """会话初始化，预加载环境配置"""
    global global_env_config
    init_project_dir()
    env = os.getenv("TEST_ENV", "test")
    cfg_path = get_project_root() / f"config/env_{env}.yaml"
    global_env_config = read_yaml(cfg_path)


@pytest.fixture(scope="session")
def env_config():
    """会话级环境配置"""
    return global_env_config


@pytest.fixture(scope="session")
def api_factory(env_config):
    """会话级API工厂"""
    base_url = env_config["base_url"]
    headers = env_config.get("common_headers", {})
    factory = ApiFactory(base_url=base_url, base_headers=headers)
    return factory


@pytest.fixture(scope="session")
def login_token(api_factory, env_config):
    """
    会话登录 + Token自动刷新回调
    """
    env_name = env_config.get("env_name", "test")
    login_data_path = get_project_root() / f"data/{env_name}/auth/auth_data.yaml"
    login_data = read_yaml(login_data_path)
    login_body = login_data["login_admin"]

    def refresh_token_func():
        with token_refresh_lock:
            auth_api: AuthApi = api_factory.get_api(AuthApi)
            auth_api.http.set_header("Authorization", "temp_placeholder")

            resp = auth_api.login(login_body)
            equal(resp["code"], 200, "自动刷新Token失败，登录返回业务码非200")
            new_token = resp["data"]["token"]
            is_not_empty(new_token, "自动刷新Token：返回token为空")
            logger.info(f"Token自动刷新成功，新token：{new_token}")

            api_factory.update_global_header("Authorization", new_token)
            return new_token

    # 全局注册刷新回调
    api_factory.set_global_token_refresh_callback(refresh_token_func)
    first_token = refresh_token_func()
    return first_token


@pytest.fixture(scope="session", autouse=True)
def auto_login(login_token):
    """自动登录"""
    logger.info("自动登录fixture触发，已完成全局登录，并注册Token自动刷新回调")


@pytest.fixture(scope="session")
def db_factory(env_config):
    """会话级DB工厂"""
    mysql_cfg = env_config.get("mysql", {})
    factory = DbFactory(db_config=mysql_cfg)
    yield factory
    # 会话结束关闭所有数据库连接
    for instance in factory._instance_cache.values():
        instance.db.close()


def pytest_sessionstart(session):
    """会话启动：清理临时文件、创建报告目录"""
    env = os.getenv("TEST_ENV", "test")
    download_tmp = get_project_root() / "assets" / "download_tmp"
    if download_tmp.exists():
        for f in download_tmp.iterdir():
            if f.is_file():
                f.unlink()
    report_dir = get_project_root() / "report"
    report_dir.mkdir(exist_ok=True)
    logger.info(f"测试会话启动，环境：{env}，已清空下载临时目录")


def pytest_sessionfinish(session):
    """会话结束日志"""
    logger.info("自动化测试会话执行完成")