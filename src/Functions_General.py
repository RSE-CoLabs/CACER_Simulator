import pandas as pd
import numpy as np
import os
import holidays
from random import random
import calendar
from datetime import date
import datetime
import yaml
from ruamel.yaml import YAML
import xlwings as xw
# from xlwings.constants import DeleteShiftDirection
import sys
import time
import csv
import glob
import shutil
import collections
from yaml.representer import Representer
yaml.SafeDumper.add_representer(collections.defaultdict, Representer.represent_dict)
from ruamel.yaml import YAML
import signal
import psutil
from simple_colors import *

##########################################################

def initialization_users():
    """
    This function aggregates the initialization processes needed in the simulation.
    """

    print(blue("\nGenerate parameters in yaml file from xlsx file:", ['bold', 'underlined']), '\n')

    generate_users_yml(base=36)

    generate_plant_yml()

    membership_matrix()

    plant_operation_matrix()

##########################################################

def generate_calendar():
    """
    This function generates the calendar.

    Inputs:
        start_date      datetime, starting date to generate the calendar (from config.yml)
        end_date        datetime, ending date to generate the calendar
        delta_t         string, time interval between 2 timesteps, indicated as datetime format ("15min" or "1H")
    Outputs:
        filename_calendar file with datetime, working_day (0=monday, 6=sunday), holiday (True/False) and Tariff time slots (1,2,3)
    """

    print(blue("\nCreate calendar:", ['bold', 'underlined']), '\n')

    # getting all needed inputs from config.yml  
    config = yaml.safe_load(open("config.yml", 'r'))
    start_date = str(config['start_date'])

    project_lifetime_yrs = config['project_lifetime_yrs']

    delta_t = config['delta_t']

    end_date = str(int(start_date[:4]) + project_lifetime_yrs) + '-01-01'

    filename_giorni_tipo = config['filename_giorni_tipo']
    giorni_tipo = pd.read_csv(filename_giorni_tipo) # ???

    print("start date: ", start_date)
    print("number of years: ", project_lifetime_yrs)
    print("delta time: ", delta_t)

    # generating the calendar
    cal = pd.DataFrame({"datetime": pd.date_range(start=start_date, end=end_date, freq=delta_t)})
    cal=cal[:-1] # removing the last element which is out of the needed range

    cal['day_week']= cal.datetime.dt.dayofweek

    cal["day"] = cal.datetime.dt.day 

    #######################################################################################################

    it_holidays = holidays.IT() # getting italian holidays
    cal['holiday'] = cal['datetime'].apply(lambda x: x.date() in it_holidays)

    #######################################################################################################

    # extracting days of the week
    Lun=cal[(cal['day_week']==0) & (cal['holiday'] == False)]
    Mar=cal[(cal['day_week']==1) & (cal['holiday'] == False)]
    Mer=cal[(cal['day_week']==2) & (cal['holiday'] == False)]
    Gio=cal[(cal['day_week']==3) & (cal['holiday'] == False)]
    Ven=cal[(cal['day_week']==4) & (cal['holiday'] == False)]
    Sab=cal[(cal['day_week']==5) & (cal['holiday'] == False)]
    Dom=cal[(cal['day_week']==6) | (cal['holiday'] == True)]

    # data ranges
    ind_L=int(Lun['day'].shape[0]/96)
    ind_M=int(Mar['day'].shape[0]/96)
    ind_Me=int(Mer['day'].shape[0]/96)
    ind_G=int(Gio['day'].shape[0]/96)
    ind_V=int(Ven['day'].shape[0]/96)
    ind_S=int(Sab['day'].shape[0]/96)
    ind_D=int(Dom['day'].shape[0]/96)

    # type of day
    arr_lun=np.array([])
    arr_mar=np.array([])
    arr_mer=np.array([])
    arr_gio=np.array([])
    arr_ven=np.array([])
    arr_sab=np.array([])
    arr_dom=np.array([])

    # establishing the tariff time slot based on type of day (working day, saturday, sunday, holiday)
    for i in range(0,ind_L):
        arr_lun=np.concatenate([arr_lun,giorni_tipo['Lav']])
    #
    for i in range(0,ind_M):
        arr_mar=np.concatenate([arr_mar,giorni_tipo['Lav']])
    #
    for i in range(0,ind_Me):
        arr_mer=np.concatenate([arr_mer,giorni_tipo['Lav']])
    #
    for i in range(0,ind_G):
        arr_gio=np.concatenate([arr_gio,giorni_tipo['Lav']])
    #
    for i in range(0,ind_V):
        arr_ven=np.concatenate([arr_ven,giorni_tipo['Lav']])
    #
    for i in range(0,ind_S):
        arr_sab=np.concatenate([arr_sab,giorni_tipo['Sab']])
    #
    for i in range(0,ind_D):
        arr_dom=np.concatenate([arr_dom,giorni_tipo['Dom']])
    
    Lun.insert(4, 'fascia', arr_lun)
    Mar.insert(4, 'fascia', arr_mar) 
    Mer.insert(4, 'fascia', arr_mer) 
    Gio.insert(4, 'fascia', arr_gio)
    Ven.insert(4, 'fascia', arr_ven)
    Sab.insert(4, 'fascia', arr_sab) 
    Dom.insert(4, 'fascia', arr_dom) 
    #
    cal = pd.concat([Lun,Mar,Mer,Gio,Ven,Sab,Dom], sort=False).sort_index()
    cal.drop(columns=["day"], inplace=True)
    
    #######################################################################################################

    # preassigning value of working_day
    cal["day_flag"] = "Working_day"
    cal.loc[cal["day_week"] == 5,"day_flag"] = "Saturday" #overwrite the saturdays
    cal.loc[cal["day_week"] == 6,"day_flag"] = "Sunday" #overwrite the sundays
    cal.loc[cal["holiday"],"day_flag"] = "Sunday" #overwrite the holidays, modelled as sundays

    filename_calendar = config['filename_calendar']
    cal.to_csv(filename_calendar,index=False)

    #######################################################################################################

    # creating a calendar for the financial analysis, monthly-based
    filename_monthly_calendar = config["filename_monthly_calendar"]
    cal["month"] = cal.datetime.dt.strftime("%Y-%m")

    monthly_calendar = pd.DataFrame(data={"month": cal["month"].unique()})
    monthly_calendar["month_number"] = np.linspace(1, len(monthly_calendar),len(monthly_calendar)).astype(int)
    monthly_calendar[["month_number","month"]].to_csv(filename_monthly_calendar,index=True)

    print("\n**** Calendar successfully exported! ****\n")

##########################################################

def get_calendar():
    """ retrieves the active calendar from the file config['filename_calendar'] as a dataframe, as it is, without updating, and adjusts the datetime format
    Output:
        cal: dataframe
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    cal = pd.read_csv(config['filename_calendar'])
    cal['datetime'] = pd.to_datetime(cal['datetime'], format = "%Y-%m-%d %H:%M:%S")
    return cal

##########################################################

def get_monthly_calendar():
    """ retrieves the active monthly calendar, consisting in just a series with months formatted as YYYY-MM
    Output:
        cal: dataframe
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    cal = pd.read_csv(config['filename_monthly_calendar'], index_col=0)
    return cal

