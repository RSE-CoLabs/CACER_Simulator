<img title="logo_RSE" src="assets\readme_images\logo_RSE.PNG" alt="logo_RSE" data-align="center" width="300">

---

# CACER Simulator

This repository contains a simulation tool for assessing the **economic**, **financial**, and **energy** performance of renewable energy sharing configurations such as CACER (Configurations for Renewable Energy Sharing in Collective Self-Consumption).

## Description

The simulator supports the evaluation of different collective self-consumption scenarios, including Renewable Energy Communities (RECs) and Groups of Remote Self-Consumers. It provides detailed metrics such as:

- **Economic benefits**: savings and revenues from self-consumed and exported energy.
- **Financial indicators**: Payback Period, Net Present Value (NPV), and Internal Rate of Return (IRR).
- **Energy performance**: self-consumption levels, self-sufficiency, and CO₂ emissions reduction.

## Flow chart CACER simulator

<div style="text-align: center;">
  <img src="assets/readme_images/Flow_chart_simulator.png" alt="Flow_chart" width="1000">
</div>

## Repository Structure

- `assets/`: contains visual outputs or auxiliary resources.
- `files/`: input/output files and configuration data for simulations.
- `Functions_Load_Emulator_and_DSM.py`: functions for emulating the residential load profile and for simulating demand-side flexibility and management.
- `Functions_Energy_Model.py`: core energy modeling functions for CACER simulations (photovoltaic productivity simulation, load profile extraction, etc.).
- `Functions_Financial_Model.py`: functions for financial analysis and investment evaluation (Discounted Cash Flow analysis).
- `Functions_General.py`: general-purpose utility functions used throughout the project.
- `config.yml`: configuration file with key parameters for the simulations and path of file and forlders.
- `main - CACER tutorial.ipynb`: interactive Jupyter Notebook with step-by-step instructions for using the CACER simulator.
- `main - CACER.ipynb`: interactive Jupyter Notebook for using the CACER simulator (cleaned version, without tutorial).
- `main - load_profile_emulator.ipynb`: interactive Jupyter Notebook with step-by-step instructions for emulating domestic load profile.
- `main - photovoltaic_productivity_simulator.ipynb`: interactive Jupyter Notebook with step-by-step instructions for simulate photovoltaic productivity.
- `Reporting.ipynb`: notebook to generate performance reports.
- `users CACER.xlsx`: example Excel file with user data.

## Prerequisites

You’ll need:

