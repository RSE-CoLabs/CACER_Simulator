
import math
import sys
import numpy as np
import pandas as pd
from simple_colors import blue, green, red
from tqdm.auto import tqdm
from datetime import datetime, timedelta
import pickle
import yaml
import plotly.express as px
import plotly.graph_objects as go

from src.Functions_General import generate_calendar_modified, suppress_printing

##########################################################################

def create_list_unique_load_profiles(dict_appliances_load):
    list_unique = []
    for a in list(dict_appliances_load.keys()):
        if a[-2:] == 'oc':
            list_unique.append(a[:-5])
        else:
            list_unique.append(a[:-2])

    list_unique_load_profile = sorted(list(set(list_unique)))

    return list_unique_load_profile

##########################################################################

def create_dict_appliances_load_info(list_unique_load_profile, dict_appliances_load):
    
    # first level: appliance name
    # second level: appliances profile parameters

    #------------------------------------------------------------------

    # profile types:
    #   - blp_profile: base load profile with pattern (96 rows) -> modelled by cycles [kWh], and mean and std values for off cycle duration [min]
    #   - blnp_profile: base load profile without pattern (96 rows) -> modelled by mean and std values [kWh] -> we had to define also a duration for activation!
    #   - s_profile: spike profile (1 row) -> modelled by mean and std values for spike energy consumption [kWh]
    #   - dc_profile: duty cycle profile (96 rows) -> modelled by cycles [kWh]

    #------------------------------------------------------------------

    list_appliances_no_pattern = ['dehumidifier', 'fan', 'internet_router', 'radiator', 'screen', 'sound_system', 'lamp']
    list_appliances_pattern = ['freezer', 'fridge']

    dict_appliances_load_info = {}

    for a in list_unique_load_profile:

        dict_appliances_load_info[a] = {}

        for b in list(dict_appliances_load.keys()):

            if a == b[:-2] and b[-2:] != 'oc':

                #------------------------------------------------------------------

                # if it has 96 rows, it means that it is a base load profile with pattern (blp_profile) or a duty cycle profile (dc_profile), otherwise it is a base load profile without pattern (blnp_profile) or a spike profile (s_profile)
                if dict_appliances_load[b].shape[0] == 96:
                    
                    df = dict_appliances_load[b]
                    num_profiles = int(df.shape[1]) # number of load profiles for the specific appliance (e.g., washing machine has 4 load profiles: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

                    if a in list_appliances_pattern:
                        profile_type = 'blp_profile' # base load profile with pattern
                        flag_pattern = True
                    
                    else:
                        profile_type = 'dc_profile' # duty cycle profile
                        flag_pattern = False

                #------------------------------------------------------------------

                    dict_appliances_load_info[a][b] = {
                        'profile_type' : profile_type,
                        'num_profiles' : num_profiles,
                        'flag_pattern' : flag_pattern,
                        'cycles' : {}
                        }
                
                #------------------------------------------------------------------
                    
                    for i, c in enumerate(df.columns):
                        
                        cycle_id = 'cycle_' + str(i+1)

                        num_timesteps = (df[c]!= 0).sum()
                        dict_appliances_load_info[a][b]['cycles'][cycle_id] = {
                            'num_timesteps' : int(num_timesteps),
                            }
                
                #------------------------------------------------------------------
                    
                else:

                    if a in list_appliances_no_pattern:
                        profile_type = 'blnp_profile' # base load profile without pattern
                    
                    else:
                        profile_type = 's_profile' # spike profile

                    #------------------------------------------------------------------

                    dict_appliances_load_info[a][b] = {
                        'profile_type' : profile_type,
                        }  

                    #------------------------------------------------------------------

    return dict_appliances_load_info                 

##########################################################################

def create_list_profile_type(profile_type, dict_appliances_load_info):
    
    list_appliances = []

    for a in dict_appliances_load_info.keys():
    
        for b in dict_appliances_load_info[a].keys():

            if dict_appliances_load_info[a][b]['profile_type'] == profile_type and a not in list_appliances:
                    list_appliances.append(a)
    
    return list_appliances

##########################################################################

def create_calendar_dfs(start_day, end_day):

    calendar_df = suppress_printing(generate_calendar_modified, start_day, end_day)

    calendar_df['datetime'] = pd.to_datetime(calendar_df['datetime'])

    calendar_df['day_type'] = np.where(
        calendar_df['datetime'].dt.weekday < 5,
        'working_day',
        'weekend'
    )

    calendar_df = calendar_df.set_index('datetime')

    #---------------------------------------------------------------------------------------------

    calendar_daily = calendar_df.resample('D').first()
    calendar_daily.index = calendar_daily.index.date
    
    # mantieni DatetimeIndex (00:00:00 per ogni giorno)
    # calendar_daily.index = calendar_daily.index.normalize()

    calendar_daily.index.rename('date', inplace=True)

    #---------------------------------------------------------------------------------------------

    return calendar_df, calendar_daily

##########################################################################

def assign_cluster_to_users(num_user, df_clusters_distribution):

    # assign each user to a cluster based on the percentage of users in each cluster (probability distribution)

    # - user id:{
    #       - cluster: {}

    ###########################################################################################

    cluster_percentage = df_clusters_distribution['cluster_percentage_normalized'] # percentage of users in each cluster (normalized)

    ###########################################################################################

    clusters = cluster_percentage.index
    probs = cluster_percentage.values

    assigned_clusters = np.random.choice(clusters, size=num_user, p=probs)

    ###########################################################################################

    dict_users = {}

    for u in range(num_user): 
        
        dict_users['user_' + str(u)] = {}
        
        dict_users['user_' + str(u)]['cluster'] = int(assigned_clusters[u])
    
    return dict_users

##########################################################################

def assign_equipment_to_users(num_user, dict_users, df_clusters_equipment, df_clusters_equipment_multi):

    # assign appliances to each user based on the cluster they belong to and the probability of having each appliance in that cluster

    # - user id:{
    #       - cluster: {}
    #       - appliances:{
    #           - appliance_name:{
    #               - number: {}

    ###########################################################################################

    for u in range(num_user):

        u = "user_" + str(u)
        
        cluster = int(dict_users[u]['cluster'])

        dict_users[u]['appliances'] = {}

        for a in df_clusters_equipment.iloc[cluster - 1].index:
            
            options = ['True', 'False'] # if true the appliance is assigned to the user
            prob = df_clusters_equipment.iloc[cluster - 1][a]
            prob_appliance = np.random.choice(options, p=[prob, 1-prob])

            if prob_appliance == 'True':

                dict_users[u]['appliances'][a] = {}

                df_clusters_equipment_multi[a]

                options = df_clusters_equipment_multi.index 
                prob = list(df_clusters_equipment_multi[a].values)
                prob_multi = int(np.random.choice(options, p=prob))
                
                dict_users[u]['appliances'][a] = {"number" : prob_multi}
    
    return dict_users

##########################################################################

def monthly_activation_probability(appliance, df_monthly_usage_probability, calendar_daily):

    prob_on = df_monthly_usage_probability.loc[appliance][calendar_daily.index[0].month]

    options = [0, 1] 
    prob = [1 - prob_on, prob_on]
    activation_flag = int(np.random.choice(options, p=prob))

    return activation_flag

##########################################################################

def create_daily_activation_matrix(dict_users, calendar_daily, dict_multi_usage_probability, df_monthly_usage_probability, show_progress = False):

    # - user id:{
    #       - cluster: {}
    #       - appliances:{
    #           - appliance_name:{
    #               - number: {}
    #               - daily_activation_matrix:[
    #                   - activation_flag,
    #                   - number_of_activation, 
    #                   - day_type,

    ###########################################################################################

    for u in tqdm(dict_users.keys(), desc="Creating daily activation matrix for users", disable=not show_progress):

        for a in dict_users[u]['appliances'].keys():
            
            if a in dict_multi_usage_probability['working_day'].columns:

                daily_activation_matrix = pd.DataFrame(index = calendar_daily.index, columns = ['activation_flag', 'number_of_activation', 'day_type'])
                daily_activation_matrix['day_type'] = calendar_daily['day_type']

                dict_users[u]['appliances'][a]['daily_activation_matrix'] = daily_activation_matrix.copy()

                # create a matrix with two columns: activation_flag and number_of_activation
                matrix = np.zeros((calendar_daily.shape[0], 2))

                for day in range(calendar_daily.shape[0]):
                    
                    #----------------------------------------------------------------------------

                    # extract daily usage probability
                    day_type = daily_activation_matrix.iloc[day]['day_type']

                    options = dict_multi_usage_probability[day_type][a].index 
                    prob = list(dict_multi_usage_probability[day_type][a].values)
                    num_activation = int(np.random.choice(options, p=prob))

                    #----------------------------------------------------------------------------

                    # check monthly activation
                    monthly_activation_flag = monthly_activation_probability(a, df_monthly_usage_probability, calendar_daily)
                    num_activation = num_activation * monthly_activation_flag

                    #----------------------------------------------------------------------------

                    # check consistency washing machine and dryer activation:
                    if a == 'washing_machine' and 'dryer' in dict_users[u]['appliances'].keys():
                        if dict_users[u]['appliances']['dryer']['daily_activation_matrix']['activation_flag'][day]:         
                            num_activation_dryer = dict_users[u]['appliances']['dryer']['daily_activation_matrix']['number_of_activation'][day]
                            num_activation = max(num_activation, num_activation_dryer)
    
                    #----------------------------------------------------------------------------

                    # save in matrix [flag_activation, num_activation]
                    matrix[day] = [(num_activation != 0), num_activation]

                    #----------------------------------------------------------------------------

                # save matrix in dict_users
                dict_users[u]['appliances'][a]['daily_activation_matrix']['activation_flag'] = matrix[:, 0]
                dict_users[u]['appliances'][a]['daily_activation_matrix']['number_of_activation'] = matrix[:, 1]

                dict_users[u]['appliances'][a]['daily_activation_matrix']['activation_flag'] = np.where(
                    dict_users[u]['appliances'][a]['daily_activation_matrix']['activation_flag'] == 0,
                    False,
                    True
                )
    
    print(green("\nDaily activation matrix created for all users and appliances.\n"))
    
    return dict_users

##########################################################################