##########################################################

def province_to_region():
    """
    As the ARERA load profiles are region-based, this function returns the region of the selected municipality, based on the file "comuni_italiani.csv" table.
    Input must be the name of the province in English
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    italian_municipalities = pd.read_csv(config["filename_comuni_italiani"], encoding='unicode_escape')

    assert (italian_municipalities["Denominazione in italiano"] == config["provincia_it"]).any(), "Location not found in comuni_italiani.csv"

    region = italian_municipalities[italian_municipalities["Denominazione in italiano"] == config["provincia_it"]]["Denominazione Regione"].iloc[0]

    return region

def province_italian_to_english():
    """
    This function translates the province name from Italian to English, based on the file "comuni_italiani.csv" table.
    Input must be the name of the province in Italian. 
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    italian_municipalities = pd.read_csv(config["filename_comuni_italiani"], encoding='unicode_escape')

    assert (italian_municipalities["Denominazione in italiano"] == config["provincia_it"]).any(), "Location not found in comuni_italiani.csv"

    province = italian_municipalities[italian_municipalities["Denominazione in italiano"] == config["provincia_it"]]["Denominazione provincia in inglese"].iloc[0]

    return province

def location_italian_to_english(location_it):
    """
    This function translates the municipality name from Italian to English, based on the file "comuni_italiani.csv" table.
    Input must be the name of the municipality in Italian. 
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    italian_municipalities = pd.read_csv(config["filename_comuni_italiani"], encoding='unicode_escape')

    assert (italian_municipalities["Denominazione in italiano"] == location_it).any(), "Location not found in comuni_italiani.csv"

    location_en = italian_municipalities[italian_municipalities["Denominazione in italiano"] == location_it]["Denominazione provincia in inglese"].iloc[0]

    return location_en

##########################################################

def generate_users_yml(base=36):
    """From the filename_users_CACER_xls file, we do some checks and then generates the filename_registry_user_types_yml as dictionary, without nesting.
    We create at the same time registry_user_types.yml and registry_user.yml.
    Inputs: 
        base: the base of the user IDs. can be base=10 (then users ID will be u_009, u_010, ..., u_999) or base=36 (then users ID will be u_009, u_00A, u_00B, ... , u_ZZZ). We can have base^3 users
    """

    print(blue("\nGenerating registry_user_types.yml and registry_user.yml:\n"))

    config = yaml.safe_load(open("config.yml", 'r')) # opening file config
    filename_recap = config['filename_recap']

    app = xw.App(visible = False)
    wb = xw.Book(config['filename_users_CACER_xls']) # opening file users CACER and importing the data in a dataframe
    
    df = wb.sheets["Utenti"].range('A1').options(pd.DataFrame, 
                                                header=1,
                                                index=False, 
                                                expand='table').value
    
    wb.close() # closing file
    app.quit()

    df = df[df["flag"] == True] # dropping users not activated for the current simulation

    df["grant_pnrr"] = df["grant_pnrr"].fillna(0) # removing nan, which can generate erros in the incentives calculation

    # CHECKS on imported data
    # all user type IDs must be unique
    assert len(df.user_type.unique()) == len(df.user_type), "ERROR: some user_type share the same ID!"

    # checking if the names are too long for excel to handle as sheetnames (will trigger errors later on)
    names_length_flag = [len(name)>31 for name in df["user_type"]] 
    assert not True in names_length_flag, "ERROR: some user_types have names with >31 characters, which will trigger Excel errors! Please rename them with less digits"

    df.set_index("user_type", inplace=True) # setting user type ID as index
    df.drop(columns=["number_type_id"],inplace=True) # removing first column, not needed
    # replacing nan and null with 0 and setting correct format, to prevent future errors
    df.num = df.num.fillna(0).astype(int) 
    df.pv = df.pv.fillna(0).astype(int)
    df.battery = df.battery.fillna(0).astype(int)
    df.wind = df.wind.fillna(0).astype(int)
    df.dummy_user = df.dummy_user.fillna(False).astype(bool)

    # initializing variables
    users_count = 1 # initializing user count
    all_users_list = {} # initializing the list of users for file registry_user.yml
    all_users_list_CACER = {} # same as above but only with users actually participaring in the CACER    
    
    # Filling the info for the users
    for user_type in df.index: # loop on the user type (which is the user type ID)
        for number_of_user in range(int(df.num[user_type])): # loop on the number of user for the selected type
            user_count_base36 = np.base_repr(users_count, base=base, padding=3)[-3:] # assuming to have max (base)^3  users
            user_category_id = config["category_id"][df.loc[user_type, "category"]] # estracting the category_id from the list (Uppercase), to identify easily the type of connection (industriale, domestico, comune, etc.)
            
            # if consumer
            if df.loc[user_type, "type"] == "consumer": 
                user_category_id = user_category_id.lower() # by convention, we indicate the category_id with lower case in case the user is a consumer
            
            # if prosumer
            if df.loc[user_type,"type"] == "producer": 
                user_category_id == "X" # by convention, we indicate a producer (only grid-connected generator, no load present) with capital "X"
            
            user_id = "u_" + user_category_id + user_count_base36 # we generate the user ID for the selected user
            
            all_users_list[user_id] = {} # we create an empty dictionary of the new user id
            all_users_list[user_id] = df.loc[user_type, :].to_dict() # we copy into the dictionary the same parameters that we find in the file user CACER.xls
            all_users_list[user_id]["user_type"] = user_type # we add also the user type id in the parameters of the users
            
            if df.loc[user_type, "flag_cacer"] == True:
                all_users_list_CACER[user_id] = {} # we create an empty dictionary of the new user id
                all_users_list_CACER[user_id] = df.loc[user_type, :].to_dict() # we copy into the dictionary the same parameters that we find in the file user CACER.xls
                all_users_list_CACER[user_id]["user_type"] = user_type # we add also the user type id in the parameters of the users

            users_count += 1 # we count the number of users generated in way to check if this exceed the maximum number of users that can be generated in base 36
    
    assert users_count < base**3, "WARNING: the number of users exceeds the maximum achievable with 3 digits. Please increase the base representation" 
    print("Total users: ", users_count-1)

    # adding the seniority level to all the users, starting from 1 from the oldest (based on entry_month in the CACER)
    # In case of users with same entry_month, no difference will be made
    # create temporary dataframe to sort plants based on commissioning month and installed capacity
    df_temp = pd.DataFrame.from_dict(all_users_list).T.sort_values(['entry_month'], ascending=True).reset_index().rename(columns={"index":"user_id"})
    df_temp["seniority_level"] = df_temp.index + 1
    df_temp.set_index("user_id", inplace=True)

    for user in list(all_users_list.keys()):
        all_users_list[user]["seniority_level"] = int(df_temp.loc[user,"seniority_level"])

    #ora invece creiamo la lista di utenti per tipologia
    user_types_list = {}
    for user_type in df.index: # loop on the user type
        if not df.flag[user_type]: continue #se non è selezionato, lo saltiamo
        user_types_list[user_type] = {}
        user_types_list[user_type] = df.loc[user_type,:].to_dict()

    # inizializziamo il file recap.yml, cancellando i dati delle passate simulazioni
    recap = {}
    with open(filename_recap, 'w') as f:
        yaml.safe_dump(recap, f)

    # save a copy of the plants sorted by seniority level in the recap file
    seniority_level_users = list(df_temp.index)
    add_to_recap_yml("users_sorted_on_seniority", seniority_level_users)

    # identifyint type of configuration
    add_to_recap_yml("type_of_cacer", config["type_of_cacer"])

    #some statistics to check
    print(len(user_types_list.keys()), " CACER members types created")

    print("List of users in active configuration:")
    prosumers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "prosumer"])
    add_to_recap_yml("numero_prosumers", prosumers)
    print(prosumers, " prosumers")

    producers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "producer"])
    print(producers, " producers")
    add_to_recap_yml("numero_producers", producers)

    consumers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "consumer"])
    print(consumers, " consumers\n")
    add_to_recap_yml("numero_consumers", consumers)

    dummy_users = [user for user in user_types_list.keys() if user_types_list[user]["dummy_user"]]
    add_to_recap_yml("dummy_users", dummy_users)

    capacity_PV_list = []
    capacity_batt_list = []
    for user in user_types_list.keys():
        if user_types_list[user]["type"] == "consumer": continue
        for i in range(user_types_list[user]["num"]):
            if not pd.isna(user_types_list[user]["pv"]): capacity_PV_list.append(int(user_types_list[user]["pv"]))
            if not pd.isna(user_types_list[user]["battery"]): capacity_batt_list.append(int(user_types_list[user]["battery"]))

    print("PV capacity installed [kW]: ", capacity_PV_list)
    add_to_recap_yml("all_PV", capacity_PV_list)

    print("Battery capacity installed [kWh]: ", capacity_batt_list)
    add_to_recap_yml("all_storage", capacity_batt_list)

    add_to_recap_yml("list_prosumers", [user for user in all_users_list.keys() if all_users_list[user]["type"] == "prosumer"])
    add_to_recap_yml("list_producers", [user for user in all_users_list.keys() if all_users_list[user]["type"] == "producer"])
    add_to_recap_yml("list_consumers", [user for user in all_users_list.keys() if all_users_list[user]["type"] == "consumer"])

    add_to_recap_yml("list_prosumers_CACER", [user for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "prosumer"])
    add_to_recap_yml("list_producers_CACER", [user for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "producer"])
    add_to_recap_yml("list_consumers_CACER", [user for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "consumer"])
    
    # list(set( )) removes the duplicates from a list
    add_to_recap_yml("list_types_prosumers", list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "prosumer"])))
    add_to_recap_yml("list_types_producers", list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "producer"])))
    add_to_recap_yml("list_types_consumers", list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "consumer"])))

    add_to_recap_yml("list_types_prosumers_CACER", list(set([all_users_list_CACER[user]["user_type"] for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "prosumer"])))
    add_to_recap_yml("list_types_producers_CACER", list(set([all_users_list_CACER[user]["user_type"] for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "producer"])))
    add_to_recap_yml("list_types_consumers_CACER", list(set([all_users_list_CACER[user]["user_type"] for user in all_users_list_CACER.keys() if all_users_list_CACER[user]["type"] == "consumer"])))

    add_to_recap_yml("list_user_types", list(set([all_users_list[user]["user_type"] for user in all_users_list.keys()])))
    add_to_recap_yml("all_users", list(all_users_list.keys()))

    add_to_recap_yml("list_user_types_CACER", list(set([all_users_list_CACER[user]["user_type"] for user in all_users_list_CACER.keys()])))
    add_to_recap_yml("all_users_CACER", list(all_users_list_CACER.keys()))

    add_to_recap_yml("configurations", list(set([all_users_list_CACER[user]["CP"] for user in all_users_list_CACER.keys()])))
    add_to_recap_yml("stakeholders", list(set([all_users_list_CACER[user]["stakeholder"] for user in all_users_list_CACER.keys() if not pd.isnull(all_users_list_CACER[user]["stakeholder"])] )))

    add_to_recap_yml("PV_tot", sum(capacity_PV_list))
    add_to_recap_yml("batt_tot", sum(capacity_batt_list))

    add_to_recap_yml("total_CACER_members", len(all_users_list_CACER.keys()))
    add_to_recap_yml("total_non_dummy_CACER_members", len([user for user in all_users_list_CACER.keys() if not all_users_list_CACER[user]["dummy_user"]]))
    
    if capacity_PV_list != []:
        add_to_recap_yml("PV_max", max(capacity_PV_list))
        add_to_recap_yml("PV_min", min(capacity_PV_list))
    else:
        add_to_recap_yml("PV_max", 0)
        add_to_recap_yml("PV_min", 0)

    if capacity_batt_list != []:
        add_to_recap_yml("batt_max", max(capacity_batt_list))
        add_to_recap_yml("batt_min", min(capacity_batt_list))
    else: 
        add_to_recap_yml("batt_max", 0)
        add_to_recap_yml("batt_min", 0)

    add_to_recap_yml("total_CACER_users", len(all_users_list_CACER.keys()))
    add_to_recap_yml("total_grid_users", len(all_users_list.keys()))

    #saving yml
    with open(config['filename_registry_user_types_yml'], "w") as f:
        yaml.safe_dump(user_types_list, f)

    with open(config["filename_registry_users_yml"], "w") as f:
        yaml.safe_dump(all_users_list, f)
    
    #saving as csv
    pd.DataFrame.from_dict(all_users_list).T.to_csv(config["filename_registry_users_csv"])

    print("\n**** Registry users completed! ****")

##########################################################

def generate_plant_yml():
    """from the excel file, generates the yml as dictionary, without nesting"""

    print(blue("\nGenerating plant yml:"))

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config['filename_recap'], 'r'))
    users = yaml.safe_load(open(config['filename_registry_users_yml'], 'r'))

    plant_registry = {}
    for user in recap["list_prosumers"] + recap["list_producers"]: # loop over users with generation plant
        plant = user.replace("u_","p_") # assigning the plant name, replacing "u" of "user" with "p" of "plant"

        plant_registry[plant] = users[user]

        plant_registry[plant]["titolare_POD"] = user
        plant_registry[plant]["installed_capacity"] = plant_registry[plant]["pv"] + plant_registry[plant]["wind"]

        if pd.isna(plant_registry[plant]["grant_pnrr"]):
            plant_registry[plant]["grant_pnrr"] = 0

        if pd.isna(plant_registry[plant]["grant_private"]):
            plant_registry[plant]["grant_private"] = 0
        
        if pd.isna(plant_registry[plant]["debt"]):
            plant_registry[plant]["debt"] = 0

        # introducing a stop on the disbursement month, as if not correctly given generates errors in the plant_operation_matrix
        assert not (np.isnan(plant_registry[plant]["disbursement_month"]) or plant_registry[plant]["disbursement_month"] == 0), f"ERROR: disbursement_month given for {plant_registry[plant]['user_type']} is NAN or 0. Provide a value >0 in the users CACER file"

    # adding the seniority level to all the plants, starting from 1 from the oldest (based on commissioning date), needed by the GSE to calculate the energy generated by which plant and thus calculate the incentive.
    # In case of plants with same commissioning date, the one with lower installed capacity will have the priority (so to simulate the maximize the incentives)
    # create temporary dataframe to sort plants based on commissioning month and installed capacity
    df_plant = pd.DataFrame.from_dict(plant_registry).T.sort_values(['commissioning_month', 'installed_capacity'], ascending=[True, True]).reset_index().rename(columns={"index":"plant_id"})
    df_plant["seniority_level"] = df_plant.index + 1
    df_plant.set_index("plant_id", inplace=True)

    for plant in list(plant_registry.keys()):
        plant_registry[plant]["seniority_level"] = int(df_plant.loc[plant,"seniority_level"])

    # save a copy of the plants sorted by seniority level in the recap file
    seniority_level_plants = list(df_plant.index)
    add_to_recap_yml("plants_sorted_by_seniority", seniority_level_plants)

    #saving as yml
    with open(config["filename_registry_plants_yml"], "w") as f:
        yaml.safe_dump(plant_registry, f)
    
    #saving as csv
    df_plant.to_csv(config["filename_registry_plants_csv"])

    print("\n**** Registry plants completed! ****")

##########################################################

def check_file_status(filename):
    """Before running time-consuming functions, juct check that the output file is not being used by other applications, to avoid Permission Denied error at the end of the run"""
    try: open(filename, "w")
    except: 
        print("ERROR: " + filename + " file is open! Close it and rerun!")
        sys.exit()

##########################################################

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
    new_fake_datapoint = pd.DataFrame(load_user_pivot[-1:].values, index=load_user_pivot.index[-1:] + datetime.timedelta(hours=1), columns=load_user_pivot.columns)
    # load_user_pivot = load_user_pivot.append(new_fake_datapoint)
    load_user_pivot = pd.concat((load_user_pivot, new_fake_datapoint), axis = 0)
    resampled_df = load_user_pivot.resample('15min', offset="1H", closed='left').mean().ffill() / 4 #resampling from 1hr to 15 min, and dividing the energy by 4
    resampled_df = resampled_df[:-1] # removing the last row which was needed as resampling boundary
    resampled_df.reset_index(inplace=True)
    resampled_df.Hour = resampled_df.Hour.dt.time
    pd.options.mode.chained_assignment = "warn"  # default='warn', disabled= None
    return resampled_df

##########################################################

def load_profile_single_user(df, user):
    """gnerating the load profile for a single user.
    Inputs:
        df                  calendar dataframe with all the needed columns, and previous load profiles from other users
        user                user_id, same user id that we have in registry_users.keys()
    Outputs: 
        output_all_users    list with user profiles, updated with new one just computed
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    user_types_set = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r')) # file yaml con i parametri delle varie categorie di utenza
    load_profile_id = user_types_set[user]["load_profile_id"] # extract load profile id from registry_user_types.yml
    power_range = user_types_set[user]["power_range"] # extract power range from registry_user_types.yml

    # CASE 1 - arera load profile
    if load_profile_id == "arera":
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
        load_user = real_profile_df[user] # real profile for Riccomassimo CER
        load_user = pd.DataFrame(load_user)

    # CASE 3 - emulated load profile
    elif load_profile_id == "emulated profile":
        load_user = emulated_load_profile_df[user] # emulated load profile for Riccomassimo CER
        load_user = pd.DataFrame(load_user)

    # CASE 4 - other load profiles
    else: # when we have our profiles given as input
        load_user = wb.sheets[load_profile_id].range('A1').options(pd.DataFrame, header=1, index=True, expand='table').value
        load_user["Hour"] = pd.date_range("00:00", "23:45", freq = "15min").time # ATTENZIONE, avevo problemi a importare correttamente il formato del time della colonna HOUR, quindi per semplicita ne ho creato uno nuovo, assumendo che tanto va da 00:00 a 23:45
        load_user.set_index("Hour", inplace = True)

    # If not real profile and not emulated profile and rand_factor is different by 0, we just consider updating_random_variation_flag = True! 
    # So the random variation is considered in arera profile cases and other profiles cases!
    updating_random_variation_flag = rand_factor != 0 and load_profile_id != "real profile" and load_profile_id != "emulated profile"

    # If not arera profile and not real profile and not emulated profile, we just define a week_factor variation imported from external file! 
    if load_profile_id != "arera" and load_profile_id != "real profile" and load_profile_id != "emulated profile":
        week_factor = wb.sheets[load_profile_id].range('P1').options(pd.DataFrame, header=1, index=True, expand='table').value#.to_dict()

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
        year_factor_stack = year_factor["yearly_correction"]
        df = pd.merge(df, year_factor_stack, on=["year"], how='inner').sort_values("datetime").reset_index(drop=True)

    else:
        df["weekly_correction"] = 1
        df["yearly_correction"] = 1

    # CALCULATION
    # we calculate the energy consumption for the specific datapoint
    df["load_active_adjusted"] = df["load_active"] * df["weekly_correction"] * df["yearly_correction"] * (1 + df["random_variation"])

    print("user created: ", blue(user), "\t\t user type: ", load_profile_id )

    return df.set_index("datetime")["load_active_adjusted"] #returning the load adjusted with the datetime as the unique index, same format of the df_results

