from Functions_General import (check_file_status, clear_folder_content, add_to_recap_yml, check_folder_exists, get_calendar, location_italian_to_english)
import pandas as pd
import numpy as np
import calendar
from random import random, choice
import datetime as dt
import yaml
import xlwings as xw
import contextlib
import io
from simple_colors import *
from tqdm import tqdm
import csv
import glob
from concurrent.futures import ThreadPoolExecutor
import pvlib
from pvlib import pvsystem
from pvlib import location
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS as PARAMS
from pvlib.pvsystem import PVSystem, Array, FixedMount
from pvlib.location import Location
from pvlib.modelchain import ModelChain
import plotly.graph_objs as go
from geopy.geocoders import Nominatim
import warnings
warnings.filterwarnings("ignore")
from simple_colors import *

###################################################################################################################

def BESS(E_terminal_theor, SOCkwh_tm1, ε_roundtrip_halfcycle, battery_min_kwh, battery_max_kwh, flag_battery_to_grid=0, battery_to_grid_capacity=0):
    """
    The function makes a simplified model of a Battery Energy Storage System, as it does not take into account of any voltage, temperature, C-rate and other battery parameters.
    Terminology:
        gross                       before applying the half cycle roundtrip efficiency losses
        net                         after applying the half cycle roundtrip efficiency losses
        theroetical                 before checking applying the DoD lower limit, assuming infinite battery capacity
        real                        after checking the battery upper (100% SOC) and lower limits (DoD)

    Inputs:
        E_terminal_theor            energy flux theoretically available at the battery terminals, given by the PV production at that timestep. Sign convention: charging (+) and discharging (-)
        SOCkwh_tm1                  battery State Of Charge at the t-1 timestep, expressed in kWh
        ε_roundtrip_halfcycle       roundtrip efficiency of a half cycle (assuming same losses for charge and discharge)
        battery_min_kwh             minimum acceptable value of kWh in the battery, above which the battery goes in protection and stops the discharge. It's related to the Dept of Discharge lower limit 
                                    (f.i. in this case DoD = 80%, means 20% is the lower boundary), set by the installer/manufacturer in the BMS. Expressed in kWh
        battery_max_kwh             max value of kWh in the battery, here assumed equal to the rated capacity (100% SOC)
        flag_battery_to_grid        flag. If 1, battery injects power into the grid to share with other REC users. If 0, only self-consumption. Default is 0, no battery-to-grid injection
        battery_to_grid_capacity    max kWh limit that the battery can inject into the grid in the delta t interval. It'r related to the discharge C-rate. It's the limit set by the inverter to the grid, configured by the user. Default is 0
    Outputs:
        E_terminal_real             real energy flow at the battery, as a result of losses . <0 se scarica cedendo energia al sistema, >0 se carica assorbendo dal sistema
        E_losses                    transformation losses at the battery terminals for receiving or injecting that energy
        SOC_kWh                     updated State Of Charge at timestep t, in kWh
        SOC_perc                    updated State Of Charge at timestep t, in % 
    """
    
    
    E_charge_theor_gross = max(0, E_terminal_theor) # if charging (+), if discharging is 0
    # Ecarica_teor_lor = max(0, Emors_teor) # flusso_carica_teorica_lorda_kwh
    E_discharge_theor_gross = min(0, E_terminal_theor - battery_to_grid_capacity * flag_battery_to_grid) # if discharging (-), if charging is 0
    # Escarica_teor_net = min(0, Emors_teor - battery_to_grid_capacity * flag_battery_to_grid) # flusso_scarica_teorico_netto_kwh
    E_halfcycle_theor = E_charge_theor_gross * ε_roundtrip_halfcycle + E_discharge_theor_gross / ε_roundtrip_halfcycle # Flusso mezzociclo teorico (kWh)
    # Emez_teor = Ecarica_teor_lor * ε_roundtrip_halfcycle + Escarica_teor_net / ε_roundtrip_halfcycle # Flusso mezzociclo teorico (kWh)

    # updating SOC checking the upper and lower boundaries
    if SOCkwh_tm1 + E_halfcycle_theor > battery_max_kwh: # in this case, we are charging and going beyond the upper limit, so we need to cap the new SOC to 100%
        SOCkWh = battery_max_kwh
    elif SOCkwh_tm1 + E_halfcycle_theor <= battery_min_kwh: # in this case we are discharging and going below the lower limit, so we need to cap the new SOC to 1-DoD
        SOCkWh = battery_min_kwh
    else: SOCkWh = SOCkwh_tm1 + E_halfcycle_theor # se non siamo in nessuna delle due condizioni limite, il nuovo stato di carica è semplicemente la somma del vecchio e del flusso in ingresso (+ o -)

    SOCperc = SOCkWh / battery_max_kwh

    E_halfcycle_real = SOCkWh - SOCkwh_tm1
    E_charge_real_net = max(0,E_halfcycle_real) # Flusso carica reale netto (kWh)
    E_charge_real_brut = E_charge_real_net / ε_roundtrip_halfcycle # Flusso carica reale lordo (kWh)
    E_discharge_real_brut = min(0,E_halfcycle_real) # Flusso scarica reale lordo (kWh)
    E_discharge_real_net = E_discharge_real_brut * ε_roundtrip_halfcycle # Flusso scarica reale netto (kWh)

    E_terminal_real = E_charge_real_brut + E_discharge_real_net # Flusso reale ai morsetti (kWh)
    E_loss = abs(E_charge_real_net - E_charge_real_brut) + abs(E_discharge_real_brut - E_discharge_real_net)

    return E_terminal_real, E_loss, E_discharge_real_net, SOCkWh, SOCperc

    # # updating SOC checking the upper and lower boundaries
    # if SOCkwh_tm1 + Emez_teor > battery_max_kwh: # siamo oltre il 100% di SOC, quindi cappiamo a battery_max_kwh
    #     SOCkWh = battery_max_kwh
    # elif SOCkwh_tm1 + Emez_teor <= battery_min_kwh: # siamo sotto il DoD, quindi cappiamo a battery_min_kwh
    #     SOCkWh = battery_min_kwh
    # else: SOCkWh = SOCkwh_tm1 + Emez_teor # se non siamo in nessuna delle due condizioni limite, il nuovo stato di carica è semplicemente la somma del vecchio e del flusso in ingresso (+ o -)

    # SOCperc = SOCkWh / battery_max_kwh

    # Emez_real = SOCkWh - SOCkwh_tm1
    # Ecarica_real_net = max(0,Emez_real) # Flusso carica reale netto (kWh)
    # Ecarica_real_lor = Ecarica_real_net / ε_roundtrip_halfcycle # Flusso carica reale lordo (kWh)
    # Escarica_real_lor = min(0,Emez_real) # Flusso scarica reale lordo (kWh)
    # Escarica_real_net = Escarica_real_lor * ε_roundtrip_halfcycle # Flusso scarica reale netto (kWh)

    # Emors_real = Ecarica_real_lor + Escarica_real_net # Flusso reale ai morsetti (kWh)
    # Eperdite = abs(Ecarica_real_net - Ecarica_real_lor) + abs(Escarica_real_lor - Escarica_real_net)

    # return Emors_real, Eperdite, Escarica_real_net, SOCkWh, SOCperc
###############################################################################################################################

def export_users_csv():
    """si esportano i flussi di energia per tutti i singoli utenti, in formato csv"""

    field_names = ["datetime",
                    "Eut", "Eprod", "Eaut_PV", "Eaut_batt", "Eaut", "battery_cumulative_charge", "SOCkWh", "SOCperc", "Eperdite", "Eprel", "Eimm", 
                    'LCF_aut', 'SCF_aut'
                    ]

    foldername_result_energy = config["foldername_result_energy"]
    
    for user_type in result.keys():
        subset = result[user_type]

        with open(foldername_result_energy + user_type + ".csv", "w", newline='') as f: #newline='' toglie le righe vuote
            w = csv.DictWriter(f, field_names)
            w.writeheader()
            for k, d in sorted(subset.items()):
                w.writerow(mergedict({"datetime":k}, d))

    print("Users 15min files created")

###############################################################################################################################

def mergedict(a,b):
    """Merge two dictionaries into one. 
    The values of the second dictionary will overwrite the values of the first one in case of common keys.
    """
    a.update(b)
    return a

###############################################################################################################################

def simulate_timestep_single_user():
    """ the function calculates the energy flow for a single timestep (15min or 1h) for a single consumer or prosumer. 
    If a PV system is present, its energy flow follows the following hierarchy: load -> battery -> grid.
    For the prosumers, the following variables are also calculated:
        - LCF: Load Cover Factor = Energy self-consumed / Energy consumed (tells us the % of consumed energy self-generated; higher means there is little dependency from the grid, as self-production is covering most of the demand) 
        - SCF: Supply Cover Factor = Energy self-consumed / Energy produced (tells us the % of produced energy self-consumed; higher means there is little energy available for injection into the grid and sharing with CACER) 

    Inputs:
        user (global)        ID of the user to be simulated
        t    (global)        the timestep of the simulation, defined outside this function
    Outputs: 
        result              list with all results organized in the correct format
        """
    
    load_t = load_profiles[user].loc[t] if user_type in ["consumer", "prosumer"] else 0
    generation_t = max(generation[user].loc[t], 0) if user_type in ["producer", "prosumer"] else 0

    # Initialize common values
    Eut = Eprod = 0
    flag_prosumer = False
    LCF_aut = SCF_aut = None 

    # assigning the variables based on the type of user:
    if user_type == "consumer":
        Eut = load_t

    elif user_type == "producer":
        Eprod = generation_t

    elif user_type == "prosumer":
        Eut = load_t
        Eprod = generation_t
        flag_prosumer = True 

    flag_noBattery = (pd.isna(user_types_set[user]["battery"]) or user_types_set[user]["battery"] == 0) # flag true if battery value is nan or 0

    # - WITHOUT BATTERY
    if flag_noBattery: # there is no battery, then no need to simulate the battery energy flow
        E_terminal_real = E_loss = E_discharge_real_net = SOCkWh = SOCperc = 0
        battery_cycles_number = None

    # - WITH BATTERY - battery plays a role in the timestep energy flows calculation, so we prepare the necessary variables for the battery simulation
    else: 

        battery_capacity = user_types_set[user]["battery"]

        # based on the initial nominal battery capacity at beginning of the lifetime, calculating the number of cycles based on the DoD
        battery_cycles_number = battery_cumulative_charge[user] / (battery_capacity * dod)
        
        # calculating the derating index based on the number of cycles the battery has gone through. f.i. 80% means the battery has lost 20% of its capacity
        derating_index = pow((1-battery_derating_factor), battery_cycles_number)

        # calculating the max and min capacity of the battery, after sdjustment of the newly updated derating index 
        battery_max_kwh = derating_index * battery_capacity
        battery_min_kwh = battery_max_kwh * (1 - dod)

        # brut theoretical energy flow at the battery terminals, given by the PV generation at that timestep. Can be negative, indicating a need to draw from the battery
        E_terminal_theor = Eprod - Eut 
        E_terminal_real, E_loss, E_discharge_real_net, SOCkWh, SOCperc = BESS(E_terminal_theor, 
                                                                        SOCkWh_tm1[user], 
                                                                        ε_roundtrip_halfcycle, 
                                                                        battery_min_kwh, 
                                                                        battery_max_kwh, 
                                                                        flag_battery_to_grid=0, 
                                                                        battery_to_grid_capacity=0
                                                                        )

        if E_terminal_real > 0:
            battery_cumulative_charge[user] = battery_cumulative_charge[user] + (SOCkWh - SOCkWh_tm1[user]) 

        SOCkWh_tm1[user] = SOCkWh # updating the variable

    # energy balance
    Eaut_PV = min(Eprod, Eut) # self-consumption from direct use of generation asset, without the contribution of battery
    Eaut_batt = min(-E_discharge_real_net, Eut - Eaut_PV) if not flag_noBattery else 0 # contribution of battery for self-consumption
    Eaut = Eaut_PV + Eaut_batt # total self-consumotion (generation + storage)
    interscambio_rete = Eprod - Eut - E_terminal_real # energy exchange with the grid (positive if injected, negative if taken from the grid)
    Eprel = -min(0, interscambio_rete) # Energy from the grid (positive or 0)
    Eimm = max(0, interscambio_rete) # Energy injected into the grid (positive or 0)
    
    # LCF and SFC calculation
    # note: denominators could be equal to 0, as calculation is hourly/quarterly (e.g. E_production at night) so need to avoid the "Error: division by zero" and set to 0
    # sometimes ii generates nan values slowing down the calucaltion, so we skip that by using if statements. If Eaut=0, for sure one between Eut o Eprod is 0
    if flag_prosumer and Eaut > 1e-4:  # Skip division by zero
        LCF_aut = Eaut / Eut if Eut != 0 else 0
        SCF_aut = Eaut / Eprod if Eprod != 0 else 0
    else:
        LCF_aut = SCF_aut = 0

    # limiting accuracy to 0.1 Wh to save memory
    result = {
        "Eut": "%.4f" %  Eut,
        "Eprod": "%.4f" % Eprod,
        "Eaut_PV": "%.4f" % Eaut_PV,
        "Eaut_batt": "%.4f" % Eaut_batt,
        "Eaut": "%.4f" % Eaut,
        "battery_cumulative_charge" : "%.2f" % battery_cumulative_charge[user],
        "SOCkWh": "%.3f" % SOCkWh, 
        "SOCperc": "%.4f" % SOCperc,
        "Eperdite": "%.4f" % E_loss,
        "Eprel": "%.4f" % Eprel,
        "Eimm": "%.4f" % Eimm,
        "LCF_aut": LCF_aut,
        "SCF_aut": SCF_aut,
    }

    return result

