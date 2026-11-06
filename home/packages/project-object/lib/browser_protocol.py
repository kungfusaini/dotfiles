"""Bounded native-messaging framing shared by the browser host and local client."""
import json
import struct

VERSION = 1
EXTENSION_ID = "gkagbidkbfggbfholmeainnbjjbcapfo"
HOST_NAME = "org.project_object.browser"
MAX_MESSAGE = 1024 * 1024


def receive(stream):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size - len(data))
            if not chunk:
                raise EOFError("Browser bridge disconnected")
            data.extend(chunk)
        return bytes(data)
    size = struct.unpack("<I", exact(4))[0]
    if not 0 < size <= MAX_MESSAGE:
        raise ValueError("Browser bridge message exceeds limit")
    value = json.loads(exact(size))
    if not isinstance(value, dict):
        raise ValueError("Browser bridge message must be an object")
    return value


def send(stream, value):
    data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if not 0 < len(data) <= MAX_MESSAGE:
        raise ValueError("Browser bridge message exceeds limit")
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()
