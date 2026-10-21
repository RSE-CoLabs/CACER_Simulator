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


# Migrated from src/Functions_General.py:641
def upsample_arera_dataframe_to_15min(load_user):
    """ function to upsample from 1hr to 15min the ARERA daily load profiles (only 24 rows, one per hour!).
    The dataframe can have multiple columns (working day, sunday, saturday) but only 24 hourly rows, to avoid mixing different profiles
    Inputs:
        load_user: dataframe arera profile to upsample
    """
    #the load_user["Hour"] updating below creates a SettingWithCopyWarning, which seems to be a false positive. We can deactivate it temporarily to avoid getting it in the output
    if pd.options.mode.chained_assignment == "warn":
        pd.options.mode.chained_assignment = None  # default='warn', disabled= None

    load_user["Hour"] = pd.to_datetime(load_user["Hour"], format="%H:%M:%S")
    load_user_pivot = pd.pivot_table(load_user, values='Prelievo medio Orario Regionale (kWh)', index=['Hour'],
                        columns=['Working day'])

    # creating a new row which was needed as resampling boundary at the end of the dataframe
    new_fake_datapoint = pd.DataFrame(load_user_pivot[-1:].values, index=load_user_pivot.index[-1:] + timedelta(hours=1), columns=load_user_pivot.columns)
    # load_user_pivot = load_user_pivot.append(new_fake_datapoint)
    load_user_pivot = pd.concat((load_user_pivot, new_fake_datapoint), axis = 0)
    resampled_df = load_user_pivot.resample('15min', offset="1H", closed='left').mean().ffill() / 4 #resampling from 1hr to 15 min, and dividing the energy by 4
    resampled_df = resampled_df[:-1] # removing the last row which was needed as resampling boundary
    resampled_df.reset_index(inplace=True)
    resampled_df.Hour = resampled_df.Hour.dt.time
    pd.options.mode.chained_assignment = "warn"  # default='warn', disabled= None
    return resampled_df


