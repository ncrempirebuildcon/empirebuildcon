"""Server-side conversions: a new enquiry reported to the ad platforms (task 6.2, D-057).

Off until configured. A platform is used only when its settings are complete (config.py,
"Server-side conversions") AND `CONVERSIONS_CONSENT_MIN_VERSION` is set: the version of the
optional marketing consent text whose wording the legal reviewer approved for sharing with ad
platforms. A lead is reported only when its marketing consent was given on that version or a
later one.

Flow (handlers.py):
  1. `lead.created` → `queue_conversions`: decides whether the lead may be reported, then emits
     one `conversion.send` event per configured platform. It never calls a platform and never
     fails, so the lead's other handlers (the sales email) aren't retried because of an ad API.
  2. `conversion.send` → `send_conversion`: reads the lead again (it may have been erased or
     marked spam since), builds the platform's request and sends it, with the outbox's retries.

COMPLIANCE:
  - Only hashed (SHA-256) phone and email leave the system (hashing.py), with the ad click IDs.
    Never the name, the message or anything else.
  - The `conversion.send` event carries ids only; the personal data is read at send time.
  - Duplicates, manual leads and samples (`alert` false) are never reported.
"""
