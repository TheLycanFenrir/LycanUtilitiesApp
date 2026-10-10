"""OS-level screen color picker.

Lets the user click anywhere on the desktop (even outside the app window) and
returns the exact pixel color under the cursor.  Windows-only: relies on a
low-level ``WH_MOUSE_LL`` hook plus a ``GetPixel`` read from the screen DC.

The bridge method ``api.screen_pick(timeout)`` keeps the app visible for the
duration of the pick so the user can click freely on any monitor.

While the pick is active:

* The system cursor is swapped to a **crosshair for the whole desktop**, and
  restored the moment the pick ends.
* A **pixel-zoom balloon** (a topmost popup) follows the cursor and shows a
  10x magnified view of the pixels under it plus the live ``#rrggbb`` color,
  updated on every mouse move.
* Every mouse button and wheel message anywhere is *consumed* by the hook
  (returns 1), client and non-client alike: nothing can be clicked, dragged
  or scrolled on screen — no accidental app launch, no window action, no
  context menu.  Mouse *movement* passes through so the cursor can aim.

A left click finishes the pick and samples that pixel, right click or ``Esc``
cancels.  A short grace period keeps the hook armed after the resolving click
so the trailing mouse-up is swallowed too and cannot trigger anything.
"""

from .picker import wait_for_screen_pick

__all__ = ["wait_for_screen_pick"]
