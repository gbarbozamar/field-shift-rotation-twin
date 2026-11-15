# Parameter records

One JSON file per parameter record. The format is described in [../README.md](../README.md).

Values, ranges and citations follow decision D34 of issue #77: an AI session may transcribe them from a published source with the full reference, the locator, the verbatim text and the date read, and one person checks every number against the source and signs `checked_by`. A value that no source prints (a declared value, such as the single C or P = 1) is declared by the lead developer, and its record says so in `note`.

Today the folder holds the 26 records of the soil-loss value at the demonstration point La Estanzuela (unit l0/first-number): the ten LS coefficients, R of Colonia (D83), K of the class T Brunosol (D100), the declared C and P, and the twelve monthly erosivity values of GloREDa at the point (D84, D101). R, K, C and P carry the scope `{}` because EP1 looks them up with the empty scope; reading a site scope is a later unit (PROPOSED). The values for one site in the empty scope are a known limit: a second site needs a scope key that EP1 reads. K is also in `data/demo/la_estanzuela_soil_slope.json`, which EP1 does not read today: a known redundancy.
