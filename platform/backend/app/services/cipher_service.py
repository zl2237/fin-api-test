# -*- coding: utf-8 -*-
"""接口级传输加解密与回调验签（对接海关 requestCipher 协议）。

协议要点（docs/调用加密说明.txt）：
- 外层请求体仅一个字段（默认 requestCipher），值为内层 JSON 的 RSA 密文
- RSA-2048（X.509/SPKI 公钥、PKCS#8 私钥）、RSA/ECB/PKCS1Padding 分段加密：
  明文每段最多 244 字节（协议约定，低于理论上限 245=256-11），每段密文固定
  256 字节，全部密文按顺序拼接后【整体一次 Base64】——不得逐段 Base64
- 响应目前为明文；「响应解密」作为可配能力实现（整体 body / 包裹字段两种模式）

回调验签（docs/回调验签说明.txt）：RSA2（SHA256withRSA）签名，待签串按对方
Fastjson2 序列化规则规范化后比对（见 canonicalize_callback）。

密钥对配置在环境的 cipher_config.key_pairs（名称多对，如 customs/cfca），
懒校验：发送时用到哪把才解析哪把。本模块是唯一加解密实现点。
"""
import base64
import json
import re
import secrets
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .. import path_setup  # noqa: F401  确保 utils 可导入（sys.path 指向本仓根）
from utils.exceptions import CipherError

# 海关协议约定：每段明文 244 字节（理论上限 245 = 256 - PKCS1v1.5 头 11）
DEFAULT_SEGMENT_SIZE = 244
MAX_SEGMENT_SIZE = 245
# RSA-2048 每段密文固定字节数
CIPHER_BLOCK_SIZE = 256

_PEM_BEGIN_PUBLIC = "-----BEGIN PUBLIC KEY-----"


def _b64_no_ws(material: str) -> bytes:
    """剥离全部空白后 Base64 解码（容忍拷贝丢失换行/多空格）"""
    return base64.b64decode(re.sub(r"\s+", "", material))


@lru_cache(maxsize=64)
def load_public_key(material: str) -> rsa.RSAPublicKey:
    """解析公钥：完整 PEM 优先；PEM 头尾在但换行丢失 / 裸 Base64(X.509 DER) 兜底。

    material 不可 hash 的调用方（理论上只有 str）不受影响；lru_cache 以密钥文本
    为键，避免每次请求重复解析同一把钥匙。
    """
    mat = (material or "").strip()
    if not mat:
        raise CipherError("公钥内容为空，请粘贴完整 PEM（-----BEGIN PUBLIC KEY-----）或 Base64 密钥材料")
    key: Any
    if "-----BEGIN" in mat:
        try:
            key = serialization.load_pem_public_key(mat.encode("utf-8"))
        except Exception:
            # PEM 头尾在但结构损坏（常见：换行丢失的单行粘贴）——取头尾之间的
            # 密钥体按裸 Base64(X.509 DER) 重试
            parts = mat.split("-----")
            if len(parts) >= 5:
                try:
                    key = serialization.load_der_public_key(_b64_no_ws(parts[2]))
                except Exception as e:
                    raise CipherError(
                        f"公钥 PEM 解析失败：{e}。请确认是 X.509/SPKI 格式公钥"
                        "（-----BEGIN PUBLIC KEY----- 开头），且内容完整未截断")
            else:
                raise CipherError(
                    "公钥 PEM 结构不完整（缺 BEGIN/END 标记），请粘贴完整公钥"
                    "（-----BEGIN PUBLIC KEY----- 至 -----END PUBLIC KEY-----）")
    else:
        try:
            key = serialization.load_der_public_key(_b64_no_ws(mat))
        except Exception as e:
            raise CipherError(
                f"公钥解析失败（既非合法 PEM 也非合法 Base64/X.509 DER）：{e}。"
                "请粘贴 -----BEGIN PUBLIC KEY----- 格式公钥或其 Base64 密钥体")
    if not isinstance(key, rsa.RSAPublicKey):
        raise CipherError("公钥不是 RSA 公钥（协议要求 RSA-2048），请与对接方确认密钥类型")
    return key


