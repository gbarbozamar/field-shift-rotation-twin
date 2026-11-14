# Frontend shell

React, Vite, TypeScript, Tailwind CSS and TanStack Query, from the stack approved in issue #36. This is the shell only: no map, analysis, data requests or example results.

## Acceptance

Node 22.12 or later:

```sh
npm ci
npm run build
npm run check:deployment
```

The build writes `dist/`. The deployment check verifies the compiled JavaScript and CSS exist under the GitHub Pages base `/field-shift-rotation-twin/`.

`npm run dev` serves the shell at `http://localhost:5173`. Navigation uses `#/` and `#/status`, so refreshing a route does not require a server fallback.

Public address: https://gbarbozamar.github.io/field-shift-rotation-twin/ . Publishing is owned by the separate Pages workflow. Rotation calculations are explicitly unavailable; this shell does not establish CP1 or validate any model.