- Python 3.x
- Required libraries listed in `requirements.txt`

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/ToniRollo/CACER-simulator.git](https://github.com/RSE-EUT/CACER-simulator.git

---

# 🔥 **New drop incoming!!**

# Main Functionalities

🚨 PAY ATTENTION: ALL THE FOLLOWING FUNCTIONALITIES ARE ALREADY DEVELOPED IN THIS REPOSITORY AND HOW IT WORKS WILL BE EXPLAINED IN DETAIL LATER IN THIS SECTION 

## 1. Photovoltaic Productivity Simulator

A simulator for the photovoltaic productivity has been created. The pvlib open source library is used in way to simulate the producitivity (more information about the library can be found at the following link ...). The main input of the simulators are:

- **location**;
- **capacity of the photovoltaic generator**;
- **yearly derating factor**.

A typical metheorological year (tmy) is extracted from PVGIS datasets. Actually is setted the Europe/Rome timezone as DatetimeIndex for the data. Furthermore, the following photovoltaic module and inverted are chosen to simulate the basic photovoltaic generator (1 kWp generator):

- **module**: 'Shell_Solar_SM100_24__2003__E__';
- **inverter**: 'Enphase_Energy_Inc___M175_24_208_Sxx__208V_'.

The possibility of setting different types of modules and inverters will be developed later. Actually, only fixed mount system are modeled.

The first step of the simulator creates a productiviy profile for 1 kWp generator. After, the productivity profile is scaled with the capacity of the generators and derated over the years with a typical derating factor (this parameter can be changed in the config.yml file).

The flow chart of the photovoltaic producitivity simulatore is showed in the following figure.

<div style="text-align: center;">
  <img title="Photovoltaic_profile_generator_scheme" src="assets\readme_images\Photovoltaic_profile_generator_scheme.png" alt="Photovoltaic_profile_generator_scheme" data-align="center" width="1000">
</div>

A notebook file to run separately a simulation for a photovoltaic generator was developed:

- `main - photovoltaic_productivity_simulator.ipynb`.

In this notebook we need to specify:

- **location**;
- **number of years of the simulation**;
- **capacity**;
- **tilt angle**;
- **azimuth angle**;
- **derating factor**;
- **directory to save the csv file with results**.

🚨 **PAY ATTENTION**: In the CACER simulation (using the `main - CACER.ipynb` file) the inputs for the simulation of the productivity are setted in a different way (using `user CACER.xlsx` file).

## 2. BESS Simulator

The simulator has the possibility to include a Battery Energy Storage System for prosumers. The module performs a time-dependant calculation of the energy flows taking as input the production and consumption profiles, and updating the the battery State of Charge for each time step and calculating the convertion losses, which are assessed by using the round-trip efficiciency but without including temperature and current limitations. 
The energy hierarchy used considers that the electricity production supplies directly the load first; if the production exceeds the load, thus the exceess flows into the battery and, once this is fully charged, the remaining production excess is injected into the grid. When production is zero or below the load, the battery gets discharged to supply the demand untill it is needed or it gets fully discharged, but without injections into the grid. 
With the current setup, the BESS is charged only from the prosumer generation (not the grid) and its energy supplies only the prosumer load, without injections into the grid.  

As shown in the figure below, the module takes, for the given timestep "t", the production excess OR the energy demand at the battery terminals, updates the battery SOC based on the previous timestep "t-1", and calculates the charging/discharging energy flows to/from the battery, net of the energy loss due to the half-cycle efficiency. 

<div align="center">
  <img title="BESS_profile_generator_scheme" src="assets\readme_images\BESS_profile_generator_scheme.png" alt="BESS_profile_generator_scheme" data-align="center" width="600">
</div>

The module keeps track of the number of cycles updating its State of Health, applying a constant derating factor to its rated capacity, which gets influent over the years. 

The inputs for the BESS are: 
- Dept Of Discharge, DoD (from "config.yml", same for all users)
- rated capacity (specific for each user, from "users CACER.xlsx")
- derating factor (from "config.yml", same for all users)

## 3. Load Profile Domestic Users Emulator

A domestic load profile emulator has been created that uses the load profiles of individual household appliances and their quarterly usage probabilities. The household appliances considered are:
- fridge;
- washing-machine;
- dish-washer;
- oven;
- microwaves;
- tv.

Additionally, a base load has been added in order to have a realistic aggregate load profile. Based on the probability of switching on of individual appliances, an activation instant is extracted at a probabilistic level. The appliance consumption profile is then scheduled and added to the aggregate daily profile. The same procedure is used for each individual appliance, for each day and for each emulated user. An explanatory flow chart is reported below.

<div style="text-align: center;">
  <img title="Flow_chart_load_emulator" src="assets\readme_images\Flow_chart_load_emulator.png" alt="Flow_chart_load_emulator" data-align="center" width="1000">
</div>

With this methodology, aggregate load profiles for domestic users are obtained similar to those shown in the following explanatory figure.

<p align="center">
  <img title="Load_emulator_result_example" src="assets\readme_images\Load_emulator_result_example.png" alt="Load_emulator_result_example" data-align="center" width="600">
</p>

In order to add greater randomness to the generation of load profiles, the following functions have been introduced that can be activated through appropriate flags:
- **Multiple daily activation of the appliance**, it is expected that the appliance can be activated up to a maximum of three times per day. The number of activations is determined at a probabilistic level.
- **Probability of activation of the appliance on the day in question**, in this case not all appliances are activated daily. The activation is determined at a probabilistic level.

More features will be implemented soon. For example:
- A large dataset with the load profile of the appliance to consider different technology levels.
- The profiles of the appliances will be selected based on the socio-territorial context in which the domestic users are being emulated.
- etc.

More information about using the emulator can be found in the file:

- `main - load_profile_emulator.ipynb`.

### 3.1. Demand Side Engagement Simulator

`⏳ work in progress...`

### 3.2. Optimal Demand Side Management Simulator

`⏳ work in progress...`

## 4. Bills Simulator

The model creates the electricity bills for a given user types, based on the energy withdrawal coming out of the energy model. If the user type is a consumer, it computes the business-as-usual electricity bill, while if he/she is a prosumer, it also includes a scenario with self-generation (thus with reduced electricity withdrawal from the grid).
The model takes the inputs from the "mercato.yml", where the user can manipulate the market parameters and prices, defining new tariffs depending on type of users, and adjustment parameters for time-dependant electricy price. 

For each user type, the model takes the following inputs from the "user CACER.xlsx":
- tariff scheme: electricity time slots (F1, F1+F2, F1+F2+F3)
- supplier: indicating the tariff adopted, as defined by the user in "mercato.yml"
- category (domestic/non domestic)
- range of contractual power
- voltage level: BT (Low Voltage) or MT (Medium Voltage)

The model can simulate a fixed or variable (PUN + SPREAD) tariffs, by manipulating the "supplier" field for each user. For the PUN data, they can be manipulated/updated manually in the "files\\PZO\\PUN_input_data.csv" file.

The bill is computed separately for each component (energy, power, fixed), duties and VAT; the output includes the file for single timestep (for in dept result exploration and validation) and monthly aggregation (needed for the financial mudules).

<div style="text-align: center;">
  <img title="Bills_generator_scheme" src="assets\readme_images\Bills_generator_scheme.png" alt="Bills_generator_scheme" data-align="center" width="1000">
</div>

## 5. Finacial Model and Discounted Cash Flow analysis

<div style="text-align: center;">
  <img title="DCF_scheme" src="assets\readme_images\DCF_scheme.png" alt="DCF_scheme" data-align="center" width="1000">
</div>

The module collects the financial inputs from the FM_inputs.xlsx file, and creates a monthly break down of all the inflated cash flows. The analysis includes the allocation of:
- Capex, grants, debt and amortization
- Opex (from plants and CACER)
- Revenues (from electricity bills savings, incentives, RID and Arera Valorization)
- Taxes
- Insurance
- EBITDA, EBIT, Profit Before Earnings

A discounted cash flow analysis is then performed to calculate economic KPIs such as IRR, return on the investment and NPV.

When assessing the economic sustainability of a CACER project, it is important to evaluate KPIs for all the stakeholders that are present. It is common, in fact, that the project itself looks somehow sustainabile, but if some users are not returning on their own investments, this could be jeopardizing the entire operation. 
Thus, to assess the overall situation, the cash flow analysis is performed on 6 separate levels: 
- **plant level**: including only the cashflows related to the installation, opex and revenues related to the specific plant and investment.
- **user level**: being consumer, prosumer or producer, related to a single POD.
- **configuration level**: for a multi-configuration CER, it is important to evaluate the cash flows related to the single configuration, to measure the state of health of each one and overall contribution. Cashflows can be significantly different based on number of users, installed capacity and access to PNRR funds which decreases the incentives over time.
- **stakeholders level**: in some configurations there might be users with multiple PODs, which can thus evaluate the overall benefits coming from each POD. Examples of multi-pod stakeholder could be Public Administrations (that has the school as prosumer and some municipality offices as consumers), or a industry, or any private entity.
- **CACER level**: keeping track of the cash flows on the bank account of the CACER entity, with incoming cash flows (such as incentives from GSE, subscription fees, etc.) and outgoing (incentives repartition, administration costs, legal entity establishment and kickoff costs, common services, communication, etc.). If the CACER is the owner of some assets or plants, the related cash flows are included. Generally, the CACER's annual economic balance breaks even, as the CACER is a non profit entity managing the cash flows and keeping no (or little, for contingency) margin for itself, distributing the earnings as per repartition scheme. It is used to allocate cash in and cash out during the project lifetime, to assess whether and when the CACER has liquidity or not on its bank account.  
- **project level**: this aggregates all the cashflows of the users, plans, configurations, etc, counting each cashflow once. It is needed to assess the overall sustainability, and measure the economic impacts generated by the project. Alone is not enough to establish whether the CACER is healty or not.

The output of each financial analysis consists in an excel file with details on monthly and yearly cash flows, easy to manipulate to get insights.

### 5.1. Funding Scheme 

`⏳ work in progress...`

### 5.2. Incentives Repartition Methodology

`⏳ work in progress...`

## 6. Grid Impact Simulator

`⏳ work in progress...`

`🚀 A tutorial main will be released later for this module!`

---

# Citations

## Pvlib citation

This project makes use of the [pvlib](https://github.com/pvlib/pvlib-python) library, which is licensed under the BSD 3-Clause License.

Copyright © 2013-2024, pvlib developers.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the pvlib organization nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

## Numpy Financial citation

This project uses [NumPy Financial](https://github.com/numpy/numpy-financial), which is licensed under the BSD 3-Clause License.

Copyright © NumPy Developers.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the NumPy organization nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

## Icons Attribution

Some icons used in this project are designed by Flaticon and are licensed under the Flaticon Basic License.
