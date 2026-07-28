from pathlib import Path
from api.base_api import BaseApi


class FileApi(BaseApi):
    def upload_file(self, file_path: str | Path) -> dict:
        """
        文件上传接口
        :param file_path: 本地待上传文件路径
        :return: 接口原始响应dict
        """
        files = {"file": open(file_path, "rb")}
        return self.http.session.post(
            url=f"{self.http.base_url}/api/file/upload",
            headers=self.http.headers,
            files=files
        ).json()

    def download_file(self, file_url: str, save_name: str) -> Path:
        """
        文件下载接口
        :param file_url: 文件远端访问地址
        :param save_name: 本地保存文件名
        :return: 本地完整保存路径Path对象
        """
        resp = self.http.session.get(file_url, headers=self.http.headers, stream=True)
        save_path = Path(self.http.base_url.split("/")[-1]) / save_name
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path