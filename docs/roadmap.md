# KeySprint Development Roadmap — Grading First

This document recommends order, not fixed submission dates; the instructor announces M1/M2/M3 timing separately. Base requirements: `INSTRUCTION.md` and the official per-class announcements.

## Priority 0 — Mandatory network core (A2/A3/B1)

**Already implemented as a draft:** own TCP protocol, byte framing, independent clients, concurrency, robust command handling, server-side room state, safe disconnect cleanup, a terminal client, WebSocket gateway and actual network integration tests.

**Team review before milestone:** verify exact messages vs `docs/protocol-design.md`; conduct TCP framing demonstration with split frames; explain how await-free state transitions protect shared rooms; practice making a small protocol change and updating the codec/docs/tests.

## Priority 1 — Race and evidence (B1/B2/C)

**Implemented as a draft:** lobby, invite code/link, 8-player limit, readiness, host permission, shared server countdown, prefix-based progress and finish ranking, several original passages, connection/disconnect scenarios.

**Next deliverables:** full two-browser manual demo; screenshot/log evidence from a clean Docker start; tests for many rooms and idle-client timeout; repeat under jitter/packet loss; inspect false progress denial, fairness caveats; document and fix actual bugs discovered. Consider explicitly tracking disconnected racers as DNF in results rather than removing them from the scoreboard (a current product limitation).

## Priority 2 — Solo experience / UX (B2)

**Implemented:** original dark responsive UI, page/time practice, visual cursor and mistake indication, synthesized key audio, keyboard hint, WPM and accuracy.

**Next:** test Vietnamese/IME input if required (current passages ASCII English and browser key-by-key handling), mobile keyboard behavior, accurate time/page definitions, more original passages, practice history, usability review with actual students. **Do not copy Typing.com's protected assets or source code.**

## Priority 3 — Reliability/polish before M3 (B1/B3/C)

Recommended work: TLS/WSS for public hosting, reconnection state with a grace period and resume token, replay protection and rate limits, authoritative cursor/update protocol instead of resending the complete prefix, baseline benchmark 10/40/100/200 clients, dockerized clean-room smoke test, clear log/event IDs and proper shutdown test. **Do not claim commercial anti-cheat security** without stronger protection.

## Priority 4 — Optional extensions only after network assessment is safe

1. Persistence (SQLite/PostgreSQL) for previous races and user profiles.
2. Tournament / lobby list / spectators / seasonal ranking.
3. New self-contained typing mini-games on **the same PTR/1.0** protocol infrastructure, not separate unrelated games.

The rubric grants more points for documented protocol, correct concurrency, robustness and oral defense than for sheer number of screens or game modes. Defer game catalog until the mandatory demonstrations are dependable.

## Suggested 3-person vertical split (confirm with team; not a contribution claim)

- Member A: protocol & framing / client codec / parser error test.
- Member B: race state, concurrency, host/disconnect behavior / race tests.
- Member C: web gateway, browser UI, Docker deployment / WebSocket integration tests.

Each member should create their own feature branch and PR and defend the code they actually reviewed or changed. AI-generated initial code itself does not establish an individual contribution. Do not modify `INSTRUCTION.md`; finish `README.md` membership and honest contribution/AI disclosure records before submission.
