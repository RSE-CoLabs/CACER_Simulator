import pandas as pd
import numpy as np
import numpy_financial as npf
from simple_colors import *
from tqdm import tqdm
import os
from random import random
import calendar
import datetime
import datetime as dt
from datetime import datetime
import contextlib
import io
import yaml
import xlwings as xw
import glob
from Functions_General import check_file_status, province_to_region, get_monthly_calendar, add_to_recap_yml, clear_folder_content, get_calendar #,add_to_input_FM_yml
from Functions_Energy_Model import get_input_gens_analysis
import warnings
warnings.filterwarnings("ignore")
from simple_colors import *

###############################################################################################################################

def run_user_type_bill(user_type):
    """ 
    This function creates the electricity bills for a given user type, based on the energy withdrawal (Eprel) coming out of the energy model. 
    If the user type is prosumer, the function creates one sheet for business-as-usual scenaro (BAU).
    If the user type is consumer, the function creates two sheets, one for BAU and one for PV (scenario in which the user installs a generation system and reduces its grid withdrawal and thus the electricity bill).
    
    Inputs:
        user_type: type of user (user_type_ID)

    Outputs:
        file with the name <user_type>.xlsx in folder config["foldername_bills"]
    """

    config  = yaml.safe_load(open("config.yml", 'r'))
    electricity_market_data = yaml.safe_load(open(config["filename_mercato"], 'r'))
    user_type_set  = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))

    print("\nUser type: " + blue(user_type))

    if user_type_set[user_type]['type']  == 'prosumer':
        scenarios = ['pv','bau']
    elif user_type_set[user_type]['type']  == 'consumer':
        scenarios = ['bau'] # consumers have the same bills in all scenarios
    else:
        # break as producers don't have bills
        assert user_type_set[user_type]['consuming'], f"User type {user_type} does not consume electricity. Can't create bills for this user type"

    writer = pd.ExcelWriter(config["foldername_bills"] + "\\" + user_type + ".xlsx", engine = 'xlsxwriter')

    dict_user       = user_type_set[user_type]          # select user dict 
    scheme          = dict_user['tariff']               # tariff scheme
    supplier        = dict_user['supplier']             # supplier
    category        = dict_user['category']             # category (domestico/non_domestico)
    power_range     = dict_user['power_range']          # range of contractual power 
    voltage         = dict_user['voltage']              # voltage level

    # extract configuration variables
    market_scenario             = config['market_scenario'] 
    folder_risultati_energy     = config['foldername_result_energy']
    yearly_variation_me         =   electricity_market_data['variazione_annua'][market_scenario]
    yearly_variation_transport  =   electricity_market_data['variazione_annua']['trasporto']
    yearly_variation_ogs        =   electricity_market_data['variazione_annua']['ogs']

    losses_load = electricity_market_data['perdite_prelievo_BT'] * (voltage == "BT") + electricity_market_data['perdite_prelievo_MT'] * (voltage == "MT")

    # importing from csv file the energy flows for the user type calculated for the whole project lifetime
    user_load   = pd.read_csv(folder_risultati_energy+user_type+".csv")[["datetime","Eprel","Eaut"]].fillna(0) # Nan in "Eaut" column will generate nan values in bau scenario
    user_load.set_index("datetime", inplace=True)     

    flag_indexed = supplier == "indexed"

    duty = electricity_market_data[category]['duty']
    vat = electricity_market_data[category]['vat']

    contractual_power = power_range_to_contractual_power(user_type)

    user_load["month"] = user_load.index.str[0:7]
    user_load["year"] = user_load.index.str[0:4].astype(int)
    user_load["month_number"] = user_load.index.str[5:7].astype(int)
    user_load["year_index"] = user_load["year"] - int(config["start_date"].year)

    # we have 2 options: fixed tariff or indexed tariff

    if flag_indexed: # 1) PUN + SPREAD TARIFF
        print("Tariff scheme: index + spread")

        pun = pd.read_csv(config["filename_input_PUN"], index_col="month_number")

        user_load["energy_price"] = [pun.loc[month_number, "eur/MWh"] / 1000 for month_number in user_load["month_number"]] # €/kWh (/1000 to pass from €/MWh to €/kWh)
        # Please note that the spread is not yet added, as PUN is yet to be adjusted with yearly variation

    else: # 2) FIXED TARIFF
        print("Tariff scheme: " + supplier)

        # need to give the energy price for each time slot. If the tariff is of monohourly or bihourly, we assign the same value of F1 to F2 (and) F3
        me_quota_energia_dict = electricity_market_data[category][supplier][scheme] # si importa la tariffa elettrica relativa all'utente in esame

        if scheme == "schema_1":
            user_load["energy_price"] = me_quota_energia_dict["F1"] # €/kWh, senza variazione annuale
        else:
            me_quota_energia_dict["F2"] = me_quota_energia_dict["F1"]
            me_quota_energia_dict["F3"] = me_quota_energia_dict["F2"]
            user_load["fascia"] = get_calendar().set_index("datetime")["fascia"]
            assert not  user_load["fascia"].isna().any(), "ERROR: There are NaN values in the fascia columnns"
            user_load["fascia"] = user_load["fascia"].replace({1: "F1", 2: "F2", 3: "F3"})
            user_load["energy_price"] = [me_quota_energia_dict[fascia] for fascia in user_load["fascia"]] # €/kWh, senza variazione annuale. Il prezzo giusto per la giusta fascia

    number_datapoints_in_year = 365 * 24 # if hourly
    if config["delta_t"] == "15Min":
        number_datapoints_in_year = number_datapoints_in_year * 4 # if quarterly

    bills_inputs = electricity_market_data[category]

    energy_items = [key for key in bills_inputs.keys() if key.endswith("_energy")]
    fixed_items = [key for key in bills_inputs.keys() if key.endswith("_fixed")]
    power_items = [key for key in bills_inputs.keys() if key.endswith("_power")]

    user_load["yearly_variation_me"] = [yearly_variation_me[year_index] for year_index in user_load["year_index"]]
    user_load["yearly_variation_transport"] = [yearly_variation_transport[year_index] for year_index in user_load["year_index"]]
    user_load["yearly_variation_ogs"] = [yearly_variation_ogs[year_index]for year_index in user_load["year_index"]]

    columns_to_keep = user_load.columns

    undiscounted_bill_totals = {} # dictionary to save bills

    for scenario in scenarios:

        user_load = user_load[columns_to_keep] # clearing any previous results

        user_load["load_active"] = (user_load["Eprel"] + (scenario == 'bau') * user_load["Eaut"]) # if BAU, then also Eaut is taken from grid and shall be paid for
        ## correction as per TIS Tabella 4 "Fattori percentuali di perdita di energia elettrica sulle reti con obbligo di connessione di terzi"
        user_load["load_active_corrected"] = user_load["load_active"]* (1+losses_load) # Eprel * (1+losses_load) 

        # ELECTRICITY BILLS COMPONENTS
        ## 1) Materia Energia (me) - Energia (PE), dispacciamento (PD), perequazione (PPE), commercializzazione (PCV) e componente di dispacciamento (DispBT)
        user_load["yearly_variation_me"] = [yearly_variation_me[year_index] for year_index in user_load["year_index"]]
        user_load["energy_price_corrected"] = user_load["yearly_variation_me"] * user_load["energy_price"] # €/kWh, updated with yearly variation
        
        if flag_indexed: # if PUN+spread, once the PUN has been corrected with the yearly variation, spread can be added. This way, we are assuming that spread is fixed over time
            spread = electricity_market_data[category]["indexed"]["spread"]
            user_load["energy_price_corrected"] = user_load["energy_price_corrected"] + spread

        user_load["me_energy"] = user_load["load_active_corrected"] * user_load["energy_price_corrected"] # €
        
        ## each can have 3 types of components: fixed [€/yr], energy [€/kWh] and power [€/kW]
        for item in energy_items + fixed_items + power_items:
            tariff = bills_inputs[item] 
            
            if flag_indexed and item == "me_PCV_fixed":
                tariff = bills_inputs["indexed"][item] # in PUN+spread scenario, named "indexed", the PCV component is established by the supplier, so we overwrite the value
            
            if item in energy_items:
                # identifying the variation factor to be applied to the energy component
                if "me" in item: variation_col = "yearly_variation_me"
                elif "transport" in item: variation_col = "yearly_variation_transport"
                else: variation_col = "yearly_variation_ogs"

                user_load[item] = user_load["load_active_corrected"] * tariff * user_load[variation_col] # [€]

            elif item in fixed_items:
                user_load[item] = tariff / number_datapoints_in_year # € N.B la quota fissa è annuale, qui la ripartiamo per intervallo
            else: # power items
                user_load[item] = contractual_power * tariff / number_datapoints_in_year # assuming the power tariff is stable in time

        # aggregating per type of cost
        for item_family in ["me","transport","ogs"]:
            # summing up all the cost for the items in the item_family
            item_family_cols = [col for col in user_load.columns if col.startswith(item_family)]
            # print(item_family_cols)
            user_load[item_family + "_cost"] = user_load[item_family_cols].sum(axis=1) # [€]

        # aggregating per type of tariff 
        for item_family in ["energy","fixed","power"]:
            # summing up all the cost for the items in the item_family
            item_family_cols = [col for col in user_load.columns if col.endswith(item_family)]
            # print(item_family_cols)
            user_load[item_family + "_cost"] = user_load[item_family_cols].sum(axis=1) # + user_load["me_"+item_family+"_cost"]# [€]

        assert (abs(user_load[["energy_cost","fixed_cost","power_cost"]].sum().sum() - user_load[["me_cost","transport_cost","ogs_cost"]].sum().sum()) < 1e-5), "ERROR in bills aggregation, something wrong"

        #  subtotal before taxes
        user_load["subtotal_before_taxes"] = user_load["me_cost"] + user_load["transport_cost"] + user_load["ogs_cost"] # [€]

        ######################################################
        # accise and iva (duty and VAT):
        # for resident domestic users with contractual power <=3, duties apply only to the share of energy above 150 kwh/month; for the rest, it applies to all consumtion
        if power_range in ['0<P<=1.5', '1.5<P<=3'] and category == "domestico":
            # calculating the cumulative sum for monthly values
            ## TBC whether the duties are applied to the consumed energy before or after the losses adjustment factor
            user_load["load_active_cumsum_monthly"] = user_load.groupby("month").apply(lambda grp: grp.load_active.cumsum()).reset_index(level=0,drop=True)
            user_load["load_active_duty"] = np.maximum(0,(user_load["load_active_cumsum_monthly"] - 150)) # share that exceeds the 150 kWh/month
            # duty
            user_load["duty_cost"]   = duty * (user_load["load_active_duty"]>0) * user_load["load_active"] # [€], if load_active_duty > 0, the duties are applied to load_active
        else:
            user_load["duty_cost"]   = duty * user_load["load_active"] # [€]

        user_load["vat_cost"] = vat * (user_load["subtotal_before_taxes"] + user_load["duty_cost"])

        #  total after taxes
        user_load["total_bill_cost"] = user_load["subtotal_before_taxes"] + user_load["duty_cost"] + user_load["vat_cost"] # [€]

        cols = [col for col in user_load.columns if col.endswith("_cost")]
        cols.append("load_active")
        cols.append("load_active_corrected")
        assert not user_load[cols].isnull().values.any(), "ERROR: user_load dataframe has nan, something wrong"
        montly_totals = user_load.groupby("month")[cols].sum()

        undiscounted_bill_totals[scenario] = user_load["total_bill_cost"].sum()

        user_load_first_year = user_load[user_load["year_index"] == 0]
        load_yr1 = user_load_first_year["load_active"].sum() # [kWh]
        expense_yr1 = user_load_first_year["total_bill_cost"].sum() # [€]
        average_cost_yr_1 = expense_yr1 / load_yr1 # [€ / kWh]

        print(f"Electricity withdrawn {scenario} in year 1:\t {load_yr1:,.1f} kWh")
        print(f"Electricity expenses {scenario} in year 1:\t {expense_yr1:,.2f} €")
        print(f"\t--> Average cost {scenario} in year 1: \t\t {average_cost_yr_1:.3f} €/kWh")

        montly_totals.to_excel(writer, sheet_name= scenario) #saving for the record

        user_load_first_year.to_excel(writer, sheet_name= scenario+"_quarterly") # saving first year for the record for checks and debugging

    writer.close()

    if "pv" in scenarios:
        undiscounted_bill_saving = (undiscounted_bill_totals["bau"] - undiscounted_bill_totals["pv"]) / undiscounted_bill_totals["bau"]
        print(f"Undiscounted bills savings in CACER scenario: {undiscounted_bill_saving*100:.1f} %")

def create_users_bill():
    """ running the bill calculation for all users, filling the bills folder with the results
    """

    print(blue("\nCreate user bills:", ['bold', 'underlined']), '\n')

    config  = yaml.safe_load(open("config.yml", 'r'))
    user_type_set  = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))

    # 
    if not os.path.exists(config["foldername_bills"]):
        os.makedirs(config["foldername_bills"])
    else:
        clear_folder_content(config["foldername_bills"])

    # for user_type in tqdm(user_type_set, desc = "Calculating electricity bills for all users"): # if there are prints in the function, the progress bar is not working right
    print("Calculating electricity bills for all users")
    for user_type in user_type_set:
        if not user_type_set[user_type]['consuming']: continue

        run_user_type_bill(user_type)

    print("\n**** Bills calculation completed! ****")

def aggregate_CACER_bills():
    """The function aggregates the electricity bills for all users in the CACER, stakeholders and configurations, which is needed as input for the financial model.
    """

    print(blue("\nAggregate bills for the entire CACER:\n", ['bold', 'underlined']))
    
    config = yaml.safe_load(open("config.yml", 'r'))
    recap   = yaml.safe_load(open(config["filename_recap"], 'r'))
    users_types_set   = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    
    for group_type in ["project"] + recap["stakeholders"] + recap["configurations"]:

        if group_type == "project":
            consuming_user_types_set = recap["list_types_consumers_CACER"] + recap["list_types_prosumers_CACER"]
        elif group_type in recap["stakeholders"]: 
            consuming_user_types_set = [user_type for user_type in users_types_set if users_types_set[user_type]["stakeholder"] == group_type and users_types_set[user_type]["consuming"] and not users_types_set[user_type]["dummy_user"]]
        else: 
            consuming_user_types_set = [user_type for user_type in users_types_set if users_types_set[user_type]["CP"] == group_type and users_types_set[user_type]["consuming"] and not users_types_set[user_type]["dummy_user"]]

        df_agg_bau = pd.DataFrame()
        df_agg_pv = pd.DataFrame()
        
        first_loop_flag = True # flag to check whether its the first loop or not

        for user_type in tqdm(consuming_user_types_set, desc = "Aggregating bills - " + group_type):
            
            # importing data for that user type
            filename = config["foldername_bills"] + user_type + ".xlsx"
            df_user_tariff_bau = pd.read_excel(filename, sheet_name="bau", index_col="month")
            
            if users_types_set[user_type]["type"] == "consumer":
                df_user_tariff_pv = df_user_tariff_bau # for consumers, bau and pv bills are the same as there is no generation and self-consumption
            else:
                df_user_tariff_pv = pd.read_excel(filename, sheet_name="pv", index_col="month")
            
            number_of_users = users_types_set[user_type]["num"] # number of users of that type
            
            # taking the electricity bill of that user type, and multiplying by the number of users of that type
            bills_bau = df_user_tariff_bau["total_bill_cost"].multiply(number_of_users)
            bills_pv = df_user_tariff_pv["total_bill_cost"].multiply(number_of_users)
            
            if not first_loop_flag: 
                df_agg_bau += bills_bau
                df_agg_pv += bills_pv
            else: 
                df_agg_bau = bills_bau
                df_agg_pv = bills_pv
                first_loop_flag = False 
        
        # exporting        
        writer = pd.ExcelWriter(config["foldername_bills"] + group_type +".xlsx", engine = 'xlsxwriter')

        df_agg_bau.to_excel(writer, sheet_name="bau")
        df_agg_pv.to_excel(writer, sheet_name="pv")
        writer.close()

    print("\n**** CACER bills aggregated! ****")
############################################################################################################################

def contractual_power_to_power_range(contractual_power):
    """function to link contractual power to the corrisponding range of ARERA dataframe
    Inputs:
        contractual_power           contractual power
    Outputs: 
        power_range                 corrisponding contractual power range
    """
    if contractual_power <= 1.5:
        power_range = "0<P<=1.5"
    elif contractual_power <= 3:
        power_range = "1.5<P<=3"
    elif contractual_power <= 4.5:
        power_range = "3<P<=4.5"
    elif contractual_power <= 6:
        power_range = "4.5<P<=6"
    else:
        power_range = "4.5<P<=6"
    return power_range

