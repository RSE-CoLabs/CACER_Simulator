import pandapower as pp
import pandas as pd
import numpy as np
import io
import datetime
import yaml
import pickle
from simple_colors import blue, red, green
from tqdm.auto import tqdm
from datetime import datetime

from src.Functions_General import *
from src.Functions_Energy_Model import * 

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# check for buses with voltage violations in the case without DSM
def bus_voltage_violations_analysis(busVoltageTime):
    
    busVoltageIssue = busVoltageTime.loc[:,( 
        (busVoltageTime<0.95) | (busVoltageTime>1.05) ).any()]

    # creating a table with the minimum and maximum voltage for buses with violations
    minVoltage = busVoltageIssue.min().to_frame(name="vm_min").reset_index()
    maxVoltage = busVoltageIssue.max().to_frame(name="vm_max").reset_index()
    tableVoltageIssue = pd.merge(minVoltage,maxVoltage)

    # printing the table with overloaded lines
    if not tableVoltageIssue.empty:
        print(red("Number of issues: " + str(tableVoltageIssue.columns.size) + "\n", ['bold']))
        print(tableVoltageIssue)
    else:
        print(green("No voltage issues!", ['bold']))

    return tableVoltageIssue

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# check for lines with load violations in the case without DSM
def line_loading_issue_analysis(lineLoadingTime):
    lineLoadingIssue = lineLoadingTime.loc[:,(lineLoadingTime>100).any()] # we extract just lines with load violations

    # creating a table with the average and maximum loading of lines with issues
    minLoading = lineLoadingIssue.min().to_frame(name="min_loading").reset_index() # minimum value for load of the lines with load violations 
    avgLoading = (lineLoadingIssue.sum()/len(lineLoadingIssue)).to_frame(name="avg_loading").reset_index() # average value for load of the lines with load violations (over time for the entire week)
    maxLoading = lineLoadingIssue.max().to_frame(name="max_loading").reset_index() # maximum value for load of the lines with load violations

    tableLineLoadingIssue = pd.merge(minLoading,avgLoading).merge(maxLoading) # merge minLoading, avgLoading and maxLoading into a single df

    # printing the table with overloaded lines
    if not tableLineLoadingIssue.empty:
        print(red("Number of issues: " + str(lineLoadingIssue.columns.size) + "\n", ['bold']))
        print(tableLineLoadingIssue)
    else:
        print(green("No loading line issues!", ['bold']))
    
    return lineLoadingIssue

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# check for transformers with load violations in the case without DSM
def trafo_loading_issue_analysis(trafoLoadingTime):
    trafoLoadingIssue = trafoLoadingTime.loc[:,(trafoLoadingTime>100).any()] # we extract just trafos with load violations

    # creating a table with the average and maximum loading of transformers with issues
    minLoading = trafoLoadingIssue.min().to_frame(name="min_loading").reset_index()  # minimum value for load of the trafos with load violations 
    avgLoading = (trafoLoadingIssue.sum()/len(trafoLoadingIssue)).to_frame(name="avg_loading").reset_index() # average value for load of the trafos with load violations (over time for the entire week)
    maxLoading = trafoLoadingIssue.max().to_frame(name="max_loading").reset_index() # maximum value for load of the trafos with load violations

    tableTrafoLoadingIssue = pd.merge(minLoading,avgLoading).merge(maxLoading) # merge minLoading, avgLoading and maxLoading into a single df

    # printing the table with overloaded lines
    if not tableTrafoLoadingIssue.empty:
        print(red("Number of issues: " + str(trafoLoadingIssue.columns.size) + "\n", ['bold']))
        print(tableTrafoLoadingIssue)
    else:
        print(green("No loading trafo issues!", ['bold']))
    
    return trafoLoadingIssue

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# we execute a preliminar check
def preliminar_check_hc_analysis_TS(result_TS_PF):

    month_list = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']

    for month in month_list:

        for day_type in ['working_day', 'saturday', 'sunday']:

            # Steady - state voltage variations (SSVV)
            busVoltageTime = result_TS_PF[month][day_type]['busVoltageTime']
            check_1 = SSVV_check(busVoltageTime)

            #######################################################

            # Rapid voltage changes (RVC)
            check_2 = RVC_check(busVoltageTime)

            #######################################################

            # Thermal limits
            lineLoadingTime = result_TS_PF[month][day_type]['lineLoadingTime']
            trafoLoadingTime = result_TS_PF[month][day_type]['trafoLoadingTime']
            check_3 = thermal_limits_check(lineLoadingTime, trafoLoadingTime)

            #######################################################

            # check violations
            check = (check_1 and check_2 and check_3)

            #######################################################

            print("Month: " + month + "; Day type: " + day_type + "\n")

            if check:
                print(green("All condition are verified!\n", ['bold', 'underlined']))
            else:
                print(red("There is some violations of the limits!", ['bold', 'underlined']))
                if not check_1:
                    print(red('SSVV limit is not verified!', ['bold']))
                if not check_2:
                    print(red('RVC limit is not verified!', ['bold']))
                if not check_3:
                    print(red('Thermal limit is not verified!', ['bold']))
                print("")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Steady - state voltage variations (SSVV)
