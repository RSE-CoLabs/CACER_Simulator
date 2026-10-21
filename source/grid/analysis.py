from __future__ import annotations

import pandas as pd


def result_analysis(network):
    loads = network.res_bus["p_mw"] # loads of the bus in [MW]
    peak_bus = network.bus.loc[loads.idxmax(),'name'] # name of the bus whit maximum load
    peak_load = loads.max() # maximum load in the network for the buses [mW]
    print("Peak load:", round(peak_load * 1000, 2), "kW at", peak_bus)
    # print("\n")

    peak_voltage = network.res_bus.loc[loads.idxmax(),'vm_pu'] # maximum voltage for the buses in the network [p.u.]
    print("Voltage at peak:", round(peak_voltage, 2), "p.u. at", peak_bus)


def voltage_check(network):

    # checking for voltage violations in the results in the bus with min value of each bus
    # if violations adding it to a variable
    if "min_vm_pu" in network.res_bus.columns and "max_vm_pu" in network.res_bus.columns:
        voltage_violations = network.res_bus [
                        (network.res_bus["vm_pu"] < network.bus["min_vm_pu"])| # checking if vm_pu < min_vm_pu
                        (network.res_bus["vm_pu"] > network.bus ["max_vm_pu"])] # checking if vm_pu > max_vm_pu
    else:
        min_vm_pu = 0.95
        max_vm_pu = 1.05

        voltage_violations = network.res_bus [
                        (network.res_bus["vm_pu"] < min_vm_pu)| # checking if vm_pu < min_vm_pu
                        (network.res_bus["vm_pu"] > max_vm_pu)] # checking if vm_pu > max_vm_pu

    return voltage_violations


def voltage_analysis(network):

    #voltage check
    check = voltage_check (network)

    # checking and printing the violated buses
    if len(check)==0:
        print('No voltage violations')
    else:
        print("List of all the bus that have a violations in the voltage limits: \n")
        print(check)

        return check


def bus_voltage_violations_analysis(busVoltageTime):

    busVoltageIssue = busVoltageTime.loc[:,(
        (busVoltageTime<0.95) | (busVoltageTime>1.05) ).any()]

    # creating a table with the minimum and maximum voltage for buses with violations
    minVoltage = busVoltageIssue.min().to_frame(name="vm_min").reset_index()
    maxVoltage = busVoltageIssue.max().to_frame(name="vm_max").reset_index()
    tableVoltageIssue = pd.merge(minVoltage,maxVoltage)

    # printing the table with overloaded lines
    if not tableVoltageIssue.empty:
        print("Number of issues: " + str(tableVoltageIssue.columns.size) + "\n")
        print(tableVoltageIssue)
    else:
        print("No voltage issues!")

    return tableVoltageIssue


def line_loading_issue_analysis(lineLoadingTime):
    lineLoadingIssue = lineLoadingTime.loc[:,(lineLoadingTime>100).any()] # we extract just lines with load violations

    # creating a table with the average and maximum loading of lines with issues
    minLoading = lineLoadingIssue.min().to_frame(name="min_loading").reset_index() # minimum value for load of the lines with load violations
    avgLoading = (lineLoadingIssue.sum()/len(lineLoadingIssue)).to_frame(name="avg_loading").reset_index() # average value for load of the lines with load violations (over time for the entire week)
    maxLoading = lineLoadingIssue.max().to_frame(name="max_loading").reset_index() # maximum value for load of the lines with load violations

    tableLineLoadingIssue = pd.merge(minLoading,avgLoading).merge(maxLoading) # merge minLoading, avgLoading and maxLoading into a single df

    # printing the table with overloaded lines
    if not tableLineLoadingIssue.empty:
        print("Number of issues: " + str(lineLoadingIssue.columns.size) + "\n")
        print(tableLineLoadingIssue)
    else:
        print("No loading line issues!")

    return lineLoadingIssue


def trafo_loading_issue_analysis(trafoLoadingTime):
    trafoLoadingIssue = trafoLoadingTime.loc[:,(trafoLoadingTime>100).any()] # we extract just trafos with load violations

    # creating a table with the average and maximum loading of transformers with issues
    minLoading = trafoLoadingIssue.min().to_frame(name="min_loading").reset_index()  # minimum value for load of the trafos with load violations
    avgLoading = (trafoLoadingIssue.sum()/len(trafoLoadingIssue)).to_frame(name="avg_loading").reset_index() # average value for load of the trafos with load violations (over time for the entire week)
    maxLoading = trafoLoadingIssue.max().to_frame(name="max_loading").reset_index() # maximum value for load of the trafos with load violations

    tableTrafoLoadingIssue = pd.merge(minLoading,avgLoading).merge(maxLoading) # merge minLoading, avgLoading and maxLoading into a single df

    # printing the table with overloaded lines
    if not tableTrafoLoadingIssue.empty:
        print("Number of issues: " + str(trafoLoadingIssue.columns.size) + "\n")
        print(tableTrafoLoadingIssue)
    else:
        print("No loading trafo issues!")

    return trafoLoadingIssue


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
                print("All condition are verified!\n")
            else:
                print("There is some violations of the limits!")
                if not check_1:
                    print("SSVV limit is not verified!")
                if not check_2:
                    print("RVC limit is not verified!")
                if not check_3:
                    print("Thermal limit is not verified!")
                print("")


def summarize_violations(
    results: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame | int | bool]:
    voltage = bus_voltage_violations_analysis(results["busVoltageTime"])
    lines = line_loading_issue_analysis(results["lineLoadingTime"])
    transformers = trafo_loading_issue_analysis(results["trafoLoadingTime"])
    return {
        "voltage": voltage,
        "lines": lines,
        "transformers": transformers,
        "voltage_violation_count": len(voltage),
        "line_violation_count": len(lines.columns),
        "transformer_violation_count": len(transformers.columns),
        "ssvv_ok": bool(SSVV_check(results["busVoltageTime"])),
        "rvc_ok": bool(RVC_check(results["busVoltageTime"])),
        "thermal_limits_ok": bool(
            thermal_limits_check(
                results["lineLoadingTime"],
                results["trafoLoadingTime"],
            )
        ),
    }


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


def thermal_limits_check(lineLoadingTime, trafoLoadingTime):
    return check_overloading(lineLoadingTime) and check_overloading(trafoLoadingTime)


def check_overloading(df):
    for column in df.columns:
        violations = sum(df[column] > 100)
        if violations > 0:
            return False
        else:
            return True
