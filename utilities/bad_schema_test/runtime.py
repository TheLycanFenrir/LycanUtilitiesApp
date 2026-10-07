"""Broken schema (test) — this file is never reached because the form schema
fails validation; it exists only so the folder looks like a real utility."""


def run(ctx) -> dict:
    return {"ok": True, "message": "Should not be reachable."}