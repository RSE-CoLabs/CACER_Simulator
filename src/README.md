# Source Code Folder

The `src/` folder contains the Python implementation of the CACER Simulator modules. It is the main location for reusable code used by the notebooks, simulations, documentation API pages, and helper scripts.

## Main Files

- `Functions_Energy_Model.py`: energy community simulation logic, energy balance calculations, shared energy indicators, and related utilities.
- `Functions_Financial_Model.py`: financial model routines, user and plant economic calculations, reporting helpers, and financial output generation.
- `Functions_General.py`: shared utilities used across the simulator, including configuration handling and common data-processing functions.
- `Functions_Grid_Simulator_1.py`: grid simulation routines for preparing and running power-flow analyses.
- `Functions_Grid_Simulator_2.py`: additional grid simulation utilities and post-processing routines.
- `Functions_Load_Emulator_and_DSM.py`: load profile emulation and demand-side management workflows.
- `Functions_Load_Emulator_v2.py`: updated load emulator implementation with additional appliance/profile handling.
- `setup_venv.py`: helper script for setting up the project virtual environment.
- `__init__.py`: package initializer for importing modules from `src`.

## Subfolders

- `hvac_functions/`: HVAC simulation package with building models, heat pump models, weather handling, thermal load calculations, and optimization routines.
  - `classes/`: Python classes for buildings, heat pumps, CER objects, and related model structures.
  - `functions/`: calculation and optimization functions for HVAC simulations, including thermal loads, solar irradiance, weather processing, and MILP helpers.
  - `config/`: YAML configuration files and reference material for building archetypes and heat pump configurations.

## Generated Files

Python cache folders such as `__pycache__/` are generated automatically by Python and should not be edited manually or committed unless explicitly required.

## Usage Notes

Most notebooks import functions directly from these modules. When adding new code, prefer keeping reusable logic in `src/` and using notebooks only as execution examples or tutorials.