# Migrated from src/Functions_General.py:668
def load_profile_single_user(
    df,
    user,
    user_types_set,
    *,
    region,
    delta_t,
    rand_factor,
    user_load_arera=None,
    real_profile_df=None,
    emulated_load_profile_df=None,
    custom_profiles=None,
    weekly_factors=None,
    yearly_factor=None,
):
    """gnerating the load profile for a single user.
    Inputs:
        df                  calendar dataframe with all the needed columns, and previous load profiles from other users
        user                user_id, same user id that we have in registry_users.keys()
    Outputs:
        output_all_users    list with user profiles, updated with new one just computed
    """

    load_profile_id = user_types_set[user]["load_profile_id"] # extract load profile id from registry_user_types.yml
    power_range = user_types_set[user]["power_range"] # extract power range from registry_user_types.yml

    # CASE 1 - arera load profile
    if load_profile_id == "arera":
        if user_load_arera is None:
            raise ValueError("ARERA profiles are required for load_profile_id 'arera'")
        for month in range(1,13): # month as integer from 1 to 12

            # we extract arera load for selected region, selected power range and selected month (we need to check also that this load profile exist!!!)
            load_user_month = user_load_arera[(user_load_arera["Regione"] == region) & (user_load_arera["Classe potenza"] == power_range) & (user_load_arera["Mese"] == month)]
            if delta_t == "15Min":
                load_user_month = upsample_arera_dataframe_to_15min(load_user_month) # arera is in 1hr
                load_user_month['month'] = month # set month in month column
                load_user_month.index.names = ['Quarter'] # set name index as 'Quarter'

            if month != 1:
                load_user = pd.concat([load_user, load_user_month], ignore_index=True) # concat all month in a single column
            else:
                load_user = load_user_month # initialization (only for the first month)

        load_user.set_index(["Hour", "month"], inplace=True) # set index as a combination of "Hour" and "month" columns

    # CASE 2 - real load profile
    elif load_profile_id == "real profile":
        if real_profile_df is None:
            raise ValueError("Real profiles are required for load_profile_id 'real profile'")
        load_user = real_profile_df[user] # real profile for Riccomassimo CER
        load_user = pd.DataFrame(load_user)

    # CASE 3 - emulated load profile
    elif load_profile_id == "emulated profile":
        if emulated_load_profile_df is None:
            raise ValueError(
                "Emulated profiles are required for load_profile_id 'emulated profile'"
            )
        load_user = emulated_load_profile_df[user] # emulated load profile for Riccomassimo CER
        load_user = pd.DataFrame(load_user)

    # CASE 4 - other load profiles
    else: # when we have our profiles given as input
        if custom_profiles is None or load_profile_id not in custom_profiles:
            raise ValueError(f"Custom load profile not found: {load_profile_id}")
        load_user = custom_profiles[load_profile_id].copy()
        load_user["Hour"] = pd.date_range("00:00", "23:45", freq = "15min").time # ATTENZIONE, avevo problemi a importare correttamente il formato del time della colonna HOUR, quindi per semplicita ne ho creato uno nuovo, assumendo che tanto va da 00:00 a 23:45
        load_user.set_index("Hour", inplace = True)

    # If not real profile and not emulated profile and rand_factor is different by 0, we just consider updating_random_variation_flag = True!
    # So the random variation is considered in arera profile cases and other profiles cases!
    updating_random_variation_flag = rand_factor != 0 and load_profile_id != "real profile" and load_profile_id != "emulated profile"

    # If not arera profile and not real profile and not emulated profile, we just define a week_factor variation imported from external file!
    if load_profile_id != "arera" and load_profile_id != "real profile" and load_profile_id != "emulated profile":
        if weekly_factors is None or load_profile_id not in weekly_factors:
            raise ValueError(f"Weekly correction not found: {load_profile_id}")
        week_factor = weekly_factors[load_profile_id]
        if yearly_factor is None:
            raise ValueError("Yearly correction is required for custom profiles")

    # random factor for peak fluctuation: update the random_variation for each datapoint, as fluctuation + or - x% if (updating_random_variation_flag == True). If not, random_variation will remain 0
    df["random_variation"] = 0 # initialize the random variation to zero value
    if updating_random_variation_flag:
        df["random"] = np.random.uniform(0, 1, [len(df),1]) # random values from 0 to 1
        df["random_variation"] = rand_factor / 100 * (df["random"] * 2 - 1) # random values between -rand_factor to +rand_factor


    if load_profile_id == "arera":
        # we prepare the load profile for the merge, stacking the hour and the day_flag, and calling the values "load_active"
        load_user_stack = load_user.stack().reset_index().rename(columns={"Working day":'day_flag',
                                                        "Hour":"hour",
                                                        0:"load_active"})
        df = pd.merge(df, load_user_stack, on=["hour", "month", 'day_flag'], how='inner').sort_values("datetime").reset_index(drop = True)

    elif load_profile_id == "real profile" or load_profile_id == "emulated profile":

        load_user = load_user.reset_index()
        load_user = load_user.drop(columns=['datetime'])
        load_user = load_user.rename(columns={user:"load_active"})
        df = pd.concat([df, load_user], axis=1)
        df = df.sort_values("datetime").reset_index(drop = True)

    else:

        # Arera case has the monthly profiles, while the other cases have the hourly profiles non depending on the month. Thus the method is different, as the structuree
        # of theload_user in this case has also the "month" column.
        # we prepare the load profile for the merge, stacking the hour and the day_flag, and calling the values "load_active"
        load_user_stack = load_user.stack().reset_index().rename(columns={"level_1":'day_flag',
                                                        "Hour":"hour",
                                                        0:"load_active"})

        # updating the df with the load_active values corresponding to the hour and day_flag
        df = pd.merge(df, load_user_stack, on=["hour", 'day_flag'], how = 'inner').sort_values("datetime").reset_index(drop = True)

    # if not arera profile and not real profile and not emulated profile, we update week_factor_active and year_factor_active!
    if load_profile_id != "arera" and load_profile_id != "real profile" and load_profile_id != "emulated profile":

        week_factor_stack = week_factor.stack().reset_index().rename(columns={"level_1":'day_flag',
                                                    "Week":"week",
                                                    0:"weekly_correction"})

        # updating the df with the load_active values corresponding to the week and day_flag
        df = pd.merge(df, week_factor_stack, on=["week", 'day_flag'], how='inner').sort_values("datetime").reset_index(drop=True)

        # updating the df with the load_active values corresponding to the year
        year_factor_stack = yearly_factor["yearly_correction"]
        df = pd.merge(df, year_factor_stack, on=["year"], how='inner').sort_values("datetime").reset_index(drop=True)

    else:
        df["weekly_correction"] = 1
        df["yearly_correction"] = 1

    # CALCULATION
    # we calculate the energy consumption for the specific datapoint
    df["load_active_adjusted"] = df["load_active"] * df["weekly_correction"] * df["yearly_correction"] * (1 + df["random_variation"])

    print("user created: ", blue(user), "\t\t user type: ", load_profile_id )

    return df.set_index("datetime")["load_active_adjusted"]


