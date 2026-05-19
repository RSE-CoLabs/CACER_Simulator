# Data and Simulation Files Folder

The `files/` folder contains input data, intermediate data, configuration files, and simulation outputs used by the CACER Simulator. It is the main working data area for energy, finance, grid, HVAC, photovoltaic, incentive, RID, and PZO workflows.

## Root-Level Files

- `registry_users.yml` / `registry_users.csv`: user registry definitions.
- `registry_user_types.yml`: user type definitions and parameters.
- `registry_plants.yml` / `registry_plants.csv`: plant registry definitions.
- `membership_matrix.csv`: user-to-configuration membership matrix.
- `plant_operation_matrix.xlsx`: plant operation matrix.
- `inputs_FM.xlsx`: financial model input workbook.
- `mercato.yml`: market-related configuration.
- `recap.yml`: recap file generated or used by simulation workflows.
- `report.yml`: report configuration.

## Subfolders

- `energy/`: energy model input/output files, load profiles, shared energy results, user profiles, and load emulator input data.
- `finance/`: financial model input matrices, user and plant workbooks, configuration workbooks, bills, and finance templates.
- `general/`: shared calendar and reference datasets, such as yearly/monthly calendars, tariff bands, and municipality data.
- `gen_pv/`: photovoltaic generation outputs.
- `grid/`: grid simulator inputs, network files, result files, and report templates.
- `HVAC/`: HVAC weather datasets and HVAC simulation results.
- `incentives/`: incentive tables and CACER fee datasets.
- `PZO/`: PZO/PUN input and output price datasets.
- `RID/`: RID input configuration and generated RID output tables.
- `results_finance/`: financial simulation results, reports, generated workbooks, and archived scenario outputs.

## File Types

This folder mainly contains `.csv`, `.xlsx`, `.yml`, `.docx`, `.pkl`, and `.p` files. Some subfolders contain large datasets or generated outputs; review the `.gitignore` rules before committing new results.

## Usage Notes

Use this folder for data that is consumed by simulator runs or produced as part of reproducible workflows. Avoid placing documentation images or chart exports here; those belong in `assets/`.
