from PyRepoScanner.utils.minio_utils import *


def test_upload_file():
    mc = MinioClient()
    on = mc.upload_file("./tmp/beautifulsoup4-4.12.2.tar.gz", "beautifulsoup4-4.12.2.tar.gz", metadata={"filename": "beautifulsoup4-4.12.2.tar.gz"})
    print(on)
    on = mc.upload_file("./tmp/beautifulsoup4-4.12.2(1).tar.gz", "beautifulsoup4-4.12.2(1).tar.gz", metadata={"filename": "beautifulsoup4-4.12.2.tar.gz"})
    print(on)


def test_download_file():
    mc = MinioClient(host="127.0.0.1:9000", access_key=ON4DfLIvn4L5QngLEnQM, secret_key="xAvHXThgJr23Ks5IFSyYp0LXCJj7s2RuxO1Tlbwu")
    fp = mc.download_file("acryl-datahub-0.9.2.4rc2.tar.gz", TMP_PATH)
    print(fp)
