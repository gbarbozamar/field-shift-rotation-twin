# Attributions

Add a row **when the item is first used**, not at the end.

## Data

| Name and version | Provider | URL | Licence or terms | Used for | Added on |
|---|---|---|---|---|---|
| NASA POWER daily point data (POWER Daily API v2.10.3, as the response header reports it; parameters `IMERG_PRECTOT`, `PRECTOTCORR`, `T2M_MAX`, `T2M_MIN`, `T2MDEW`, `WS2M`, `ALLSKY_SFC_SW_DWN`, community `ag`, 2024-01-01 to 2024-01-10), accessed 2026-11-14 | NASA Langley Research Center, Prediction Of Worldwide Energy Resources (POWER) project | https://power.larc.nasa.gov/api/temporal/daily/point | OPEN: the POWER site states no licence (#15, section 8); the Registry of Open Data on AWS entry for NASA POWER states "There are no restrictions on the use, access, and/or download of data from the NASA POWER Project" and "Creative Commons BY 4.0", and does not say whether that covers data obtained through the API (#15, section 8). Which statement to record is for a person (#15, decision 9) | Evidence of the documented request of D32 of issue #77, committed under D17: `docs/evidence/nasa-power-2026-11-14/`. A made-up point in the ocean, not a producer's field | 2026-11-14 |

## Libraries

| Name | Version | URL | Licence | Added by lane | Added on |
|---|---|---|---|---|---|
| FastAPI | 0.162.7 | https://pypi.org/project/fastapi/ | MIT | L2a | 2026-11-14 |
| Pydantic | 2.14.3 | https://pypi.org/project/pydantic/ | MIT | L2a | 2026-11-14 |
| Uvicorn | 0.54.0 | https://pypi.org/project/uvicorn/ | BSD-3-Clause | L2a | 2026-11-14 |
| HTTPX (runtime: HTTP client of the data adapters in `adapters/`; development: test client) | 0.28.1 | https://pypi.org/project/httpx/ | BSD-3-Clause | L2a | 2026-11-14 |
| pytest (development) | 9.2.0 | https://pypi.org/project/pytest/ | MIT | L2a | 2026-11-14 |
| Ruff (development) | 0.17.5 | https://pypi.org/project/ruff/ | MIT | L2a | 2026-11-14 |
| Python container image `python:3.12-slim` | 3.12 | https://hub.docker.com/_/python | PSF-2.0 (Python); Debian packages under their own licences | L2a | 2026-11-14 |
| uv (container image `ghcr.io/astral-sh/uv`) | 0.12.2 | https://github.com/astral-sh/uv | MIT OR Apache-2.0 | L2a | 2026-11-14 |
| pip-licenses (development: licence check) | 5.5.5 | https://pypi.org/project/pip-licenses/ | MIT | L2a | 2026-11-14 |
| gitleaks (CI: secret scan, container image `ghcr.io/gitleaks/gitleaks`) | 8.21.2 | https://github.com/gitleaks/gitleaks | MIT | L2a | 2026-11-14 |
| GitHub Actions `actions/checkout`, `actions/setup-python`, `actions/setup-node` (CI) | v5, v6, v4 | https://github.com/actions | MIT | L2a | 2026-11-14 |
| GitHub Action `astral-sh/setup-uv` (CI) | v6 | https://github.com/astral-sh/setup-uv | MIT | L2a | 2026-11-14 |
| React | 19.3.1 | https://react.dev | MIT | l3 | 2026-11-14 |
| React DOM | 19.3.1 | https://react.dev | MIT | l3 | 2026-11-14 |
| Vite | 8.3.8 | https://vite.dev | MIT | l3 | 2026-11-14 |
| TypeScript | 7.0.2 | https://www.typescriptlang.org | Apache-2.0 | l3 | 2026-11-14 |
| Tailwind CSS | 4.3.5 | https://tailwindcss.com | MIT | l3 | 2026-11-14 |
| @tailwindcss/vite | 4.3.5 | https://tailwindcss.com | MIT | l3 | 2026-11-14 |
| TanStack Query | 5.107.1 | https://tanstack.com/query | MIT | l3 | 2026-11-14 |
| @vitejs/plugin-react | 6.3.0 | https://github.com/vitejs/vite-plugin-react | MIT | l3 | 2026-11-14 |
| @types/react | 19.3.0 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | l3 | 2026-11-14 |
| @types/react-dom | 19.3.0 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | l3 | 2026-11-14 |
| @types/node | 24.19.2 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | l3 | 2026-11-14 |

## Tables and publications

| Citation | URL or DOI | What is taken from it | Checked by a second person |
|---|---|---|---|

Rules:

- Each NASA product is identified by name, version and URL.
- Data from partner agencies is listed separately from NASA data.
- Non-NASA data: only freely and publicly accessible, with its licence written down.
- Synthetic data is labelled as synthetic here and in the interface.
