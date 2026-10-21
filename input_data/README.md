# Input data ownership

Static inputs are grouped by the pipeline that first loads them:

- `config/`: simulation configuration, user workbook, municipality and tariff
  lookups.
- `load/`: emulator, ARERA, DSM, and external load-profile inputs.
- `energy/`: building and heat-pump properties, weather sources, and external
  energy profiles.
- `finance/`: market, RID, PUN/PZO, fee, ownership, and financial-model inputs.
- `grid/`: network definitions.

The requested target tree has no `input_data/reporting` domain. Reporting
templates, chart layout, Sankey configuration, and grid-report presentation
files therefore live in `config/reporting/` as cross-cutting presentation
configuration.

Generated calendars, registries, profiles, simulation results, financial
results, grid results, and reports are not inputs. They belong under the
corresponding `output_data/RunN/` domain directory.

The weather CSV files are local inputs and remain ignored because the complete
future-weather source exceeds normal Git hosting limits. Place them under
`energy/weather/` using the filenames referenced by `config/config.yml`.

`energy/pv/milan_pvgis_tmy.csv` is the frozen PVGIS typical meteorological year
that reproduced the accepted simulated-PV baseline exactly. Native PV runs may
receive it through `PVSimulationOptions.weather`; this keeps parity tests
deterministic while leaving live PVGIS retrieval available as an explicit
weather-provider choice.