###############################################################################################################################

def CACER_energy_flows():

    """
    Simulates the energy flows for all the members of the CACER, for all the timesteps of the model.

    This function calculates the energy flows for users with and without energy storage systems. It reads configurations 
    and user data from files, checks necessary folders, and clears old results. The function then simulates the energy 
    flows for each user based on their typology (consumer, producer, prosumer) and whether they have a Battery Energy Storage 
    System (BESS). Results are exported to CSV files.

    For the users without storage, the simulation is non time dependant (meaning what happens in timestep t-1 has no influence on timestep t) 
    thus a calculation by vectors is used. When storage is present, iterative calculation (time consuming) is needed, as there is interdependence between timesteps
    (battery SOC of time t-1 plays as role in establishing where energy flows to in timestep t). 

    Global Variables:
        t (int): Current timestep of the simulation.
        user (str): Current user being simulated.
        user_type (str): Type of the current user.
        battery_cumulative_charge (dict): Cumulative charge of the battery for each user.
        SOCkWh_tm1 (dict): State of Charge (SOC) in kWh at the previous timestep for each user.
        result (dict): Dictionary to store the results of the simulation for each user.
        load_profiles (DataFrame): Load profiles for each user.
        generation (DataFrame): Generation profiles for each user.
        dod (float): Depth of discharge.
        battery_derating_factor (float): Factor for battery capacity degradation over cycles.
        ε_roundtrip_halfcycle (float): Efficiency of a half charge-discharge cycle.
        user_types_set (dict): Configuration of user types and their attributes.
        config (dict): Configuration settings loaded from a YAML file.

    Input Files:
        config.yml: Configuration file with simulation parameters.
        filename_carichi: CSV file with load profiles.
        filename_output_csv_gen_pv: CSV file with generation profiles.
        filename_registry_user_types_yml: YAML file with user types registry.
        filename_plant_operation_matrix: Excel file with plant operation data.

    Output:
        CSV files for each user with energy flow data, saved to the configured output directory.
    """

    print(blue("\nGenerate all CACER energy flows:", ['bold', 'underlined']), '\n')

    # using global variables to avoid reading the file every time
    global t, user, user_type, battery_cumulative_charge, SOCkWh_tm1, result, load_profiles, generation, dod, battery_derating_factor, ε_roundtrip_halfcycle, user_types_set, config

    config = yaml.safe_load(open("config.yml", 'r'))
    
    ε_roundtrip = config["round_trip_efficiency"] # roundtrip efficiency of a full charge-discharge cycle. Assuming constant efficiency disregarding the temperature and current
    ε_roundtrip_halfcycle = np.sqrt(ε_roundtrip) #roundtrip efficiency of a half cycle (assuming same losses for charge and discharge)
    dod = config["dod"]
    battery_derating_factor = config["battery_derating_factor"]

    load_profiles = pd.read_csv(config["filename_carichi"], index_col="datetime")
    # load_profiles = pd.read_hdf(config["filename_carichi"], index_col="datetime") # HDF seems to be a more efficient alternative. To be explored
    generation = pd.read_csv(config["filename_output_csv_gen_pv"], index_col="datetime")
    generation["month"] = generation.index.str[0:7]
    user_types_set = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    
    print(len(user_types_set), "user types found\n")

    plant_type_operational_matrix = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_type_operation_matrix", index_col=0, header=1).T # user_type as column, month "YYYY-MM" as index

    check_folder_exists(config["foldername_result_energy"]) # checking that output folder exists before running the time-consuming loops
    clear_folder_content(config["foldername_result_energy"]) # now we can delete its content

    # creating lists of users with and without storage
    user_types_with_storage = [user for user in user_types_set.keys() if user_types_set[user]["battery"] > 0]
    user_types_without_storage = [user for user in user_types_set.keys() if user not in user_types_with_storage]

    # Looping over time user typess with BESS system - TIME-DEPENDANT 
    if user_types_with_storage != []:

        # as we need to iterate over large number on timesteps, dictionaries will be used instead of dataframes to save computational time
        result = {user: {} for user in user_types_with_storage} # initialize to prevent key errors
        battery_cumulative_charge = {}
        SOCkWh_tm1 = {}

        # "static" energy balance, meaning we exclude the injection of energy from battery towards the grid. Battery user are considered to be non-cooperative, for self-consumption only
        # as the users are considered here to be non-cooperative in the energy consumption, the simulation is done per user
        for user in tqdm(user_types_with_storage, desc = " - users with storage: "): # loop over users

            user_type = user_types_set[user]["type"]
            # print("User: " + user + "; User_type: " + user_type)

            # battery initial conditions
            battery_cumulative_charge[user] = 0 # battery is brand new, 0 cycles
            SOCkWh_tm1[user] = 20 # we start with battery at 20% (simulating years of operations, this assumption has no impact on results. We just need to start somewhere
            
            for t in load_profiles.index: # loop over time
                result[user][t] = {} # initialization
                result[user][t] = simulate_timestep_single_user() # simulate timestep

        export_users_csv()

    ################### NON TIME-DEPENDANT ###################
    # with non time-dependant calculation, dataframes and vectorial operations are used

    for user in tqdm(user_types_without_storage, desc = " - users without storage: "):

        user_type = user_types_set[user]["type"]

        # CONSUMER 

        if user_types_set[user]["type"] == "consumer":
            df_user = pd.DataFrame()
            df_user["Eprel"] = load_profiles[user]
            df_user["Eut"] = df_user["Eprel"]
            df_user["Eimm"] = None
            df_user["Eprod"] = None
            df_user["Eperdite"] = None
            df_user["Eaut"] = None
            df_user["Eaut_PV"] = None
            df_user["Eaut_batt"] = None

        # PRODUCER 

        if user_type == "producer":

            operating_months = [month for month in plant_type_operational_matrix.index if plant_type_operational_matrix[user][month] == 1] # list of months in which the plant is operating

            generation["operation"] = 1

            if operating_months != []:
                # creating a column of 0s and 1s for the datapoints in which the plant is operating
                generation["operation"] = np.where(np.isin(generation["month"], operating_months), 1, 0)

            # calculation of energy flows
            df_user = pd.DataFrame()
            df_user["Eprod"] = generation[user] * generation["operation"] # removing the values for the months in which the plant is not operating
            df_user["Eimm"] = df_user["Eprod"]  # Eimm = Eprod. 
            df_user["Eprod"] = generation[user] * generation["operation"] # removing the values for the months in which the plant is not operating
            df_user["Eimm"] = df_user["Eprod"]  # Eimm = Eprod. 
            df_user["Eut"] = None
            df_user["Eperdite"] = None
            df_user["Eprel"] = None
            df_user["Eaut"] = None
            df_user["Eaut_PV"] = None
            df_user["Eaut_batt"] = None

            generation["operation"] = None # resetting the column to avoid mixing data of different user_types

        # PROSUMER

        if user_type == "prosumer": 

            operating_months = [month for month in plant_type_operational_matrix.index if plant_type_operational_matrix[user][month] == 1] # list of months in which the plant is operating
            
            generation["operation"] = 1

            if operating_months != []:
                # creating a column of 0s and 1s for the datapoints in which the plant is operating
                generation["operation"] = np.where(np.isin(generation["month"], operating_months), 1, 0) # seems to run faster than the above

            # calculation of energy flows
            df_user = pd.DataFrame()
            df_user["Eut"] = load_profiles[user]
            df_user["Eprod"] = generation[user] * generation["operation"] # removing the values for the months in which the plant is not operating
            df_user["Eaut"] = df_user[["Eut", "Eprod"]].min(axis=1)
            df_user["Eprel"] = df_user["Eut"] - df_user["Eaut"]
            df_user["Eimm"] = df_user["Eprod"] - df_user["Eaut"]
            df_user["Eperdite"] = None # we consider here only the storage roundtrip losses, no inverter nor cables
            df_user["Eaut_PV"] = df_user["Eaut"] # no battery, so all self consumption comes from PV
            df_user["Eaut_batt"] = None # no battery, so all self consumption comes from PV

            generation["operation"] = None # resetting the column to avoid mixing data of different user_types

        df_user.to_csv(config["foldername_result_energy"]+"\\"+user+".csv")

    print("\n**** All CACER energy flows created! ****")

###############################################################################################################################

