import plotly.express as px
import plotly.graph_objs as go
import numpy as np
import pandas as pd
import numpy as np
import math
import random
from datetime import date, datetime, timedelta
import yaml
import pickle
import holidays
import calendar
import warnings
from tqdm import tqdm
from simple_colors import *
import contextlib
import io
from files.energy.input.DSM_optimizer.main import ott_year
from simple_colors import *

###################################################################################################################

# function to suppress the printing sections of a specified function
def suppress_printing(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)

###################################################################################################################

def generate_calendar_modified(start_day, end_day):
    """Generate a calendar with the specified start and end dates.

    Inputs:
        start_day                  datetime, starting date to generate the calendar
        end_day                    datetime, ending date to generate the calendar
    
    Outputs:
        cal                         dataframe con datetime, working_day (0=lunedi, 6=domenica), holiday (True False) and Tariff (1,2,3)
    """ 

    delta_t = '15Min' # we need to modify this in the future versions!!!

    start_date = start_day.strftime("%Y-%m-%d")

    end_day = end_day + timedelta(days=1)
    end_date = end_day.strftime("%Y-%m-%d")

    # creation of a calendar that starts from the indicated date with the indicated frequency
    cal = pd.DataFrame({"datetime": pd.date_range(start = start_date, end = end_date, freq = delta_t)})
    cal = cal[:-1] # delete the last row

    cal['day_week'] = cal.datetime.dt.dayofweek # create day of the week column (1: monday; 2: thursday; etc.)
    
    it_holidays = holidays.IT() # create a list with all italian holidays
    cal['holiday'] = cal['datetime'].apply(lambda x: x.date() in it_holidays) # create a column with the holidays (True False)

    cal["day_flag"] = "Working_day" # preassigning value of working_day
    cal.loc[cal["day_week"] == 5, "day_flag"] = "Saturday" # overwrite the saturdays
    cal.loc[cal["day_week"] == 6, "day_flag"] = "Sunday" # overwrite the sundays
    cal.loc[cal["holiday"], "day_flag"] = "Sunday" # overwrite the holidays, modelled as sundays

    cal.drop(columns=["holiday"], inplace=True) # drop the holiday column (not necessary)

    print("**** Calendar successfully created! *****")

    return cal

###################################################################################################################

def set_values_to_zero(data, index, delta):
    """Set the values in the specified range to zero.
    
    Inputs:
        data                        list, list of values to modify
        index                       int, index of the value to modify
        delta                       int, range of values to modify
    
    Outputs:
        data                        list, modified list of values
    """

    # Determine the start and end indices for zeroing
    start = max(0, index - delta)
    end = min(len(data), index + delta + 1)  # +1 because range is exclusive
    
    # Set the values in the specified range to zero
    for i in range(start, end):
        data[i] = 0
    
    return data

###################################################################################################################

# we create the list with the datetime for all timestep
def datetime_range(start, end, delta):
    """This function create a list with all timesteps in the range between start and end datetime.
    
    Inputs:
        start (datetime): starting datetime
        end (datetime): ending datetime
        delta (timedelta): time step

    Outputs:
        list: list with all timesteps in the range between start and end datetime
    """

    current = start 
    if not isinstance(delta, timedelta):
        delta = timedelta(**delta)
    while current < end:
        yield current
        current += delta

###################################################################################################################