def extract_appliance(list_appliances, user_id, appliance, dict_users):
    
    # extract appliance
    options = list_appliances
    prob = [1/len(list_appliances)] * len(list_appliances) # equal probability for each appliance, but we could use different probabilities if we want to give more importance to someone
    appliance_extracted = str(np.random.choice(options, p=prob))
    
    #---------------------------------------------------------------------------------------------

    # save selected appliance in dict_users for the current user and appliance
    dict_users[user_id]['appliances'][appliance]['appliance_id'] = appliance_extracted

    #---------------------------------------------------------------------------------------------

    return appliance_extracted, dict_users

##########################################################################

def extract_next_activation_time(df_usage_appliance, day_date):

    options = df_usage_appliance.index
    prob = df_usage_appliance # equal probability for each load profile, but we could use different probabilities if we want to give more importance to some profiles
    prob = prob / prob.sum()
    timestep_extracted = datetime.strptime(str(day_date) + ' ' + str(np.random.choice(options, p=prob)), '%Y-%m-%d %H:%M:%S')

    print("\n         - Extracted timestep:", str(timestep_extracted))

    return timestep_extracted

##########################################################################

def smooth_bias(p, strength=2):
    p_arr = np.asarray(p, dtype=float)
    x = np.linspace(1, 0, len(p_arr))  # decrescente nel tempo
    w = x**strength                # controlli quanto è forte il bias
    p_new = p_arr * w

    p_new = p_new / p_new.sum()

    p_df = p.copy()
    p_df[:] = p_new

    return p_df

##########################################################################

def remove_scheduled_probability(df_usage_appliance, timestep_extracted, num_timesteps):
    updated_usage = df_usage_appliance.copy()

    try:
        start_idx = updated_usage.index.get_loc(timestep_extracted.time())
    except KeyError:
        return updated_usage

    end_idx = min(start_idx + max(num_timesteps, 1), len(updated_usage))
    updated_usage.iloc[start_idx:end_idx] = 0

    return updated_usage

##########################################################################

def remove_overlapping_start_probability(df_usage_appliance, df_scheduling, day_date, num_timesteps):
    updated_usage = df_usage_appliance.copy()

    day_date = pd.Timestamp(day_date).date()
    day_mask = df_scheduling.index.date == day_date
    day_index = df_scheduling.index[day_mask]

    if len(day_index) == 0:
        updated_usage[:] = 0
        return updated_usage

    occupied = df_scheduling.loc[day_index, 'appliance_consumption_kWh'].values > 0
    cycle_timesteps = max(int(num_timesteps), 1)

    for i, time_value in enumerate(updated_usage.index):
        timestep = pd.Timestamp(datetime.combine(day_date, time_value))

        try:
            start_idx = day_index.get_loc(timestep)
        except KeyError:
            updated_usage.iloc[i] = 0
            continue

        end_idx = start_idx + cycle_timesteps

        if end_idx > len(day_index) or occupied[start_idx:end_idx].any():
            updated_usage.iloc[i] = 0

    return updated_usage

##########################################################################

def extract_load_profile(a, appliance_extracted, num_activation, dict_appliances_load_info, strength = 2, ):

    # extract load profile
    list_cycle = list(dict_appliances_load_info[a][appliance_extracted]['cycles'].keys())

    #---------------------------------------------------------------------------------------------

    options = list_cycle
    prob = [1/len(list_cycle)] * len(list_cycle) # equal probability for each load profile, but we could use different probabilities if we want to give more importance to some profiles
    
    #---------------------------------------------------------------------------------------------

    p_arr = np.asarray(prob, dtype=float)
    x = np.linspace(1, 0, len(p_arr))  # decrescente nel tempo
    w = x**(num_activation + strength)                # controlli quanto è forte il bias
    p_new = p_arr * w
    p_new = p_new / p_new.sum()

    #---------------------------------------------------------------------------------------------

    load_profile_extracted = str(np.random.choice(options, p=p_new))

    #---------------------------------------------------------------------------------------------

    # number of timesteps for the extracted load profile
    num_timesteps = dict_appliances_load_info[a][appliance_extracted]['cycles'][load_profile_extracted]['num_timesteps']

    # print("     - number of timesteps:", str(num_timesteps), "\n")

    #---------------------------------------------------------------------------------------------

    return load_profile_extracted, num_timesteps

##########################################################################

def extract_df_usage_probability(day_type, df_usage_probability_wd, df_usage_probability_we):
    
    if day_type == 'working_day':
                df_usage_probability = df_usage_probability_wd.copy() # if the day type is working day, we use the usage probability for working days
    else:
        df_usage_probability = df_usage_probability_we.copy() # if the day type is weekend, we use the usage probability for weekends

    return df_usage_probability

##########################################################################

def create_scheduling(appliance_extracted, 
                      day_date, 
                      timestep_extracted,
                      df_scheduling, 
                      load_profile_extracted, 
                      dict_appliances_load):

    #---------------------------------------------------------------------------------------------

    df_scheduling.loc[timestep_extracted, 'scheduled_activation'] = 1
    df_scheduling.loc[timestep_extracted, 'load_profile_extracted'] = load_profile_extracted

    #---------------------------------------------------------------------------------------------

    profile_arr = dict_appliances_load[appliance_extracted][load_profile_extracted].values
    profile_arr = profile_arr[profile_arr != 0]

    start_idx = df_scheduling.index.get_loc(timestep_extracted) # posizione di start
    day_mask = df_scheduling.index.date == day_date
    day_positions = np.flatnonzero(day_mask)
    day_end_idx = int(day_positions[-1])
    end_idx = min(start_idx + len(profile_arr), day_end_idx + 1)
    profile_arr = profile_arr[: max(end_idx - start_idx, 0)]

    if len(profile_arr) > 0:
        df_scheduling.iloc[start_idx:end_idx, df_scheduling.columns.get_loc('appliance_consumption_kWh')] += profile_arr # inserimento nel dataframe

    #---------------------------------------------------------------------------------------------

    last_scheduling = timestep_extracted

    last_activation = df_scheduling.index[end_idx - 1] if end_idx > start_idx else last_scheduling
    last_date_new = last_activation.date()
    last_time_new = last_activation.time()

    print("         - Last activation time:", str(last_activation))
    print("         - Load cycle duration:", str(len(profile_arr) * 15), "minutes")

    #---------------------------------------------------------------------------------------------

    return df_scheduling, last_scheduling, last_date_new, last_time_new

##########################################################################
import time 

def scheduling_duty_cycle_appliances(
    user_id,
    appliance,
    dict_users,
    dict_appliances_load,
    dict_appliances_load_info,
    calendar_df,
    calendar_daily,
    df_usage_probability_wd,
    df_usage_probability_we,
    strength=2,
    max_seconds=None,
    start_time=None
):

    df = dict_users[user_id]['appliances'][appliance]['daily_activation_matrix'] # daily activation matrix for the specific user and appliance

    list_appliances = list(dict_appliances_load_info[appliance].keys()) # list of load profiles for the specific appliance (e.g., washing machine has 4 appliances: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------

    count_error = 0 # count the number of errors during the scheduling process (e.g., no available timesteps for activation, timestep not extracted, etc.)

    #---------------------------------------------------------------------------------------------

    df_scheduling = pd.DataFrame(0, index = calendar_df.index, columns = ['scheduled_activation', 'load_profile_extracted', 'appliance_consumption_kWh']) # create an empty scheduling matrix for the specific user and appliance, with the same index as calendar_df and columns: scheduled_activation, load_profile_extracted, appliance_consumption_kWh

    #---------------------------------------------------------------------------------------------

    appliance_extracted, dict_users = extract_appliance(list_appliances, user_id, appliance, dict_users) # extract appliance for the specific user and appliance (e.g., washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------

    for day in range(calendar_daily.shape[0]):
        
        if max_seconds is not None and start_time is not None:
            if time.monotonic() - start_time > max_seconds:
                raise TimeoutError(f"Timeout su {user_id} - {appliance}")
        if df.iloc[day]['activation_flag'] == False:
            continue

        else:

            day_date = df.index[day] # date of the current day
            num_activation = int(df.iloc[day]['number_of_activation']) # number of activations for the current day
            day_type = df.iloc[day]['day_type'] # day type (working day or weekend) for the current day

            print('\n', blue((f"Date: {str(day_date)}"), ['bold', 'underlined']))
            print("\n- Number of activations:", str(num_activation))

            #---------------------------------------------------------------------------------------------

            df_usage_probability = extract_df_usage_probability(day_type, df_usage_probability_wd, df_usage_probability_we)

            #---------------------------------------------------------------------------------------------

            df_usage_appliance = df_usage_probability[appliance].copy() # usage probability for the specific appliance (e.g., washing_machine)
            df_usage_appliance.index = pd.to_datetime(df_usage_appliance.index, format='%H:%M:%S').time # convert index to time format

            # iterate over the number of activations for the current day
            for n in range(num_activation):
                if max_seconds is not None and start_time is not None:
                    if time.monotonic() - start_time > max_seconds:
                        raise TimeoutError(f"Timeout su {user_id} - {appliance}")
            

                print("\n     - Activation number:", str(n + 1))

                #---------------------------------------------------------------------------------------------

                # extract load profile for the specific appliance and the specific activation (e.g., washing_machine_1, activation 1)
                load_profile_extracted, num_timesteps = extract_load_profile(appliance, appliance_extracted, num_activation, dict_appliances_load_info, strength = 2)

                #---------------------------------------------------------------------------------------------
                df_usage_available = remove_overlapping_start_probability(df_usage_appliance, df_scheduling, day_date, num_timesteps)

                if df_usage_available.sum() <= 0:
                    print(red("        No non-overlapping timesteps for activation, skipping the remaining activations of the day."))
                    break

                timestep_extracted = extract_next_activation_time(df_usage_available, day_date)

                df_scheduling, _, _, _ = create_scheduling(appliance_extracted, 
                                                           day_date, 
                                                           timestep_extracted,
                                                           df_scheduling, 
                                                           load_profile_extracted, 
                                                           dict_appliances_load)

                df_usage_appliance = remove_scheduled_probability(df_usage_appliance, timestep_extracted, num_timesteps)

                #---------------------------------------------------------------------------------------------

    return df_scheduling, count_error

##########################################################################

def generate_random_value(mean, std):
    random_values = np.random.normal(mean, std)
    random_values = np.maximum(random_values, 0)
    return float(random_values)