##########################################################

def load_profile_all_users():
    
    """
    Loop over all user types, to create the 15min or 1H load profiles.
    Exports:

    """

    print(blue("\nGenerate load profile for user types added:", ['bold', 'underlined']), '\n')

    global xls, month_factor, year_factor, user_load_arera, region, delta_t, wb, output_all_users, rand_factor, real_profile_df, emulated_load_profile_df

    ########### INPUTS ##############

    config = yaml.safe_load(open("config.yml", 'r'))
    filename_user_load_arera = config['filename_user_load_arera']
    filename_carico_input = config["filename_carico_input"]
    filename_registry_user_types_yml = config["filename_registry_user_types_yml"]

    check_file_status(config["filename_carichi"]) # check if "carichi.xlsx" file is being used by other apps. If not, it'd crash at the very end of the run
    region = province_to_region() # region of Italy
    rand_factor = config['rand_factor'] # random factor for peak fluctuation
    print("Random factor: " + str(rand_factor) + " %")
    delta_t = config['delta_t'] 

    user_types_set = yaml.safe_load(open(filename_registry_user_types_yml, 'r')) # file yaml with user type data
    users_consuming_energy = [user for user in user_types_set.keys() if user_types_set[user]["consuming"]] # we extract the list of user type of which consuming is true, excluding the prosumers which don't have load profile
    load_profiles_list = [user_types_set[user]["load_profile_id"] for user in users_consuming_energy] # we extract the load profile list of user type to simulate (the values can be arera, real profile, emulated profile, etc.)

    print(len(users_consuming_energy), "user types consuming found")

    df = get_calendar() # importing the calendar
    df.drop(columns=["fascia"], inplace=True)

    # generating columns needed for calculation  
    df["hour"] = df["datetime"].dt.time # create hour column
    df["week"] = df["datetime"].dt.isocalendar().week # create week column
    df["month"] = df["datetime"].dt.month # create month column
    df["year"] = df["datetime"].dt.year # create year column

    # import load profile arera
    if "arera" in load_profiles_list:
        user_load_arera = pd.read_csv(filename_user_load_arera) # si importano i profili di consumo arera

        user_load_arera["Hour"] = pd.to_datetime(user_load_arera.Ora, format="%H").dt.time # create the Hour column in the arera df with the correct format
        
        # replace day type with the correct format
        vals_to_replace = {"Giorno feriale": "Working_day", "Sabato": "Saturday", "Domenica": "Sunday"} 
        user_load_arera["Working day"] = user_load_arera["Working day"].map(vals_to_replace) 

    # import real load profile
    if "real profile" in load_profiles_list:
        filename = config["filename_load"]
        real_profile_df = pd.read_csv(filename, index_col = 'datetime')

        first_year = config['start_date'].year
        num_years = config['project_lifetime_yrs']

        if num_years == 1:
            real_profile_df.index = pd.to_datetime(real_profile_df.index)
            real_profile_df = real_profile_df[real_profile_df.index.year == first_year]

    # import emulated load profile
    if "emulated profile" in load_profiles_list:
        filename = config["filename_emulated_load_profile"]
        emulated_load_profile_df = pd.read_csv(filename, index_col = 'datetime')

    # import other load profiles
    app = xw.App(visible = False)
    wb = xw.Book(filename_carico_input)

    year_factor = wb.sheets['Yearly_Variation'].range('A1').options(pd.DataFrame, header=1, index=True, expand='table').value

    # check on load profile name, to make sure they are all given
    for user in users_consuming_energy:
        load_profile_id = user_types_set[user]["load_profile_id"]
        if load_profile_id in ["arera", "real profile", "emulated profile", None]: 
            continue
        else:
            # if profile does not come from any of the above sources, it must come from the input file, meaning the load_profile_id must be in one of the document's sheets
            sheets = [sheet.name for sheet in wb.sheets] 
            # If not present, then error must be triggered
            assert load_profile_id in sheets, print("ATTENTION: the", load_profile_id, "load profile given as input was not found!")

    #Start the loop over the consuming user types

    # initializing the results datafame, as copy of df (calendar imported) but with "datetime" as index
    df_results = df.copy(deep=True)
    df_results = df_results.set_index("datetime")

    for user in users_consuming_energy: # loop on user types

        # we generate the load profile of the selected user type for all the timestep over the project lifetime and append it in the output_all_users
        df_results[user] = load_profile_single_user(df, user)
        assert not df_results[user].isna().any(), "ERROR: Indexing failure! NaN found in " + user

    wb.close()
    app.quit()

    # #################### EXIT ################
    df_results.drop(columns=["hour", "week", "month", "year", "holiday", "day_week", "day_flag"]).to_csv(config["filename_carichi"])

    print("\n**** Load profiles successfully exported! ****")

