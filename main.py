from datetime import date
import yaml

from src.Functions_Load_Emulator_v2 import *


def main():
    #---------------------------------------------------------------------------------------------
    # Number of users to emulate
    #---------------------------------------------------------------------------------------------

    num_user = 300
    name = "300_3" # name to add to the results files, e.g. "300_users", "500_users", etc.
    #---------------------------------------------------------------------------------------------
    # Simulation period
    #---------------------------------------------------------------------------------------------

    start_day = date(2025, 1, 1) # start day for simulation
    end_day = date(2025, 12, 31) # end day for simulation

    calendar_df, calendar_daily = create_calendar_dfs(start_day, end_day)

    data_input = import_data_load_emulator_v2()

    data_input = remove_specific_appliance(data_input, specific_appliance='induction_hob')


    dict_users, stacked_df = load_emulator_v2(num_user, 
                                  data_input, 
                                  calendar_df, 
                                  calendar_daily,
                                  
                                  name = name,
                                  simulate_boiler=False, # if True, the boiler will be simulated 
                                  all_boiler_profiles=False,
                                  
                                  show_results=False, # a progress bar and some plots with results will be shown
                                  save_all_results=False, # save the results in a pickle file, disactivate if there are too many users!!
                                  
                                  specific_appliance=None, # if not None, only the specified appliance will be simulated (e.g. 'washing_machine', 'induction_hob', 'boiler', etc.)
                                  
                                  parallelize=True, # parallelize the creation of duty cycle profiles, time-consuming part of the process
                                  max_workers=10, # number of workers to use for parallelization
                                  )


    export_mean_profile_load_emulator_v2(stacked_df, name=name, specific_appliance=None)


if __name__ == "__main__":
    main()



