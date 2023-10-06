import os
import re
import time
import json
import arrow
import queue
import random
import logging
import datetime
import threading

import requests
import xmlrpc.client
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List

import PyRepoScanner.utils.basic_tools as prs_utils
import PyRepoScanner.utils.mongo_utils as prs_mongo
import PyRepoScanner.utils.minio_utils as prs_minio
import PyRepoScanner.utils.poison_detection_tools as prs_poison_detection
from PyRepoScanner.scanner.pypi.scanner import PypiScanner


LOGGER = logging.getLogger()
PYPI_URL = "https://pypi.org"
INDEX_FILE_URL = "https://pypi.org/simple/"
PROJECT_JSON_TEMPLATE = "https://pypi.org/pypi/{PROJECT}/json"
RELEASE_JSON_TEMPLATE = "https://pypi.org/pypi/{PROJECT}/{VERSION}/json"
NEWEST_PACKAGE_FEED_URL = "https://pypi.org/rss/packages.xml"
LATEST_UPDATES_FEED_URL = "https://pypi.org/rss/updates.xml"
TOP5000_PACKAGES_THIS_MONTH_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
PEP691_CONTENT_TYPES = [
    "application/vnd.pypi.simple.v1+json",
    "application/vnd.pypi.simple.v1+html;q=0.2",
    "text/html;q=0.01",  # For legacy compatibility
]
PEP691_ACCEPT = ", ".join(PEP691_CONTENT_TYPES)