def import_users_energy_flows(user_type_set):
    # creo dataframe degli users, uno per tipologia di utenza. quindi un profilo per un singolo utente di quel tipo, per ogni tipo
    """
    Function to import energy flows of all users of a given type given in input. 
    The function aggregates the load profiles of all the user types (one column per user type) and returns a single dataframe.
    Parameters
    user_type_set : list with the user types of interest
    """

    rows = 0
    df_merged = pd.DataFrame()
    config = yaml.safe_load(open("config.yml", 'r'))
    foldername_result_energy = str(config['foldername_result_energy'])
    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    
    for user_type_type in user_type_set:
        filename = foldername_result_energy + user_type_type + ".csv"
        number_of_users = registry_user_types[user_type_type]["num"] # number of users of that type

        with open(filename) as f:
            df = pd.read_csv(filename).fillna(0)
            df["user"] = user_type_type
            df["num"] = number_of_users
            rows += len(df)
        
        # check if df_merged exists already within the variables, if yes just append the dataframe
        if not 'df_merged' in locals(): 
            df_merged = df
        else: 
            df_merged = pd.concat([df_merged, df])

    df_merged.drop_duplicates(inplace=True) # removing duplicates. We should not have duplicates, thus asserting the values match before returning the dataframe
    assert (rows == len(df_merged)), "ERROR: the number of rows in the aggregated file does not match the sum of rows of single files. There might be some duplicates or missing datapoints."
    
    return df_merged

###############################################################################################################################

def import_users_energy_flow_single_column(user_type_set, energy_column):
    """ exports a dataframe with timesteps on index and user_types (given as input) on columns, 
    filled with values of the energy_column (f.i. "Eimm") given as input
    """
    df_result = pd.DataFrame()
    config = yaml.safe_load(open("config.yml", 'r'))
    foldername_result_energy = str(config['foldername_result_energy'])
    
    for user_type in user_type_set:
        filename = foldername_result_energy + user_type + ".csv"

        with open(filename) as f:
            df = pd.read_csv(filename).fillna(0).set_index("datetime")
            df_result[user_type] = df[energy_column]

    assert not df_result.isnull().values.any(), "ERROR: There are NaN values in the dataframe"
    
    return df_result

###############################################################################################################################

def simulate_location_productivity(location, tilt_angle, azimuth):
    
    """
    Simulate the productivity of a PV plant with a capacity of 1 kWp in a given location with a fixed delta_t 
    (the results are derated respect to a corrective parameter)

    Parameters
    location : str, location of the PV plant
    tilt_angle : float, tilt angle of the PV plant
    azimuth : float, azimuth of the PV plant

    """
    config = yaml.safe_load(open("config.yml", 'r')) 
    
    print(blue("- Simulation of the productivity for a pv plant with a capacity of 1 kWp:", ['bold']))

    # create a dataset with the coordinates of all the locations
    locations_input = [location]
    coordinates_dataset = suppress_printing(create_coordinates_dataset, locations_input)

    # calculate the productivity for a PV plant with a capacity of 1 kWp in the selected location with a fixed delta t (the results are derated respect the GSE/RSE annual production found in the report)
    # result_ac_energies_resampled is a dictionary where the keys are the locations in input
    result_ac_energies_resampled = suppress_printing(simulate_1_kWp_generators, coordinates_dataset, tilt_angle, azimuth)

    # derate the annual productivity with the derating factor that reduce the efficiency of the modules
    
    derating_factor = config['pv_derating_factor']  # derating factor that reduce the efficiency of the modules
    result_ac_energies_gens_derated = suppress_printing(simulate_gens_derated_productivity, derating_factor, result_ac_energies_resampled)

    # crete two unstacked dataframe (the other functions work with dictionaries)
    result_ac_energies_to_csv_df = suppress_printing(simulate_unstacked_productivity, result_ac_energies_gens_derated)

    # export results in a csv file
    path = str(config['filename_output_csv_1kWp'])
    result_ac_energies_to_csv_df.to_csv(path, encoding='utf-8')

###############################################################################################################################

def simulate_1_kWp_generators(coordinates_dataset, tilt_angle, azimuth):

    """calculating the productivity for a photovoltaic generator with an installed capacity of 1 kWp for the selected locations 
    using hourly time interval and obtaining a dictionary as output, in which the keys are the input locations.
    Inputs:
        gen_data                           dictionary with {'location' : location, 'capacity' : capacity, 'tilt_angle' : tilt_angle, 'azimuth' : azimuth}
    Outputs:
        result_ac_energies_resampled       dictionary in which we save the results for each time iteration in (kWh / delta t) [dict]       
    """

    config = yaml.safe_load(open("config.yml", 'r')) 
    check_file_status(config['filename_output_csv_gen_pv'])    
    check_calendar_status()
    
    clear_folder_content(config['foldername_graph_pv'])

    # set parameters for the photovoltaic module and the inverter
    module, inverter = set_system()

    # create a typical meteorological year for the locations in the list
    tmys = weather_data(coordinates_dataset)

    # calculate the productivity for the selected photovoltaic module and inverter
    result_ac_energies = simulate_module_productivity(coordinates_dataset, tmys, module, tilt_angle, azimuth, inverter)


    # calculate the productivity for a pv plant with a capacity of 1 kWp
    result_ac_energies_1kWp = simulate_1_kWp_productivity(module, result_ac_energies)

    # resample data with the correct datetime
    result_ac_energies_resampled = simulate_resampled_productivity(result_ac_energies_1kWp)

    return  result_ac_energies_resampled

###############################################################################################################################

def simulate_configuration_productivity():

    """we calculate the productivity for each installed photovoltaic generators of the configuration under exam 
       in different time interval (1 hour, daily, monthly)
    
    Outputs:
        output_gen_pv.csv                   .csv file
    """

    print(blue("\nGenerate production profile for user types added:", ['bold', 'underlined']))

    print("\n0. Simulation of the productivity for each generators ")
    result_ac_energies_gens = suppress_printing_no_args(simulate_gens_productivity)

    # derate the annual productivity with the derating factor that reduce the efficiency of the modules
    config = yaml.safe_load(open("config.yml", 'r')) 
    derating_factor = config['pv_derating_factor']  # derating factor that reduce the efficiency of the modules
    result_ac_energies_gens_derated = simulate_gens_derated_productivity(derating_factor, result_ac_energies_gens)

    # crete two unstacked dataframe (the other functions work with dictionaries)
    result_ac_energies_to_csv_df = simulate_unstacked_productivity(result_ac_energies_gens_derated)

    # export results in a csv file
    print("11.2. Export csv ")

    path = str(config['filename_output_csv_gen_pv'])
    result_ac_energies_to_csv_df.to_csv(path, encoding='utf-8')

    print("\n     completed!")

###############################################################################################################################

def get_input_gens_analysis():
    
    """Reading the data from the yaml file and save them into the internal variables of the script

    Outputs:
        locations_input
        capacity_input
        gen_data
    """
    # initializing dictrionaries andl lists to save the data of the generators of the configuration under exam
    gen_data = {} 
    locations_input = []
    capacity_input = {} 

    config = yaml.safe_load(open("config.yml", 'r')) 
    name_yaml_file = str(config['filename_registry_user_types_yml'])
    registry_user_types = yaml.safe_load(open(name_yaml_file, 'r')) 

    for user in registry_user_types:

        if str(registry_user_types[user]['pv']) == "nan" or registry_user_types[user]['pv'] == 0:
            pass

        else:
            location_it = str(registry_user_types[user]['location'])
            location = location_italian_to_english(location_it)
            capacity = float(registry_user_types [user]['pv']) # installed capacitity for the given plant
            tilt_angle = float(registry_user_types[user]['tilt_angle']) # tilt angle of the modules over the horizontal surface in degrees
            azimuth = float(registry_user_types[user]['azimuth']) # azimuth angle of the modules, with respect to South
            
            gen_data [user] = {'location' : location, 'capacity' : capacity, 'tilt_angle' : tilt_angle, 'azimuth' : azimuth} # saving useful information in a dictionary
            
            locations_input.append(location) # saving all locations to be analyzed in a list

            capacity_input.setdefault(location, [])
            capacity_input[location].append(capacity) # saving the installed capacity for each location, dictionary indixed on locations

    locations_input = [*set(locations_input)] # removing duplicates
    locations_input.sort() # sorting in alphabetic order

    return locations_input, capacity_input, gen_data

###############################################################################################################################

def get_coordinates(address):

    """we evaluate the latitude and the longitude of a location in input as "address" (it needs just the name of the location, ex. "Roma")
    Inputs:
        address              the name of the location you want to evaluate latitude and longitude [str]
    Outputs:
        location.latitude    latitude of the location [float]
        location.longitude   longitude of the location [float]
    """

    geolocator = Nominatim(user_agent="myapplication")
    location = geolocator.geocode(address)
    
    return location.latitude, location.longitude

###############################################################################################################################

def create_coordinates_dataset(locations_input):

    """we create a dataset in which we save for each location under exam the values of latitude, longitude, name, altitude and time zone
    Inputs:
        locations_input        list with the name of the locations under exam [list]
    Outputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    """

    coordinates_dataset = [] # initialization

    for name_location in locations_input:

        latitude_location = get_coordinates(name_location)[0]
        longitude_location = get_coordinates(name_location)[1]
        altitude_location = pvlib.location.lookup_altitude(latitude_location, longitude_location)

        data_location = (latitude_location, longitude_location, name_location, altitude_location, 'Etc/GMT+2')

        coordinates_dataset.append(data_location)

    print("\n2. Creation of the dataset with geographical information completed!")

    return coordinates_dataset
    
###############################################################################################################################

# Function: set_system()

# si ricavano le informazioni circa il modulo e l'inverter da SA (System Advisor Model, questo 
# è un software per simulazioni tecnico-economiche di impianti fotovoltaici sviluppato dal National Renewable Energy Laboratory - NREL).

def set_system():

    """we select the module and the inverter 
    Inputs:
        -
    Outputs:
        module        module item and its parameters (we fix a module with a nominal power of 100 W)
        inverter      inverter item and its parameters (we fix an inverter who respects the limits of power, voltage and current of the selected module)
    """

    sandia_modules = pvsystem.retrieve_sam('SandiaMod') # possible dataset: CECMod, SandiaMod

    # inserting the nominal power in the sandia dataset
    sorted_sandia_modules = sandia_modules

    for column in sorted_sandia_modules:
        Pmpo = sorted_sandia_modules.loc['Impo', column] * sorted_sandia_modules.loc['Vmpo', column] # potenza nominale del modulo
        sorted_sandia_modules.loc['Pmpo', column] = Pmpo
    sorted_sandia_modules = sorted_sandia_modules.sort_values('Pmpo', axis = 1, ascending = False)

    CEC_inverters = pvsystem.retrieve_sam('cecinverter') # for example, using the CEC inverter dataset

    module = sandia_modules['Shell_Solar_SM100_24__2003__E__'] # choosing module from the Sandia modules dataset
    # module = sorted_CEC_modules['MiasoleLEX_03_500W'] # choosing module from the CEC modules dataset

    # calcuting the max power power
    Pmpo_selected_mod = sorted_sandia_modules.loc['Pmpo', module.name]

    # inverter = sandia_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_'] # choosing one of the Sandia inverters
    inverter = CEC_inverters['Enphase_Energy_Inc___M175_24_208_Sxx__208V_'] # choosing one of the CEC inverters

    inverter['Pnt'] = 0

    print("3. Setting of the photovoltaic system parameters completed!")

    return module, inverter

