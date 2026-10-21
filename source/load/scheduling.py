from __future__ import annotations

import calendar
import contextlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import io
import math
from pathlib import Path
import pickle
import random
import sys
from typing import Any, Mapping
import warnings

import holidays
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.graph_objs as go_objs
from simple_colors import blue, green, red
from tqdm.auto import tqdm
import yaml

from source.config.utilities import generate_calendar_modified


# Migrated from src/Functions_Load_Emulator_and_DSM.py:78
def create_appliance_start_time(
    num_days,
    calendario,
    flag_daily_activation=True,
    flag_multi_use=True,
    *,
    appliance_load_df,
    usage_probability_df,
    num_daily_usage_probability_df,
    week_usage_probability_df,
):
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

    num_timestep_load_profile = (appliance_load_df != 0).sum() # we calculate the number of timesteps for each appliance

    ##########################################################################################################################################

    wm_week_usage_probability_df = week_usage_probability_df.loc['washing_machines'].copy() # we extract the weekly usage probability for the washing machine

    boolean_list = [True, False]

    ##########################################################################################################################################

    appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"] # list of all appliance

    ##########################################################################################################################################

    start = datetime(2025,1,1)
    end = datetime(2025,1,2)

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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:212
def create_all_user_appliance_start_time(
    emulated_users_list,
    num_days,
    calendario,
    flag_daily_activation=True,
    flag_multi_use=True,
    *,
    appliance_load_df,
    usage_probability_df,
    num_daily_usage_probability_df,
    week_usage_probability_df,
):
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

    print(blue("\nGenerate all user appliance start time:\n"))

    # initialize the dictionaries
    output = {}
    all_user_appliance_start_time_dict_1 = {} # number of uses equal to 1
    all_user_appliance_start_time_dict_2 = {} # number of uses equal to 2
    all_user_appliance_start_time_dict_3 = {} # number of uses equal to 3

    all_user_appliance_start_time_dict = {}

    # we create the start time for the appliance for each user
    for id_user in tqdm(emulated_users_list, desc = "Generate all user appliance start time"):

        output = create_appliance_start_time(
            num_days,
            calendario,
            flag_daily_activation,
            flag_multi_use,
            appliance_load_df=appliance_load_df,
            usage_probability_df=usage_probability_df,
            num_daily_usage_probability_df=num_daily_usage_probability_df,
            week_usage_probability_df=week_usage_probability_df,
        )

        all_user_appliance_start_time_dict_1[id_user] = output[0] # number of uses equal to 1
        all_user_appliance_start_time_dict_2[id_user] = output[1] # number of uses equal to 2
        all_user_appliance_start_time_dict_3[id_user] = output[2] # number of uses equal to 3

    all_user_appliance_start_time_dict[0] = all_user_appliance_start_time_dict_1 # number of uses equal to 1
    all_user_appliance_start_time_dict[1] = all_user_appliance_start_time_dict_2 # number of uses equal to 2
    all_user_appliance_start_time_dict[2] = all_user_appliance_start_time_dict_3 # number of uses equal to 3

    print("\n     **** All appliance start time created! ****")

    return (all_user_appliance_start_time_dict_1, all_user_appliance_start_time_dict_2, all_user_appliance_start_time_dict_3)


