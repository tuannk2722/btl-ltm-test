"""Browser ⇄ WebSocket ⇄ independent PTR/1.0 TCP server gateway."""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path

from aiohttp import web, WSMsgType
from wire import pack, receive

HERE = Path(__file__).resolve().parent
STATIC = HERE / 'static'
TCP_HOST = os.getenv('CLIENT_TARGET_HOST', 'server')
TCP_PORT = int(os.getenv('CLIENT_TARGET_PORT', '5000'))
WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
WEB_PORT = int(os.getenv('WEB_PORT', '8080'))
LOG = logging.getLogger('ptr.gateway')


async def home(request):
    return web.FileResponse(STATIC / 'index.html')


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=16384)
    await ws.prepare(request)
    try:
        tcp_reader, tcp_writer = await asyncio.wait_for(asyncio.open_connection(TCP_HOST, TCP_PORT), timeout=5)
    except (OSError, asyncio.TimeoutError):
        await ws.send_json({'type': 'ERROR', 'data': {'code': 503, 'message': 'Game server unavailable'}})
        await ws.close()
        return ws

    async def from_server():
        try:
            while not ws.closed:
                await ws.send_json(await receive(tcp_reader))
        except (asyncio.IncompleteReadError, ConnectionError, ValueError, RuntimeError) as exc:
            LOG.debug('TCP disconnected: %s', exc)
        finally:
            if not ws.closed:
                await ws.close()

    async def heartbeat():
        try:
            while not ws.closed:
                await asyncio.sleep(25)
                tcp_writer.write(pack({'type': 'PING', 'requestId': 'gateway-heartbeat', 'payload': {}}))
                await tcp_writer.drain()
        except (asyncio.CancelledError, ConnectionError, OSError):
            pass

    relay = asyncio.create_task(from_server())
    pulse = asyncio.create_task(heartbeat())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    tcp_writer.write(pack(data))
                    await tcp_writer.drain()
                except (json.JSONDecodeError, ValueError, TypeError):
                    await ws.send_json({'type': 'ERROR', 'data': {'code': 400, 'message': 'Invalid client message'}})
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        relay.cancel()
        pulse.cancel()
        await asyncio.gather(relay, pulse, return_exceptions=True)
        tcp_writer.close()
        with contextlib.suppress(ConnectionError, OSError):
            await tcp_writer.wait_closed()
    return ws


async def style(request):
    return web.FileResponse(STATIC / 'style.css')


async def script(request):
    return web.FileResponse(STATIC / 'app.js')


app = web.Application(client_max_size=16384)
app.router.add_get('/', home)
app.router.add_get('/style.css', style)
app.router.add_get('/app.js', script)
app.router.add_get('/ws', websocket)
app.router.add_static('/assets', STATIC, show_index=False)

if __name__ == '__main__':
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
    web.run_app(app, host=WEB_HOST, port=WEB_PORT, print=lambda msg: LOG.info('%s', msg))