###############################################################################################################################

def check_folder_exists(folder_path):
    """check if a folder exists. If not, it creates it. It is needed before running the time-consuming functions to verify the output folder actually exists"""
    if not os.path.isdir(folder_path):
        os.makedirs(folder_path)

###############################################################################################################################

def clear_folder_content(folder_directory):
    """removing all content in a folder"""
    files = glob.glob(folder_directory+'*')
    for f in files:
        os.remove(f) #deleting all files
    print("All files in " + folder_directory + " folder deleted")

###############################################################################################################################

def add_to_recap_yml(key, value):
    """saving some value under a given key in the recap.yml dictionary. Needed for reporting and recap purposes"""
    config = yaml.safe_load(open("config.yml", 'r'))
    filename_recap = config['filename_recap']
    
    recap = yaml.safe_load(open(filename_recap, 'r'))
    
    recap[key] = value

    with open(filename_recap, 'w') as f:
        yaml.safe_dump(recap, f)

def update_irr_on_recap_yml(user,irr_value):
    """saving some irr_value under a given user in the recap.yml dictionary. Needed for reporting and recap purposes"""
    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config['filename_recap'], 'r'))

    if "irr" not in recap.keys(): recap["irr"] = None
    
    recap["irr"][user] = irr_value
    
    with open(config['filename_recap'], 'w') as f:
        yaml.safe_dump(recap, f)

