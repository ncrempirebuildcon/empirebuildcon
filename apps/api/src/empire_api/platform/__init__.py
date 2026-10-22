"""Shared platform pieces every module uses: audit log, outbox, rate limits, crypto helpers.

WHY these tables live here and not in users/ or integrations/ (ARCHITECTURE §4 lists AuditLog
under users and OutboxEvent under integrations): every module writes audit rows and events in
its own transaction, so the writers and their tables sit in one dependency-free module that
nothing else imports back.
"""