###############################################################################################################################

def select_desired_module(desired_pow_value):

    """Selecting the module with the desired nominal power
    Inputs:
        desired_pow_value    value of the desired power of the module in (W) [float]
    Outputs:
        module               module item and its parameters
    """

    sandia_modules = pvsystem.retrieve_sam('SandiaMod') # possible dataset: CECMod, SandiaMod

    # inserting the nominal power in the sandia dataset
    sorted_sandia_modules = sandia_modules

    for column in sorted_sandia_modules:
        Pmpo = sorted_sandia_modules.loc['Impo', column] * sorted_sandia_modules.loc['Vmpo', column] # mudule nominal rated power
        sorted_sandia_modules.loc['Pmpo', column] = Pmpo
    sorted_sandia_modules = sorted_sandia_modules.sort_values('Pmpo', axis = 1, ascending = False)



    desired_pow = desired_pow_value # power [W]
    prev_diff_pow = 1000000 # setting a high value for the difference between the desired power and the module nominal rated power, that will be overwritten in the loop

    for key in sorted_sandia_modules.keys():
        Pmpo_test = sorted_sandia_modules[key]['Pmpo']
        diff_pow = abs(Pmpo_test - desired_pow)

        if diff_pow < prev_diff_pow:
            desired_key = key
            prev_diff_pow = diff_pow
        else:
            prev_diff_pow = diff_pow

    print("Desired module key:" , desired_key, '\n')
    # print("Parameters of the desired module:\n\n", sorted_sandia_modules[desired_key])

    desired_module = sorted_sandia_modules[desired_key]

    Pmpo_selected_mod = desired_module['Pmpo']

    # si plotta a schermo la relativa potenza di picco del modulo selezionato
    print("Peak power of the desired module : ", round(Pmpo_selected_mod, 2), 'W')

    print("Individuation of the module with the desired nominal power completed!")

    return desired_module

###############################################################################################################################

def check_inverter(module):
    
    """selecting the inverter who respects the limits of power, voltage and current for the module in input
    Inputs:
        module       module item and its parameters
    Outputs:
        inverter     inverter item and its parameters
    """

    Tmax = 85 # max operating temperature [°C]
    Tmin = -40 # min operating temperature [°C]
    Tamb = 25 # ambient temperature [°C]

    Vmpp = module['Vmpo'] # max power point voltage [V]
    Voc = module['Voco'] # open circuit voltage [V]
    Isc = module['Isco'] # short circuit current [A]

    beta_volt_mp = module['Bvmpo'] / 100 # voltage temperature coefficient at max power point [%]
    beta_volt_oc = module['Bvoco'] / 100 # voltage temperature coefficient at open circuit [%]
    beta_curr_sc = module['Aisc'] / 100 # current temperature coefficient at short circuit [%]

    num_mod_per_string = 1 # number of modules per string 
    num_string = 1 # number of strings

    Vmax_string = Vmpp * num_mod_per_string # max voltage per string    [V]
    Voc_string = Voc * num_mod_per_string # open circuit voltage per string [V]
    Isc_PV = Isc * num_string # short circuit current for the PV arrays [A]

    V_mod_Tmin = Vmax_string * (1-beta_volt_mp*(Tamb-Tmin))
    V_mod_Tmax = Vmax_string * (1-beta_volt_mp*(Tamb-Tmax))
    V_max_Tmin = Voc_string * (1-beta_volt_oc*(Tamb-Tmin))
    Idcmax_mod = Isc_PV * (1-beta_curr_sc*(Tamb-Tmax))
    Pdc_mod = module['Pmpo']

    CEC_inverters = pvsystem.retrieve_sam('cecinverter') 
    sorted_CEC_inverters = CEC_inverters.sort_values('Paco', axis = 1, ascending = True)

    check_tot = 0

    for key in sorted_CEC_inverters.keys():

        inverter_test = sorted_CEC_inverters[key]

        Vmax_inverter = inverter_test['Mppt_high'] # max inverter temperature
        Vmin_inverter = inverter_test['Mppt_low'] # min inverter temperature
        Idcmax_inverter = inverter_test['Idcmax'] # max current inverter in DC
        Pdc_inverter = inverter_test['Pdco'] # max power inverter in DC

        # check 1 => V_Tmin > 1.2 * Vmin_inverter
        if V_mod_Tmin > 1.2 * Vmin_inverter:
            check_1 = 1
        else:
            check_1 = 0

        # check 2 => V_mod_Tmax < 0.8 * Vmax_inverter
        if V_mod_Tmax < 0.8 * Vmax_inverter:
            check_2 = 1
        else:
            check_2 = 0

        # check 3 => Vmax_Tmin > 0.8 * Vmax_inverter
        if V_max_Tmin > 0.8 * Vmax_inverter:
            check_3 = 1
        else:
            check_3 = 0

        # check 4 => 0.5 * Idcmax_mod < Idcmax_inverter
        if Idcmax_inverter > 0.5 * Idcmax_mod:
            check_4 = 1
        else:
            check_4 = 0

        # check 5 => Pdc,STC < 0.8 * Pdc, inverter
        if Pdc_mod < 0.8 * Pdc_inverter:
            check_5 = 1
        else:
            check_5 = 0

        check_tot = check_1 * check_2 * check_3 * check_4 * check_5

        if check_tot == 1:
            break
    
    if check_tot == 1:
        print('Result of the research: Compatible inverter found! \n')

        # looking for the inverter 
        inverter_checked = sorted_CEC_inverters[key]
        print("Name of the module under exam: ", module.name, '\n')
        print("Name of the verified inverter: ", inverter_checked.name, '\n')
    else:
        print('Result of the research: No compatible inverters! \n')

    print("Individuation of the compatible inverter completed!")

    inverter_checked['Pnt'] = 0

    return inverter_checked

###############################################################################################################################

def weather_data(coordinates_dataset):

    """calculating a tipical meteorogical year (tmys) for the selected locations from PVGIS 
    via pvlib function "pvlib.iotools.get_pvgis_tmy", with timestep of 60 minutes.
    For more info:  https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.iotools.get_pvgis_tmy.html

    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    Outputs:
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
    """

    coordinates = coordinates_dataset 

    config = yaml.safe_load(open("config.yml", 'r')) 

    date_string = str(config['start_date']) # project start date
    data = dt.datetime.strptime(date_string, "%Y-%m-%d") # converting to correct format
    start_year = int(data.strftime("%Y")) # start year

    tmys = [] # initialization of the list containing the tmys data for the locations
    
    for location in coordinates:
        latitude, longitude, name, altitude, timezone = location
        weather = pvlib.iotools.get_pvgis_tmy(latitude, longitude, map_variables=True)[0] # Get TMY data from PVGIS
        weather.index.name = "datetime"
        weather.index = weather.index.map(lambda t: t.replace(year=start_year))

        # # Convert the time column to datetime and set it to UTC
        # weather.index = pd.to_datetime(weather.index, utc=True)

        # # Set the local timezone (for example, 'Europe/Rome')
        # local_timezone = 'Europe/Rome'
        # weather.index = weather.index.tz_convert(local_timezone)

        # Replace the first three rows with 0 (instead of NaN)
        weather = weather.shift(2)
        weather.iloc[:1] = 0 

        # Convert the time column to datetime and set it to UTC
        weather.index = pd.to_datetime(weather.index, utc=True)

        # Set the local timezone (for example, 'Europe/Rome')
        local_timezone = 'Europe/Rome'
        weather.index = weather.index.tz_convert(local_timezone)
        
        tmys.append(weather)

    print("\n4. Creation of the datasets with meteorogical data for the selected locations completed!")

    return tmys

###############################################################################################################################

def weather_data_15_min(coordinates_dataset):

    """Calculating a tipical meteorogical year (tmys) for the selected locations
    via pvlib function "pvlib.location.Location.get_clearsky", with timestep of 15 minutes
    For more info:    https://pvlib-python.readthedocs.io/en/latest/_modules/pvlib/location.html#Location.get_clearsky
    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    Outputs:
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
    """

    config = yaml.safe_load(open("config.yml", 'r')) 

    date_string = str(config['start_date']) # project start date
    data = dt.datetime.strptime(date_string, "%Y-%m-%d") # converting to correct format
    start_year = int(data.strftime("%Y")) # start year

    tmys_15_min = [] # initialization of the list containing the tmys data for the locations

    for coordinates in coordinates_dataset:
        latitude, longitude, name, altitude, timezone = coordinates 
        
        # Calculate the clear sky estimates of GHI, DNI, and/or DHI at this location
        location = location.Location(latitude, longitude) # creating a 'location' object
        times = pd.date_range('2022-01-01 00:00', '2023-01-01 00:00', freq='15min') # creating a time series with delta time of 15 min
        weather = location.get_clearsky(times, model = 'ineichen') # model = 'ineichen', 'haurwitz' or 'simplified_solis', creating a dataframe 
        
        # alternatively, currently suppressed
        # si usa di seguito un'altra libreria sviluppata dall'istituto NREL, non sono purtroppo presenti dati per tutte le località!
        # key = <INSERIRE API KEY>
        # email_personale = <INSERIRE EMAIL PERSONALE>
        # weather = pvlib.iotools.get_psm3(latitude, longitude, api_key = key , email = email_personale , interval = 60)
        
        weather.index.name = "datetime" # setting index name
        weather.index = weather.index.map(lambda t: t.replace(year=start_year)) # setting the correct year to the weather dataframe
        weather = weather[~weather.index.duplicated(keep='first')] # removing duplicates
        tmys_15_min.append(weather) # appending the data for each location

    print("\nCreation of the dataset with meteorogical data with a time interval of 15 min for the selected location completed!")

    return tmys_15_min

###############################################################################################################################

def simulate_module_productivity(coordinates_dataset, tmys, module, tilt_angle, azimuth, inverter):

    """simulating the system under exam and calculating the results 
       in different time interval (delta t, daily, monthly, yearly)
    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
        module                 module type and its parameters
        inverter               inverter type and its parameters
    Outputs:
        result_ac_energies     dictionary in which we save the results for each time iteration in (kWh) for 100 Wp photovoltaic generator [dict]
    """

    # setting the thermal model parameters
    temperature_model_parameters = PARAMS['sapm']['open_rack_glass_glass']  

    result_ac_energies = {} # initialazing the result dictionary

    # calculating the annual energy production for each location
    for location, weather in zip(coordinates_dataset, tmys):
        
        #GEOGRAPHICAL INFORMATION
        latitude, longitude, name, altitude, timezone = location
        location = Location(
            latitude,
            longitude,
            name = name,
            altitude = altitude,
            tz = timezone,
        )

        # MOUNTING TYPE
        mount = FixedMount(surface_tilt = tilt_angle, surface_azimuth = azimuth)

        # one array case
        array = Array(
            mount = mount,
            module_parameters = module,
            temperature_model_parameters = temperature_model_parameters,
            modules_per_string = 1,
            strings = 1,
        )

        system = PVSystem(arrays = [array], inverter_parameters=inverter)
        
        # multiple arrays case
        # array_one = Array(
        #     mount=mount,
        #     module_parameters=module,
        #     temperature_model_parameters=temperature_model_parameters,
        #     modules_per_string = 10,
        #     strings = 2,
        # )

        # array_two = Array(
        #     mount=mount,
        #     module_parameters=module,
        #     temperature_model_parameters=temperature_model_parameters,
        #     modules_per_string = 10,
        #     strings = 4,
        # )

        #system_two_arrays = PVSystem(arrays=[array_one, array_two], inverter_parameters=inverter)

        # creating the model with the system and location characteristics
        mc = ModelChain(system, location)

        # simulating the model with the weather data
        mc.run_model(weather)

        # exporting the AC output results for the selected location
        result_ac = mc.results.ac / 1000 # [kWh]

        # saving the results in a dictionary [name : location]
        result_ac_energies[name] = result_ac # [kWh]

    print("\n5. Simulation of the productivity for a single module completed!")

    return result_ac_energies

