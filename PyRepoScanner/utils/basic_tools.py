import logging
import os
import re
import time
import datetime
import random
import shutil
import tarfile
import tempfile
import zipfile
import requests
import email.message


# TMP_PATH = tempfile.gettempdir() if tempfile.gettempdir() else "tmp"
TMP_PATH = "tmp"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
]
EXTRACT_FILENAME_REGEX = re.compile("""(?:remove|add\s+\S+)\s+file\s+(\S+)""")
EXTRACT_OWNER_REGEX = re.compile("""(?:add|invite|accepted|remove|change)\s+Owner\s+(\S+)""")
EXTRACT_MAINTAINER_REGEX = re.compile("""(?:add|invite|accepted|remove|change)\s+Maintainer\s+(\S+)""")
LOGGER = logging.getLogger()


def download_file_to_dir(url: str, dir_path: str, file_name: str = None):
    """利用requests将文件下载到本地指定位置

    :param url: 文件下载链接
    :param dir_path: 本地目录地址
    :param file_name: 本地文件名
    :return 最终创建成功的文件路径
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    file_path = dir_path
    if file_name:
        file_path = os.path.join(dir_path, file_name)
    else:
        _, url_name = os.path.split(url)
        file_path = os.path.join(dir_path, url_name)

    available_file_path = get_available_filepath(file_path)

    headers = {
        "Connection": "close",
        "User-Agent": random.choice(USER_AGENTS)
    }
    # GET pypi index file
    resp = requests.get(url, headers=headers)
    with open(available_file_path, "wb") as f:
        f.write(resp.content)

    return available_file_path


def get_available_filepath(file_path: str):
    """
    检查文件是否存在，如果存在则为其添加递增的尾标
    :param file_path: 打算创建的文件路径
    :return: 可用的文件路径
    """
    if not os.path.exists(file_path):
        return file_path

    file_dir, file_name = os.path.split(file_path)
    file_base_name, file_ext = os.path.splitext(file_name)

    i = 1
    new_file_name = file_name
    while os.path.exists(os.path.join(file_dir, new_file_name)):
        # 对于双层扩展名, 如.tar.gz文件，需要进一步确定base_name
        if file_ext in [".gz"] and file_base_name.endswith(".tar"):
            file_base_name, new_file_ext = os.path.splitext(file_base_name)
            file_ext = new_file_ext + file_ext
        new_file_name = "{}({}){}".format(file_base_name, i, file_ext)
        i += 1

    return os.path.join(file_dir, new_file_name)


def remove_file(file_path: str):
    """删除指定文件

    :param file_path: 文件地址
    """
    if not os.path.isfile(file_path):
        return
    try:
        os.remove(file_path)
    except Exception as e:
        LOGGER.error(f"remove file {file_path} failed with: {e}")


def remove_dir(dir_path: str):
    """删除指定文件夹

    :param dir_path: 文件夹地址
    """
    if not os.path.isdir(dir_path):
        return
    try:
        os.rmdir(dir_path)
    except Exception as e:
        LOGGER.error(f"remove dir {dir_path} failed with: {e}")


def empty_dir(dir_path: str):
    """清空指定目录下的全部文件夹及文件

    :param dir_path: 要清空的目录
    """
    del_list = os.listdir(dir_path)
    for f in del_list:
        file_path = os.path.join(dir_path, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


def extract_tar_gz_to_dir(source_path: str, dest_path: str):
    """将tar.gz文件解压到指定目录

    对于extract_tar_gz_to_dir("a(1).tar.gz", "tmp")，将解压到tmp/a(1)/目录下

    :param source_path: tar.gz文件路径
    :param dest_path: 目标解压目录路径
    :return: 最终解压文件的路径
    """
    _, file_name = os.path.split(source_path)
    file_base_name, _ = os.path.splitext(file_name)
    file_base_name, _ = os.path.splitext(file_base_name)
    dest_dir = os.path.join(dest_path, file_base_name)
    if not os.path.exists(dest_dir):
        os.mkdir(dest_dir)
    with tarfile.open(source_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)

    return dest_dir


def extract_whl_to_dir(source_path: str, dest_path: str):
    """将whl文件解压到指定目录

    :return: str: dir path
    """
    _, file_name = os.path.split(source_path)
    file_base_name, _ = os.path.splitext(file_name)
    dest_dir = os.path.join(dest_path, file_base_name)
    if not os.path.exists(dest_dir):
        os.mkdir(dest_dir)
    with zipfile.ZipFile(source_path, allowZip64=True) as z:
        z.extractall(path=dest_dir)

    return dest_dir


def parse_content_type(header: str) -> str:
    """copied from PEP691 document, no real use"""
    m = email.message.Message()
    m["content-type"] = header
    return m.get_content_type()


def parse_version_from_tar_gz_filename(project_name: str, filename: str):
    """根据tar.gz文件名解析release版本"""
    return filename.lstrip(project_name).lstrip("-").rstrip(".tar.gz")


def popular_time_need_update(src_time):
    """检查popular是否过期

    当popular时间与当前年月不符 / 当前day > 1时popular需要更新，返回True
    """
    last_update = None
    now_time = datetime.datetime.now()

    if isinstance(src_time, str):
        last_update = datetime.datetime.strptime(src_time, "%Y-%m-%d %H:%M:%S")
    elif isinstance(src_time, datetime.datetime):
        last_update = src_time

    if last_update is not None:
        # 同年同月 => 已是最新
        if last_update.year == now_time.year and last_update.month == now_time.month:
            return False
        # 非同年同月，当月非初日 => 本月API已更新
        elif now_time.day > 1:
            return True
        # 当月初日 => 本月API不一定更新
        else:
            return False
    else:
        return True


def extract_filename_from_action(action: str):
    result = EXTRACT_FILENAME_REGEX.search(action)
    if result is None:
        return None
    matches = result.groups()
    if len(matches) > 0:
        return matches[0]
    return None


def extract_owner_from_action(action: str):
    result = EXTRACT_OWNER_REGEX.search(action)
    if result is None:
        return None
    matches = result.groups()
    if len(matches) > 0:
        return matches[0]
    return None


def extract_maintainer_from_action(action: str):
    result = EXTRACT_MAINTAINER_REGEX.search(action)
    if result is None:
        return None
    matches = result.groups()
    if len(matches) > 0:
        return matches[0]
    return None