################################################################################################################################
# UNNEEDED
# def add_to_config_yml(key,value):
#     #dati utili per report
#     config = yaml.safe_load(open("config.yml", 'r'))
    
#     # modifichiamo quello che ci serve
#     config[key] = value

#     # salviamo
#     with open("config.yml", 'w') as f:
#         yaml.safe_dump(config, f)

###############################################################################################################################
# UNNEEDED
# def add_to_file_yml(path, filename, key, value):
       
#     #importiamo
#     diz = yaml.safe_load(open(path + filename, 'r'))
    
#     # modifichiamo quello che ci serve
#     diz[key] = value

#     # salviamo
#     with open(path + filename, 'w') as f:
#         yaml.safe_dump(diz, f)

###############################################################################################################################

def add_to_file_yml(path, filename, key, value):
    yaml = YAML()
    yaml.preserve_quotes = True

    # Read the YAML file
    with open(path, 'r', encoding='utf-8') as file:
        data = yaml.load(file)

    # Ensure the structure exists
    if filename:
        if filename not in data:
            data[filename] = {}
        data[filename][key] = value
    else:
        data[key] = value

    # Write back to the file without losing comments
    with open(path, 'w', encoding='utf-8') as file:
        yaml.dump(data, file)

##########################################################

def edit_file_yml_preserving_comments(file_path, key, value): 
    """
    Edit a YAML file, preserving comments.
    Inputs:
        file_path: path to the YAML file to edit
        key: key to be modified
        value: new value for the key
    """
    yaml = YAML()
    
    # Read the file and preserve comments
    with open(file_path, 'r') as file:
        data = yaml.load(file)
    
    # Modify the data as needed
    data[key] = value
    
    # Write back to the file, keeping comments
    with open(file_path, 'w') as file:
        yaml.dump(data, file)

################################################################################################################################

