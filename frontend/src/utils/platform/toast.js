let handler = null;

export function setToastHandler(fn) {
  handler = fn;
}

// A `sticky` toast is undismissable: it has no auto-dismiss timer and its
// action (if any) does not remove it. It persists until a reload/restart.
export function showToast(message, type = "good", ms = 4600, action = null, sticky = false) {
  if (handler) handler({ message, type, ms, action, sticky });
}