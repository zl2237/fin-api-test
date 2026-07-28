from api.file_api import FileApi
from utils.assert_util import equal, is_not_empty


class FileWorkflow:
    def __init__(self, file_api: FileApi):
        """
        文件流程类
        :param file_api: 文件API实例
        """
        self.file_api = file_api

    def upload_file_step(self, local_file_path: str) -> str:
        """
        原子步骤：文件上传
        :param local_file_path: 本地待上传文件路径
        :return: file_id 文件唯一标识
        """
        resp = self.file_api.upload_file(local_file_path)
        equal(resp["code"], 200, "文件上传：业务code不等于200")
        file_id = resp["data"]["fileId"]
        is_not_empty(file_id, "文件上传：fileId返回为空")
        return file_id