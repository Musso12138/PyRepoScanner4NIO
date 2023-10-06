import logging
import datetime
import typing
import pymongo
import pymongo.errors
from pymongo import MongoClient
from dataclasses import dataclass
from typing import Union, Optional


LOGGER = logging.getLogger()


@dataclass
class PRSPypiMongoClient:
    mongo_uri: str

    def __post_init__(self):
        self.client = MongoClient(self.mongo_uri)
        self.pypi_db = self.client["pypi"]
        # projects元数据
        self.projects_collection = self.pypi_db["projects"]
        # releases元数据
        self.releases_collection = self.pypi_db["releases"]
        # results集合，以文件md5索引对python包的检测结果
        self.results_collection = self.pypi_db["results"]
        # aliases集合，存储project name, project version -> import names间的关系
        self.aliases_collection = self.pypi_db["aliases"]
        # serials集合，记录本地更新的serial
        self.serials_collection = self.pypi_db["serials"]
        # 流行包集合
        self.popular_collection = self.pypi_db["popular"]
        # 私有仓库内容集合
        self.private_collection = self.pypi_db["private"]

        if self.load_local_serial() is None:
            self._config()

    def _config(self):
        """初次连接时为各个集合建立合适的索引"""
        # projects collection
        self.projects_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("remove", pymongo.ASCENDING),
                ("remove_serial", pymongo.DESCENDING)
            ],
            unique=True
        )
        self.projects_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
            ]
        )
        self.projects_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("remove", pymongo.ASCENDING),
            ]
        )
        self.projects_collection.create_index(
            [
                ("info.author", pymongo.ASCENDING),
            ]
        )
        self.projects_collection.create_index(
            [
                ("analyzed", pymongo.ASCENDING),
            ]
        )
        self.projects_collection.create_index(
            [
                ("suspicion", pymongo.ASCENDING),
            ]
        )

        # releases collection
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("info.version", pymongo.ASCENDING),
                ("last_serial", pymongo.DESCENDING),
                ("remove", pymongo.ASCENDING),
                ("remove_serial", pymongo.DESCENDING)
            ],
            unique=True
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("info.version", pymongo.ASCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("remove", pymongo.ASCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("info.version", pymongo.ASCENDING),
                ("remove", pymongo.ASCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("info.version", pymongo.ASCENDING),
                ("remove", pymongo.ASCENDING),
                ("remove_serial", pymongo.DESCENDING)
            ]
        )
        self.releases_collection.create_index(
            [
                ("suspicion", pymongo.DESCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("info.name", pymongo.ASCENDING),
                ("analyzed", pymongo.ASCENDING),
            ]
        )
        self.releases_collection.create_index(
            [
                ("analyzed", pymongo.ASCENDING),
            ]
        )

        # results collection
        self.results_collection.create_index(
            [
                ("url.filename", pymongo.ASCENDING)
            ],
            unique=True
        )
        self.results_collection.create_index(
            [
                ("url.md5_digest", pymongo.ASCENDING)
            ]
        )
        self.results_collection.create_index(
            [
                ("url.digests.sha256", pymongo.ASCENDING)
            ]
        )
        self.results_collection.create_index(
            [
                ("url.digests.blake2b_256", pymongo.ASCENDING)
            ]
        )
        self.results_collection.create_index(
            [
                ("name", pymongo.ASCENDING)
            ]
        )
        self.results_collection.create_index(
            [
                ("name", pymongo.ASCENDING),
                ("version", pymongo.ASCENDING)
            ]
        )

        # aliases collection
        self.aliases_collection.create_index(
            [
                ("name", pymongo.ASCENDING),
                ("version", pymongo.ASCENDING),
                ("import_name", pymongo.ASCENDING)
            ],
            unique=True
        )
        self.aliases_collection.create_index(
            [
                ("name", pymongo.ASCENDING),
            ]
        )
        self.aliases_collection.create_index(
            [
                ("name", pymongo.ASCENDING),
                ("version", pymongo.ASCENDING)
            ]
        )
        self.aliases_collection.create_index(
            [
                ("import_name", pymongo.ASCENDING),
            ]
        )

        # serials collection
        self.serials_collection.create_index(
            [
                ("serial", pymongo.DESCENDING)
            ],
            unique=True
        )

        # popular collection
        self.popular_collection.create_index(
            [
                ("last_update", pymongo.DESCENDING)
            ],
            unique=True
        )

        # private collection
        self.private_collection.create_index(
            [
                ("name", pymongo.ASCENDING)
            ],
            unique=True
        )

    def insert_project(self, project_metadata):
        """插入一条project元数据

        格式为：
        在https://pypi.org/pypi/<project>/json API的JSON基础上，
        {
            raw JSON data replied by PyPI API...,
            "maintainers": [ maintainer1, maintainer2, ... ],
            "owners": [ owner1, owner2, ... ],
            "remove": True/False,
            "remove_serial": project removed serial,
            "remove_time": local time when remove detected,
            "remove_timestamp": timestamp when project removed,
            "suspicion": poisoning suspicion score,
            "suspicion_info": reason for the suspicion score,
            "analyzed": True/False,
        }
        """
        try:
            self.projects_collection.insert_one(project_metadata)
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert project {project_metadata['info']['name']} failed with: {e}")

    def insert_update_project(self, project_metadata: dict):
        """插入一条project元数据，不存在则insert，存在则update

        格式为：
        在https://pypi.org/pypi/<project>/json API的JSON基础上，
        {
            raw JSON data replied by PyPI API...,
            "maintainers": [ maintainer1, maintainer2, ... ],
            "owners": [ owner1, owner2, ... ],
            "remove": True/False,
            "remove_serial": project removed serial,
            "remove_time": local time when remove detected,
            "remove_timestamp": timestamp when project removed,
            "suspicion": poisoning suspicion score,
            "suspicion_info": reason for the suspicion score,
            "analyzed": True/False,
        }
        """
        project_name = project_metadata["info"]["name"]
        project_version = project_metadata["info"]["version"]

        curr_proj = self.find_project_by_name(project_name, False)
        if curr_proj is None:
            try:
                self.projects_collection.insert_one(project_metadata)
            except Exception as e:
                LOGGER.error(f"mongo insert project {project_name} failed with: {e}")
            return project_metadata
        else:
            analyzed = curr_proj["analyzed"]
            if project_version != curr_proj["info"]["version"]:
                analyzed = False
            try:
                return self.projects_collection.find_one_and_update(
                    filter={
                        "info.name": project_name,
                        "remove": False
                    },
                    update={
                        "$set": {
                            "info": project_metadata["info"],
                            "last_serial": project_metadata["last_serial"],
                            "urls": project_metadata["urls"],
                            "vulnerabilities": project_metadata["vulnerabilities"],
                            "analyzed": analyzed
                        }
                    },
                    return_document=pymongo.ReturnDocument.AFTER
                )
            except Exception as e:
                LOGGER.error(f"mongo update project {project_name} failed with: {e}")
        return None

    def set_project_removed(self, project_name: str, serial: int, timestamp: int):
        """将project设置为removed"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$set": {
                        "remove": True,
                        "remove_serial": serial,
                        "remove_time": datetime.datetime.fromtimestamp(timestamp),
                        "remove_timestamp": timestamp,
                    }
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo set project {project_name} removed failed with: {e}")

    def add_project_owner(self, project_name: str, owner: str):
        """为project新增owner"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$push": {"owners", owner}
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo add owner {owner} to project {project_name} failed with: {e}")

    def remove_project_owner(self, project_name: str, owner: str):
        """为project删除owner"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$pull": {"owners", owner}
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo remove owner {owner} to project {project_name} failed with: {e}")

    def change_project_owner_to_maintainer(self, project_name: str, owner: str):
        """为project将owner转为maintainer"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$pull": {"owners", owner},
                    "$push": {"maintainers", owner},
                }
            )
        except Exception as e:
            LOGGER.error("mongo change owner " + owner + " to maintainer of project " + project_name + " failed with: " + str(e))

    def add_project_maintainer(self, project_name: str, maintainer: str):
        """为project新增maintainer"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$push": {"maintainers", maintainer}
                }
            )
        except Exception as e:
            LOGGER.error("mongo add maintainer " + maintainer + " to project " + project_name + " failed with: " + str(e))

    def remove_project_maintainer(self, project_name: str, maintainer: str):
        """为project删除maintainer"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$pull": {"maintainers", maintainer}
                }
            )
        except Exception as e:
            LOGGER.error("mongo remove maintainer " + maintainer + " to project " + project_name + " failed with: " + str(e))

    def change_project_maintainer_to_owner(self, project_name: str, maintainer: str):
        """为project将maintainer转为owner"""
        try:
            self.projects_collection.update_one(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$pull": {"maintainers", maintainer},
                    "$push": {"owners", maintainer},
                }
            )
        except Exception as e:
            LOGGER.error("mongo change maintainer " + maintainer + " to owner of project " + project_name + " failed with: " + str(e))

    def find_project_by_name(self, project_name: str, remove: bool):
        """根据名称搜索project

        :return: dict: project(not removed) metadata / None
        """
        project_metadata = self.projects_collection.find_one(
            filter={
                "info.name": project_name,
                "remove": remove
            },
        )
        return project_metadata

    def insert_release(self, release_metadata):
        """插入一条release元数据

        格式为：
        在https://pypi.org/pypi/<project>/<version>/json API的JSON基础上，
        {
            raw JSON data replied by PyPI API...,
            "remove": True/False,
            "remove_serial": project removed serial,
            "remove_time": local time when remove detected,
            "remove_timestamp": timestamp when release removed,
            "suspicion": poisoning suspicion score,
            "suspicion_info": reason for the suspicion score,
            "analyzed": True/False,
            "analyzed_files": [filename1, filename2],
        }
        """
        try:
            self.releases_collection.insert_one(release_metadata)
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert release {release_metadata['info']['name']} {release_metadata['info']['version']} "
                         f"failed with: {e}")

    def set_project_releases_removed(self, project_name: str, serial: int, timestamp: int):
        """将project下的全部release设置为removed"""
        try:
            self.releases_collection.update_many(
                filter={
                    "info.name": project_name,
                    "remove": False
                },
                update={
                    "$set": {
                        "remove": True,
                        "remove_serial": serial,
                        "remove_time": datetime.datetime.fromtimestamp(timestamp),
                        "remove_timestamp": timestamp,
                    }
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo set releases of project {project_name} removed failed with: {e}")

    def set_release_removed(self, project_name: str, release_version: str,
                            serial: int, timestamp: int):
        """将release设置为removed"""
        try:
            self.releases_collection.update_one(
                filter={
                    "info.name": project_name,
                    "info.version": release_version,
                    "remove": False
                },
                update={
                    "$set": {
                        "remove": True,
                        "remove_serial": serial,
                        "remove_time": datetime.datetime.fromtimestamp(timestamp),
                        "remove_timestamp": timestamp,
                    }
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo set release {project_name} {release_version} removed failed with: {e}")

    def set_release_analyzed(self, project_name: str, release_version: str, remove: bool, remove_serial: Optional[int], analyzed_filename: str):
        """将release设置为analyzed"""
        try:
            self.releases_collection.update_one(
                filter={
                    "info.name": project_name,
                    "info.version": release_version,
                    "remove": remove,
                    "remove_serial": remove_serial
                },
                update={
                    "$set": {"analyzed": True},
                    "$addToSet": {"analyzed_files": analyzed_filename}
                }
            )
        except Exception as e:
            LOGGER.error(f"mongo set release {project_name} {release_version} analyzed failed with: {e}")

    def insert_result(self, result):
        """插入一条result检测数据

        格式为：
        {
            "name": project name,
            "version": release version,
            "url": {
                url data from release metadata...
            },
            "analyzed_time": analyze time,
            "results": {
                analysis results from scanner...
            }
        }
        """
        try:
            self.results_collection.insert_one(result)
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert result failed with: {e}")

    def update_result(self, result):
        """覆盖或插入一条result"""
        try:
            self.results_collection.update_one(
                filter={
                    "url.filename": result["url"]["filename"]
                },
                update={
                    "$set": result
                },
                upsert=True
            )
        except Exception as e:
            LOGGER.error(f"mongo update result failed with: {e}")

    def find_result_by_filename(self, filename: str):
        """根据filename搜索并返回result"""
        return self.results_collection.find_one(
            filter={
                "url.filename": filename
            }
        )

    def insert_alias(self, alias):
        """插入一条alias数据

        每个project version可能包含多个import name，逐个insert即可

        格式为：
        {
            "name": project name,
            "version": release version,
            "import_name": name,
        }
        """
        try:
            self.aliases_collection.insert_one(alias)
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert alias failed with: {e}")

    def find_project_info_by_import_name(self, alias):
        """根据import name检索project信息

        由于只有当project name与import name不同时才会被存入此表，
        本函数用于发现是否存在引入名抢注攻击
        """

    def find_alias_by_name(self, project_name):
        """根据名称搜索alias

        :return: dict: alias / None
        """
        alias = self.aliases_collection.find_one(
            filter={
                "name": project_name,
            },
        )
        return alias

    def find_alias_by_name_version(self, project_name, release_version):
        """根据名称版本搜索alias

        :return: dict: alias / None
        """
        alias = self.aliases_collection.find_one(
            filter={
                "name": project_name,
                "version": release_version,
            },
        )
        return alias

    def insert_serial(self, serial):
        """插入一个serial，插入时加入本地时间"""
        try:
            self.serials_collection.insert_one(
                {
                    "serial": serial,
                    "time": datetime.datetime.now()
                }
            )
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert serial failed with: {e}")

    def load_local_serial(self):
        """加载本地最近一次更新到的serial"""
        serial = self.serials_collection.find_one(
            sort=[
                ("serial", pymongo.DESCENDING)
            ]
        )
        if serial is not None:
            return serial["serial"]
        return None

    def insert_popular(self, popular_data):
        """插入一条popular数据

        格式为：{
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
        try:
            self.popular_collection.insert_one(popular_data)
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            LOGGER.error(f"mongo insert popular failed with: {e}")

    def load_latest_popular(self):
        """加载最近一条popular数据"""
        pipeline = [
            {
                "$project": {
                    "_id": 1,
                    "last_update": {
                        "$dateFromString": {
                            "dateString": "$last_update",
                            "format": "%Y-%m-%d %H:%M:%S"
                        }
                    },
                    "rows": 1
                }
            },
            {
                "$sort": {
                    "last_update": -1
                }
            },
            {
                "$limit": 1
            }
        ]

        result = list(self.popular_collection.aggregate(pipeline))

        if result:
            return result[0]
        else:
            return None

    def update_private(self, private):
        """插入一条private数据

        格式为:
        {
            "name": project_name,
            "version_list": [
                version1,
                version2,
                ...
            ]
        }
        """
        try:
            self.private_collection.update_one(
                filter={
                    "name": private["name"]
                },
                update={
                    "$set": private
                },
                upsert=True
            )
        except Exception as e:
            LOGGER.error(f"mongo update private failed with: {e}")

    def find_private_project_by_name(self, project_name):
        return self.private_collection.find_one(
            filter={
                "name": project_name,
            },
        )

    def _delete_all(self):
        """清空pypi数据库中全部集合的内容"""
        for coll_name in self.pypi_db.list_collection_names():
            self.pypi_db.get_collection(coll_name).delete_many({})

    def _drop_all(self):
        """删除pypi数据库的全部collection"""
        for coll_name in self.pypi_db.list_collection_names():
            self.pypi_db.drop_collection(coll_name)
