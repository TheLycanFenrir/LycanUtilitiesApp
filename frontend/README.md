# Lycan Utilities — Frontend

The React SPA for **Lycan Utilities**. It renders the dashboard, the dynamically
generated utility forms and the job console, and talks to the Python backend
through PyWebView's JS bridge. Built with **Vite**, **React 19** and **SCSS**.

> For the full application (backend + window), see the [root README](../README.md).
> A plain browser has no `window.pywebview` bridge, so run tools through the root
> launcher (`python build_react_n_run.py`) rather than `npm run dev` alone.

## Prerequisites

- **Node.js 20.19+** (or 22.12+) with **npm**

## Commands

```bash
npm install      # install dependencies
npm run dev      # Vite dev server with HMR (frontend only — no backend bridge)
npm run build    # production bundle into dist/
npm run preview  # preview the production build
npm run lint     # ESLint (eslint.config.js)
```

Use `python build_react_n_run.py` from the repo root for the full experience: by
default it starts the Vite dev server and launches the PyWebView window against
it (instant HMR for `.jsx` / `.js` / `.scss` / `.css`, app restart on `.py`
changes). Use `--no-hmr` for a `dist/` build with a restart watcher.

## How it talks to the backend

Every public backend method is exposed as `window.pywebview.api.<method>(...)`
and returns a promise resolving to a standard envelope:

```js
{ ok: true, reason: "SUCCESS", detail: null, /* ...payload */ }
```

`reason` is a status token (`SUCCESS` / `WARNING` / `FAILED` / `INFO`) and any
machine-readable sub-code travels in the optional `code` field.

Wrap calls with the `usePyWebView` hook, which sanitizes path-like arguments and
no-ops safely until the bridge is ready:

```jsx
import { usePyWebView } from "../hooks/usePyWebView";

const { call, isAvailable } = usePyWebView();
const res = await call("start_job", { utility: "frames_to_video", params });
```

Long-running jobs are polled rather than pushed: `start_job` returns a job id and
the `useJobConsole` hook advances a per-consumer cursor over `poll(job_id, cursor)`
to stream `log` / `status` / `progress` / `confirm` / `done` events.

## Source layout

```
src/
├── main.jsx            # React bootstrap
├── App.jsx             # Shell wiring & routing
├── tabs/               # HomeDashboard, FormTool, UtilityErrorTab
├── components/         # ConsolePanel, FormGenerator, PresetBar, UtilityCardList, ...
├── contexts/           # FormState, Modal, Theme, Toast, Zoom
├── hooks/              # usePyWebView, useJobConsole, usePersistentForm, useCyanPulse
├── styles/             # SCSS: abstracts, base, components, layout, pages, themes
├── utils/              # color, emoji, form, icons, paths, platform, validate
└── assets/             # heroicons + app icons
```

- **Dynamic forms** — `components/FormGenerator/` renders a utility's JSON form
  schema; form state lives in `contexts/FormStateContext` and is persisted per
  tool by `hooks/usePersistentForm`.
- **Theming** — dark/light is driven by `contexts/ThemeContext` over the SCSS
  design tokens in `styles/themes/`.

## ESLint

Linting is configured in `eslint.config.js` using the flat config format with
`eslint-plugin-react-hooks` and `eslint-plugin-react-refresh`. Run it with
`npm run lint`.
