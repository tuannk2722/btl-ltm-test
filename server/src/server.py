"""PTR/1.0 authoritative multiplayer typing server (TCP, length-prefixed JSON)."""
import asyncio
import json
import logging
import os
import secrets
import struct
import time
from dataclasses import dataclass, field

MAX_FRAME = 16384
READ_TIMEOUT = int(os.getenv('READ_TIMEOUT', '90'))
MAX_CLIENTS = int(os.getenv('MAX_CLIENTS', '200'))
MAX_ROOMS = int(os.getenv('MAX_ROOMS', '100'))
MAX_PLAYERS = 8
COUNTDOWN = 3
RACE_LIMIT_SECONDS = 180
LOG = logging.getLogger('ptr.server')

# Original sample passages; no third-party text/assets are redistributed.
PASSAGES = [
    'A small habit becomes a powerful skill when it is practiced every day. Focus on the next key, relax your hands, and keep a steady rhythm. Accuracy matters more than rushing because confident movement gradually leads to speed. Each finished sentence is another step forward.',
    'Across the quiet city, the morning trains begin to move. People carry notebooks, coffee, and bright ideas to work. A clear plan makes a difficult task simpler, while patience helps a team solve problems together. Every good result starts with careful attention.',
    'The first computer networks connected a few distant machines. Today, messages travel between millions of devices in moments. Reliable communication depends on clear rules, sensible timeouts, and software that continues working when connections fail.',
    'Learning to type is like learning an instrument. At first, every movement requires attention. With steady practice, familiar patterns become natural. The aim is not to press keys as fast as possible, but to make each movement precise and comfortable.',
]


def frame(message):
    data = json.dumps(message, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    if len(data) > MAX_FRAME:
        raise ValueError('outbound frame too large')
    return struct.pack('!I', len(data)) + data


class ProtocolError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(eq=False)
class Client:
    writer: asyncio.StreamWriter
    id: str = field(default_factory=lambda: secrets.token_hex(4))
    name: str = ''
    room: str | None = None
    outbound: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=128))
    closing: bool = False
    sender: asyncio.Task | None = None


@dataclass
class Racer:
    client: Client
    ready: bool = False
    correct: int = 0
    finished: float | None = None
    dnf: bool = False
    last_event: float = 0


@dataclass
class Room:
    code: str
    host: str
    passage: str
    racers: dict[str, Racer] = field(default_factory=dict)
    phase: str = 'lobby'
    start_mono: float = 0
    start_unix: int = 0
    end_task: asyncio.Task | None = None


