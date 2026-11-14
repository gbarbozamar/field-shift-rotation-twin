# Attributions

Add a row **when the item is first used**, not at the end.

## Data

| Name and version | Provider | URL | Licence or terms | Used for | Added on |
|---|---|---|---|---|---|
| NASA POWER daily point data (POWER Daily API v2.10.3, as the response header reports it; parameters `IMERG_PRECTOT`, `PRECTOTCORR`, `T2M_MAX`, `T2M_MIN`, `T2MDEW`, `WS2M`, `ALLSKY_SFC_SW_DWN`, community `ag`, 2024-01-01 to 2024-01-10), accessed 2026-11-14 | NASA Langley Research Center, Prediction Of Worldwide Energy Resources (POWER) project | https://power.larc.nasa.gov/api/temporal/daily/point | OPEN: the POWER site states no licence (#15, section 8); the Registry of Open Data on AWS entry for NASA POWER states "There are no restrictions on the use, access, and/or download of data from the NASA POWER Project" and "Creative Commons BY 4.0", and does not say whether that covers data obtained through the API (#15, section 8). Which statement to record is for a person (#15, decision 9) | Evidence of the documented request of D32 of issue #77, committed under D17: `docs/evidence/nasa-power-2026-11-14/`. A made-up point in the ocean, not a producer's field | 2026-11-14 |
| Global Rainfall Erosivity database (GloREDa), version 1.2: the twelve monthly rasters `Rfactor_<Month>.tif` of `GloREDa.zip` (2,224,877,134 bytes, md5 82e545774cc96781f4623e3b98a60be4), accessed 2026-11-14 | Panagos, P., et al. (2023), Zenodo record 8036998; data paper Panagos et al. (2023), Data in Brief 50:109482, https://doi.org/10.1016/j.dib.2023.109482 | https://doi.org/10.5281/zenodo.8036998 | Creative Commons Attribution 4.0 International, of the Zenodo record, with attribution (decision D101 of issue #77; the contrary conditions of the ESDAC copy are not applied to the Zenodo copy) | The twelve cell values at the demonstration point La Estanzuela (D69, D84), in `params/records/rusle_r_monthly_erosivity_*.json`. Not NASA data | 2026-11-14 |

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
| Node.js container image `node:22-slim` (local development of the frontend, `compose.yaml`) | 22 | https://hub.docker.com/_/node | MIT (Node.js and the image scripts); Debian packages under their own licences | L2a | 2026-11-14 |
| uv (container image `ghcr.io/astral-sh/uv`) | 0.12.2 | https://github.com/astral-sh/uv | MIT OR Apache-2.0 | L2a | 2026-11-14 |
| pip-licenses (development: licence check) | 5.5.5 | https://pypi.org/project/pip-licenses/ | MIT | L2a | 2026-11-14 |
| gitleaks (CI: secret scan, container image `ghcr.io/gitleaks/gitleaks`) | 8.21.2 | https://github.com/gitleaks/gitleaks | MIT | L2a | 2026-11-14 |
| GitHub Actions `actions/checkout`, `actions/setup-python`, `actions/setup-node` (CI) | v5, v6, v4 | https://github.com/actions | MIT | L2a | 2026-11-14 |
| GitHub Action `astral-sh/setup-uv` (CI) | v6 | https://github.com/astral-sh/setup-uv | MIT | L2a | 2026-11-14 |
| GitHub Actions `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages` (deploy of the frontend to GitHub Pages) | v6, v5, v5 | https://github.com/actions | MIT | L2a | 2026-11-14 |
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
| Vitest | 5.1.0 | https://vitest.dev | MIT | l3 | 2026-11-14 |
| OpenStreetMap standard tiles | (no version) | https://www.openstreetmap.org/copyright | ODbL (attribution required; OSMF tile usage policy) | l3 | 2026-11-14 |
| leaflet | 1.9.4 | https://leafletjs.com | BSD-2-Clause | l3 | 2026-11-14 |
| @types/leaflet | 1.9.22 | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | l3 | 2026-11-14 |
## Tables and publications