###############################################################################################################################

def simulate_1_kWp_productivity(module, result_ac_energies):

    """calculating the productivity for a photovoltaic system of 1 kWp 
       in different time interval (delta t, daily, monthly, yearly)
    Inputs:
        module                      module type and its parameters
        result_ac_energies          dictionary in which we save the results for each time iteration in (kWh / delta t) for 100 Wp photovoltaic generator [dict]
    Outputs:
        result_ac_energies_1kWp     dictionary in which we save the results for each time iteration in (kWh) for 1 kWp photovoltaic generator [dict]
    """

    result_ac_energies_1kWp = {} # initializing the output dictionary

    Pmpo_selected_mod = module['Pmpo']

    num_mod = round(1000/Pmpo_selected_mod, 0) # calcualating the number of modules needed for 1 kWp system

    # key: location
    for key in result_ac_energies.keys():

        result_ac_energies_1kWp[key] = result_ac_energies[key] * num_mod # results for 1 kWp [kWh]

    print("\n6. Simulation of the productivity for a generator with an installed capacity of 1 kWp completed!")

    return result_ac_energies_1kWp

###############################################################################################################################

def simulate_resampled_productivity(result_ac_energies_1kWp):

    """resampling the time interval of the data and set it to 1 hour 
       in different time interval (1 hour, daily, monthly)
    Inputs:
        result_ac_energies_1kWp_GSE         dictionary in which we save the results for each time iteration in (kWh / delta t) with an yealy limitation based on the GSE/RSE report [dict]
    Outputs:
        result_ac_energies_resampled        dictionary in which we save the results for each time iteration in (kWh / delta t) with resampled data based on the selected delta t [dict]
    """

    result_ac_energies_resampled = {} # initialization of the output dictionary

    config = yaml.safe_load(open("config.yml", 'r')) 

    time_interval = str(config['delta_t']) # delta t

    time_delta = pd.to_timedelta(time_interval)
    seconds = time_delta.total_seconds()
    hours = seconds / 3600

    # key: location
    for key in result_ac_energies_1kWp.keys():

        result_ac_1H = result_ac_energies_1kWp[key].copy() # [kWh]

        result_ac_1H[result_ac_1H.index[-1]+pd.Timedelta(hours = 1)] = result_ac_1H[-1]

        # if delta_t >= 1h
        if pd.to_timedelta(time_interval) >= pd.to_timedelta('1H'): 
            result_ac_resampled = result_ac_1H.resample(time_interval).sum() # [kWh]
        
        # if delta_t < 1h
        else:
            result_ac_resampled = result_ac_1H.resample(time_interval).interpolate(method = 'linear') * hours # [kWh / 15Min]

        result_ac_energies_resampled[key] = result_ac_resampled # [kWh]

        # creating an index with the correct datetime

        result_ac_energies_resampled[key] = result_ac_energies_resampled[key].reset_index()
        result_ac_energies_resampled[key].index = result_ac_energies_resampled[key]['datetime'] # setting the index
        del result_ac_energies_resampled[key]['datetime'] # removing the created column

        result_ac_energies_resampled[key]=result_ac_energies_resampled[key][:-1]

    date_string = str(config['start_date'])
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year = int(data.strftime("%Y")) 

    # erasing the leap_day values if the initial year of the simulation is a leap year
    if calendar.isleap(start_year):  
        for key in result_ac_energies_resampled.keys():
            start_time = str(start_year)+'-02-28 23:45:00'
            end_time = str(start_year)+'-03-01 00:00:00'
            result_ac_energies_resampled[key] = pd.concat([result_ac_energies_resampled[key].loc[:start_time], result_ac_energies_resampled[key].loc[end_time:]])

    print("\n7. Resampling of the data respect the specified delta t completed!")

    return result_ac_energies_resampled

###############################################################################################################################

def simulate_gens_productivity():

    """calculating the productivity for each generator with different capacity 
       in different time interval (1 hour, daily, monthly, yearly)
        Outputs:
            result_ac_energies_gens     dictionary with the results for an entire year for every pv plant (different capactity and plant parameters)
        """

    result_ac_energies_gens = {} # initialization of the output dictionary

    # create a list with all locations
    config = yaml.safe_load(open("config.yml", 'r')) 
    filename = config['filename_registry_user_types_yml']
    registry_user_types_yml = yaml.safe_load(open(filename, 'r'))

    locations_input = []

    for user in registry_user_types_yml.keys():
        location_it = registry_user_types_yml[user]['location']
        location_en = location_italian_to_english(location_it) 
        locations_input.append(location_en)

    locations_input = list(set(locations_input))

    # create a dataset with the coordinates of all the locations
    coordinates_dataset = create_coordinates_dataset(locations_input)

    gen_data = get_input_gens_analysis()[2] # this is a dictionary --> gen_data[user] = {'location' : location, 'capacity' : capacity, 'tilt_angle' : tilt_angle, 'azimuth' : azimuth}
    
    # key: gen
    for gen in gen_data.keys():
        location = gen_data[gen]['location'] # getting location
        capacity = gen_data[gen]['capacity'] # getting installed capacity [kWp]
        tilt_angle = gen_data[gen]['tilt_angle'] # getting tilt angle [°]
        azimuth = gen_data[gen]['azimuth'] # getting azimuth [°]
        
        # calculate the productivity for a PV plant with a capacity of 1 kWp in the selected location with a fixed delta t (the results are derated respect the GSE/RSE annual production found in the report)
        # result_ac_energies_resampled is a dictionary where the keys are the locations in input
        result_ac_energies_resampled = simulate_1_kWp_generators(coordinates_dataset, tilt_angle, azimuth)

        # obtaining ht edataframe for each location for the correct capacity
        result_ac_energies_gens[gen] = result_ac_energies_resampled[location] * capacity # [kWh]

    print("\n8. Simulation of the productivity for each generators  completed!")

    return result_ac_energies_gens

###############################################################################################################################

def simulate_gens_derated_productivity(derating_factor, result_ac_energies_gens):

    """calculating the productivity for each generator with different capacity and applying the derating factor 
       in different time interval (1 hour, daily, monthly, yearly)
        Inputs:
            result_ac_energies_gens             dictionary in which we save the results for each time iteration in (kWh / delta t) [dict]
        Outputs:
            result_ac_energies_gens_derated     dictionary in which we save the results for each time iteration in (kWh / delta t) considering an annual production derating [dict]
        """

    print("\n9. Derating of the yearly production")

    result_ac_energies_gens_derated = {} # initialization of the output dictionary

    config = yaml.safe_load(open("config.yml", 'r')) 

    date_string = str(config['start_date'])
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year = str(data.strftime("%Y")) 
    project_life_time = config['project_lifetime_yrs']

    # loop over the PV plants
    for gen in result_ac_energies_gens.keys():

        result_ac_energies_gens_derated.setdefault(gen, {}) # setting the key of the dictionary with the name of the generator with an empty dictionary as value

        actual_year = start_year # setting the actual year as the starting year
        derating_factor_init = 0 # initializing the derating factor for the first year to 0

        actual_result_ac_energies = result_ac_energies_gens[gen] # setting the initial values of the results, before the derating [kWh]

        # loop over years
        for year in range (0, project_life_time):
            
            actual_year_str = str(actual_year)

            result_ac_energies_gens_derated[gen].setdefault(actual_year_str, {}) # setting the key with the denomination of the actual year with a dictionary type value
            result_ac_energies_gens_derated[gen][actual_year_str] = actual_result_ac_energies * (1-derating_factor_init) # filling the derated values for the actual year [kWh]

            # updating the values
            actual_result_ac_energies = result_ac_energies_gens_derated[gen][actual_year_str] # [kWh]

            actual_year = int(actual_year) + 1 # updating the actual year
            derating_factor_init = derating_factor # getting the derating factor for the actual year
        
    print("\n\tcompleted!")

    return result_ac_energies_gens_derated

###############################################################################################################################

def simulate_unstacked_productivity(result_ac_energies_gens_derated):
    """calculating the productivity for each generator with different capacity and organizing data in an unstacked format (one column for each generators)
       in different time interval (1 hour, daily, monthly, yearly)
        Inputs:
            result_ac_energies_gens_derated          dictionary in which we save the results for each time iteration in (kWh / delta t) considering an annual production derating [dict]
        Outputs:
            result_ac_energies_to_csv_df             dataframe with results calculated for each timestep in (kWh / delta t) ready for the exportation in csv file [dataframe]
        """

    print("\n10. Formatting the dataset in an unstacked structure")

    result_ac_energies_unstacked = {} # initialization

    config = yaml.safe_load(open("config.yml", 'r')) 

    date_string = str(config['start_date'])
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year_str = str(data.strftime("%Y"))
    start_year_int = int(start_year_str)
    project_life_time = config['project_lifetime_yrs']

    for gen in result_ac_energies_gens_derated.keys():

        result_ac_energies_unstacked_df = pd.DataFrame() # initializing the dataframe with the unstacked results, with a column for eaach user

        result_ac_energies_unstacked.setdefault(gen, {}) # initializing an empty dictionary in which the results will be stored, with the name of the generator as key

        actual_year_int = start_year_int # string with the actual year (string)

        for year in range (0, project_life_time):
            
            actual_year_str = str(actual_year_int) # string with the actual year (string)

            df = result_ac_energies_gens_derated[gen][actual_year_str].copy()

            df.index = df.index.tz_convert('UTC')

            # Convert to string and remove timezone information
            df.index = df.index.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')

            shifted_df = df.shift(-4)
            shifted_df.fillna(0, inplace=True)

            shifted_df.index = [actual_year_str + row[4:] for row in shifted_df.index]

            result_ac_energies_unstacked_df = pd.concat([result_ac_energies_unstacked_df , shifted_df]) # iteratively merging the dataframes

            actual_year_int += 1 # updating the actual year

        result_ac_energies_unstacked[gen] = result_ac_energies_unstacked_df # [kWh]

        print('     ' + blue(str(gen)) + ' completed!')

    result_ac_energies_to_csv_df = pd.DataFrame() # creating the dataframe for the export

    for user in result_ac_energies_unstacked.keys():
        result_ac_energies_to_csv_df[user] = round(result_ac_energies_unstacked[user], 3) # [kWh]

    end_year_int = start_year_int + project_life_time

    # checking the condition is True or not
    for year in range(start_year_int, end_year_int):
        val = calendar.isleap(year)
        
        # adding the leap day if present in the current year
        if val == True:

            # Define the start and end of the desired range in your local time zone (UTC+1)
            start_date = (str(year)+'-02-28 00:00:00')
            end_date = (str(year)+'-03-01 00:00:00')

            # Extract the data between the specified datetime range
            leap_day = result_ac_energies_to_csv_df[(result_ac_energies_to_csv_df.index >= start_date) & (result_ac_energies_to_csv_df.index < end_date)]

            leap_day.index = [row[:8] + "29" + row[10:] for row in leap_day.index]

            start_index = (str(year)+'-02-28 23:45:00')
            end_index = (str(year)+'-03-01 00:00:00')

            df_before = result_ac_energies_to_csv_df.loc[:end_index]  # Include start_index in this case
            df_after = result_ac_energies_to_csv_df.loc[end_index:]     # Include end_index in this case

            df_before = df_before.iloc[:-1]

            df_before.index = df_before.index.str.replace(str(year) + "-02-29", str(year) + "-02-28")

            # Concatenate the DataFrames: before + new_df + after
            result_ac_energies_to_csv_df = pd.concat([df_before, leap_day, df_after])


    print ("\n\tCheck leap day completed!")

    # redefining the dateetimes used to index the dataframes using a calendar generated externally from a function (here it is removed the timezone)
    cal = get_calendar() # getting the calendar with the standard format
    result_ac_energies_to_csv_df.index = cal['datetime'] # updating the datetime index with the one from the calendar
    result_ac_energies_to_csv_df.index.name = 'datetime' # fixing the name of the index

    print("\n\tcompleted!\n")

    return result_ac_energies_to_csv_df