# Migrated from src/Functions_General.py:786
def load_profile_all_users(
    calendar_df,
    user_types_set,
    *,
    region,
    delta_t,
    rand_factor,
    user_load_arera=None,
    real_profile_df=None,
    emulated_load_profile_df=None,
    custom_profiles=None,
    weekly_factors=None,
    yearly_factor=None,
):

    """
    Loop over all user types, to create the 15min or 1H load profiles.
    Exports:

    """

    print(blue("\nGenerate load profile for user types added:", ['bold', 'underlined']), '\n')

    print("Random factor: " + str(rand_factor) + " %")
    users_consuming_energy = [user for user in user_types_set.keys() if user_types_set[user]["consuming"]] # we extract the list of user type of which consuming is true, excluding the prosumers which don't have load profile
    load_profiles_list = [user_types_set[user]["load_profile_id"] for user in users_consuming_energy] # we extract the load profile list of user type to simulate (the values can be arera, real profile, emulated profile, etc.)

    print(len(users_consuming_energy), "user types consuming found")

    df = calendar_df.copy()
    df.drop(columns=["fascia"], inplace=True)

    # generating columns needed for calculation
    df["hour"] = df["datetime"].dt.time # create hour column
    df["week"] = df["datetime"].dt.isocalendar().week # create week column
    df["month"] = df["datetime"].dt.month # create month column
    df["year"] = df["datetime"].dt.year # create year column

    if "arera" in load_profiles_list:
        if user_load_arera is None:
            raise ValueError("ARERA profiles are required by the configured users")
        user_load_arera = user_load_arera.copy()
        user_load_arera["Hour"] = pd.to_datetime(user_load_arera.Ora, format="%H").dt.time # create the Hour column in the arera df with the correct format

        # replace day type with the correct format
        vals_to_replace = {"Giorno feriale": "Working_day", "Sabato": "Saturday", "Domenica": "Sunday"}
        user_load_arera["Working day"] = user_load_arera["Working day"].map(vals_to_replace)

    for user in users_consuming_energy:
        load_profile_id = user_types_set[user]["load_profile_id"]
        if load_profile_id in ["arera", "real profile", "emulated profile", None]:
            continue
        if custom_profiles is None or load_profile_id not in custom_profiles:
            raise ValueError(f"Custom load profile not found: {load_profile_id}")

    #Start the loop over the consuming user types

    # initializing the results datafame, as copy of df (calendar imported) but with "datetime" as index
    df_results = df.copy(deep=True)
    df_results = df_results.set_index("datetime")

    for user in users_consuming_energy: # loop on user types

        # we generate the load profile of the selected user type for all the timestep over the project lifetime and append it in the output_all_users
        df_results[user] = load_profile_single_user(
            df,
            user,
            user_types_set,
            region=region,
            delta_t=delta_t,
            rand_factor=rand_factor,
            user_load_arera=user_load_arera,
            real_profile_df=real_profile_df,
            emulated_load_profile_df=emulated_load_profile_df,
            custom_profiles=custom_profiles,
            weekly_factors=weekly_factors,
            yearly_factor=yearly_factor,
        )
        assert not df_results[user].isna().any(), "ERROR: Indexing failure! NaN found in " + user

    print("\n**** Load profiles successfully exported! ****")
    return df_results.drop(
        columns=["hour", "week", "month", "year", "holiday", "day_week", "day_flag"]
    )


