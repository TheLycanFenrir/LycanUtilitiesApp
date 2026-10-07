"""UI Tester utility runtime.

No-op sandbox: echoes every submitted field value back to the console so the
interop bridge, form hydrating and value-passing can be inspected end to end.
"""

from __future__ import annotations


def run(ctx) -> dict:
    data = ctx.get_all_form_data() or {}
    ctx.log(f"UI Tester received {len(data)} field(s):")
    for key in sorted(data):
        ctx.log(f"  {key} = {data[key]!r}")
    ctx.status("UI Tester ran successfully!", "green")
    return {"ok": True, "message": f"UI Tester complete. {len(data)} field(s) echoed to the console."}