##########################################################################

def scheduling_spike_appliances(user_id,
                            appliance,
                            dict_users,
                            dict_appliances_load,
                            dict_appliances_load_info,
                            calendar_df,
                            calendar_daily,
                            df_usage_probability_wd,
                            df_usage_probability_we
                            ):
    
    df = dict_users[user_id]['appliances'][appliance]['daily_activation_matrix'] # daily activation matrix for the specific user and appliance

    list_appliances = list(dict_appliances_load_info[appliance].keys()) # list of load profiles for the specific appliance (e.g., washing machine has 4 appliances: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------
    
    df_scheduling = pd.DataFrame(0, index = calendar_df.index, columns = ['scheduled_activation', 'appliance_consumption_kWh']) # create an empty scheduling matrix for the specific user and appliance, with the same index as calendar_df and columns: scheduled_activation, load_profile_extracted, appliance_consumption_kWh
    last_time = calendar_df.index[0].time() # initial last time is the first time of the calendar

    #---------------------------------------------------------------------------------------------

    appliance_extracted, dict_users = extract_appliance(list_appliances, user_id, appliance, dict_users) # extract appliance for the specific user and appliance (e.g., washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------

    for day in range(calendar_daily.shape[0]):

        day_date = df.index[day] # date of the current day
        num_activation = int(df.iloc[day]['number_of_activation']) # number of activations for the current day
        day_type = df.iloc[day]['day_type'] # day type (working day or weekend) for the current day

        print('\n', blue((f"Date: {str(day_date)}"), ['bold', 'underlined']))
        
        #---------------------------------------------------------------------------------------------

        if num_activation == 0:
            print("\n- No activations for this day!")
            continue
        
        print("\n- Number of activations:", str(num_activation))

        #---------------------------------------------------------------------------------------------

        last_time = datetime.strptime('00:00:00', '%H:%M:%S').time()

        #---------------------------------------------------------------------------------------------

        df_usage_probability = extract_df_usage_probability(day_type, df_usage_probability_wd, df_usage_probability_we)

        #---------------------------------------------------------------------------------------------

        # iterate over the number of activations for the current day
        for n in range(num_activation):

            print("\n     - Activation number:", str(n + 1))

            #---------------------------------------------------------------------------------------------

            df_usage_appliance = df_usage_probability[appliance].copy() # usage probability for the specific appliance (e.g., washing_machine)
            df_usage_appliance.index = pd.to_datetime(df_usage_appliance.index, format='%H:%M:%S').time # convert index to time format

            # set to zero the probabilities of the timesteps that are before the last activation time
            # because we cannot extract a timestep for activation that is before the last activation time
            df_usage_appliance.loc[df_usage_appliance.index == last_time] = 0 

            #---------------------------------------------------------------------------------------------

            timestep_extracted = extract_next_activation_time(df_usage_appliance, day_date)

            #---------------------------------------------------------------------------------------------

            df_scheduling.loc[timestep_extracted, 'scheduled_activation'] = 1

            #---------------------------------------------------------------------------------------------

            mean = float(dict_appliances_load[appliance_extracted].loc['mean'][0])
            std = float(dict_appliances_load[appliance_extracted].loc['std'][0])
            consumption_extracted = generate_random_value(mean, std)

            start_idx = df_scheduling.index.get_loc(timestep_extracted) # posizione di start

            df_scheduling.loc[df_scheduling.index[start_idx], 'appliance_consumption_kWh'] += consumption_extracted

            #---------------------------------------------------------------------------------------------

            last_scheduling = timestep_extracted
            last_time = last_scheduling.time()

            #---------------------------------------------------------------------------------------------

    return df_scheduling

##########################################################################

def explore_tree(obj, indent=0, name="root", max_preview=40):
    # Colors per level
    COLORS = [
        "\033[94m",  # blue
        "\033[92m",  # green
        "\033[93m",  # yellow
        "\033[91m",  # red
        "\033[95m",  # magenta
        "\033[96m",  # cyan
    ]
    RESET = "\033[0m"

    color = COLORS[indent % len(COLORS)]
    prefix = "│   " * indent + "├── "

    # Value preview
    if isinstance(obj, (int, float, str, bool)):
        preview = f": {str(obj)[:max_preview]}"
    else:
        preview = ""

    print(f"{color}{prefix}{name} ({type(obj).__name__}){preview}{RESET}")

    # Dict
    if isinstance(obj, dict):
        for k, v in obj.items():
            explore_tree(v, indent + 1, f"[{k}]")

    # Iterable
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            explore_tree(v, indent + 1, f"[{i}]")

    # Optional pandas support
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            print(f"{color}{'│   ' * (indent+1)}├── shape: {obj.shape}{RESET}")
            print(f"{color}{'│   ' * (indent+1)}├── columns: {list(obj.columns)}{RESET}")
    except ImportError:
        pass

##########################################################################

def save_dictionary_to_pickle(dictionary, filename):

    with open(filename, "wb") as f:
        pickle.dump(dictionary, f)
    
    print(green(f"\n  **** Dictionary saved to {filename} ****"))

##########################################################################

def explore_dictionary(filename):

    with open(filename, "rb") as f:
        data = pickle.load(f)

    explore_tree(data)

##########################################################################

def create_on_cycle(df_consumption, last_scheduling, t, appliance_extracted, appliance, dict_appliances_load, dict_appliances_load_info, calendar_df):

    num_activation = 1
    load_profile_extracted, num_timesteps = extract_load_profile(appliance, 
                                                                 appliance_extracted, 
                                                                 num_activation, 
                                                                 dict_appliances_load_info, 
                                                                 strength = 2)

    last_activation = last_scheduling + timedelta(minutes = (num_timesteps - 1) * 15)

    last_activation = min(calendar_df.index[-1], last_activation)
    t = min(t + (num_timesteps), len(calendar_df.index))

    profile_arr = dict_appliances_load[appliance_extracted][load_profile_extracted].values
    profile_arr = profile_arr[profile_arr != 0]

    df_consumption.loc[last_scheduling : last_activation , 'on_cycle'] = 1
    df_consumption.loc[last_scheduling : last_activation, 'load_profile_extracted'] = load_profile_extracted

    # slice temporale
    time_index = df_consumption.loc[last_scheduling:last_activation].index
    n_steps = len(time_index)

    # taglia o adatta profile_arr
    profile_arr = profile_arr[:n_steps]

    df_consumption.loc[last_scheduling : last_activation, 'appliance_consumption_kWh'] += profile_arr # inserimento nel dataframe

    print(f"On cycle - last iteration index {t}")
    print(f"On cycle duration: {num_timesteps * 15} minutes")
    print(f"last scheduling: {last_scheduling}, last activation: {last_activation}\n")
    print("-----------------------------------------------------------------------------------------------\n")

    return df_consumption, last_activation, t

##########################################################################

def create_off_cycle(df_consumption, last_activation, t, appliance_extracted, dict_appliances_load, calendar_df):

    mean = float(dict_appliances_load[appliance_extracted+'_oc'].loc['mean'][0]) # value in hours
    std = float(dict_appliances_load[appliance_extracted+'_oc'].loc['std'][0]) # value in hours
    
    off_cycle_duration_extracted = generate_random_value(mean, std)
    off_cycle_duration_extracted = math.ceil(off_cycle_duration_extracted * 60 / 15)

    last_scheduling_oc = last_activation + timedelta(minutes = 15)
    last_activation_oc = last_scheduling_oc + timedelta(minutes = (off_cycle_duration_extracted - 1) * 15)

    last_activation_oc = min(calendar_df.index[-1], last_activation_oc)

    t = min(t + (off_cycle_duration_extracted), len(calendar_df.index))

    df_consumption.loc[last_scheduling_oc : last_activation_oc , 'off_cycle'] = 1

    print(f"Off cycle - last iteration index {t}")
    print(f"num_timesteps off cycle: {off_cycle_duration_extracted * 15} minutes")
    print(f"last scheduling: {last_scheduling_oc}, last activation: {last_activation_oc}\n")
    print("-----------------------------------------------------------------------------------------------\n")

    return df_consumption, last_activation_oc, t

##########################################################################

def create_dc_profiles(dict_users, list_appliances_dc, dict_appliances_load, dict_appliances_load_info, calendar_df, calendar_daily, df_usage_probability_wd, df_usage_probability_we, pbar):
    
    n_users = len(dict_users.keys())

    for u, user_id in enumerate(dict_users.keys()):
        
        pbar.set_description("Create consumption for appliances with duty cycle profiles - user " + str(u+1) + " of " + str(n_users))

        print(blue((f"{user_id}"), ['bold']))

        i = 0

        for appliance in dict_users[user_id]['appliances'].keys():

            if appliance not in list_appliances_dc:
            
                continue
            
            else:
                
                i+=1

                print('\n', (f"{i}. Creating scheduling matrix for:"), blue(appliance), '\n')

                count_error = 1
                
                iteration = 0

                while count_error != 0 and iteration < 100:

                    df_scheduling, count_error = suppress_printing(scheduling_duty_cycle_appliances, 
                                                                    user_id,
                                                                    appliance,
                                                                    dict_users,
                                                                    dict_appliances_load,
                                                                    dict_appliances_load_info,
                                                                    calendar_df,
                                                                    calendar_daily,
                                                                    df_usage_probability_wd,
                                                                    df_usage_probability_we, 
                                                                    strength = 2)
                    iteration += 1

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_scheduling.copy()

                if count_error == 0:
                    print(green(f"      **** Scheduling matrix created for {appliance} with no errors! ****", ['bold']))
                else:
                    print(red(f"      **** Scheduling matrix created for {appliance} with {count_error} errors! ****", ['bold']))

        pbar.update(1/n_users)

        print("\n---------------------------------------------------------------------------------------------\n")

    return dict_users

##########################################################################

from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import copy


