from PyRepoScanner.monitor.pypi.monitor import *


pm = PypiMonitor("mongodb://pypi_owner:pypi_owner@localhost:27017")


def test_scrape_projects_from_simple():
    indexes = pm.scrape_all_projects_from_simple_pep503()
    print(indexes["serial"])
    print(indexes["projects"][0:5])


def test_scrape_project_metadata():
    meta = pm.scrape_project_metadata("exapl_www")
    print(meta)


def test_scrape_release_metadata():
    meta = pm.scrape_release_metadata("beautifulsoup4", "4.11.2")
    print(type(meta))


def test_scrape_changelog_last_serial():
    last_serial = pm.scrape_changelog_last_serial()
    print(last_serial)


def test_scrape_changelog_since_serial():
    changelog = pm.scrape_changelog_since_serial(19853000)
    print(changelog)


def test_process_save_project_metadata():
    metadata = pm.scrape_project_metadata("pwntools")
    pm.process_save_project_metadata_init(metadata)

    data = pm.mongo_client.find_project_by_name("pwntools")
    print(data)


def test_scrape_all_projects_from_simple_pep503():
    project_list = pm.scrape_all_projects_from_simple_pep503()
    print(project_list.keys())
    print(project_list["serial"])
    print(len(project_list["projects"]))


def test_scrape_all_projects_from_simple_pep691():
    project_list = pm.scrape_all_projects_from_simple_pep691()
    print(project_list.keys())
    # print(project_list["meta"])
    print(project_list["serial"])
    print(len(project_list["projects"]))
    print(project_list["projects"][:5])


def test_scrape_project_all_versions_from_simple_pep503():
    release_list = pm.scrape_project_all_versions_from_simple_pep503("beautifulsoup4")
    print(release_list)


def test_scrape_project_all_versions_from_simple_pep691():
    release_list = pm.scrape_project_all_versions_from_simple_pep691("beautifulsoup4")
    print(release_list)
    # print(release_list.keys())
    # print(project_list["meta"])


def test_scrape_popular_list():
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2000-02-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2010-02-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2023-02-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2023-04-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2024-11-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    popular_list = pm.scrape_popular_list()
    popular_list["last_update"] = "2024-10-01 08:13:20"
    pm.mongo_client.insert_popular(popular_list)
    print(popular_list)


def test_update_popular():
    pm.update_popular()
    print(pm.popular.keys())
