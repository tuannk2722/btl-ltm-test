# Project Proposal — M1: KeySprint

> **Status:** AI-assisted draft for team review. The team must confirm its decisions and enter its own identity, ownership and instructor feedback. `INSTRUCTION.md` remains authoritative.

## 1. Team & Topic

- **Team:** *(fill with team name and members; max 3)*.
- **Topic:** KeySprint — real-time multiplayer typing practice and race over a custom TCP application protocol.
- **Course:** INT1433 — Network Programming, PTIT.

## 2. Problem

Typing platforms are useful for solo speed/accuracy practice, but a group of learners also benefits from a lightweight private room where everyone races **on the same text, at the same time**. The interesting problem is not rendering characters: it is maintaining a consistent result when clients have varying latency, disconnect, or transmit bad or manipulated progress.

## 3. Idea

KeySprint provides local 1/3/5-minute and 1/2/3-page typing practice, plus invite-code races for 2–8 users. The host creates a room and shares a link; entrants ready up; the authoritative TCP server starts a shared countdown and tracks validated correct prefixes. A responsive browser UI handles visual feedback and synthesized key sounds; a separate terminal client demonstrates raw protocol interaction.

We study Typing.com's public **test categories and WPM/accuracy conventions** as a functional reference but create **our own code, visual design, passages, and synthesized sounds** rather than copying protected assets. Public reference: https://www.typing.com/student/tests ; https://support.typing.com/en/articles/9048321

## 4. Scope

| Must have (M3 target) | Nice to have | Intentionally out of scope for this implementation |
|---|---|---|
| TCP framing and protocol; Docker server + terminal client; independent browser gateway; rooms/invitations; ready/start/countdown; validated progress; finish ranking; host reassignment; disconnect/malformed-frame handling; practice by page/time; reproducible integration tests | Account system, persist results, reconnect grace period, more practice languages, race spectators, multiple original mini-games, deployment TLS | Exact Typing.com UI/assets/audio, scraping or bundling proprietary content, account-based anti-cheat, large-scale distributed cluster |

## 5. Key Networking Challenge

- **Message framing:** TCP is a byte stream; a 4-byte unsigned big-endian length precedes UTF-8 JSON. Server validates the length before allocation.
- **Consistency:** only the server owns room state, shared text, phase, authoritative progress and finish timestamps. Client cannot supply finish time or place.
- **Concurrency:** Python `asyncio` event loop multiplexes many sockets; no state mutation yields to other coroutines. Separate bounded outbound queues isolate slow readers.
- **Fairness limitations:** validate immutable shared text/prefix and conservative velocity bounds, but pure remote typing cannot fully prove a human actually typed the characters. This is acknowledged, not presented as cheat-proof.

## 6. Initial Design Sketch

- **Transport:** raw TCP between independently deployable gateway/terminal client and game server; browser uses WebSocket to the gateway because browsers lack raw TCP APIs.
- **Protocol:** `PTR/1.0`, JSON, big-endian 4-byte length, 16 KiB max frame, stateful per-TCP session.
- **Core commands:** `HELLO`, `CREATE_ROOM`, `JOIN_ROOM`, `SET_READY`, `START_RACE`, `RACE_PROGRESS`, `LEAVE_ROOM`, `GET_STATE`, `PING`, `QUIT`.
- **Push events:** `ROOM_STATE`, `ERROR`.
- **Language:** Python 3.12, standard-library `asyncio` game server, `aiohttp` WebSocket gateway, plain JavaScript/CSS browser UI.

## 7. Alternatives Considered

| Alternative | Selected | Reason |
|---|:---:|---|
| Browser connects to a WebSocket-only game server | No | Simpler but makes the required custom raw TCP framing demonstration less direct. |
| Raw TCP game server + independent WebSocket gateway | **Yes** | Preserves socket/framing assessment while enabling multiplayer browser UI; gateway is additional complexity. |
| Thread per connection | No | Easier blocking code, but additional OS threads and locking. |
| `asyncio` state owner/event loop | **Yes** | Concurrent sockets; no `await` while mutating game state; bounded per-peer output. |
| UDP for keystroke synchronization | No | Out-of-order/loss requires additional retry and consistency work; TCP is sufficient for a small room. |
| Server trusts reported WPM/finish time | No | Easily falsified. Server computes progress and elapsed time independently. |

## 8. Ownership Plan

| Member | Proposed vertical slice (team must confirm) |
|---|---|
| *(Member 1)* | TCP protocol, parser, error handling and parser tests |
| *(Member 2)* | Room/game server, state machine, race tests and network robustness |
| *(Member 3)* | Independent client/gateway, practice/race browser UI, end-to-end tests |

Each member should contribute verified code/design and a separate PR. Do not treat this proposed allocation as proof of ownership.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Slow/failed client | Bounded queue, write timeout, idle disconnect, automatic cleanup |
| Race starts for different users at different apparent times | Single server start time broadcast to everyone; client only displays local countdown |
| User sends fake progress | Validate prefix, monotonic length, throughput bound; document limitations |
| Game blocked by unstable network | State machine rejects out-of-phase commands; disconnect releases room membership |
| Hard to demo on lab PC | Python 3.12 local startup, Docker Compose for clean-run verification, terminal client available |
| AI code cannot be defended | Review line by line, draw sequences and run oral-defense change exercises |

## 10. Instructor Feedback

*(To be filled by the team after M1 feedback.)*
