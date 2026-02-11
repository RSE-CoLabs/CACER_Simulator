import numpy as np
import pandas as pd
from simple_colors import blue
import yaml

from HVAC_simulator.functions.io import read_weather_parameters, df_results_generator
from HVAC_simulator.functions.thermal_load import thermal_load_calculator
from HVAC_simulator.functions.hp_energy_consumption import hp_energy_consumption

from src.Functions_General import clear_folder_content
from src.Functions_Energy_Model import create_coordinates_dataset, suppress_printing

"""Questa funzione restituisce una simulazione del consumo energetico di una AUC con impianto di climatizzazione
a Pompa di calore (PdC) non ottimizzato a setpoint di temperatura fisso.
Il modello di edificio considerato è di tipo 5R3C"""

def non_optimized(cacer):

    """
    This function returns a simulation of the energy consumption of a non-optimized Heat Pump
    system for an office building with a setpoint temperature.

    Parameters
    ----------
    cacer : CacerConfig
        Configuration of the CACER
    climate_data_file : str
        File path of the climate data file
    location : str
        Location of the building

    Returns
    -------
    df_total_results : pandas.DataFrame
        DataFrame containing the energy consumption and thermal load of the Heat Pump system for each user type
    """ 

    config = yaml.safe_load(open("config.yml", 'r'))

    num_years = config['project_lifetime_yrs']

    results_HVAC_folder = config['folder_results_HVAC']
    suppress_printing(clear_folder_content, results_HVAC_folder)

    #----------------------------------------------------------------------------------------------------------

    location = config['provincia_it'] # getting the location from the configuration file

    coordinates = suppress_printing(create_coordinates_dataset, [location])

    #----------------------------------------------------------------------------------------------------------

    delta_t = cacer.simulation_interval # Time step of the simulation (15Min or 1H)

    if delta_t == '15Min':
        time_factor = 0.25
    else:
        time_factor = 1

    #----------------------------------------------------------------------------------------------------------

    climate_data_filename = config['filename_weather_data_selected_years']
    df_climate_data, months, hours, t_ext, rh_ext = read_weather_parameters(climate_data_filename) # Read climate data parameters

    #----------------------------------------------------------------------------------------------------------

    n_intervals = df_climate_data.shape[0] # Number of time intervals

    df_total_results = pd.DataFrame() # DataFrame to store the total results of the simulation

    th_load = np.zeros(n_intervals) # Initialize thermal load array
    hp_energy_heating = np.zeros(n_intervals) 
    hp_energy_cooling = np.zeros(n_intervals) 

    #----------------------------------------------------------------------------------------------------------

    # monthly_range_heat = range(1, 13) # intervallo di mesi per cui si considera attivo il riscaldamento (es. da gennaio a dicembre)
    monthly_range_heat = [1, 2, 3, 11, 12] # intervallo di mesi per cui si considera attivo il riscaldamento (es. da gennaio a dicembre)
    monthly_range_cool = range(5, 10) # intervallo di mesi per cui si considera attivo il raffrescamento (es. da maggio a settembre)

    #----------------------------------------------------------------------------------------------------------

    # scheduling_heating = range(0, 24) # intervallo di ore per cui si considera attivo il riscaldamento (es. da 0 a 24)
    # scheduling_cooling = range(0, 24) # intervallo di ore per cui si considera attivo il raffrescamento (es. da 0 a 24)

    scheduling_heating = [0, 7, 8, 18, 19, 20, 21, 22, 23]
    scheduling_cooling = [0, 7, 8, 18, 19, 20, 21, 22, 23]

    #----------------------------------------------------------------------------------------------------------

    print (blue("Non-optimized HVAC simulation:", ["bold", "underlined"]), '\n')

    for u in range(len(cacer.hp_users_type)):

        print(f"Simulating user type:", blue(f'{cacer.hp_users_type[u].user_name}\n'))
        print(f"- HVAC type:", blue(f"{cacer.hp_users_type[u].hvac_type}"))
        print(f"- Comfort temperature heating setpoint: {cacer.hp_users_type[u].th_comfort_heating} °C")
        print(f"- Comfort temperature cooling setpoint: {cacer.hp_users_type[u].th_comfort_cooling} °C\n")

        #--------------------------------------------- THERMAL LOAD ESTIMATION ---------------------------------------------

        # Funzione per il calcolo del fabbisogno energetico dell'edificio
        print("- Thermal load:\n")
        phi_hc_nd_ac, t_int = thermal_load_calculator(cacer.hp_users_type[u], 
                                                      df_climate_data, 
                                                      n_intervals, 
                                                      months, 
                                                      hours, 
                                                      coordinates, 
                                                      t_ext, 
                                                      monthly_range_heat, 
                                                      monthly_range_cool, 
                                                      scheduling_heating, 
                                                      scheduling_cooling)

        for uu in range(cacer.hp_users_type[u].user_numbers):
            t_int_uu = t_int[:, uu]
            phi_hc_nd_ac_uu = phi_hc_nd_ac[:, uu]

            if cacer.hp_users_type[u].user_numbers > 1: print(f"  -> User number:", blue(f"{uu+1}\n"))
            print(f"    -> Average internal temperature: {np.mean(t_int_uu):.2f} °C\n")
            print(f"    -> Total heating load: {np.sum(phi_hc_nd_ac_uu[phi_hc_nd_ac_uu>0])*time_factor/1000000/num_years:.2f} MWh")
            print(f"    -> Total cooling load: {np.sum(np.abs(phi_hc_nd_ac_uu[phi_hc_nd_ac_uu<0]))*time_factor/1000000/num_years:.2f} MWh\n")
            print(f"    -> Peak heating load: {np.max(phi_hc_nd_ac_uu)/1000:.2f} kW") 
            print(f"    -> Peak cooling load: {np.min(phi_hc_nd_ac_uu)/1000:.2f} kW\n")

        
        #--------------------------------------------- HEATING ENERGY CONSUMPTION ---------------------------------------------

        thermal_load_heat = phi_hc_nd_ac.copy()
        thermal_load_heat[thermal_load_heat < 0] = 0
        
        print("- Heat pump energy consumption for heating:\n")
        hp_energy_consumption_array_heat = hp_energy_consumption(cacer.hp_users_type[u], 
                                                                 thermal_load_heat, 
                                                                 n_intervals, 
                                                                 months, 
                                                                 hours, 
                                                                 t_ext, 
                                                                 t_int, 
                                                                 rh_ext, 
                                                                 delta_t, 
                                                                 monthly_range_heat, 
                                                                 monthly_range_cool, 
                                                                 scheduling_heating)
        
        #--------------------------------------------- COOLING ENERGY CONSUMPTION ---------------------------------------------

        thermal_load_cool = phi_hc_nd_ac.copy()
        thermal_load_cool[thermal_load_cool > 0] = 0

        print("- Heat pump energy consumption for cooling:\n")
        hp_energy_consumption_array_cool = hp_energy_consumption(cacer.hp_users_type[u], 
                                                                thermal_load_cool, 
                                                                n_intervals, 
                                                                months, 
                                                                hours, 
                                                                t_ext, 
                                                                t_int, 
                                                                rh_ext,
                                                                delta_t, 
                                                                monthly_range_heat, 
                                                                monthly_range_cool, 
                                                                scheduling_cooling)

        #--------------------------------------------- ENERGY CONSUMPTION RESULTS ---------------------------------------------

        for uu in range(cacer.hp_users_type[u].user_numbers):
            hp_energy_consumption_array_heat_uu = hp_energy_consumption_array_heat[:, uu]
            hp_energy_consumption_array_cool_uu = hp_energy_consumption_array_cool[:, uu]
            if cacer.hp_users_type[u].user_numbers > 1: print(f"  -> User number:", blue(f"{uu+1}\n"))
            print(f"    -> Total energy consumption by heat pump (heating): {np.sum(hp_energy_consumption_array_heat_uu)*time_factor/1000000/num_years:.2f} MWh")
            print(f"    -> Total energy consumption by heat pump (cooling): {np.sum(hp_energy_consumption_array_cool_uu)*time_factor/1000000/num_years:.2f} MWh\n")

        #--------------------------------------------- EXPORT RESULTS ---------------------------------------------

        for uu in range(cacer.hp_users_type[u].user_numbers):
            
            th_load = phi_hc_nd_ac[:, uu] # thermal load (kWh)
            hp_energy_heating = hp_energy_consumption_array_heat[:, uu] # energy consumption of the heat pump system for heating (kWh)
            hp_energy_cooling = hp_energy_consumption_array_cool[:, uu] # energy consumption

            # Generazione del DataFrame dei risultati
            df_total_results = df_results_generator(th_load, # thermal load (kWh)
                                                    
                                                    hp_energy_heating, # energy consumption of the heat pump system for heating (kWh)
                                                    hp_energy_cooling, # energy consumption of the heat pump system for cooling (kWh)
                                                    
                                                    time_factor, # delta_t in hours (0.25 for 15Min, 1 for 1H)
                                                    
                                                    df_climate_data,  # climate data (df)
                                                    
                                                    n_intervals, # number of intervals in a day
                                                    
                                                    df_total_results # total results (df)
                                                    )  
            
            # Save results to CSV
            user_name = cacer.hp_users_type[u].users[uu].name
            df_total_results.to_csv(results_HVAC_folder + '\\' + user_name + ".csv", index = False)

        print(f"**** Simulation for user type {cacer.hp_users_type[u].user_name} completed! ****\n")

    print("**** HVAC simulation completed! ****")

    return df_total_results

############################################################################################################################################################################

def adding_HVAC_energy_consumption():
    config = yaml.safe_load(open("config.yml", 'r'))

    df_carichi = pd.read_csv(config['filename_carichi'])

    registry_users_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    registry_users_types.keys()
    user_type_list = [key for key in registry_users_types.keys() if registry_users_types[key]['heat_load'] == True]

    for u in user_type_list:
        df_user = pd.read_csv(config['folder_results_HVAC'] + "\\" + u + ".csv")
        df_carichi[u] += df_user['energy consumption [kWh]']

    df_carichi.to_csv(config['filename_carichi_with_hvac'], index = False)

    print("\n**** HVAC energy consumption added to carichi.csv file! ****")




