"""
minio对象存储仓库管理函数
"""


import os
import urllib3
import minio.error
from minio import Minio
from dataclasses import dataclass
import PyRepoScanner.utils.basic_tools as prs_utils


@dataclass
class MinioClient:
    """
    利用MinIO Python-SDK实现适用于PyRepoScanner的MinIO Client对象
    """
    host: str
    access_key: str
    secret_key: str
    secure = False
    region = None
    cert_check = False
    # 以下为对象对pypi的特制内容
    bucket_name = "pypi-files"

    def __post_init__(self):
        self.client = Minio(endpoint=self.host,
                            access_key=self.access_key,
                            secret_key=self.secret_key,
                            secure=self.secure,
                            region=self.region,
                            cert_check=self.cert_check)

    def create_bucket(self, bucket_name):
        """创建bucket

        检查bucket是否存在，如果不存在则创建

        :param bucket_name: 默认为pypi-files
        """
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)

    def upload_file(self, bucket_name, filepath, object_name, metadata=None):
        """上传文件

        :param bucket_name: 上传目标bucket
        :param filepath: 待上传文件，要求为.tar.gz或.whl文件
        :param object_name: 存入MinIO中的文件名（对象名）
        :param metadata: dict, e.g. {"filename": "<实际文件名>"}
        :return: object_name
        """
        mime_type = None
        if filepath.endswith(".tar.gz"):
            mime_type = "application/gzip"
        elif filepath.endswith(".whl"):
            mime_type = "application/x-wheel+zip"
        self.client.fput_object(bucket_name=bucket_name, object_name=object_name, file_path=filepath,
                                content_type=mime_type, metadata=metadata)
        return object_name

    def download_file(self, object_name, dir_path):
        """从MinIO下载文件到本地

        :param object_name:
        :param dir_path:
        :return: str: 保存下载文件的地址
        """
        stat = self.client.stat_object(bucket_name=self.bucket_name, object_name=object_name)
        file_name = stat.metadata["x-amz-meta-filename"]
        file_path = os.path.join(dir_path, file_name)
        # 获取一个未被占用的路径用于存文件
        file_path = prs_utils.get_available_filepath(file_path)
        self.client.fget_object(bucket_name=self.bucket_name, object_name=object_name, file_path=file_path)

        return file_path

    def exists_object(self, bucket_name, object_name):
        """检查MinIO是否已经存在对象"""
        try:
            _ = self.client.stat_object(bucket_name, object_name)
            return True
        except minio.error.InvalidResponseError:
            return False
