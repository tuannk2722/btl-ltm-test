# Testing Guide & Evidence — KeySprint

> Never claim unexecuted tests passed. The automated results recorded here were run directly against live local TCP/WebSocket listeners; Docker and GUI manual tests must be verified by the group.

## 1. Reproduce the Automated Tests

From repository root on a machine with Python >=3.12 and `aiohttp` installed:

```bash
python -m pip install -r client/requirements.txt
python -m unittest discover -s tests -v
```

Tests spin up ephemeral **real TCP listening ports** (`127.0.0.1:0`) for each test, send actual framed bytes and tear down sockets. Browser gateway test runs an actual local HTTP server/WebSocket and forwards into an actual TCP game server.

| Test | File | Coverage |
|---|---|---|
| Framing | `test_protocol.py` | fragmented 4-byte header/payload, two messages coalesced into one TCP write |
| Concurrent users | `test_protocol.py` | 40 simultaneous HELLO + PING TCP connections |
| Robust input | `test_protocol.py` | malformed JSON then valid PING; oversized frame then healthy peer still works |
| Session cleanup | `test_protocol.py` | host closes abruptly without QUIT, host migrates and empty room is deleted |
| Race authority | `test_protocol.py` | non-host cannot start; all ready required; early and invalid prefix denied, rollback denied |
| Finish and ranking | `test_protocol.py` | two racers finish a short shared passage; server records correct relative order and marks room finished |
| Web gateway | `test_gateway.py` | GET `/` renders UI; two independent WebSocket clients HELLO/create/join via live TCP game server |

### Recorded automated test execution (2026-10-20)

Command: `python -m unittest discover -s tests -v`

```text
test_static_home_and_two_browser_clients (test_gateway.GatewayTests.test_static_home_and_two_browser_clients) ... ok
test_concurrent_clients (test_protocol.ProtocolTests.test_concurrent_clients) ... ok
test_fragmented_frame_and_multiple_clients (test_protocol.ProtocolTests.test_fragmented_frame_and_multiple_clients) ... ok
test_invalid_json_and_oversized_frame_do_not_kill_server (test_protocol.ProtocolTests.test_invalid_json_and_oversized_frame_do_not_kill_server) ... ok
test_race_authority_and_progress_validation (test_protocol.ProtocolTests.test_race_authority_and_progress_validation) ... ok
test_race_full_finish_and_results (test_protocol.ProtocolTests.test_race_full_finish_and_results) ... ok
test_rooms_host_transfer_and_disconnect (test_protocol.ProtocolTests.test_rooms_host_transfer_and_disconnect) ... ok
----------------------------------------------------------------------
Ran 7 tests in 6.702s
OK
```

**Important:** This confirms the covered Python network integration behavior at that point in development. It is **not** evidence of a clean Docker Compose deployment, browser UI usability, or a 1,000-user scalability benchmark.

## 2. Manual Demo / Pending Evidence (team must perform)

1. `docker compose down -v && docker compose up --build` on a clean machine. Confirm both `server` and `web` start. Open http://localhost:8080 in two different browser windows.
2. In browser A choose **Race**, set name, create room, copy link. In browser B set a **different name** and join the code.
3. Verify join, readiness, host-only start, 3-second countdown, text shared, progress bars, finish ranking.
4. With browser B racing, close/kill its process. Verify A remains responsive and receives an updated room snapshot.
5. In terminal run `docker compose run --rm client`, execute `create`, `ready`, `state`, and `quit`.
6. Return to Practice; try time 1/3/5 minutes and page 1/2/3, incorrect characters, backspace, Restart and sound toggle.
7. Capture **genuine screenshots** of active multiplayer and terminal logs in `docs/asset/` after actually running the checks.

| # | Manual evidence | Status | Evidence (fill after running) |
|:-:|---|---|---|
| 1 | Clean Docker Compose deployment | **Pending** | |
| 2 | Two-browser race and ranking | **Pending** | |
| 3 | Abnormal disconnect in GUI | **Pending** | |
| 4 | Page/time practice from browser | **Pending** | |
| 5 | Docker terminal client commands | **Pending** | |

## 3. Stress/Edge Test Plan

- Compare completed operations and per-client latency with `N=10,40,100,200` connections; avoid claiming support beyond observed results.
- Check long-lived idle clients, false progress, alternate incorrect prefixes, frame length zero, malformed UTF-8, and rapid connect/disconnect.
- Observe CPU/memory under concurrent room broadcasts. Note 200 is **configured maximum**, not a benchmark-proven capacity.
- Perform NAT/latency tests under real `tc netem` on supported Linux, if desired; network-delay fairness has no formal guarantee.
- Keep screenshots and logs from the exact tested commit for B1/B2 evidence and oral defense.

### Visual preview (not a browser-to-server networking test)

`docs/asset/typing-ui-preview.png` is an actual screenshot captured by headless Chromium rendering the original static HTML/CSS/JS with an inline local document, not an invented mockup. Because HTTP navigation in that headless environment was blocked by the runtime administrator, the screenshot **does not establish HTTP/WebSocket UI connectivity**. The latter has separate `test_gateway.py` network coverage; a full interactive GUI check is still pending.