def power_range_to_contractual_power(user_type):
    """function to link the range of ARERA electricity consumption dataset to the corrisponding contractual power
    Inputs:
        power_range                 corrisponding contractual power range
    Outputs: 
        contractual_power           contractual power
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    registry_user_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
    power_range = registry_user_types[user_type]["power_range"]

    if power_range == "0<P<=1.5":
        contractual_power = 1.5
    elif power_range == "1.5<P<=3":
        contractual_power = 3
    elif power_range == "3<P<=4.5":
        contractual_power = 4.5
    elif power_range == "4.5<P<=6":
        contractual_power = 6
    else:
        load_profiles = pd.read_csv(config["filename_carichi"], index_col="datetime")
        factor = 1
        if config["delta_t"] == "15Min": factor = 4  # if 15min, multiply by 4, as those are kWh/15min. 
        contractual_power = load_profiles[user_type].max() * factor * 1.3 # assumption: contractual power is 1.3 times the max power withdrawn

    return contractual_power
############################################################################################################################

def incentives():
    """
    This function calculates and exports the incentives for CACER configurations based on multiple factors 
    including regional factors, plant capacity, public grants, and the type of CACER. It processes data from 
    various input files and applies conditions from the CACER decree and GSE regulations to compute the 
    incentive tariffs, shared energy valorization, and social fund contributions.

    Procedure:
    - Part A: Calculates incentives from MASE based on regional factors, plant capacity, and public grants.
    - Part B: Values shared energy as per ARERA regulations.
    - Part C: Aggregates and exports the results for each configuration.
    - Part D: Computes surplus based on shared energy thresholds and updates incentives accordingly.
    - Computes contributions to a social fund based on incentive and surplus repartition schemes.

    Outputs:
        - Exports the calculated incentives and valorization data to a specified output file
    """

    print(blue("\nCalculate incentives:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    is_AUC_flag = recap["type_of_cacer"] == "AUC"

    check_file_status(config["filename_CACER_incentivi"]) # checking output file is closed

    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))

    # PART A - incentives from MASE as per CACER decree (7 dicembre 2023, n. 414) e GSE Regole Operative

    # 1) calculating the regional factor 
    region = province_to_region() # Assuming all the configurations are the same macro-region (Nord, Centro, Sud)
    northern_regions = ["Emilia Romagna","Emilia-Romagna","Friuli Venezia Giulia","Friuli-Venezia-Giulia", "Liguria", "Lombardia", 
                    "Piemonte", "Trentino Alto Adige","Trentino-Alto Adige", "Valle d'Aosta", "Valle D'Aosta", "Veneto"]
    central_regions = ["Lazio","Marche","Toscana","Umbria","Abruzzo"]
    southern_regions = ["Sardegna", "Molise","Campania","Calabria","Basilicata","Puglia","Sicilia"]

    if region in northern_regions: FC_zonale = 10 #€/MWh
    elif region in central_regions: FC_zonale = 4 #€/MWh
    elif region in southern_regions: FC_zonale = 0 #€/MWh
    else: "ERROR: Region not found!! Check spelling"

    print("Factor FC_zonale: €/MWh ", FC_zonale)

    #importing PZO and shared energy eligible for incentives
    pzo = pd.read_csv(config["filename_output_csv_PZO_data"], index_col="datetime")
    pzo.rename(columns={"0":"PZO"}, inplace=True)
    cond_TIP = pd.read_csv(config["filename_incentive_shared_energy_hourly"], index_col="dayhour").fillna(0) # this file includes the CACER total
    cond_val = pd.read_csv(config["filename_valorization_shared_energy_hourly"], index_col="dayhour").fillna(0) # this file includes the CACER total
    pzo["dayhour"] = pzo.index.str[:13] # estracting the dayhour formatted as "YYYY-MM-DD HH"
    pzo.set_index("dayhour", inplace=True)
    df_merged = pd.concat([cond_TIP, cond_val, pzo], axis=1, join="inner")

    assert len(df_merged) != 0, "ERROR: empty df_merged! The datehour of pzo and cond_TIP have different formats"
    assert len(pzo) == len(cond_TIP), "ERROR: pzo (" + str(len(pzo)) + ") and cond_TIP (" + str(len(cond_TIP)) + ") have different number of datapoints! Something is wrong"
    assert len(df_merged) == len(cond_TIP), "ERROR: we lost datapoints during the merge! the datehour of pzo and cond_TIP do not exactly match"

    # calculating the TIP for each plant, based on power capacity, location and PNRR
    incentivized_plants = [plant for plant in registry_plants if registry_plants[plant]["new_plant"]]
    for plant in incentivized_plants:
        print("\nPlant: " + blue(plant))
        
        # 2) plant capacity
        plant_power_capacity = max(registry_plants[plant]["pv"], registry_plants[plant]["wind"])

        # obtaining the factors for the incentive's tariff calculation, as per Decree
        if plant_power_capacity >= 600: 
            TP_base = 60
            cap_parte_variabile = 100
        elif plant_power_capacity >= 200: 
            TP_base = 70
            cap_parte_variabile = 110
        else : 
            TP_base = 80
            cap_parte_variabile = 120

        print("Size factor - TP_base: €/MWh ", TP_base)
        print("Size factor - CAP: €/MWh ", cap_parte_variabile)

        # 3) Calculating the TIP reduction as consequence of public grants (such as PNRR)
        grant_pnrr = registry_plants[plant]["grant_pnrr"]
        if grant_pnrr > 0.4:
            F_pnrr = 1 # this will put the TIP = 0
            print("WARNING: plant has gone beyond the threshold of 40% of public grants, and consequently GSE contract imposes loss of incentives: TIP = 0")
        else: 
            F_pnrr = (grant_pnrr / 0.4) * 0.5 
            print(f"F_pnrr = {F_pnrr}")
        
        F_pnrr = 0 if np.isnan(F_pnrr) else F_pnrr
        # calculating the incentive tariff and incentives for given plant
        df_merged["tariffa_premio"] = (np.minimum(cap_parte_variabile, TP_base + np.maximum(0, 180 - df_merged["PZO"])) + FC_zonale) * (1 - F_pnrr)

        # TO BE FIXED: put in a better position, no need to arrive up to here
        if recap["type_of_cacer"] == "NO_CACER":
            df_merged["tariffa_premio"] = 0 # overwriting 
            print("No CACER --> no incentives")

        print("Average TIP: €/MWh ", df_merged["tariffa_premio"].mean())
        df_merged["tariffa_premio"] = df_merged["tariffa_premio"] / 1000 # from €/MWh to €/kWh

        # erasing the TIP tariff after year 20 ###################################################
        months_matrix = get_monthly_calendar().set_index("month")["month_number"] 
        df_merged["month"] = df_merged.index.str[:7]
        df_merged["month_number"] = df_merged["month"].apply(lambda x: months_matrix.loc[x])
        commissioning_month = registry_plants[plant]["commissioning_month"]
        expiration_month = commissioning_month + 20 * 12 # 20 years from plant commissioning
        df_merged.loc[df_merged["month_number"] > expiration_month, "tariffa_premio"] = 0 
        
        Econd_plant = "Econd_" + plant
        plant_incentive_col = "incentivo_" + plant
        df_merged[plant_incentive_col] = df_merged[Econd_plant] * df_merged["tariffa_premio"]

    ############################################################################
    # PART B - valorizzazione ARERA as per TIAD (delibera ARERA 727/2022/R/eel)
    # divide by 1000 to pass from [€/MWh] to [€/kWh]
    TRASe = config["TRASe"] / 1000
    BTAU = config["BTAU"] / 1000
    Cpr_bt = config["Cpr_bt"]
    Cpr_mt = config["Cpr_mt"]

    for configuration in recap["configurations"]:
        
        valorizzazione_config = "valorizzazione_config_" + configuration
        Econd = "Econd_"+configuration+"_VAL"
        Econd_bt = "Econd_bt_"+configuration+"_VAL"
        Econd_mt = "Econd_mt_"+configuration+"_VAL"

        # if CER --> only the first term of the equation; if AUC --> we have them all
        df_merged[valorizzazione_config] = df_merged[Econd] * TRASe + is_AUC_flag * (df_merged[Econd] * BTAU + (df_merged[Econd_bt] * Cpr_bt + df_merged[Econd_mt] * Cpr_mt) * df_merged["PZO"])

    ############################################################################
    # PART C - aggregating and exporting results

    df_merged["incentivo"] = 0 # initialization
    df_merged["valorizzazione"] = 0 # initialization
    for configuration in recap["configurations"]:
        cols_names = ["incentivo_" + plant for plant in incentivized_plants if registry_plants[plant]["CP"] == configuration]
        df_merged["incentivo_config_" + configuration] = df_merged[cols_names].sum(axis=1)
        df_merged["incentivo"] += df_merged["incentivo_config_" + configuration]
        df_merged["valorizzazione"] += df_merged["valorizzazione_config_" + configuration]

    df_merged["month"] = df_merged.index.str[0:7] # extracting the month "YYYY-MM"

    #saving the monthly incentive and valorization for all configurations + the total, to later appreciate the weight of each contribution
    incentivo_cols = ["incentivo_config_" + configuration for configuration in recap["configurations"]]
    valorizzazione_cols = ["valorizzazione_config_" + configuration for configuration in recap["configurations"]]
    df_merged.groupby("month")[incentivo_cols + valorizzazione_cols + ["incentivo", "valorizzazione"]].sum().to_csv(config["filename_CACER_incentivi_per_configuration"])

    df_merged_monthly = df_merged.groupby("month")[["incentivo","valorizzazione"]].sum() # dropping all configurations data to work on the totals

    df_merged_monthly["incentivo_totale"] = df_merged_monthly["incentivo"] # initialization

    ############################################################################
    # PART D - Surplus (CACER decree, Allegato 1, comma 4. Valori soglia per l’applicazione delle previsioni di cui all’articolo 3, comma 2, lettera g)
    # TO BE CONFIRMED: It is not clear if the surplus threshold should be an average based on all plants, 
    # or if the CACER has used it once even if for only one plant, then the lower threshold of 45% is applied. It shall be clarified later on. 
    # It is currently assumed that the threshold on the Surplus calculation depends on the max PNRR found in all the plants. 

    max_grant_pnrr = max(0, max([registry_plants[plant]["grant_pnrr"] for plant in registry_plants if not np.isnan(registry_plants[plant]["grant_pnrr"])]))
    print("\nThe max_grant_pnrr found is: ", max_grant_pnrr)
    surplus_threshold = 0.55 * (grant_pnrr == 0) + 0.45 * (grant_pnrr > 0) # upperbound threshold for the shared energy
    print("The surplus threshold is: ", surplus_threshold)

    yearly_shared_energy = pd.read_csv(config["filename_incentive_shared_energy_yearly"], index_col=0)["perc_cond_annuale"]
    yearly_shared_energy.index = yearly_shared_energy.index.astype(str) # year on the index
    years_exceeding_threshould = [year for year,value in zip(yearly_shared_energy.index, yearly_shared_energy) if value > surplus_threshold]

    if years_exceeding_threshould == []: 
        print("The incentive surplus threshold is never exceeded")
        df_merged_monthly["surplus"] = 0
    else: 
        print(f"The incentive surplus threshold exceeded in {len(years_exceeding_threshould)} years")
        #merging the two tables
        df_merged_monthly["year"] = df_merged_monthly.index.str[0:4]
        df_merged_monthly["yearly_shared_energy"] = [yearly_shared_energy[year] for year in df_merged_monthly["year"]]

        #calculating the surplus
        df_merged_monthly["surplus"] = df_merged_monthly["incentivo_totale"] * np.maximum(0,(df_merged_monthly["yearly_shared_energy"] - surplus_threshold) / df_merged_monthly["yearly_shared_energy"])
        df_merged_monthly["incentivo"] = df_merged_monthly["incentivo_totale"] - df_merged_monthly["surplus"]

    # social fund: it is the fund addressed to social purposes and it can be originated by:
    # 1) the incentive repartition matrix (as the CACER can address a share of the incentive and valorization directly to social fund), AND/OR 
    # 2) the surplus repartition scheme (as instructed by CACER decree art.3 comma 2, lettera g) 
        
    df_merged_monthly["social_fund"] = 0 # intialization

    # 1) the incentive repartition scheme
    incentives_repartition_matrix = pd.read_excel(config["filename_repartition_matrix"], sheet_name="incentives", index_col=0, header=1).T # month as index
    if "social_fund" in incentives_repartition_matrix.columns:
        incentives_social_fund_repartition_share = incentives_repartition_matrix["social_fund"].astype(float)
        df_merged_monthly["social_fund"] += df_merged_monthly["incentivo"] * incentives_social_fund_repartition_share
        df_merged_monthly["social_fund"] += df_merged_monthly["valorizzazione"] * incentives_social_fund_repartition_share

    # 2) the surplus repartition scheme
    surplus_repartition_matrix = pd.read_excel(config["filename_repartition_matrix"], sheet_name="surplus", index_col=0, header=1).T # month as index
    if "social_fund" in surplus_repartition_matrix.columns:
        surplus_social_fund_repartition_share = surplus_repartition_matrix["social_fund"].astype(float)
        df_merged_monthly["social_fund"] += df_merged_monthly["surplus"] * surplus_social_fund_repartition_share
        print(f"The nominal Social Fund generated is {df_merged_monthly['social_fund'].sum():,.1f} €")

    if "year" in df_merged_monthly.columns:
        df_merged_monthly = df_merged_monthly.drop(columns="year")

    assert not df_merged_monthly.isnull().values.any(), "ERROR: There are NaN values in the incentives dataframe"

    df_merged_monthly.index =  get_FM_template().index
    df_merged_monthly.to_csv(config["filename_CACER_incentivi"], index=True)

    # adding the CACER fees to be paid to GSE
    # CACER_fees_value = CACER_fees() # DA VERIFICARE DUPLICAZIONE 
    ## add_to_input_FM_yml("opex_CACER_GSE_fees", CACER_fees_value)

    print("\n**** Incentives calculation completed! ****")

###############################################################################################################################

def RID_calculation():
    """Function running all the subfuctions to: 
    - calculate the earnings from the energy sales with the Ritiro Dedicato (RID) mechanism. 
    - export the data of the hourly distribution of PZO for each year of the simulation
    - calculate the GSE fee tha every user must pay to GSE for the RID 
    The RID is the NOMINAL cash flow, meaning the inflation is not yet considered !
    """

    print(blue("\nCalculate RID:\n", ['bold', 'underlined']))

    config = yaml.safe_load(open("config.yml", 'r'))
    check_file_status(str(config['filename_output_csv_GSE_RID_fees'])) 
    check_file_status(str(config['filename_output_csv_PZO_data']))  
    check_file_status(str(config['filename_output_csv_RID']))  

    corrispettivo_RID_dict, corrispettivo_RID_df = RID_GSE_fees_CACER()

    output_file_path = str(config['filename_output_csv_GSE_RID_fees'])
    df = corrispettivo_RID_df.copy()
    name_df = "GSE_RID_fees"
    open_file_output = "off"
    
    export_to_csv(output_file_path, df, name_df, open_file_output)

    PMG_check_dict()

    yearly_variation, PMG_price, zona_di_mercato = read_yaml_file_RID()

    PZO = generate_PZO_values()

    PZO_data = add_leap_day(PZO)

    monthly_energy_sold_df, monthly_energy_sold_df_to_csv = calculation_monthly_energy_sold()

    path = str(config["filename_output_csv_PZO_data"])
    df = PZO_data.copy()
    name_df = "PZO_data"
    open_file_output = "off"
    export_to_csv(path, df, name_df, open_file_output)

    path = str(config["filename_output_csv_RID"])    
    df = monthly_energy_sold_df_to_csv.copy()
    name_df = "RID_data"
    open_file_output = "off"
    export_to_csv(path, df, name_df, open_file_output)

###############################################################################################################################

def RID_GSE_fees_user(gen_cap):
    """function to calculate the costs for the management of the photovoltaic generator
    Inputs:
        gen_cap       power capacity of the photovoltaic generator [kWp]
    Outputs: 
        corr_RID      total costs for the management of the single generator [€]
    """ 
    config = yaml.safe_load(open("config.yml", 'r'))
    RID_input = yaml.safe_load(open(str(config['filename_RID_input']), 'r')) 

    # importing the unitary corrispettive to pay [€ / kWp]
    threshold_1 = RID_input['corrispettivi_unitari']['PV']['threshold_1'] # [€ / kWp]
    threshold_2 = RID_input['corrispettivi_unitari']['PV']['threshold_2'] # [€ / kWp]
    threshold_3 = RID_input['corrispettivi_unitari']['PV']['threshold_3'] # [€ / kWp]
    massimale = RID_input['corrispettivi_unitari']['PV']['massimale'] # [€ / kWp]

    corr_threshold_1 = min(gen_cap, 20) * threshold_1 # [€]
    corr_threshold_2 = max(0, min(gen_cap-20, 200)) * threshold_2 # [€]
    corr_threshold_3 = max(0, gen_cap-200) * threshold_3 # [€]

    corr_RID = min(corr_threshold_1 + corr_threshold_2 + corr_threshold_3, massimale) # [€]

    return corr_RID

###############################################################################################################################

def RID_GSE_fees_CACER():
    """function to calculate the costs for the management of the photovoltaic plants for each generators
    Outputs: 
        corrispettivo_RID_dict      total costs in € for the management of all generators [dict]
        corrispettivo_RID_df        total costs in € for the management of all generators [df]
    """

    corrispettivo_RID_dict = {} # initialization

    gen_data = get_input_gens_analysis()[2] # importing the data of the generators [kWp]

    config = yaml.safe_load(open("config.yml", 'r')) 
    registry_user_types = yaml.safe_load(open(config['filename_registry_user_types_yml'], 'r')) 

    for user in gen_data:
        gen_cap = registry_user_types[user]['pv'] # generation capacity of the plant [kWp]
        corr_RID = RID_GSE_fees_user(gen_cap) # RID fee to be paid to GSE for that plant [€/yr]
        corrispettivo_RID_dict.setdefault(user, {}) # setting the label
        corrispettivo_RID_dict[user] = corr_RID # saving

        # print(str(user) + " completed!")

    corrispettivo_RID_df = pd.DataFrame(corrispettivo_RID_dict, index=['GSE_fees']) # setting the df index

    print('Yearly costs for the management of the different generators [€/year]: \t' , corrispettivo_RID_dict)
    print("Calculation RID fees for CACER users completed!")

    return corrispettivo_RID_dict, corrispettivo_RID_df


###############################################################################################################################

def PMG_check_dict():

    """function to evaluate the access to PMG for each generator
        Inputs:
            -
        Outputs: 
            PMG_check_dict          boolean value, equal to 1 if the PV generator can access to the PMG concessions for each generator [dict]
    """

    gen_data = get_input_gens_analysis()[2] # importing the generation capacity for the plants [kWp]

    PMG_check_dict = {} # initialization

    config = yaml.safe_load(open("config.yml", 'r'))
    
    registry_user_types = yaml.safe_load(open(config['filename_registry_user_types_yml'], 'r')) 

    for user in gen_data:
        gen_cap = registry_user_types[user]['pv'] # generation capacity of the specific plant [kWp]
        check = gen_cap <= 100 # checking if the plant is eligible for PMG (Capacity below or equal to 100kWp)
        PMG_check_dict.setdefault(user, {}) # setting the label
        PMG_check_dict[user] = check # saving

        # print(str(user) + " completed!")

    print('\nCheck PMG concessions: \n' , PMG_check_dict)

    print("Checking PMG concessions for all users completed!")

###############################################################################################################################

def province_italian_market_zone():
    """
    This function identifies the market zone for the selected province in the config file.
    TO BE IMPLEMENTED: with the CER being enabled to operate in multiple market zones, the province reference must be redirected from the config file to the specific location of the plant 
    
    Returns:
        market_zone (str): market zone for the selected province
    """
    config = yaml.safe_load(open("config.yml", 'r')) 
    comuni_italiani = pd.read_csv(config["filename_comuni_italiani"], encoding='unicode_escape') # reading the csv with all the italian municipalities and provinces
    market_zone = comuni_italiani[comuni_italiani["Denominazione in italiano"] == config["provincia_it"]]["Zona di mercato"].iloc[0] # finding the corresponding market zone
    # print("Market zone: ", market_zone)
    return market_zone

###############################################################################################################################

def read_yaml_file_RID():
    """we read the data from the external yaml file and save them into the internal variables
    Outputs:
        yearly_variation          annual variation of the producitvity due to the losses in efficiency [float]
        PMG_price                 price for the PMG at the current year [float]
        market_zone               name of the market zone [str]
        file_input                name of the input file with the historical data of the PZO [str]
    """

    config = yaml.safe_load(open("config.yml", 'r')) 
    
    RID_input = yaml.safe_load(open(config['filename_RID_input'], 'r')) 

    yearly_variation = RID_input['variazione_annua'] # list with the yearly variation of the PZO
    PMG_price = RID_input['PMG']['PV'] # importing the PMG threshold value [€ / MWh]
    market_zone = province_italian_market_zone() # getting the market zone, to be able to selecte the corresponding PZO (PZO depends on the market zone)

    return yearly_variation, PMG_price, market_zone

###############################################################################################################################

def generate_PZO_values():
    """we calculate the values of PZO in €/kWh for each hour for each year of the project
    Outputs:
        PZO_merged             hourly values of the PZO in € / kWh for each year of the project [df]
    """

    yearly_variation, PMG_price, zona_di_mercato = read_yaml_file_RID() # si imporanto i valori di variazione annuale del PZO, il PMG e la zona di mercato per l'analisi in esame

    config = yaml.safe_load(open("config.yml", 'r'))

    PZO_input_df = pd.read_csv(str(config['filename_input_PZO']), header=0, parse_dates = ['Date'], infer_datetime_format = True) # si apre il file csv contenente il PZO medio mensile per l'anno iniziale

    PZO_input_df.index = pd.DatetimeIndex(PZO_input_df['Date']) # setting the date column as DateTime.index 

    PZO_market_zone = PZO_input_df[zona_di_mercato] # estracting the df with only the PZO of our market zone

    date_string = str(config['start_date']) # si importa la data di inizio del progetto [%Y-%m-%d]
    data = dt.datetime.strptime(date_string, "%Y-%m-%d") # si converte la data importata in formato stringa in un formato datetime
    start_year = str(data.strftime("%Y")) # si acquisisce la vita utile dell'impianto con cui svolgere la simulazione da file yaml 

    project_life_time = int(config['project_lifetime_yrs']) # si acquisisce la vita utile dell'impianto con cui svolgere la simulazione da file yaml

    current_year = int(start_year) - 1 # starting year

    PZO_merged = pd.DataFrame() # initialization, with PZO corrected with yearly_variation

    current_yearly_rate = 1 # initialization of yearly variation

    for year in range (0, project_life_time):
        current_year += 1 # updating actual year
        current_yearly_rate *= (1-yearly_variation[year]) # yearly variation of actual year
        PZO_concat = PZO_market_zone.copy() * current_yearly_rate / 1000  # [€ / kWh]
        PZO_concat.index = PZO_input_df.index.map(lambda t: t.replace(year=current_year)) # replacing in the si rimpiazza nel datetime.index the previous year with the current year
        PZO_merged = pd.concat([PZO_merged, PZO_concat]) # concatenating data

    PZO_merged.index.name = 'datetime' # renaming index

    PZO_merged.columns = ['PZO'] 
    
    print("\nCalculation PZO values for each hour for all the years of the project completed!")

    format = '%Y-%m-%d %H:%M:%S'
    PZO_merged_index = pd.to_datetime(PZO_merged.index, format=format)
    PZO_merged = PZO_merged.set_index(pd.DatetimeIndex(PZO_merged_index))

    PZO_merged = PZO_merged.sort_index()

    return PZO_merged

###############################################################################################################################

def add_leap_day(PZO):

    """
    Add a leap day to the PZO data for each leap year in the project duration.

    This function checks each year within the project duration to determine if it is a leap year.
    If a year is a leap year, it duplicates the data for February 28th and assigns it to February 29th,
    effectively adding a leap day to the dataset. The adjusted PZO data is then returned.

    Args:
        PZO (pd.DataFrame): The input DataFrame containing PZO values with a datetime index.

    Returns:
        pd.DataFrame: The modified PZO DataFrame with added leap days for each leap year.
    """

    config = yaml.safe_load(open("config.yml", 'r'))

    date_string = str(config['start_date'])
    data = datetime.strptime(date_string, "%Y-%m-%d")
    start_year = int(data.strftime("%Y")) 

    project_life_time = int(config['project_lifetime_yrs'])

    end_year = start_year + project_life_time

    PZO_data = PZO
    format = '%Y-%m-%d %H:%M:%S'
    PZO_data_index = pd.to_datetime(PZO_data.index, format=format)
    PZO_data = PZO_data.set_index(pd.DatetimeIndex(PZO_data_index))

    # checking the condition is True or not
    for year in range(start_year, end_year):
        val = calendar.isleap(year)
        if val == True:

            start_day = datetime.strptime(str(year)+'-02-28 00:00:00', "%Y-%m-%d %H:%M:%S")
            end_day = datetime.strptime(str(year)+'-02-28 23:00:00', "%Y-%m-%d %H:%M:%S")

            leap_day = PZO_data.loc[start_day: end_day]

            leap_day.index = leap_day.index.map(lambda t: t.replace(year=year))
            leap_day.index = leap_day.index.map(lambda t: t.replace(day=29))

            PZO_data = pd.concat([PZO_data, leap_day])

            # print(str(year)+" completed!")
        
        else:
            continue
            # print(str(year)+" is not a leap year!")

    format = '%Y-%m-%d %H:%M:%S'
    PZO_data_index = pd.to_datetime(PZO_data.index, format=format)
    PZO_data = PZO_data.set_index(pd.DatetimeIndex(PZO_data_index))
    PZO_data = PZO_data.sort_index()

    return PZO_data

###############################################################################################################################

def calculation_monthly_energy_sold():
    """Calculating monthly energy sold in € / month for each user
    Outputs:
        monthly_energy_sold_df                     monthly energy cumulated sold for each user [df]
        monthly_energy_sold_df_to_csv              monthly energy cumulated sold for each user with an index in string format ready to the csv export [df]
    """

    config = yaml.safe_load(open("config.yml", 'r'))  
    
    recap = yaml.safe_load(open(str(config['filename_recap']), 'r'))  
    
    registry_user_types = yaml.safe_load(open(config['filename_registry_user_types_yml'], 'r'))

    foldername_result_energy = str(config['foldername_result_energy']) 

    MT_losses = float(config['perdite_MT'])
    BT_losses = float(config['perdite_BT'])

    PZO = generate_PZO_values() # houly profile of PZO for entire project lifetime [df]

    monthly_energy_sold_df = pd.DataFrame() # initialization
    gen_data = get_input_gens_analysis()[2]

    # loop over prosumers and producers
    for user_type in gen_data.keys():

        voltage = registry_user_types[str(user_type)]['voltage'] # voltage level of the user (BT is LV, MV is)

        if voltage == "BT":
            losses = BT_losses # [%]
        else:
            losses = MT_losses # [%]

        df = pd.read_csv(foldername_result_energy+user_type+".csv") # getting the enegy flows fot he selected user type
        E_imm = df['Eimm'] # injected energy [kWh]
        E_imm = E_imm * (1+losses) # applying the losses correction factor for the injected energy for the voltage level 
        E_imm.index = pd.DatetimeIndex(df['datetime']) # setting index

        time_interval = '1H' # setting a time inteval of 1h to resample the data with a different delta_t

        # if delta_t >= 1H
        if pd.to_timedelta(time_interval) >= pd.to_timedelta('1H'): 
            E_imm_resampled = E_imm.resample(time_interval, kind = 'timestamp').sum() # [kWh]
                
        # if delta_t < 1H
        else:
            E_imm_resampled = E_imm.resample(time_interval).first() # [kWh]
            E_imm_resampled = E_imm_resampled.groupby(E_imm_resampled.notna().cumsum()).apply(lambda x: x/len(x.index)).ffill()

        E_imm_monthly_cum = E_imm.resample('1M').sum() # summing up to obtain the monthly values, for reporting anche check purporses

        hourly_energy_sold = PZO.mul(E_imm_resampled, axis = 0) # multiplying the hourly PZO [€ / kWh] by the injected energy [KWh] obtaining the cash flow [€] for the specific user type

        hourly_energy_sold.columns = [user_type] # renaming the column

        monthly_energy_sold = hourly_energy_sold.resample('1M').sum() # monthly resampling
        yearly_energy_sold = hourly_energy_sold.resample('1Y').sum() # yearly resampling

        hourly_energy_sold.index.name = 'datetime' #  setting index
        monthly_energy_sold.index.name = 'datetime' #  setting index
        yearly_energy_sold.index.name = 'datetime' #  setting index

        monthly_energy_sold_df[user_type] = monthly_energy_sold[user_type] # saving into an aggregated df for all user types

    monthly_energy_sold_df_to_csv = monthly_energy_sold_df.copy() # copying the aggregated dataframe

    # modifying the datetime.index format before exporting
    monthly_energy_sold_df_to_csv.index = pd.to_datetime(monthly_energy_sold_df_to_csv.index, format = '%d/%m/%Y %H:%M').strftime('%Y-%m') 

    monthly_energy_sold_df.index.name = 'month' #  setting index
    monthly_energy_sold_df_to_csv.index.name = 'month' #  setting index

    print("\nCalculation of the monthly energy sold for all users completed!")

    return monthly_energy_sold_df, monthly_energy_sold_df_to_csv

###############################################################################################################################

def export_to_csv(path, df, name_df, open_file_output = "on"):

    """we export data to a csv file
        Inputs:
            path                                  path where we export the dataframe in a csv file [str]
            df                                    dataframe to export [df]
            open_file_output                      boolean value, if "on" we open the file at the end [boolean]
        Default:
            open_file_output                      "on"
        Outputs:
            output_RID.csv                        a csv file with all the monthly results [csv]
        """

    df.to_csv(path, encoding='utf-8')

    if open_file_output == "on":
        os.startfile(path)
    
    else:
        pass
    
    print("\nExport "+name_df+" to csv completed!")

###############################################################################################################################

def CACER_fees():
    """
    Calculate the CACER GSE fees. This function calculates the total CER fees based on the configuration based 
    on their generation capacity, and adds variable user fees scaled by the total number of members. 

    Outputs:
        CER_GSE_fees:   The total CER fees 
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

    CER_fees = yaml.safe_load(open(config["CER_fees"], 'r'))

    total_CACER_members = recap['total_CACER_members']
    var_fees_user = CER_fees['var_fees_user'] * total_CACER_members
    gens_CACER_fees = 0

    for user in registry_users:
        if str(registry_users[user]['pv']) == "nan":
            pass

        else:
            gen_cap = int(registry_users[user]['pv'])

            if gen_cap <= 3:
                fixed_fees = CER_fees['fixed_fees']['range_0_3_kw']
                var_fees = CER_fees['var_fees']['range_0_3_kw']
            
            elif gen_cap <= 20:
                fixed_fees = CER_fees['fixed_fees']['range_3_20_kw']
                var_fees = CER_fees['var_fees']['range_3_20_kw']
            
            else:   
                fixed_fees = CER_fees['fixed_fees']['range_20_1000_kw']
                var_fees = CER_fees['var_fees']['range_20_1000_kw']
            
            gen_fixed_fees = fixed_fees
            gen_var_fees = var_fees * gen_cap

            total_gen_fees = gen_fixed_fees + gen_var_fees

            gens_CACER_fees += total_gen_fees

    CER_GSE_fees = gens_CACER_fees + var_fees_user

    return CER_GSE_fees

