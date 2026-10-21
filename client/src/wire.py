"""Independent PTR/1.0 client implementation. Do not import server code."""
import asyncio
import json
import struct

MAX_FRAME = 16384


def pack(message):
    payload = json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_FRAME:
        raise ValueError('Frame exceeds 16KiB limit')
    return struct.pack('!I', len(payload)) + payload


async def receive(reader):
    prefix = await reader.readexactly(4)
    size = struct.unpack('!I', prefix)[0]
    if size == 0 or size > MAX_FRAME:
        raise ValueError('Invalid server frame')
    return json.loads((await reader.readexactly(size)).decode('utf-8'))