###############################################################################################################################

def change_index(df, gen_data):
    
    """
    Change the index of a dataframe to include location and capacity of each generator.

    Parameters
    df : pandas.DataFrame to change the index of.
    gen_data : dict with the location and capacity of each generator.

    Returns
    df : pandas.DataFrame with the modified index.
    """
    index_list = []

    for index in df.index:
        loc_str = str(gen_data[index]['location'])
        cap_str = str(gen_data[index]['capacity'])
        
        new_index = index + ' - ' + loc_str + ' - ' + cap_str + ' kWp'

        index_list.append(new_index)

    df.set_index(pd.Index(index_list), drop=False, append=False, inplace=True, verify_integrity=True)
    
    return(df)
###############################################################################################################################

def get_html_graph(df, title, y_parameter, xaxis_label, yaxis_label, path):

    """
    Function to generate a html graph from a given dataframe with a specified title, y parameter, x and y labels, and path.

    Parameters
    df : pandas.DataFrame to generate the graph from.
    title : str title of the graph.
    y_parameter : float to divide the y values by.
    xaxis_label : str to label the x axis.
    yaxis_label : str to label the y axis.
    path : str path to save the graph to.

    Returns
    fig : plotly.graph_objs.Figure the generated figure.
    """
    x = df.columns

    fig = go.Figure()

    for index in df.index:
        y = df.loc[index]/y_parameter
        fig.add_trace(go.Scatter(
            x = x, y = y,

            name = index
        ))

    fig.update_layout(
        title_text = title, 
        xaxis = dict(title = xaxis_label
                    ))

    fig.update_yaxes(title_text = yaxis_label)

    fig.write_html(path + title + ".html")

    return fig

###############################################################################################################################

def check_calendar_status():

    """
    Function to check if the calendar is updated with the correct number of values.

    The function reads the start_date and project_lifetime_yrs from the config file, then calculates the total number of values that the calendar should have considering the project lifetime and the delta_t.
    Finally, it checks if the actual number of values in the calendar is equal to the total number of values calculated.
    If the check fails, an assert error is raised with a message asking to run the function <<generate_calendar()>> again.
    """
    cal = get_calendar()
    size_cal = cal.shape[0]

    config = yaml.safe_load(open("config.yml", 'r'))  
    project_life_time = int(config['project_lifetime_yrs']) # si acquisisce la vita utile dell'impianto con cui svolgere la simulazione da file yaml
    delta_t = str(config['delta_t'])
    time_interval = pd.to_timedelta(delta_t)
    seconds = time_interval.total_seconds()
    hours = seconds / 3600

    date_string = str(config['start_date'])
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year = int(data.strftime("%Y")) # si acquisisce la vita utile dell'impianto con cui svolgere la simulazione da file yaml 
    end_year = start_year + project_life_time

    total_number_of_values = 0

    for year in range(start_year, end_year):
        val = calendar.isleap(year)
        if val == True:     
            days = 366
            total_number_of_values_year = days*24/hours

        else:
            days = 365
            total_number_of_values_year = days*24/hours

        total_number_of_values+=total_number_of_values_year

    assert int(total_number_of_values) == int(size_cal), "ERROR: the calendar is not updated, run again the function <<generate_calendar()>>"

###############################################################################################################################

def export_energy_exchange_profiles_csv():
    """creating the profile of the energy exchange with the grid for each user type, as csv, needed for the Load Flow Module"""

    # importing needed information
    config = yaml.safe_load(open("config.yml", 'r'))

    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    user_type_set = list(registry_user_types.keys()) # this is the list of all users IDs of the "registry_user_types.yml" file

    foldername_result_energy = config["foldername_result_energy"]

    # Function to process each file
    def process_user_type(user_type):
        file_path = foldername_result_energy + user_type + ".csv"
        df = pd.read_csv(file_path, index_col="datetime")
        df = df.fillna(0)
        df[user_type] = df["Eprel"].astype(float) - df["Eimm"].astype(float)
        return df[[user_type]]  # return only the net grid exchange column

    # Use multi-threading to read and process files concurrently
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(process_user_type, user_type_set))

    # Concatenate all results at once for efficiency
    df_results = pd.concat(results, axis=1)
    
    filename = config["filename_pod_energy_exchange"]
    df_results.to_csv(filename)

    print("User types net energy exchange file created!")

###############################################################################################################################

def CACER_shared_energy_for_TIP():
    """
    Calculates and exports the shared energy for TIP (Tariff Incentive Premimum) for each configuration.

    This function processes energy exchange data for each configuration, identifying the energy withdrawal 
    and injection for incentive purposes. It calculates the shared energy based on the minimum of energy 
    withdrawn and injected, allocates the shared energy to each plant based on seniority, and exports 
    the results both hourly and yearly.

    The function also handles cases where no CACER is present, exporting 
    zero-filled dataframes in such cases.

    Outputs:
        - Two CSV files with the shared energy data for TIP: one with hourly data and another with yearly data.
    """

    print(blue('\nCalculating shared energy for TIP:'))
    
    config = yaml.safe_load(open("config.yml", 'r'))

    check_file_status(config["filename_incentive_shared_energy_hourly"])
    check_file_status(config["filename_incentive_shared_energy_yearly"])

    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    plants_set = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    project_lifetime_yrs = config["project_lifetime_yrs"]
    
    df_results = pd.DataFrame() # initializing an empty dataframe

    for configuration in recap["configurations"]:

        print("\n- Configuration: " + configuration)

        # 1) calculating the energy withdrawal from the grid, for the incentive purpose calculation
        # all the user types which contribute to the Eprel calculation (including the prosumers with old plant)
        user_type_set_configuration = [user_type for user_type in registry_user_types.keys() if registry_user_types[user_type]["CP"] == configuration and registry_user_types[user_type]["num"] > 0 and registry_user_types[user_type]["flag_cacer"]]
        print("User types: ", len(user_type_set_configuration))
        user_type_set_configuration_consuming = [user_type for user_type in user_type_set_configuration if registry_user_types[user_type]["consuming"]]
        print("Consuming users: ", [(user_type, registry_user_types[user_type]["num"]) for user_type in user_type_set_configuration_consuming])

        df_consuming_quarterly = import_users_energy_flow_single_column(user_type_set_configuration_consuming, "Eprel")
        df_consuming_quarterly["dayhour"] = df_consuming_quarterly.index.str[:13]
        df_consuming_hourly = df_consuming_quarterly.groupby(["dayhour"]).sum()

        # # If no CACER, then no need to compute the shared energy. Exporting a dataframe of zeros correctly formatted and returning
        ###########################################################################################################
        # # TO DO: SISTEMARLO FUORI DAL CICLO IN MANIERA PIU INTUITIVA ###############################################
        ###########################################################################################################
        # if recap["type_of_cacer"] == "NO_CACER":
        #     print("No CACER present --> no shared energy")
        #     df_results = pd.DataFrame(index = df_consuming_hourly.index, columns=["Econd_CACER"])
        #     df_results.replace(0,np.nan).to_csv(config["filename_incentive_shared_energy_hourly"])
        #     return

        # exporting the aggregated values
        list_num = [registry_user_types[user_type]["num"] for user_type in df_consuming_hourly.columns] 
        df_results['Eprel_config'] = 0
        df_results["Eprel_config"] = df_consuming_hourly.multiply(list_num).sum(axis=1) # sumproduct: multiplying each energy flow by the number of users for each user_type, then summing up.
        # this will be overwritten by each configuration


        # 2) calculating the E injected into the grid by the eligible plants 

        # all the producers which contribute to the Eimm calculation (removing the producers and prosumers with an old plant, as they do not generate shared energy valid for the inventives
        user_type_set_configuration_producing_new_plant = [user for user in user_type_set_configuration if registry_user_types[user]["producing"] and registry_user_types[user]["new_plant"]]
        # print("Producing users with new plant: ", user_type_set_configuration_producing_new_plant)

        df_producing_quarterly = import_users_energy_flow_single_column(user_type_set_configuration_producing_new_plant, "Eimm")
        df_producing_quarterly["dayhour"] = df_producing_quarterly.index.str[:13]
        df_producing_hourly = df_producing_quarterly.groupby(["dayhour"]).sum()

        # exporting the aggregated values
        list_num = [registry_user_types[user_type]["num"] for user_type in df_producing_hourly.columns] 
        df_results["Eimm_config"] = df_producing_hourly.multiply(list_num).sum(axis=1) # sumproduct: multiplying each energy flow by the number of users for each user_type, then summing up. 
        # this will be overwritten by each configuration
        
        # keeping track of the sum of all energy injected in the grid by the entire CACER, needed later for the Surplus calculation
        if "Eimm_CACER" not in df_results.columns:
            df_results["Eimm_CACER"] = df_results["Eimm_config"]
        else: 
            df_results["Eimm_CACER"] += df_results["Eimm_config"]


        # 3) calculating the shared Energy and assigning the share in kWh to each plant based on the seniority level. In fact, as per GSE's instruction, 
        # each plant will have its own TIP based on size and access to public grants (PNRR), and the allocation of share energy is based on construction and entry date in the configuration (seniority)

        Econd_config = "Econd_config_" + configuration # this will be saved for eache configuration
        df_results[Econd_config] = df_results[["Eprel_config","Eimm_config"]].min(axis=1)
        df_results["Eprel_residual"] = df_results["Eprel_config"] # initialization, will be overwritten by each configuration
        df_results["zeros"] = 0 # just needed for the calculation, to avoid negative values in the Eprel_residual calculation

        plant_cols = []
        print("The total shared energy of the configuration is generated hierarchically by the following plants:")

        for plant in recap["plants_sorted_by_seniority"]:
            plat_user_type = plants_set[plant]["user_type"]
            
            # skipping the plants if not in the configuration
            if plat_user_type not in user_type_set_configuration_producing_new_plant:
                continue

            # assigning the shared energy generation to each plant sorted by seniority 
            df_results["plant_production"] = df_producing_hourly[plat_user_type]
            # print(f"Plant {plant} injected {df_results['plant_production'].sum():,.1f}")

            col_name = "Econd_" + plant
            plant_cols.append(col_name)
            df_results[col_name] = df_results[['Eprel_residual',"plant_production"]].min(axis=1)
            df_results["Eprel_residual"] = df_results['Eprel_residual'] - df_results[col_name]
            df_results["Eprel_residual"] = df_results[['Eprel_residual',"zeros"]].max(axis=1)

            share = df_results[col_name].sum() / df_results[Econd_config].sum()
            print(f"\tPlant {blue(plant)}, type {plat_user_type} share:\t {share*100:,.1f} %")

        assert abs(df_results[plant_cols].sum(axis=1).sum() - df_results[Econd_config].sum()) < 0.0001, "ERROR in plants' shares of shared energy. They don't add up"
        
        print(f"Configuration {configuration} for TIP: \
            \n\t{df_results[Econd_config].sum()/1000/project_lifetime_yrs:,.0f} MWh/y shared, \
            \n\t{df_results['Eprel_config'].sum()/1000/project_lifetime_yrs:,.0f} MWh/y withdrawal, \
            \n\t{df_results['Eimm_config'].sum()/1000/project_lifetime_yrs:,.0f} MWh/y injected.")

        df_results.drop(columns=["plant_production","zeros","Eprel_config","Eprel_residual","Eimm_config"], inplace=True) # dropping unneeded columns

    # summing up all configurations shared energy
    config_cols = [col for col in df_results.columns if col.startswith("Econd_config_")]
    df_results["Econd_CACER"] = df_results[config_cols].sum(axis=1)

    assert not df_results.isnull().values.any(), "ERROR: There are NaN values in the dataframe. Indexes probably got mixed up"

    df_results.replace(0,np.nan).to_csv(config["filename_incentive_shared_energy_hourly"])

    # downsampling to yearly, to compute the Econd/Eimm ratio, needed later on for the surplus calculation
    df_results["year"] = df_results.index.str[:4]
    df_results_yearly = df_results.groupby(["year"])[["Eimm_CACER", "Econd_CACER"]].sum()
    df_results_yearly["perc_cond_annuale"] = df_results_yearly["Econd_CACER"] / df_results_yearly["Eimm_CACER"]
    df_results_yearly.rename(columns={"Econd_CACER":"Econd","Eimm_CACER":"Eimm"}, inplace=True)
    df_results_yearly.to_csv(config["filename_incentive_shared_energy_yearly"])
    assert not df_results_yearly.isnull().values.any(), "ERROR: There are NaN values in the dataframe"

    # If no CACER, then no need to compute the shared energy. Exporting a dataframe of zeros correctly formatted and returning
    ###########################################################################################################
    # TO DO: SISTEMARLO FUORI DAL CICLO IN MANIERA PIU INTUITIVA ###############################################
    ###########################################################################################################

    if recap["type_of_cacer"] == "NO_CACER":
        print("No CACER present --> no shared energy")
        # overwriting
        df_results = pd.DataFrame(index = df_results.index, columns=df_results.columns)
        df_results.fillna(0).to_csv(config["filename_incentive_shared_energy_hourly"])

        df_results_yearly = pd.DataFrame(index = df_results_yearly.index, columns=df_results_yearly.columns)
        df_results_yearly.fillna(0).to_csv(config["filename_incentive_shared_energy_yearly"])

        return

    print("\n**** Shared energy for TIP exported ****")