# Migrated from src/Functions_Load_Emulator_and_DSM.py:26
def suppress_printing(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


# Migrated from src/Functions_Load_Emulator_and_DSM.py:32
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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:57
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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:268
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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:307
def create_single_user_load_profile(
    start_time_df_1,
    start_time_df_2,
    start_time_df_3,
    num_days,
    appliances_list,
    *,
    appliances_load_df,
):
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

    # Create an empty DataFrame to hold aggregated load profiles for each day
    # rows: 96 timesteps, columns: num_days days
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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:379
def create_all_user_load_profile(
    start_time_dict_1,
    start_time_dict_2,
    start_time_dict_3,
    emulated_users_list,
    num_days,
    flag_DSM,
    flag_all_appliance=True,
    *,
    appliances_load_df,
):
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

    print(blue("\nGenerate all users profile dictionary:\n"))

    all_user_load_profile_dict = {} # we create a dict with all load profile for each day for every users (timesteps on rows and user_id on columns)

    # if true we use all appliances for the user load profile simulation
    if flag_all_appliance:
        # List of all appliances. The order of the appliances needs to be equal to the order of the columns in appliance_load_df to work correctly.
        appliances_list = ["electricity_mains", "fridge", "washing_machine", "dish_washer", "microwaves", "tv", "oven"]

    # else we deactivate some appliance in the user load profile simulation
    else:
        # List of all appliances. The order of the appliances needs to be equal to the order of the columns in appliance_load_df to work correctly.
        appliances_list = ["electricity_mains", "fridge", "microwaves", "tv", "oven"]

    for id_user in tqdm(emulated_users_list, desc = "Generate all user load profile"):

        start_time_df_1 = start_time_dict_1[id_user] # we extract the start time for the first use of the appliance for the user under exam
        start_time_df_2 = start_time_dict_2[id_user] # we extract the start time for the second use of the appliance for the user under exam
        start_time_df_3 = start_time_dict_3[id_user] # we extract the start time for the third use of the appliance for the user under exam

        # we create the load profile for the user under exam
        all_user_load_profile_dict[id_user] = create_single_user_load_profile(
            start_time_df_1,
            start_time_df_2,
            start_time_df_3,
            num_days,
            appliances_list,
            appliances_load_df=appliances_load_df,
        )

    return all_user_load_profile_dict


# Migrated from src/Functions_Load_Emulator_and_DSM.py:439
def create_appliance_load_profile(
    start_time_df,
    num_days,
    *,
    appliances_load_df,
):
    """Create a dictionary with all appliance load profile for each day for the user under exam.

    Inputs:
        start_time_df (dataframe): start time for the appliance
        num_days (int): number of days to simulate

    Outputs:
        appliance_consumption_dict: dictionary with all appliance load profile for each day for the user under exam
    """

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


# Migrated from src/Functions_Load_Emulator_and_DSM.py:503
def create_all_user_appliance_load_profile(
    start_time_dict,
    emulated_users_list,
    num_days,
    flag_DSM,
    *,
    appliances_load_df,
):
    """Create all user appliance load profile for all days fixed using the start time simulated.

    Inputs:
        start_time_dict (dict): start time for the appliance
        emulated_users_list (list): list of users to simulate
        num_days (int): number of days to simulate
        flag_DSM (bool): if true we simulate a demand side management scenario

    Outputs:
        all_user_appliance_load_profile_dict: dictionary with all appliance load profile for each day for all the users under exam
    """

    print(blue("Generate all users appliances load profile dictionary:\n"))

    all_user_appliance_load_profile_dict = {} # we create a dict with all appliance load profile for each day for all the users under exam

    for id_user in tqdm(emulated_users_list, desc = "Generate all user appliances load profile"):

        start_time_df = start_time_dict[id_user] # we extract the start time df for the appliance for the user under exam

        all_user_appliance_load_profile_dict[id_user] = (
            create_appliance_load_profile(
                start_time_df,
                num_days,
                appliances_load_df=appliances_load_df,
            )
        )

    print("\n**** All users completed! ****")

    return all_user_appliance_load_profile_dict


# Migrated from src/Functions_Load_Emulator_and_DSM.py:550
def create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM):
    """We change the structure of the dictionary in input. With this function we will obtain an unified dataframe with timestep on rows and different users on columns.

    Inputs:
        all_user_load_profile_dict (dict): dictionary with all load profile for each day for every users (timesteps on rows and user_id on columns)
        calendario (dataframe): calendar
        flag_DSM (bool): if true we simulate a demand side management scenario

    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users on columns.
    """

    print(blue("Generate single user load profile df:\n"))

    all_user_df = pd.DataFrame() # we create a df to save all load profile for each days for every users (timesteps on rows and user_id on columns)

    for user in tqdm(all_user_load_profile_dict.keys(), desc = "Generate single user load profile df"):

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

    return all_user_df


