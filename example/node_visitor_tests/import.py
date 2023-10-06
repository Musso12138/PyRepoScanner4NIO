import socket
import requests, urllib3
import base64 as b64
import numpy as np, pandas as pd
import importlib
# from .typo import TYPO
from bs4 import BeautifulSoup, BeautifulStoneSoup
from subprocess import run, call, Popen as subP, check_call as subCC
from PyRepoScanner.scanner.pypi.scanner import PypiScanner as pyScanner

aaa = __import__("base64")
bbb = __import__("base64").b64decode
ccc = __import__("importlib").load_module("os").path.isdir
ddd = importlib.__import__("socket")
eee = importlib.import_module(".path", "os").exists