###############################################################################################################################

def aggregate_CACER_RID():
    """
    Function to aggregate the RID bills for all users in the CACER, needed as input for the financial model.
    """

    print(blue("\nAggregate RID for the entire CACER:\n", ['bold', 'underlined']))

    config = yaml.safe_load(open("config.yml", 'r'))
    recap   = yaml.safe_load(open(config["filename_recap"], 'r'))
    registry_user_types   = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))

    rid = pd.read_csv(config["filename_output_csv_RID"],index_col="month")
    
    user_list = recap["list_types_prosumers_CACER"] + recap["list_types_producers_CACER"]

    rid = rid[user_list] # removing the ones we don't need

    first_loop_flag = True 

    for user in tqdm(user_list, desc = "Aggregate RID CACER"):
        
        number_of_users = registry_user_types[user]["num"] # number o f users for this user type
        
        # summing up all the users' RID
        rid["CER"] = rid[user].multiply(number_of_users) 
        if first_loop_flag: 
            rid["CER"] = rid[user].multiply(number_of_users) 
            first_loop_flag = False 
        else: 
            rid["CER"] = rid["CER"] + rid[user].multiply(number_of_users)

    rid.to_csv(config["filename_output_csv_RID_active_CACER"])
    print("\n**** Aggregated RID CACER (energy sold revenues) created! ****")

####################################################################################################################################

def FM_initialization():
    """
    Initialize the financial model (FM) by generating all the necessary input files:
    - the template for the FM
    - the investment matrix
    - the ownership matrix
    - the repartition matrix
    - the subscription matrix.
    """

    print(blue("\nInitialize financial simulation:", ['bold', 'underlined']), '\n')

    FM_template()
    create_investment_matrix()
    create_ownership_matrix()
    create_repartition_matrix()
    create_subscription_matrix()

####################################################################################################################################

def FM_template():
    """
    Function to generate the template for the financial model, containing:
    - import of the monthly calendar
    - calculation of the yearly and monthly inflation rates
    - calculation of the discount factors for each user category
    The output is a csv file, used as template used as baseline for the next cashflow calculations.
    """

    print(blue("Creating FM template:\n"))

    config = yaml.safe_load(open("config.yml", 'r'))
    
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    
    #importing the monthly calendar formatted as string "YYYY-MM" and we add the month number
    df = get_monthly_calendar()
    df["year"] = df["month"].str[0:4]

    # INFLATION
    inflation_rate_pa_df = wb.sheets["Inflation"]["A1"].options(pd.Series, header=1, index=True, expand='table').value
    inflation_rate_pa_df.index = inflation_rate_pa_df.index.astype(int).astype(str) # checking year format is string YYYY

    # passing from yearly to monthly
    df["inflation_rate_pa"] = np.nan
    df["inflation_rate_pm"] = np.nan

    for i in range(len(df)):
        
            active_year = df.loc[i,"year"]
            df.loc[i,"inflation_rate_pa"] = inflation_rate_pa_df[active_year]
            df.loc[i,"inflation_rate_pm"] = (1 + df.loc[i,"inflation_rate_pa"])**(1/12)-1 # (1 + yearly_inflation) = (1 + monthly_inflation)^12
            
            if i == 0: #inizialization for first element (i-1 does not exist)
                df.loc[i,"inflation_factor"] = 1 # starting from 1 in first month of the series
            else:
                df.loc[i,"inflation_factor"] =  df.loc[i-1,"inflation_factor"] * (1 + df.loc[i,"inflation_rate_pm"]) # factor_t = factor_t-1 * (1 + inflation_rate_t)

    print("yearly inflation rate yr1: " + str(round(df.loc[0,"inflation_rate_pa"]*100,3))+ " %")
    # print("yearly inflation rate yr2: " + str(round(df.loc[12,"inflation_rate_pa"]*100,3))+ " %")

    # DISCOUNT RATE
    # discount rate depends on user category
    discount_rate_pa_table = wb.sheets["CAPEX"]["financial_structure_table"].options(pd.Series, header=1, index=True, expand='table').value.drop(columns="Unit")
    user_categories = list(discount_rate_pa_table.columns)

    for user_category in user_categories:
        print("\nuser category: "+user_category)
        discount_rate_pa = discount_rate_pa_table.loc["discount_rate_pa",user_category] 
        print("yearly discount rate: " + str(round(discount_rate_pa*100,3))+ " %")
        discount_rate_pm = (1+ discount_rate_pa)**(1/12)-1
        # print("monthly discount rate: " + str(round(discount_rate_pm*100,3)) + " %")
        df["discount_factor_"+user_category] =  1/((1+discount_rate_pm)**(df["month_number"]-1)) # 1/((1+d_monthly)^(month-1))

    #dropping unneeded columns
    df.drop(columns=["inflation_rate_pa","inflation_rate_pm"],inplace=True)
    df.set_index("month_number", inplace=True)

    df.to_csv(config["filename_FM_template"])

    print("**** FM template created! ****")

    wb.close()
    app.quit()

#####################################################################################################
def get_FM_template(user_category=None):
    """
    Imports the FM_template and processes it based on the user category.
    
    Parameters:
    - user_category (str, optional): Specifies the user category to retain the relevant discount factor. 
      If None, discount factors are ignored.
    
    Returns:
    - DataFrame: Contains the month, inflation_factor, and discount_factor (if user_category is provided).
    """
    
    # Load configuration file
    config = yaml.safe_load(open("config.yml", 'r'))
    
    # Read the FM template CSV into a DataFrame
    df = pd.read_csv(config["filename_FM_template"], index_col=0)

    if user_category is None:
        # Return DataFrame with only month and inflation_factor columns if no user category is specified
        return df[["month", "inflation_factor"]]
    else:
        # Identify and drop discount_factor columns not related to the specified user category
        cols_to_drop = [col for col in df.columns if col.startswith("discount_factor_") and not col.endswith(user_category)]
        df.drop(columns=cols_to_drop, inplace=True)
        
        # Rename the relevant discount_factor column for clarity
        df.rename(columns={"discount_factor_" + user_category: "discount_factor"}, inplace=True)
        
        # Return DataFrame with month, inflation_factor, and the relevant discount_factor
        return df[["month", "inflation_factor", "discount_factor"]]