# Migrated from src/Functions_Load_Emulator_and_DSM.py:799
def load_profile_emulator(
    emulated_users_list,
    start_day,
    end_day,
    flag_last_dict=False,
    flag_optDSM=False,
    flag_all_appliance=True,
    flag_daily_activation=True,
    flag_multi_use=True,
    *,
    appliance_load_df,
    usage_probability_df,
    num_daily_usage_probability_df,
    week_usage_probability_df,
    prior_start_times=None,
):
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
        if prior_start_times is None:
            raise ValueError("prior_start_times is required when flag_last_dict is true")
        output = prior_start_times
        print("     All appliance start time imported!")

    # if true we use the optimized simulated appliance start time to create the load profile
    elif flag_optDSM:
        if prior_start_times is None:
            raise ValueError("prior_start_times is required when flag_optDSM is true")
        output = prior_start_times
        print("     Optimized all appliance start time imported!")

    # else we create the appliance start time
    else:
        output = create_all_user_appliance_start_time(
            emulated_users_list,
            num_days,
            calendario,
            flag_daily_activation,
            flag_multi_use,
            appliance_load_df=appliance_load_df,
            usage_probability_df=usage_probability_df,
            num_daily_usage_probability_df=num_daily_usage_probability_df,
            week_usage_probability_df=week_usage_probability_df,
        )

    #########################################################################

    # split dictionaries in different part (dict_1 are the start time for the first activation; dict_2 are the start time for the second activation, etc.)
    start_time_dict_1 = output[0]
    start_time_dict_2 = output[1]
    start_time_dict_3 = output[2]

    print('\n-----------------------------------------\n')

    #########################################################################

    print("3 - Generate all user profile dictionary:\n")

    flag_DSM = False

    all_user_load_profile_dict = create_all_user_load_profile(
        start_time_dict_1,
        start_time_dict_2,
        start_time_dict_3,
        emulated_users_list,
        num_days,
        flag_DSM,
        flag_all_appliance,
        appliances_load_df=appliance_load_df,
    )

    print('\n-----------------------------------------\n')

    #########################################################################

    print("4 - Generate all user profiles dataframe and export csv:\n")

    all_user_df = create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM)

    #########################################################################

    print('\n-----------------------------------------\n-----------------------------------------')
    print ('        Simulation completed!')
    print('-----------------------------------------\n-----------------------------------------')
    return all_user_df, output, all_user_load_profile_dict