def SSVV_check(busVoltageTime):
    perc_upper_limit = 0.1
    perc_lower_limit = -0.1

    num_time_interval = len(busVoltageTime)

    perc_time_limit = 0.95

    limit_time = perc_time_limit * num_time_interval

    for column in busVoltageTime.columns:
        violations = sum(busVoltageTime[column] < (1 + perc_lower_limit)) + sum(busVoltageTime[column] > (1 + perc_upper_limit))
        if violations > limit_time:
            return False
        else:
            return True

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Rapid voltage changes (RVC)
def RVC_check(busVoltageTime):
    perc_limit = 0.05

    delta_voltage = busVoltageTime.diff() 
    delta_voltage = delta_voltage.iloc[1:]
    busVoltageTime_prev_val = busVoltageTime.tail(-1).copy()
    delta_voltage = (delta_voltage / busVoltageTime_prev_val)

    for column in busVoltageTime.columns:
        violations = sum(delta_voltage[column] > (perc_limit))
        if violations > 0:
            return False
        else:
            return True

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Thermal limits
def thermal_limits_check(lineLoadingTime, trafoLoadingTime):
    return check_overloading(lineLoadingTime) and check_overloading(trafoLoadingTime)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# check overloading element
def check_overloading(df):
    for column in df.columns:
        violations = sum(df[column] > 100)
        if violations > 0:
            return False
        else:
            return True

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# def load_flow_simulator(case_denomination, network):
    
    # config = yaml.safe_load(open("config.yml", 'r'))
    # year = config['start_date'].year
    # start_time = datetime(year, 1, 1, 0, 0, 0).strftime("%Y-%m-%d %H:%M:%S")
    # end_time = datetime(year, 12, 31, 23, 45, 0).strftime("%Y-%m-%d %H:%M:%S")

    # flag_hourly_PF = True

    # #############################################################################################################################

    # result_TS_PF = {} # create an empty dictionary for the result

    # #############################################################################################################################

    # # initialization of tables to contain simulation result for each time step

    # extgridActivePowerTime = pd.DataFrame( [] , columns=network.ext_grid["name"] )
    # extgridReactivePowerTime = pd.DataFrame( [] , columns=network.ext_grid["name"] )

    # busVoltageTime = pd.DataFrame( [] , columns=network.bus["name"] )
    # busActivePowerTime = pd.DataFrame( [] , columns=network.bus["name"] )
    # busReactivePowerTime = pd.DataFrame( [] , columns=network.bus["name"] )

    # lineLoadingTime = pd.DataFrame( [] , columns=network.line["name"] )
    # lineActiveLossesTime = pd.DataFrame( [] , columns=network.line["name"] )
    # lineReactiveLossesTime = pd.DataFrame( [] , columns=network.line["name"] )
    # lineActivePowerTimeTo = pd.DataFrame( [] , columns=network.line["name"] )
    # lineReactivePowerTimeTo = pd.DataFrame( [] , columns=network.line["name"] )
    # lineActivePowerTimeFrom = pd.DataFrame( [] , columns=network.line["name"] )
    # lineReactivePowerTimeFrom = pd.DataFrame( [] , columns=network.line["name"] )

    # trafoLoadingTime = pd.DataFrame( [] , columns=network.trafo["name"] )
    # trafoActiveLossesTime = pd.DataFrame( [] , columns=network.trafo["name"] )
    # trafoReactiveLossesTime = pd.DataFrame( [] , columns=network.trafo["name"] )

    # loadPowerTime = pd.DataFrame( [] , columns=network.load["name"] )    

    # genPowerTime = pd.DataFrame( [] , columns=network.gen["name"] )

    # #############################################################################################################################

    # # extract load data for simulation (active power)

    # filename = config['filename_pod_energy_exchange']

    # data_simulation = pd.read_csv(filename) # import data load profile from 'user_type_energy_exchange.csv' file
    # data_simulation = data_simulation.set_index(pd.DatetimeIndex(data_simulation['datetime'])).copy() # set datetime as index
    # data_simulation.drop(['datetime'], axis = 1, inplace = True) # drop datetime column
    # data_simulation = data_simulation.loc[start_time : end_time]

    # #############################################################################################################################

    # if flag_hourly_PF:

    #     interval = '1H'

    #     df_1 = data_simulation.copy()

    #     def resample_kwh(df, interval):
    #         resampled_df = df.resample(interval).sum()
    #         return resampled_df

    #     data_simulation = resample_kwh(df_1, interval)

    # ##########################################################################################################################

    # time_delta = ((data_simulation.index[1] - data_simulation.index[0]).seconds) / 60 # time delta of the input data

    # ##########################################################################################################################

    # # importing list of pod of all users (prosumager; prosumer; consumer)
    # filename = config["filename_data"]
    # load = pd.read_excel(filename, sheet_name="load")

    # ##########################################################################################################################

    # list_pod_user = load['id_pod'] # we extract all id_pod (CER e noCER)
    # list_pod_user.dropna(inplace = True)

    # # check pod list
    # i = 1
    # for pod in list_pod_user:
    #     if pod not in data_simulation.iloc[0, :].index:
    #         print(str(i) + ") " + pod + " is not in load data!")
    #         i+=1

    # ##########################################################################################################################

    # # organize dataframe with active power

    # # extract dataframe with just id_bus and id_pod column
    # df_load_name_id_pod = load[['name', 'id_pod', 'power factor']]

    # df_1 = data_simulation.T

    # # Set the index for the load name ID POD DataFrame
    # df_2 = df_load_name_id_pod.set_index('id_pod')

    # # Merge the two DataFrames on the index
    # df_P = pd.merge(left=df_2, right=df_1, left_index=True, right_index=True, how="inner") # dataframe active power ordered

    # ##########################################################################################################################

    # # calculate reactive power

    # # Extract and preprocess the power factor column
    # df_PF = df_P["power factor"].replace("-", 1).astype(float)

    # # Remove unnecessary columns and scale the active power
    # df_P = df_P.drop(columns=['name', 'power factor']) / (time_delta / 60) / 1000

    # # Calculate reactive power directly using vectorized operations
    # df_Q = df_P * np.tan(np.arccos(df_PF.values[:, np.newaxis]))

    # # Ensure the result is a DataFrame with the same index and columns as df_P
    # df_Q = pd.DataFrame(df_Q, index=df_P.index, columns=df_P.columns) # dataframe reactive power ordered

    # ##########################################################################################################################

    # # for over timestep

    # count_no_convergence = 0

    # for t in tqdm(data_simulation.index, desc="Time series power flow analysis", unit=" timestep"):

    #     network.load['p_mw'] = df_P[t].values 
    #     network.load['q_mvar'] = df_Q[t].values 

    #     ##########################################################################################################################

    #     try:

    #         # running Power Flow (not optimal - flexibility disabled)
    #         pp.runpp(net = network, numba = False, algorithm='nr', init='results', max_iteration=1000, tolerance_mva=1e-6, verbose=True)

    #         #####################################################################################################

    #     except:
    #         count_no_convergence+=1
    #         # print("Timestep: " + str(data_simulation.index[t]) + "\n")
    #         print("Timestep: " + str(t) + "\n")
    #         print(red("Actual iteration didn't converge! Go on. \n", ['bold']))
    #         print("----------------------------------\n")

    #     #####################################################################################################

    #     # we create a df with the timesteps on the rows and the controlled parameters on the columns 

    #     # updating time profiles!!!!!
    #     extgridActivePowerTime.loc[t] = network.res_ext_grid["p_mw"].values             # Transmission network exchange
    #     extgridReactivePowerTime.loc[t] = network.res_ext_grid["q_mvar"].values         # Transmission network exchange
        
    #     busVoltageTime.loc[t] = network.res_bus["vm_pu"].values                      # voltage profile
    #     busActivePowerTime.loc[t] = network.res_bus["p_mw"].values                   # voltage profile
    #     busReactivePowerTime.loc[t] = network.res_bus["q_mvar"].values               # voltage profile
        
    #     lineLoadingTime.loc[t] = network.res_line["loading_percent"].values    # line loading [%]
    #     lineActiveLossesTime.loc[t] = network.res_line["pl_mw"].values         # active power losses of the line [MW]
    #     lineReactiveLossesTime.loc[t] = network.res_line["ql_mvar"].values     # reactive power losses of the line [MVar]
    #     lineActivePowerTimeTo.loc[t] = network.res_line["p_to_mw"].values        # active power flow into the line at "to" bus [MW]
    #     lineReactivePowerTimeTo.loc[t] = network.res_line["q_to_mvar"].values    # reactive power flow into the line at "to" bus [MVar]
    #     lineActivePowerTimeFrom.loc[t] = network.res_line["p_from_mw"].values        # active power flow into the line at "from" bus [MW]
    #     lineReactivePowerTimeFrom.loc[t] = network.res_line["q_from_mvar"].values    # reactive power flow into the line at "from" bus [MVar]
        
    #     trafoLoadingTime.loc[t] = network.res_trafo["loading_percent"].values # trafo loading
    #     trafoActiveLossesTime.loc[t] = network.res_trafo["pl_mw"].values      # active power losses of the trafo [MW]
    #     trafoReactiveLossesTime.loc[t] = network.res_trafo["ql_mvar"].values  # reactive power consumption of the trafo [MVar]

    #     loadPowerTime.loc[t] = network.res_load["p_mw"].values   # load power (just baseline load)
        
    #     if not network.gen.empty:
    #         genPowerTime.loc[t] = network.res_gen["p_mw"].values              # gen power

    # ##########################################################################################################################

    # extgridActivePowerTime = extgridActivePowerTime.set_index(data_simulation.index)
    # extgridReactivePowerTime = extgridReactivePowerTime.set_index(data_simulation.index)

    # busVoltageTime = busVoltageTime.set_index(data_simulation.index)
    # busActivePowerTime = busActivePowerTime.set_index(data_simulation.index)
    # busReactivePowerTime = busReactivePowerTime.set_index(data_simulation.index)

    # lineLoadingTime = lineLoadingTime.set_index(data_simulation.index)
    # lineActiveLossesTime = lineActiveLossesTime.set_index(data_simulation.index)
    # lineReactiveLossesTime = lineReactiveLossesTime.set_index(data_simulation.index)
    # lineActivePowerTimeTo = lineActivePowerTimeTo.set_index(data_simulation.index)
    # lineReactivePowerTimeTo = lineReactivePowerTimeTo.set_index(data_simulation.index)
    # lineActivePowerTimeFrom = lineActivePowerTimeFrom.set_index(data_simulation.index)
    # lineReactivePowerTimeFrom = lineReactivePowerTimeFrom.set_index(data_simulation.index)

    # trafoLoadingTime = trafoLoadingTime.set_index(data_simulation.index)
    # trafoActiveLossesTime = trafoActiveLossesTime.set_index(data_simulation.index)
    # trafoReactiveLossesTime = trafoReactiveLossesTime.set_index(data_simulation.index)

    # loadPowerTime = loadPowerTime.set_index(data_simulation.index)

    # if not network.gen.empty:
    #     genPowerTime = genPowerTime.set_index(data_simulation.index)

    # ##########################################################################################################################

    # result_TS_PF = {'extgridActivePowerTime' : extgridActivePowerTime,
    #                     'extgridReactivePowerTime' : extgridReactivePowerTime,
                            
    #                         'busVoltageTime' : busVoltageTime,
    #                         'busActivePowerTime' : busActivePowerTime,
    #                         'busReactivePowerTime' : busReactivePowerTime,
                            
    #                         'lineLoadingTime' : lineLoadingTime,
    #                         'lineActiveLossesTime' : lineActiveLossesTime,
    #                         'lineReactiveLossesTime' : lineReactiveLossesTime,
    #                         'lineActivePowerTimeTo' : lineActivePowerTimeTo,
    #                         'lineReactivePowerTimeTo' : lineReactivePowerTimeTo,
    #                         'lineActivePowerTimeFrom' : lineActivePowerTimeFrom,
    #                         'lineReactivePowerTimeFrom' : lineReactivePowerTimeFrom,
                            
    #                         'trafoLoadingTime' : trafoLoadingTime,
    #                         'trafoActiveLossesTime' : trafoActiveLossesTime,
    #                         'trafoReactiveLossesTime' : trafoReactiveLossesTime,
                            
    #                         'loadPowerTime' : loadPowerTime,
                            
    #                         'genPowerTime' : genPowerTime,
    #                         }


    # print("Number of timestep without convergence: " + str(count_no_convergence) + "\n")
    # print("**** Time series power flow analysis completed! \n(" + str(start_time) + "; " + str(end_time) + ") ****\n")

    # ##########################################################################################################################

    # # export dictionary in external file
    # result_filename = case_denomination + '.pkl'
    # export_TS_PF_results(result_TS_PF, result_filename)

    # return result_TS_PF

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def export_TS_PF_results(all_results, filename):

    config = yaml.safe_load(open("config.yml", 'r'))
    folder_result = config["foldername_result_PF"] # foldername to save results

    # export dictionary in external file
    # now = datetime.datetime.now().strftime("(%Y-%m-%d_%H-%M)")
    with open(folder_result + filename, 'wb') as fp:
        pickle.dump(all_results, fp)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def load_configuration(config_path="config.yml"):

    config = yaml.safe_load(open(config_path, "r"))

    return config

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def load_time_series(config, resample_interval="1H"):

    year = config["start_date"].year

    start_time = datetime(year, 1, 1, 0, 0, 0)
    end_time = datetime(year, 12, 31, 23, 45, 0)

    filename = config["filename_pod_energy_exchange"]

    df = pd.read_csv(filename)

    df["datetime"] = pd.to_datetime(df["datetime"])

    df.set_index("datetime", inplace=True)

    df = df.loc[start_time:end_time]

    if resample_interval is not None:
        df = df.resample(resample_interval).sum()

    return df

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def preprocess_profiles(config, network, data_simulation):

    filename = config["filename_data"]

    load_df = pd.read_excel(
        filename,
        sheet_name="load"
    )

    load_df = load_df.dropna(subset=["id_pod"])

    missing_pods = [
        pod for pod in load_df["id_pod"]
        if pod not in data_simulation.columns
    ]

    if missing_pods:

        print("\nWARNING: Missing PODs in time series:\n")

        for pod in missing_pods:
            print(pod)

    mapping_df = load_df[
        ["name", "id_pod", "power factor"]
    ].copy()

    ts_transposed = data_simulation.T

    mapping_df.set_index("id_pod", inplace=True)

    df_P = mapping_df.join(
        ts_transposed,
        how="inner"
    )

    df_P["load_name"] = df_P["name"]

    df_P.set_index("load_name", inplace=True)

    df_P = df_P.reindex(network.load["name"])

    power_factor = (
        df_P["power factor"]
        .replace("-", 1)
        .fillna(1)
        .astype(float)
        .clip(lower=0.01, upper=1)
    )

    time_delta = (
        data_simulation.index[1] - data_simulation.index[0]
    ).seconds / 60

    df_P = df_P.drop(columns=["name", "power factor"])

    # kWh/timestep -> kW
    df_P = df_P / (time_delta / 60)

    # kW -> MW
    df_P = df_P / 1000

    tan_phi = np.tan(np.arccos(power_factor.values))

    df_Q = df_P.mul(tan_phi, axis=0)

    return df_P, df_Q

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def initialize_result_buffers(network, n_timesteps):

    dtype = np.float32

    buffers = {

        "ext_p": np.zeros(
            (n_timesteps, len(network.ext_grid)),
            dtype=dtype
        ),

        "ext_q": np.zeros(
            (n_timesteps, len(network.ext_grid)),
            dtype=dtype
        ),

        "bus_vm": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "bus_p": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "bus_q": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "line_loading": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_pl": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_ql": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_p_to": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_q_to": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_p_from": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_q_from": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "trafo_loading": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "trafo_pl": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "trafo_ql": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "load_p": np.zeros(
            (n_timesteps, len(network.load)),
            dtype=dtype
        )
    }

    if len(network.gen) > 0:

        buffers["gen_p"] = np.zeros(
            (n_timesteps, len(network.gen)),
            dtype=dtype
        )

    return buffers

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def run_single_power_flow(network, p_mw, q_mvar, first_run):

    network.load["p_mw"] = p_mw
    network.load["q_mvar"] = q_mvar

    kwargs = dict(
        net=network,
        algorithm="nr",
        init="flat" if first_run else "results",
        tolerance_mva=1e-6,
        max_iteration=20,
        numba=False,
        verbose=False
    )

    # recycle only after first successful PF
    if not first_run:

        kwargs["recycle"] = {
            "trafo": True,
            "gen": True,
            "bus_pq": True,
            "Ybus": True
        }

    pp.runpp(**kwargs)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def store_timestep_results(network, buffers, i):

    buffers["ext_p"][i] = network.res_ext_grid["p_mw"].values
    buffers["ext_q"][i] = network.res_ext_grid["q_mvar"].values

    buffers["bus_vm"][i] = network.res_bus["vm_pu"].values
    buffers["bus_p"][i] = network.res_bus["p_mw"].values
    buffers["bus_q"][i] = network.res_bus["q_mvar"].values

    buffers["line_loading"][i] = network.res_line["loading_percent"].values
    buffers["line_pl"][i] = network.res_line["pl_mw"].values
    buffers["line_ql"][i] = network.res_line["ql_mvar"].values

    buffers["line_p_to"][i] = network.res_line["p_to_mw"].values
    buffers["line_q_to"][i] = network.res_line["q_to_mvar"].values

    buffers["line_p_from"][i] = network.res_line["p_from_mw"].values
    buffers["line_q_from"][i] = network.res_line["q_from_mvar"].values

    buffers["trafo_loading"][i] = network.res_trafo["loading_percent"].values
    buffers["trafo_pl"][i] = network.res_trafo["pl_mw"].values
    buffers["trafo_ql"][i] = network.res_trafo["ql_mvar"].values

    buffers["load_p"][i] = network.res_load["p_mw"].values

    if "gen_p" in buffers:
        buffers["gen_p"][i] = network.res_gen["p_mw"].values

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def run_time_series_pf(
    network,
    time_index,
    df_P,
    df_Q,
    buffers
):

    first_run = True

    count_no_convergence = 0

    for i, t in enumerate(
        tqdm(
            time_index,
            desc="Time series power flow",
            unit="timestep"
        )
    ):

        try:

            run_single_power_flow(
                network=network,
                p_mw=df_P[t].values,
                q_mvar=df_Q[t].values,
                first_run=first_run
            )

            first_run = False

            store_timestep_results(
                network,
                buffers,
                i
            )

        except pp.LoadflowNotConverged:

            count_no_convergence += 1

            print(red(f"WARNING: PF not converged at {t}"))

    print(
        f"\n - Number of timestep without convergence: "
        f"{count_no_convergence}"
    )

    return buffers

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def build_result_dataframes(
    network,
    time_index,
    buffers
):

    results = {

        "extgridActivePowerTime": pd.DataFrame(
            buffers["ext_p"],
            index=time_index,
            columns=network.ext_grid["name"]
        ),

        "extgridReactivePowerTime": pd.DataFrame(
            buffers["ext_q"],
            index=time_index,
            columns=network.ext_grid["name"]
        ),

        "busVoltageTime": pd.DataFrame(
            buffers["bus_vm"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "busActivePowerTime": pd.DataFrame(
            buffers["bus_p"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "busReactivePowerTime": pd.DataFrame(
            buffers["bus_q"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "lineLoadingTime": pd.DataFrame(
            buffers["line_loading"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActiveLossesTime": pd.DataFrame(
            buffers["line_pl"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactiveLossesTime": pd.DataFrame(
            buffers["line_ql"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActivePowerTimeTo": pd.DataFrame(
            buffers["line_p_to"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactivePowerTimeTo": pd.DataFrame(
            buffers["line_q_to"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActivePowerTimeFrom": pd.DataFrame(
            buffers["line_p_from"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactivePowerTimeFrom": pd.DataFrame(
            buffers["line_q_from"],
            index=time_index,
            columns=network.line["name"]
        ),

        "trafoLoadingTime": pd.DataFrame(
            buffers["trafo_loading"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "trafoActiveLossesTime": pd.DataFrame(
            buffers["trafo_pl"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "trafoReactiveLossesTime": pd.DataFrame(
            buffers["trafo_ql"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "loadPowerTime": pd.DataFrame(
            buffers["load_p"],
            index=time_index,
            columns=network.load["name"]
        )
    }

    if "gen_p" in buffers:

        results["genPowerTime"] = pd.DataFrame(
            buffers["gen_p"],
            index=time_index,
            columns=network.gen["name"]
        )

    return results

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def export_results(result_TS_PF, case_denomination):

    result_filename = case_denomination + ".pkl"

    export_TS_PF_results(
        result_TS_PF,
        result_filename
    )

    print(f"\n - Results exported:", blue(f"{result_filename}"))

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def load_flow_simulator(case_denomination, network):

    config = load_configuration()

    data_simulation = load_time_series(config)

    df_P, df_Q = preprocess_profiles(
        config=config,
        network=network,
        data_simulation=data_simulation
    )

    buffers = initialize_result_buffers(
        network=network,
        n_timesteps=len(data_simulation)
    )

    buffers = run_time_series_pf(
        network=network,
        time_index=data_simulation.index,
        df_P=df_P,
        df_Q=df_Q,
        buffers=buffers
    )

    result_TS_PF = build_result_dataframes(
        network=network,
        time_index=data_simulation.index,
        buffers=buffers
    )

    export_results(
        result_TS_PF=result_TS_PF,
        case_denomination=case_denomination
    )

    print(green(
        "\n     **** Time series power flow analysis completed! ****\n"
    ))

    return result_TS_PF

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def initialize_load_flow_simulator():
    
    n_iterations = 9 # number of iterations to perform for each day type (for the entire year)

    with tqdm(total=n_iterations, desc="Load flow simulator") as pbar:

        #---------------------------------------------------------------------------------------------
        # 1. Get calendar
        #---------------------------------------------------------------------------------------------

        pbar.set_description("1. Get calendar")
        suppress_printing(generate_calendar)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 2. Import power flow data in CACER simulator
        #---------------------------------------------------------------------------------------------

        pbar.set_description("2. Import power flow data in CACER simulator")
        suppress_printing(modify_user_CACER_xlsx)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 3. Extract users and plant data
        #---------------------------------------------------------------------------------------------

        pbar.set_description("3. Extract users and plant data")
        suppress_printing(generate_users_yml, base=36)
        suppress_printing(generate_plant_yml) 
        suppress_printing(membership_matrix)
        suppress_printing(plant_operation_matrix)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 4. Restore CACER simulator
        #---------------------------------------------------------------------------------------------

        pbar.set_description("4. Restore CACER simulator")
        suppress_printing(restore_user_CACER_xlsx)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 5. Emulate domestic users load profile
        #---------------------------------------------------------------------------------------------

        pbar.set_description("5. Emulate domestic users load profile")
        suppress_printing(run_load_emulator)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 6. Simulate all users load profile
        #---------------------------------------------------------------------------------------------

        pbar.set_description("6. Simulate all users load profile")
        suppress_printing(load_profile_all_users)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 7. Simulate all plants production profile
        #---------------------------------------------------------------------------------------------

        pbar.set_description("7. Simulate all plants production profile")
        suppress_printing(simulate_configuration_productivity)
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 8. Calculate users energy flows
        #---------------------------------------------------------------------------------------------

        pbar.set_description("8. Calculate users energy flows")
        suppress_printing(CACER_energy_flows)
        pbar.update(1)
        
        #---------------------------------------------------------------------------------------------
        # 9. Export all users energy exchange profiles
        #---------------------------------------------------------------------------------------------
        
        pbar.set_description("9. Export all users energy exchange profiles")
        suppress_printing(export_energy_exchange_profiles_csv)
        pbar.update(1)

        pbar.set_description("Finished")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------