def _create_dc_profiles_single_user(args):
    (
        user_id,
        user_data,
        list_appliances_dc,
        dict_appliances_load,
        dict_appliances_load_info,
        calendar_df,
        calendar_daily,
        df_usage_probability_wd,
        df_usage_probability_we
    ) = args


    import time

    MAX_SECONDS_PER_APPLIANCE = 60
    MAX_ITERATIONS = 20

    user_data = copy.deepcopy(user_data)

    logs = []
    logs.append(f"\nUSER: {user_id}")

    i = 0

    for appliance in user_data["appliances"].keys():

        if appliance not in list_appliances_dc:
            continue

        i += 1
        logs.append(f"{i}. Creating scheduling matrix for: {appliance}")

        count_error = 1
        iteration = 0
        df_scheduling = None

        start_appliance_time = time.monotonic()

        while count_error != 0 and iteration < MAX_ITERATIONS:

            if time.monotonic() - start_appliance_time > MAX_SECONDS_PER_APPLIANCE:
                logs.append(
                    f"SKIPPED - {user_id} - {appliance} superati {MAX_SECONDS_PER_APPLIANCE} secondi"
                )
                break

            temp_dict_users = {user_id: user_data}

            try:
                df_scheduling, count_error = suppress_printing(
                    scheduling_duty_cycle_appliances,
                    user_id,
                    appliance,
                    temp_dict_users,
                    dict_appliances_load,
                    dict_appliances_load_info,
                    calendar_df,
                    calendar_daily,
                    df_usage_probability_wd,
                    df_usage_probability_we,
                    strength=2,
                    max_seconds=MAX_SECONDS_PER_APPLIANCE,
                    start_time=start_appliance_time
                )
            except TimeoutError:
                logs.append(f"TIMEOUT - {user_id} - {appliance}")
                break
            except Exception as e:
                logs.append(f"ERROR - {user_id} - {appliance}: {e}")
                break

            iteration += 1


        if df_scheduling is not None:
            user_data["appliances"][appliance]["consumption_dataframe"] = df_scheduling.copy()
        else:
            user_data["appliances"][appliance]["consumption_dataframe"] = pd.DataFrame(
                0,
                index=calendar_df.index,
                columns=["appliance_consumption_kWh"]
            )

        if count_error == 0:
            logs.append(f"OK - {appliance} created with no errors")
        else:
            logs.append(f"WARNING - {appliance} created with {count_error} errors")

    return user_id, user_data, logs

###########################################################################

def create_dc_profiles_parallel(
    dict_users,
    list_appliances_dc,
    dict_appliances_load,
    dict_appliances_load_info,
    calendar_df,
    calendar_daily,
    df_usage_probability_wd,
    df_usage_probability_we,
    pbar=None,
    max_workers=None
):

    if max_workers is None:
        max_workers = max(1, os.cpu_count() - 1)

    n_users = len(dict_users)

    tasks = []
    for user_id, user_data in dict_users.items():
        tasks.append((
            user_id,
            user_data,
            list_appliances_dc,
            dict_appliances_load,
            dict_appliances_load_info,
            calendar_df,
            calendar_daily,
            df_usage_probability_wd,
            df_usage_probability_we
        ))

    results_users = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_create_dc_profiles_single_user, task) for task in tasks]

        with tqdm(
            total=n_users,
            desc="Create DC profiles users",
            leave=False,
            file=sys.stderr,
            dynamic_ncols=False
        ) as user_pbar:

            for k, future in enumerate(as_completed(futures), start=1):
                user_id, user_data, logs = future.result()

                results_users[user_id] = user_data

                user_pbar.set_description(
                    f"Create DC profiles - completed {k}/{n_users} - last user: {user_id}",
                    refresh=False
                )
                user_pbar.update(1)

    if pbar is not None:
        pbar.set_description(
            "Create consumption for appliances with duty cycle profiles",
            refresh=False
        )
        pbar.update(1)

    return results_users

###########################################################################

def create_spike_profiles(dict_users, list_appliances_sp, dict_appliances_load, dict_appliances_load_info, calendar_df, calendar_daily, df_usage_probability_wd, df_usage_probability_we):
    for u, user_id in enumerate(dict_users.keys()):

        print(blue((f"{user_id}"), ['bold']))

        i = 0
        flag_spike_appliances = False

        for appliance in dict_users[user_id]['appliances'].keys():

            if appliance not in list_appliances_sp:

                continue
            
            else:
                
                flag_spike_appliances = True

                i+=1

                print('\n', f"{i}. Creating scheduling matrix for:", blue(appliance), '\n')

                df_scheduling = suppress_printing(scheduling_spike_appliances, 
                                                    user_id, 
                                                    appliance,dict_users,
                                                    dict_appliances_load,
                                                    dict_appliances_load_info,
                                                    calendar_df,
                                                    calendar_daily,
                                                    df_usage_probability_wd,
                                                    df_usage_probability_we)

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_scheduling.copy()

                print(green(f"      **** Scheduling matrix created for {appliance} with no errors! ****", ['bold']))

        if not flag_spike_appliances:
            print(f"\n      **** No spike appliances for this user! ****")

        print("\n---------------------------------------------------------------------------------------------\n")

    return dict_users

##########################################################################

def create_base_load_profiles(dict_users, calendar_df, calendar_daily, dict_base_load_stats, show_progress = False):
    
    for u, user_id in tqdm(enumerate(dict_users.keys()), desc="Creating base load profile for users", total=len(dict_users.keys()), disable=not show_progress):

        print(blue((f"{user_id}"), ['bold']))

        dict_users[user_id]['base_load'] = {}

        df_base_load = pd.DataFrame(0, index = calendar_df.index, columns = ['base_load_consumption_kWh']) # create an empty scheduling matrix for the specific user and appliance, with the same index as calendar_df and columns: scheduled_activation, load_profile_extracted, appliance_consumption_kWh

        t = 0

        for day in range(calendar_daily.shape[0]):

                day_date = calendar_daily.index[day] # date of the current day
                day_type = calendar_daily.iloc[day]['day_type'] # day type (working day or weekend) for the current day

                mean_profile = dict_base_load_stats[day_type]['mean']
                std_profile = dict_base_load_stats[day_type]['std']
                upper_bound = dict_base_load_stats[day_type]['upper']
                lower_bound = dict_base_load_stats[day_type]['lower']
                
                base_load_extracted = np.random.normal(mean_profile, std_profile)
                base_load_extracted = base_load_extracted.clip(0) / 1000 # convert from Wh to kWh

                # base_load_extracted = pd.Series(
                #     np.random.uniform(lower_bound, upper_bound),
                #     index=mean_profile.index
                #     ) / 1000

                df_base_load.iloc[t : t + 96, df_base_load.columns.get_loc('base_load_consumption_kWh')] += base_load_extracted # inserimento nel dataframe

                t += 96

        dict_users[user_id]['base_load'] = df_base_load.copy()

        print(green(f"\n      **** Base load created ****"))

        print("\n---------------------------------------------------------------------------------------------\n")

    return dict_users

##########################################################################

def create_base_load_with_pattern_profiles(dict_users, list_appliances_blp, dict_appliances_load, dict_appliances_load_info, calendar_df, show_progress = False):

    for u, user_id in enumerate(dict_users.keys()):

        print(blue((f"\n{user_id}"), ['bold']))

        i = 0

        for appliance in dict_users[user_id]['appliances'].keys():

            if appliance not in list_appliances_blp:
            
                continue
            
            else:
                
                i+=1

                print('\n', (f"{i}. Creating scheduling matrix for:"), blue(appliance), '\n')

                list_appliances = list(dict_appliances_load_info[appliance].keys()) # list of load profiles for the specific appliance (e.g., washing machine has 4 appliances: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

                appliance_extracted, dict_users = extract_appliance(list_appliances, user_id, appliance, dict_users) # extract appliance for the specific user and appliance (e.g., washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

                df_consumption = pd.DataFrame(0, index = calendar_df.index, columns = ['on_cycle', 'off_cycle', 'load_profile_extracted', 'appliance_consumption_kWh']) # create an empty scheduling matrix for the specific user and appliance, with the same index as calendar_df and columns: scheduled_activation, load_profile_extracted, appliance_consumption_kWh
                last_scheduling = calendar_df.index[0]
                t = 0

                with tqdm(desc=f"Creating {appliance} load profile for {user_id}", total=len(calendar_df.index), disable=not show_progress) as pbar:
                    
                    while t < (len(calendar_df.index)):

                        df_consumption, last_activation, t = suppress_printing(create_on_cycle, df_consumption, last_scheduling, t, appliance_extracted, appliance, dict_appliances_load, dict_appliances_load_info, calendar_df)

                        df_consumption, last_activation_oc, t = suppress_printing(create_off_cycle, df_consumption, last_activation, t, appliance_extracted, dict_appliances_load, calendar_df)

                        last_scheduling = last_activation_oc + timedelta(minutes = 15)

                        pbar.update(t - pbar.n)
                
                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_consumption.copy()
        
        print("\n---------------------------------------------------------------------------------------------\n")

    return dict_users


def _create_base_load_with_pattern_single_user(args):
    (
        user_id,
        user_data,
        list_appliances_blp,
        dict_appliances_load,
        dict_appliances_load_info,
        calendar_df
    ) = args

    user_data = copy.deepcopy(user_data)

    logs = []
    logs.append(f"\nUSER: {user_id}")

    i = 0

    for appliance in user_data["appliances"].keys():

        if appliance not in list_appliances_blp:
            continue

        i += 1
        logs.append(f"{i}. Creating base load with pattern for: {appliance}")

        temp_dict_users = {user_id: user_data}

        list_appliances = list(dict_appliances_load_info[appliance].keys())

        appliance_extracted, temp_dict_users = extract_appliance(
            list_appliances,
            user_id,
            appliance,
            temp_dict_users
        )

        user_data = temp_dict_users[user_id]

        df_consumption = pd.DataFrame(
            0,
            index=calendar_df.index,
            columns=[
                "on_cycle",
                "off_cycle",
                "load_profile_extracted",
                "appliance_consumption_kWh"
            ]
        )

        last_scheduling = calendar_df.index[0]
        t = 0

        while t < len(calendar_df.index):

            df_consumption, last_activation, t = suppress_printing(
                create_on_cycle,
                df_consumption,
                last_scheduling,
                t,
                appliance_extracted,
                appliance,
                dict_appliances_load,
                dict_appliances_load_info,
                calendar_df
            )

            df_consumption, last_activation_oc, t = suppress_printing(
                create_off_cycle,
                df_consumption,
                last_activation,
                t,
                appliance_extracted,
                dict_appliances_load,
                calendar_df
            )

            last_scheduling = last_activation_oc + timedelta(minutes=15)

        user_data["appliances"][appliance]["consumption_dataframe"] = df_consumption.copy()

        logs.append(f"OK - {appliance} created")

    return user_id, user_data, logs