# Migrated from src/Functions_Load_Emulator_and_DSM.py:1276
def comparison_average_load_profile_arera_profile(
    all_user_load_profile,
    month,
    arera_df,
    *,
    output_path=None,
):
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

    start = datetime(2025,1,1)
    end = datetime(2025,1,2)

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

    if output_path is not None:
        path = Path(output_path)
        path.mkdir(parents=True, exist_ok=True)
        fig.write_html(path / f"{title}.html")
        fig.write_image(
            path / f"{title}.png",
            width=1000,
            height=1200/13.2*5,
            scale=4,
        )


# Migrated from src/Functions_Load_Emulator_and_DSM.py:1541
def extract_single_appliance_df(appliance, calendar, all_user_appliance_load_profile_dict):

    all_user_df = pd.DataFrame() # we create a df to save all load profile for each days for every users (timesteps on rows and user_id on columns)

    for user in tqdm(all_user_appliance_load_profile_dict.keys(), desc = "Extracting load profile for " + appliance + " for all users..."):

        df = all_user_appliance_load_profile_dict[user][appliance].copy()

        df_1 = pd.DataFrame() # we create a df to save the load profile for each days for the user under exam (timesteps on rows and a unique column)

        i = 0 # flag first iteration

        for column in df.columns:

            df_2 = df[column].copy() # we extract a colum (corresponding to a single day load profile)

            # if first iteration
            if i == 0:
                df_1 = df_2.copy(deep = False)
            # if not first iteration
            else:
                df_1 = pd.concat([df_1, df_2], axis = 0, ignore_index = True).copy()

            i = 1 # update flag first iteration

        all_user_df[user] = df_1.values # add df single user load profile to all_user_df

    all_user_df.set_index(calendar['datetime'].values, inplace = True) # set right index with calendar
    all_user_df.index.names = ['datetime']

    print('Dataframe ' + appliance + ' created!\n')

    return all_user_df


# Migrated from src/Functions_Load_Emulator_and_DSM.py:1582
def create_emulated_users_list(num_user):

    print(blue("Create emulated users id list:\n"))

    emulated_users_list = []

    users_count = 1

    for user in range(num_user):

        user_count_base36 = np.base_repr(users_count, base=10, padding=3)[-3:]
        user_id = "u_" + user_count_base36

        users_count += 1

        emulated_users_list.append(user_id)

    print("**** Emulated users id list created! ****\n")

    return emulated_users_list


# Migrated from src/Functions_Load_Emulator_v2.py:24
def create_list_unique_load_profiles(dict_appliances_load):
    list_unique = []
    for a in list(dict_appliances_load.keys()):
        if a[-2:] == 'oc':
            list_unique.append(a[:-5])
        else:
            list_unique.append(a[:-2])

    list_unique_load_profile = sorted(list(set(list_unique)))

    return list_unique_load_profile


# Migrated from src/Functions_Load_Emulator_v2.py:38
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


# Migrated from src/Functions_Load_Emulator_v2.py:124
def create_list_profile_type(profile_type, dict_appliances_load_info):

    list_appliances = []

    for a in dict_appliances_load_info.keys():

        for b in dict_appliances_load_info[a].keys():

            if dict_appliances_load_info[a][b]['profile_type'] == profile_type and a not in list_appliances:
                    list_appliances.append(a)

    return list_appliances


# Migrated from src/Functions_Load_Emulator_v2.py:139
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


# Migrated from src/Functions_Load_Emulator_v2.py:169
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


# Migrated from src/Functions_Load_Emulator_v2.py:201
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


# Migrated from src/Functions_Load_Emulator_v2.py:424
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


# Migrated from src/Functions_Load_Emulator_v2.py:459
def extract_df_usage_probability(day_type, df_usage_probability_wd, df_usage_probability_we):

    if day_type == 'working_day':
                df_usage_probability = df_usage_probability_wd.copy() # if the day type is working day, we use the usage probability for working days
    else:
        df_usage_probability = df_usage_probability_we.copy() # if the day type is weekend, we use the usage probability for weekends

    return df_usage_probability