def edit_users_CACER(variable, user_type, value):
    """editing the users_CACER excel file, directly on the file
    WARNING: this function, if used in large for loops, can become very slow. Sometimes leaves some background activity that slows down the laptop (check Task Manager) and a restart could be recommended.
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_users_CACER_xls"])
    num_rows = len(wb.sheets["Utenti"]["A1"].options(pd.Series, header=1, index=True, expand='table').value)

    col = 1
    while col < 100: # modificare se dovessimo avere piu di 100 colonne
        if wb.sheets["Utenti"].range((1,col)).value == variable: break
        else: col += 1

    # looking for user_type column (position might change over time)
    col_user_type = 1
    while col_user_type < 100: # edit in case we exceed the 100 columns
        if wb.sheets["Utenti"].range((1,col_user_type)).value == "user_type": break
        else: col_user_type += 1

    row = 1
    while row < num_rows+2: 
        if wb.sheets["Utenti"].range((row,col_user_type)).value == user_type: break
        else: row += 1

    # print("The Row is: "+str(row)+" and the column is "+str(col))
    wb.sheets["Utenti"].range((row,col)).value = value

    wb.save()
    wb.close()
    app.quit()

################################################################################################################################
def clear_users_utenti_CACER():
    """resets the num column in the filename_users_CACER_xls to a series of nan. Could be needed f.i. when performing a sensitivity analysis on CACER members numerosity, or when activating or removing some specific users"""

    config = yaml.safe_load(open("config.yml", 'r'))
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_users_CACER_xls"])
    num_rows = len(wb.sheets["Utenti"]["A1"].options(pd.Series, header=1, index=True, expand='table').value)

    # looking for num column (position might change over time)
    col_num = 1
    while col_num < 100: # edit in case we exceed the 100 columns
        if wb.sheets["Utenti"].range((1,col_num)).value == "num": break
        else: col_num += 1

    row = 2
    while row < num_rows+2: # modificare se dovessimo avere piu di 100 righe
        wb.sheets["Utenti"].range((row,col_num)).clear_contents()
        row += 1

    wb.save()
    wb.close()
    app.quit()

def edit_incentive_repartition_scheme(value):
    """edits the incentive repartition scheme in the "Scenario" sheet in the filename_input_FM_excel. It is sometimes needed when comparing different repartition schemes"""

    config = yaml.safe_load(open("config.yml", 'r'))
    
    ###### WARNING: the use of xw.App can cause issues if the file is already opened... To be fixed ########################
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    wb.sheets["Scenario"].range("incentives_repartition_scheme").value = value

    wb.save()
    wb.close()
    app.quit()

def edit_opex_repartition_scheme(value):
    """edits the OPEX repartition scheme in the "Scenario" sheet in the filename_input_FM_excel. It is sometimes needed when comparing different repartition schemes"""

    config = yaml.safe_load(open("config.yml", 'r'))
    
    ###### WARNING: the use of xw.App can cause issues if the file is already opened... To be fixed ########################
    # app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    wb.sheets["Scenario"].range("opex_repartition_scheme").value = value

    wb.save()
    # wb.close()
    # app.quit()

def edit_surplus_repartition_scheme(value):
    """edits the SURPLUS repartition scheme in the "Scenario" sheet in the filename_input_FM_excel. It is sometimes needed when comparing different repartition schemes"""

    config = yaml.safe_load(open("config.yml", 'r'))
    
    ###### WARNING: the use of xw.App can cause issues if the file is already opened... To be fixed ########################
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    wb.sheets["Scenario"].range("surplus_repartition_scheme").value = value

    wb.save()
    wb.close()
    app.quit()

# UNNEEDED
# def duplicate_and_rename_folder(source_folder_path, new_folder_path):
#     # Get parent and child directories
#     parent_dir = os.path.dirname(source_folder_path)

#     # Create the new directory
#     # new_folder_path = os.path.join(parent_dir, child_dir)
#     os.makedirs(new_folder_path, exist_ok=True)

#     # Copy all the files and directories from the old folder to the new one
#     for root, dirs, files in os.walk(source_folder_path):
#         for file in files:
#             src_file_path = os.path.join(root, file)
#             dst_file_path = os.path.join(new_folder_path, file)
#             shutil.copy2(src_file_path, dst_file_path)
#     print(source_folder_path + " folder successfully duplicated as " + new_folder_path)



################################################################################################################################

# DA SISTEMARE!!!
# # UNNEEDED
# def aggiungi_nuovi_utenti_yml(base=36):
#     """from the excel file, generates the yml as dictionary, without nesting.
#     We create at the same time registry_user_types.yml and registry_user.yml.
#     """

#     config = yaml.safe_load(open("config.yml", 'r'))
#     filename_users_CACER_xls = config['filename_users_CACER_xls'] # si importa il nome del file .xls contenente gli utenti da simulare (tutte le tipologie di utenza!)
#     filename_registry_user_types_yml = config['filename_registry_user_types_yml'] # si importa il file yaml in cui si salveranno le caratteristiche delle varie tipologie di utenza
#     filename_recap = config['filename_recap'] # si importa il file recap

#     #########################################################################

#     # si apre il file excel e si importa il foglio "utenti" in un df
#     # app = xw.App(visible = False)
#     wb = xw.Book(filename_users_CACER_xls)
#     df = wb.sheets["Utenti"].range('A1').options(pd.DataFrame, 
#                                                 header=1,
#                                                 index=False, 
#                                                 expand='table').value
    
#     wb.close() # si chiude il file excel
#     # app.quit()

#     #########################################################################

#     assert len(df.user_type.unique()) == len(df.user_type), "some user_type share the same ID!" # si verifica che lo user ID sia unico per ogni utente
    
#     #########################################################################

#     df.set_index("user_type", inplace=True) # si setta lo user ID come index
#     df.drop(columns=["number_type_id"],inplace=True) # si elimina la prima colonna
#     df.num = df.num.fillna(0).astype(int) # si annulla la numerosità di tutti gli utenti

#     #########################################################################
    
#     # creiamo la lista di utenti della configurazione in esame che useremo per creare il file registry_user_yml
#     users_count = 0 # salviamo il numero di utenti
#     all_users_list = {} # creiamo la lista di utenti per nome che servirà per creare il file refistry_user.yml
    
#     for user_type in df.index: # loop on the user type (ID)
#         for number_of_user in range(int(df.num[user_type])): # loop on the number of user for the selected type
#             user_count_base36 = np.base_repr(users_count, base=base, padding=3)[-3:] # assuming to have max (36)^3 =  users
#             user_category_id = config["category_id"][df.loc[user_type, "category"]] # estracting the category_id from the list (Uppercase), to identify easily the type of connection (industriale, domestico, comune, etc.)
            
#             # if consumer
#             if df.loc[user_type, "type"] == "consumer": 
#                 user_category_id = user_category_id.lower() # by convention, we indicate the category_id with lower case in case the user is a consumer
            
#             # if prosumer
#             if df.loc[user_type,"type"] == "producer": 
#                 user_category_id == "X" # by convention, we indicate a producer (only grid-connected generator, no load present) with capital "X"
            
#             user_id = "u_" + user_category_id + user_count_base36 # we generate the user id for the selected user
            
#             all_users_list[user_id] = {} # we create an empty dictionary of the new user id
#             all_users_list[user_id] = df.loc[user_type, :].to_dict() # we copy into the dictionary the same parameters that we find in the file user CACER.xls
#             all_users_list[user_id]["user_type"] = user_type # we add also the user type id in the parameters of the users
            
#             users_count += 1 # we count the number of users generated in way to check if this exceed the maximum number of users that can be generated in base 36
    
#     assert users_count < base**3, "WARNING: the number of users exceeds the maximum achievable with 3 digits. Please increase the base representation" 
#     print("Total users: ", users_count)

#     #########################################################################

#     # creiamo la lista di user_types_list per tipologia che useremo per creare il file registry_user_types.yml
#     user_types_list = {}
#     for user_type in df.index: # loop on the user type
#         if not df.flag[user_type]: continue #se non è selezionato, lo saltiamo
#         user_types_list[user_type] = {}
#         user_types_list[user_type] = df.loc[user_type,:].to_dict()

#     #########################################################################

#     # saving yml with data of user types
#     with open(filename_registry_user_types_yml, "w") as f:
#         yaml.safe_dump(user_types_list, f)

