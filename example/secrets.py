import os
import socket as sk


hostname = sk.gethostname()
computer_name = os.environ["COMPUTERNAME"]
cwd, cwdb = os.getcwd().lstrip("/").rstrip().split("/"), os.getcwdb()
user = __import__("getpass").getuser()
req = sk.socket.connect("127.0.0.1").receive()
