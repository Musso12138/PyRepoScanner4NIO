import pymongo.errors

import PyRepoScanner.monitor.pypi.monitor as pypi_monitor
import PyRepoScanner.utils.log_utils as prs_log
import PyRepoScanner.utils.mongo_utils as prs_mongo


prs_log.config_logger()
mongo_client = prs_mongo.PRSPypiMongoClient("mongodb://pypi_owner:pypi_owner@localhost:27017")


def test_insert_project():
    metadata = pypi_monitor.PypiMonitor.scrape_project_metadata("beautifulsoup4")
    mongo_client.insert_update_project(metadata)
    res = mongo_client.find_project_by_name("beautifulsoup4")
    print(res)


def test_find_project_by_name():
    res = mongo_client.find_project_by_name("beautifulsoup4")
    print(res)


def test_drop_serials_collection():
    mongo_client.serials_collection.drop()


def test_insert_serial():
    mongo_client.insert_serial(30)
    mongo_client.insert_serial(30)
    mongo_client.insert_serial(30)
    mongo_client.insert_serial(26929999)
    mongo_client.insert_serial(170000009)
    mongo_client.insert_serial(18459000)
    mongo_client.insert_serial(18000000)


def test_load_local_serial():
    latest_serial = mongo_client.load_local_serial()
    print(latest_serial)


def test_load_latest_popular():
    latest_popular = mongo_client.load_latest_popular()
    print(latest_popular)


def test_delete_all():
    mongo_client._delete_all()


def test_drop_all():
    mongo_client._drop_all()