# Migrated from src/Functions_Load_Emulator_v2.py:840
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
                df_scheduling = pd.DataFrame(
                    0,
                    index=calendar_df.index,
                    columns=['scheduled_activation', 'load_profile_extracted', 'appliance_consumption_kWh']
                )

                try:
                    while count_error != 0 and iteration < 100:

                        df_scheduling, count_error = suppress_printing(
                            scheduling_duty_cycle_appliances,
                            user_id,
                            appliance,
                            dict_users,
                            dict_appliances_load,
                            dict_appliances_load_info,
                            calendar_df,
                            calendar_daily,
                            df_usage_probability_wd,
                            df_usage_probability_we,
                            strength=2
                        )
                        iteration += 1
                except Exception as e:
                    print(red(f"      **** Error while creating {appliance} for {user_id}: {e} ****", ['bold']))
                    count_error = 1

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_scheduling.copy()

                if count_error == 0:
                    print(green(f"      **** Scheduling matrix created for {appliance} with no errors! ****", ['bold']))
                else:
                    print(red(f"      **** Scheduling matrix created for {appliance} with {count_error} errors! ****", ['bold']))

        pbar.update(1/n_users)

        print("\n---------------------------------------------------------------------------------------------\n")

    return dict_users


# Migrated from src/Functions_Load_Emulator_v2.py:913
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


# Migrated from src/Functions_Load_Emulator_v2.py:1007
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


# Migrated from src/Functions_Load_Emulator_v2.py:1074
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


# Migrated from src/Functions_Load_Emulator_v2.py:1119
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


# Migrated from src/Functions_Load_Emulator_v2.py:1163
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


# Migrated from src/Functions_Load_Emulator_v2.py:1210
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


# Migrated from src/Functions_Load_Emulator_v2.py:1295
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


# Migrated from src/Functions_Load_Emulator_v2.py:1359
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
                    mean = float(dict_appliances_load[appliance_extracted].loc['mean'].iloc[0]) # value in hours
                    std = float(dict_appliances_load[appliance_extracted].loc['std'].iloc[0]) # value in hours

                    consumption_extracted = generate_random_value(mean, std)
                    df_consumption.loc[timestamp, 'appliance_consumption_kWh'] = consumption_extracted

                dict_users[user_id]['appliances'][appliance]['consumption_dataframe'] = df_consumption.copy()

        print("\n---------------------------------------------------------------------------------------------")

    return dict_users


# Migrated from src/Functions_Load_Emulator_v2.py:1400
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

        mean = float(dict_appliances_load[appliance_extracted].loc["mean"].iloc[0])
        std = float(dict_appliances_load[appliance_extracted].loc["std"].iloc[0])

        for timestamp in df_consumption.index:
            consumption_extracted = generate_random_value(mean, std)
            df_consumption.loc[timestamp, "appliance_consumption_kWh"] = consumption_extracted

        user_data["appliances"][appliance]["consumption_dataframe"] = df_consumption.copy()

        logs.append(f"OK - {appliance} created")

    return user_id, user_data, logs


# Migrated from src/Functions_Load_Emulator_v2.py:1460
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


# Migrated from src/Functions_Load_Emulator_v2.py:1644
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


# Migrated from src/Functions_Load_Emulator_v2.py:1920
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


# Migrated from src/Functions_Load_Emulator_v2.py:1945
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


# Migrated from src/Functions_Load_Emulator_v2.py:2490
def remove_specific_appliance(data_input, specific_appliance):

    data_input["df_clusters_equipment"][specific_appliance] = 0
    data_input["df_clusters_equipment_multi"][specific_appliance] = 0

    return data_input


# Migrated from src/Functions_Load_Emulator_v2.py:2560
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


from source.load.scheduling import (
    create_all_user_appliance_start_time,
    create_off_cycle,
    create_on_cycle,
    extract_appliance,
    generate_random_value,
    scheduling_boiler,
    scheduling_duty_cycle_appliances,
    scheduling_light,
    scheduling_spike_appliances,
)