def create_base_load_with_pattern_profiles_parallel(
    dict_users,
    list_appliances_blp,
    dict_appliances_load,
    dict_appliances_load_info,
    calendar_df,
    max_workers=None,
    show_user_progress=True
):

    if max_workers is None:
        max_workers = max(1, os.cpu_count() - 1)

    n_users = len(dict_users)

    tasks = []

    for user_id, user_data in dict_users.items():
        tasks.append((
            user_id,
            user_data,
            list_appliances_blp,
            dict_appliances_load,
            dict_appliances_load_info,
            calendar_df
        ))

    results_users = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:

        futures = [
            executor.submit(_create_base_load_with_pattern_single_user, task)
            for task in tasks
        ]

        with tqdm(
            total=n_users,
            desc="Create BLP profiles users",
            leave=False,
            file=sys.stderr,
            disable=not show_user_progress
        ) as user_pbar:

            for k, future in enumerate(as_completed(futures), start=1):

                user_id, user_data, logs = future.result()

                results_users[user_id] = user_data

                user_pbar.set_description(
                    f"Create BLP profiles - completed {k}/{n_users} - last user: {user_id}",
                    refresh=False
                )
                user_pbar.update(1)

    return results_users





##########################################################################

def create_base_load_without_pattern_profiles(dict_users, list_appliances_blnp, dict_appliances_load, dict_appliances_load_info, calendar_df, show_progress = False):

    for u, user_id in enumerate(dict_users.keys()):

        print(blue((f"\n{user_id}"), ['bold']))

        i = 0

        for appliance in dict_users[user_id]['appliances'].keys():

            if appliance not in list_appliances_blnp:
            
                continue
            
            else:
                
                i+=1

                print('\n', (f"{i}. Creating scheduling matrix for:"), blue(appliance), '\n')
                
                list_appliances = list(dict_appliances_load_info[appliance].keys()) # list of load profiles for the specific appliance (e.g., washing machine has 4 appliances: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

                appliance_extracted, dict_users = extract_appliance(list_appliances, user_id, appliance, dict_users) # extract appliance for the specific user and appliance (e.g., washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

                df_consumption = pd.DataFrame(0, index = calendar_df.index, columns = ['appliance_consumption_kWh'])

                for timestamp in tqdm(df_consumption.index, desc=f"Creating {appliance} load profile for {user_id}", total=len(df_consumption.index), disable=not show_progress):
                    mean = float(dict_appliances_load[appliance_extracted].loc['mean'][0]) # value in hours
                    std = float(dict_appliances_load[appliance_extracted].loc['std'][0]) # value in hours

                    consumption_extracted = generate_random_value(mean, std)
                    df_consumption.loc[timestamp, 'appliance_consumption_kWh'] = consumption_extracted

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_consumption.copy()
        
        print("\n---------------------------------------------------------------------------------------------")
    
    return dict_users

##########################################################################

def _create_base_load_without_pattern_single_user(args):
    (
        user_id,
        user_data,
        list_appliances_blnp,
        dict_appliances_load,
        dict_appliances_load_info,
        calendar_df
    ) = args

    user_data = copy.deepcopy(user_data)

    logs = []
    logs.append(f"\nUSER: {user_id}")

    i_appliance = 0

    for appliance in user_data["appliances"].keys():

        if appliance not in list_appliances_blnp:
            continue

        i_appliance += 1
        logs.append(f"{i_appliance}. Creating base load without pattern for: {appliance}")

        temp_dict_users = {user_id: user_data}

        list_appliances = list(dict_appliances_load_info[appliance].keys())

        appliance_extracted, temp_dict_users = extract_appliance(
            list_appliances,
            user_id,
            appliance,
            temp_dict_users
        )

        user_data = temp_dict_users[user_id]

        df_consumption = pd.DataFrame(
            0,
            index=calendar_df.index,
            columns=["appliance_consumption_kWh"]
        )

        mean = float(dict_appliances_load[appliance_extracted].loc["mean"][0])
        std = float(dict_appliances_load[appliance_extracted].loc["std"][0])

        for timestamp in df_consumption.index:
            consumption_extracted = generate_random_value(mean, std)
            df_consumption.loc[timestamp, "appliance_consumption_kWh"] = consumption_extracted

        user_data["appliances"][appliance]["consumption_dataframe"] = df_consumption.copy()

        logs.append(f"OK - {appliance} created")

    return user_id, user_data, logs


#########################################################################

def create_base_load_without_pattern_profiles_parallel(
    dict_users,
    list_appliances_blnp,
    dict_appliances_load,
    dict_appliances_load_info,
    calendar_df,
    max_workers=None,
    show_user_progress=True
):

    if max_workers is None:
        max_workers = max(1, os.cpu_count() - 1)

    n_users = len(dict_users)

    tasks = []

    for user_id, user_data in dict_users.items():
        tasks.append((
            user_id,
            user_data,
            list_appliances_blnp,
            dict_appliances_load,
            dict_appliances_load_info,
            calendar_df
        ))

    results_users = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:

        futures = [
            executor.submit(_create_base_load_without_pattern_single_user, task)
            for task in tasks
        ]

        with tqdm(
            total=n_users,
            desc="Create BLNP profiles users",
            leave=False,
            file=sys.stderr,
            disable=not show_user_progress
        ) as user_pbar:

            for k, future in enumerate(as_completed(futures), start=1):

                user_id, user_data, logs = future.result()

                results_users[user_id] = user_data

                user_pbar.set_description(
                    f"Create BLNP profiles - completed {k}/{n_users} - last user: {user_id}",
                    refresh=False
                )
                user_pbar.update(1)

    return results_users


###########################################################################








def scheduling_light(dict_users, user_id, calendar_df, calendar_daily, df_usage_probability_wd, df_usage_probability_we, dict_appliances_load, dict_appliances_load_info):

    appliance = 'lamp'

    #---------------------------------------------------------------------------------------------

    # at the moment we neglect the number of lamps of the user
    # num_lamps = dict_users['user_0']['appliances']['lamp']['number'] # repeat for all the lamps of the user (e.g., lamp_1, lamp_2, lamp_3, lamp_4, lamp_5)

    #---------------------------------------------------------------------------------------------

    df = dict_users[user_id]['appliances'][appliance]['daily_activation_matrix'] # daily activation matrix for the specific user and appliance

    #---------------------------------------------------------------------------------------------

    list_appliances = list(dict_appliances_load_info[appliance].keys()) # list of load profiles for the specific appliance (e.g., washing machine has 4 appliances: washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------

    df_scheduling = pd.DataFrame(0, index = calendar_df.index, columns = ['scheduled_activation', 'appliance_consumption_kWh']) # create an empty scheduling matrix for the specific user and appliance, with the same index as calendar_df and columns: scheduled_activation, load_profile_extracted, appliance_consumption_kWhlast_time = calendar_df.index[0].time() # initial last time is the first time of the calendar

    #---------------------------------------------------------------------------------------------

    appliance_extracted, dict_users = extract_appliance(list_appliances, user_id, appliance, dict_users) # extract appliance for the specific user and appliance (e.g., washing_machine_1, washing_machine_2, washing_machine_3, washing_machine_4)

    #---------------------------------------------------------------------------------------------

    for day in range(calendar_daily.shape[0]):

        day_date = df.index[day] # date of the current day
        num_activation = int(df.iloc[day]['number_of_activation']) # number of activations for the current day
        day_type = df.iloc[day]['day_type'] # day type (working day or weekend) for the current day

        print('\n', blue((f"Date: {str(day_date)}"), ['bold', 'underlined']))

        #---------------------------------------------------------------------------------------------

        if num_activation == 0:
            print("\n- No activations for this day!")
            continue

        #---------------------------------------------------------------------------------------------

        print("\n- Number of activations:", str(num_activation))

        #---------------------------------------------------------------------------------------------

        df_usage_probability = extract_df_usage_probability(day_type, df_usage_probability_wd, df_usage_probability_we)

        #---------------------------------------------------------------------------------------------

        # iterate over the number of activations for the current day
        for n in range(num_activation):

            print("\n     - Activation number:", str(n + 1))

            #---------------------------------------------------------------------------------------------

            df_usage_appliance = df_usage_probability[appliance].copy() # usage probability for the specific appliance (e.g., washing_machine)
            df_usage_appliance.index = pd.to_datetime(df_usage_appliance.index, format='%H:%M:%S').time # convert index to time format

            #---------------------------------------------------------------------------------------------
            
            # set to zero the probabilities of the timesteps that are before the last activation time
            # because we cannot extract a timestep for activation that is before the last activation time
            # df_usage_appliance.loc[df_usage_appliance.index == last_time] = 0 

            #---------------------------------------------------------------------------------------------

            timestep_extracted = extract_next_activation_time(df_usage_appliance, day_date)

            #---------------------------------------------------------------------------------------------

            df_scheduling.loc[timestep_extracted, 'scheduled_activation'] = 1

            #---------------------------------------------------------------------------------------------

            mean = float(dict_appliances_load['lamp_1'].loc['mean'][0])
            std = float(dict_appliances_load['lamp_1'].loc['std'][0])
            consumption_extracted = generate_random_value(mean, std) / 1000

            #---------------------------------------------------------------------------------------------

            mean = float(dict_appliances_load['lamp_1_d'].iloc[0].values[0])
            std = float(dict_appliances_load['lamp_1_d'].iloc[1].values[0])
            
            flag = True
            while flag:

                duration_extracted = generate_random_value(mean, std)
                duration_extracted = max(math.ceil(duration_extracted), 0)

                if duration_extracted > 0:
                    print("\n         - Extracted duration:", duration_extracted * 15, "minutes")
                    flag = False 

            #---------------------------------------------------------------------------------------------

            start_idx = df_scheduling.index.get_loc(timestep_extracted) # posizione di start

            df_scheduling.iloc[start_idx : start_idx + duration_extracted, df_scheduling.columns.get_loc('appliance_consumption_kWh')] += consumption_extracted

            #---------------------------------------------------------------------------------------------

            last_scheduling = timestep_extracted

            last_activation = last_scheduling + timedelta(minutes = (duration_extracted - 1) * 15)

            print("\n         - Last activation time:", str(last_activation))

            #---------------------------------------------------------------------------------------------

    return df_scheduling

