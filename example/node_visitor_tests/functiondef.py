import socket
import base64


def base64_to_exec(encoded, a="a", /, b="b", *args, raw_cmd: str = "c", **kwargs):
    bdecoded = base64.b64decode(encoded)

    def try_exec(cmd):
        exec(cmd)

    try_exec(bdecoded)
    try_exec(raw_cmd)

    return bdecoded
