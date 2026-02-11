import calendar
import pandas as pd 
import numpy as np
import pulp as plp
from pulp.apis.coin_api import PULP_CBC_CMD
import time
from simple_colors import blue
from tqdm.auto import tqdm
import yaml

from HVAC_simulator.functions.io import read_weather_parameters, df_results_generator, users_list_generator
from HVAC_simulator.functions.thermal_load import th_fluxes_generator
from HVAC_simulator.functions.milp_model.milp_io import *
from HVAC_simulator.functions.milp_model.milp_constraints import *

from src.Functions_Energy_Model import create_coordinates_dataset, suppress_printing

#-------------------CONSTANTS-------------------
M = 100000000 # Big M constant for MILP model
P_CONTRACT_USER = 3500 # Contracted power for each user [W]

T_MAX = 26 # Maximum setpoint temperature [°C]
T_MIN = 19 # Minimum setpoint temperature [°C]

ELECTRICITY_COST = 0.35 # Electricity cost [€/kWh]
RID = 0.15 # Feed-in tariff [€/kWh]
INC = 0.13 # Incentive for energy fed into the grid [€/kWh]

def optimized(cacer, month='Gen', year=2005):

    """
    Function to optimize the energy consumption of a non-optimized Heat Pump system for an office building with a setpoint temperature.

    Parameters
    ----------
    cacer : CacerConfig
        Configuration of the CACER
    climate_data_file : str
        File path of the climate data file
    location : str
        Location of the building
    pv_data_file : str
        File path of the PV data file

    Returns
    -------
    df_total_results : pandas.DataFrame
        DataFrame containing the energy consumption and thermal load of the Heat Pump system for each user type
    """
    
    print(blue("Optimized HVAC simulation:", ["bold", "underlined"]), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))

    location = config['provincia_it'] # getting the location from the configuration file

    coordinates = suppress_printing(create_coordinates_dataset, [location])

    climate_data_filename = config['filename_weather_data']

    pv_data_file = config['filename_output_csv_gen_pv'] # File path of the solar PV data

    #-------------------INPUT TIME-------------------
    mese = month # Scegli il mese per l'ottimizzazione (Gen, Feb,... Ott...)
    anno = year # Inserisci l'anno per l'ottimizzazione

    dt, n_intervals, total_intervals, e_cast_pv, month_days = time_forecast_data_generator(mese, anno, pv_data_file, cacer.simulation_interval) # Generate time forecast data

    print(f" - Simulation month:", blue(mese), blue(anno), f"with", blue(month_days), f"days \n")

    #-------------------USERS' VARIABLES CHARACTERIZATION-------------------
    df_total_results, user_name_list, n_prosumers, hp_users_list, prosumer_p_contr, consumer_p_contr, hp_hvac_users_list = users_list_generator(cacer.hp_users_type, n_intervals, P_CONTRACT_USER, M) # Generate users' list and variables
    df_climate_data, months, t_ext, rh_ext = read_weather_parameters(climate_data_filename) # Read climate data parameters
    
    mode_pdc = mode_pdc_generator(months, total_intervals) # Generate heating/cooling mode based on months
    
    n_consumers = len(hp_users_list) # Number of consumers with heat pumps
    t_start_dayahead = np.ones((n_consumers,3))*T_MIN # Initial day-ahead temperature setpoint for each user type

    # Generate thermal fluxes for each user type
    for config in range(len(cacer.hp_users_type)):
        phi_ia, phi_st, phi_m = th_fluxes_generator(cacer.hp_users_type[config], df_climate_data, coordinates) 
    
    #------------------- MONEY INPUT CONSTANTS-------------------
    costo_prel      =   [[ELECTRICITY_COST for _ in range(n_intervals)] for _ in range(n_consumers)] # Electricity cost for each consumer and interval
    rid             =   [[RID for _ in range(n_intervals)] for _ in range(n_consumers)] # Feed-in tariff for each consumer and interval

    #####################################################################################################################
    ##################################### MILP OPTIMIZATION PROBLEM #####################################################
    #####################################################################################################################

    #---------------------------------------- MILP CONSTANTS ENERGY AND THERMAL -----------------------------------------  

    set_P, set_HVAC, set_N, set_T, set_Temp = milp_intervals(n_prosumers, n_consumers, n_intervals) # Generate MILP model sets

    #---------------------------------------- CER -----------------------------------------

    if cacer.cacer_type == 'CER':
        t_media=(T_MAX+T_MIN)/2 # Average temperature for CER type CACER
        eta, q_max, q_min, pe_defrost, q_crankcase_activation = milp_hp_autonomous_constants(total_intervals, n_consumers, hp_users_list, hp_hvac_users_list, t_media, t_ext, rh_ext, months) # Generate MILP model constants for CER type CACER
    
    #---------------------------------------- AUC -----------------------------------------

    elif cacer.cacer_type == 'AUC':
        t_water_tank_0 = (cacer.hp_users_type[0].users[0].hp_aux.t_cut_in + cacer.hp_users_type[0].users[0].hp_aux.t_dead_band) # Generate initial water tank temperature for AUC type CACER
        eta, q_max, q_min = milp_hp_centralized_constants(total_intervals, hp_users_list, hp_hvac_users_list, t_water_tank_0, t_ext, months) # Generate MILP model constants for AUC type CACER
        
        if cacer.hp_users_type[0].users[0].hp_heating.thermal_storage == True:
            t_water_tank_0 = (cacer.hp_users_type[0].users[0].hp_aux.t_cut_in + cacer.hp_users_type[0].users[0].hp_aux.t_dead_band) # Initial water tank temperature
            k_compressor_status_0 = 0 # Initial compressor status

    for day in tqdm(range(month_days), desc = " - Day: "):  
        
        start_time_optimization = n_intervals*(day)

        opt_model = plp.LpProblem(name="MIP_Model")  # modello di ottimizzazione     

        #---------------------------------------- MILP VARIABLES ENERGY AND THERMAL -----------------------------------------                                                                                                               

        e_in_vars, e_out_vars, k_vars, l_vars, e_in_virtual_vars, e_out_virtual_vars, a_vars, b_vars = milp_energy_variables(set_P, set_N) # Energy variables
        
        phi_hc_nd_ac, omega_m_ac, omega_s_ac, t_int = milp_thermal_variables(set_Temp, set_HVAC, set_N) # Thermal variables

        #---------------------------------------- MILP VARIABLES HEAT PUMP AND THERMAL STORAGE ----------------------------------------- 

        #---------------------------------------- CER -----------------------------------------

        if cacer.cacer_type == 'CER':
            q_hp, ee_binary, ee_tot, q_heater, q_crankcase = milp_hp_autonomous_variables(set_HVAC, set_N) # Heat pump variables for CER type CACER

        #---------------------------------------- AUC -----------------------------------------

        elif cacer.cacer_type == 'AUC':
            q_hp, ee_binary, ee_tot = milp_hp_centralized_variables(set_N) # Heat pump variables for AUC type CACER

            if cacer.hp_users_type[0].users[0].hp_heating.thermal_storage == True and mode_pdc[start_time_optimization] == 'heating':
                m_water_tank, h_water_tank_0 = milp_hp_centralized_storage_constants(cacer.hp_users_type[0].users[0].hp_aux, t_water_tank_0) # Thermal storage constants
                k_compressor_on, k_compressor_off, k_compressor_status, t_water_tank, delta_h = milp_hp_centralized_storage_variables(set_N, set_Temp, h_water_tank_0) # Thermal storage variables

        #---------------------------------------- MILP CONSTRAINTS ENERGY AND THERMAL -----------------------------------------
        
        opt_model, constraints = milp_energy_constraints(opt_model, e_in_vars, e_out_vars, e_cast_pv, ee_tot, k_vars, l_vars, set_P, set_N, 
                                                       set_HVAC, prosumer_p_contr, consumer_p_contr, e_in_virtual_vars, e_out_virtual_vars, 
                                                       a_vars, b_vars, M, start_time_optimization, dt, cacer.cacer_type)# Energy constraints

        opt_model, constraints = milp_thermal_constraints(opt_model, hp_users_list, set_HVAC, t_int, omega_s_ac, omega_m_ac, set_T, 
                                                        t_start_dayahead, set_Temp, t_ext, start_time_optimization, 
                                                        phi_ia, phi_st, phi_m, phi_hc_nd_ac, T_MAX, T_MIN, constraints) # Thermal constraints
        
        #---------------------------------------- MILP CONSTRAINTS HEAT PUMP AND THERMAL STORAGE -----------------------------------------

        #---------------------------------------- CER -----------------------------------------
        
        if cacer.cacer_type == 'CER':
            opt_model, constraints = milp_hp_autonomous_constraints(opt_model, phi_hc_nd_ac, q_crankcase, q_heater, q_hp, q_min, q_max, ee_tot, ee_binary, 
                                                                  mode_pdc, set_N, set_HVAC, dt, eta, pe_defrost, hp_users_list, start_time_optimization,
                                                                    q_crankcase_activation, constraints) # Autonomous heat pump constraints (CER type CACER)
            
            # MILP OBJECTIVE FUNCTION CER TYPE 
            objective = plp.lpSum(plp.lpSum(e_in_vars[p,n]*costo_prel[p][n-1] - e_out_vars[p,n]*rid[p][n-1] for p in set_P) + plp.lpSum((ee_tot[n,pdc])*costo_prel[pdc][n-1] for pdc in set_HVAC) 
                                    -(plp.lpSum(e_out_vars[p,n] for p in set_P)- e_out_virtual_vars[n])*INC  
                        for n in set_N)/1000
        
        #---------------------------------------- AUC -----------------------------------------
        
        elif cacer.cacer_type == 'AUC':
            
            # Thermal storage constraints (AUC type CACER)
            if cacer.hp_users_type[0].users[0].hp_heating.thermal_storage == True and mode_pdc[start_time_optimization] == 'heating': 
                set_S = range(2, n_intervals+1) 
                opt_model, constraints = milp_hp_centralized_storage_constraints(opt_model, ee_tot, phi_hc_nd_ac, 
                                            delta_h, t_water_tank, k_compressor_status, k_compressor_off, k_compressor_on, 
                                            cacer.hp_users_type[0].users[0].hp_aux, start_time_optimization, set_HVAC, set_T, set_N, set_S, q_max, eta, M, 
                                            t_water_tank_0, k_compressor_status_0, m_water_tank, dt) # Centralized thermal storage constraints

            
            else:             
                opt_model, constraints = milp_hp_centralized_constraints(opt_model, phi_hc_nd_ac, q_hp, q_min, q_max, ee_tot, 
                                                                    ee_binary, mode_pdc, set_N, set_HVAC, dt, eta, 
                                                                    start_time_optimization, hp_users_list[0].hp_aux, constraints) # Centralized heat pump constraints
             
            # MILP OBJECTIVE FUNCTION AUC TYPE
            objective = plp.lpSum(plp.lpSum(e_in_vars[p,n]*costo_prel[p][n-1] - e_out_vars[p,n]*rid[p][n-1] for p in set_P) + (ee_tot[n])*costo_prel[0][n-1] 
                                    -(plp.lpSum(e_out_vars[p,n] for p in set_P)- e_out_virtual_vars[n])*INC  
                        for n in set_N)/1000
        
        #---------------------------------------- MILP SOLVER -----------------------------------------

        opt_model.sense = plp.LpMinimize # Per la minimizzazione LpMinimize, per la massimizzazione LpMaximize 
        
        opt_model.setObjective(objective)
        
        # Solver CBC per risoluzione di un problema di ottimizzazione misto-interi 
        opt_model.solve(PULP_CBC_CMD( presolve = True, cuts= True,msg=True, gapRel=0.005)) #timeLimit = 60*5, gapRel=0.05  # 0.005 Euro ---> 5*60 = 5 minuti
        
        #---------------------------------------- MILP RESULTS -----------------------------------------

        if cacer.hp_users_type[0].users[0].hp_heating.thermal_storage == True and mode_pdc[start_time_optimization] == 'heating':
            k_compressor_status_0, t_water_tank_0=milp_hp_storage_results(k_compressor_status, t_water_tank, set_N) # Get thermal storage results for next day

        th_load, hp_energy, t_start_dayahead=milp_results(set_HVAC, set_N, phi_hc_nd_ac, ee_tot, omega_m_ac, omega_s_ac, t_int, 
                                                          t_start_dayahead, n_intervals, cacer.cacer_type) # Get MILP results for each day
        
        df_total_results=df_results_generator(th_load, hp_energy, dt, df_climate_data, n_intervals, user_name_list, df_total_results, start_time_optimization) # Generate results DataFrame
    
    print("\nOptimization completed!\n")

    return df_total_results

