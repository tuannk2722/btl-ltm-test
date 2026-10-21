"""HTTP/WebSocket gateway integration test against a live TCP game listener."""
import asyncio
import sys
import unittest
from pathlib import Path
from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'src'))
sys.path.insert(0, str(ROOT / 'client' / 'src'))
from server import GameServer
import web_gateway


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.game = GameServer()
        self.tcp = await asyncio.start_server(self.game.connection, '127.0.0.1', 0)
        web_gateway.TCP_HOST = '127.0.0.1'
        web_gateway.TCP_PORT = self.tcp.sockets[0].getsockname()[1]
        self.runner = web.AppRunner(web_gateway.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        self.http_port = self.site._server.sockets[0].getsockname()[1]
        self.session = ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.tcp.close()
        await self.tcp.wait_closed()

    async def recv_type(self, ws, kind):
        for _ in range(10):
            msg = await asyncio.wait_for(ws.receive_json(), 2)
            if msg['type'] == kind:
                return msg
        raise AssertionError('missing event ' + kind)

    async def test_static_home_and_two_browser_clients(self):
        url = f'http://127.0.0.1:{self.http_port}'
        async with self.session.get(url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn('KeySprint', await resp.text())
        async with self.session.ws_connect(url+'/ws') as a, self.session.ws_connect(url+'/ws') as b:
            await a.send_json({'type': 'HELLO', 'requestId': '1', 'payload': {'name': 'A'}})
            await b.send_json({'type': 'HELLO', 'requestId': '2', 'payload': {'name': 'B'}})
            self.assertEqual((await self.recv_type(a, 'HELLO_RESULT'))['code'], 200)
            self.assertEqual((await self.recv_type(b, 'HELLO_RESULT'))['code'], 200)
            await a.send_json({'type': 'CREATE_ROOM', 'requestId': '3', 'payload': {}})
            code = (await self.recv_type(a, 'ROOM_STATE'))['data']['code']
            self.assertEqual((await self.recv_type(a, 'CREATE_ROOM_RESULT'))['data']['code'], code)
            await b.send_json({'type': 'JOIN_ROOM', 'requestId': '4', 'payload': {'code': code}})
            self.assertEqual(len((await self.recv_type(a, 'ROOM_STATE'))['data']['players']), 2)
            self.assertEqual((await self.recv_type(b, 'ROOM_STATE'))['data']['code'], code)
            self.assertEqual((await self.recv_type(b, 'JOIN_ROOM_RESULT'))['code'], 200)


if __name__ == '__main__':
    unittest.main()
