from PyRepoScanner.utils.basic_tools import *


def test_download_file():
    download_file_to_dir("https://files.pythonhosted.org/packages/af/0b/44c39cf3b18a9280950ad63a579ce395dda4c32193ee9da7ff0aed547094/beautifulsoup4-4.12.2.tar.gz", TMP_PATH)
    download_file_to_dir("https://files.pythonhosted.org/packages/af/0b/44c39cf3b18a9280950ad63a579ce395dda4c32193ee9da7ff0aed547094/beautifulsoup4-4.12.2.tar.gz", TMP_PATH)
    # download_file_to_dir("https://files.pythonhosted.org/packages/af/0b/44c39cf3b18a9280950ad63a579ce395dda4c32193ee9da7ff0aed547094/beautifulsoup4-4.12.2.tar.gz", TMP_PATH)
    # download_file_to_dir("https://files.pythonhosted.org/packages/af/0b/44c39cf3b18a9280950ad63a579ce395dda4c32193ee9da7ff0aed547094/beautifulsoup4-4.12.2.tar.gz", TMP_PATH)
    #
    # download_file_to_dir("https://files.pythonhosted.org/packages/57/f4/a69c20ee4f660081a7dedb1ac57f29be9378e04edfcb90c526b923d4bebc/beautifulsoup4-4.12.2-py3-none-any.whl", TMP_PATH)
    # download_file_to_dir("https://files.pythonhosted.org/packages/57/f4/a69c20ee4f660081a7dedb1ac57f29be9378e04edfcb90c526b923d4bebc/beautifulsoup4-4.12.2-py3-none-any.whl", TMP_PATH)
    # download_file_to_dir("https://files.pythonhosted.org/packages/57/f4/a69c20ee4f660081a7dedb1ac57f29be9378e04edfcb90c526b923d4bebc/beautifulsoup4-4.12.2-py3-none-any.whl", TMP_PATH)
    # download_file_to_dir("https://files.pythonhosted.org/packages/57/f4/a69c20ee4f660081a7dedb1ac57f29be9378e04edfcb90c526b923d4bebc/beautifulsoup4-4.12.2-py3-none-any.whl", TMP_PATH)

    assert os.path.exists(os.path.join(TMP_PATH, "beautifulsoup4-4.12.2(3).tar.gz"))


def test_remove_file():
    remove_file(os.path.join(TMP_PATH, "beautifulsoup4-4.12.2(3).tar.gz"))
    assert not os.path.exists(os.path.join(TMP_PATH, "beautifulsoup4-4.12.2(3).tar.gz"))


def test_remove_dir():
    empty_dir(TMP_PATH)
    assert len(os.listdir(TMP_PATH)) == 1


def test_extract_tar_gz():
    print(extract_tar_gz_to_dir("../../sample/packages/pwntools-4.11.0.tar.gz", TMP_PATH))


def test_extract_whl_to_dir():
    print(extract_whl_to_dir("../../sample/packages/beautifulsoup4-4.12.2-py3-none-any.whl", TMP_PATH))


def test_parse_version_from_tar_gz_filename():
    assert parse_version_from_tar_gz_filename("beautifulsoup4", "beautifulsoup4-4.12.2.tar.gz") == "4.12.2"


def test_parse_filename_from_action():
    assert extract_filename_from_action("add py2.py3 file tencentcloud_sdk_python_cloudhsm-3.0.986-py2.py3-none-any.whl") == "tencentcloud_sdk_python_cloudhsm-3.0.986-py2.py3-none-any.whl"
    assert extract_filename_from_action("add source file tencentcloud-sdk-python-cloudhsm-3.0.986.tar.gz") == "tencentcloud-sdk-python-cloudhsm-3.0.986.tar.gz"
    assert extract_filename_from_action("add py3 file ribs-0.6.1-py3-none-any.whl") == "ribs-0.6.1-py3-none-any.whl"
    assert extract_filename_from_action("add cp38 file NMODL_nightly-0.6.34-cp38-cp38-manylinux_2_17_x86_64.manylinux2014_x86_64.whl") == "NMODL_nightly-0.6.34-cp38-cp38-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    assert extract_filename_from_action("anything") == None
    assert extract_filename_from_action("add py2 file odoo10_addon_sale_commission-10.0.2.6.0.99.dev12-py2-none-any.whl") == "odoo10_addon_sale_commission-10.0.2.6.0.99.dev12-py2-none-any.whl"
    assert extract_filename_from_action("add cp311 file pycde-0.3.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl") == "pycde-0.3.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    assert extract_filename_from_action("remove file nt4PAdyP-0.0.8-py3-none-any.whl") == "nt4PAdyP-0.0.8-py3-none-any.whl"
    assert extract_filename_from_action("remove file moira-python-client-4.1.2.tar.gz") == "moira-python-client-4.1.2.tar.gz"


def test_extract_owner_from_action():
    assert extract_owner_from_action("add Owner NeilJiang") == "NeilJiang"
    assert extract_owner_from_action("invite Owner devhel") == "devhel"
    assert extract_owner_from_action("accepted Owner vanous") == "vanous"
    assert extract_owner_from_action("remove Owner guillaumekln") == "guillaumekln"
    assert extract_owner_from_action("change Owner aidaph to Maintainer") == "aidaph"