#######################################################################################################################################################################

def time_forecast_data_generator(mese, anno, pv_data_file, simulation_interval):
    """
    Function to generate the input data for the time forecast of the CER's energy consumption.

    Parameters
    ----------
    mese : str
        Month of the year (from 'Gen' to 'Dic')
    anno : int
        Year of the simulation
    pv_data_file : str
        File path of the solar PV data
    simulation_interval : str
        Simulation interval of the time forecast (either '15Min' or '1H')

    Returns
    -------
    dt : float
        Time step of the simulation
    n_intervals : int
        Number of intervals in a day
    total_intervals : int
        Total number of intervals in the month
    e_cast_pv : numpy.array
        Array of the solar PV energy output in the month
    month_days : int
        Number of days in the month
    """
    lista_mesi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']
    
    mese_numero = lista_mesi.index(mese) + 1  # Convert month name to number (1-12)
    _, month_days=calendar.monthrange(anno, mese_numero)
    
    df_e_cast_pv=  pd.read_csv(pv_data_file, sep=',', decimal='.', parse_dates=['datetime'])
    
    if simulation_interval == '15Min':
        dt = 0.25
        n_intervals = 96
        e_cast_pv=df_e_cast_pv.iloc[:, 1].values

    else:
        dt = 1
        n_intervals = 24
        df_hour_e_cast_pv=df_e_cast_pv.loc[df_e_cast_pv['datetime'].dt.strftime('%M:%S') == '00:00']
        e_cast_pv=df_hour_e_cast_pv.iloc[:, 1].values
    
    total_intervals = n_intervals*month_days

    return dt, n_intervals, total_intervals, e_cast_pv, month_days

#######################################################################################################################################################################

def mode_pdc_generator(months, total_intervals):
    """
    Function to generate an array of heating/cooling mode based on the months of the year.

    Parameters
    ----------
    months : list
        List of months of the year (from 1 to 12)
    total_intervals : int
        Total number of intervals in the year

    Returns
    -------
    list
        List of 'heating' or 'cooling' mode based on the months of the year
    """
    mode_pdc=[]

    # Generate heating/cooling mode based on months
    for i in range(total_intervals):
        if months[i]>=5 and months[i]<9:
            mode_pdc.append('cooling')
        else:
            mode_pdc.append('heating')

    return mode_pdc
