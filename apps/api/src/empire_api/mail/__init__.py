"""Email the system sends: security notices, password links and lead alerts (Phase 4 part 5).

`transport.py` is the one interface with two transports (Resend, and a dev mailbox that never
sends), `templates.py` the messages, `handlers.py` the outbox handlers that send them,
`delivery.py` sends one message once, `routes_dev.py` the dev-only mailbox route.
Implements: D-007 (Resend Free), ARCHITECTURE §8 (lead alerts), §9 (events and consumers).
"""