def create_appliance_start_time(num_days, calendario, flag_daily_activation = True, flag_multi_use = True): 
    """This function create a dataframe with the start time for the appliance under exam.

    Inputs:
        num_days (int): number of days to create
        calendario (dataframe): calendar
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.

    Outputs:
        start_time_df_1: dataframe with the start time for the first use of the appliance
        start_time_df_2: dataframe with the start time for the second use of the appliance (if activated)
        start_time_df_3: dataframe with the start time for the third use of the appliance (if activated)
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_appliance_load = config['filename_appliances_load']
    appliance_load_df = pd.read_excel(filename_appliance_load, header = 0, index_col = 0, sheet_name = "load_profile") # we import the load profile for all appliances
    num_timestep_load_profile = (appliance_load_df != 0).sum() # we calculate the number of timesteps for each appliance

    ##########################################################################################################################################

    filename_usage_probability = config['filename_usage_probability']
    usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "daily_usage_probability") # we import usage probability for dish washer, washing machine, oven, tv e microwaves

    num_daily_usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "num_of_uses") # we import daily usage probability with different number of uses

    week_usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "week_usage_probability") # we import weekly usage probability
    wm_week_usage_probability_df = week_usage_probability_df.loc['washing_machines'].copy() # we extract the weekly usage probability for the washing machine

    boolean_list = [True, False]

    ##########################################################################################################################################

    appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"] # list of all appliance

    ##########################################################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    ##########################################################################################################################################

    # we extract a random value for the start time for each appliance for every day for the user under exam and save all values in a specific df

    time_list = np.arange(0, 96 , 1).tolist() # we create a list with all timesteps
    num_of_uses_list = np.arange(1, 4 , 1).tolist() # we create a list with all number of uses
    
    start_time_df_1 = pd.DataFrame(index = np.arange(num_days), columns = appliances_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 1)
    start_time_df_2 = pd.DataFrame(index = np.arange(num_days), columns = appliances_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 2)
    start_time_df_3 = pd.DataFrame(index = np.arange(num_days), columns = appliances_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 3)

    for day in range(num_days):  
        
        for appliance in appliances_list:
            
            activation_probability_flag = True # we initialize the flag probability for the daily usage for the selected day and appliance

            # if the appliance is in list (only washing machine for the moment) and the external flag is setted to true, we modifify with a probability the daily activation of the appliance
            if appliance in ["washing_machine"] and not flag_daily_activation:

                day_type = calendario.iloc[day]['day_flag'] # Working_day; Saturday; Sunday
                activation_wm_probability = wm_week_usage_probability_df[day_type] # we extract the weekly usage probability for the washing machine in the selected day type
                activation_wm_probability_list = [activation_wm_probability, 100 - activation_wm_probability] # we create a list with the weekly usage probability for the washing machine in the selected day type
                activation_probability_flag = random.choices(boolean_list, weights = activation_wm_probability_list, k = 1)[0] # we randomly choose the start time for the selected appliance

            #############################################################################

            # if the appliance is activated in the selected days
            if activation_probability_flag:
                
                num_of_uses_selected = 1 # we initialize the number of uses for the selected appliance

                # if the external flag for the multiple usages during the day is true
                if flag_multi_use:
                    num_of_uses = num_daily_usage_probability_df[appliance].tolist() # we import the number of uses probability for the selected appliance
                    num_of_uses_selected = random.choices(num_of_uses_list, weights = num_of_uses, k = 1)[0] # we randomly choose the number of uses for the selected appliance

                #############################################################################

                # number of uses equal to 1

                probability_1 = usage_probability_df[appliance].tolist() # we import the usage probability for the selected appliance
                
                timestep_selected_1 = random.choices(time_list, weights = probability_1, k = 1)[0] # we randomly choose the start time for the selected appliance
                start_time_df_1.loc[day, appliance] = timestep_selected_1 # we save the start time for the selected day

                #############################################################################

                # number of uses equal to 2

                if num_of_uses_selected > 1:
                    
                    # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                    index = timestep_selected_1 
                    delta = num_timestep_load_profile[appliance]
                    probability_2 = set_values_to_zero(probability_1, index, delta) 

                    timestep_selected_2 = random.choices(time_list, weights = probability_2, k = 1)[0] # we randomly choose the start time for the selected appliance
                    start_time_df_2.loc[day, appliance] = timestep_selected_2 # we save the start time for the selected day

                    assert (timestep_selected_1 != timestep_selected_2), "The timesteps are equal!"
                    assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]), "The timesteps are equal!"

                #############################################################################

                # number of uses equal to 3

                if num_of_uses_selected > 2:

                    # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                    index = timestep_selected_2 
                    delta = num_timestep_load_profile[appliance]
                    probability_3 = set_values_to_zero(probability_2, index, delta)

                    timestep_selected_3 = random.choices(time_list, weights = probability_3, k = 1)[0] # we randomly choose the start time for the selected appliance
                    start_time_df_3.loc[day, appliance] = timestep_selected_3 # we save the start time for the selected day
                
                    assert (timestep_selected_1 != timestep_selected_2 or timestep_selected_1 != timestep_selected_3 or timestep_selected_2 != timestep_selected_3), "The timesteps are equal!"
                    assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]  or abs(timestep_selected_1 - timestep_selected_3) > num_timestep_load_profile[appliance]  or abs(timestep_selected_2 - timestep_selected_3) > num_timestep_load_profile[appliance] ), "The timesteps are equal!"
    
    return (start_time_df_1, start_time_df_2, start_time_df_3)

###################################################################################################################

def create_all_user_appliance_start_time(emulated_users_list, num_days, calendario, flag_daily_activation = True, flag_multi_use = True):
    """Create all user appliance start time for all days fixed.
    
    Inputs:
        emulated_users_list (list): list of users to simulate
        num_days (int): number of days to simulate
        calendario (dataframe): calendar
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.
    
    Outputs:
        all_user_appliance_start_time_dict_1: dictionary with the start time for the first use of the appliance
        all_user_appliance_start_time_dict_2: dictionary with the start time for the second use of the appliance (if activated)
        all_user_appliance_start_time_dict_3: dictionary with the start time for the third use of the appliance (if activated)
    """

    # initialize the dictionaries
    output = {}
    all_user_appliance_start_time_dict_1 = {} # number of uses equal to 1
    all_user_appliance_start_time_dict_2 = {} # number of uses equal to 2
    all_user_appliance_start_time_dict_3 = {} # number of uses equal to 3

    all_user_appliance_start_time_dict = {}

    # we create the start time for the appliance for each user
    for id_user in tqdm(emulated_users_list):
        
        output = create_appliance_start_time(num_days, calendario, flag_daily_activation, flag_multi_use)

        all_user_appliance_start_time_dict_1[id_user] = output[0] # number of uses equal to 1
        all_user_appliance_start_time_dict_2[id_user] = output[1] # number of uses equal to 2
        all_user_appliance_start_time_dict_3[id_user] = output[2] # number of uses equal to 3

    all_user_appliance_start_time_dict[0] = all_user_appliance_start_time_dict_1 # number of uses equal to 1
    all_user_appliance_start_time_dict[1] = all_user_appliance_start_time_dict_2 # number of uses equal to 2
    all_user_appliance_start_time_dict[2] = all_user_appliance_start_time_dict_3 # number of uses equal to 3

    #############################################################################
    
    # export dictionary in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["foldername_result_emulator"]
    # now = datetime.now().strftime("(%Y-%m-%d_%H-%M)")
    with open(folder + 'all_user_appliance_start_time_dict.pkl', 'wb') as fp:
        pickle.dump(all_user_appliance_start_time_dict, fp)

    #############################################################################

    return (all_user_appliance_start_time_dict_1, all_user_appliance_start_time_dict_2, all_user_appliance_start_time_dict_3)

###################################################################################################################

def add_appliance(appliance_profile, start_time, day, user_consumption_df, df_2):
    """Add the appliance to the user consumption dataframe.
    
    Inputs:
        appliance_profile (dataframe): appliance load profile
        start_time (int): start time of the appliance
        day (int): day of the simulation
        user_consumption_df (dataframe): user consumption dataframe
        df_2 (dataframe): dataframe to add the appliance
    
    Outputs:
        user_consumption_df: updated user consumption dataframe
        df_2: updated dataframe to add the appliance
    """

    df_1 = appliance_profile.head(96 - start_time).to_frame() # we extract the load profile for the selected appliance (from the 00:00 to the start time)
    new_rows = pd.DataFrame(0, index=range(start_time), columns=df_1.columns) # we create a df with zeros for the timesteps from the start time to the end of the day
    df_1 = pd.concat([new_rows, df_1], ignore_index=True) # we concatenate the two df (before zeros and after load profile)

    #############################################################################

    user_consumption_df[day] += df_1.iloc[:, 0] # we add df_1 to the user consumption dataframe

    #############################################################################

    # if day>0 we add the previous day load profile (df_2) to the current day
    if day>0:
        user_consumption_df[day] += df_2.iloc[:, 0] # we add df_2 to the user consumption dataframe

    #############################################################################

    df_2 = appliance_profile.tail(start_time).to_frame() # we extract the load profile for the selected appliance (from the start time to the end of the day)
    new_rows = pd.DataFrame(0, index=range(96 - start_time), columns=df_2.columns) # we create a df with zeros for the timesteps from the 00:00 to the start time
    df_2 = pd.concat([df_2, new_rows], ignore_index=True) # we concatenate the two df (load profile and after zeros)

    return user_consumption_df, df_2

###################################################################################################################

def create_single_user_load_profile(start_time_df_1, start_time_df_2, start_time_df_3, num_days, appliances_list):
    """Create a single user load profile over all days fixed using the start time simulated.
    
    Inputs:
        start_time_df_1 (dataframe): start time for the first use of the appliance
        start_time_df_2 (dataframe): start time for the second use of the appliance (if activated)
        start_time_df_3 (dataframe): start time for the third use of the appliance (if activated)
        num_days (int): number of days to simulate
        appliances_list (list): list of appliances to simulate
    
    Outputs:
        user_consumption_df: user load profile
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_appliances_load = config['filename_appliances_load']
    appliances_load_df = pd.read_excel(filename_appliances_load, header=0, index_col=0) # we import the load profile for all appliances

    #############################################################################

    # Create an empty DataFrame to hold aggregated load profiles for each day
    # rows: 96 timesteps, columns: num_days days
    num_years = config['project_lifetime_yrs']
    user_consumption_df = pd.DataFrame(0, index=range(96), columns=range(num_days))

    ############################################################################

    # Iterate over each appliance and day
    for appliance in appliances_list:

        appliance_profile = appliances_load_df[appliance] # we extract the load profile for the selected appliance

        df_2 = df_3 = df_4 = pd.DataFrame(0, index=range(96), columns=range(1)) # we create an empty df to save the load profile for the selected appliance

        for day in range(num_days):

            # number of uses equal to 1

            start_time_1 = start_time_df_1[appliance][day] # Read the start time for the current appliance and day

            # if the start time is not nan we add the appliance to the user consumption dataframe
            if not math.isnan(start_time_1):
                user_consumption_df, df_2 = add_appliance(appliance_profile, start_time_1, day, user_consumption_df, df_2) 

            #############################################################################

            if appliance not in ["electricity_mains", "fridge"]:

                # number of uses equal to 2

                start_time_2 = start_time_df_2[appliance][day] # Read the start time for the current appliance and day

                # if the start time is not nan we add the appliance to the user consumption dataframe
                if not math.isnan(start_time_2):
                    user_consumption_df, df_3 = add_appliance(appliance_profile, start_time_2, day, user_consumption_df, df_3)
            
                #############################################################################

                # number of uses equal to 3

                start_time_3 = start_time_df_3[appliance][day] # Read the start time for the current appliance and day
                
                # if the start time is not nan we add the appliance to the user consumption dataframe
                if not math.isnan(start_time_3):
                    user_consumption_df, df_4 = add_appliance(appliance_profile, start_time_2, day, user_consumption_df, df_4)

                #############################################################################

    return user_consumption_df