####################################################################################################################################
def create_subscription_matrix():
    """
    Generates the annual subscription matrix, which combines membership matrix with month on January of every year, when subscriptions are collected, as 1 or 0.
    It is needed to compute the total collection of fees by the CACER and the fee payment for users.
    index = users
    columns = month_number
    """
    
    print(blue("\nCreating subscription matrix:"))

    config = yaml.safe_load(open("config.yml", 'r'))

    # Read the membership matrix
    df = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=0).T

    # Convert the month numbers to integers
    df.index = df.index.astype(int)

    # Identify the non-subscription months
    non_subscription_months = [month_number for month_number in df.index if not df.loc[month_number,"month"].endswith("-01")]

    # Identify the user columns
    users_col = [col for col in df.columns if col.startswith("u_")]

    # Set the non-subscription months to 0 for each user
    df.loc[non_subscription_months,users_col] = 0

    # Save the subscription matrix
    df.T.to_csv(config["filename_subscription_matrix"])

    print("\n**** Subscription matrix created! ****")

####################################################################################################################################
def create_ownership_matrix():
    """ Generates a time-dependant matrix for each plant, indicating the ownership shares of each user/third party. it is similar to the investment matrix, which is just a snapshot of the ownership matrix
    at disburnment phase needed to allocate CAPEX between the users. The ownership matrix depends on the entry-exit of investors and players (such as an ESCo, which handover the asset after cetain number of years) as asset owners. 
    The ownership matrix is needed to establish, for each month of the project, which are the users bearing the OPEX and receinving the energy sales (RID) from GSE.  
    """

    print(blue("\nCreating ownership matrix:"))

    config = yaml.safe_load(open("config.yml", 'r'))

    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    funding_scheme_repartition = wb.sheets["Funding scheme"]["A1"].options(pd.Series, header=1, index=True, expand='table').value.fillna(0).drop("Ownership",axis=1)

    inv_mat = pd.read_csv(config["filename_investment_matrix"], index_col=0).fillna(0) # investment matrix

    plant_operational_matrix = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_operation_matrix", index_col=0, header=1) # plant_id as index, month "YYYY-MM" as column

    membership_matrix = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=1) # user_id as index, month "YYYY-MM" as column
    investment_matrix = pd.read_csv(config["filename_investment_matrix"], index_col=0, header=0) # user_id as index, plant_id as column

    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))

    months = get_monthly_calendar()["month"].to_list()

    writer = pd.ExcelWriter(config["filename_ownership_matrix"], engine = 'xlsxwriter')

    for plant in registry_plants:
        
        users = inv_mat.loc[inv_mat[plant] > 0,plant].index.to_list() # taking only the users who funded the plant
        if "ESCo" in users: users.remove("ESCo")
        if "CACER" in users: users.remove("CACER")

        plant_operational_series = plant_operational_matrix.loc[plant].astype(float) # Series of 0 and 1, months as column 

        df = pd.DataFrame(index=users,columns=months).fillna(0) # creating the Ownership Matrix as dataframe
        
        plant_funding = registry_plants[plant]["funding_scheme"]
        active_funding_scheme_repartition = funding_scheme_repartition.loc[plant_funding]
        esco_flag = active_funding_scheme_repartition["ESCo_flag"] #saving the info on the presence of the ESCo
        active_funding_scheme_repartition = active_funding_scheme_repartition.drop("ESCo_flag") # dropping the column as no longer needed in this dataframe

        assert abs(active_funding_scheme_repartition.sum() - 1) < 0.0001, "ERROR, sum of shares for scheme <{}> different from 100%".format(plant_funding)

        # If the Esco flag is True then the ESCo bears 100% of capex and we can move to next plant
        if esco_flag: 
            df.loc["ESCo",:] = 0 # initialize ESCo row

            commissioning_month = registry_plants[plant]["commissioning_month"]
            ppa_duration_months = wb.sheets["ESCo"]["esco_table"].options(pd.Series, header=1, index=True, expand='table').value.loc["ppa_contract_duration","Value"] * 12
            ppa_expiring_month_number = ppa_duration_months + commissioning_month # month number from beginning of project

            ppa_active_series = get_monthly_calendar().set_index("month").lt(ppa_expiring_month_number)["month_number"]
            # series of True (ppa is active, before ppa_expiring_month_number) and False (ppa expired). Index is the months. Operation btw strings f.i. "2025-12" > "2025-05" --> True

            df.loc["ESCo"] = plant_operational_series * ppa_active_series
        else: 
            # if esco is not present, then we impose the ppa never active (series filled with False) 
            ppa_active_series = pd.Series(index=months,dtype='float64').fillna(False)   

        # active_funding_scheme_repartition is a Series with "Titolare POD", "CACER members" and "CACER". We now remove the ones equal to 0 to avoid looping on them
        active_funding_scheme_repartition = active_funding_scheme_repartition[active_funding_scheme_repartition > 0]

        for stakeholder, ownership_share in active_funding_scheme_repartition.items():
            
            # note: we shall not overwrite the value, but update, as users might have shares coming from different sources 

            if stakeholder == "Titolare POD": 
                user_pod = registry_plants[plant]["titolare_POD"]

                if esco_flag:
                    df.loc[user_pod] = 0 # initialization

                # plant_operational_series is the series of flags (1/0) indicating whether the plant is operational for the CACER's POV at given month. 
                df.loc[user_pod] += plant_operational_series * ownership_share * ~ppa_active_series

            elif stakeholder == "CACER members": 
                plant_investors = investment_matrix[plant].dropna().index.to_list() # list of users who actually invested in the plant
                investors_subset_membership_matrix = membership_matrix.loc[plant_investors] # subset of membership matrix with only investors, dropping those not involved
                investors_subset_membership_matrix_totals = investors_subset_membership_matrix.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                membership_matrix_percentage = investors_subset_membership_matrix / investors_subset_membership_matrix_totals # calculating the share of each investor over the total over time
                membership_matrix_percentage = membership_matrix_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s
                
                cond_equal_1 = abs(membership_matrix_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(membership_matrix_percentage.sum() - 0) < 1e-5
                
                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error is triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage for {plant} do not add up to 100%"

                df += plant_operational_series * membership_matrix_percentage * ownership_share

            else: #cases of CACER
                df.loc["CACER"] = 0 # initialize CACER row
                df.loc["CACER"] += plant_operational_series * ownership_share * ~ppa_active_series
        
        cond_equal_1 = abs(df.sum() - 1) < 1e-5
        cond_equal_0 = abs(df.sum() - 0) < 1e-5
        assert (cond_equal_1 + cond_equal_0).all(), "ERROR, sum of shares for plant {} different from 100%".format(plant)

        # adjusting format for export
        df.loc["month"] = df.columns.tolist()
        df = pd.concat([df.loc[['month'],:], df.drop('month', axis=0)], axis=0) # bringing the month "YYYY-MM" row to the top pf the dataframe
        df.columns = list(get_monthly_calendar()["month_number"]) # updating the columns to month_number, not month, so it's more intuitive for user

        df.to_excel(writer, sheet_name= plant) #saving for the record

    writer.close()

    wb.close()
    app.quit()

    print("\n**** Ownership matrix created! ****")

def create_investment_matrix():
    """ Generates a non time-dependant investment matrix for each plant, indicating the investment shares of each user/third party, 
    needed to allocate CAPEX between the users. The sum of each plant shares is 100%. 
    """

    print(blue("\nCreating Investment Matrix:\n"))

    config = yaml.safe_load(open("config.yml", 'r'))

    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    funding_scheme_repartition = wb.sheets["Funding scheme"]["A1"].options(pd.Series, header=1, index=True, expand='table').value.fillna(0).drop("Ownership",axis=1)

    membership_matrix = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=1) # user_id as index, month "YYYY-MM" as column

    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))

    users = list(registry_users.keys())
    plants = list(registry_plants.keys())

    inv_mat = pd.DataFrame(index=users,columns=plants).fillna(0) # creating the Ownership Matrix as dataframe
    inv_mat.loc["CACER",:] = 0 # initialize CACER row
    inv_mat.loc["ESCo",:] = 0 # initialize ESCo row

    for plant in plants:
        
        plant_funding = registry_plants[plant]["funding_scheme"]
        active_funding_scheme_repartition = funding_scheme_repartition.loc[plant_funding]
        esco_flag = active_funding_scheme_repartition["ESCo_flag"] #saving the info on the presence of the ESCo
        active_funding_scheme_repartition = active_funding_scheme_repartition.drop("ESCo_flag") # dropping the column as no longer needed in this dataframe

        assert active_funding_scheme_repartition.sum() == 1, f"ERROR, sum of shares for scheme <{plant_funding}> different from 100%"

        # If the Esco flag is True then the ESCo bears 100% of capex and we can move to next plant
        if esco_flag: 
            inv_mat.loc["ESCo",plant] = 1
            continue

        for stakeholder, ownership_share in active_funding_scheme_repartition.items():
            # print(stakeholder)
            
            # note: we shall not overwrite the value, but update, as users might have shares coming from different sources 

            if ownership_share > 0: # if the value is not 0, we add it to the ownership matrix, for the given user and given plant

                if stakeholder == "Titolare POD": 
                    user = registry_plants[plant]["titolare_POD"]
                    # print(user)
                    inv_mat.loc[user,plant] += ownership_share

                elif stakeholder == "CACER members": 
                    # we need to verify which members were in the CACER at the disbursment month
                    disbursement_month = registry_plants[plant]["disbursement_month"] # month_number
                    disbursement_month_string = get_monthly_calendar().set_index("month_number").loc[disbursement_month,"month"] # string as YYYY-MM
                    users_investing_in_plant = [user for user, membership in membership_matrix[disbursement_month_string].iteritems() if membership == 1] # list of users who are member of the CACER at disbursment month
                    
                    # shortlisting to the actual users, who are shareholders and not dummy producers whose shares are owned by other CACER users 
                    users_investing_in_plant = [user for user in users_investing_in_plant if not registry_users[user]["dummy_user"]]

                    # print(users_investing_in_plant)
                    ################################ PER ORA USIAMO UN METODO EGUALITARIO, POI DA SOSTUIRE CON RIPARTIZIONE DA INPUT #############
                    share = ownership_share / len(users_investing_in_plant) #quota egualitaria
                    ################################################################################################################################
                    
                    inv_mat.loc[users_investing_in_plant,plant] += share 

                else: #cases of CACER and ESCo
                    inv_mat.loc[stakeholder,plant] += ownership_share
        
        assert abs(inv_mat[plant].sum() - 1) < 1e-5, "ERROR, sum of shares for plant <{}> different from 100%".format(plant)

    inv_mat.replace(0,"").to_csv(config["filename_investment_matrix"])
    print(inv_mat.replace(0,"")*100)

    print("\n**** Investment matrix created! ****")

    wb.close()
    app.quit()

    ####################################################################################################################################