##########################################################################

def create_light_profiles(dict_users, calendar_df, calendar_daily, df_usage_probability_wd, df_usage_probability_we, dict_appliances_load, dict_appliances_load_info):

    for u, user_id in enumerate(dict_users.keys()):

        print(blue((f"\n{user_id}"), ['bold']))

        i = 0

        for appliance in dict_users[user_id]['appliances'].keys():

            if appliance not in ['lamp']:
            
                continue
            
            else:
                
                i+=1

                print('\n', (f"{i}. Creating scheduling matrix for:"), blue(appliance), '\n')
                
                df_scheduling = suppress_printing(scheduling_light, dict_users, user_id, calendar_df, calendar_daily, df_usage_probability_wd, df_usage_probability_we, dict_appliances_load, dict_appliances_load_info)

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_scheduling.copy()
        
        print("---------------------------------------------------------------------------------------------")

    return dict_users

##########################################################################

def plot_load_profile_by_day_type(df_user_consumption, calendar_df, a, hourly_resample = True):

        df = pd.DataFrame(df_user_consumption[a].values, index = calendar_df.index, columns=[a])

        df['day_type'] = calendar_df['day_type']

        #------------------------------------------------------------------------------------------------------------

        df_wd = df[df['day_type'] == 'working_day']

        df_we = df[df['day_type'] == 'weekend']

        #------------------------------------------------------------------------------------------------------------

        df_wd.index = pd.to_datetime(df_wd.index)
        df_wd.drop(columns=['day_type'], inplace=True)

        df_we.index = pd.to_datetime(df_we.index)
        df_we.drop(columns=['day_type'], inplace=True)

        #------------------------------------------------------------------------------------------------------------

        df_wd["date"] = df_wd.index.date
        df_wd["time"] = df_wd.index.strftime("%H:%M")
        df_wd = df_wd.pivot(index="time", columns="date", values=a)

        df_we["date"] = df_we.index.date
        df_we["time"] = df_we.index.strftime("%H:%M")
        df_we = df_we.pivot(index="time", columns="date", values=a)

        #------------------------------------------------------------------------------------------------------------

        df_wd.index = pd.to_datetime(df_wd.index, format='%H:%M')
        if hourly_resample:
            df_wd = df_wd.resample('1H').sum()

        df_we.index = pd.to_datetime(df_we.index, format='%H:%M')
        if hourly_resample:
            df_we = df_we.resample('1H').sum()

        #------------------------------------------------------------------------------------------------------------

        fig_wd = go.Figure()

        for col in df_wd.columns:
            fig_wd.add_trace(
                go.Scatter(
                    x=df_wd.index,
                    y=df_wd[col],
                    mode="lines",
                    name=str(col)
                )
            )

        fig_wd.update_layout(title=f"{a} - working Days", xaxis_title="Time", yaxis_title="Consumption (kWh)")
        fig_wd.update_xaxes(tickformat="%H:%M")
        fig_wd.show()

        #------------------------------------------------------------------------------------------------------------

        fig_we = go.Figure()

        for col in df_we.columns:
            fig_we.add_trace(
                go.Scatter(
                    x=df_we.index,
                    y=df_we[col],
                    mode="lines",
                    name=str(col)
                )
            )

        fig_we.update_layout(title=f"{a} - weekends", xaxis_title="Time", yaxis_title="Consumption (kWh)")
        fig_we.update_xaxes(tickformat="%H:%M")
        fig_we.show()

##########################################################################

def analyze_results(user_id, calendar_df, dict_users, df_clusters_distribution):
    
    df = extract_df_user_consumption(dict_users, user_id, calendar_df)

    df.index = pd.to_datetime(df.index)
    df_hourly = df.resample('H').sum()

    cluster = dict_users[user_id]['cluster']

    members = df_clusters_distribution.iloc[cluster - 1]['members']
    retirees = df_clusters_distribution.iloc[cluster - 1]['retirees']
    workers = df_clusters_distribution.iloc[cluster - 1]['workers']
    unemployed = df_clusters_distribution.iloc[cluster - 1]['unemployed']

    print(blue(f"\n{user_id} characteristics:\n"))
    print(f"   - Cluster: {cluster}\n")
    print(f"        - Members: {members}")
    print(f"        - Retirees: {retirees}")
    print(f"        - Workers: {workers}")
    print(f"        - Unemployed: {unemployed}")

    num_days = df.index.normalize().nunique()

    print(blue(f"\nTotal consumption for {user_id}:", ['bold']), round(df['total_consumption'].sum(), 2), "kWh")
    print(blue(f"Average daily consumption for {user_id}:", ['bold']), round(df['total_consumption'].sum() / num_days, 2), "kWh/day")
    print(blue(f"Maximum hourly consumption for {user_id}:", ['bold']), round(df_hourly['total_consumption'].max(), 2), "kWh/hour")
    print(blue(f"Total base load consumption for {user_id}:", ['bold']), round(df['base_load'].sum(), 2), "kWh")

    print("\n--------------------------------------------------------------------------------\n")

    print(blue(f"Yearly consumption breakdown by appliance for {user_id}:\n", ['bold']))

    for a in df.columns:
        print(f"   - {a}: {round(df[a].sum(), 2)} kWh")

    print("\n--------------------------------------------------------------------------------\n")

    print(blue(f"Yearly consumption breakdown by appliance for {user_id} in percentage:\n", ['bold']))

    for a in df.columns:
        print(f"   - {a}: {round(df[a].sum() / df['total_consumption'].sum() * 100, 2)} %")

##########################################################################

def plot_average_load_profile(user_id, df_user_consumption, calendar_df):
    
    df = pd.DataFrame(df_user_consumption['total_consumption'].values, index = calendar_df.index, columns=['total_consumption'])

    df['day_type'] = calendar_df['day_type']

    df_wd = df[df['day_type'] == 'working_day']
    df_we = df[df['day_type'] == 'weekend']

    df_wd.index = pd.to_datetime(df_wd.index)
    df_wd.drop(columns=['day_type'], inplace=True)
    df_we.index = pd.to_datetime(df_we.index)
    df_we.drop(columns=['day_type'], inplace=True)

    mean_daily_profile_wd = df_wd.groupby(df_wd.index.time).mean()
    mean_daily_profile_we = df_we.groupby(df_we.index.time).mean()

    mean_daily_profile_wd.index = pd.to_datetime(mean_daily_profile_wd.index, format='%H:%M:%S')
    mean_daily_profile_wd = mean_daily_profile_wd.resample('1H').sum()

    mean_daily_profile_we.index = pd.to_datetime(mean_daily_profile_we.index, format='%H:%M:%S')
    mean_daily_profile_we = mean_daily_profile_we.resample('1H').sum()

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=mean_daily_profile_wd.index, y=mean_daily_profile_wd['total_consumption'], mode='lines', name='Working Day'))
    fig.add_trace(go.Scatter(x=mean_daily_profile_we.index, y=mean_daily_profile_we['total_consumption'], mode='lines', name='Weekend'))
    fig.update_layout(title=f"Load profile for {user_id} - Working Days vs Weekends", xaxis_title="Time", yaxis_title="Consumption (kWh)")
    fig.update_layout(showlegend=True)

    fig.show()

##########################################################################

def plot_average_appliance_load_profile(df_user_consumption, calendar_df):
    
    for a in df_user_consumption.columns:

        if a in ['fridge', 'freezer', 'internet_router', 'base_load']:
            continue

        df = pd.DataFrame(df_user_consumption[a].values, index = calendar_df.index, columns=[a])

        df['day_type'] = calendar_df['day_type']

        df_wd = df[df['day_type'] == 'working_day']
        df_we = df[df['day_type'] == 'weekend']

        df_wd.index = pd.to_datetime(df_wd.index)
        df_wd.drop(columns=['day_type'], inplace=True)
        df_we.index = pd.to_datetime(df_we.index)
        df_we.drop(columns=['day_type'], inplace=True)

        mean_daily_profile_wd = pd.DataFrame()
        mean_daily_profile_we = pd.DataFrame()

        mean_daily_profile_wd = df_wd.groupby(df_wd.index.time).mean()
        mean_daily_profile_we = df_we.groupby(df_we.index.time).mean()

        mean_daily_profile_wd.index = pd.to_datetime(mean_daily_profile_wd.index, format='%H:%M:%S')
        mean_daily_profile_wd = mean_daily_profile_wd.resample('1H').sum()

        mean_daily_profile_we.index = pd.to_datetime(mean_daily_profile_we.index, format='%H:%M:%S')
        mean_daily_profile_we = mean_daily_profile_we.resample('1H').sum()

        fig = go.Figure()

        fig.add_trace(go.Scatter(x = mean_daily_profile_wd.index, y = mean_daily_profile_wd[a] * 1000, mode='lines', name='Working Day'))
        fig.add_trace(go.Scatter(x = mean_daily_profile_we.index, y = mean_daily_profile_we[a] * 1000, mode='lines', name='Weekend'))
        fig.update_layout(title=f"{a}", xaxis_title="Time", yaxis_title="Consumption (Wh)")
        fig.update_layout(showlegend=True)
        fig.update_xaxes(tickformat="%H:%M")

        fig.show()

##########################################################################

def extract_df_user_consumption(dict_users, user_id, calendar_df):
    
    # create an empty dataframe with the same index as calendar_df
    df_user_consumption = pd.DataFrame(0, index = calendar_df.index, columns = list(dict_users[user_id]['appliances'].keys())) 

    # fill the dataframe with the consumption of each appliance
    for a in dict_users[user_id]['appliances'].keys():

        if a == 'total_consumption':
            continue

        if 'consumption_dataframe' in dict_users[user_id]['appliances'][a]:
            df_user_consumption[a] = dict_users[user_id]['appliances'][a]['consumption_dataframe']['appliance_consumption_kWh']

    # add the base load
    if 'base_load' in dict_users[user_id].keys():
        df_user_consumption['base_load'] = dict_users[user_id]['base_load']

    # add the total consumption
    df_user_consumption['total_consumption'] = df_user_consumption.sum(axis=1)

    return df_user_consumption

##########################################################################