| Citation | URL or DOI | What is taken from it | Checked by a second person |
|---|---|---|---|
| Renard, K.G., Foster, G.R., Weesies, G.A., McCool, D.K., Yoder, D.C. (coord.) (1997). Predicting Soil Erosion by Water: A Guide to Conservation Planning With the Revised Universal Soil Loss Equation (RUSLE). USDA Agriculture Handbook No. 703 | https://www.ars.usda.gov/ARSUserFiles/60600505/RUSLE/AH_703%20-%20Predicting%20Soil%20Erosion%20by%20Water%20-%20A%20Guide%20to%20Conservation%20Planning%20With%20the%20RUSLE%20(RUSLE).pdf | The ten LS coefficients (Eq. [4-3] to [4-5], pp. 105 and 107), the unit length 22.1 m (Appendix A, p. 325) and the definition of P (Eq. [1-2], p. 15), in `params/records/` | Yes: gbarbozamar, 2026-11-14 |
| Pérez Bidegain, M., Piaggio, J.M., Baethgen, W., García Préchac, F. (2017). Actualización del factor erosividad de la lluvia en Uruguay. Agrociencia Uruguay 21(2):91-99 (CC BY 4.0) | https://doi.org/10.31285/agro.21.2.11 | R of the locality Colonia, Cuadro 2, 1980-2009, p. 94 (D83), in `params/records/rusle_r_factor.colonia.json` | Yes: gbarbozamar, 2026-11-14 |
| Beretta-Blanco, A., Carrasco-Letelier, L. (2017). USLE/RUSLE K-factors allocated through a linear mixed model for Uruguayan soils. Ciencia e Investigación Agraria 44(1):100-112 (CC BY 4.0) | https://doi.org/10.7764/rcia.v44i1.1622 | K of the class T Brunosol, Table 1, p. 104 (D70, D100), in `params/records/rusle_k_factor.t_brunosol.json` and `data/demo/la_estanzuela_soil_slope.json` | Yes: gbarbozamar, 2026-11-14 |
| Grahmann, K., Rubio, V., Perez-Bidegain, M., Quincke, J.A. (2022). Soil Use Legacy as Driving Factor for Soil Erosion under Conservation Agriculture. Frontiers in Environmental Science 10:822967 (CC BY) | https://doi.org/10.3389/fenvs.2022.822967 | Plot length 22.1 m, slope 4.3 to 4.7 % and the coordinates of the demonstration site, p. 3 (D100), in `data/demo/la_estanzuela_soil_slope.json` | Yes: gbarbozamar, 2026-11-14 |
| García Préchac, F., Durán, A. (1998). Propuesta de estimación del impacto de la erosión sobre la productividad del suelo en Uruguay. Agrociencia (Uruguay) II(1):26-36 | https://beta.acuedi.org/book/4731/pdf (third-party copy; no official open copy found) | The single declared C, 0.036, "Sistema 3.7", p. 29, in `params/records/rusle_c_factor.json` (declared by the lead developer) | Yes: gbarbozamar, 2026-11-14 |
| Clérici, C., García Préchac, F. (2001). Aplicaciones del modelo USLE/RUSLE para estimar pérdidas de suelo por erosión en Uruguay y la región sur de la cuenca del Río de la Plata. Agrociencia (Uruguay) V(1):92-103 | https://beta.acuedi.org/book/5162/pdf (third-party copy; no official open copy found) | The same C, 0.036, Cuadro 6, row 6, p. 99, cited in `params/records/rusle_c_factor.json` | Yes: gbarbozamar, 2026-11-14 |

Rules:

- Each NASA product is identified by name, version and URL.
- Data from partner agencies is listed separately from NASA data.
- Non-NASA data: only freely and publicly accessible, with its licence written down.
- Synthetic data is labelled as synthetic here and in the interface.
