# Development

[← Back to README](README.md)

## Day-to-day

- `npm run build` inside `frontend/` produces the production bundle. `npm run dev` starts the Vite dev server for frontend iteration, but note that a plain browser has no `window.pywebview` bridge — use `build_react_n_run.py` (default HMR mode) to exercise backend calls.
- The bridge surface (every method the frontend can call) is split into per-section mixins under `app/bridges/` and composed in `app/bridge.py`.
- Adding or editing a utility under `utilities/` is picked up automatically: the scanner re-hashes the folder on startup and recompiles `utilities_cache.json` when something changed.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the project layout and the request/job pipeline.

## Debug logging

`core/debug_log.py` provides tiered `debug_info` logging. Verbosity is a level 0–4 (0 off, 1 important, 2 public method traces, 3 internal/hot paths, 4 everything):

```bash
python main.py --debug-level=3
# or, for the launcher:
python build_react_n_run.py --debug-level=3
```

It can also be set via the `LYCANTOOLS_DEBUG_LEVEL` environment variable (read at startup). `debug_info` inspects the call stack and automatically prefixes each message with the calling `Class.method`, so call sites pass only the bare message.

Separately, `--debug` (or `LYCANTOOLS_DEBUG=1`) enables the WebView2 developer tools.

## Authoring utilities

See [WRITING_A_UTILITY.md](WRITING_A_UTILITY.md).
