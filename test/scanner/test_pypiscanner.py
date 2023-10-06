import os
import astpretty
from PyRepoScanner.scanner.pypi.scanner import PypiScanner


def test_load_rules():
    print(os.getcwd())
    scanner = PypiScanner("../../rules")
    print(scanner.rules)


def test_parse_ast():
    print(os.getcwd())
    scanner = PypiScanner("../rules.yml")
    node = scanner._parse_ast("../sample/packages/incode/pytagora-1.2/pytagora/functions.py")
    print(type(node))
    astpretty.pprint(node, show_offsets=True)


def test_scan_local_file():
    print(os.getcwd())
    scanner = PypiScanner("../../rules.yml")
    scanner.scan_local_py_file("")


def test_getattr():
    s = getattr(os, "getcwd")
    print(s())
