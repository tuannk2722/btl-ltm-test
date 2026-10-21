# KeySprint — Oral Defense Practice (C1/C2/C3)

The instructor assesses each student **individually** for code ownership, reasoning and a live change. Do not memorize these answers without opening the code and demonstrating them.

1. **Why custom TCP instead of direct WebSocket?** `server/src/server.py` is a real TCP service with an independent wire protocol. A browser cannot open raw TCP, so `client/src/web_gateway.py` translates WebSocket JSON to raw TCP length-prefix frames. Alternative WebSocket-only reduces components but obscures low-level framing exercise.
2. **What if the 4-byte length is split into two TCP packets?** `StreamReader.readexactly(4)` buffers until all four bytes are available, then reads exactly the announced body length. `tests/test_protocol.py::test_fragmented_frame_and_multiple_clients` transmits header and body in multiple writes.
3. **What if two requests arrive in one `recv`?** The reader loops, decoding each frame in sequence; test coalesces two `PING`s into one write.
4. **Why validate length before body?** To reject a bogus size without allocating an arbitrary amount of memory; `MAX_FRAME=16384`, code 413 and close.
5. **What do `requestId` and `*_RESULT` do?** Correlate responses to requests when unsolicited `ROOM_STATE` events are interleaved; inspect `reply()` and `event()`.
6. **What shared state can race?** `GameServer.rooms`, `Room.racers`, connection set and room phase. They belong to one asyncio event loop; `dispatch()` has no awaited I/O during room mutation. `asyncio.Queue` separates writing from mutation.
7. **Why not put `await writer.drain()` inside `broadcast()`?** A slow client could stall all room updates. We enqueue to a per-client bounded queue and let a separate writer task handle backpressure.
8. **What happens when the host disconnects with `kill -9`?** TCP eventually produces EOF/reset/idle timeout. `finally` removes the member, reassigns `hostId` to a remaining member, broadcasts and closes resources. See the socket-level disconnect test.
9. **Why can a client not send arbitrary 100% progress?** The server verifies the exact correct text prefix, non-decreasing progress, and a rough character-per-second limit; finish timestamps are taken from server monotonic time. It still cannot prove a human typed it.
10. **What happens if `RACE_PROGRESS` arrives during countdown?** Code 409, no progress mutation; server uses its own monotonic start time instead of trusting a client-supplied clock.
11. **How does a race end?** All remaining racers finish or time out (180 seconds), or only one racer remains after disconnect. Finish time ordering is server-generated.
12. **Can this handle 1,000 simultaneous clients?** Not guaranteed. Default `MAX_CLIENTS=200`, and only a 40-connection automated smoke scenario has been executed. More users require benchmarking CPU, memory, broadcast fanout, and possibly a distributed architecture.
13. **How would you add a new command live?** First add request/response definition, payload and status in `docs/protocol-design.md`. Next add a `dispatch()` branch and client command, then add a socket integration test and run the suite.
14. **How to change maximum frame length?** Update both `server/src/server.py` and `client/src/wire.py`, discuss new limits in protocol docs, add over-limit test. Avoid a silent protocol incompatibility.
15. **What can the gateway not do?** It cannot authenticate a race result or decide who won. It only translates framing and forwards JSON. Keep room authority on server.

## Live-change rehearsal

Practice one **small actual modification** per member, e.g. add a `GET_SERVER_INFO` command, cap a room to 6 racers, change countdown from 3s to 5s, or add a new error-code test. Explain how that change affects protocol documents, client behavior and tests. Run the modified tests rather than claiming success from unexecuted code.
