"""运行时服务：构建 HTTP 客户端与登录，供 DagExecutor / 接口调试 / 环境登录测试复用。

从 DagExecutor._build_http_client / _login 提取，消除路由层对 DagExecutor 私有方法的
依赖及 _DummyCase 占位对象的重复定义。行为与原 DagExecutor 实现完全一致。
"""
import io
import time
from copy import deepcopy
from typing import Any

from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JsonPathParserError
from utils.http_client import HttpClient

from .. import path_setup  # noqa: F401  确保 utils 可导入
from .token_cache import EnvTokenCache


def _extract_by_jsonpath(data: Any, path: str) -> Any:
    try:
        matches = jsonpath_parse(path).find(data)
        return matches[0].value if matches else None
    except JsonPathParserError:
        # jsonpath 语法错误（如路径写错）
        return None
    except (IndexError, KeyError, TypeError, AttributeError):
        # 数据结构不匹配：取值越界 / 字段缺失 / 类型不支持
        return None


def build_http_client(env) -> HttpClient:
    """按 env 构建 HttpClient：base_url + common_headers（空则用默认 JSON 头）。"""
    client = HttpClient(base_url=env.base_url)
    client.headers = deepcopy(env.common_headers or {}) or {"Content-Type": "application/json"}
    return client


# ddddocr 懒加载单例：None=未初始化，False=不可用（缺失时验证码自动识别降级跳过）
_ocr_instance = None


def _get_ocr():
    """获取 ddddocr 识别器单例；包缺失/初始化失败时返回 None（调用方降级）。"""
    global _ocr_instance
    if _ocr_instance is False:
        return None
    if _ocr_instance is None:
        try:
            import ddddocr
            try:
                _ocr_instance = ddddocr.DdddOcr(show_ad=False)
            except TypeError:
                # 旧版 ddddocr 无 show_ad 参数
                _ocr_instance = ddddocr.DdddOcr()
        except Exception as e:
            print(f"[验证码] ddddocr 不可用，跳过自动识别: {e}")
            _ocr_instance = False
            return None
    return _ocr_instance


def _preprocess_captcha(content: bytes) -> bytes:
    """验证码图预处理：灰度 → 对比度拉伸 → 二值化 → 2x 放大。

    低对比度验证码（如 21eline 144×36，灰度 169~249）实测单次识别率 25%→50%。
    PIL 缺失或图损坏时原样返回（降级直读），不阻断登录。
    """
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(content)).convert("L")
        img = ImageOps.autocontrast(img)
        img = img.point(lambda p: 255 if p > 127 else 0)
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return content