#     #saving yml with data of configuration users
#     with open(config["filename_utenze_users_yml"], "w") as f:
#         yaml.safe_dump(all_users_list, f)

#     #########################################################################

#     # si popola il file recap con varie statistiche

#     recap = {} # inizializziamo il file recap.yml, cancellando i dati delle passate simulazioni

#     # ripuliamo il file recap al fine di ripopolarlo nuovamente
#     with open(filename_recap, 'w') as f:
#         yaml.safe_dump(recap, f)

#     print(len(user_types_list.keys()), " CER members types created")

#     print("List of users in active configuration:")
#     prosumers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "prosumer"])
#     add_to_recap_yml("numero_prosumers",prosumers)
#     print(prosumers, " prosumers")

#     producers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "producer"])
#     print(producers, " producers")
#     add_to_recap_yml("numero_producers",producers)

#     consumers = sum([user_types_list[user]["num"] for user in user_types_list.keys() if user_types_list[user]["type"] == "consumer"])
#     print(consumers, " consumers")
#     add_to_recap_yml("numero_consumers",consumers)

#     #########################################################################

#     capacity_PV_list = []
#     capacity_batt_list = []
#     for user in user_types_list.keys():
#         if user_types_list[user]["type"] == "consumer": continue
#         for i in range(user_types_list[user]["num"]):
#             if not pd.isna(user_types_list[user]["pv"]): capacity_PV_list.append(int(user_types_list[user]["pv"]))
#             if not pd.isna(user_types_list[user]["battery"]): capacity_batt_list.append(int(user_types_list[user]["battery"]))

#     print("PV capacity installed [kW]: ", capacity_PV_list)
#     add_to_recap_yml("all_PV", capacity_PV_list)

#     print("Battery capacity installed [kWh]: ", capacity_batt_list)
#     add_to_recap_yml("all_storage", capacity_batt_list)

#     #########################################################################

#     add_to_recap_yml("list_prosumers",[user for user in all_users_list.keys() if all_users_list[user]["type"] == "prosumer"])
#     add_to_recap_yml("list_producers",[user for user in all_users_list.keys() if all_users_list[user]["type"] == "producer"])
#     add_to_recap_yml("list_consumers",[user for user in all_users_list.keys() if all_users_list[user]["type"] == "consumer"])

#     #########################################################################
    
#     # list(set( )) serve per rimuovere i doppioni dalla lista
#     add_to_recap_yml("list_types_prosumers",list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "prosumer"])))
#     add_to_recap_yml("list_types_producers",list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "producer"])))
#     add_to_recap_yml("list_types_consumers",list(set([all_users_list[user]["user_type"] for user in all_users_list.keys() if all_users_list[user]["type"] == "consumer"])))

#     add_to_recap_yml("list_user_types", list(set([all_users_list[user]["user_type"] for user in all_users_list.keys()])))
#     add_to_recap_yml("all_users", list(all_users_list.keys()))

#     add_to_recap_yml("PV_tot", sum(capacity_PV_list))
#     add_to_recap_yml("batt_tot", sum(capacity_batt_list))
#     add_to_recap_yml("PV_max", max(capacity_PV_list))
#     add_to_recap_yml("PV_min", min(capacity_PV_list))

#     if capacity_batt_list != []:
#         add_to_recap_yml("batt_max", max(capacity_batt_list))
#         add_to_recap_yml("batt_min", min(capacity_batt_list))
#     else: 
#         add_to_recap_yml("batt_max", 0)
#         add_to_recap_yml("batt_min", 0)
        
#     add_to_recap_yml("total_CACER_members", len(all_users_list.keys()))

#     print("Export complete")

################################################################################################################################



def plant_operation_matrix():
    """Generating the plant activity matrix, which reports the activity or inactivity for each plant in the CACER in each month time for the project lifetime, as 1 or 0.
    It is needed to check whether the plant is operational and generating energy for the community, incentives and opex.
    If the plant exits the CACER, then it will be considered inactive for the purpose of generating value for the CACER, thus 0 from the exit month.
    IMPORTANT: plant being operational means it produces power, not necessarily it generates shared energy and thus incentives (can be active even after expiring of incentivation contract of 20 yrs). 
    Each cash flow will be evaluated separately in each dedicated function
    df has plants on index and month_number on columns"""

    print(blue("\nGenerating plant operation matrix:"))

    config = yaml.safe_load(open("config.yml", 'r'))
    user_type_set = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    user_types_producing = [user_type for user_type in user_type_set if user_type_set[user_type]["producing"]]

    plants_set = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    
    writer = pd.ExcelWriter(config["filename_plant_operation_matrix"], engine = 'xlsxwriter')

    df = get_monthly_calendar().set_index("month_number")

    for user_type in user_types_producing:

        commissioning_month = user_type_set[user_type]["commissioning_month"]
        exit_month = user_type_set[user_type]["exit_month"]

        if exit_month == "end":
            exit_month = df.index[-1] + 1

        df[user_type] = [1*((month >= commissioning_month) and (month < exit_month)) for month in df.index ] # for each month, 1 meaning plant is operative (thus opex is applicable); 0 means not operative

    df.T.to_excel(writer, sheet_name= "plant_type_operation_matrix") #saving for the record

    df = get_monthly_calendar().set_index("month_number")

    for plant in plants_set:

        commissioning_month = plants_set[plant]["commissioning_month"]
        exit_month = plants_set[plant]["exit_month"]

        if exit_month == "end":
            exit_month = df.index[-1] + 1

        df[plant] = [1*((month >= commissioning_month) and (month < exit_month)) for month in df.index ] # for each month, 1 meaning plant is operative (thus opex is applicable); 0 means not operative

    df.T.to_excel(writer, sheet_name= "plant_operation_matrix") #saving for the record

    writer.close()

    print("\n**** Plant Operation Matrix created! ****")

################################################################################################################################

def membership_matrix():
    """generating the membership matrix, which reports the precence or absense for each user in the CACER in each month time for the project lifetime, as 1 or 0.
    It is needed to compute several cashflows (such as incentives repartition) and energy flows (such shared energy)
    Generating also the entry month recording, to facilitate the entry fee calculation and user entries statistics"""

    print(blue("\nGenerating Membership Matrix:"))

    config = yaml.safe_load(open("config.yml", 'r'))
    users_set = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

    df_membership = get_monthly_calendar().set_index("month_number") 
    df_entry = get_monthly_calendar().set_index("month_number")

    for user in users_set:

        entry_month = users_set[user]["entry_month"]
        exit_month = users_set[user]["exit_month"]

        if exit_month == "end":
            exit_month = df_membership.index[-1] + 1
        
        df_entry[user] = 0
        df_entry.loc[entry_month,user] = 1

        df_membership[user] = [1*((month >= entry_month) and (month < exit_month)) for month in df_membership.index ] # for each month, 1 meaning plant is operative (thus opex is applicable); 0 means not operative

    df_membership.T.to_csv(config["filename_membership_matrix"])
    df_entry.T.to_csv(config["filename_user_entry_matrix"])

    # getting which users are present in month 1, to bear the constitution costs
    df_t = df_membership.T
    users_present_month_1 = list(df_t[df_t[1] == 1].index)
    add_to_recap_yml("users_present_month_1", users_present_month_1)

    print("\n **** Membership Matrix created! ****")