###################################################################################################################

def create_all_user_load_profile(start_time_dict_1, start_time_dict_2, start_time_dict_3, emulated_users_list, num_days, flag_DSM, flag_all_appliance = True):
    """Create all user load profile over all days fixed using the start time simulated.

    Inputs:
        start_time_dict_1 (dict): Start time for the first use of the appliance
        start_time_dict_2 (dict): Start time for the second use of the appliance (if activated)
        start_time_dict_3 (dict): Start time for the third use of the appliance (if activated)
        num_users (float): number of users to simulate
        num_days (float): number of days to simulate
        flag_DSM (bool): if true we simulate a demand side management scenario
        flag_all_appliance (bool, optional): if false we don't use all appliances in the user load profile simulation. Defaults to True.

    Outputs:
        all_user_load_profile_dict: dictionary with all load profile for all days simulated for all users fixed
    """

    all_user_load_profile_dict = {} # we create a dict with all load profile for each day for every users (timesteps on rows and user_id on columns)

    # if true we use all appliances for the user load profile simulation
    if flag_all_appliance:
        # List of all appliances. The order of the appliances needs to be equal to the order of the columns in appliance_load_df to work correctly.
        appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"]
    
    # else we deactivate some appliance in the user load profile simulation
    else:
        # List of all appliances. The order of the appliances needs to be equal to the order of the columns in appliance_load_df to work correctly.
        appliances_list = ["electricity_mains", "fridge", "microwaves", "tv", "oven"]

    for id_user in tqdm(emulated_users_list):
        
        start_time_df_1 = start_time_dict_1[id_user] # we extract the start time for the first use of the appliance for the user under exam
        start_time_df_2 = start_time_dict_2[id_user] # we extract the start time for the second use of the appliance for the user under exam
        start_time_df_3 = start_time_dict_3[id_user] # we extract the start time for the third use of the appliance for the user under exam

        # we create the load profile for the user under exam
        all_user_load_profile_dict[id_user] = create_single_user_load_profile(start_time_df_1, start_time_df_2, start_time_df_3, num_days, appliances_list)

    #############################################################################

    # export dictionary in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["foldername_result_emulator"]

    if flag_DSM:
        title_flag = 'DSM_'
    else:
        title_flag = ''

    # export dictionary in external file
    # now = datetime.now().strftime("(%Y-%m-%d_%H-%M)")
    with open(folder + title_flag + 'all_user_load_profile_dict.pkl', 'wb') as fp:
        pickle.dump(all_user_load_profile_dict, fp)
        print("\nDictionary users load profile exported!")

    return all_user_load_profile_dict

###################################################################################################################