# Migrated from src/Functions_Load_Emulator_and_DSM.py:1435
def create_optimal_appliance_start_time_dictionary(
    registry_users,
    injected_energy,
    appliance_profiles,
    all_user_appliance_start_time_dict,
    start_date,
    *,
    create_plot=True,
    show_plot=False,
):
    """Create the optimal appliance start time dictionary for the users that partecipate to DSM in CER.

    Outputs:
        optimal appliance start time dictionary for the users that partecipate to DSM in CER
    """

    # input to set for the optimzer
    intervals = 96 # number of time intervals (we can set here an hourly simulation?)

    ########################################################################

    # if there is some DSM user in registry_users_types.yml we create also the DSM load profile
    DSM_emulated_users_list = [registry_users[user_id]['user_type']
                                for user_id in registry_users
                                if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer') and (registry_users[user_id]['flag_DSM'] == True)]

    n_device = int(len(DSM_emulated_users_list)) # number of device to optimize (equal to the number of user that partecipate to DSM in CER)

    ########################################################################

    # number of days to simulate (we can set also all year!)
    days = 365

    year = start_date.year
    if calendar.isleap(year):
        days+=1

    ################################################################################################################

    immissione = injected_energy['Enet_inj_config'].head(days * intervals)

    rng = pd.date_range('2022-01-01', periods = days * intervals, freq='15min')
    immissione.index = rng

    ################################################################################################################
    ################################################################################################################

    print("Start optimization of the loads (DSM optimizer)...")

    # optimzize start time of washing-machines and dishwashers respect to the net injected energy
    from source.load.DSM import ott_year

    start_time_dict = suppress_printing(
        ott_year,
        immissione,
        n_device,
        appliance_profiles,
        create_plot=create_plot,
        show_plot=show_plot,
    )

    print("\nOptimization completed!")

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

    return start_time_dict, all_user_appliance_start_time_dict


# Migrated from src/Functions_Load_Emulator_and_DSM.py:1605
def create_all_user_appliance_start_time_mod(num_user, num_days, calendar, flag_daily_activation = True, flag_multi_use = True):

    emulated_users_list = create_emulated_users_list(num_user)

    output = create_all_user_appliance_start_time(emulated_users_list, num_days, calendar, flag_daily_activation, flag_multi_use)

    start_time_dict_1 = output[0]
    start_time_dict_2 = output[1]
    start_time_dict_3 = output[2]

    return (start_time_dict_1, start_time_dict_2, start_time_dict_3)


# Migrated from src/Functions_Load_Emulator_v2.py:243
def monthly_activation_probability(appliance, df_monthly_usage_probability, calendar_daily):

    prob_on = df_monthly_usage_probability.loc[appliance][calendar_daily.index[0].month]

    options = [0, 1]
    prob = [1 - prob_on, prob_on]
    activation_flag = int(np.random.choice(options, p=prob))

    return activation_flag


# Migrated from src/Functions_Load_Emulator_v2.py:255
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


# Migrated from src/Functions_Load_Emulator_v2.py:331
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


# Migrated from src/Functions_Load_Emulator_v2.py:349
def extract_next_activation_time(df_usage_appliance, day_date):

    options = df_usage_appliance.index
    prob = df_usage_appliance # equal probability for each load profile, but we could use different probabilities if we want to give more importance to some profiles
    prob = prob / prob.sum()
    timestep_extracted = datetime.strptime(str(day_date) + ' ' + str(np.random.choice(options, p=prob)), '%Y-%m-%d %H:%M:%S')

    print("\n         - Extracted timestep:", str(timestep_extracted))

    return timestep_extracted


# Migrated from src/Functions_Load_Emulator_v2.py:362
def smooth_bias(p, strength=2):
    p_arr = np.asarray(p, dtype=float)
    x = np.linspace(1, 0, len(p_arr))  # decrescente nel tempo
    w = x**strength                # controlli quanto è forte il bias
    p_new = p_arr * w

    p_new = p_new / p_new.sum()

    p_df = p.copy()
    p_df[:] = p_new

    return p_df


# Migrated from src/Functions_Load_Emulator_v2.py:377
def remove_scheduled_probability(df_usage_appliance, timestep_extracted, num_timesteps):
    updated_usage = df_usage_appliance.copy()

    try:
        start_idx = updated_usage.index.get_loc(timestep_extracted.time())
    except KeyError:
        return updated_usage

    end_idx = min(start_idx + max(num_timesteps, 1), len(updated_usage))
    updated_usage.iloc[start_idx:end_idx] = 0

    return updated_usage


# Migrated from src/Functions_Load_Emulator_v2.py:392
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


# Migrated from src/Functions_Load_Emulator_v2.py:470
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


# Migrated from src/Functions_Load_Emulator_v2.py:515
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


# Migrated from src/Functions_Load_Emulator_v2.py:612
def generate_random_value(mean, std):
    random_values = np.random.normal(mean, std)
    random_values = np.maximum(random_values, 0)
    return float(random_values)


# Migrated from src/Functions_Load_Emulator_v2.py:619
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

            mean = float(dict_appliances_load[appliance_extracted].loc['mean'].iloc[0])
            std = float(dict_appliances_load[appliance_extracted].loc['std'].iloc[0])
            consumption_extracted = generate_random_value(mean, std)

            start_idx = df_scheduling.index.get_loc(timestep_extracted) # posizione di start

            df_scheduling.loc[df_scheduling.index[start_idx], 'appliance_consumption_kWh'] += consumption_extracted

            #---------------------------------------------------------------------------------------------

            last_scheduling = timestep_extracted
            last_time = last_scheduling.time()

            #---------------------------------------------------------------------------------------------

    return df_scheduling


# Migrated from src/Functions_Load_Emulator_v2.py:776
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


# Migrated from src/Functions_Load_Emulator_v2.py:814
def create_off_cycle(df_consumption, last_activation, t, appliance_extracted, dict_appliances_load, calendar_df):

    mean = float(dict_appliances_load[appliance_extracted+'_oc'].loc['mean'].iloc[0]) # value in hours
    std = float(dict_appliances_load[appliance_extracted+'_oc'].loc['std'].iloc[0]) # value in hours

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


# Migrated from src/Functions_Load_Emulator_v2.py:1528
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

            mean = float(dict_appliances_load['lamp_1'].loc['mean'].iloc[0])
            std = float(dict_appliances_load['lamp_1'].loc['std'].iloc[0])
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


# Migrated from src/Functions_Load_Emulator_v2.py:2499
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


from source.load.profiles import (
    create_emulated_users_list,
    datetime_range,
    extract_df_usage_probability,
    extract_load_profile,
    set_values_to_zero,
    suppress_printing,
)