@dataclass
class PypiMonitor:
    """
    PypiMonitor
    自动化监控PyPI仓库
    """
    mongo_uri: str
    minio_host: str
    minio_access_key: str
    minio_secret_key: str
    interval: int = 60              # 间隔interval秒检查register状态
    analyze_threshold: int = -1     # suspicion >= analyze_threshold检测，-1不检测
    file_type: str = "tgz"          # 检测的包类型，tgz/whl/*
    rule_path: str = None
    file_rules_path: str = None     # 要检测的内容，默认为setup.py, __init__.py文件
    levenshtein_distance: int = 1
    cover_flag: bool = False
    local_serial = None             # 本地已经维护的serial
    curr_serial = None              # 本地正在处理的serial
    popular = None
    analysis_queue_index = 0
    download_queue_index = 0

    def __post_init__(self):
        self.mongo_client = prs_mongo.PRSPypiMongoClient(mongo_uri=self.mongo_uri)
        self.minio_client = prs_minio.MinioClient(host=self.minio_host,
                                                  access_key=self.minio_access_key,
                                                  secret_key=self.minio_secret_key)
        self.minio_bucket_name = "pypi-files"
        self.minio_client.create_bucket(self.minio_bucket_name)

        # 如果需要检测，则创建扫描器以及用于检测的优先级队列
        if self.analyze_threshold > -1:
            self.scanner = PypiScanner(rule_path=self.rule_path, file_rules_path=self.file_rules_path)
            # 分析队列格式: (-suspicion, project_name, release_version, local_file_path, index, url)
            self.analysis_priority_queue = queue.PriorityQueue()
            analysis_thread = threading.Thread(target=self.analysis_thread_handler)
            analysis_thread.daemon = True
            analysis_thread.start()

        # 启动线程下载并保存文件内容
        # 下载队列格式: (-suspicion, project_name, release_version, index, url)
        self.download_priority_queue = queue.PriorityQueue()
        download_thread = threading.Thread(target=self.download_save_thread_handler)
        download_thread.daemon = True
        download_thread.start()

    def monitor(self):
        """自动化监控PyPI仓库

        每间隔interval时间:
            检查本地是否已有记录，没有则全量爬取；有则利用PyPI API获取本地最近一次serial后的更新

        day > 1:
            更新本地的popular记录（开源项目每月1日不定时更新top5000）
        """
        LOGGER.info("start monitor")
        print("start monitor")
        while True:
            if self.local_serial is None:
                self.local_serial = self.load_local_serial()
            if self.popular is None or prs_utils.popular_time_need_update(self.popular["last_update"]):
                self.update_popular()

            if self.local_serial is None:
                print("local serial is None")
                self.scrape_save_all_projects_releases()
            else:
                self.update()
            time.sleep(self.interval)

    def scrape_save_all_projects_releases(self):
        """全量爬取pypi仓库中的projects和releases，并存入相应数据库

        用于首次使用系统进行监控时全量爬取并存储pypi simple projects和releases。
        根据PyPI Legacy API(https://warehouse.pypa.io/api-reference/legacy.html)实现。
        """
        try:
            projects_list = self.scrape_all_projects_from_simple_pep691()
            if projects_list is None:
                LOGGER.error("scrape all projects from PyPI simple PEP691 API got None.")
                exit(-1)

            self.curr_serial = projects_list["serial"]
            LOGGER.info(f"local serial: {self.local_serial}, pypi serial: {self.curr_serial}"
                        f", begin to scrape all from simple API")
            print("pypi serial:", self.curr_serial)
            print("begin to scrape all from simple API")

            for project in projects_list["projects"]:
                project_name = project["name"]

                LOGGER.info(f"scrape, process and save project metadata: {project_name}")

                # 爬取并存储project元数据
                try:
                    project_metadata = self.scrape_project_metadata(project_name)
                    if self.json_is_not_found(project_metadata):
                        LOGGER.warning(f"PyPI project metadata not found: {project_name}")
                        continue
                    self.process_save_project_metadata_init(project_metadata)
                except Exception as e:
                    LOGGER.error(f"scrape and save metadata of project: {project_name} failed with: {e}")
                    continue

                suspicion = project_metadata["suspicion"]
                suspicion_info = project_metadata["suspicion_info"]

                # 爬取并存储所有release元数据
                version_list = self.scrape_project_all_versions_from_simple_pep691(project_name)
                if version_list is None:
                    LOGGER.error(f"scrape version list of project: {project_name} from PyPI simple PEP691 API got None.")
                    continue
                for version in version_list["versions"]:
                    LOGGER.info(f"scrape, process and save release metadata: {project_name} {version}")
                    try:
                        release_metadata = self.scrape_release_metadata(project_name, version)
                        if self.json_is_not_found(release_metadata):
                            LOGGER.warning("PyPI release metadata not found: " + project_name + " " + version)
                            continue
                        self.process_save_release_metadata_init(release_metadata, suspicion, suspicion_info)
                    except Exception as e:
                        LOGGER.error(f"scrape and save metadata of release: {project_name} {version} failed with: {e}")
                        continue

            # 全量爬取并保存后，将本地serial置位到curr_serial并存到本地
            self._update_local_serial()
        except Exception as e:
            LOGGER.error(f"scrape projects list from PyPI simple API failed with: {e}")
            exit(-1)

    def scrape_all_projects_from_simple_pep503(self):
        """基于PEP503获取pypi仓库全量project名称

        PEP503: https://peps.python.org/pep-0503/
        PyPI提供了simple API https://warehouse.pypa.io/api-reference/legacy.html
        获取pypi index file记录的全部project名称及进一步的version list链接

        :return: {
            "serial": X-PyPI-Last-Serial,
            "meta": {
                "api-version": "1.0"
            },
            "projects": [
                {"name": "Frob"},
                {"name": "spamspamspam"},
                ...
            ]
        }
        """
        # 过滤目标地址代理
        os.environ['NO_PROXY'] = INDEX_FILE_URL
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS)
        }
        # GET pypi index file
        resp = requests.get(INDEX_FILE_URL, headers=headers)
        # 从响应头中获取serial信息
        serial = resp.headers.get("X-PyPI-Last-Serial")
        if serial is None:
            LOGGER.error("scrape pypi projects from simple API PEP691 "
                         "got invalid response with None X-PyPI-Last-Serial in header.")
            return None
        self.curr_serial = serial

        # 解析html返回结果
        res = self.parse_projects_from_simple_html_resp(resp=resp)
        res["serial"] = serial
        return res

    def scrape_all_projects_from_simple_pep691(self):
        """基于PEP691获取pypi仓库全量project名称

        PEP691: https://peps.python.org/pep-0691/
        获取pypi index file记录的全部project名称及project最近更新serial

        :return: {
            "serial": X-PyPI-Last-Serial,
            "meta": {
                "_last-serial": 17619998
                "api-version": "1.1"
            },
            "projects": [
                {"name": "Frob", "_last-serial": 3075854},
                {"name": "spamspamspam", "_last-serial": 1448421},
                ...
            ]
        }
        """
        # 设置PEP691规定的API请求头
        # 过滤目标地址代理
        os.environ['NO_PROXY'] = INDEX_FILE_URL
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS),
            "Accept": PEP691_ACCEPT
        }
        # GET pypi index file
        resp = requests.get(INDEX_FILE_URL, headers=headers)

        # 解析响应结果
        serial = resp.headers.get("X-PyPI-Last-Serial")
        if serial is None:
            LOGGER.error("scrape pypi projects from simple API PEP691 "
                         "got invalid response with None X-PyPI-Last-Serial in header.")
            return None

        content_type = resp.headers.get("content-type", "")
        # 解析html返回结果
        if content_type == "application/vnd.pypi.simple.v1+json":
            res = json.loads(resp.text)
            res["serial"] = serial
            return res
        elif content_type == "application/vnd.pypi.simple.v1+html" or content_type == "text/html":
            res = self.parse_projects_from_simple_html_resp(resp=resp)
            res["serial"] = serial
            return res
        else:
            LOGGER.warning(
                f"scrape pypi projects from simple API PEP691 got invalid response content type: {content_type}")
            return None

    @staticmethod
    def parse_projects_from_simple_html_resp(resp):
        """解析PEP503 simple API响应的projects html内容

        :return: {
            "projects": [
                {"name": "Frob"},
                {"name": "spamspamspam"},
                ...
            ]
        }
        """
        res = {
            "projects": []
        }
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a"):
            project_name = link.text
            # href = link.get("href")
            res["projects"].append({"name": project_name})

        return res

    def scrape_project_all_versions_from_simple_pep503(self, project_name: str):
        """基于PEP503获取pypi仓库指定project的全部release version

        :return: {
            "serial": 17619998,
            "name": "beautifulsoup4",
            "versions": [
                "4.0.1", "4.0.2", ...
            ]
        }
        """
        # 过滤目标地址代理
        os.environ['NO_PROXY'] = INDEX_FILE_URL
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS)
        }
        # GET pypi project releases
        release_url = INDEX_FILE_URL + project_name
        resp = requests.get(release_url, headers=headers)

        # 解析响应结果
        serial = resp.headers.get("X-PyPI-Last-Serial")
        res = self.parse_releases_from_simple_html_resp(project_name=project_name, resp=resp)
        res["serial"] = serial
        res["name"] = project_name
        return res

    def scrape_project_all_versions_from_simple_pep691(self, project_name: str):
        """基于PEP691获取pypi仓库指定project的全部release version

        :return: {
            "serial": 17619998,
            "meta": {
                "_last-serial": 17619998,
                "api-version": "1.1"
            },
            "name": "beautifulsoup4",
            "versions": [
                "4.0.1", "4.0.2", ...
            ],
            "files": [
                {
                    'core-metadata': False,
                    'data-dist-info-metadata': False,
                    'filename': 'beautifulsoup4-4.0.1.tar.gz',
                    'hashes': {
                        'sha256': 'dc6bc8e8851a1c590c8cc8f25915180fdcce116e268d1f37fa991d2686ea38de'
                    },
                    'requires-python': None,
                    'size': 51024,
                    'upload-time': '2014-01-21T05:35:05.558877Z',
                    'url': 'https://files.pythonhosted.org/packages/6f/be/99dcf74d947cc1e7abef5d0c4572abcb479c33ef791d94453a8fd7987d8f/beautifulsoup4-4.0.1.tar.gz',
                    'yanked': False
                }
            ]
        }
        """
        # 设置PEP691规定的API请求头
        # 过滤目标地址代理
        os.environ['NO_PROXY'] = INDEX_FILE_URL
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS),
            "Accept": PEP691_ACCEPT
        }
        # GET pypi project releases
        release_url = INDEX_FILE_URL + project_name
        resp = requests.get(release_url, headers=headers)

        # 解析响应结果
        serial = resp.headers.get("X-PyPI-Last-Serial")
        content_type = resp.headers.get("content-type", "")
        # 解析html返回结果
        if content_type == "application/vnd.pypi.simple.v1+json":
            res = json.loads(resp.text)
            res["serial"] = serial
            return res
        elif content_type == "application/vnd.pypi.simple.v1+html" or content_type == "text/html":
            res = self.parse_releases_from_simple_html_resp(project_name, resp)
            res["serial"] = serial
            return res
        else:
            LOGGER.warning(
                "scrape pypi releases of " + project_name +
                " from simple API PEP691 got invalid response content type: " + content_type)
            return None

    @staticmethod
    def parse_releases_from_simple_html_resp(project_name, resp):
        """解析PEP503 simple API响应的releases html内容

        :return: {
            "versions": [
                "4.0.1", "4.0.2", ...
            ]
        }
        """
        res = {
            "versions": []
        }

        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a"):
            filename = link.text
            if filename.endswith(".tar.gz"):
                version = prs_utils.parse_version_from_tar_gz_filename(project_name, filename)
                if version is not None:
                    res["versions"].append(version)

        return res

    def update(self):
        """基于本地状态监控并存储PyPI仓库更新

        local_serial < last_serial:
            获取自本地更新以来的全部更新行为记录，根据行为做出本地更新
        """
        pypi_last_serial = self.scrape_changelog_last_serial()
        if self.local_serial < pypi_last_serial:
            self.curr_serial = pypi_last_serial
            LOGGER.info(f"local serial: {self.local_serial}, pypi serial: {self.curr_serial}, begin to update")
            print("local serial:", self.local_serial)
            print("pypi last serial:", self.curr_serial)
            print("begin to update")

            changelog = self.scrape_changelog_since_serial(self.local_serial)
            self.handle_changelog(changelog)

            self._update_local_serial()

    @staticmethod
    def scrape_changelog_last_serial():
        """获取PyPI最近一次更新的serial id

        :return: int: latest updated serial id of PyPI
        """
        client = xmlrpc.client.ServerProxy(PYPI_URL)
        return client.changelog_last_serial()

    @staticmethod
    def scrape_changelog_since_serial(since_serial: int):
        """获取自指定serial后的每个serial对应的更新信息

        xml-rpc API中的changelog_since_serial，
        根据action区分更新内容，详情参考PYPI_ACTIVITIES

        :return: [ [project, version, timestamp, action, serial] , ... ]
        """
        client = xmlrpc.client.ServerProxy(PYPI_URL)
        return client.changelog_since_serial(since_serial)

    def handle_changelog(self, changelog: list):
        """根据action逐条处理changelog"""
        pre_project_name = None
        pre_release_version = None
        file_action_regex = re.compile("""(?:remove|add\s+\S+)\s+file\s+(\S+)""")

        for activity in changelog:
            project_name = activity[0]
            release_version = activity[1]
            timestamp = activity[2]
            action = activity[3]
            serial = activity[4]
            try:
                # 创建project
                if action == "create":
                    project_metadata = self.scrape_project_metadata(project_name)
                    if self.json_is_not_found(project_metadata):
                        LOGGER.warning(f"PyPI project metadata not found: {project_name}")
                        continue
                    self.process_save_project_metadata_init(project_metadata)
                # 删除project
                elif action == "remove project":
                    self.mongo_client.set_project_removed(project_name, serial, timestamp)
                    self.mongo_client.set_project_releases_removed(project_name, serial, timestamp)

                # change owner
                elif action.startswith("add Owner"):
                    owner = prs_utils.extract_owner_from_action(action)
                    self.mongo_client.add_project_owner(project_name, owner)
                elif action.startswith("invite Owner"):
                    pass
                elif action.startswith("accepted Owner"):
                    owner = prs_utils.extract_owner_from_action(action)
                    self.mongo_client.add_project_owner(project_name, owner)
                elif action.startswith("remove Owner"):
                    owner = prs_utils.extract_owner_from_action(action)
                    self.mongo_client.remove_project_owner(project_name, owner)
                elif action.startswith("change Owner"):
                    owner = prs_utils.extract_owner_from_action(action)
                    self.mongo_client.change_project_owner_to_maintainer(project_name, owner)

                # change maintainer
                elif action.startswith("add Maintainer"):
                    maintainer = prs_utils.extract_maintainer_from_action(action)
                    self.mongo_client.add_project_maintainer(project_name, maintainer)
                elif action.startswith("invite Maintainer"):
                    pass
                elif action.startswith("accepted Maintainer"):
                    maintainer = prs_utils.extract_maintainer_from_action(action)
                    self.mongo_client.add_project_maintainer(project_name, maintainer)
                elif action.startswith("remove Maintainer"):
                    maintainer = prs_utils.extract_maintainer_from_action(action)
                    self.mongo_client.remove_project_maintainer(project_name, maintainer)
                elif action.startswith("change Maintainer"):
                    maintainer = prs_utils.extract_maintainer_from_action(action)
                    self.mongo_client.change_project_maintainer_to_owner(project_name, maintainer)

                # 创建release/增删文件且当前action release与上一个action release不同
                elif action == "new release" or \
                        action.startswith("yank release") or action.startswith("unyank release") or \
                        (file_action_regex.search(action) and (project_name != pre_project_name or release_version != pre_release_version)):
                    # 更新本地数据库中project元数据
                    project_metadata = self.scrape_project_metadata(project_name)
                    if self.json_is_not_found(project_metadata):
                        LOGGER.warning(f"PyPI project metadata not found: {project_name}")
                        continue
                    project_metadata = self.process_save_project_metadata(project_metadata)
                    if project_metadata is None:
                        LOGGER.error(f"process and save project metadata {project_name} failed")
                        continue

                    # 爬取并存储release元数据
                    release_metadata = self.scrape_release_metadata(project_name, release_version)
                    if self.json_is_not_found(release_metadata):
                        LOGGER.warning("PyPI release metadata not found: " + project_name + " " + release_version)
                        continue
                    self.process_save_release_metadata_init(
                        release_metadata,
                        project_metadata["suspicion"],
                        project_metadata["suspicion_info"]
                    )
                # 删除release
                elif action == "remove release":
                    self.mongo_client.set_release_removed(project_name, release_version, serial, timestamp)
                # 其他操作，主要是新增各类文件，认为随release元数据一起爬取成功，
                else:
                    LOGGER.debug("monitor doesn't support to handle activity currently: " + str(activity))
            except Exception as e:
                LOGGER.error("monitor handle activity " + str(activity) + " failed with: " + str(e))

            pre_project_name = project_name
            pre_release_version = release_version

    def update_popular(self):
        """获取下载量top5000的project列表

        本地存在本月的则在本地load，否则从远端获取并存入本地

        :return: {
            "last_update": time string,
            "query": { ... },
            "rows": [
                {
                    "download_count": download count,
                    "project": project name
                },
                ...
            ]
        }
        """
        LOGGER.info(f"update popular")
        popular = self.mongo_client.load_latest_popular()
        if popular is None or prs_utils.popular_time_need_update(popular["last_update"]):
            try:
                popular = self.scrape_popular_list()
                self.popular = popular
                self.mongo_client.insert_popular(popular)
                LOGGER.info(f"updating popular succeeded")
            except Exception as e:
                LOGGER.error("scrape popular list failed with: " + str(e))
                return None
        else:
            self.popular = popular

    @staticmethod
    def scrape_popular_list():
        """获取最近一个月下载量top5000的project列表

        从GitHub开源项目直接获取：
        https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json

        :return: {
            "last_update": time string,
            "query": { ... },
            "rows": [
                {
                    "download_count": download count,
                    "project": project name
                },
                ...
            ]
        }
        """
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS)
        }
        resp = requests.get(TOP5000_PACKAGES_THIS_MONTH_URL, headers=headers)
        return json.loads(resp.text)

    @staticmethod
    def scrape_projects_latest_serial():
        """获取pypi中现有的全部project最近一次更新对应的serial

        返回的字典较大，时间开销10s+
        :return: dict: { project name: latest serial }
        """
        client = xmlrpc.client.ServerProxy(PYPI_URL)
        return client.list_packages_with_serial()

    @staticmethod
    def get_project_latest_serial(project_name: str):
        """获取指定project的最近一次更新对应的serial

        :param project_name: project name
        :return: latest serial (int)
        """
        return PypiMonitor.scrape_projects_latest_serial()[project_name]

    def load_local_serial(self):
        """从数据库读取本地最新的serial

        :return: latest updated local serial
        """
        return self.mongo_client.load_local_serial()

    @staticmethod
    def scrape_project_metadata(project_name: str):
        """获取project的元数据

        利用PyPI提供的JSON API: https://pypi.org/pypi/{PROJECT}/json

        :param project_name: project名称
        :return: 以json格式返回project元数据，如果project不存在，则返回{"message": "Not Found"}
        """
        prj_meta_url = PypiMonitor.get_project_json_url(project_name)
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS)
        }
        resp = requests.get(prj_meta_url, headers=headers)
        return json.loads(resp.text)

    @staticmethod
    def get_project_json_url(project_name: str):
        """获取存储project元数据的url

        :param project_name: projectname
        :return: str: API for getting metadata of project in JSON format
        """
        return PROJECT_JSON_TEMPLATE.format(PROJECT=project_name)

    @staticmethod
    def scrape_release_metadata(project_name: str, version: str):
        """获取release的元数据

        利用PyPI提供的JSON API: https://pypi.org/pypi/{PROJECT}/{VERSION}/json

        :param project_name: project名称
        :param version: release的版本号
        :return: 以json格式返回project元数据，如果project不存在，则返回{"message": "Not Found"}
        """
        rel_meta_url = PypiMonitor.get_release_json_url(project_name, version)
        headers = {
            "Connection": "close",
            "User-Agent": random.choice(prs_utils.USER_AGENTS)
        }
        resp = requests.get(rel_meta_url, headers=headers)
        return json.loads(resp.text)

    @staticmethod
    def get_release_json_url(project_name: str, version: str):
        """获取存储release元数据的url

        :param project_name: project name
        :param version: release version
        :return: str: API for getting metadata of release in JSON format
        """
        return RELEASE_JSON_TEMPLATE.format(PROJECT=project_name, VERSION=version)

    def process_save_project_metadata_init(self, project_metadata):
        """根据存储需求处理project元数据并存入MongoDB，
        用于初次存储project元数据过程，包括全量爬取/create处理

        主要进行以下操作：
            - 删除弃用字段
            - 计算project投毒可能性
            - 新增项目所需字段
            - 存入数据库
        """
        project_name = project_metadata["info"]["name"]
        project_version = project_metadata["info"]["version"]

        # 删除PyPI API文档中声明未来将被remove/deprecate的字段
        # 包括releases, downloads, has_sig, bugtrack_url

        # The releases key on this response should be considered deprecated,
        # and projects should shift to using the simple API (which can be
        # accessed as JSON via PEP 691) to get this information where possible.
        #
        # In the future, the releases key may be removed from this response.
        if "releases" in project_metadata:
            del project_metadata["releases"]

        # The downloads key on this response should be considered deprecated.
        #
        # It currently always returns -1 and in the future,
        # the downloads key may be removed from this response.
        # 暂不删除，后续可以根据需要自行更新
        # try:
        #     del project_metadata["info"]["downloads"]
        # except KeyError:
        #     pass

        # 计算project投毒可疑度
        suspicion, suspicion_info = self.calculate_project_suspicion(project_name, project_version)

        # 新增项目需要的信息字段
        project_metadata["maintainers"] = []
        project_metadata["owners"] = []
        project_metadata["remove"] = False
        project_metadata["remove_serial"] = None
        project_metadata["remove_time"] = None
        project_metadata["remove_timestamp"] = None
        project_metadata["suspicion"] = suspicion
        project_metadata["suspicion_info"] = suspicion_info
        project_metadata["analyzed"] = False

        # 存入数据库
        self.mongo_client.insert_project(project_metadata)

    def process_save_project_metadata(self, project_metadata):
        """根据存储需求处理project元数据并存入MongoDB，
        用于project更新过程，包括

        主要进行以下操作：
            - 删除弃用字段
            - 存入数据库

        :return: MongoDB Document: project metadata from MongoDB after being updated
        """
        project_name = project_metadata["info"]["name"]
        project_version = project_metadata["info"]["version"]

        # 删除PyPI API文档中声明未来将被remove/deprecate的字段
        # 包括releases, downloads, has_sig, bugtrack_url

        # The releases key on this response should be considered deprecated,
        # and projects should shift to using the simple API (which can be
        # accessed as JSON via PEP 691) to get this information where possible.
        #
        # In the future, the releases key may be removed from this response.
        try:
            del project_metadata["releases"]
        except KeyError:
            pass

        # The downloads key on this response should be considered deprecated.
        #
        # It currently always returns -1 and in the future,
        # the downloads key may be removed from this response.
        # 暂不删除，后续可以根据需要自行更新
        # try:
        #     del project_metadata["info"]["downloads"]
        # except KeyError:
        #     pass

        # 存入数据库
        return self.mongo_client.insert_update_project(project_metadata)

    def process_save_release_metadata_init(self, release_metadata, suspicion: int, suspicion_info: list):
        """根据存储需求处理release元数据并存入MongoDB

        主要进行以下操作：
            - 将文件信息放入下载队列
            - 新增项目所需字段
            - 存入数据库
        """
        project_name = release_metadata["info"]["name"]
        version = release_metadata["info"]["version"]

        # 将文件信息放入下载队列
        if "urls" in release_metadata:
            for url in release_metadata["urls"]:
                self.download_priority_queue.put((-suspicion, project_name, version,
                                                  self._get_download_queue_task_index(), url.copy()))

        # release相关弃用字段体量小，暂无需删除

        # 新增项目所需字段
        release_metadata["remove"] = False
        release_metadata["remove_serial"] = None
        release_metadata["remove_time"] = None
        release_metadata["remove_timestamp"] = None
        release_metadata["suspicion"] = suspicion
        release_metadata["suspicion_info"] = suspicion_info
        release_metadata["analyzed"] = False
        release_metadata["analyzed_files"] = []

        # 存入数据库
        self.mongo_client.insert_release(release_metadata)

    def calculate_project_suspicion(self, project_name, project_version):
        """根据project name和version评估投毒可疑度

        :return: int: suspicious score, list: suspicious info
        """
        suspicion = 0
        suspicion_info = []

        # 检查popular是否更新成功
        if self.popular is None:
            print("update popular failed, system exits")
            LOGGER.error("update popular failed, system exits")
            exit(-1)

        # 比对project name和流行包name，发现typosquatting
        for popular in self.popular["rows"]:
            popular_name = popular["project"]
            download_count = popular["download_count"]
            # 流行包本身
            if project_name == popular_name:
                suspicion = max(suspicion, 4)
                suspicion_info.append(f"Popular Project: popular project {project_name} downloaded {download_count} times")
            # typosquatting，0 < Levenshtein距离 < levenshtein threshold，alice->allice
            if prs_poison_detection.detect_levenshtein(project_name, popular_name, self.levenshtein_distance):
                suspicion = max(suspicion, 7)
                suspicion_info.append(f"Typosquatting: suspected to be typosquatting of project {popular_name}")
            # typosquatting，置换alice->ailce
            if prs_poison_detection.detect_permutation(project_name, popular_name):
                suspicion = max(suspicion, 7)
                suspicion_info.append(f"Typosquatting: suspected to be typosquatting of project {popular_name}")

        # 引入名抢注，抢注其他包的引入名
        if self.mongo_client.find_project_info_by_import_name(project_name) is not None:
            suspicion = max(suspicion, 10)
            suspicion_info.append(f"Import-Name Hijacking: project name is same as the import name of popular project {popular_name}")

        # 包名重用，复用已被删除的包名
        if self.mongo_client.find_project_by_name(project_name, True) is not None:
            suspicion = max(suspicion, 10)
            suspicion_info.append(f"Project Use-After-Free: creating project with name {project_name}, a project with the same name was removed before")

        # 依赖混淆，在pypi抢注私有仓库的包名
        if self.mongo_client.find_private_project_by_name(project_name) is not None:
            suspicion = max(suspicion, 10)
            suspicion_info.append(f"Dependency Confusion: a project with the same name exists in private sources")

        return suspicion, suspicion_info

    def download_save_thread_handler(self):
        """处理下载队列中的任务"""
        while True:
            task = self.download_priority_queue.get()
            LOGGER.info(f"processing download and save task: {task}")
            try:
                self.download_save_file(task)
            except Exception as e:
                LOGGER.error(f"download and save: {task} failed with: {e}")
                continue

    def download_save_file(self, task):
        """下载并保存release文件

        下载PyPI release的tgz和whl文件，保存到MinIO，
        如果suspicion达到检测阈值，将相关信息放入检测队列等待检测，否则从本地文件系统删除文件。
        """
        suspicion = -task[0]
        project_name = task[1]
        release_version = task[2]
        url = task[-1]
        analysis_flag = False

        # 解析信息
        filename = url["filename"]
        download_url = url["url"]
        digests = url["digests"]

        # 是否已存入MinIO
        file_in_minio = False
        download_filepath = None

        # 下载文件到本地
        if self.minio_client.exists_object(self.minio_bucket_name, filename):
            file_in_minio = True
        else:
            download_filepath = prs_utils.download_file_to_dir(download_url, prs_utils.TMP_PATH)
            # 存入MinIO
            metadata = {
                "name": project_name,
                "version": release_version,
                "filename": filename,
                "digests": digests
            }
            self.minio_client.upload_file(bucket_name=self.minio_bucket_name,
                                          filepath=download_filepath,
                                          object_name=filename,
                                          metadata=metadata)

        # 判断是否需要扫描
        if self.analyze_threshold > -1:
            if suspicion >= self.analyze_threshold:
                if self.file_type == "*":
                    analysis_flag = True
                elif filename.endswith(".tar.gz") and self.file_type == "tgz":
                    analysis_flag = True
                elif filename.endswith(".whl") and self.file_type == "whl":
                    analysis_flag = True

        # 需要扫描放入扫描队列
        if analysis_flag:
            if file_in_minio:
                download_filepath = self.minio_client.download_file(filename, prs_utils.TMP_PATH)
            self.analysis_priority_queue.put((-suspicion, project_name, release_version, download_filepath,
                                              self._get_analysis_queue_task_index(), url))
        # 不需要扫描，将其删除
        else:
            if not file_in_minio:
                os.remove(download_filepath)

    def analysis_thread_handler(self):
        """处理扫描队列中的任务"""
        while True:
            task = self.analysis_priority_queue.get()
            LOGGER.info(f"processing analysis task: {task}")
            try:
                self.analyze_save_file(task)
            except Exception as e:
                LOGGER.error(f"analyze: {task} failed with: {e}")
                continue

    def analyze_save_file(self, task):
        """调用scanner检测文件，将结果存入results集合"""
        suspicion = -task[0]
        project_name = task[1]
        release_version = task[2]
        local_file_path = task[3]
        url = task[-1]

        filename = url["filename"]

        # 扫描文件
        analysis_flag = False
        if self.cover_flag:
            analysis_flag = True
        elif self.mongo_client.find_result_by_filename(filename) is None:
            analysis_flag = True

        if analysis_flag:
            results = self.scanner.scan_local_file(local_file_path)
            if results is None:
                os.remove(local_file_path)
                return
        else:
            return

        # results中发现问题，告警
        if results["metrics"]["total"]["cnt"] > 0:
            print("find issues in release:", project_name, release_version, filename)
            LOGGER.critical(f"issues found in project: {project_name} {release_version}, filename: {filename}, "
                            f"results: {results}")

        # 形成结果数据，存入数据库
        results_metadata = {
            "name": project_name,
            "version": release_version,
            "url": url,
            "analyzed_time": datetime.datetime.now(),
            "results": results
        }
        self.mongo_client.update_result(results_metadata)

        # 将release设置为已扫描
        self.mongo_client.set_release_analyzed(project_name, release_version, False, None, filename)

        # 将import_name中与project name不同的结果放入aliases表
        for import_name in results["import_name"]:
            if import_name != project_name:
                self.mongo_client.insert_alias(
                    {
                        "name": project_name,
                        "version": release_version,
                        "import_name": import_name
                    }
                )

        # 完成后删除文件
        os.remove(local_file_path)

    def _update_local_serial(self):
        """更新local serial，并存入本地数据库"""
        self.local_serial = self.curr_serial
        self.mongo_client.insert_serial(self.local_serial)
        LOGGER.info(f"finished, local serial: {self.local_serial}")
        print("finished, local serial:", self.local_serial)

    def _get_analysis_queue_task_index(self):
        """获取下一个入队analysis priority queue的task编号

        预防dict大小比较，用作url前一位int比较

        :return: int: current index of analysis queue task
        """
        self.analysis_queue_index += 1
        return self.analysis_queue_index

    def _get_download_queue_task_index(self):
        """获取下一个入队download priority queue的task编号

        预防dict大小比较，用作url前一位int比较

        :return: int: current index of download queue task
        """
        self.download_queue_index += 1
        return self.download_queue_index

    @staticmethod
    def json_is_not_found(json_data: dict):
        """判断pypi api返回的结果是否有效"""
        if "message" in json_data and json_data["message"] == "Not Found":
            return True
        return False