def create_appliance_load_profile(start_time_df, num_days):
    """Create a dictionary with all appliance load profile for each day for the user under exam.
    
    Inputs:
        start_time_df (dataframe): start time for the appliance
        num_days (int): number of days to simulate
    
    Outputs:
        appliance_consumption_dict: dictionary with all appliance load profile for each day for the user under exam
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_appliances_load = config['filename_appliances_load'] 
    appliances_load_df = pd.read_excel(filename_appliances_load, header = 0, index_col = 0) # we import the load profile for all appliances

    ##########################################################################################################################################

    appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"] # list of all appliance

    ##########################################################################################################################################

    appliance_consumption_dict = {} # we create a dict with all appliance load profile for each day for the user under exam

    ##########################################################################################################################################

    for appliance in appliances_list:

        appliance_consumption_df = pd.DataFrame(0.0, index = np.arange(96), columns = np.arange(num_days)) # we create a df with all timesteps on rows and days on columns

        for day in range(num_days):
            
            time = start_time_df[appliance][day] # we extract the start time for the selected appliance and day

            #############################################################################

            df_1 = appliances_load_df[appliance].head(96 - time).to_frame() # we extract the load profile for the selected appliance (from the 00:00 to the time)
            new_rows = pd.DataFrame(0, index=range(time), columns=df_1.columns) # we create a df with zeros for the timesteps from the time to the end of the day
            df_1 = pd.concat([new_rows, df_1], ignore_index=True) # we concatenate the two df (before zeros and after load profile)
            
            #############################################################################

            appliance_consumption_df[day] = appliance_consumption_df[day].to_frame() + df_1.values # we add df_1 to the appliance consumption dataframe

            #############################################################################

            if day>0:
                appliance_consumption_df[day] = appliance_consumption_df[day].to_frame() + df_2.values # we add df_2 to the appliance consumption dataframe

            #############################################################################

            df_2 = appliances_load_df[appliance].tail(time).to_frame() # we extract the load profile for the selected appliance (from the time to the end of the day)
            new_rows = pd.DataFrame(0, index=range(96 - time), columns=df_2.columns) # we create a df with zeros for the timesteps from the 00:00 to the time
            df_2 = pd.concat([df_2, new_rows], ignore_index=True) # we concatenate the two df (load profile and after zeros)
        
        #############################################################################

        appliance_consumption_dict[appliance] = appliance_consumption_df # we save the appliance consumption dataframe in the dictionary
    
    return appliance_consumption_dict

###################################################################################################################

# NOT COMPLETED!!!

def create_all_user_appliance_load_profile(start_time_dict, emulated_users_list, num_days, flag_DSM):
    """Create all user appliance load profile for all days fixed using the start time simulated.
    
    Inputs:
        start_time_dict (dict): start time for the appliance
        emulated_users_list (list): list of users to simulate
        num_days (int): number of days to simulate
        flag_DSM (bool): if true we simulate a demand side management scenario
    
    Outputs:
        all_user_appliance_load_profile_dict: dictionary with all appliance load profile for each day for all the users under exam    
    """

    all_user_appliance_load_profile_dict = {} # we create a dict with all appliance load profile for each day for all the users under exam

    for id_user in tqdm(emulated_users_list):
        
        start_time_df = start_time_dict[id_user] # we extract the start time df for the appliance for the user under exam

        all_user_appliance_load_profile_dict[id_user] = create_appliance_load_profile(start_time_df, num_days) # we create all appliance load profile for all the users under exam

    #############################################################################
    
    # export dictionary in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["foldername_result_emulator"]

    if flag_DSM:
        title_flag = 'DSM_'
    else:
        title_flag = ''

    # now = datetime.now().strftime("(%Y-%m-%d_%H-%M)")
    with open(folder + title_flag + 'all_user_appliance_load_profile_dict.pkl', 'wb') as fp:
        pickle.dump(all_user_appliance_load_profile_dict, fp)
        print("Dictionary appliance load profile exported!")
        print('')

    #############################################################################

    print("All users completed!")

    return all_user_appliance_load_profile_dict

###################################################################################################################

def create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM):
    """We change the structure of the dictionary in input. With this function we will obtain an unified dataframe with timestep on rows and different users on columns.

    Inputs:
        all_user_load_profile_dict (dict): dictionary with all load profile for each day for every users (timesteps on rows and user_id on columns)
        calendario (dataframe): calendar
        flag_DSM (bool): if true we simulate a demand side management scenario

    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users on columns.
    """

    all_user_df = pd.DataFrame() # we create a df to save all load profile for each days for every users (timesteps on rows and user_id on columns)

    for user in tqdm(all_user_load_profile_dict.keys()):

        df_load_profile_user = all_user_load_profile_dict[user].copy() # we extract the df_load_profile_user for the user under exam

        df = pd.DataFrame() # we create a df to save the load profile for each days for the user under exam (timesteps on rows and a unique column)

        i = 0 # flag first iteration

        for column in df_load_profile_user.columns:
            
            df_1 = df_load_profile_user[column].copy() # we extract a colum (corresponding to a single day load profile)
            
            # if first iteration
            if i == 0:
                df = df_1.copy(deep = False) # we save the first day load profile in the df
            # if not first iteration
            else:
                df = pd.concat([df, df_1], axis = 0, ignore_index = True).copy() # we concatenate the two df (before and after)

            i = 1 # update flag first iteration

        all_user_df[user] = df.values # add df single user load profile to all_user_df

        all_user_df.set_index(calendario['datetime'].values, inplace = True) # set right index with calendar
        all_user_df.index.names = ['datetime'] # rename index

    ###################################################################################################################

    # export csv
    config = yaml.safe_load(open("config.yml", 'r'))

    if flag_DSM:
        filename = config['filename_DSM_emulated_load_profile']
    else:
        filename = config['filename_emulated_load_profile']

    all_user_df.to_csv(filename)

    print('\nAll user load profiles csv exported!')

    return all_user_df

###################################################################################################################
##################################### DSM APPLIANCES START TIME ###################################################
###################################################################################################################

def create_all_user_appliance_DSM_start_time(DSM_emulated_users_list, num_days, calendario, flag_daily_activation = True, flag_multi_use = True):
    """Create all user DSM (Demand Side Management) appliance start time. 
        
        In particular, we use the dictionary created before for a noDSM case and modify the start time of specified appliances with 
        a different daily usage probability concentrate in the productivity period (we set equal to zeros all usage probabilities 
        out of the productivity period in way to be sure that the activation of the flex appliaces is inside this period). 

    Inputs:
        num_days (float): number of days to simulate
        calendario (dataframe): calendar 
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.

    Outputs:
        all_user_appliance_start_time_dict_1: dictionary with the start time for the first use of the appliance
        all_user_appliance_start_time_dict_2: dictionary with the start time for the second use of the appliance (if activated)
        all_user_appliance_start_time_dict_3: dictionary with the start time for the third use of the appliance (if activated)
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_appliance_load = config['filename_appliances_load']
    appliance_load_df = pd.read_excel(filename_appliance_load, header = 0, index_col = 0, sheet_name = "load_profile") # we import the load profile for all appliances
    num_timestep_load_profile = (appliance_load_df != 0).sum() # we calculate the number of timesteps for each appliance

    filename_usage_probability = config['filename_usage_probability']
    usage_probability_DSM_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "daily_usage_probability_DSM") # import of DSM usage probability for dish washer, washing machine, oven, tv e microwaves
    num_daily_usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "num_of_uses") # import daily usage probability with different number of uses

    week_usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "week_usage_probability") # import weekly usage probability
    wm_week_usage_probability_df = week_usage_probability_df.loc['washing_machines'].copy() # extract the weekly usage probability for the washing machine

    boolean_list = [True, False] # list of boolean values
    time_list = np.arange(0, 96 , 1).tolist() # we create a list with all timesteps
    num_of_uses_list = np.arange(1, 4 , 1).tolist() # we create a list with all number of uses

    ##################################################################################################
    
    # import dictionary from external file with the start time calculated for the reference case (no DSM)
    folder = config['foldername_result_emulator']
    with open(folder + "all_user_appliance_start_time_dict.pkl", 'rb') as fp:
        start_time_dict = pickle.load(fp)
        print("     Dictionary appliance start time imported!\n")

    ##################################################################################################

    # split dictionaries in different part (dict_1 are the start time for the first activation; dict_2 are the start time for the second activation, etc.)
    start_time_dict_1 = start_time_dict[0] # number of uses equal to 1
    start_time_dict_2 = start_time_dict[1] # number of uses equal to 2
    start_time_dict_3 = start_time_dict[2] # number of uses equal to 3

    # copy the dictionaries
    start_time_DSM_dict_1 = start_time_dict_1.copy() # number of uses equal to 1
    start_time_DSM_dict_2 = start_time_dict_2.copy() # number of uses equal to 2
    start_time_DSM_dict_3 = start_time_dict_3.copy() # number of uses equal to 3

    ##################################################################################################
    ##################################################################################################

    appliances_flex_list = ['washing_machine', "dish_washer"] # set the list for the flexible appliances; name appliances --> ["washing_machine", "dish_washer", "microwaves", "tv", "oven"]

    ##################################################################################################
    ##################################################################################################

    for user in tqdm(DSM_emulated_users_list):

        for appliance in appliances_flex_list:

            # we extract a random value for the start time for each appliance for every day for the user under exam and save all values in a specific df
            start_time_DSM_df_1 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 1)
            start_time_DSM_df_2 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 2)
            start_time_DSM_df_3 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 3)

            ##################################################################################################

            for day in range(num_days):  

                activation_probability_flag = True # we initialize the flag probability for the daily usage for the selected day and appliance

                # if the appliance is in list (only washing machine for the moment) and the external flag is setted to true, we modifify with a probability the daily activation of the appliance
                if appliance in ["washing_machine"] and flag_daily_activation:

                    day_type = calendario.iloc[day]['day_flag'] # Working_day; Saturday; Sunday
                    activation_wm_probability = wm_week_usage_probability_df[day_type]
                    activation_wm_probability_list = [activation_wm_probability, 100 - activation_wm_probability]
                    activation_probability_flag = random.choices(boolean_list, weights = activation_wm_probability_list, k = 1)[0] # we randomly choose the start time for the selected appliance

                #############################################################################

                # if the appliance is activated in the selected days
                if activation_probability_flag:
                    
                    num_of_uses_selected = 1
                
                    # number of uses equal to 1

                    probability_1 = usage_probability_DSM_df[appliance].tolist() # we import the usage probability for the selected appliance

                    timestep_selected_1 = random.choices(time_list, weights = probability_1, k = 1)[0] # we randomly choose the start time for the selected appliance
                    start_time_DSM_df_1[appliance][day] = timestep_selected_1 # we save the start time for the selected day

                    ##################################################################################################

                    # if the external flag for the multiple usages during the day is true
                    if flag_multi_use:

                        num_of_uses = num_daily_usage_probability_df[appliance].tolist() # we import the number of uses probability for the selected appliance
                        num_of_uses_selected = random.choices(num_of_uses_list, weights = num_of_uses, k = 1)[0] # we randomly choose the number of uses for the selected appliance

                        # number of uses equal to 2

                        if num_of_uses_selected > 1:
                            
                            # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                            index = timestep_selected_1
                            delta = num_timestep_load_profile[appliance]
                            probability_2 = set_values_to_zero(probability_1, index, delta)

                            # we check if the probability is different from zero
                            if not all(x == 0 for x in probability_2):

                                timestep_selected_2 = random.choices(time_list, weights = probability_2, k = 1)[0] # we randomly choose the start time for the selected appliance
                                start_time_DSM_df_2[appliance][day] = timestep_selected_2 # we save the start time for the selected day

                                assert (timestep_selected_1 != timestep_selected_2), "The timesteps are equal!"
                                assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]), "The timesteps are equal!"
                            
                            else:
                                warnings.warn("All values in probability are zeros in the case with 2 number of uses!", UserWarning)
                                print("")

                        #############################################################################

                        # number of uses equal to 3

                        if num_of_uses_selected > 2:
                            
                            # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                            index = timestep_selected_2 
                            delta = num_timestep_load_profile[appliance]
                            probability_3 = set_values_to_zero(probability_2, index, delta)

                            # we check if the probability is different from zero
                            if not all(x == 0 for x in probability_3):

                                timestep_selected_3 = random.choices(time_list, weights = probability_3, k = 1)[0] # we randomly choose the start time for the selected appliance
                                start_time_DSM_df_3[appliance][day] = timestep_selected_3 # we save the start time for the selected day
                            
                                assert (timestep_selected_1 != timestep_selected_2 or timestep_selected_1 != timestep_selected_3 or timestep_selected_2 != timestep_selected_3), "The timesteps are equal!"
                                assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]  or abs(timestep_selected_1 - timestep_selected_3) > num_timestep_load_profile[appliance]  or abs(timestep_selected_2 - timestep_selected_3) > num_timestep_load_profile[appliance] ), "The timesteps are equal!"

                            else:
                                warnings.warn("All values in probability are zeros in the case with 3 number of uses!", UserWarning)
                                print("")

            ##################################################################################################

            # we set the new dataframe with the start time in the DSM case for the selected appliance
            start_time_DSM_dict_1[user][appliance] = start_time_DSM_df_1[appliance] # number of uses equal to 1
            start_time_DSM_dict_2[user][appliance] = start_time_DSM_df_2[appliance] # number of uses equal to 2
            start_time_DSM_dict_3[user][appliance] = start_time_DSM_df_3[appliance] # number of uses equal to 3

    ##################################################################################################

    # create an aggregated dictionary with all the start time for the different number of uses
    start_time_DSM_dict = {}

    start_time_DSM_dict[0] = start_time_DSM_dict_1 # number of uses equal to 1
    start_time_DSM_dict[1] = start_time_DSM_dict_2 # number of uses equal to 2
    start_time_DSM_dict[2] = start_time_DSM_dict_3 # number of uses equal to 3 

    ##################################################################################################

    # export dictionary in external file
    folder = config["foldername_result_emulator"]
    # now = datetime.now().strftime("(%Y-%m-%d_%H-%M)")
    with open(folder + 'DSM_all_user_appliance_start_time_dict.pkl', 'wb') as fp:
        pickle.dump(start_time_DSM_dict, fp)

    ##################################################################################################

    print("\n     All users start time DSM completed!")

    return (start_time_DSM_dict_1, start_time_DSM_dict_2, start_time_DSM_dict_3)

