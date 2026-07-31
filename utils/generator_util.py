import time
import random
import string
import uuid
from utils.log_util import get_logger

logger = get_logger()


def get_random_str(length: int = 4) -> str:
    """
    获取指定长度大写字母+数字随机字符串
    :param length: 随机串长度
    :return: 随机字符串
    """
    char_pool = string.ascii_uppercase + string.digits
    return ''.join(random.choice(char_pool) for _ in range(length))


def generate_bl_no(prefix: str = "BL") -> str:
    """
    生成提单号 BL_NO
    规则：前缀 + 年月日时分秒 + 4位随机码
    示例：BL20260727192530A78Z
    :param prefix: 单号前缀
    :return: 唯一bl_no
    """
    time_str = time.strftime("%Y%m%d%H%M%S")
    rand_str = get_random_str(4)
    bl_no = f"{prefix}{time_str}{rand_str}"
    logger.info(f"生成BL_NO：{bl_no}")
    return bl_no


def generate_invoice_number(prefix: str = "INV") -> str:
    """
    生成发票号 invoice_number
    规则：前缀 + 年月日时分秒 + 4位随机码
    示例：INV20260727192612X9S3
    :param prefix: 单号前缀
    :return: 唯一invoice_number
    """
    time_str = time.strftime("%Y%m%d%H%M%S")
    rand_str = get_random_str(4)
    invoice_no = f"{prefix}{time_str}{rand_str}"
    logger.info(f"生成InvoiceNumber：{invoice_no}")
    return invoice_no


def generate_unique_id() -> str:
    """
    生成UUID格式唯一ID
    示例：349142e7-5991-43d8-9ce7-3bf78fd908d4
    :return: uuid字符串（小写，不带横杠大写可自行调整）
    """
    unique_id = str(uuid.uuid4())
    logger.info(f"生成unique_id：{unique_id}")
    return unique_id