@lru_cache(maxsize=64)
def load_private_key(material: str) -> rsa.RSAPrivateKey:
    """解析私钥：PKCS#8/PKCS#1 PEM 优先，裸 Base64(PKCS#8 DER) 兜底。"""
    mat = (material or "").strip()
    if not mat:
        raise CipherError("私钥内容为空，请粘贴完整 PEM（-----BEGIN PRIVATE KEY-----）或 Base64 密钥材料")
    key: Any
    if "-----BEGIN" in mat:
        try:
            key = serialization.load_pem_private_key(mat.encode("utf-8"), password=None)
        except Exception as e:
            raise CipherError(
                f"私钥 PEM 解析失败：{e}。请确认是 PKCS#8 格式私钥"
                "（-----BEGIN PRIVATE KEY----- 开头，无口令），且内容完整未截断")
    else:
        try:
            key = serialization.load_der_private_key(_b64_no_ws(mat), password=None)
        except Exception as e:
            raise CipherError(
                f"私钥解析失败（既非合法 PEM 也非合法 Base64/PKCS#8 DER）：{e}。"
                "请粘贴 -----BEGIN PRIVATE KEY----- 格式私钥或其 Base64 密钥体")
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CipherError("私钥不是 RSA 私钥（协议要求 RSA-2048），请与对接方确认密钥类型")
    return key


def encrypt_to_base64(plaintext: bytes, public_material: str,
                      segment_size: int = DEFAULT_SEGMENT_SIZE) -> str:
    """明文分段加密 → 密文顺序拼接 → 整体一次 Base64。

    空明文产出单段「空段」密文（256 字节），保持「至少一段」不变量。
    """
    try:
        seg = int(segment_size)
    except (TypeError, ValueError):
        raise CipherError(f"分段大小须为整数（1~{MAX_SEGMENT_SIZE}），当前: {segment_size!r}")
    if not 1 <= seg <= MAX_SEGMENT_SIZE:
        raise CipherError(
            f"分段大小须在 1~{MAX_SEGMENT_SIZE} 字节之间"
            f"（RSA-2048 PKCS1v1.5 明文段上限 = 256 - 11 = {MAX_SEGMENT_SIZE}），当前: {seg}")
    pub = load_public_key(public_material)
    chunks = [plaintext[i:i + seg] for i in range(0, len(plaintext), seg)] or [b""]
    cipher_bytes = b"".join(pub.encrypt(c, padding.PKCS1v15()) for c in chunks)
    return base64.b64encode(cipher_bytes).decode("ascii")


def encrypt_json_body(body: Any, public_material: str,
                      segment_size: int = DEFAULT_SEGMENT_SIZE) -> str:
    """内层 JSON（UTF-8、紧凑分隔符、非 ASCII 原字符）加密为整体 Base64 密文。"""
    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return encrypt_to_base64(plaintext, public_material, segment_size)


def decrypt_from_base64(cipher_b64: str, private_material: str) -> bytes:
    """整体 Base64 密文 → 256 字节分段解密 → 明文字节拼接。"""
    if not cipher_b64 or not cipher_b64.strip():
        raise CipherError("密文为空，无法解密", stage="response")
    try:
        raw = _b64_no_ws(cipher_b64)
    except Exception as e:
        raise CipherError(f"密文不是合法 Base64：{e}", stage="response")
    if len(raw) == 0 or len(raw) % CIPHER_BLOCK_SIZE != 0:
        raise CipherError(
            f"密文长度 {len(raw)} 不是 {CIPHER_BLOCK_SIZE} 的整数倍"
            "（RSA-2048 每段密文固定 256 字节），密文可能被截断或格式不符",
            stage="response")
    priv = load_private_key(private_material)
    try:
        return b"".join(
            priv.decrypt(raw[i:i + CIPHER_BLOCK_SIZE], padding.PKCS1v15())
            for i in range(0, len(raw), CIPHER_BLOCK_SIZE))
    except ValueError as e:
        raise CipherError(
            f"RSA 解密失败：{e}。常见原因：公私钥不配对（测试/生产密钥不可混用）、"
            "密钥已轮换（请与对接方确认最新密钥）、或密文在传输中被损坏",
            stage="response")


def key_pairs_from_config(cipher_config: dict | None) -> dict[str, dict[str, str | None]]:
    """从环境 cipher_config 解析 {名称: {public_key, private_key}} 材料表。

    不做格式校验（懒校验：用到哪把才解析哪把，坏密钥不影响无加密接口的环境）；
    重名后者覆盖。
    """
    pairs = (cipher_config or {}).get("key_pairs") or []
    table: dict[str, dict[str, str | None]] = {}
    for p in pairs:
        if isinstance(p, dict) and p.get("name"):
            table[str(p["name"])] = {
                "public_key": p.get("public_key"),
                "private_key": p.get("private_key"),
            }
    return table


