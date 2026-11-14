# Evidence: one documented request to NASA POWER, 14 November 2026

## What it is

One request to the public daily point endpoint of the NASA POWER service, and its raw response, kept as evidence for decision D32 of issue #77 ("Check the documentation against the service before the settings are written").

| File | What it holds |
|---|---|
| `request.txt` | The exact URL of the request and the UTC time recorded when it was made |
| `response.json` | The raw response, byte for byte as it was received |

SHA-256 of `response.json`:

```
7344bb9610131b7565e975b0c7c47481dec359a536b588c1941e3443ff2815c8
```

The file was copied unchanged from the folder where the request was recorded, and the checksum of the copy equals the checksum of the original.

## Who made it, and on whose instruction

The orchestrating AI session made the request on the instruction of the lead developer, on 14 November 2026 (D32 of issue #77). D32 gives the time as "about 18:10 UTC"; the time recorded with the request is in `request.txt`. A builder session committed the two files; it called no service.

## The point

Longitude `-50`, latitude `-35`: "a made-up point in the ocean that is no producer's field" (D32).

## Which decision allows committing it

- D17 of issue #77: "**Yes, one,** for a point that is not a real producer's field, recorded after a person makes the first documented request, with its row in `ATTRIBUTIONS.md`."
- D32 of issue #77: "**Done**, see below. The recorded response may be committed under D17"; "below" is the section of the same comment that this README copies.

Its row is in the "Data" section of `ATTRIBUTIONS.md`.

## What it settles, as D32 writes it

Answer `200`. What it settles of the questions #15 left open:

| Point | What the response shows |
|---|---|
| Does `ag` accept `IMERG_PRECTOT` at daily level? | Yes: ten daily values returned |
| Unit of each parameter, as the response labels it | `IMERG_PRECTOT` and `PRECTOTCORR`: `mm/day`; `T2M_MAX`, `T2M_MIN`, `T2MDEW`: `C`; `WS2M`: `m/s`; `ALLSKY_SFC_SW_DWN`: `MJ/m^2/day` (the "per Hour" wording of the dictionary does not appear in the response) |
| Fill value | `"fill_value": -999.0` in the header; none of the seventy values was the fill value |
| Time standard | `"time_standard": "UTC"` in the header |
| Sources | header `sources`: `MERRA2`, `SYN1DEG`, `IMERG`, `POWER`; there is no source per value |
| Point of the series | `geometry.coordinates` `[-50.0, -35.0, 0.0]`: the elevation reported for an ocean cell is `0.0` |

## What it does not settle, as D32 writes it

Still not settled by one request: which IMERG run (Late or Final) a given day comes from; whether the daily IMERG value is a depth summed over the UTC day (the unit `mm/day` is consistent with it); which underlying product supplies a given day of `PRECTOTCORR`.

These questions stay `OPEN` in `contracts/CLIMATE_QUANTITIES.md` (O4 and O5).