###################################################################################################################
###################################################################################################################

def load_profile_emulator(emulated_users_list, start_day, end_day, flag_last_dict = False, flag_optDSM = False, flag_all_appliance = True, flag_daily_activation = True, flag_multi_use = True):
    """Simulate all user load profile.

    Inputs:
        num_users (float): number of users 
        start_day (datetime): start day for simulation
        end_day (datetime): end day for simulation
        flag_last_dict (bool, optional): if true we use the last simulated appliance start time to create the load profile. Defaults to False.
        flag_optDSM (bool, optional): if true we use the optimized simulated appliance start time to create the load profile. Defaults to False.
        flag_all_appliance (bool, optional): if false we use as input file the modified appliance load profile. Defaults to True.
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.
    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users
    """

    num_days = (end_day - start_day).days + 1 # we calculate the number of days to simulate

    num_users = int(len(emulated_users_list)) # we calculate the number of users to simulate

    #########################################################################
    
    print("\nRecap:\n")

    print('     num users ', num_users)
    print('     start day ', start_day.strftime("%Y-%m-%d"))
    print('     end day ', end_day.strftime("%Y-%m-%d"))
    print('     num days ', num_days)
    print('\n-----------------------------------------\n')

    #########################################################################

    print("1 - Generate calendar for emulator:\n")

    calendario = generate_calendar_modified(start_day, end_day)

    print('\n-----------------------------------------\n')

    #########################################################################

    print("2 - Generate start time dictionary:\n")

    assert not (flag_last_dict == flag_optDSM == True), "Flag for the import of the last appliance start time dictionary and for the import of the optimized start time dictionary are both true!"

    # if true we use the last simulated appliance start time to create the load profile
    if flag_last_dict:
        config = yaml.safe_load(open("config.yml", 'r'))
        folder = config['foldername_result_emulator']
        with open(folder + 'all_user_appliance_start_time_dict.pkl', 'rb') as fp:
            output = pickle.load(fp)
            print("     All appliance start time imported!")
    
    # if true we use the optimized simulated appliance start time to create the load profile
    elif flag_optDSM:
        config = yaml.safe_load(open("config.yml", 'r'))
        folder = config['foldername_result_emulator']
        with open(folder + 'opt_DSM_all_user_appliance_start_time_dict.pkl', 'rb') as fp:
            output = pickle.load(fp)
            print("     Optimized all appliance start time imported!")
    
    # else we create the appliance start time
    else:
        output = create_all_user_appliance_start_time(emulated_users_list, num_days, calendario, flag_daily_activation, flag_multi_use)
        print("\n     All appliance start time created!")

    #########################################################################

    # split dictionaries in different part (dict_1 are the start time for the first activation; dict_2 are the start time for the second activation, etc.)
    start_time_dict_1 = output[0]
    start_time_dict_2 = output[1]
    start_time_dict_3 = output[2]

    print('\n-----------------------------------------\n')

    #########################################################################

    print("3 - Generate all user profile dictionary:\n")

    flag_DSM = False

    all_user_load_profile_dict = create_all_user_load_profile(start_time_dict_1, start_time_dict_2, start_time_dict_3, emulated_users_list, num_days, flag_DSM, flag_all_appliance)

    print('\n-----------------------------------------\n')

    #########################################################################

    print("4 - Generate all user profiles dataframe and export csv:\n")

    all_user_df = create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM)

    #########################################################################

    print('\n-----------------------------------------\n-----------------------------------------')
    print ('        Simulation completed!')
    print('-----------------------------------------\n-----------------------------------------')

