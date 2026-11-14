# Field Shift Rotation Twin — web interface

Skeleton shell for the web interface: React + Vite + TypeScript with Tailwind
CSS, TanStack Query and hash-based client-side routing.

## Commands

- `npm ci` — install dependencies from the lockfile.
- `npm run dev` — dev server at `http://localhost:5173`.
- `npm run build` — type-check and build into `dist/`.
- `npm run preview` — preview the production build.

## Configuration

- Vite `base` is `/field-shift-rotation-twin/`, matching the GitHub Pages URL
  https://gbarbozamar.github.io/field-shift-rotation-twin/.
- Routing is hash-based (`/#/...`) because GitHub Pages has no index.html
  fallback for client-side paths.
- The backend URL is read at build time from `VITE_API_URL` and defaults to
  `http://localhost:8000` (see `src/lib/api.ts`). To point elsewhere, create a
  local `.env` file (gitignored) with `VITE_API_URL=<url>`; never commit it.