def resolve_key_pair(cipher_keys: dict | None, name: str) -> dict[str, str | None]:
    """按名称取密钥对材料；未命中给带指引的报错。"""
    pair: dict[str, str | None] | None = (cipher_keys or {}).get(name)
    if not pair:
        raise CipherError(
            f"环境未配置名为「{name}」的加密密钥对，请到「环境编辑 → 加密配置」"
            "录入该名称的密钥对，或修改接口加密配置里的密钥对名称")
    return pair


def verify_key_pair(public_material: str | None, private_material: str | None) -> int:
    """公私钥配对自检：600 字节随机样本（跨 3 段）加密→解密→比对。

    返回样例密文 Base64 长度；缺钥匙/解析失败/不配对均抛带下一步动作的 CipherError。
    """
    if not public_material or not private_material:
        raise CipherError("公钥与私钥都需录入后才能测试加解密（可先只配请求加密用的公钥，但自检需要成对）")
    sample = secrets.token_bytes(600)
    cipher_b64 = encrypt_to_base64(sample, public_material)
    plain = decrypt_from_base64(cipher_b64, private_material)
    if plain != sample:
        raise CipherError("加解密往返不一致：公私钥疑似不配对（测试/生产密钥不可混用），请与对接方确认")
    return len(cipher_b64)


# ============ 回调验签（RSA2 / SHA256withRSA，Fastjson2 规范化） ============

def _canonical_json(value: Any) -> str:
    """Fastjson2 风格紧凑 JSON：递归字典序键、数组保序、嵌套 null 保持 null、
    非 ASCII 原字符、仅转义引号/反斜杠/控制字符（对齐 JSON.toJSONString(x, WriteNulls)）。

    键序为 Python sorted（Unicode 码点序）——对方字段键均为 ASCII，与 Java
    String.compareTo（UTF-16 码元序）在此范围内一致。
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _canonical_json(v)
            for k, v in sorted(value.items(), key=lambda kv: kv[0])
        ) + "}"
    raise CipherError(f"回调报文含不支持序列化的值类型: {type(value).__name__}")


def _top_value_str(value: Any) -> str:
    """待签串顶层值的字符串形态：null→空串、布尔 true/false、数字十进制、
    字符串原样（不 URL 编码）、对象/数组用规范化 JSON。"""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return _canonical_json(value)


def canonicalize_callback(payload: dict) -> tuple[str, str | None]:
    """重建待验签原串：剔除顶层 sign/signType，其余键字典序 k=v&k=v 拼接。

    返回 (待签原串, items 的规范化 JSON 或 None)。items 为 None 仅当报文不含
    该键（非本协议回调时原串仍可重建，验签自然不通过）。
    """
    if not isinstance(payload, dict):
        raise CipherError("回调报文必须是 JSON 对象，请粘贴完整回调请求体")
    keys = sorted(k for k in payload if k not in ("sign", "signType"))
    canonical = "&".join(f"{k}={_top_value_str(payload[k])}" for k in keys)
    items_json = _canonical_json(payload["items"]) if "items" in payload else None
    return canonical, items_json


def sign_callback_canonical(canonical: str, private_material: str) -> str:
    """用私钥对待签原串做 RSA2 签名（仅测试/自证用——线上签名在对方侧）。"""
    priv = load_private_key(private_material)
    sig = priv.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def verify_callback_sign(payload: dict, sign: str, public_material: str) -> bool:
    """验签：重建原串 → SHA256withRSA 公钥校验。任何格式问题按「不通过」处理。"""
    canonical, _ = canonicalize_callback(payload)
    pub = load_public_key(public_material)
    try:
        sig = base64.b64decode((sign or "").strip() or "invalid")
    except Exception:
        return False
    try:
        pub.verify(sig, canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def build_assertion_cipher_ctx(env: Any, api: Any = None) -> dict | None:
    """response_sign_verify 断言的密钥上下文：环境密钥对表 + 接口加密配置的默认密钥名。

    duck-typing 取属性（不引模型，测试替身可直接传 SimpleNamespace/dict 包装）；
    环境一个密钥对都没有 → None（断言按「环境未配置密钥对」失败并给指引，
    与工具页口径一致）。默认密钥名解析顺序：接口请求加密 key > 响应解密 key；
    两者皆无时断言侧回落「第一对」（与工具页留空语义一致，由断言引擎处理）。
    """
    pairs = key_pairs_from_config(getattr(env, "cipher_config", None))
    if not pairs:
        return None
    cc = getattr(api, "crypto_config", None) if api is not None else None
    cc = cc or {}
    default_key = ((cc.get("request") or {}).get("key")
                   or (cc.get("response") or {}).get("key")
                   or None)
    return {"key_pairs": pairs, "default_key": default_key}