###################################################################################################################
###################################################################################################################

def DSM_load_profile_emulator(emulated_users_list, DSM_emulated_users_list, start_day, end_day, flag_all_appliance = True, flag_daily_activation = True, flag_multi_use = True):
    """Simulate all user load profile with DSM (Demand Side Management).
    Inputs:
        emulated_users_list (list): list of users to simulate
        DSM_emulated_users_list (list): list of users to simulate with DSM
        start_day (datetime): start day for simulation
        end_day (datetime): end day for simulation
        flag_all_appliance (bool, optional): if false we use as input file the modified appliance load profile. Defaults to True.
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.
    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users
    """

    num_days = (end_day - start_day).days + 1 # we calculate the number of days to simulate

    #########################################################################

    print("\n1 - Generate calendar:\n")

    calendario = generate_calendar_modified(start_day, end_day)

    print('\n-----------------------------------------\n')

    #########################################################################

    print("2 - Generate start time DSM dictionary:\n")

    output_DSM = create_all_user_appliance_DSM_start_time(DSM_emulated_users_list, num_days, calendario, flag_daily_activation, flag_multi_use)

    start_time_DSM_dict_1 = output_DSM[0]
    start_time_DSM_dict_2 = output_DSM[1]
    start_time_DSM_dict_3 = output_DSM[2]

    print('\n-----------------------------------------\n')

    #########################################################################

    print("3 - Generate all user profile DSM dictionary:\n")

    flag_DSM = True

    all_user_load_profile_dict = create_all_user_load_profile(start_time_DSM_dict_1, start_time_DSM_dict_2, start_time_DSM_dict_3, emulated_users_list, num_days, flag_DSM, flag_all_appliance)

    print('\n-----------------------------------------\n')

    #########################################################################

    print("4 - Generate all user profiles DSM dataframe and export csv:\n")

    all_user_df = create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM)

    #########################################################################

    print('\n-----------------------------------------\n-----------------------------------------')
    print ('        Simulation completed!')
    print('-----------------------------------------\n-----------------------------------------')

    return

###################################################################################################################
############################### EMULATOR FOR USERS IN USER CACER.XLSX #############################################
###################################################################################################################

