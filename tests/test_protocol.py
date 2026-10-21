"""Real-socket integration tests: framing, concurrency, rooms, abnormal input and race."""
import asyncio
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'src'))
from server import GameServer, frame


class Peer:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.serial = 0

    async def recv(self):
        header = await asyncio.wait_for(self.reader.readexactly(4), timeout=3)
        n = struct.unpack('!I', header)[0]
        return json.loads(await self.reader.readexactly(n))

    async def command(self, name, payload=None, fragment=False):
        self.serial += 1
        request_id = str(self.serial)
        raw = frame({'type': name, 'requestId': request_id, 'payload': payload or {}})
        if fragment:
            self.writer.write(raw[:2])
            await self.writer.drain()
            await asyncio.sleep(.01)
            self.writer.write(raw[2:8])
            await self.writer.drain()
            self.writer.write(raw[8:])
        else:
            self.writer.write(raw)
        await self.writer.drain()
        while True:
            msg = await self.recv()
            if msg.get('requestId') == request_id:
                return msg

    def close(self):
        self.writer.close()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = GameServer()
        self.listener = await asyncio.start_server(self.app.connection, '127.0.0.1', 0)
        self.port = self.listener.sockets[0].getsockname()[1]
        self.peers = []

    async def asyncTearDown(self):
        for peer in self.peers:
            peer.close()
        await asyncio.gather(*(p.writer.wait_closed() for p in self.peers), return_exceptions=True)
        await asyncio.sleep(.025)
        self.listener.close()
        await self.listener.wait_closed()
        for room in self.app.rooms.values():
            if room.end_task:
                room.end_task.cancel()

    async def peer(self, name=None):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        peer = Peer(reader, writer)
        self.peers.append(peer)
        if name:
            reply = await peer.command('HELLO', {'name': name})
            self.assertEqual(reply['code'], 200)
        return peer

    async def test_fragmented_frame_and_multiple_clients(self):
        alice = await self.peer()
        hello = await alice.command('HELLO', {'name': 'alice'}, fragment=True)
        self.assertEqual(hello['data']['name'], 'alice')
        # Coalesce requests in a single TCP write.
        alice.writer.write(frame({'type': 'PING', 'requestId': 'a', 'payload': {}}) + frame({'type': 'PING', 'requestId': 'b', 'payload': {}}))
        await alice.writer.drain()
        a, b = await alice.recv(), await alice.recv()
        self.assertEqual([a['requestId'], b['requestId']], ['a', 'b'])
        self.assertEqual([a['code'], b['code']], [200, 200])

    async def test_rooms_host_transfer_and_disconnect(self):
        a = await self.peer('alice')
        b = await self.peer('bob')
        created = await a.command('CREATE_ROOM')
        code = created['data']['code']
        joined = await b.command('JOIN_ROOM', {'code': code})
        self.assertEqual(joined['code'], 200)
        self.assertEqual((await b.command('START_RACE'))['code'], 403)
        self.assertEqual((await a.command('START_RACE'))['code'], 409)
        a.close()  # abrupt disconnect, no QUIT
        for _ in range(40):
            if len(self.app.clients) == 1:
                break
            await asyncio.sleep(.025)
        state = await b.command('GET_STATE')
        self.assertEqual(state['data']['hostId'], next(iter(self.app.clients)).id)
        self.assertEqual(state['data']['players'][0]['name'], 'bob')
        b.close()
        await asyncio.sleep(.05)
        self.assertEqual(len(self.app.rooms), 0)

    async def test_invalid_json_and_oversized_frame_do_not_kill_server(self):
        p = await self.peer()
        p.writer.write(struct.pack('!I', 6) + b'broken')
        await p.writer.drain()
        msg = await p.recv()
        self.assertEqual(msg['data']['code'], 400)
        self.assertEqual((await p.command('PING'))['code'], 200)
        bad = await self.peer()
        bad.writer.write(struct.pack('!I', 999999))
        await bad.writer.drain()
        self.assertEqual((await bad.recv())['data']['code'], 413)
        ok = await self.peer('healthy')
        self.assertEqual((await ok.command('PING'))['code'], 200)

    async def test_concurrent_clients(self):
        async def visitor(i):
            p = await self.peer(f'user{i}')
            return await p.command('PING')
        result = await asyncio.gather(*(visitor(i) for i in range(40)))
        self.assertTrue(all(x['code'] == 200 for x in result))
        self.assertEqual(len(self.app.clients), 40)

    async def test_race_full_finish_and_results(self):
        a = await self.peer('alpha')
        b = await self.peer('beta')
        code = (await a.command('CREATE_ROOM'))['data']['code']
        # Short original challenge keeps the finish test fast while exercising real timing.
        self.app.rooms[code].passage = 'abcdefghij'
        await b.command('JOIN_ROOM', {'code': code})
        await a.command('SET_READY', {'ready': True})
        await b.command('SET_READY', {'ready': True})
        self.assertEqual((await a.command('START_RACE'))['code'], 200)
        await asyncio.sleep(3.05)
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': 'abcdefghij'}))['code'], 200)
        first = (await a.command('GET_STATE'))['data']
        self.assertEqual(first['phase'], 'racing')
        self.assertIsNotNone(first['players'][0]['finishSeconds'])
        await asyncio.sleep(.04)
        self.assertEqual((await b.command('RACE_PROGRESS', {'typed': 'abcdefghij'}))['code'], 200)
        result = (await b.command('GET_STATE'))['data']
        self.assertEqual(result['phase'], 'finished')
        self.assertLess(result['players'][0]['finishSeconds'], result['players'][1]['finishSeconds'])

    async def test_race_authority_and_progress_validation(self):
        a = await self.peer('alpha')
        b = await self.peer('beta')
        code = (await a.command('CREATE_ROOM'))['data']['code']
        await b.command('JOIN_ROOM', {'code': code})
        await a.command('SET_READY', {'ready': True})
        await b.command('SET_READY', {'ready': True})
        begin = await a.command('START_RACE')
        self.assertEqual(begin['code'], 200)
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': 'A'}))['code'], 409)
        await asyncio.sleep(3.04)
        state = (await a.command('GET_STATE'))['data']
        self.assertEqual(state['phase'], 'racing')
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': 'zzzzzz'}))['code'], 422)
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': state['text'][:10]}))['code'], 200)
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': state['text'][:9]}))['code'], 422)
        self.assertEqual((await a.command('RACE_PROGRESS', {'typed': state['text']}))['code'], 422)
        self.assertEqual((await b.command('GET_STATE'))['data']['players'][0]['correct'], 10)


if __name__ == '__main__':
    unittest.main()