###############################################################################################################################

def CACER_shared_energy_for_valorization():

    """
    Calculates and exports the shared energy for VALORIZZAZIONE ARERA for each configuration.

    This is similar to the CACER_shared_energy_for_TIP function, but focused on the VALORIZZAZIONE ARERA.
    The calculation is slightly different, as for TIP it's necessary to check the seniority of each plant 
    and reconduct the shared energy generated by ach plant, as TIP tariff changes based on the installed capacity and location.

    For the valorization, the shared energy calculation is simplified, but needs to consider the voltage level, as described in the 
    TIAD formula. Thus there is a need to distinguish the shared enerrgy for the 2 different purposes, even if in most of the cases
    the final values will be exactly the same. 

    This function processes energy data for each configuration, identifying energy withdrawal 
    and injection at different voltage levels for valorization purposes. It calculates the shared 
    energy based on the minimum of energy withdrawn and injected, aggregates the energy data 
    by voltage level, and exports the results on both an hourly and monthly basis. 

    The function also manages cases where no CACER is present, 
    exporting zero-filled dataframes in such cases. Additionally, it calculates and saves user-specific 
    energy profiles and aggregated energy flows for reporting purposes.

    Outputs:
        - CSV files with shared energy data on an hourly basis.
        - Excel files with monthly aggregated energy data for each user type and configuration.
        - Updates the recap YAML file with percentage of consumer withdrawals on total.
    """

    print(blue('\nCalculating shared energy for valorization:'))
          
    config = yaml.safe_load(open("config.yml", 'r'))
    check_file_status(config["filename_CACER_energy_monthly"])

    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    project_lifetime_yrs = config["project_lifetime_yrs"]

    # opening an excel file where the data will be written. The name will be assigned later in the saving phase
    app = xw.App(visible=False) # opening in background
    wb = app.books[0] 

    for configuration in recap["configurations"]: # looping over configurations

        print(f"\n- Configuration: {configuration}")

        user_type_set_configuration = [user_type for user_type in registry_user_types.keys() if registry_user_types[user_type]["CP"] == configuration and registry_user_types[user_type]["num"] > 0 and registry_user_types[user_type]["flag_cacer"]]
        print("User types: ", len(user_type_set_configuration))
        print("Users: ", [(user_type, registry_user_types[user_type]["num"]) for user_type in user_type_set_configuration])
        user_type_set_configuration_old_plants = [(user_type, registry_user_types[user_type]["num"]) for user_type in user_type_set_configuration if not registry_user_types[user_type]["new_plant"] and registry_user_types[user_type]["producing"]]
        print(f"Old plants and numerosity: {user_type_set_configuration_old_plants}")

        df_merged = import_users_energy_flows(user_type_set_configuration) 

        # creating a column "MT", with value True if the energy flow refers to a POD in medium voltage, or False if in low voltage
        user_type_set_MT = [user for user in registry_user_types.keys() if registry_user_types[user]["voltage"] == "MT"]

        df_merged["MT"] = False # initializing everything to Low Voltage, then we will overwrite it when we have Medium Voltage

        for user_type in user_type_set_configuration:
            if registry_user_types[user_type]["voltage"] == "MT": 
                df_merged.loc[df_merged["user"] == user_type, "MT"] = True
                user_type_set_MT.append(user_type)

        # print("Medium Voltage user types are:", df_merged[df_merged["MT"] == True]["user"].unique()) #facciamo un check visivo se gli utenti in MT sono effettivamente quelli che gli abbiamo dato

        # computing
        df_merged["Eut_bt"] = df_merged["Eut"] * ~df_merged["MT"] # please note that ~ is used to deny the T/F value, so that True turns to False and viceversa
        df_merged["Eut_mt"] = df_merged["Eut"] * df_merged["MT"]
        df_merged["Eprod_bt"] = df_merged["Eprod"] * ~df_merged["MT"]
        df_merged["Eprod_mt"] = df_merged["Eprod"] * df_merged["MT"]
        df_merged["Eimm_bt"] = df_merged["Eimm"] * ~df_merged["MT"]
        df_merged["Eimm_mt"] = df_merged["Eimm"] * df_merged["MT"]
        df_merged["Eprel_bt"] = df_merged["Eprel"] * ~df_merged["MT"]
        df_merged["Eprel_mt"] = df_merged["Eprel"] * df_merged["MT"]
        df_merged["Eaut_bt"] = df_merged["Eaut"] * ~df_merged["MT"]
        df_merged["Eaut_mt"] = df_merged["Eaut"] * df_merged["MT"]
        df_merged["Eperdite_bt"] = df_merged["Eperdite"] * ~df_merged["MT"]
        df_merged["Eperdite_mt"] = df_merged["Eperdite"] * df_merged["MT"]

        # aggregating the data based on their numerosity in the configuration. From here on, values are aggregated!
        df_merged_agg = df_merged.copy()
        col_agg_list = ["Eut","Eprod","Eaut_PV","Eaut_batt","Eaut","Eperdite","Eprel","Eimm","Eut_bt",
                        "Eut_mt","Eprod_bt","Eprod_mt","Eimm_bt","Eimm_mt","Eprel_bt","Eprel_mt","Eaut_bt","Eaut_mt","Eperdite_bt","Eperdite_mt"]
        df_merged_agg[col_agg_list] = df_merged_agg[col_agg_list].multiply(df_merged_agg["num"], axis="index")

        df_merged_agg["dayhour"] = df_merged_agg["datetime"].str[:13] # format "YYYY-MM-DD HH" f.i. "2024-06-18 01"

        # IMPORTANT: as per TIAD, the shared energy is calculated on hourly basis. If done by quarterly basis, it returns an error (few % points)
        # Then it is important to add up the 15min datapoints to hourly before proceeding!!!

        # dataframe with all the values of the cacer aggregated on hourly/quarterly basis
        totals_hourly = df_merged_agg.groupby(["dayhour"])[col_agg_list].sum()

        totals_hourly["Econd_bt"] = totals_hourly[['Eprel_bt','Eimm_bt']].min(axis=1) # da TIAD, Econd for low voltage is only bt-->bt
        totals_hourly["Econd_mt"] = totals_hourly[['Eprel','Eimm_mt']].min(axis=1) # da TIAD, Econd for medium voltage is mt-->mt+bt
        totals_hourly["Econd"] = totals_hourly[['Eprel','Eimm']].min(axis=1)
        # WARNING: Econd != Econd_bt + Econd_mt! as we could have bt-->mt sharing, which is not computed in the Econd_bt and Econd_mt columns

        print(f"Configuration {configuration} for Valorization: \
            \n\t{totals_hourly['Econd'].sum()/1000/project_lifetime_yrs:,.0f} MWh/y shared, \
            \n\t{totals_hourly['Eprel'].sum()/1000/project_lifetime_yrs:,.0f} MWh/y withdrawal, \
            \n\t{totals_hourly['Eimm'].sum()/1000/project_lifetime_yrs:,.0f} MWh/y injected.")

        # saving part of the dataframe, replacing 0s with NaN to save space
        # totals[["Eut","Eprod","Eimm","Eprel","Eaut","Eperdite", "Econd"]].replace({'0':np.nan, 0:np.nan}).to_csv(config["filename_CACER_energy_quarterly"])

        valorization_cols = ["Econd","Econd_bt","Econd_mt"]
        totals_cond_hourly = totals_hourly[valorization_cols]
        # totals_cond_hourly = totals.groupby(["dayhour"])[valorization_cols].sum()
            
        bt_percentage = (totals_cond_hourly["Econd_bt"].sum() / totals_cond_hourly["Econd"].sum())*100
        print(f"\nConfiguration {configuration} with {totals_cond_hourly['Econd'].sum()/1000:,.0f} MWh shared for Valorizzazione, {bt_percentage:,.0f} % of which on Low Voltage")

        # these are the columns needed for the charts, to visualize the aggregated energy flows of the CACER.
        # scope here is to export the overall aggregated energy flows for reporting purposes
        cols_for_totals = ["Eut","Eprod","Eimm","Eprel","Eaut","Eperdite","Econd"] 
        if "totals_CACER_hourly" not in locals():
            totals_CACER_hourly = pd.DataFrame()
            totals_CACER_hourly[cols_for_totals] = totals_hourly[cols_for_totals] # creating the total column, for the sum
        else:
            totals_CACER_hourly[cols_for_totals] += totals_hourly[cols_for_totals] # adding to the total column

        # here the idea is to aggregate only the shared energy per voltage level, and the configuration's, so to compare the totals. This will be used to compute the valorization
        config_cols = [value + "_" + configuration for value in valorization_cols]
        if "totals_cond_hourly_CACER" not in locals():
            totals_cond_hourly_CACER = pd.DataFrame()
            totals_cond_hourly_CACER[valorization_cols] = totals_cond_hourly[valorization_cols] # creating the total column, for the sum
            totals_cond_hourly_CACER[config_cols] = totals_cond_hourly[valorization_cols] # creating the configuration columns
        else:
            totals_cond_hourly_CACER[valorization_cols] += totals_cond_hourly[valorization_cols] # adding to the total column
            totals_cond_hourly_CACER[config_cols] = totals_cond_hourly[valorization_cols] # creating the configuration columns

        # downsampling to monthly values, aaggregating totals. For CACER, configurations and all users. Saving and exporting to excel
        # totals["month"] = totals.index.dt.strftime("%Y-%m") # this method wouldbe preferable, but is too slow.... 
        totals_hourly["month"] = totals_hourly.index.str[:7] # ... thus for now treating it as string
        totals_monthly = totals_hourly.groupby(["month"]).sum()

        # computing the  Load Cover Factor self-consumed and shared #Please note that denominators should not be 0s, as it is a monthly sum
        totals_monthly["LCF_aut"] = totals_monthly["Eaut"] / totals_monthly["Eut"] # self-consumed
        totals_monthly["LCF_cond"] = totals_monthly["Econd"] / totals_monthly["Eut"] # shared
        # computing Supply Cover Factor self-consumed and shared
        totals_monthly["SCF_aut"] = totals_monthly["Eaut"] / totals_monthly["Eprod"] # self-consumed
        totals_monthly["SCF_cond"] = totals_monthly["Econd"] / totals_monthly["Eprod"] # shared

        totals_monthly["Eprel_non_cond"] = totals_monthly["Eprel"] - totals_monthly["Econd"]
        totals_monthly["Evend_non_cond"] = totals_monthly["Eimm"] - totals_monthly["Econd"]

        df_merged["month"] = df_merged["datetime"].str[:7]

        # please note that df_merged refers to data of a single user type only, while df_merged_agg is the sum 
        # of all users of that type, for each type. Thus for the export of a single user we use df_merged, 
        # for the aggregation we use totals which comes from df_merged_agg

        perc_prelievi_consumer_su_totale = {}

        for user_type in user_type_set_configuration:
            # writes as many sheets as there are dataframes to transfer
            df_user = df_merged.loc[df_merged["user"] == user_type, :]
            df_user = df_user.drop(columns=['datetime',"user","MT","battery_cumulative_charge","SOCkWh","SOCperc","LCF_aut","SCF_aut"], errors="ignore") # drop cols only if they exist
            df_user_monthly = df_user.groupby(["month"]).sum()


            df_user_monthly["LCF_aut"] = df_user_monthly["Eaut"] / df_user_monthly["Eut"]
            df_user_monthly["SCF_aut"] = df_user_monthly["Eaut"] / df_user_monthly["Eprod"]

            wb.sheets.add(name=user_type) # creating the empty sheet for the user type...
            wb.sheets[user_type]["A1"].options(pd.DataFrame, header=1, index=True, expand='table').value = df_user_monthly # ...then pasting the values in it

        wb.sheets.add(name=configuration) # creating the empty sheet for the configuration...       
        wb.sheets[configuration]["A1"].options(pd.DataFrame, header=1, index=True, expand='table').value = totals_monthly # ...then pasting the values in it

        if "totals_month_CACER" not in locals():
            totals_month_CACER = totals_monthly
        else:
            totals_month_CACER += totals_monthly

    totals_CACER_hourly.to_csv(config["filename_CACER_energy_hourly"])

    totals_month_CACER.drop(columns=["LCF_aut","SCF_aut"], inplace=True)
    wb.sheets.add(name="CACER") 

    if recap["type_of_cacer"] == "NO_CACER":
        totals_month_CACER["Econd"] = 0
        totals_month_CACER["Econd_bt"] = 0
        totals_month_CACER["Econd_mt"] = 0

    wb.sheets["CACER"]["A1"].options(pd.DataFrame, header=1, index=True, expand='table').value = totals_month_CACER 

    wb.save(config["filename_CACER_energy_monthly"]) 
    wb.close()
    app.quit()

    totals_cond_hourly_CACER = totals_cond_hourly_CACER.add_suffix('_VAL')
    totals_cond_hourly_CACER.to_csv(config["filename_valorization_shared_energy_hourly"])

    # If no CACER, then no need to compute the shared energy. Exporting a dataframe of zeros correctly formatted and returning
    # TO DO: SISTEMARLO FUORI DAL CICLO IN MANIERA PIU INTUITIVA ###############################################
    ###########################################################################################################
    if recap["type_of_cacer"] == "NO_CACER":
        print("No CACER present --> no shared energy")
        # overwriting
        totals_CACER_hourly = pd.DataFrame(index = totals_CACER_hourly.index, columns=totals_CACER_hourly.columns)
        totals_CACER_hourly.fillna(0).to_csv(config["filename_CACER_energy_hourly"])

        totals_cond_hourly_CACER = pd.DataFrame(index = totals_cond_hourly_CACER.index, columns=totals_cond_hourly_CACER.columns)
        totals_cond_hourly_CACER.fillna(0).to_csv(config["filename_valorization_shared_energy_hourly"])

        return

    add_to_recap_yml("perc_prelievi_consumer_su_totale", perc_prelievi_consumer_su_totale)

    print("\n**** Shared energy for Valorizzazione exported! ****")