def aggregate_load_profile(dict_users, calendar_df, show_plot = False):

    print(blue("\nAggregating load profiles for all users:", ['bold']))
    print("\n--------------------------------------------------------------------------------------------------------------------------------")

    for u, user_id in enumerate(dict_users.keys()):

        print(f"\nAggegated load profile for", blue(user_id, ['bold']), ':\n')

        #-----------------------------------------------------------------------------------------------------------------------------

        df_user_consumption = extract_df_user_consumption(dict_users, user_id, calendar_df)

        #-----------------------------------------------------------------------------------------------------------------------------

        dict_users[user_id]['appliances']['total_consumption'] = df_user_consumption['total_consumption']

        #-----------------------------------------------------------------------------------------------------------------------------

        fig = px.line(df_user_consumption)
        fig.update_layout(title=f"Load profile for {user_id}", xaxis_title="Time", yaxis_title="Consumption (kWh)")
        if show_plot: fig.show()

        print("\n--------------------------------------------------------------------------------------------------------------------------------")
    
    return dict_users

##########################################################################

def import_data_load_emulator_v2():

    #---------------------------------------------------------------------------------------------
    # 0. Import paths
    #---------------------------------------------------------------------------------------------

    config = yaml.safe_load(open("config.yml", 'r'))

    path_metadata = config['filename_metadata_v2']
    path_usage_probability = config['filename_usage_probability_v2']
    path_multi_usage_probability = config['filename_multi_usage_probability_v2']
    path_appliances_load_profiles = config['filename_appliances_load_profiles_v2']
    path_base_load_profiles = config['filename_base_load_profiles_v2']
    path_boiler_profiles = config['filename_boiler_profiles_v2']

    results = {}

    #---------------------------------------------------------------------------------------------
    # 1. Import appliances load profiles
    #---------------------------------------------------------------------------------------------

    dict_appliances_load = pd.read_excel(path_appliances_load_profiles, sheet_name = None, index_col = 0)

    list_unique_load_profile = list(pd.read_excel(path_metadata, sheet_name = 'clusters_equipment', index_col = 0).columns)
    # list_unique_load_profile = create_list_unique_load_profiles(dict_appliances_load)

    dict_appliances_load_info = create_dict_appliances_load_info(list_unique_load_profile, dict_appliances_load)

    # list of appliances for each profile type
    list_appliances_sp = create_list_profile_type('s_profile', dict_appliances_load_info)
    list_appliances_blp = create_list_profile_type('blp_profile', dict_appliances_load_info)
    list_appliances_blnp = create_list_profile_type('blnp_profile', dict_appliances_load_info)
    list_appliances_dc = create_list_profile_type('dc_profile', dict_appliances_load_info)

    #---------------------------------------------------------------------------------------------
    # 2. Import base load profiles statistics
    #---------------------------------------------------------------------------------------------

    dict_base_load_stats = pd.read_excel(path_base_load_profiles, sheet_name = None, index_col = 0)

    #---------------------------------------------------------------------------------------------
    # 3. Import usage probability
    #---------------------------------------------------------------------------------------------

    dict_usage_probability = pd.read_excel(path_usage_probability, sheet_name = None, index_col = 0)

    df_usage_probability_wd = dict_usage_probability['working_day']
    df_usage_probability_we = dict_usage_probability['weekend']

    #---------------------------------------------------------------------------------------------
    # 4. Import multi usage probability
    #---------------------------------------------------------------------------------------------

    dict_multi_usage_probability = pd.read_excel(path_multi_usage_probability, sheet_name = None, index_col = 0)

    df_multi_usage_probability_wd = dict_multi_usage_probability['working_day']
    df_multi_usage_probability_we = dict_multi_usage_probability['weekend']

    #---------------------------------------------------------------------------------------------
    # 5. Import metadata load emulator
    #---------------------------------------------------------------------------------------------

    dict_metadata_load_emulator = pd.read_excel(path_metadata, sheet_name = None, index_col = 0)

    df_clusters_distribution = dict_metadata_load_emulator['clusters_distribution']
    df_clusters_equipment = dict_metadata_load_emulator['clusters_equipment']
    df_clusters_equipment_multi = dict_metadata_load_emulator['clusters_equipment_multi']
    df_monthly_usage_probability = dict_metadata_load_emulator['monthly_usage_probability']

    #---------------------------------------------------------------------------------------------
    # 6. Import boiler profiles
    #---------------------------------------------------------------------------------------------

    dict_boiler_profiles = pd.read_excel(path_boiler_profiles, sheet_name = None, index_col = 0)

    #---------------------------------------------------------------------------------------------
    # 6. Return all results
    #---------------------------------------------------------------------------------------------

    results = {'dict_appliances_load': dict_appliances_load,
               'dict_appliances_load_info': dict_appliances_load_info,
               
               'list_appliances_sp': list_appliances_sp,
               'list_appliances_blp': list_appliances_blp,
               'list_appliances_blnp': list_appliances_blnp,
               'list_appliances_dc': list_appliances_dc,
               
               'dict_base_load_stats': dict_base_load_stats,
               
               'df_usage_probability_wd': df_usage_probability_wd,
               'df_usage_probability_we': df_usage_probability_we,
                
               'dict_multi_usage_probability': dict_multi_usage_probability,
               'df_multi_usage_probability_wd': df_multi_usage_probability_wd,
               'df_multi_usage_probability_we': df_multi_usage_probability_we,
               
               'df_clusters_distribution': df_clusters_distribution,
               'df_clusters_equipment': df_clusters_equipment,
               'df_clusters_equipment_multi': df_clusters_equipment_multi,
               
               'df_monthly_usage_probability': df_monthly_usage_probability,
               
               'dict_boiler_profiles': dict_boiler_profiles}
    
    return results

##########################################################################

