"""UI Demo utility runtime.

No-op sandbox: echoes every submitted field value back to the console so the
UI-driven form, embedded fields and value-passing can be inspected end to end.
"""

from __future__ import annotations


def run(ctx) -> dict:
    data = ctx.get_all_form_data() or {}
    ctx.log(f"UI Demo received {len(data)} field(s):")
    for key in sorted(data):
        ctx.log(f"  {key} = {data[key]!r}")
    ctx.status("UI Demo ran successfully!", "green")
    return {"ok": True, "message": f"UI Demo complete. {len(data)} field(s) echoed to the console."}


def on_ui_action(ctx, action_id, params):
    """UI action hook: receives declarative node actions dispatched from React.

    Buttons in the demo schema carry actionId / actionParams; the frontend
    routes them here via Api.ui_action when no local handler owns the id.
    """
    ctx.log(f"UI action '{action_id}' params={params!r}")
    return {"ok": True, "action": action_id, "params": params, "via": "python"}