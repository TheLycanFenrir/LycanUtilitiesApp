let handler = null;

export function setToastHandler(fn) {
  handler = fn;
}

export function showToast(message, type = "good", ms = 4600, action = null) {
  if (handler) handler({ message, type, ms, action });
}