###############################################################################################################################

def CACER_shared_energy():
    """
    Calls the functions to calculate the shared energy for the TIP and the valorization.
    """

    print(blue("\nCalculate CACER shared energy:", ['bold', 'underlined']))

    CACER_shared_energy_for_TIP()

    CACER_shared_energy_for_valorization()

###############################################################################################################################

def suppress_printing(func, *args, **kwargs):
    """function to suppress the printing sections of a specified function"""
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)

###############################################################################################################################

def suppress_printing_no_args(func):
    """
    Suppresses the printing sections of a specified function without arguments.
    This function takes a function as an argument and redirects the standard output to a StringIO object, effectively suppressing any print statements in the function.
    Parameters
    func :  The function for which to suppress the printing sections.
    Returns
    func    The function with printing sections suppressed.
    """
    
    with contextlib.redirect_stdout(io.StringIO()):
        return func()

###############################################################################################################################

def CACER_injected_energy_optimizer():

    """
    Calculates and exports the energy injected into the grid for the optimizer.

    This function calculates the energy withdrawn from the grid, the energy injected into the grid, and the net injected energy for the optimizer.
    It exports the results to a CSV file.

    Outputs:
        - A CSV file with the energy injected into the grid for the optimizer.
    """
    print("\nInjected energy for optimizer:\n")

    ########### INPUTS ##############
    config = yaml.safe_load(open("config.yml", 'r'))

    check_file_status(config["filename_injected_energy_optimizer"])

    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))

    df_results = pd.DataFrame() # in this dataframe we will save all the result for the csv exporting

    # 1) calculating the energy withdrawal from the grid

    # we extract only the list of users that participate to energy community 
    user_type_set_configuration = [user_type for user_type in registry_user_types.keys() if registry_user_types[user_type]["num"] > 0 and registry_user_types[user_type]["flag_cacer"]]
    print("User types: ", len(user_type_set_configuration))

    # we extract only the list of users that participate to energy community and are also consumer
    user_type_set_configuration_consuming = [user_type for user_type in user_type_set_configuration if registry_user_types[user_type]["consuming"]]

    # we import all quarterly withdrawn energy for all consumers 
    df_consuming_quarterly = import_users_energy_flow_single_column(user_type_set_configuration_consuming, "Eprel") 

    # exporting the aggregated values
    list_num = [registry_user_types[user_type]["num"] for user_type in df_consuming_quarterly.columns] # export the number of user for each consumer
    df_results["Eprel_config"] = df_consuming_quarterly.multiply(list_num).sum(axis=1) # sumproduct: multiplying each energy flow by the number of users for each user_type, then summing up.

    # 2) calculating the E injected into the grid 

    user_type_set_configuration_producing_new_plant = [user for user in user_type_set_configuration if registry_user_types[user]["producing"] and registry_user_types[user]["new_plant"]]
    print("Producing users with new plant: ", user_type_set_configuration_producing_new_plant)

    df_producing_quarterly = import_users_energy_flow_single_column(user_type_set_configuration_producing_new_plant, "Eimm")

    # exporting the aggregated values
    list_num = [registry_user_types[user_type]["num"] for user_type in df_producing_quarterly.columns] # export the number of user for each prosumer/producer
    df_results["Einj_config"] = df_producing_quarterly.multiply(list_num).sum(axis=1) # sumproduct: multiplying each energy flow by the number of users for each user_type, then summing up. 

    # 3) calculating the net injected energy (we don't consider the washing-machine and dishwasher in the load profile calculation) 
    df_results["Enet_inj_config"] = df_results["Einj_config"] - df_results["Eprel_config"] # we calculate for each timestep the minimum value between the injected and withdrawn aggregated energy for the entire energy community
    df_results['Enet_inj_config'].iloc[[0]] = 0
    df_results["Enet_inj_config"] = df_results["Enet_inj_config"].where(df_results["Enet_inj_config"] >= 0, 0)

    assert not df_results.isnull().values.any(), "ERROR: There are NaN values in the dataframe. Indexes probably got mixed up"

    df_results.to_csv(config["filename_injected_energy_optimizer"])

    print("\nInjected energy for optimizer exported!")