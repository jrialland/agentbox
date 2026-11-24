"""Repository helpers for persisting model-layer records.

Repositories accept a session factory and open short-lived sessions for their
own reads and writes. Module-level helpers that take a ``session`` argument run
on a caller-owned session and leave the transaction boundary to the caller.
"""
