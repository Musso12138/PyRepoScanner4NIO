# PyRepoScanner的命令行参数及解析
import os
import time

import click
import json
import logging
from PyRepoScanner.utils.minio_utils import *
import PyRepoScanner.utils.log_utils as prs_log
from PyRepoScanner.parser.pypi.project import PypiProject
from PyRepoScanner.scanner.pypi.scanner import PypiScanner
from PyRepoScanner.monitor.pypi.monitor import PypiMonitor


# 后续将所有default配置写入config.json
@click.group()
@click.option("-l", "--log_level", default="info", type=click.Choice(["debug", "info", "warn", "error", "critical"]),
              help="log level of PyRepoScanner monitor/scan, default to be info.")
@click.option("--log_stream", default=False, type=click.BOOL,
              help="whether output log message to stdout, default to be True.")
@click.option("--log_file", default="./logs/py-repo-scanner.log", type=click.Path(),
              help="filepath to log message, default to be None.")
@click.pass_context
def cli(ctx, log_level, log_stream, log_file):
    ctx.ensure_object(dict)

    _log_level = getattr(logging, log_level.upper())

    ctx.obj["log_level"] = _log_level
    ctx.obj["log_stream"] = log_stream
    ctx.obj["log_file"] = log_file


@cli.command("monitor")
@click.option("-R", "--register", "reg_name", default="pypi", type=click.Choice(["pypi"]),
              help="name of the register you want to monitor, default to be pypi.")
@click.option("-i", "--interval", "raw_interval", default="60s",
              help="interval between two updates when monitoring, e.g. 60s,2m,1h, default to be 60s.")
@click.option("--mongo", "mongo_uri", default="mongodb://pypi_owner:pypi_owner@localhost:27017",
              help="MongoDB URI, dbOwner access to database 'pypi' is necessary.")
@click.option("--minio_host", "minio_host", default="127.0.0.1:9000",
              help="MinIO host address.")
@click.option("--minio_access_key", "minio_access_key", default="ON4DfLIvn4L5QngLEnQM",
              help="MinIO access key.")
@click.option("--minio_secret_key", "minio_secret_key", default="xAvHXThgJr23Ks5IFSyYp0LXCJj7s2RuxO1Tlbwu",
              help="MinIO secret key.")
@click.option("-r", "--rule", "rule_path", default="./rules",
              help="dir path or file path of rules used by scanner, default to be ./rules.")
@click.option("-fr", "--file_rule", "file_rule_path", default="./file_rules.yml", type=click.Path(exists=True),
              help="file path of file rules used by scanner, default to be ./file_rules.yml.")
@click.option("-ft", "--file_type", "file_type", default="tgz", type=click.Choice(["tgz", "whl", "*"]),
              help="specific type of file to be scanned, default to be tgz.")
@click.option("-a", "--analyze", "analyze_threshold", default=-1, type=click.IntRange(-1, 10),
              help="threshold of whether to analyze projects during monitor, "
                   "projects with suspicion ge the threshold will be analyzed automatically, "
                   "-1 for not analyzing, 0 for analyzing all projects, default to be -1.")
@click.option("-ld", "--levenshtein_distance", "levenshtein_distance", default=1, type=click.INT,
              help="levenshtein distance threshold, default to be 1.")
@click.option("-c", "--cover", "cover_flag", default=False, type=click.BOOL,
              help="whether to rescan and cover history analysis results.")
@click.pass_context
def monitor_cli(ctx, reg_name, raw_interval, mongo_uri,
                minio_host, minio_access_key, minio_secret_key,
                rule_path, file_rule_path, file_type,
                analyze_threshold, levenshtein_distance, cover_flag):
    # 配置logger
    prs_log.config_logger(log_level=ctx.obj["log_level"],
                          stream_flag=ctx.obj["log_stream"],
                          file_path=ctx.obj["log_file"])

    # 计算间隔时间
    interval = 60
    raw_interval = raw_interval.lower()
    if raw_interval[-1] == "s":
        interval = int(raw_interval[:-1])
    elif raw_interval[-1] == "m":
        interval = int(raw_interval[:-1]) * 60
    elif raw_interval[-1] == "h":
        interval = int(raw_interval[:-1]) * 60 * 60
    else:
        print("[ERROR] Invalid arguments: interval can only end with s/m/h. Received:", raw_interval)
        exit(-2)

    # 根据reg_name选择监控器
    if reg_name == "pypi":
        monitor = PypiMonitor(
            mongo_uri=mongo_uri,
            minio_host=minio_host,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            rule_path=rule_path,
            file_rules_path=file_rule_path,
            file_type=file_type,
            interval=interval,
            analyze_threshold=analyze_threshold,
            levenshtein_distance=levenshtein_distance,
            cover_flag=cover_flag,
        )
        monitor.monitor()


@cli.command("scan")
@click.option("-f", "--file", "file_path", type=click.Path(exists=True),
              help="project file or dir to be analyzed.")
@click.option("-fr", "--file_rule", "file_rule_path", default="./file_rules.yml", type=click.Path(exists=True),
              help="file path of file rules used by scanner, default to be ./file_rules.yml.")
@click.option("-r", "--rule", "rule_path", default="./rules",
              help="dir path or file path of rules, default to be ./rules.")
@click.option("-o", "--output", "output_filepath", default=None, type=click.Path(),
              help="output JSON file path.")
@click.pass_context
def scan_cli(ctx, file_path, file_rule_path, rule_path, output_filepath):
    # 配置logger
    prs_log.config_logger(log_level=ctx.obj["log_level"],
                          stream_flag=ctx.obj["log_stream"],
                          file_path=ctx.obj["log_file"])

    print_flag = True
    if output_filepath is not None:
        print_flag = False
    scanner = PypiScanner(rule_path=rule_path, file_rules_path=file_rule_path, print_flag=print_flag)
    results = scanner.scan_local_file(file_path)
    if results is None:
        print("Something bad during scanning file, see more details in log file:", ctx.obj["log_file"])
        exit(-1)

    # 输出扫描结果
    if output_filepath is not None:
        with open(output_filepath, "w") as out_f:
            json.dump(results, out_f)
    else:
        scanner.print_results_beautiful(results)


# 专门用于测试一些接口
@cli.command("test")
def test():
    begin = time.time()
    # mc = PypiMinioClient()
    # mc.upload_file("./sample/packages/beautifulsoup4-4.12.2-py3-none-any.whl", "test111")
    scanner = PypiScanner
    print(time.time() - begin)

