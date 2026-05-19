# Assets Folder

The `assets/` folder contains visual outputs, chart exports, report templates, and static resources used by notebooks, reports, README files, and documentation pages.

## Root-Level Files

- `layout_charts.yml`: chart layout configuration.
- `sankey_inputs.xlsx`: input workbook for Sankey diagram generation.

## Subfolders

- `all_results/`: placeholder or archive area for aggregated result assets.
- `bills/`: exported bill visualizations, typically in `.png` and `.html` formats.
- `energy/`: generated energy plots and interactive chart exports.
- `finance/`: generated financial plots and interactive chart exports.
- `general/`: general-purpose figures, tables, and chart exports used in reports or analysis notebooks.
- `gen_pv/`: photovoltaic generation chart assets.
- `grid/`: reserved location for grid-related chart assets.
- `load_profile_emulator/`: interactive HTML visualizations for appliance and load profile emulation.
- `readme_images/`: static images used in the main repository README and project documentation.
- `report/`: report templates, including Word document templates.
- `results/`: placeholder or archive area for generated result assets.

## File Types

This folder mainly contains `.png`, `.html`, `.docx`, `.xlsx`, `.yml`, and `.gitkeep` files. The `.html` files are usually interactive chart exports, while `.png` files are static images suitable for reports and documentation.

## Usage Notes

Use `assets/` for presentation material and visual outputs. Keep raw simulation inputs and tabular working data in `files/`; keep Python implementation code in `src/`.
