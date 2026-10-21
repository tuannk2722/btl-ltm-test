"""Terminal TCP client for the instructor's `docker compose run --rm client` requirement.

Commands: create, join CODE, leave, ready, unready, start, state, progress TEXT, ping, quit.
The browser UI is preferable for the typing game itself.
"""
import asyncio
import os
import secrets
import shlex

from wire import pack, receive


async def main():
    host = os.getenv('CLIENT_TARGET_HOST', 'server')
    port = int(os.getenv('CLIENT_TARGET_PORT', '5000'))
    reader, writer = await asyncio.open_connection(host, port)
    name = os.getenv('PLAYER_NAME', 'Terminal-' + secrets.token_hex(2))

    async def listen():
        try:
            while True:
                msg = await receive(reader)
                kind = msg.get('type')
                if kind == 'ROOM_STATE':
                    state = msg['data']
                    print(f"\nROOM {state['code']} [{state['phase']}] players: " + ', '.join(
                        f"{p['name']} ({p['correct']} chars)" for p in state['players']), flush=True)
                    if state['phase'] == 'racing':
                        print('RACE TEXT:', state['text'], flush=True)
                elif msg.get('requestId') != 'heartbeat':
                    print('\nRECV:', msg, flush=True)
        except (asyncio.IncompleteReadError, OSError):
            print('\nServer disconnected', flush=True)

    task = asyncio.create_task(listen())
    serial = 0

    async def request(kind, payload=None):
        nonlocal serial
        serial += 1
        writer.write(pack({'type': kind, 'requestId': str(serial), 'payload': payload or {}}))
        await writer.drain()

    await request('HELLO', {'name': name})
    print(f'Connected as {name}. Commands: create, join CODE, leave, ready, unready, start, state, progress TEXT, ping, quit')
    try:
        while not task.done():
            try:
                line = (await asyncio.to_thread(input, '> ')).strip()
            except EOFError:
                break
            if not line:
                continue
            op, _, arg = line.partition(' ')
            command = {
                'create': 'CREATE_ROOM', 'join': 'JOIN_ROOM', 'leave': 'LEAVE_ROOM',
                'ready': 'SET_READY', 'unready': 'SET_READY', 'start': 'START_RACE',
                'state': 'GET_STATE', 'progress': 'RACE_PROGRESS', 'ping': 'PING', 'quit': 'QUIT',
            }.get(op.lower())
            if not command:
                print('Unknown command')
                continue
            payload = ({'code': arg} if command == 'JOIN_ROOM' else
                       {'ready': op == 'ready'} if command == 'SET_READY' else
                       {'typed': arg} if command == 'RACE_PROGRESS' else {})
            await request(command, payload)
            if command == 'QUIT':
                await asyncio.sleep(.1)
                break
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        writer.close()
        await writer.wait_closed()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