class GameServer:
    def __init__(self):
        self.clients: set[Client] = set()
        self.rooms: dict[str, Room] = {}
        self.counter = 0

    def enqueue(self, client, message):
        if client.closing:
            return
        try:
            client.outbound.put_nowait(frame(message))
        except (asyncio.QueueFull, ValueError):
            # Disconnect a slow or non-reading peer, rather than stall other racers.
            client.closing = True
            client.writer.close()

    def reply(self, client, command, request_id, data=None, error=None):
        code = error.code if error else (201 if command == 'CREATE_ROOM' else 200)
        self.enqueue(client, {
            'type': f'{command}_RESULT', 'requestId': request_id,
            'code': code, 'status': 'OK' if not error else 'ERROR',
            'data': data or {}, 'message': str(error) if error else '',
        })

    def event(self, client, name, data):
        self.enqueue(client, {'type': name, 'data': data})

    def snapshot(self, room):
        now = time.monotonic()
        elapsed = max(0.001, now - room.start_mono) if room.phase != 'lobby' else 0.001
        return {
            'code': room.code, 'hostId': room.host, 'phase': room.phase,
            'text': room.passage, 'startAtUnixMs': room.start_unix,
            'serverUnixMs': int(time.time() * 1000),
            'players': [{
                'id': r.client.id, 'name': r.client.name, 'ready': r.ready,
                'correct': r.correct, 'length': len(room.passage),
                'wpm': round(r.correct / 5 * 60 / max(1, r.finished or elapsed), 1)
                if room.phase != 'lobby' else 0,
                'finishSeconds': round(r.finished, 3) if r.finished is not None else None,
                'dnf': r.dnf,
            } for r in room.racers.values()],
        }

    def broadcast(self, room):
        state = self.snapshot(room)
        for racer in list(room.racers.values()):
            self.event(racer.client, 'ROOM_STATE', state)

    def room_for(self, client):
        room = self.rooms.get(client.room or '')
        if room is None or client.id not in room.racers:
            raise ProtocolError(409, 'Not in a room')
        return room

    def require_hello(self, client):
        if not client.name:
            raise ProtocolError(401, 'Send HELLO first')

    async def dispatch(self, client, message):
        if not isinstance(message, dict):
            raise ProtocolError(400, 'Expected a JSON object')
        command = message.get('type')
        request_id = message.get('requestId')
        payload = message.get('payload', {})
        if not isinstance(command, str) or not isinstance(request_id, str) or len(request_id) > 64 or not isinstance(payload, dict):
            raise ProtocolError(400, 'type, requestId and payload are required')
        if command == 'HELLO':
            if client.name:
                raise ProtocolError(409, 'Already introduced')
            name = payload.get('name')
            if not isinstance(name, str) or not (1 <= len(name.strip()) <= 20) or any(ord(ch) < 32 for ch in name):
                raise ProtocolError(400, 'Name must contain 1-20 visible characters')
            client.name = name.strip()
            return {'id': client.id, 'name': client.name, 'version': 'PTR/1.0'}
        if command == 'PING':
            return {'serverUnixMs': int(time.time() * 1000)}
        self.require_hello(client)
        if command == 'CREATE_ROOM':
            if client.room:
                raise ProtocolError(409, 'Leave your current room first')
            if len(self.rooms) >= MAX_ROOMS:
                raise ProtocolError(503, 'Room capacity reached')
            code = secrets.token_hex(3).upper()
            while code in self.rooms:
                code = secrets.token_hex(3).upper()
            room = Room(code, client.id, PASSAGES[self.counter % len(PASSAGES)])
            self.counter += 1
            room.racers[client.id] = Racer(client)
            self.rooms[code] = room
            client.room = code
            self.broadcast(room)
            return {'code': code}
        if command == 'JOIN_ROOM':
            if client.room:
                raise ProtocolError(409, 'Leave your current room first')
            code = payload.get('code')
            if not isinstance(code, str):
                raise ProtocolError(400, 'Room code required')
            room = self.rooms.get(code.strip().upper())
            if room is None:
                raise ProtocolError(404, 'Room not found')
            if room.phase != 'lobby':
                raise ProtocolError(409, 'Race already started')
            if len(room.racers) >= MAX_PLAYERS:
                raise ProtocolError(409, 'Room is full')
            room.racers[client.id] = Racer(client)
            client.room = room.code
            self.broadcast(room)
            return {'code': room.code}
        if command == 'GET_STATE':
            return self.snapshot(self.room_for(client))
        if command == 'LEAVE_ROOM':
            room = self.room_for(client)
            self.leave(client)
            return {'left': room.code}
        if command == 'SET_READY':
            room = self.room_for(client)
            if room.phase != 'lobby':
                raise ProtocolError(409, 'Race is not in lobby')
            ready = payload.get('ready')
            if not isinstance(ready, bool):
                raise ProtocolError(400, 'ready must be boolean')
            room.racers[client.id].ready = ready
            self.broadcast(room)
            return {'ready': ready}
        if command == 'START_RACE':
            room = self.room_for(client)
            if client.id != room.host:
                raise ProtocolError(403, 'Only host can start')
            if room.phase != 'lobby':
                raise ProtocolError(409, 'Race already started')
            if len(room.racers) < 2 or any(not r.ready for r in room.racers.values()):
                raise ProtocolError(409, 'At least two players must be ready')
            room.phase = 'countdown'
            room.start_mono = time.monotonic() + COUNTDOWN
            room.start_unix = int(time.time() * 1000) + COUNTDOWN * 1000
            room.end_task = asyncio.create_task(self.race_lifecycle(room))
            self.broadcast(room)
            return {'startAtUnixMs': room.start_unix}
        if command == 'RACE_PROGRESS':
            room = self.room_for(client)
            now = time.monotonic()
            if room.phase != 'racing' or now < room.start_mono:
                raise ProtocolError(409, 'Race is not active yet')
            racer = room.racers[client.id]
            if racer.finished is not None or racer.dnf:
                raise ProtocolError(409, 'Player already finished')
            typed = payload.get('typed')
            if not isinstance(typed, str) or len(typed) > len(room.passage):
                raise ProtocolError(400, 'Invalid typed prefix')
            if not room.passage.startswith(typed) or len(typed) < racer.correct:
                raise ProtocolError(422, 'Prefix mismatch or progress rollback')
            elapsed = max(0.0, now - room.start_mono)
            # A coarse velocity gate rejects instant full-text submissions; not a secure anti-bot measure.
            if len(typed) > 12 + 35 * elapsed:
                raise ProtocolError(422, 'Progress is unrealistically fast')
            if len(typed) == racer.correct:
                return {'accepted': racer.correct}
            racer.correct = len(typed)
            if racer.correct == len(room.passage):
                racer.finished = elapsed
            if now - racer.last_event >= 0.1 or racer.finished is not None:
                racer.last_event = now
                self.broadcast(room)
            if all(r.finished is not None or r.dnf for r in room.racers.values()):
                self.finish_room(room)
            return {'accepted': racer.correct}
        if command == 'QUIT':
            return {'bye': True}
        raise ProtocolError(400, 'Unknown command')

    async def race_lifecycle(self, room):
        try:
            await asyncio.sleep(COUNTDOWN)
            if self.rooms.get(room.code) is not room or room.phase != 'countdown':
                return
            room.phase = 'racing'
            self.broadcast(room)
            await asyncio.sleep(RACE_LIMIT_SECONDS)
            if room.phase == 'racing':
                for racer in room.racers.values():
                    if racer.finished is None:
                        racer.dnf = True
                self.finish_room(room)
        except asyncio.CancelledError:
            pass

    def finish_room(self, room):
        if room.phase == 'finished':
            return
        room.phase = 'finished'
        self.broadcast(room)
        if room.end_task and room.end_task is not asyncio.current_task():
            room.end_task.cancel()

    def leave(self, client):
        if not client.room:
            return
        room = self.rooms.get(client.room)
        client.room = None
        if not room:
            return
        room.racers.pop(client.id, None)
        if not room.racers:
            self.rooms.pop(room.code, None)
            if room.end_task:
                room.end_task.cancel()
            return
        if room.host == client.id:
            room.host = next(iter(room.racers))
        if room.phase in ('countdown', 'racing') and len(room.racers) == 1:
            self.finish_room(room)
        else:
            self.broadcast(room)

    async def write_loop(self, client):
        try:
            while True:
                data = await client.outbound.get()
                client.writer.write(data)
                await asyncio.wait_for(client.writer.drain(), timeout=5)
        except (asyncio.CancelledError, ConnectionError, OSError, asyncio.TimeoutError):
            client.closing = True
            client.writer.close()

    async def connection(self, reader, writer):
        if len(self.clients) >= MAX_CLIENTS:
            writer.write(frame({'type': 'ERROR', 'code': 503, 'message': 'Server full'}))
            await writer.drain()
            writer.close()
            return
        client = Client(writer)
        self.clients.add(client)
        client.sender = asyncio.create_task(self.write_loop(client))
        LOG.info('connect id=%s peers=%d', client.id, len(self.clients))
        try:
            while not client.closing:
                head = await asyncio.wait_for(reader.readexactly(4), READ_TIMEOUT)
                length = struct.unpack('!I', head)[0]
                if length == 0 or length > MAX_FRAME:
                    self.event(client, 'ERROR', {'code': 413, 'message': 'Invalid frame length'})
                    await asyncio.sleep(0.05)
                    break
                body = await asyncio.wait_for(reader.readexactly(length), READ_TIMEOUT)
                try:
                    message = json.loads(body.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.event(client, 'ERROR', {'code': 400, 'message': 'Malformed JSON/UTF-8'})
                    continue
                command = message.get('type', 'INVALID') if isinstance(message, dict) else 'INVALID'
                request_id = message.get('requestId', '') if isinstance(message, dict) else ''
                try:
                    data = await self.dispatch(client, message)
                    self.reply(client, command, request_id, data=data)
                except ProtocolError as exc:
                    self.reply(client, command, request_id, error=exc)
                if command == 'QUIT':
                    await asyncio.sleep(0.05)
                    break
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except asyncio.TimeoutError:
            self.event(client, 'ERROR', {'code': 408, 'message': 'Idle connection timeout'})
        finally:
            client.closing = True
            self.leave(client)
            self.clients.discard(client)
            if client.sender:
                client.sender.cancel()
                await asyncio.gather(client.sender, return_exceptions=True)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            LOG.info('disconnect id=%s peers=%d', client.id, len(self.clients))


async def main():
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
    host = os.getenv('SERVER_HOST', '0.0.0.0')
    port = int(os.getenv('SERVER_PORT', '5000'))
    app = GameServer()
    server = await asyncio.start_server(app.connection, host, port)
    LOG.info('PTR/1.0 listening on %s:%d', host, port)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