def load_emulator_v2(num_user, data_input, calendar_df, calendar_daily, simulate_boiler = True, all_boiler_profiles = True, show_results = False, save_all_results = True, specific_appliance = None, parallelize = True, max_workers = 1):

    n_iterations = 12
    run_base_load = specific_appliance is None
    run_blp_profiles = specific_appliance is None or specific_appliance in data_input['list_appliances_blp']
    run_blnp_profiles = specific_appliance is None or specific_appliance in data_input['list_appliances_blnp']
    use_parallel = parallelize and (max_workers is None or max_workers > 1)

    with tqdm(total=n_iterations) as pbar:

        #---------------------------------------------------------------------------------------------
        # 0. Assign clusters to users and create dict_user
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Assign clusters to users")

        dict_users = assign_cluster_to_users(num_user, data_input['df_clusters_distribution'])
        
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 1. Assign appliances to users
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Assign appliances to users")

        if run_base_load:

            dict_users = assign_equipment_to_users(num_user, dict_users, data_input['df_clusters_equipment'], data_input['df_clusters_equipment_multi'])

        else: 

            for u in dict_users.keys():

                dict_users[u]['appliances'] = {specific_appliance: {'number': 1},}

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 2. Evaluate daily activation matrix
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create daily activation matrix")

        dict_users = suppress_printing(create_daily_activation_matrix, 
                                       dict_users, 
                                       calendar_daily, 
                                       data_input['dict_multi_usage_probability'], 
                                       data_input['df_monthly_usage_probability'], 
                                       )

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 3. Calculate scheduled consumption for appliance with "duty cycle profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with duty cycle profiles")

        # ---------------------------------------------------------------------------------------------
        # Create consumption for appliances with duty cycle profiles
        # ---------------------------------------------------------------------------------------------

        dc_args = (
            dict_users,
            data_input['list_appliances_dc'],
            data_input['dict_appliances_load'],
            data_input['dict_appliances_load_info'],
            calendar_df,
            calendar_daily,
            data_input['df_usage_probability_wd'],
            data_input['df_usage_probability_we'],
            pbar
        )

        if use_parallel:
            # Modifica PAOLO 07/05:
            # parallelizzazione della creazione dei profili duty cycle,
            # parte più time-consuming del processo di emulazione.
            dict_users = suppress_printing(
                create_dc_profiles_parallel,
                *dc_args,
                max_workers
            )
        else:
            dict_users = suppress_printing(
                create_dc_profiles,
                *dc_args
            )
            pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 4. Calculate scheduled consumption for appliance with "spike profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with spike profiles")

        dict_users = suppress_printing(create_spike_profiles, 
                                       dict_users, 
                                       data_input['list_appliances_sp'], 
                                       data_input['dict_appliances_load'], 
                                       data_input['dict_appliances_load_info'], 
                                       calendar_df, 
                                       calendar_daily, 
                                       data_input['df_usage_probability_wd'], 
                                       data_input['df_usage_probability_we'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 5. Calculate base load
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create base load")

        if run_base_load:

            dict_users = suppress_printing(create_base_load_profiles, 
                                           dict_users, 
                                           calendar_df, 
                                           calendar_daily, 
                                           data_input['dict_base_load_stats'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 6. Calculate scheduled consumption for appliance with "continuous with pattern profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with continuous pattern profiles")

        if run_blp_profiles:

            if parallelize:
                dict_users = suppress_printing_keep_tqdm(
                    create_base_load_with_pattern_profiles_parallel,
                    dict_users,
                    data_input['list_appliances_blp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df,
                    max_workers,
                    show_user_progress=True
                )
            else:
                dict_users = suppress_printing(
                    create_base_load_with_pattern_profiles,
                    dict_users,
                    data_input['list_appliances_blp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df
                )
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 7. Calculate scheduled consumption for appliance with "continuous without pattern profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with continuous no pattern profiles")

        if run_blnp_profiles:

            if parallelize:
                dict_users = suppress_printing_keep_tqdm(
                    create_base_load_without_pattern_profiles_parallel,
                    dict_users,
                    data_input['list_appliances_blnp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df,
                    max_workers,
                    show_user_progress=True
                )
            else:
                dict_users = suppress_printing(
                    create_base_load_without_pattern_profiles,
                    dict_users,
                    data_input['list_appliances_blnp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df
                )
                
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 8. Calculate scheduled consumption for lighting
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for lighting")

        dict_users = suppress_printing(create_light_profiles, 
                                       dict_users, 
                                       calendar_df, 
                                       calendar_daily, 
                                       data_input['df_usage_probability_wd'], 
                                       data_input['df_usage_probability_we'], 
                                       data_input['dict_appliances_load'], 
                                       data_input['dict_appliances_load_info'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 9. Calculate scheduled consumption for boiler
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for boiler")

        if simulate_boiler:

            dict_users = suppress_printing(create_boiler_profiles, 
                                        dict_users, 
                                        calendar_df, 
                                        calendar_daily, 
                                        data_input['dict_boiler_profiles'], 
                                        all_boiler_profiles)

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------
        # 10. Calculate total consumption for each user
        #---------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Aggregate load profile")

        if show_results: 
            dict_users = aggregate_load_profile(dict_users, calendar_df, show_plot = True)
        else: 
            dict_users = suppress_printing(aggregate_load_profile, dict_users, calendar_df, show_plot = False)

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 11. Save results
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Save results")

        if save_all_results:

            config = yaml.safe_load(open("config.yml", 'r'))
            path_results_emulator = config['foldername_result_emulator']

            suppress_printing(save_dictionary_to_pickle, dict_users, path_results_emulator + "dict_users_emulator_v2.pkl")
        
        stacked_df = export_csv_emulator_v2(dict_users, specific_appliance)

        pbar.update(1)
        
        pbar.set_description("Finished")

    return dict_users, stacked_df

##########################################################################

def export_csv_emulator_v2(dict_users, specific_appliance):

    csv_df = pd.DataFrame(index = dict_users['user_0']['appliances']['total_consumption'].index, columns = dict_users.keys())

    for u in dict_users.keys():
        csv_df[u] = dict_users[u]['appliances']['total_consumption'].copy()

    config = yaml.safe_load(open("config.yml", 'r'))

    if specific_appliance is None:
        path_csv = config['foldername_result_emulator'] + "emulated_load_profile_v2.csv"
    else:
        path_csv = config['foldername_result_emulator'] + specific_appliance + '_emulated_load_profile_v2.csv'
    
    csv_df.to_csv(path_csv)

    return csv_df

##########################################################################

def export_emulated_load_profile_v2(dict_users, specific_appliance):

    csv_df = pd.DataFrame(index = dict_users['user_0']['appliances']['total_consumption'].index, columns = dict_users.keys())

    for u in dict_users.keys():
        csv_df[u] = dict_users[u]['appliances']['total_consumption'].copy()

    config = yaml.safe_load(open("config.yml", 'r'))

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_registry_users = config['filename_registry_users_yml']
    registry_users = yaml.safe_load(open(filename_registry_users, 'r'))
    emulated_users_list = [registry_users[user_id]['user_type'] 
                        for user_id in registry_users 
                            if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer')]

    csv_df.columns = emulated_users_list

    if specific_appliance is None:
        path_csv = config['filename_emulated_load_profile']
    else:
        path_csv = config['filename_emulated_appliance_load_profile_v2'] + specific_appliance + '_emulated_load_profile.csv'
    
    csv_df.to_csv(path_csv)

##########################################################################

def run_load_emulator_v2(simulate_boiler = True, all_boiler_profiles = True, show_results = False, save_all_results = True, specific_appliance = None, parallelize = True, max_workers = 1):

    print(blue("\nCreate load profile for emulated users:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_registry_users = config['filename_registry_users_yml']
    registry_users = yaml.safe_load(open(filename_registry_users, 'r'))
    emulated_users_list = [registry_users[user_id]['user_type'] 
                        for user_id in registry_users 
                            if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer')]

    num_users = int(len(emulated_users_list)) # we calculate the number of users to simulate

    start_day = config['start_date']
    project_lifetime = config['project_lifetime_yrs']
    end_day = start_day.replace(year = start_day.year + project_lifetime) - timedelta(days=1)

    if num_users == 0:

        print('**** No emulated users found! ****') 

    else:

        print('Recap:\n')
        print(f'    - Number of emulated users: {num_users}')
        print(f'    - Start day: {start_day}')
        print(f'    - End day: {end_day}')
        print(f'    - Project lifetime: {project_lifetime} years')

        #---------------------------------------------------------------------------------------------
        # 0. Create calendar
        #---------------------------------------------------------------------------------------------

        print(blue("\n0. Creating calendar:"), '\n')

        calendar_df, calendar_daily = create_calendar_dfs(start_day, end_day)

        print("     **** Calendar created! *****")

        #---------------------------------------------------------------------------------------------
        # 1. Import data: all input needed for the emulator
        #---------------------------------------------------------------------------------------------

        print(blue("\n1. Importing data:"), '\n')

        data_input = import_data_load_emulator_v2()

        print("     **** Data imported! *****")

        #---------------------------------------------------------------------------------------------
        # 2. Run emulator: create and exoport dict_users
        #---------------------------------------------------------------------------------------------

        print(blue("\n2. Running emulator:"), '\n')

        dict_users, stacked_df = load_emulator_v2(num_users, 
                                data_input, 
                                calendar_df, 
                                calendar_daily, 
                                show_results, # a progress bar and some plots with results will be shown
                                save_all_results, # save the results in a pickle file, disactivate if there are too many users!!
                                specific_appliance
                                )
        
        print("     **** Users emulated! *****")

        #---------------------------------------------------------------------------------------------
        # 3. Export results: create "files\\energy\\input\\emulated_load_profile.csv"
        #---------------------------------------------------------------------------------------------

        print(blue("\n3. Export results:"), '\n')

        export_emulated_load_profile_v2(dict_users, specific_appliance)

        print("     **** Results exported! *****")

        print("\n       **** Emulated load profiles exported! ****\n")

        return dict_users

##########################################################################

def export_mean_profile_load_emulator_v2(stacked_df, specific_appliance = None):
    
    mean_profile = stacked_df.mean(axis=1)

    config = yaml.safe_load(open("config.yml", 'r'))

    if specific_appliance is None:
        path_csv = config['foldername_result_emulator'] + 'mean_profile_load_emulator_v2.csv'
    else:
        path_csv = config['foldername_result_emulator'] + specific_appliance + '_mean_profile_load_emulator_v2.csv'

    mean_profile = pd.DataFrame(mean_profile)

    mean_profile.columns = ['mean_profile']

    mean_profile.to_csv(path_csv)

    print("     **** Mean profile exported! ****")

##########################################################################

def remove_specific_appliance(data_input, specific_appliance):
    
    data_input["df_clusters_equipment"][specific_appliance] = 0
    data_input["df_clusters_equipment_multi"][specific_appliance] = 0

    return data_input

##########################################################################

def scheduling_boiler(user_id, dict_users, calendar_df, calendar_daily, dict_boiler_profiles):

        eta = dict_users[user_id]['appliances']['boiler']['efficiency']

        list_boiler = []
        
        for i in dict_boiler_profiles.keys():
                list_boiler.append(i[:-3])

        list_boiler = list(set(list_boiler))

        options = list_boiler
        probs = [1/len(list_boiler)] * len(list_boiler)

        assigned_boiler = str(np.random.choice(options, p=probs))

        df_stats_wd = dict_boiler_profiles[assigned_boiler + '_wd'] 
        df_stats_we = dict_boiler_profiles[assigned_boiler + '_we']

        dict_stats = {
        'working_day': df_stats_wd,
        'weekend': df_stats_we
        }

        print(blue((f"{user_id}"), ['bold']))

        dict_users[user_id]['appliances']['boiler']['consumption_dataframe'] = {}

        df_boiler_load = pd.DataFrame(0, index = calendar_df.index, columns = ['thermal_load_consumption_kWh', 'appliance_consumption_kWh'])

        t = 0

        for day in range(calendar_daily.shape[0]):

                day_date = calendar_daily.index[day] # date of the current day
                day_type = calendar_daily.iloc[day]['day_type'] # day type (working day or weekend) for the current day

                mean_profile = dict_stats[day_type]['mean']
                std_profile = dict_stats[day_type]['std']
                upper_bound = dict_stats[day_type]['upper']
                lower_bound = dict_stats[day_type]['lower']
                
                boiler_load_extracted = np.random.normal(mean_profile, std_profile)
                boiler_load_extracted = boiler_load_extracted.clip(0) # convert from Wh to kWh

                df_boiler_load.iloc[t : t + 96, df_boiler_load.columns.get_loc('thermal_load_consumption_kWh')] += boiler_load_extracted

                t += 96
        
        df_boiler_load['appliance_consumption_kWh'] = df_boiler_load['thermal_load_consumption_kWh'] / eta

        dict_users[user_id]['appliances']['boiler']['consumption_dataframe'] = df_boiler_load.copy()

        print(green(f"\n      **** Boiler profiles created ****"))

        print("\n---------------------------------------------------------------------------------------------\n")

        return dict_users

##########################################################################

def create_boiler_profiles(dict_users, calendar_df, calendar_daily, dict_boiler_profiles, all_boiler_profiles = True):
    
    i = 0

    for u, user_id in enumerate(dict_users.keys()):

            print(blue((f"\n{user_id}"), ['bold']))

            if 'boiler' not in dict_users[user_id]['appliances'].keys():
                    
                continue
                
            else:
                
                i+=1

                print('\n', (f"{i}. Creating scheduling matrix for:"), blue('boiler'), '\n')

                dict_users[user_id]['appliances']['boiler'] = {}

                eta = round(np.random.normal(0.97, 0.01), 2)

                print(f"   - Efficiency: {eta * 100} %\n")

                dict_users[user_id]['appliances']['boiler']['efficiency'] = eta

                # modified dict_boiler_profiles: if all_boiler_profiles is True, we use all the boiler profiles, otherwise we use only boiler_1 and boiler_4 profiles (the ones with lowest mean consumption)
                if all_boiler_profiles == True:
                    dict_boiler_profiles_mod = dict_boiler_profiles
                else:
                    dict_boiler_profiles_mod = {k: v for k, v in dict_boiler_profiles.items() if k[:-3] in ['boiler_1', 'boiler_4']}

                dict_users = suppress_printing(scheduling_boiler, user_id, dict_users, calendar_df, calendar_daily, dict_boiler_profiles_mod)

                print(f"   - Mean daily consumption: {round(dict_users[user_id]['appliances']['boiler']['consumption_dataframe']['appliance_consumption_kWh'].sum() / calendar_daily.shape[0], 2)} kWh\n")

    return dict_users

##########################################################################



##########################################################################



##########################################################################



##########################################################################



##########################################################################