def create_emulated_users(flag_last_dict = False, flag_optDSM = False, flag_all_appliance = True, flag_daily_activation = True, flag_multi_use = True):  
    """Create emulated load profile (and eventually DSM emulated load profile) for all emulated users setted in the user CACER.xlsx external file. 

    Inputs:
        flag_last_dict (bool, optional): if true we use the last simulated appliance start time to create the load profile. Defaults to False.
        flag_optDSM (bool, optional): if true we use the optimized simulated appliance start time to create the load profile. Defaults to False.
        flag_all_appliance (bool, optional): if false we use as input file the modified appliance load profile. Defaults to True.
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.
    
    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users
    """

    print(blue("\nCreate load profile for emulated users:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_registry_users = config['filename_registry_users_yml']
    registry_users = yaml.safe_load(open(filename_registry_users, 'r'))
    emulated_users_list = [registry_users[user_id]['user_type'] 
                            for user_id in registry_users 
                            if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer')]

    num_users = int(len(emulated_users_list)) # we calculate the number of users to simulate

    ########################################################################

    # if there is some DSM user in registry_users_types.yml we create also the DSM load profile
    DSM_emulated_users_list = [registry_users[user_id]['user_type'] 
                                for user_id in registry_users 
                                if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer') and (registry_users[user_id]['flag_DSM'] == True)]

    if DSM_emulated_users_list != []:
        flag_simpleDSM = True
    else:
        flag_simpleDSM = False

    ########################################################################

    if num_users == 0:

        print('**** No emulated users found! ****') 

    else:
        start_day = config['start_date']
        project_lifetime = config['project_lifetime_yrs']
        end_day = start_day.replace(year = start_day.year + project_lifetime) - timedelta(days=1)

        ########################################################################
        
        print(blue("\n - Load user emulator:", ['bold']))
        print('-----------------------------------------\n-----------------------------------------')

        load_profile_emulator(emulated_users_list, start_day, end_day, flag_last_dict, flag_optDSM, flag_all_appliance, flag_daily_activation, flag_multi_use)
        
        ########################################################################

        if flag_simpleDSM and not flag_optDSM:
                
            print(blue("\n - DSM load user emulator:", ['bold']))
            print('-----------------------------------------\n-----------------------------------------')

            DSM_load_profile_emulator(emulated_users_list, DSM_emulated_users_list, start_day, end_day, flag_all_appliance, flag_daily_activation, flag_multi_use)
    
    return

###################################################################################################################

############################################## ALL PLOTS ##########################################################

###################################################################################################################

# area graph with all appliance load profile for each day for the user under exam 
def plot_single_user_appliance_load_profile(all_user_appliance_load_profile_dict, id_user, day):
    """Plot the appliance load profile for the user under exam for the selected day.
    
    Inputs:
        all_user_appliance_load_profile_dict (dict): dictionary with all appliance load profile for each day for the user under exam
        id_user (str): user id
        day (int): day to plot
    
    Outputs:
        plot of the appliance load profile for the user under exam for the selected day
    """

    title = 'consumption ' + id_user + ' in day ' + str(day)

    ##########################################################################################################################################

    appliance_consumption_dict = all_user_appliance_load_profile_dict[id_user] # we extract the appliance consumption dictionary for the user under exam

    ##########################################################################################################################################

    appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"] # list of all appliance

    ##########################################################################################################################################

    df = pd.DataFrame()

    ##########################################################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    ##########################################################################################################################################

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    for appliance in appliances_list:
        df[appliance] = appliance_consumption_dict[appliance][day]

    df = df.set_index([list_timestep_dt])

    ##########################################################################################################################################

    fig = px.area(df)

    ##########################################################################################################################################

    fig.update_xaxes(title_text = 'time')
    fig.update_yaxes(title_text = '[kWh]')
    fig.update_layout(title_text = title)
    fig.show()

    ##########################################################################################################################################
    
    # export graph in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################

# graph average load profiles
def plot_appliance_load_profile():
    """Plot the average load profile for all appliances for the user under exam.
    
    Internal inputs:
        usage_probability_df (dataframe): dataframe with the usage probability for all appliances for the user under exam
    
    Outputs:
        plot of the average load profile for all appliances for the user under exam
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_usage_probability = config['filename_usage_probability']
    usage_probability_df = pd.read_excel(filename_usage_probability, header = 0, index_col = 0, sheet_name = "daily_usage_probability") # import of usage probability for dish washer, washing machine, oven, tv e microwaves

    #########################################################################################################

    fig = go.Figure()
    title = 'Daily usage probability of appliances'

    #########################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    #########################################################################################################

    df = usage_probability_df

    for appliance in df.columns:
        if appliance != 'electricity_mains' and appliance != 'fridge':
            fig.add_trace(go.Scatter(
                    x = list_timestep_dt, 
                    y = df[appliance].values,
                    name = appliance))

    #########################################################################################################

    fig.update_layout(
        title_text = title, 
        xaxis = dict(title = 'time', rangeslider = dict(visible=False)))

    fig.update_yaxes(title_text = '[%]')

    fig.show()

    #########################################################################################################

    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################

# graph load profiles
def plot_all_day_load_profile(all_user_load_profile, user):
    """Plot the load profile for the user under exam for all days.
    
    Inputs:
        all_user_load_profile (dict): dictionary with all load profile for each day for every users (timesteps on rows and user_id on columns)
        user (str): user id
    
    Outputs:
        plot of the load profile for the user under exam for all days
    """
    
    df = all_user_load_profile[user]

    #########################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    #########################################################################################################

    fig = go.Figure()
    title = 'Daily ' + user + ' consumption' # you can change the title to plot cer o no cer values

    for day in all_user_load_profile[user].columns:
        fig.add_trace(go.Scatter(
                x = list_timestep_dt, 
                y = df[day],
                name = day))
    
    #########################################################################################################

    fig.update_layout(
        title_text = title, 
        xaxis = dict(title='time', rangeslider=dict(visible=False)))

    fig.update_yaxes(title_text = '[kWh]')

    fig.show()

    #########################################################################################################

    # export graph in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################

# graph average load profiles
def plot_average_users_load_profile(all_user_load_profile, plot_type):
    """Plot the average load profile for all users.
    
    Inputs:
        all_user_load_profile (dict): dictionary with all load profile for each day for every users (timesteps on rows and user_id on columns)
        plot_type (str): type of plot (scatter plot or bar plot)
    
    Outputs:
        plot of the average load profile for all users
    """
    
    fig = go.Figure()
    title = 'Daily average users consumption'

    #########################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    #########################################################################################################

    for user in all_user_load_profile.keys():

        df = all_user_load_profile[user].mean(axis = 1)

        if plot_type == 'scatter plot':

            fig.add_trace(go.Scatter(
                    x = list_timestep_dt, 
                    y = df.values,
                    name = user))
        else:
            fig.add_trace(go.Bar(
            x = df.index,
            y = df.values,
            name = user))

    #########################################################################################################

    fig.update_layout(
        title_text = title, 
        xaxis = dict(title='time', rangeslider=dict(visible=False)))

    fig.update_yaxes(title_text = '[kWh]')

    fig.show()

    #########################################################################################################

    # export graph in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################

# graph average load profiles
def comparison_average_load_profile_arera_profile(all_user_load_profile, month):
    """Plot the average load profile for all users and the arera load profile for the selected month.
    
    Inputs:
        all_user_load_profile (dict): dictionary with all load profile for each day for every users (timesteps on rows and user_id on columns)
        month (int): month to plot
    
    Outputs:
        plot of the average load profile for all users and the arera load profile for the selected month
    """

    fig = go.Figure()
    title = 'Daily average users consumption with arera load profile (DA RIVEDERE!)'

    #########################################################################################################

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    #########################################################################################################

    for user in all_user_load_profile.keys():

        df = pd.DataFrame()
        df['mean'] = all_user_load_profile[user].mean(axis = 1)
        df = df.set_index([list_timestep_dt])

        df = df.resample('1h').sum()

        # ???
        # we shift one hour backward the data for emulated load profile
        # df_1 = df.shift(-1)
        # df_1.iloc[-1] = df.iloc[0]

        fig.add_trace(go.Scatter(
                # x = df.index, 
                y = df['mean'].values,
                name = user))

    #########################################################################################################

    # import of arera load profile
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config['filename_user_load_arera'] 

    arera_df = pd.read_csv(filename, header = 0)

    # Classe potenza: '0<P<=1.5' ; '1.5<P<=3' ; '3<P<=4.5'; '4.5<P<=6' ; 'P>6'
    # Working day: 'Giorno feriale' ; 'Sabato' ; 'Domenica'
    # arera_load_profile_df = arera_df[(arera_df['Mese'] == 1) & (arera_df['Regione'] == 'Calabria') & (arera_df['Classe potenza'] == '3<P<=4.5') & (arera_df['Working day'] == 'Giorno feriale')]

    list_region = ['Abruzzo', 'Basilicata', 'Calabria', 'Campania', 'Emilia-Romagna', 'Friuli-Venezia Giulia', 'Lazio', 'Liguria', 'Lombardia', 'Marche', 'Molise', 'Piemonte', 'Puglia', 'Sardegna', 'Sicilia', 'Toscana', 'Trentino-Alto Adige', 'Umbria']

    for region in list_region:
        
        df = arera_df[(arera_df['Mese'] == month) & (arera_df['Regione'] == region) & (arera_df['Classe potenza'] == '3<P<=4.5') & (arera_df['Working day'] == 'Giorno feriale')]
        
        # ???

        # we shift one hour forward the data for arera load profile
        df_1 = df.shift(1)
        df_1.iloc[0] = df.iloc[-1]

        fig.add_trace(go.Scatter( 
                y = df_1['Prelievo medio Orario Regionale (kWh)'].values,
                name = region))

    #########################################################################################################

    fig.update_layout(
        title_text = title, 
        
        xaxis = dict(title = 'hour', 
                    rangeslider = dict(visible=False),
                    tickmode = 'linear',
                    tick0 = 1,
                    dtick = 1),

        yaxis = dict(title = '[kWh]')
    )

    fig.show()

    #########################################################################################################

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################

def plot_all_day_appliance_load_profile(user, appliance, df):
    """Plot the appliance load profile for the user under exam for all days.
    
    Inputs:
        user (str): user id
        appliance (str): appliance id
        df (dataframe): dataframe with the appliance load profile for the user under exam
    
    Outputs:
        plot of the appliance load profile for the user under exam for all days
    """

    start = datetime(2024,1,1)
    end = datetime(2024,1,2)

    list_timestep_dt = []

    for dt in datetime_range(start, end, {'days': 0, 'minutes' : 15}):
        list_timestep_dt.append(dt)

    #########################################################################################################

    fig = go.Figure()
    title = 'Daily ' + user + ' - ' + appliance + ' consumption' # you can change the title to plot cer o no cer values

    for day in df.columns:
        fig.add_trace(go.Scatter(
                x = list_timestep_dt, 
                y = df[day],
                name = 'day_' + str(day)))

    #########################################################################################################

    fig.update_layout(
        title_text = title, 
        xaxis = dict(title='time', rangeslider=dict(visible=False)))

    fig.update_yaxes(title_text = '[kWh]')

    fig.show()

    #########################################################################################################

    # export graph in external file
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forlername_graphs_load_profile_emulator"]
    fig.write_html(folder + title + ".html") 
    fig.write_image(folder + title + ".png", width = 1000, height = 1200/13.2*5, scale = 4)

###################################################################################################################
###################################################################################################################

def create_optimal_appliance_start_time_dictionary():
    """Create the optimal appliance start time dictionary for the users that partecipate to DSM in CER.
    
    Outputs:
        optimal appliance start time dictionary for the users that partecipate to DSM in CER
    """

    # input to set for the optimzer
    intervals = 96 # number of time intervals (we can set here an hourly simulation?)

    ########################################################################

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_registry_users = config['filename_registry_users_yml']
    registry_users = yaml.safe_load(open(filename_registry_users, 'r'))

    # if there is some DSM user in registry_users_types.yml we create also the DSM load profile
    DSM_emulated_users_list = [registry_users[user_id]['user_type'] 
                                for user_id in registry_users 
                                if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer') and (registry_users[user_id]['flag_DSM'] == True)]

    n_device = int(len(DSM_emulated_users_list)) # number of device to optimize (equal to the number of user that partecipate to DSM in CER)

    ########################################################################

    # number of days to simulate (we can set also all year!)
    days = 365

    config = yaml.safe_load(open("config.yml", 'r'))
    year = config['start_date'].year
    if calendar.isleap(year):
        days+=1

    ################################################################################################################

    filename = config["filename_injected_energy_optimizer"] # foldername to save results
    df = pd.read_csv(filename, parse_dates=['datetime'])
    df.set_index('datetime', inplace=True)

    immissione = df['Enet_inj_config'].head(days * intervals)

    rng = pd.date_range('2022-01-01', periods = days * intervals, freq='15min')
    immissione.index = rng

    ################################################################################################################
    ################################################################################################################

    print("Start optimization of the loads (DSM optimizer)...")

    # optimzize start time of washing-machines and dishwashers respect to the net injected energy
    start_time_dict = suppress_printing(ott_year, immissione, n_device, create_plot = True, show_plot = False)

    print("\nOptimization completed!")

    ################################################################################################################
    ################################################################################################################

    # we export the optimized all users appliance start time dictionary
    folder = config['foldername_result_emulator']
    with open(folder + 'opt_DSM_start_time_dict.pkl', 'wb') as file:
        pickle.dump(start_time_dict, file)

    print("\nExport optimal start time dictionary!")

    ################################################################################################################

    # we import the last dictionary created before the optimization 
    folder = config['foldername_result_emulator']
    with open(folder + 'all_user_appliance_start_time_dict.pkl', 'rb') as file:  # 'rb' is for reading in binary mode
        all_user_appliance_start_time_dict = pickle.load(file)

    print("\nImport all users appliance start time dictionary!")

    ################################################################################################################

    print("\nList of user that partecipate to optimal DSM: \n     " + str(DSM_emulated_users_list) + "\n")

    ################################################################################################################

    # we modify the all user appliance start time dictionary just for the users that partecipate to optimal DSM
    
    count = 0

    for user in DSM_emulated_users_list:

        user_id = "user_" + str(count)
        
        for appliance in ['washing_machine', 'dish_washer']:

            for i in start_time_dict[user_id][appliance].index:

                all_user_appliance_start_time_dict[0][user][appliance].iloc[i] = int(start_time_dict[user_id][appliance].loc[i]) # we modify the start time for the selected appliance

        count+=1

    ################################################################################################################

    # we export the optimized all users appliance start time dictionary
    folder = config['foldername_result_emulator']
    with open(folder + 'opt_DSM_all_user_appliance_start_time_dict.pkl', 'wb') as file:
        pickle.dump(all_user_appliance_start_time_dict, file)

    print("**** Optimized all users appliance start time dictionary exported! ****")

###################################################################################################################



###################################################################################################################