def login(client: HttpClient, env) -> None:
    """按 env.login_config 配置登录并注册 token 刷新回调；未配置则跳过。

    - 登录时带占位鉴权头跳过验证码校验，成功后用真实 token 覆盖
    - 首次登录失败抛 RuntimeError（上层统一捕获记为执行失败）
    - token 共享模式（login_config.token_share_mode，默认 shared）：
      - shared：环境级共享 token（EnvTokenCache）。同环境并行执行复用一次登录，
        401 时条件重登（已被他人刷新则直接复用），消除单会话系统下的乒乓互踢
      - isolated：每执行独立登录（原行为）。多会话系统用，保留每执行独立 session

    登录方式与提交格式（login_config，均可选，向后兼容）：
    - login_mode：token（默认，提取 token 注入鉴权头）/ session（登录后靠 Cookie 会话，
      不提取 token 不注头；Cookie 由 requests.Session 自动保持到后续请求）
    - login_content_type：json（默认）/ form（x-www-form-urlencoded 表单提交）
    - login_check_jsonpath + login_check_value：session 模式可选成功校验
      （这类后台登录失败也常返回 HTTP 200，靠特征字段区分成败；两者都填才生效）

    验证码自动识别（login_config，可选）：
    - captcha_url + captcha_field：两者都填才启用。登录前经同一 Session 取验证码图
      → ddddocr OCR 识别 → 填入表单该字段后提交（同会话保证验证码与登录请求绑定）
    - captcha_retry：识别错误自动重试次数，默认 3（每次重试取新验证码图）
    - ddddocr 缺失时降级：不取图不填码，字段保持 login_body 原值
    """
    login_cfg: dict[str, Any] = env.login_config or {}
    login_path = login_cfg.get("login_path", "/api/home/login/userLogin")
    login_body = login_cfg.get("login_body")
    token_jsonpath = login_cfg.get("token_jsonpath", "$.data.token")
    auth_header_name = login_cfg.get("auth_header_name", "Authorization")
    # 鉴权头值模板：支持 ${token} 和 ${timestamp} 占位符
    # 默认 ${token}（直接注入）；可配为 Bearer ${token}、${token}_${timestamp} 等
    auth_header_value_template = login_cfg.get("auth_header_value_template") or "${token}"
    # token 共享模式：shared 默认（单会话系统防乒乓），isolated 保留独立登录
    share_mode = login_cfg.get("token_share_mode", "shared")
    login_mode = login_cfg.get("login_mode", "token")
    content_type = login_cfg.get("login_content_type", "json")
    check_jsonpath = login_cfg.get("login_check_jsonpath") or ""
    check_value = login_cfg.get("login_check_value") or ""
    captcha_url = login_cfg.get("captcha_url") or ""
    captcha_field = login_cfg.get("captcha_field") or ""
    try:
        captcha_attempts = max(1, int(login_cfg.get("captcha_retry", 3)))
    except (TypeError, ValueError):
        captcha_attempts = 3
    captcha_enabled = bool(captcha_url and captcha_field)
    if not login_body:
        return

    def _build_header_value(token: str) -> str:
        """按模板渲染鉴权头值"""
        return (auth_header_value_template
                .replace("${token}", str(token))
                .replace("${timestamp}", str(int(time.time()))))

    def _fill_captcha(form: dict[str, Any]) -> None:
        """经同一 Session 取验证码图 → ddddocr OCR → 填入表单字段。

        同会话是关键：验证码绑定 PHPSESSID，取图与提交登录必须共用 Session。
        任何失败仅打印日志降级（字段保持原值），不阻断登录流程。
        """
        ocr = _get_ocr()
        if not ocr:
            return
        try:
            img_resp = client.session.get(
                client.base_url + captcha_url, headers=dict(client.headers), timeout=20)
            if img_resp.status_code != 200:
                print(f"[验证码] 取图失败 HTTP {img_resp.status_code}")
                return
            code = (ocr.classification(_preprocess_captcha(img_resp.content)) or "").replace(" ", "").strip()
            if code:
                form[captcha_field] = code
            else:
                print("[验证码] OCR 识别结果为空")
        except Exception as e:
            print(f"[验证码] 获取/识别失败（忽略）: {e}")

    def _post_login_raw():
        """经 requests.Session 直发登录请求（绕过 HttpClient 的严格响应校验，
        适配响应非 {code:200} 约定的后台系统，如 ThinkPHP 的 {status:1}）。
        form 模式必须覆写 Content-Type：默认 JSON 头会让服务端按 JSON 解析表单体。
        每次调用独立拷贝表单并重填验证码（重试时取新图新码）。"""
        headers = dict(client.headers)
        kwargs: dict[str, Any]
        if content_type == "form":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            form = dict(login_body)
            if captcha_enabled:
                _fill_captcha(form)
            kwargs = {"data": form}
        else:
            payload = dict(login_body)
            if captcha_enabled:
                _fill_captcha(payload)
            kwargs = {"json": payload}
        return client.session.request(
            "POST", client.base_url + login_path, headers=headers, timeout=20, **kwargs)

    def _retry(attempt):
        """验证码登录重试装饰逻辑：未启用验证码时 attempt 原样返回（行为不变）。"""
        def wrapper():
            last_exc = None
            for i in range(captcha_attempts if captcha_enabled else 1):
                try:
                    return attempt()
                except Exception as e:
                    last_exc = e
                    if captcha_enabled and i < captcha_attempts - 1:
                        print(f"[验证码] 第 {i + 1} 次登录失败，取新验证码重试: {e}")
            raise last_exc
        return wrapper

    if login_mode == "session":
        # session 模式：登录成功即止，Set-Cookie 由 requests.Session 自动保持；
        # 不提取 token、不注入鉴权头，也不进共享缓存
        # （Cookie 无法跨客户端共享，每执行独立登录）
        def _attempt_login_session():
            resp = _post_login_raw()
            if resp.status_code != 200:
                raise RuntimeError(f"登录接口 HTTP {resp.status_code}: {resp.text[:200]}")
            if check_jsonpath:
                try:
                    body = resp.json()
                except Exception:
                    body = None
                actual = _extract_by_jsonpath(body, check_jsonpath)
                ok = (actual is not None) if not check_value else (str(actual) == str(check_value))
                if not ok:
                    detail = f"登录成功特征不匹配：{check_jsonpath} = {actual!r}"
                    if check_value:
                        detail += f"（期望 {check_value!r}）"
                    raise RuntimeError(detail)

        _do_login_session = _retry(_attempt_login_session)

        try:
            _do_login_session()
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e

        def refresh_session():
            # 401 等鉴权失效时重登刷 session cookie；失败返回 None 不污染调用方
            try:
                _do_login_session()
                return True
            except Exception as e:
                print(f"[token刷新] 重新登录失败（忽略）: {e}")
                return None

        client.set_token_refresh_callback(refresh_session)
        return

    def _attempt_login():
        # 登录时带任意 Authorization 头跳过验证码校验，登录成功后会被真实 token 覆盖
        client.set_header(auth_header_name, "skip-captcha-placeholder")
        if content_type == "form":
            # 表单提交走 Session 直发（绕过严格校验），手动解析 JSON 供 token 提取
            resp = _post_login_raw()
            if resp.status_code != 200:
                raise RuntimeError(f"登录接口 HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                resp_json = resp.json()
            except Exception as e:
                raise RuntimeError(f"登录响应非 JSON: {resp.text[:200]}") from e
            return _extract_by_jsonpath(resp_json, token_jsonpath)
        payload = dict(login_body)
        if captcha_enabled:
            _fill_captcha(payload)
        resp = client.post(login_path, json=payload)
        return _extract_by_jsonpath(resp, token_jsonpath)

    def _attempt_login_with_token_retry():
        """token 模式的验证码重试：未取到 token（识别错被服务端拒）也重试。"""
        last_exc = None
        for i in range(captcha_attempts if captcha_enabled else 1):
            try:
                token = _attempt_login()
                if token is not None or not captcha_enabled:
                    return token
                last_exc = RuntimeError(f"未从响应提取到 token（{token_jsonpath}）")
                print(f"[验证码] 第 {i + 1} 次未取到 token，取新验证码重试")
            except Exception as e:
                last_exc = e
                if not captcha_enabled or i == captcha_attempts - 1:
                    raise
                print(f"[验证码] 第 {i + 1} 次登录异常，取新验证码重试: {e}")
        raise last_exc

    _do_login = _attempt_login_with_token_retry

    def _apply_token(token) -> None:
        if token:
            client.set_header(auth_header_name, _build_header_value(token))

    # 跟踪当前使用的裸 token（refresh 时识别 stale；嵌套函数写回需容器）
    current = {"token": None}

    if share_mode == "isolated":
        # 原行为：独立登录 + 独立刷新，token 不进共享缓存
        try:
            current["token"] = _do_login()
            _apply_token(current["token"])
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e

        def refresh():
            try:
                current["token"] = _do_login()
                _apply_token(current["token"])
                return current["token"]
            except Exception as e:
                print(f"[token刷新] 重新登录失败（忽略）: {e}")
                return None

        client.set_token_refresh_callback(refresh)
        return

    # ---- shared 模式：环境级共享 token ----
    cached = EnvTokenCache.get(env.id)
    if cached:
        # 其他执行已登录过：直接复用，零登录请求
        current["token"] = cached
        _apply_token(cached)
    else:
        # 首个执行：加锁登录一次入缓存；并发到达者等待后直接复用结果
        try:
            token = EnvTokenCache.login_shared(env.id, _do_login)
        except Exception as e:
            raise RuntimeError(f"登录失败：{e}") from e
        current["token"] = token
        _apply_token(token)

    def refresh():
        # 401 条件重登：缓存 token 已被其他执行刷新则直接复用新值（不登录），
        # 仅当缓存仍是自己失效的那个 token 时才真正重登，消除乒乓互踢
        try:
            stale = current["token"]
            if stale is None:
                return None
            token = EnvTokenCache.refresh_shared(env.id, stale, _do_login)
            current["token"] = token
            _apply_token(token)
            return token
        except Exception as e:
            print(f"[token刷新] 重新登录失败（忽略）: {e}")
            return None

    client.set_token_refresh_callback(refresh)


def build_db_client(env):
    """按 env.db_config 构建 DBClient；未配置 host 或导入/初始化失败时返回 None（降级无 DB 模式）。

    从 DagExecutor._build_db_client 提取，与 build_http_client 对称，统一运行时资源构建。
    DBClient 构造不建连（self.conn=None），实际连接在 query 时懒建立。
    """
    cfg = env.db_config or {}
    if not cfg.get("host"):
        return None
    # 延迟导入，避免无 DB 环境启动报错
    try:
        from db.db_client import DBClient
        return DBClient(
            host=cfg.get("host"),
            port=int(cfg.get("port", 3306)),
            user=cfg.get("user", ""),
            password=cfg.get("password", ""),
            database=cfg.get("database", ""),
        )
    except ImportError as e:
        # db_client 模块缺失（精简部署），降级为无 DB 模式
        print(f"[DBClient] 导入失败，跳过 DB 能力: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        # 配置项缺失或类型错误
        print(f"[DBClient] 配置异常，跳过 DB 能力: {e}")
        return None
    except Exception as e:
        # 连接失败等运行时异常
        print(f"[DBClient] 初始化失败，跳过 DB 能力: {e}")
        return None
