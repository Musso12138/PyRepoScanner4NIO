import os
import subprocess
from os import system as sys


exec("something bad")

y = os.popen
z = sys

y(cmd="something bad")
z(command="something bad")

__import__("subprocess").call(args="something bad")
