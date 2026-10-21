# Contributor guidelines

## Environment

Use CPython 3.14.7 and create the project environment from the repository
root:

```powershell
py -3.14 setup_venv.py
```

Before submitting a change, validate the existing environment with:

```powershell
py -3.14 setup_venv.py --validate-only
```

Do not add notebook-kernel setup or user-level package installation. Add a
dependency only when production or test code requires it, pin its exact version
in `requirements.txt`, and rerun environment validation.

## Architecture

`source/pipeline/CACER_simulator.py` is the only full-simulation entry point.
The execution order is configuration, load, energy, grid, finance, and
reporting.

- Pipelines load domain inputs, call domain functions, persist run-local
  outputs, and return typed results.
- Domain calculations should accept explicit values and should not read
  configuration or intermediate files implicitly.
- Pass results between domains through the contracts in
  `source/data_structures/Results.py`.
- Put static inputs under the domain that first loads them in `input_data/`.
- Put generated artifacts only under `output_data/RunN/<domain>/`.
- Preserve formulas, units, column names, indices, defaults, ordering, and
  rounding during structural migration.
- Do not silently fall back to legacy files when an input or bypass result is
  missing.
- Keep energy calculation modules free of persistence. Route PV, HVAC, battery,
  user-flow, aggregate, shared-energy, incentive, and valorizzazione outputs
  through `source/energy/energy_pipeline.py`.

Reporting templates and presentation configuration live under
`input_data/config/reporting/` because the requested target architecture has no
separate reporting input domain.

## Validation

Run the smallest relevant tests while developing, then the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q source tests tools setup_venv.py
git diff --check
```

Preserve the accepted frozen fixtures under
`legacy_baseline/fixtures/run_2026-10-06/`. Do not rerun randomized legacy
stages to redefine expected values.