################################################################################################################################

#

# we add to "user CACER.xlsx" file all parameter for CER and noCER users that are listed in config["filename_data"] file
# def modify_user_CACER_xlsx():

#     global num_rows_cacer_file_bkp # we save this parameter in way to restore the "user CACER.xlsx" file after the creation of all yaml files
    
#     config = yaml.safe_load(open("config.yml", 'r'))
#     filename_users_CACER_xls = config['filename_users_CACER_xls'] # si importa il nome del file .xls contenente gli utenti da simulare (tutte le tipologie di utenza!)

#     # si apre il file excel e si importa il foglio "utenti" in un df
#     # app = xw.App(visible = False)
#     wb = xw.Book(filename_users_CACER_xls)
#     user_CACER_df = wb.sheets["Utenti"].range('A1').options(pd.DataFrame, 
#                                                 header=1,
#                                                 index=False, 
#                                                 expand='table').value

#     num_rows_cacer_file = len(user_CACER_df.index)  
#     num_rows_cacer_file_bkp = num_rows_cacer_file # we save this parameter in way to restore the "user CACER.xlsx" file after the creation of all yaml files

#     wb.sheets["Utenti"].range("B2:B" + str(num_rows_cacer_file + 1)).clear_contents() # clearing contents for the column "flag", we considered the real number of rows
#     wb.sheets["Utenti"].range("D2:D" + str(num_rows_cacer_file + 1)).clear_contents() # clearing contents for the column "num", we considered the real number of rows

#     #######################################################################################################################################################################

#     filename = config["filename_data"]
#     load_df = pd.read_excel(filename, sheet_name="load")
#     n = load_df.columns.get_loc('flag')
#     load_df = load_df.iloc[:, n:]

#     num_rows = len(load_df.index) # number of load to import inside the "user CACER.xlsx" file

#     range = "A" + str(num_rows_cacer_file + 2) + ":A" + str(num_rows_cacer_file + 1 + num_rows) # define range for pasting formula
#     formula = wb.sheets["Utenti"].range("A2").formula # copy formula to paste
#     wb.sheets["Utenti"].range(range).formula = formula # paste in the first column the formula to estimate the id number of user inside "user CACER.xlsx" file

#     range = "B" + str(num_rows_cacer_file + 2) # define range to paste load parameters
#     wb.sheets["Utenti"][range].options(pd.DataFrame, header=0, index=False, expand='table').value = load_df # paste load parameters

#     wb.save()
#     wb.close()
#     app.quit()

#     print("All users added to user CACER xlsx file!")

################################################################################################################################

# 

# def restore_user_CACER_xlsx():
#     config = yaml.safe_load(open("config.yml", 'r'))
#     filename_users_CACER_xls = config['filename_users_CACER_xls'] # si importa il nome del file .xls contenente gli utenti da simulare (tutte le tipologie di utenza!)

#     # si apre il file excel e si importa il foglio "utenti" in un df
#     app = xw.App(visible = False)
#     wb = xw.Book(filename_users_CACER_xls)
#     user_CACER_df = wb.sheets["Utenti"].range('A1').options(pd.DataFrame, 
#                                                         header=1,
#                                                         index=False, 
#                                                         expand='table').value
    
#     num_rows = len(user_CACER_df)
    
#     range = str(num_rows_cacer_file_bkp + 2) + ":" + str(num_rows + 1) # define range of values to clean
#     wb.sheets["Utenti"].range(range).api.Delete(DeleteShiftDirection.xlShiftUp) # clean values in excel file

#     wb.save()
#     wb.close()
#     app.quit()

#     print("User CACER xlsx file restored!")

################################################################################################################################

def copy_folder_content(source_folder, destination_folder):
    """copy and paste of folder content from source_folder to destination_folder"""
    
    # create the destination folder if it doesn't exist
    os.makedirs(destination_folder, exist_ok=True)

    # check if the source folder is a file or a folder
    if os.path.isfile(source_folder):
        # copy the file to the destination folder
        destination_path = os.path.join(destination_folder, os.path.basename(source_folder))
        shutil.copy2(source_folder, destination_path)
    elif os.path.isdir(source_folder):
        # iterate over the files and subfolders in the source folder
        for filename in os.listdir(source_folder):
            # get the full path of the file
            source_path = os.path.join(source_folder, filename)
            destination_path = os.path.join(destination_folder, filename)

            # check if it's a file or a directory
            if os.path.isfile(source_path):
                # copy the file to the destination folder
                shutil.copy2(source_path, destination_path)
            elif os.path.isdir(source_path):
                # recursively copy the subfolder
                copy_folder_content(source_path, destination_path)

def save_simulation_results(simulation_name="test"):
    """Saving the main simulation results in a folder with the simulation_name, for the record"""
    
    print(blue("\nSave all finance results:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    destination_folder = config["foldername_result_finance"] + "\\" + simulation_name
    # clear_folder_content(destination_folder)

    copy_folder_content(config["foldername_finance"], destination_folder)
    copy_folder_content(config["filename_CACER_energy_monthly"], destination_folder)
    copy_folder_content(config["filename_CACER_incentivi"], destination_folder)
    copy_folder_content(config["filename_membership_matrix"], destination_folder)
    copy_folder_content(config["filename_plant_operation_matrix"], destination_folder)
    copy_folder_content(config["filename_input_FM_excel"], destination_folder)
    copy_folder_content(config["filename_registry_plants_yml"], destination_folder)
    copy_folder_content(config["filename_registry_user_types_yml"], destination_folder)
    copy_folder_content(config["filename_registry_users_yml"], destination_folder)
    copy_folder_content(config["filename_FM_results_last_simulation"], destination_folder)
    copy_folder_content(config["filename_recap"], destination_folder)
    output_file_docx = config["foldername_result_finance"] + recap["case_denomination"] + '.docx'
    copy_folder_content(output_file_docx, destination_folder)

    print("\n**** All finance results saved! ****")

################################################################################################################################

def kill_excel_processes():

    print(blue("\nKilling all excel process in backgroud:", ['bold', 'underlined']), '\n')

    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and 'excel' in proc.info['name'].lower():
            try:
                os.kill(proc.info['pid'], signal.SIGTERM)
                # print(f"Killed Excel process: {proc.info['pid']}")
            except Exception as e:
                print(f"Could not kill Excel process {proc.info['pid']}: {e}")
    
    print("\n**** All excel processes killed! ****")

################################################################################################################################

def setting_CACER_scenario(case_denomination, CACER_type, repartition_scheme):
    """Setting the CACER scenario.
    Args:
        case_denomination (string): denomination of the case
        CACER_type (string): type of CACER
        repartition_scheme (string): repartition scheme for incentives
    """

    print(blue("\nSetting input financial simulation:", ['bold', 'underlined']), '\n')

    add_to_recap_yml(key = "case_denomination", value = case_denomination)
    add_to_recap_yml(key = "type_of_cacer", value = CACER_type)
    edit_incentive_repartition_scheme(repartition_scheme)
    print("**** All inputs setted! ****")