def create_repartition_matrix():
    """ Generates a time-dependant matrix, reporting the incentives and valorization shares of each user/third party, as p.u. over 1.
    It assigns for each month the share based on the repartition_scheme indicated in the "inputs_FM.xlsx"s making a cross check on which users are active members of the CACER.
    It generates 3 repartition matrices for:
    1) incentives: shares of the TIP and Valorization for each user NOT EXCEEDING THE SURPLUS THRESHOLD INDICATED BY CACER DECREE (55% or 45% based on access to PNRR funding)
    2) CACER OPEX: share of the CACER handling OPEX, which could be deducted by the incentives and valorization before repartition (matematiacally it is obtained by indicating the same 
                repartition criteria of the "incentives") OR with a new different criteria, f.i. Public Administration or prosumers might decide to cover those costs to leave more 
                economic value for social purposes, etc
    3) surplus: shares of the TIP and Valorization for each user EXCEEDING THE SURPLUS THRESHOLD INDICATED BY CACER DECREE (55% or 45% based on access to PNRR funding)
    """

    print(blue("\nCreating repartition matrix:"))

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    output_file = config["filename_repartition_matrix"]

    # if not a CACER, then some repartition criteria could trigger the calculation, so we exit and move on
    # if recap["type_of_cacer"] not in ["AUC", "CER", "AID"]:
    #     print("NO INCENTIVES, NO REPARTITION MATRIX")
    #     return
    # THIS GENERATES ERRORS, AS ORIGINAL FILES ARE NOT OVERWRITTEN. TO BE FIXED
    
    writer = pd.ExcelWriter(output_file, engine = 'xlsxwriter')
    
    # we need to define 3 repartition matrices, for incentives (1), CACER opex (2) and surplus (3)
    for case in ["incentives", "CACER opex", "surplus"]:

        if case == "incentives":
            cacer_incentives = True
            surplus = False   
            repartition_scheme_active = "Incentives repartition scheme"
            input_file_repartition_sheet = "Repartition"
            print("\nCalculating Incentives Repartition Matrix")
        elif case == "CACER opex": 
            cacer_incentives = False
            surplus = False   
            repartition_scheme_active = "CACER opex repartition scheme"
            input_file_repartition_sheet = "Repartition"
            print("\nCalculating CACER OPEX Repartition Matrix")
            
        elif case == "surplus":
            cacer_incentives = True
            surplus = True   
            repartition_scheme_active = "Surplus repartition scheme"
            input_file_repartition_sheet = "Surplus"
            print("\nCalculating Surplus Repartition Matrix")

        registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))
        #filtering the user subset based on conditions
        filtered_users = [user for user in registry_users.keys() if not registry_users[user]["dummy_user"]] # removing dummy users

        if surplus: # as per DM CACER, only consumers different from industrial and commercial can receive the surplus
            filtered_users = [user for user in filtered_users if registry_users[user]["type"] != "producer"]

            #####################################################################################
            ## ATTENZIONE: la norma parla di 'consumatori diversi da imprese e/o utilizzato per finalità sociali con ricadute sul territorio'. 
            # Resta il dubbio sul significato di consumatore, perche il prosumer è consumatore e produttore. In attesa di chiarimento, qui interpretiamo il prosumer come consumatore, quindi che accede al fondo sociale
            #####################################################################################          

            filtered_users = [user for user in filtered_users if registry_users[user]["category"] not in ["industriale", "commerciale"]]

        months = get_monthly_calendar()["month"].to_list()
        df = pd.DataFrame(index=filtered_users, columns=months).fillna(0) # creating the Repartition Matrix as dataframe

        membership_matrix = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=1) # user_id as index, month "YYYY-MM" as column
        membership_matrix = membership_matrix.loc[filtered_users] # removing dummy users

        repartition_scheme_active = pd.read_excel(config["filename_input_FM_excel"], sheet_name="Scenario", index_col=0).loc[repartition_scheme_active,"Value"]
        repartition_scheme = pd.read_excel(config["filename_input_FM_excel"], sheet_name=input_file_repartition_sheet, index_col=0).loc[repartition_scheme_active].dropna() # selecting only the acrive repartition_scheme and removing the repartition_items with Nan
        # print(repartition_scheme)
        df.loc["CACER"] = 0 # initializing the CACER repartition share to 0. Needed even if remains 0

        for repartition_item, repartition_item_share in zip(repartition_scheme.index, repartition_scheme):
            
            if repartition_item == "Prosumers":

                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

                active_user_type = "prosumer"
                
                users_subset = [user for user in filtered_users if registry_users[user]["type"] == active_user_type]
                assert users_subset != [], f"ERROR: no non-dummy {active_user_type} found but repartition scheme allocating incentives to {repartition_item}"

                membership_matrix_subset = membership_matrix.loc[users_subset]
                membership_matrix_subset_totals = membership_matrix_subset.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                membership_matrix_subset_percentage = membership_matrix_subset / membership_matrix_subset_totals # calculating the share of each investor over the total over time
                membership_matrix_subset_percentage = membership_matrix_subset_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s
                
                cond_equal_1 = abs(membership_matrix_subset_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(membership_matrix_subset_percentage.sum() - 0) < 1e-5
                
                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error gets triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage do not add up to 100%"

                # df += membership_matrix_subset_percentage * repartition_item_share
                df = df.add(membership_matrix_subset_percentage * repartition_item_share, fill_value=0) # this is the correct way of doing it
            
            if repartition_item == "Consumers":
                
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

                active_user_type = "consumer"
                
                users_subset = [user for user in filtered_users if registry_users[user]["type"] == active_user_type]
                assert users_subset != [], f"ERROR: no non-dummy {active_user_type} found but repartition scheme allocating incentives to {repartition_item}"

                membership_matrix_subset = membership_matrix.loc[users_subset]
                membership_matrix_subset_totals = membership_matrix_subset.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                membership_matrix_subset_percentage = membership_matrix_subset / membership_matrix_subset_totals # calculating the share of each investor over the total over time
                membership_matrix_subset_percentage = membership_matrix_subset_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s
                
                cond_equal_1 = abs(membership_matrix_subset_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(membership_matrix_subset_percentage.sum() - 0) < 1e-5
                
                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error gets triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage do not add up to 100%"

                # df += membership_matrix_subset_percentage * repartition_item_share
                df = df.add(membership_matrix_subset_percentage * repartition_item_share, fill_value=0) # this is the correct way of doing it

            if repartition_item == "CACER members - fixed":
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

                assert filtered_users != [], f"ERROR: no non-dummy CACER members found but repartition scheme allocating incentives to {repartition_item}"

                # Assumption: considering the whole set of users present in the CACER for a particular month, without distinguishing prosumers, consumers or producers (but dummy users). In future a specific subset could be identified
                membership_matrix_totals = membership_matrix.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                membership_matrix_percentage = membership_matrix / membership_matrix_totals # calculating the share of each investor over the total over time
                membership_matrix_percentage = membership_matrix_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s
                
                cond_equal_1 = abs(membership_matrix_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(membership_matrix_percentage.sum() - 0) < 1e-5
                
                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error gets triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage do not add up to 100%"

                # df += membership_matrix_percentage * repartition_item_share
                df = df.add(membership_matrix_percentage * repartition_item_share, fill_value=0) # this is the correct way of doing it

            if repartition_item == "CACER members - variable":
                
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

                assert filtered_users != [], f"ERROR: no non-dummy CACER members found but repartition scheme allocating incentives to {repartition_item}"

                # Assumption: considering the whole set of users present in the CACER for a particular month, without distinguishing prosumers, consumers or producers (but dummy users). In future a specific subset could be identified
                # print(filtered_users)
                membership_matrix_subset = membership_matrix.loc[filtered_users] # removing dummy from set 
                consumption_matrix_subset = membership_matrix_subset.copy(deep=True) # creating a copy of the matrix, which will be filled with the kWh consumed in each month by each user

                #loop over user_types active in the CACER to retrieve the electricity withdrawal in each month
                for user_type in recap["list_user_types"]:
                    # series with the electricity withdrawal in each month in kWh (Eprel)
                    consumption = pd.read_excel(config["filename_CACER_energy_monthly"], sheet_name=user_type, index_col=0, header=0)["Eprel"] # user_id as index, month "YYYY-MM" as column
                    users_subset = [user for user in filtered_users if registry_users[user]["user_type"] == user_type]
                    # print(user_type)
                    consumption_matrix_subset.loc[users_subset] = membership_matrix_subset.loc[users_subset] * consumption

                # print(consumption_matrix_subset)

                consumption_matrix_subset_totals = consumption_matrix_subset.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                consumption_matrix_subset_percentage = consumption_matrix_subset / consumption_matrix_subset_totals # calculating the share of each investor over the total over time
                consumption_matrix_subset_percentage = consumption_matrix_subset_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s

                cond_equal_1 = abs(consumption_matrix_subset_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(consumption_matrix_subset_percentage.sum() - 0) < 1e-5

                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error gets triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage do not add up to 100%"

                # df += consumption_matrix_subset_percentage * repartition_item_share
                df = df.add(consumption_matrix_subset_percentage * repartition_item_share, fill_value=0) # this is the correct way of doing it
            
            if repartition_item == "ESCo":
                #####################
                # TO BE IMPELEMENTED
                #####################
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

            if repartition_item == "CACER":
                
                df.loc["CACER"] = repartition_item_share
                
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

            if repartition_item == "Social Fund":
                
                df.loc["social_fund"] = repartition_item_share
                
                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

            if repartition_item == "Surplus CACER users":

                print(f" - {repartition_item} = {repartition_item_share*100:,.1f}% share")

                assert filtered_users != [], f"ERROR: no non-dummy CACER members found but repartition scheme allocating incentives to {repartition_item}"
    
                membership_matrix_subset = membership_matrix.loc[filtered_users]
                membership_matrix_subset_totals = membership_matrix_subset.sum() # to calculate the ownership shares between investors, we count how many of them are still member of the CACER over time, as some may eventually leave the CACER leaving their shares to the others
                membership_matrix_subset_percentage = membership_matrix_subset / membership_matrix_subset_totals # calculating the share of each investor over the total over time
                membership_matrix_subset_percentage = membership_matrix_subset_percentage.fillna(0) # if there are no members in a month, it returns Nan. If so, we replace them with 0s
                
                cond_equal_1 = abs(membership_matrix_subset_percentage.sum() - 1) < 1e-5
                cond_equal_0 = abs(membership_matrix_subset_percentage.sum() - 0) < 1e-5
                
                # sum of each membership_matrix_percentage month shall be 0 or 100%. If not, Error gets triggered
                assert (cond_equal_1 + cond_equal_0).all(), f"ERROR: some columns in membership_matrix_percentage do not add up to 100%"

                # df += membership_matrix_subset_percentage * repartition_item_share
                df = df.add(membership_matrix_subset_percentage * repartition_item_share, fill_value=0) # this is the correct way of doing it

            # print(df) 

        # Chcking the calculation was successful
        cond_equal_1 = abs(df.sum() - 1) < 1e-5 #  sum of each month shall be 100%. If not, Error gets triggered
        assert (cond_equal_1).all(), f"ERROR: some columns in repartition_matrix do not add up to 100%"

        # adjusting format for export
        df.loc["month"] = df.columns.tolist()
        df = pd.concat([df.loc[['month'],:], df.drop('month', axis=0)], axis=0) # bringing the month "YYYY-MM" row to the top pf the dataframe
        df.columns = list(get_monthly_calendar()["month_number"]) # updating the columns to month_number, not month, so it's more intuitive for user

        df.to_excel(writer, sheet_name= case) #saving for the record

    print("\n**** Repartition Matrix successfully created! ****")

    writer.close()

####################################################################################################################################

def calculate_capex_for_item(capex_item, item_size, replacement=False):
    """
    This function calculates the Capex for a given item, given its size and whether it's a replacement or not.

    Parameters:
    capex_item (str): the item for which the Capex shall be calculated. It shall be one of the items in the "capex_table" in the "CAPEX" excel sheet
    item_size (float): the size of the item in the relevant units (e.g. kWp, kWh)
    replacement (bool): whether this is a replacement item or not. Default is False

    Returns:
    capex_value (float): the calculated Capex value in €
    """

    # getting the cost per unit [€/kWp or €/kWh]
    if replacement:
        cost_per_unit = capex_costs_per_item.loc["replacement_cost_per_unit",capex_item]
    else:
        cost_per_unit = capex_costs_per_item.loc["cost_per_unit",capex_item]

    # getting the scale factor
    scale_factor_active_bin = np.digitize(item_size,scale_factor["Pmax"]) # checking in which bin on the Pmax the item_size falls into, saving the row number
    scale_factor_active = scale_factor.loc[scale_factor_active_bin,capex_item] # estracting the related scale factor for the given item and item_size, in p.u.

    if capex_item == "mv_cabinet": item_size = 1 # the mv_cabinet cost is not given per unit as others, but per single item with scale factor correction. So we overwrite the item_size to 1 to remove direct correlation in the fomula below
    
    capex_value = scale_factor_active * item_size * cost_per_unit
    
    if item_size>0:
        # printing the results, for visual check
        print("CHECK: item= {},\t size = {},\t scale factor found: {:.2f},\t capex €: {:.2f}".format(capex_item, item_size, scale_factor_active, capex_value))
    
    return float(capex_value)

def plant_capex_breakdown():

    """
    Function to execute the capex calculation over all the plants for every component, and save the results in the "registry_plants.yml" file.
    This is later used to calculate the D&A and assign the cash flows in time
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    # creating dictionary with all capex costs
    global capex_costs_per_item, scale_factor
    
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    capex_costs_per_item = wb.sheets["CAPEX"]["capex_table"].options(pd.Series, header=1, index=True, expand='table').value
    scale_factor = wb.sheets["CAPEX"]["scale_factor_table"].options(pd.Series, header=1, index=False, expand='table').value
    plants = yaml.safe_load(open(config["filename_registry_plants_yml"],"r"))

    for plant in plants.keys():
        # updating "registry_plants.yml" with capex info, based on inputs processing
        capex_breakdown = {}

        for capex_item in ["pv","battery","wind"]:
            item_size = plants[plant][capex_item] # in kWp or kWh, size of the component for the given plant
            # print(capex_item)
            # print(item_size)
            # if the size is null or 0, we move to the next item
            if item_size == None or item_size == np.nan: 
                # continue
                item_size = 0

            capex_breakdown["capex_" + capex_item] = calculate_capex_for_item(capex_item, item_size) # populating the dictionary with the final value for the whole plant in €
            # capex_breakdown["capex_" + capex_item] = suppress_printing(calculate_capex_for_item, capex_item, item_size)

        ############################### repeating for the pv inverter
        capex_item = "pv_inverter"
        item_size = plants[plant]["pv"] * 0.8 # in kWp, ASSUMPTION: as rule of thumb, we assume the inverter kVA equal to 80% of the installed pv capacity
        capex_breakdown["capex_" + capex_item] = calculate_capex_for_item(capex_item, item_size)

        ############################### repeating for the mv cabinet
        capex_item = "mv_cabinet"
        item_size = (plants[plant]["pv"] + plants[plant]["wind"]) # in kWp, ASSUMPTION: as rule of thumb, we assume the MV cabinet in kVA equal to 100% of the sum of installed pv + wind capacity
        item_size *= (plants[plant]["mv_cabinet"] == True)  # check if mv_cabinet is present for this plant. If not, size becomes 0
        capex_breakdown["capex_" + capex_item] = calculate_capex_for_item(capex_item, item_size) # populating the dictionary with the final value for the whole plant in €

        ############################## replacement pv inverter
        capex_item = "pv_inverter"
        replacement_flag = capex_costs_per_item.loc["replacement_flag", capex_item]
        if replacement_flag: 
            item_size = plants[plant]["pv"] * 0.8 # in kWp, ASSUMPTION: as rule of thumb, we assume the inverter kVA equal to 80% of the installed pv capacity
            capex_breakdown["capex_replacement_" + capex_item] = calculate_capex_for_item(capex_item, item_size, replacement=True)

        ############################## replacement battery
        capex_item = "battery"
        replacement_flag = capex_costs_per_item.loc["replacement_flag", capex_item]
        if replacement_flag: 
            item_size = plants[plant]["battery"] # in kWh
            capex_breakdown["capex_replacement_" + capex_item] = calculate_capex_for_item(capex_item, item_size, replacement=True)

        # saving capex breakdown in plants dictionary
        plants[plant].update(capex_breakdown)

    # updating registry_plants yml file with new capex info
    with open(config["filename_registry_plants_yml"], "w") as f:
        yaml.safe_dump(plants, f)
    
    wb.close()
    # app.quit()

####################################################################################################################################

def cash_flows_per_user(user = "CACER"):
    """ function to assign the capex related to the specified user/configuration, for all the assets related to such user/configuration
    It is composed of 2 sections: 
    1) ASSETS: importing data from existing plants' capex, depreciation, debt and opex calculation and for all it obtains the user's share based on the ownership matrix. 
    2) CACER: calculating the user's share of project development and deployment of the CACER (legal expenses, entry fee, feasibility studies, etc) based on inputs.
    
    It exports details of each asset and for the CACER as separate sheets in output excel file, for consultation and debugging purpose. 

    The aggregation of all expense items is reported in the "totals" sheet, which is the core output of the function which is the input of next steps in the Financial Model. 
    """

    flag_user_is_cacer = user == "CACER" 

    global user_investment, da_per_item, duration_per_item, writer, config, capex_costs_per_item, registry_users, entry_fee
    config = yaml.safe_load(open("config.yml", 'r'))

    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

    inv_mat = pd.read_csv(config["filename_investment_matrix"],index_col=0)
    
    user_investment = inv_mat.loc[user,:].dropna()
    
    user_plants = list(user_investment.index) # this is the list of the plants' names in which our user has shares
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))

    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])
    active_cacer_kickoff = wb.sheets["CAPEX"]["active_cacer_kickoff"].value * (recap["type_of_cacer"] == "CER") # if not CER, then shall be 0, as no new legal entity is needed
    
    # cacer_kickoff_costs can be "CACER" or "all users at month 1". If CACER, only the CACER legal entity will bear the capex costs, 
    # and users only pay the entry fee, otherwise all users present in month 1 will split equally the cacer kickoff costs
    cacer_kickoff_costs_users = wb.sheets["Scenario"]["A1"].options(pd.DataFrame, header=1, index=True, expand='table').value.loc["CACER kickoff costs","Value"]
    if cacer_kickoff_costs_users == "CACER":
        cacer_kickoff = - abs(active_cacer_kickoff) * flag_user_is_cacer
    else: # splitting between all cacer users present at month 1     
        users_present_month_1 = recap["users_present_month_1"]
        users_present_month_1_non_dummy = [user for user in users_present_month_1 if not registry_users[user]["dummy_user"]]
        assert len(users_present_month_1_non_dummy) > 0, "ERROR: currently we need at least one user to be present at month 1 to bear cacer kickoff costs"
        cacer_kickoff = - abs(active_cacer_kickoff) / len(users_present_month_1_non_dummy) # must be negative as it is an expense
        cacer_kickoff = cacer_kickoff * (flag_user_is_cacer == False) # if user is CACER, then goes to 0

    capex_costs_per_item = wb.sheets["CAPEX"]["capex_table"].options(pd.Series, header=1, index=True, expand='table').value
    da_per_item = capex_costs_per_item.loc["amortization",:]
    duration_per_item = capex_costs_per_item.loc["duration",:]

    #CAPEX from assets ################################################################################################
    if not flag_user_is_cacer:
        user_category = registry_users[user]["category"]
        df_totals = get_FM_template(user_category) # month as index
    else:
        df_totals = get_FM_template("CACER") # month as index

    df_totals["capex_total"] = 0
    df_totals["da_total"] = 0
    df_totals["debt_interest"] = 0
    df_totals["opex_total"] = 0
    df_totals["revenues_total"] = 0

    writer = pd.ExcelWriter(config["foldername_finance_users"]+"//"+user+".xlsx", engine = 'xlsxwriter')

    ################################################### ASSETS ###############################################################
    if user_plants != []:
        print(f"\nUser {blue(user)} owning:")

    for plant in user_plants:

        df = cash_flows_per_user_per_plant(plant, user)

        df.T.to_excel(writer, sheet_name= plant) #saving for the record
      
        capex_cols = [col for col in list(df.columns) if col.startswith("capex_")]
        da_cols = [col for col in list(df.columns) if col.startswith("da_")]
        opex_cols = [col for col in list(df.columns) if col.startswith("opex_")]
        revenues_cols = [col for col in list(df.columns) if col.startswith("revenues_")]
        
        df_totals["capex_total"] += df[capex_cols].sum(axis=1)
        df_totals["da_total"] += df[da_cols].sum(axis=1)
        df_totals["debt_interest"] += df["debt_interest"]
        df_totals["opex_total"] += df[opex_cols].sum(axis=1)
        df_totals["revenues_total"] += df[revenues_cols].sum(axis=1)
    
    ################################################### CACER ###############################################################

    df = get_FM_template()

    # if the configuration is not a CACER (f.i we could be simulating a BAU case or an isolated prosumer not in a CER), then no need to fill the CACER sheet, just export it blank and moving on
    
    if recap["type_of_cacer"] in ["CER", "AUC", "AID"]:

        ####################### CAPEX for Project development and CACER setup and kickoff
        
        if recap["type_of_cacer"] == "CER":
            if flag_user_is_cacer:
                entry_fee = + abs(wb.sheets["CAPEX"]["entry_fee"].value) # in this case for the CACER it's a revenue, thus positive 
                entry_matrix = pd.read_csv(config["filename_user_entry_matrix"], index_col=0, header=0).T.drop(columns="month").astype(int)
                entry_matrix.index = entry_matrix.index.astype(int) # making sure the index are integers
                entry_matrix_totals = entry_matrix.sum(axis = 1) # assumption: all users are paying the same entry fee, disregarding their type
                df["revenues_entry_fee"] = + abs(entry_fee) * entry_matrix_totals * df["inflation_factor"]
                assert not df['revenues_entry_fee'].isna().any(), "ERROR: There are NaN values in the entry fees"

            else:
                entry_fee = - abs(wb.sheets["CAPEX"]["entry_fee"].value)
                entry_matrix_user = pd.read_csv(config["filename_user_entry_matrix"], index_col=0, header=0).T[user].astype(int)
                entry_matrix_user.index = entry_matrix_user.index.astype(int) # making sure the index are integers
                df["capex_entry_fee"] = entry_fee * entry_matrix_user * df["inflation_factor"] 
                assert not df['capex_entry_fee'].isna().any(), "ERROR: There are NaN values in the entry fees"
                # this cost is not considered in the DA calculation, as assumed to be a subscription fee, not an investment in asset eligible for taxation calculation

        df["capex_cacer_kickoff"] = 0 # initialization
        df.loc[1,"capex_cacer_kickoff"] += cacer_kickoff # adding the cacer_kickoff in month 1 (if not funder, then cacer_kickoff is 0)

        ####################### REVENUES generated from the CACER (incentives and valorization)

        df_incentives = pd.read_csv(config["filename_CACER_incentivi"], index_col=0).reset_index().set_index(df.index)
        # incentives_user_repartition_share = pd.read_csv(config["filename_incentives_repartition_matrix"], index_col=0).loc[user].astype(float) # Series
        incentives_user_repartition_share = pd.read_excel(config["filename_repartition_matrix"], sheet_name="incentives", index_col=0).loc[user].astype(float) # Series
        
        # incentives_user_repartition_share = pd.read_excel(config["filename_ownership_matrix"], index_col=0, sheet_name=plant).loc[user] # series of floats, index are month_number
        incentives_user_repartition_share.index = incentives_user_repartition_share.index.astype(int) # making sure the index are integers

        # please note: we shall not not apply inflation to the incentives, as TIP is fixed by decree. Inflation only applies to valorization, which is updated by ARERA on quartely basis
        if flag_user_is_cacer:
            # in case of CACER, we want to explicitely keep track the cash in and out from GSE. Mathematically it's the same as below, but still we bring evidence of the transactions
            df["revenues_incentives_from_GSE"] =  + df_incentives["incentivo"] # 100%, cash in, positive
            df["opex_incentives_repartition"] = - df_incentives["incentivo"] * (1 - incentives_user_repartition_share)# cash out, negative
            df["revenues_valorization_from_GSE"] = + df_incentives["valorizzazione"] * 1 * df["inflation_factor"] # 100%, cash in, positive
            df["opex_valorization_repartition"] = - df_incentives["valorizzazione"] * (1 - incentives_user_repartition_share) * df["inflation_factor"]# cash out, negative
            # making sure there are no NaN values, which happens if indeces are not aligned
            assert not df['revenues_incentives_from_GSE'].isna().any(), "ERROR: There are NaN values in the CACER incentives revenue"
            assert not df['revenues_valorization_from_GSE'].isna().any(), "ERROR: There are NaN values in the CACER valorization revenue"
            assert not df['opex_incentives_repartition'].isna().any(), "ERROR: There are NaN values in the CACER incentives repartition"
            assert not df['opex_valorization_repartition'].isna().any(), "ERROR: There are NaN values in the CACER valorization repartition"
            
            # incentive from the surplus repartition, not included in the above
            surplus_repartition_matrix = pd.read_excel(config["filename_repartition_matrix"], sheet_name="surplus", index_col=0).T
            surplus_user_repartition_share = surplus_repartition_matrix[user].astype(float) # Series
            df["revenues_surplus_from_GSE"] = df_incentives["surplus"]
            df["opex_surplus_redistribution"] = - df_incentives["surplus"] * (1 - surplus_user_repartition_share)
            assert not df['revenues_incentives_from_GSE'].isna().any(), "ERROR: There are NaN values in the CACER incentives revenue"
            assert not df['revenues_valorization_from_GSE'].isna().any(), "ERROR: There are NaN values in the CACER valorization revenue"
        else: 
            df["revenues_incentives"] = df_incentives["incentivo"] * incentives_user_repartition_share 
            df["revenues_valorization"] = df_incentives["valorizzazione"] * incentives_user_repartition_share * df["inflation_factor"]
            # making sure there are no NaN values, which happens if indeces are not aligned
            assert not df['revenues_incentives'].isna().any(), "ERROR: There are NaN values in the incentives revenue"
            assert not df['revenues_valorization'].isna().any(), "ERROR:There are NaN values in the valorization revenue"

            # incentive from the surplus repartition
            # please note: we shall not not apply inflation to the surplus incentives, as TIP is fixed by decree. 
            surplus_repartition_matrix = pd.read_excel(config["filename_repartition_matrix"], sheet_name="surplus", index_col=0).T
            if user in surplus_repartition_matrix.columns: 
                surplus_user_repartition_share = surplus_repartition_matrix[user].astype(float) # Series
                df["revenues_surplus"] = df_incentives["surplus"] * surplus_user_repartition_share

        ####################### OPEX generated from the CACER 
        ###################################################################
        # DA CAMBIARE LOGICA: COSTRUIRE IL CASH FLOW DELLA CACER CON REVENUES E OPEX E POI SUDDIVIDERE PER UTENTI 
        ####################################################################

        if recap["type_of_cacer"] == "CER":

            subscription_fee = - abs(wb.sheets["OPEX"]["subscription_fee"].value)
            if flag_user_is_cacer:
                subscription_matrix = pd.read_csv(config["filename_subscription_matrix"], index_col=0, header=0).T.drop(columns="month").astype(int)
                subscription_matrix.index = subscription_matrix.index.astype(int) # making sure the index are integers
                subscription_matrix_totals = subscription_matrix.sum(axis = 1) # assumption: all users are paying the same subscription fee, disregarding their type
                df["revenues_subscription_fee"] = + abs(subscription_fee) * subscription_matrix_totals * df["inflation_factor"] # Note: subscription fee is negative, but from CACER pov is a revenue and must be set positive
                assert not df['revenues_subscription_fee'].isna().any(), "ERROR:There are NaN values in the subscription fees"
            
            else:
                subscription_matrix_user = pd.read_csv(config["filename_subscription_matrix"], index_col=0, header=0).T[user].astype(int)
                subscription_matrix_user.index = subscription_matrix_user.index.astype(int) # making sure the index are integers
                df["opex_subscription_fee"] = subscription_fee * subscription_matrix_user * df["inflation_factor"] 
                assert not df['opex_subscription_fee'].isna().any(), "ERROR:There are NaN values in the subscription fees"

        opex_CACER_table = wb.sheets["OPEX"]["opex_CACER_table"].options(pd.Series, header=1, index=True, expand='table').value

        opex_user_repartition_share = pd.read_excel(config["filename_repartition_matrix"], sheet_name="CACER opex", index_col=0).loc[user].astype(float) # Series
        opex_user_repartition_share.index = opex_user_repartition_share.index.astype(int) # making sure the index are integers

        membership_matrix = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=0).T.drop(columns="month").astype(int) # index is month number. TO BE FIXED
        membership_matrix_total = membership_matrix.sum(axis = 1) # series wit number of existing members for each month
        membership_matrix_total.index = membership_matrix_total.index.astype(int) # making sure the index are integers
        
        CACER_GSE_fees_value = opex_CACER_table.loc["CACER_GSE_fees_per_configuration","Value"] * len(recap["configurations"]) # per configuration per year
        df["opex_CACER_GSE_fees"] = - opex_user_repartition_share * CACER_GSE_fees_value * df["inflation_factor"] / 12

        # taking the administration expenses only if the CACER is not an AUC, case in which these expenses are already present in the BAU conditions and thus not related to the CACER
        administration_value = opex_CACER_table.loc["administration","Value"] * (recap["type_of_cacer"] == "CER") # per cacer per year
        df["opex_administration"] = - opex_user_repartition_share * administration_value * df["inflation_factor"] / 12 

        cacer_management_platform_fixed_value = opex_CACER_table.loc["cacer_management_platform_fixed","Value"] # per CACER per year
        cacer_management_platform_variable_value = opex_CACER_table.loc["cacer_management_platform_variable","Value"] # per user per year
        df["opex_cacer_management_platform"] = - (cacer_management_platform_variable_value * membership_matrix_total + cacer_management_platform_fixed_value) * opex_user_repartition_share * df["inflation_factor"] / 12 # this cost is per user already

        # making sure there are no NaN values, which happens if indeces are not aligned
        assert not df['opex_CACER_GSE_fees'].isna().any(), "ERROR: There are NaN values in the opex_CACER_GSE_fees"
        assert not df['opex_administration'].isna().any(), "ERROR:There are NaN values in the opex_administration"
        assert not df['opex_cacer_management_platform'].isna().any(), "ERROR:There are NaN values in the opex_cacer_management_platform"

    # saving
    df.T.to_excel(writer, sheet_name= "CACER") #saving for the record

    if flag_user_is_cacer:
        total_incentives = sum(df[["revenues_incentives_from_GSE","revenues_valorization_from_GSE","revenues_surplus_from_GSE"]].sum())
        total_CACER_survival_costs = sum(df[["opex_CACER_GSE_fees","opex_administration","opex_cacer_management_platform"]].sum())
        incentives_sustainment_ratio = abs(total_CACER_survival_costs / total_incentives)
        print(f"\nCACER entity sustainment ratio: {incentives_sustainment_ratio*100:,.1f} % share")

    # ADD HERE OTHER SOURCES OF CAPEX RELATED TO THE CACER ONLY

    # updating the total calculation
    capex_cols = [col for col in list(df.columns) if col.startswith("capex_")]
    revenues_cols = [col for col in list(df.columns) if col.startswith("revenues_")]
    opex_cols = [col for col in list(df.columns) if col.startswith("opex_")]
    df_totals["capex_total"] += df[capex_cols].sum(axis=1)
    df_totals["revenues_total"] += df[revenues_cols].sum(axis=1)
    df_totals["opex_total"] += df[opex_cols].sum(axis=1)
 
    # saving the totals 
    df_totals.T.to_excel(writer, sheet_name= "totals") #saving for the record
    writer.close() # if DCF_analysis() function uses xlwings, the writer must be closed !!!
    wb.close()
    # app.quit()
    ################################################### Discounted Cash Flow and IRR ###############################################################    

    DCF_analysis(user) # discounted cash flow analysis on the obtained results

    return df

def cash_flows_per_user_per_plant(plant, user):

    """ function to assign all cash flows related to the specified user related to a single plant. These include:
    - Plant Capex, debt and amortization --> based on investment_matrix
    - Plant Opex --> based on ownership_matrix
    - Revenues RID (energy sales) --> based on ownership_matrix
    - Revenues electricity bills reduction (indirect benefit applicable to prosumers only) --> based on membership_matrix and plant_operation_matrix

        Importing data from existing plants' capex, depreciation, debt and opex calculation and for all it obtains the user's share based on the ownership matrix. 
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    user_investment_share = pd.read_csv(config["filename_investment_matrix"],index_col=0).loc[user,plant] # single float
    user_ownership_share = pd.read_excel(config["filename_ownership_matrix"], index_col=0, sheet_name=plant).loc[user] # series of floats, index are month_number
    print(f"- plant {plant} with {user_investment_share*100:,.1f}% share")

    assert user_investment_share <= 1, f"ERROR. Plant {plant}: User Ownership Share value invalid: beyond 100%"

    first_iteration_flag = True

    for sheet in ["Capex", "D&A", "Debt", "Opex", "Revenues"]: 
        
        # importing the data of the specific plant and sheet
        df = pd.read_excel(config["foldername_finance_plants"]+"//"+plant+".xlsx", sheet_name=sheet, index_col=0, header=0).T # index is items, month_number on columns

        # Initialization of results dataframe
        if first_iteration_flag: 
            df_result = df.copy(deep=True) # index is items, month_number on columns
            first_iteration_flag = False

        values_col = list(df.columns)
        if "month" in values_col: values_col.remove("month")

        if sheet in ["Capex", "D&A", "Debt"]: 
        # CAPEX, DA and Debt are split according to the user_investment_share, as they only refer to the disbursment month
            df_result[values_col] = df[values_col] * user_investment_share # user_investment_share is a scalar
        else: 
        # OPEX and revenues(RID), on the other hand, are split according to the user_ownership_share, which can change in time as members may choose to exit the CACER
            df_result[values_col] = (df[values_col].T * user_ownership_share).T # user_ownership_share is a string of float

        
    #  REVENUES FROM ELECTRICITY BILLS RELATED TO TITOLARE POD AND MEMBERSHIP MATRIX E PLANT OPERATION MATRIX
    
    if registry_plants[plant]["titolare_POD"] == user and registry_users[user]["type"] == "prosumer": 
        membership_matrix_user = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=1).T[user] # month "YYYY-MM" as index
        plant_operation_matrix_plant = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_operation_matrix", index_col=0, header=1).T[plant] # month "YYYY-MM" as index

        user_type = registry_plants[plant]["user_type"]

        filename = config["foldername_bills"] + user_type + ".xlsx"
        df_user_tariff_bau = pd.read_excel(filename, sheet_name="bau", index_col="month")
        df_user_tariff_pv = pd.read_excel(filename, sheet_name="pv", index_col="month")
        revenues_electricity_savings = df_user_tariff_bau["total_bill_cost"] - df_user_tariff_pv["total_bill_cost"]
        revenues_electricity_savings = revenues_electricity_savings * membership_matrix_user * plant_operation_matrix_plant # verifying that the plant is operational in the given month and member of the CACER
        revenues_electricity_savings = revenues_electricity_savings * get_FM_template()["inflation_factor"].values #from nominal to real
        revenues_electricity_savings = revenues_electricity_savings.rename("revenues_electricity_savings")

        assert not revenues_electricity_savings.lt(0).any(), "ERROR: There are negative savings in the electricity bill"

        # merging electricity_bill_savings on df_result
        df_result["revenues_electricity_savings"] = revenues_electricity_savings.values # this method would also be ok, but if indexes gets mixed up, it might compromise the results without triggering an error
        # df_result = pd.merge(df_result, revenues_electricity_savings, on=["month", "month"]) # this method triggers the error, as index is reset. To be fixed
        assert not df_result.isna().any().sum(), "ERROR: There are Nan values in totals dataframe"

    # in case of AUC, the prosumer is the condominium, which is a dummy user and the savings shall be split between the other users, as they are the ones paying the bills
    df_result["revenues_condominium_electricity_savings"] = 0 # initializing, if not AUC it remains 0
    if recap["type_of_cacer"] == "AUC":
        # calculating the savings for the condominium
        membership_matrix_user = pd.read_csv(config["filename_membership_matrix"], index_col=0, header=1).T[user] # month "YYYY-MM" as index
        plant_operation_matrix_plant = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_operation_matrix", index_col=0, header=1).T[plant] # month "YYYY-MM" as index

        user_type = registry_plants[plant]["user_type"]

        filename = config["foldername_bills"] + user_type + ".xlsx"
        df_user_tariff_bau = pd.read_excel(filename, sheet_name="bau", index_col="month")
        df_user_tariff_pv = pd.read_excel(filename, sheet_name="pv", index_col="month")
        revenues_condominium_electricity_savings = df_user_tariff_bau["total_bill_cost"] - df_user_tariff_pv["total_bill_cost"]
        revenues_condominium_electricity_savings = revenues_condominium_electricity_savings * membership_matrix_user * plant_operation_matrix_plant # verifying that the plant is operational in the given month and member of the CACER
        revenues_condominium_electricity_savings = revenues_condominium_electricity_savings * get_FM_template()["inflation_factor"].values #from nominal to real
        revenues_condominium_electricity_savings = revenues_condominium_electricity_savings.rename("revenues_condominium_electricity_savings")

        assert not revenues_condominium_electricity_savings.lt(0).any(), "ERROR: There are negative savings in the electricity bill"

        # merging electricity_bill_savings on df_result
        df_result["revenues_condominium_electricity_savings"] = revenues_condominium_electricity_savings.values / recap["total_non_dummy_CACER_members"]  # this method would also be ok, but if indexes gets mixed up, it might compromise the results without triggering an error

        assert not df_result.isna().any().sum(), "ERROR: There are Nan values in totals dataframe"

    #  OPEX FROM PPA ELECTRICITY BILLS RELATED TO PRESENCE OF ESCO
    ######################## To be implemented

    return df_result

def cash_flows_for_all_plants():
    """Function to execute the capex and D&A calculation over all the plants"""

    print(blue("\nCalculate cash flows for all power plants:", ['bold', 'underlined']), '\n')

    plant_capex_breakdown() # updating the "registry_plants.yml" with capex details needed for the incoming steps

    config = yaml.safe_load(open("config.yml", 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))

    clear_folder_content(config["foldername_finance_plants"])

    for plant in registry_plants:
        cash_flows_per_plant(plant)
        print(f"Plant {plant} capex calculation successful")
    
    print("\n**** All plants Capex calculation executed! ****")

def cash_flows_for_all_users():
    """ function to loop the capex and D&A calculation over all the users. Chronologically, this step must come after the 
    cash_flows_for_all_plants() execution, as takes the plants data from the plants cash flows"""

    print(blue("\nCalculate cash flows for all users:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

    clear_folder_content(config["foldername_finance_users"])

    for user in registry_users:
        
        if registry_users[user]["dummy_user"]: 
            print(f"Skipping dummy user {user} of type {registry_users[user]['user_type']}")
            continue # skipping dummy users

        cash_flows_per_user(user)
        print(f"User {blue(user)} calculation successful\n")
    
    # CACER
    if not recap["type_of_cacer"] == "NO_CACER":
        cash_flows_per_user("CACER")

    # Organizing the results for the social fund
    df_social_fund = get_FM_template() # month as index
    df_social_fund["revenues_social_fund"] = pd.read_csv(config["filename_CACER_incentivi"]).set_index("month_number")["social_fund"] * df_social_fund["inflation_factor"] 
    # df_social_fund.T.to_excel(config["foldername_finance_users"]+"//social_fund.xlsx", sheet_name= "totals")
    df_social_fund.T.to_excel(config["foldername_finance_users"]+"//social_fund.xlsx", sheet_name= "CACER")

    print("\n**** All Users Capex calculation executed! ****")
    
def cash_flows_per_plant(plant):
    """Core Fìfunction for the plant cash flows, it generates a breakdown of non energy-related cashflows, which are:
        - CAPEX
        - Depreciation & Amortization (referred to as DA) for fiscal purpose (ammortamento fiscale) of assets, fot the specific cathegory of user.
        - Debt (when applicable) and repayments
        - OPEX
    
    To simplify, the DA is calculated with a straight-line approach (metodo lineare), with salvage value (valore residuale) of the asset equal to 0 at end of lifetime.
    See here for more info: https://www.indeed.com/career-advice/career-development/straight-line-depreciation
    """

    global config

    config = yaml.safe_load(open("config.yml", 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))

    if not registry_plants[plant]["new_plant"]:
        print(f"Plant {blue(plant)} existed before the CACER constitution, so the capex calculation will not be performed")
        #exiting the function
        return 

    item_list = ["pv","pv_inverter","battery","wind","mv_cabinet","grant_pnrr","grant_private"]
    capex_item_list = ["capex_" + x for x in item_list] 
    replacement_item_list = ["replacement_battery","replacement_pv_inverter"]
    capex_replacement_item_list = ["capex_" + x for x in replacement_item_list] 
    # each capex item will have a correspondent amortization 
    da_item_list = ["da_" + x for x in item_list] 
    da_replacement_item_list = ["da_" + x for x in replacement_item_list] 

    app = xw.App(visible=False) # opening in background
    wb = xw.Book(config["filename_input_FM_excel"])
    
    capex_costs_per_item = wb.sheets["CAPEX"]["capex_table"].options(pd.Series, header=1, index=True, expand='table').value
    ground_mounted_factor = wb.sheets["CAPEX"]["capex_ground_factor"].value # valid for both capex and opex
    da_per_item = capex_costs_per_item.loc["amortization",:]

    disbursement_month = registry_plants[plant]["disbursement_month"] # month in which the investment is issued
    if np.isnan(disbursement_month):
        disbursement_month = 1
    commissioning_month = registry_plants[plant]["commissioning_month"]
    if np.isnan(commissioning_month):
        commissioning_month = 1
    # exit_month = registry_plants[plant]["exit_month"]

    ##########################################################################################################
    # CAPEX AND AMORTIZATION #################################################################################
    ##########################################################################################################

    print(f"\nPlant: {blue(plant)} of {registry_plants[plant]['pv'] + registry_plants[plant]['wind']}kW and {registry_plants[plant]['battery']}kWh")

    user_category = registry_plants[plant]["category"]
    df = get_FM_template() # dataframe initialization

    #capex inizialization
    df[capex_item_list] = 0
    df[capex_replacement_item_list] = 0
    df[da_item_list] = 0
    df[da_replacement_item_list] = 0

    total_plant_capex = 0

    for item in ["pv", "pv_inverter", "battery", "wind", "mv_cabinet"]:
        capex_item = "capex_" + item
        
        ### CAPEX

        # allocating capex expenses at the "disbursement_month". Must be updating the existing value, to prevent overwriting previous values
 
        capex_value = - registry_plants[plant][capex_item] * df.loc[disbursement_month,"inflation_factor"] # sign convention: negative for disbursment, positive for incoming cash flow
        
        # increasing if pv is mounted on ground
        if item == "pv" and registry_plants[plant]["pv_mounting"] == "ground":
            capex_value *= ground_mounted_factor

        df.loc[disbursement_month,capex_item] += capex_value
        print(f"\t- Capex {item}:€ {capex_value:,.2f}")

        total_plant_capex += capex_value # updating total capex of the plant for the given customer

        da_months = min(da_per_item[item] * 12, config["project_lifetime_yrs"]*12 - commissioning_month) #we make sure the da time from filename_registry_plants_ymlssioning does not exceed that project lifetime

        ### Depreciation & Amortization of capex item

        da_amount = capex_value / da_months
        da_indexes = np.logical_and(df.index < (da_months + disbursement_month), df.index >= disbursement_month ) # finding the indexes of the month which satifly the 2 conditions
        df.loc[da_indexes, "da_" + item] += da_amount

        assert abs(capex_value - df["da_" + item].sum()) < 0.0001, f"Error in calculating the amortization of plant: {plant}, item: {item}"

    # BIG Assumption here: all costs are admissible for grants
    capex_value_admittable_for_grants = total_plant_capex
    print(f"TOTAL CAPEX: € {capex_value_admittable_for_grants:,.2f}")

    # GRANTS ################################################################################################################

    for item in ["grant_pnrr","grant_private"]:

        #allocating grants at the filename_registry_plants_ymlssioning month  

        grant_pu = registry_plants[plant][item] # it's the grant in per unit over the total project cost
        capex_value = 0 # resetting

        if grant_pu > 0: 
            
            capex_value = - grant_pu * capex_value_admittable_for_grants  # sign convention: negative for disbursment, positive for incoming cash flow. No need for inflation, as capex_value_admittable_for_grants is already inflated
            
            assert capex_value >= 0, f"ERROR in calculating the grant of plant: the value is negative while by convention it should be positive"
            print(f"{item} applied for {grant_pu*100:,.0f}% over total: € {capex_value:,.2f}")
            df.loc[disbursement_month,"capex_"+item] += capex_value

            da_months = min(da_per_item["pv"] * 12, config["project_lifetime_yrs"]*12 - disbursement_month) # for grants, we consider the pv as reference

            # da of capex item
            da_amount = capex_value / da_months
            da_indexes = np.logical_and(df.index < (da_months + disbursement_month), df.index >= disbursement_month ) # finding the indexes of the month which satifly the 2 conditions
            df.loc[da_indexes, "da_" + item] += da_amount
            # print(f"capex_value = {capex_value}")
            # print(f"da_amount= {da_amount}")
            # print(f"da_months= {da_months}")
            # print(df["da_" + item].sum())
            assert abs(capex_value - df["da_" + item].sum()) < 0.0001, f"ERROR in calculating the grant amortization of plant: {plant}, item: {item}"

    # CAPEX of REPLACEMENTS ########################################################################################

    # allocating capex expenses at the "disbursement_month" + duration period
    for replacement_item in replacement_item_list:

        item = replacement_item.replace("replacement_","") # extracting item name by removing "replacement_" from the string

        # verify that the replacement flag is True. If not, move to next replacement_item
        replacement_flag = capex_costs_per_item.loc["replacement_flag",item]
        if not replacement_flag: 
            continue

        df["capex_"+replacement_item] = 0 
        replacement_month_from_commissioning = capex_costs_per_item.loc["duration",item] * 12 # replacement after commissioning of plant
        # print("replacement_month_from_commissioning " + str(replacement_month_from_commissioning))
        replacement_month = commissioning_month + replacement_month_from_commissioning # it's the actual replacement month from beginning of project
        
        capex_value = - registry_plants[plant]["capex_"+ replacement_item] * df.loc[replacement_month,"inflation_factor"]

        df.loc[replacement_month,"capex_"+replacement_item] += capex_value

        if replacement_month > config["project_lifetime_yrs"] * 12: 
            #it means the given project lifetime exceeds the replacement period, so we skip it to avoid conflict
            continue

        # for the given capex item, we calculate the expected lifetime to be used in the depreciation&amortization calculation. To prevent errors, we impose a cap equal to the project lifetime
        da_months = config["project_lifetime_yrs"] * 12 - replacement_month + 1

        # da of capex item
        da_amount = capex_value / da_months
        da_indexes = df.index >= (replacement_month)

        df.loc[da_indexes, "da_" + replacement_item] += da_amount
        assert abs(capex_value - df["da_" + replacement_item].sum()) < 0.0001, f"ERROR in calculating the amortization of plant: {plant}, item: {replacement_item}"

    ##########################################################################################################
    # DEBT & INTEREST ########################################################################################
    ##########################################################################################################

    # introducing a debt for the initial capex 
    debt = registry_plants[plant]['debt'] # debt in pu (0 to 1)

    if debt != None or debt != np.nan:

        cost_of_capital_table = wb.sheets["CAPEX"]["cost_of_capital_table"].options(pd.Series, header=1, index=True, expand='table').value

        loan = - total_plant_capex * debt 
        loan_start_month = int(disbursement_month)
        interest_rate_yrs = cost_of_capital_table.loc["debt_interest_rate_pa","Value"]
        loan_duration_yrs = int(cost_of_capital_table.loc["debt_tenor","Value"])

        df_debt = debt_and_interest_per_plant(loan, interest_rate_yrs, loan_start_month, loan_duration_yrs)
        df["debt_disbursment/payment"] = df_debt["debt_disbursment/payment"]
        df["debt_interest"] = df_debt["debt_interest"]
    else: 
        df_debt = pd.DataFrame()
        df["debt_disbursment/payment"] = 0
        df["debt_interest"] = 0

    ###########################################################################################################
    # OPEX ####################################################################################################
    ###########################################################################################################

    df_opex = opex_per_plant(plant, asset_value=total_plant_capex)

    ###########################################################################################################
    # revenues ####################################################################################################
    ###########################################################################################################
    
    df_revenues = get_RID_per_plant(plant)

    ###########################################################################################################
    # EXPORTING RESULTS #######################################################################################
    ###########################################################################################################

    # selecting the columns to be included in each sheet
    capex_cols = [col for col in list(df.columns) if col.startswith("capex_")]
    da_cols = [col for col in list(df.columns) if col.startswith("da_")]
    opex_cols = [col for col in list(df_opex.columns) if col.startswith("opex_")]
    revenues_cols = [col for col in list(df_revenues.columns) if col.startswith("revenues_")]

    df["capex_total"] = df[capex_cols].sum(axis=1)
    df["da_total"] = df[da_cols].sum(axis=1)
    df["opex_total"] = df_opex[opex_cols].sum(axis=1)
    df["revenues_total"] = df_revenues[revenues_cols].sum(axis=1)

    # saving outputs in excel file
    writer = pd.ExcelWriter(config["foldername_finance_plants"]+"//"+plant+".xlsx", engine = 'xlsxwriter')

    df[["month"] + capex_cols].T.to_excel(writer, sheet_name= "Capex") #saving for the record
    df[["month"] + da_cols].T.to_excel(writer, sheet_name= "D&A") #saving for the record
    df_debt.T.to_excel(writer, sheet_name= "Debt") #saving for the record
    df_opex.T.to_excel(writer, sheet_name= "Opex") #saving for the record
    df_revenues.T.to_excel(writer, sheet_name= "Revenues") #saving for the record

    totals_cols = ["month","capex_total","da_total","debt_interest","opex_total","revenues_total"]
    df[totals_cols].T.to_excel(writer, sheet_name= "Totals") #saving for the record
    
    writer.close()

def debt_and_interest_per_plant(loan, interest_rate_yrs, loan_start_month, loan_duration_yrs):
    """function adapted from: https://www.toptal.com/finance/cash-flow-consultants/python-cash-flow-model
    return a dataframe with interest and principal payments, beginning and ending balances, and net Disbursment/Repayment.
    The loan shall be real (adjusted for inflation) and not nominal.   
    """

    print(f"Loan: € {loan:,.2f} at interest rate of {interest_rate_yrs*100:,.1f}% for {loan_duration_yrs} years")

    loan_end_month = loan_start_month + loan_duration_yrs*12

    # payments
    periods = range(loan_start_month, loan_end_month+1)

    interest_payment = npf.ipmt(rate=interest_rate_yrs / 12, per=periods, nper=loan_end_month, pv=-loan)
    principal_payment = npf.ppmt(rate=interest_rate_yrs / 12, per=periods, nper=loan_end_month, pv=-loan)

    # cash flows
    cf_data = {'debt_interest': interest_payment, 'debt_principal': principal_payment}
    cf_table = pd.DataFrame(data=cf_data, index=periods)

    cf_table['debt_disbursment'] = 0
    cf_table.loc[loan_start_month, 'debt_disbursment'] = loan

    cf_table['debt_payment'] = cf_table['debt_interest'] + cf_table['debt_principal']

    cf_table['debt_ending_balance'] = loan - cf_table['debt_principal'].cumsum()

    cf_table['debt_disbursment/payment'] = cf_table['debt_disbursment'] - cf_table['debt_payment']

    cf_table['debt_beginning_balance'] = [loan] + list(cf_table['debt_ending_balance'])[:-1]

    df = get_FM_template()
    df = df[["month"]]
    df = pd.concat((df,cf_table),axis=1).fillna(0)

    return df

####################################################################################################################################

def opex_per_plant(plant, asset_value):
    """ returns the real opex breakdown in € for the plant. 
    Asset value is the economic value of the asset at commissionig, which is used to compute the insurance across asset lifetime"""

    config = yaml.safe_load(open("config.yml", 'r'))
    
    app = xw.App(visible = False)
    wb = xw.Book(config["filename_input_FM_excel"])

    opex_plant_table = wb.sheets["OPEX"]["opex_plant_table"].options(pd.Series, header=1, index=True, expand='table').value
    ground_mounted_factor = wb.sheets["OPEX"]["opex_ground_factor"].value # valid for both capex and opex

    df = get_FM_template() # using month_number as index

    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    commissioning_month = registry_plants[plant]["commissioning_month"]

    plant_active_production = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_operation_matrix", index_col=0, header=0).T[plant].astype(float)
    plant_active_production.index = plant_active_production.index.astype(float) # in some cases it is imported as float
    df["plant_active_production"] = plant_active_production # for each month, 1 meaning plant is operative (thus opex is applicable); 0 means not operative
    assert not df["plant_active_production"].isna().any(), f"ERROR: plant_active_production for {plant} contains Nan values. Could be an index-related error"

    df["opex_subtotal"] = 0 # initialization of the subtotal used to compute the contingency

    for item in ["pv","battery","wind","mv_cabinet"]:
        if item == "mv_cabinet":
            if not registry_plants[plant]["mv_cabinet"]: 
                continue # skipping to next item if cabinet is not present for this plant
            else:
                item_size = max(registry_plants[plant]["pv"], registry_plants[plant]["wind"]) # we report the mv bainet size to max btw the pv and wind sizes
        else:
            item_size = registry_plants[plant][item] # kW or kWh
        
        opex_unit_cost = opex_plant_table.loc[item,"Value"] # €/kWp or €/kWh per year
        
        # increasing opex for pv if it is mounted on ground
        if item == "pv" and registry_plants[plant]["pv_mounting"] == "ground":
            opex_unit_cost *= ground_mounted_factor 

        df["opex_"+item] = - df["plant_active_production"] * df["inflation_factor"] * item_size * opex_unit_cost / 12 # negative sign = expense
        df["opex_subtotal"] += df["opex_"+item]

    # asset insurance 
    insurance_factor = opex_plant_table.loc["asset_insurance","Value"] # p.u. over asset value per year
    df["opex_asset_insurance"] = + df["plant_active_production"] * df["inflation_factor"] * asset_value * insurance_factor / 12 # negative sign = expense, note that asset_value is negative
    df["opex_subtotal"] += df["opex_asset_insurance"]

    # RID GSE annual fees
    user_type = registry_plants[plant]["user_type"]
    df_rid_gse = pd.read_csv(config["filename_output_csv_GSE_RID_fees"]).loc[0,user_type] # DataFrame with the fixed fees for RID contract execution wit GSE (annual, per type of plant)
    df["opex_rid_GSE_fees"] = - df["plant_active_production"] * df["inflation_factor"] * df_rid_gse / 12 # modelled as monthly cashflows. df_rid_gse is positive, so must have a minus in front
    df["opex_subtotal"] += df["opex_rid_GSE_fees"]

    # opex contingencies
    contingency_factor = opex_plant_table.loc["contingency","Value"] # p.u. over opex subtotal per year
    df["opex_contingency"] = df["plant_active_production"] * df["inflation_factor"] * df["opex_subtotal"] * contingency_factor / 12 # negative sign = expense
    df["opex_subtotal"] += df["opex_contingency"]

    total_first_year = sum(df.loc[commissioning_month : commissioning_month + 12, "opex_subtotal"]) # summing opex of first 12 months of operation
    print(f"Opex: € {total_first_year:,.2f} per year")

    df.drop(columns=["opex_subtotal", "inflation_factor","plant_active_production"], inplace=True) # removing the subtotal as totals will be computed later in future steps

    opex_cols = [col for col in list(df.columns) if col.startswith("opex_")]
    assert sum(df[opex_cols].gt(0).any()) == 0, f"ERROR: some opex values in plant {plant} have positive sign. Being expenses, they must all be negative"
    wb.close()
    # app.quit()

    return df

####################################################################################################################################

def get_RID_per_plant(plant):
    """
    Function to calculate the revenues from the Ritiro Dedicato (RID) mechanism for one specific plant.
    
    Parameters
    ----------
    plant : str, the identifier of the plant.
    
    Returns
    -------
    df : A DataFrame with the monthly revenues from the RID mechanism, indexed by month number, 
        and with a column 'revenues_rid' containing the revenues in €.
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    user_type = registry_plants[plant]["user_type"]

    # importing the nominal RID, revenues from energy sold to GSE
    rid = pd.read_csv(config["filename_output_csv_RID_active_CACER"],index_col="month") # dataframe with month on index and user_typee on columns

    plant_active_production = pd.read_excel(config["filename_plant_operation_matrix"], sheet_name= "plant_operation_matrix", index_col=0, header=0).T[plant].astype(float)
    plant_active_production.index = plant_active_production.index.astype(float) # in some cases it is imported as float
    assert not plant_active_production.isna().any(), f"ERROR: plant_active_production for {plant} contains Nan values. Could be an index-related error"


    df = get_FM_template().reset_index().set_index("month")
    df["revenues_rid"] = rid[user_type] # rid dataframe currently has month as index. To be armonized
    df = df.reset_index().set_index("month_number") # changing index to month number to accomodate next steps. To be armonized
    df["revenues_rid"] = df["revenues_rid"] * plant_active_production * df["inflation_factor"]
    assert not df["revenues_rid"] .isna().any(), f"ERROR: revenues RID for {plant} contains Nan values. Could be an index-related error"

    df.drop(columns=["inflation_factor"], inplace=True)

    return df

####################################################################################################################################

def pnrr_deadline_check(df, disbursment_month, commissioning_month):
    """function to check whether the disbursment month exceeds the PNRR deadline, currently set by MASE and GSE at November 2025 (updated at March 2025)"""
    # pnrr_disbursment_deadline_month = df[df["month"] == "2025-11"].index[0]
    # pnrr_filename_registry_plants_ymlssioning_deadline_month = df[df["month"] == "2025-06"].index[0]
    # pnrr_filename_registry_plants_ymlssioning_deadline_month
    # if disbursment_month > pnrr_deadline_month:

    # if commissioning_month > pnrr_filename_registry_plants_ymlssioning_deadline_month or disbursment_month - commissioning_month > 16:


    # da completare

    # aggiungere anche check sui massimali di spesa

    return True

def DCF_analysis(user):

    """
    Perform a Discounted Cash Flow (DCF) analysis on a given user and saves results to user's Excel file.
    Some functions from numpy-financial library are adopted, while Payback Period methodologuy was inspired by https://sushanthukeri.wordpress.com/2017/03/29/discounted-payback-periods/ 
    """
    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))
    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    
    flag_user_not_CACER = user != "CACER"

    if flag_user_not_CACER:
        user_category = registry_users[user]["category"]
    else: 
        user_category = "CACER"

    filename_user = config["foldername_finance_users"]+user+".xlsx"

    df = pd.read_excel(filename_user, sheet_name= "totals", index_col=0, header=0).T

    ######## EBITDA ########################
    df["revenues_total_taxable"] = df["revenues_total"]
    if flag_user_not_CACER and registry_users[user]["type"] == "prosumer":
        # if the user is a prosumer, it means the revenues include the electricity bill savings, which are indirect and non taxable
        plants = [plant for plant in registry_plants if registry_plants[plant]["titolare_POD"] == user] # for how the user_id assignation is structured, currently this should be a list of one value only
        
        for plant in plants:
            df_plant = pd.read_excel(config["foldername_finance_users"]+user+".xlsx", sheet_name=plant, index_col=0, header=0).T
            df["revenues_total_taxable"] -= df_plant["revenues_electricity_savings"]
    
    # if it's AUC, then there are energy savings related to condominium electricity bill, which are indirect and non taxable
    if recap["type_of_cacer"] == "AUC" and flag_user_not_CACER:
        # for simulation purposes, in case of user==cacer, if it's an AUC, the plant is owned by the users based on the ownership matrix, not by the cacer itself. 
        # the CACER.xlsx will not have the plant sheet, in fact
        plants = [plant for plant in registry_plants if registry_plants[plant]["condominium"]] # we might have multiple sections of the plant, or condomium with multiple roofs and PODs, so plants might be more than one
        for plant in plants:
            df_plant = pd.read_excel(config["foldername_finance_users"]+user+".xlsx", sheet_name=plant, index_col=0, header=0).T
            df["revenues_total_taxable"] -= df_plant["revenues_condominium_electricity_savings"]

    df["EBITDA"] = df["revenues_total_taxable"] + df["opex_total"] # sign is already positive or negative according to direction of cashflow
    df["EBIT"] = df["EBITDA"] + df["da_total"]
    df["PBT"] = df["EBIT"] + df["debt_interest"]

    ######## TAXES ########################

    taxes = pd.read_excel(config["filename_input_FM_excel"], sheet_name= "Taxes", index_col="Item", header=0)
    ires = taxes.loc["ires","Value"] * taxes.loc["ires",user_category] 
    irap = taxes.loc["irap","Value"] * taxes.loc["irap",user_category]

    df["taxes_ires"] = - df["PBT"] * ires * (df["PBT"] > 0)
    df["taxes_irap"] = - df["PBT"] * irap * (df["PBT"] > 0)
    df["taxes_total"] = df["taxes_ires"] + df["taxes_irap"]

    df["Net Earnings"] = df["PBT"] + df["taxes_total"]

    df["Net Final Earnings"] = df["Net Earnings"] + (df["revenues_total"] - df["revenues_total_taxable"]) # adding back the electricity bill savings

    ######## FREE CASH FLOW ########################

    df["FCF"] = df["capex_total"] + df["opex_total"] + df["revenues_total"] + df["taxes_total"] + df["debt_interest"]
    df["FCF_cum"] = df["FCF"].cumsum()

    ######## DISCOUNTED CASH FLOW ########################

    df["DCF"] = df["FCF"] * df["discount_factor"]
    df["DCF_cum"] = df["DCF"].cumsum()

    # saving
    app = xw.App(visible=False)
    wb = xw.Book(filename_user)
    wb.sheets.add("DCF_monthly",after="totals")
    wb.sheets["DCF_monthly"].range("A1").value = df.T

    # creating the yearly DCF dataframe

    df["year"] = df["month"].str[0:4]
    df_yearly = df.drop(columns=["month","inflation_factor","discount_factor", "FCF_cum","DCF_cum"]).groupby("year").sum()
    df_yearly["FCF_cum"] = df_yearly["FCF"].cumsum() # having passed from monthly to yearly, this shall be recalculated
    df_yearly["DCF_cum"] = df_yearly["DCF"].cumsum() # having passed from monthly to yearly, this shall be recalculated
    df_yearly.reset_index(inplace=True)
    df_yearly.index = df_yearly.index + 1 # starting from year 1 instead of 0

    irr = npf.irr(df_yearly["FCF"].values) # https://numpy.org/numpy-financial/latest/
    # IMPORTANT: npf.irr() shall be applied to yearly cash flows only, not monthly! 
    print(f"IRR: {irr*100:,.2f} %")
    net_present_value = df["DCF_cum"].iloc[-1]
    print(f"Net Present Value: {net_present_value:,.2f} €")

    # Payback Period (inspired by https://sushanthukeri.wordpress.com/2017/03/29/discounted-payback-periods/)
    if df[df.DCF_cum < 0].empty: # in some cases some users might not have a single energy flow different from 0. This way we avoid errors
        final_full_month = df.index.values.max()
    else:
        final_full_month = df[df.DCF_cum < 0].index.values.max()
    if final_full_month == df.index.values.max(): # no return on investment
        payback_period_yrs = final_full_month / 12
    else:
        # fractional_month = - df.DCF_cum[final_full_month] / df.DCF_cum[final_full_month + 1] # I disagree with this method
        delta_y = (df.DCF_cum[final_full_month + 1] - df.DCF_cum[final_full_month])
        fractional_month = abs(df.DCF_cum[final_full_month] / delta_y) # I believe this is the right method using linear interpolation
        payback_period_months = final_full_month + fractional_month
        payback_period_yrs = payback_period_months / 12

    wb.sheets.add("DCF_yearly", after="DCF_monthly")
    wb.sheets.add("Results", after="DCF_yearly")
    
    wb.sheets["DCF_yearly"].range("A1").value = df_yearly.T
    wb.sheets["Results"].range("A1").value = pd.DataFrame([irr, net_present_value, payback_period_yrs], index=["IRR", "NPV", "Payback Period"], columns=[user])

    wb.save()
    wb.close()
    # app.quit()

def organize_simulation_results_for_reporting():
    """recreating the old structured filename_FM_results_last_simulation file. 
    This is temporary, to be organized in a less chaotic way"""

    print(blue("\nOrganize results for report:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))

    check_file_status(config["filename_FM_results_last_simulation"])

    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))
    registry_plants = yaml.safe_load(open(config["filename_registry_plants_yml"], 'r'))
    results = registry_users.copy()
    recap = yaml.safe_load(open(config['filename_recap'], 'r'))

    user_and_configurations = list(registry_users.keys()) + ["project"] + recap["stakeholders"] + recap["configurations"]

    for user in user_and_configurations:

        real_user_flag = user in list(registry_users.keys())  # T/F
        # print(user)
        # print(real_user_flag)
        
        if real_user_flag and registry_users[user]["dummy_user"]: continue # skipping dummy users

        if real_user_flag:
            filename_user = config["foldername_finance_users"]+user+".xlsx"
        else:
            filename_user = config["foldername_finance_configurations"]+user+".xlsx"
            results[user] = {} # creating space for results for configurations

        df_dcf = pd.read_excel(filename_user, sheet_name= "DCF_yearly", index_col=0, header=0).T

        results[user]["IRR"] = pd.read_excel(filename_user, sheet_name= "Results",index_col=0).astype(float).loc["IRR", user]
        results[user]["NPV"] = pd.read_excel(filename_user, sheet_name= "Results",index_col=0).astype(float).loc["NPV", user]
        results[user]["payback_period"] = pd.read_excel(filename_user, sheet_name= "Results",index_col=0).astype(float).loc["Payback Period", user]
        results[user]["capex_total"] = df_dcf["capex_total"].sum()
        results[user]["opex_total"] = df_dcf["opex_total"].sum()
        results[user]["revenues_total"] = df_dcf["revenues_total"].sum()
        results[user]["taxes_total"] = df_dcf["taxes_total"].sum()

        for i in range(1, config["project_lifetime_yrs"] + 1):
            key = "DCF_yr_" + str(("{:02d}".format(i)))
            results[user][key] = df_dcf.loc[i,"DCF"]

        results[user]["capex_total"] = df_dcf["capex_total"].sum()
        results[user]["opex_total"] = df_dcf["opex_total"].sum()
        results[user]["revenues_total_taxable"] = df_dcf["revenues_total_taxable"].sum()
        results[user]["taxes_total"] = df_dcf["taxes_total"].sum()
        results[user]["debt_interest"] = df_dcf["debt_interest"].sum()

        if real_user_flag:
            user_type = registry_users[user]["user_type"]
        else: 
            user_type = user

        filename = config["foldername_bills"] + user_type + ".xlsx"
        df_user_tariff_bau = pd.read_excel(filename, sheet_name="bau", index_col="month")
        if real_user_flag and registry_users[user]["type"] == "consumer":
            df_user_tariff_pv = df_user_tariff_bau
        else: 
            df_user_tariff_pv = pd.read_excel(filename, sheet_name="pv", index_col="month")
        results[user]["electricity_bills_bau"] = - (df_user_tariff_bau["total_bill_cost"] * get_FM_template()["inflation_factor"].values).sum() #from nominal to real
        results[user]["electricity_bills"] = - (df_user_tariff_pv["total_bill_cost"] * get_FM_template()["inflation_factor"].values).sum() #from nominal to real
        results[user]["electricity_bills_savings"] = - (results[user]["electricity_bills_bau"] - results[user]["electricity_bills"]) # positive sign if there is a saving

    # if it's an AUC, then we should add the energy savings related to the condominium bills, which are otherwise lost as the condominium is a dummy user
    # these savings are in the CACER sheet
        if recap["type_of_cacer"] == "AUC" and real_user_flag:
            
            results[user]["revenues_condominium_electricity_savings"] = 0
            
            plants = [plant for plant in registry_plants if registry_plants[plant]["condominium"]] # we might have multiple sections of the plant, or condomium with multiple roofs and PODs, so plants might be more than one
            for plant in plants:
                df_plant = pd.read_excel(config["foldername_finance_users"]+user+".xlsx", sheet_name=plant, index_col=0, header=0).T
                results[user]["revenues_condominium_electricity_savings"] += df_plant["revenues_condominium_electricity_savings"].sum()

        if recap["type_of_cacer"] == "AUC" and not real_user_flag:
            # if it's a configuration, we need to add the energy savings related to the condominium bills, taken from the project.xlsx file, which are otherwise lost as the condominium is a dummy user
            
            results[user]["revenues_condominium_electricity_savings"] = 0

            df_plant = pd.read_excel(config["foldername_finance_configurations"]+user+".xlsx", sheet_name="plants", index_col=0, header=0).T
            results[user]["revenues_condominium_electricity_savings"] += df_plant["revenues_condominium_electricity_savings"].sum()


        df_cacer = pd.read_excel(filename_user, sheet_name= "CACER", index_col=0, header=0).T
        
        if recap["type_of_cacer"] in ["CER", "AUC", "AID"]:
            results[user]["revenues_incentives"] = df_cacer["revenues_incentives"].sum()
            results[user]["revenues_valorization"] = df_cacer["revenues_valorization"].sum()

            for item in ["revenues_surplus","capex_entry_fee","capex_cacer_kickoff"]:
                if item in df_cacer.columns:
                    results[user][item] = df_cacer[item].sum()
                else: 
                    results[user][item] = 0
            
        else: 
            results[user]["revenues_incentives"] = 0
            results[user]["revenues_valorization"] = 0
            results[user]["revenues_surplus"] = 0
            results[user]["capex_entry_fee"] = 0
            results[user]["capex_cacer_kickoff"] = 0

        total_rid = 0
        for plant in list(registry_plants.keys()) +  ["plants"]: # note that the aggregation of users such configurations or stakehorlders or CACER, has the aggregated plants under the sheetname of "plants"! 
            # print(plant)
            try: 
                df_plant = pd.read_excel(filename_user, sheet_name= plant, index_col=0, header=0).T
                total_rid += df_plant["revenues_rid"].sum()
            except: continue
        results[user]["revenues_rid"] = total_rid

    # saving some CACER outputs in the recap yaml
    df_incentives = pd.read_csv(config["filename_CACER_incentivi"], index_col="month_number")

    add_to_recap_yml("surplus_nominal", float(df_incentives["surplus"].sum()))
    add_to_recap_yml("incentives_bounded_nominal",float(df_incentives["incentivo"].sum()))
    add_to_recap_yml("valorizzazione_nominal",float(df_incentives["valorizzazione"].sum()))
    add_to_recap_yml("social_fund_nominal",float(df_incentives["social_fund"].sum()))
    add_to_recap_yml("incentives_total_nominal",float(df_incentives["incentivo_totale"].sum()))

    inflation_factor = get_FM_template()["inflation_factor"] # month_number as default index

    assert inflation_factor.index.equals(df_incentives.index), "ERROR: indexes don't match"

    add_to_recap_yml("surplus_real", float(sum(df_incentives["surplus"] * inflation_factor)))
    add_to_recap_yml("incentives_bounded_real",float(sum(df_incentives["incentivo"] * inflation_factor)))
    add_to_recap_yml("valorizzazione_real",float(sum(df_incentives["valorizzazione"] * inflation_factor)))
    add_to_recap_yml("social_fund_real",float(sum(df_incentives["social_fund"] * inflation_factor)))
    add_to_recap_yml("incentives_total_real",float(sum(df_incentives["incentivo_totale"] * inflation_factor)))

    pd.DataFrame(results).to_csv(config["filename_FM_results_last_simulation"]) # table with users on columns and variables on rows

    print("**** All results organized! *****")

##############################################################################################################################################
def aggregate_FM_single_group(flag_configuration = True, user_group="project"):
    """
    flag_configuration = true means the user group is CACER or a configuration, else it will be stakeholder. Difference is only related to the users_list definition
    user_group = generic term which can be a configuration, the whole CACER or a specific stakeholder
    """

    config = yaml.safe_load(open("config.yml", 'r'))
    registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

    # Initialize an empty list with emty dataframes
    results_dict = {"plants": pd.DataFrame(),
                    "CACER": pd.DataFrame(),
                    "totals": pd.DataFrame(),
                    "DCF_monthly": pd.DataFrame(),
                    "DCF_yearly": pd.DataFrame()}

    if flag_configuration:
        print("\nConfiguration: ", user_group)

        # Loop through all files in the folder
        if user_group == "project":
            users_list = [file.split('\\')[-1].replace('.xlsx','') for file in glob.glob(config["foldername_finance_users"] + "/*.xlsx")]
            if "social_fund" in users_list: 
                users_list.remove("social_fund") # from the economic stability of the project, the social fund shall be kept out of the boundary, as cash flow directed to social purposes only

        else:
            users_list = [user for user in registry_users if registry_users[user]["CP"] == user_group and not registry_users[user]["dummy_user"]]

    else: 
        print("\nStakeholder: ", user_group)
        users_list = [user for user in registry_users if registry_users[user]["stakeholder"] == user_group and not registry_users[user]["dummy_user"]]

    for user in users_list:

        # Read the Excel file, as dictoinary of dataframes of all the sheets
        data_dictionary = pd.read_excel(config["foldername_finance_users"] + user + ".xlsx", sheet_name=None,index_col=0)

        for sheet_name, df in data_dictionary.items():
            # print(sheet_name)
            if sheet_name.startswith("p_"): 
                sheet_name = "plants" # aggregating all the plants in one sheet
            elif sheet_name == "Results":
                continue # skip results sheets which refear to the single user, no point in aggregating them

            df = df.T # Transpose the dataframe, month_number on index and item on columns
            cols_to_ignore = [col for col in df.columns if col in ['inflation_factor','discount_factor',"month","EBITDA","EBIT","PBT","FCF_cum","DCF_cum"]]
            cols_to_read = [cols for cols in df.columns if cols not in cols_to_ignore]
            # print(df)

            for col in cols_to_read:
                if col in results_dict[sheet_name].columns:
                    results_dict[sheet_name][col] += df[col]
                else:
                    results_dict[sheet_name][col] = df[col]

    # in the DCF dataframes, we shall recalculated the FCF_cum and DCF_cum columns
    for sheet_name in ["DCF_monthly","DCF_yearly"]:
        results_dict[sheet_name]["FCF_cum"] = results_dict[sheet_name]["FCF"].cumsum()
        results_dict[sheet_name]["DCF_cum"] = results_dict[sheet_name]["DCF"].cumsum()

    ######################################
    # Calculate the IRR
    irr = npf.irr(results_dict["DCF_yearly"]["FCF"].values) # https://numpy.org/numpy-financial/latest/
    # IMPORTANT: npf.irr() shall be applied to yearly cash flows only, not monthly! 
    print(f"IRR: {irr*100:,.2f} %")
    net_present_value = results_dict["DCF_monthly"]["DCF_cum"].iloc[-1]
    print(f"Net Present Value: {net_present_value:,.2f} €")

    # Payback period (inspired by https://sushanthukeri.wordpress.com/2017/03/29/discounted-payback-periods/)
    df = results_dict["DCF_monthly"]
    final_full_month = df[df.DCF_cum < 0].index.values.max()
    if final_full_month == df.index.values.max(): # no return on investment
        payback_period_yrs = final_full_month / 12
    else:
        # fractional_month = - df.DCF_cum[final_full_month] / df.DCF_cum[final_full_month + 1] # I disagree with this method
        delta_y = (df.DCF_cum[final_full_month + 1] - df.DCF_cum[final_full_month])
        fractional_month = abs(df.DCF_cum[final_full_month] / delta_y) # I believe this is the right method using linear interpolation
        payback_period_months = final_full_month + fractional_month
        payback_period_yrs = payback_period_months / 12
    print(f"Payback time: {payback_period_yrs:,.1f} yrs")

    results_dict["Results"] = pd.DataFrame([irr, net_present_value, payback_period_yrs], index=["IRR", "NPV", "Payback Period"], columns=[user_group]).T

    # Export the aggregated data to a new Excel file
    writer = pd.ExcelWriter(config["foldername_finance_configurations"] + user_group + ".xlsx", engine='openpyxl') 
    for df_name, df in results_dict.items():
        df.T.to_excel(writer, sheet_name=df_name)
    writer.close()

def aggregate_FM():
    
    """
    Aggregate financial model data for all configurations, stakeholders, and the project as a whole.

    This function clears the content of the finance configurations folder and processes each configuration,
    stakeholder, and the entire project to aggregate financial model data using the `aggregate_FM_single_group` function.
    
    The configurations and stakeholders are retrieved from the recap file specified in the config file.

    The function performs the following tasks:
    - Clears the finance configurations folder.
    - Aggregates data for each configuration defined in the recap file.
    - Aggregates data for each stakeholder defined in the recap file.
    - Aggregates data for the entire project.

    The aggregated data is exported to Excel files named after each user group.
    """

    print(blue("\nRun financial model for each configurations:", ['bold', 'underlined']), '\n')

    config = yaml.safe_load(open("config.yml", 'r'))
    recap = yaml.safe_load(open(config["filename_recap"], 'r'))

    clear_folder_content(config["foldername_finance_configurations"])
    
    for configuration in recap["configurations"]:

        aggregate_FM_single_group(user_group=configuration)

    for stakeholder in recap["stakeholders"]:

        aggregate_FM_single_group(flag_configuration=False, user_group=stakeholder)

    aggregate_FM_single_group(user_group="project")

    print("\n**** FM for configurations aggregated! ****")
    
####################################################################################################################################

    # function to suppress the printing sections of a specified function
def suppress_printing(func, *args, **kwargs):
    """
    Suppresses the printing sections of a specified function.
    This function takes a function as an argument and redirects the standard output to a StringIO object, effectively suppressing any print statements in the function.
    Parameters
    ----------
    func : function
        The function for which to suppress the printing sections.
    *args : arguments
        The arguments to be passed to the function.
    **kwargs : keyword arguments
        The keyword arguments to be passed to the function.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)

