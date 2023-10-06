"""
实现本项目的日志部分
"""


import sys
import logging
from dataclasses import dataclass


def config_logger(log_level=logging.INFO, stream_flag=True, file_path=None):
    LOGGER = logging.getLogger()

    LOGGER.setLevel(log_level)
    log_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 添加控制台输出
    if stream_flag:
        sh_handler = logging.StreamHandler(stream=sys.stdout)
        sh_handler.setLevel(log_level)
        sh_handler.setFormatter(log_fmt)
        LOGGER.addHandler(sh_handler)

    # 添加文件输出
    if file_path is not None:
        fh_handler = logging.FileHandler(filename=file_path)
        fh_handler.setLevel(log_level)
        fh_handler.setFormatter(log_fmt)
        LOGGER.addHandler(fh_handler)
