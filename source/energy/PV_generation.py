from __future__ import annotations

import calendar
import contextlib
import csv
import datetime as dt
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import io
import math
import os
import shutil
import tempfile
from typing import Any, Callable, Mapping, Sequence
import warnings

from concurrent.futures import ThreadPoolExecutor
from geopy.geocoders import Nominatim
import numpy as np
import pandas as pd
import plotly.graph_objs as go
import pvlib
from pvlib import location, pvsystem
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import Array, FixedMount, PVSystem
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS as PARAMS
from random import choice, random
from simple_colors import blue, green, red
from tqdm.auto import tqdm

from source.config.utilities import location_italian_to_english


Coordinates = tuple[float, float, str, float, str]
CoordinateProvider = Callable[[Sequence[str]], list[Coordinates]]
WeatherProvider = Callable[[list[Coordinates], int], list[pd.DataFrame]]


@dataclass(frozen=True, slots=True)
class PVSimulationOptions:
    module_name: str = "Shell_Solar_SM100_24__2003__E__"
    inverter_name: str = "Enphase_Energy_Inc___M175_24_208_Sxx__208V_"
    weather_source: str = "PVGIS TMY"
    coordinates: Mapping[str, Coordinates] | None = None
    weather: Mapping[str, pd.DataFrame] | None = None
    coordinate_provider: CoordinateProvider | None = None
    weather_provider: WeatherProvider | None = None


def simulate_location_productivity(
    location,
    tilt_angle,
    azimuth,
    *,
    settings: Mapping[str, Any],
    coordinates_dataset: list[Coordinates] | None = None,
    weather_frames: list[pd.DataFrame] | None = None,
):

    """
    Simulate the productivity of a PV plant with a capacity of 1 kWp in a given location with a fixed delta_t
    (the results are derated respect to a corrective parameter)

    Parameters
    location : str, location of the PV plant
    tilt_angle : float, tilt angle of the PV plant
    azimuth : float, azimuth of the PV plant

    """
    print(blue("- Simulation of the productivity for a pv plant with a capacity of 1 kWp:", ['bold']))

    # create a dataset with the coordinates of all the locations
    locations_input = [location]
    coordinates_dataset = coordinates_dataset or suppress_printing(
        create_coordinates_dataset,
        locations_input,
    )

    # calculate the productivity for a PV plant with a capacity of 1 kWp in the selected location with a fixed delta t (the results are derated respect the GSE/RSE annual production found in the report)
    # result_ac_energies_resampled is a dictionary where the keys are the locations in input
    result_ac_energies_resampled = suppress_printing(
        simulate_1_kWp_generators,
        coordinates_dataset,
        tilt_angle,
        azimuth,
        settings=settings,
        weather_frames=weather_frames,
    )

    # derate the annual productivity with the derating factor that reduce the efficiency of the modules

    derating_factor = settings['pv_derating_factor']
    result_ac_energies_gens_derated = suppress_printing(
        simulate_gens_derated_productivity,
        derating_factor,
        result_ac_energies_resampled,
        start_date=settings["start_date"],
        project_lifetime_yrs=int(settings["project_lifetime_yrs"]),
    )

    # crete two unstacked dataframe (the other functions work with dictionaries)
    return suppress_printing(
        simulate_unstacked_productivity,
        result_ac_energies_gens_derated,
        calendar_frame=settings["calendar"],
        start_date=settings["start_date"],
        project_lifetime_yrs=int(settings["project_lifetime_yrs"]),
    )


def simulate_1_kWp_generators(
    coordinates_dataset,
    tilt_angle,
    azimuth,
    *,
    settings: Mapping[str, Any],
    weather_frames: list[pd.DataFrame] | None = None,
    module_name: str = "Shell_Solar_SM100_24__2003__E__",
    inverter_name: str = "Enphase_Energy_Inc___M175_24_208_Sxx__208V_",
):

    """calculating the productivity for a photovoltaic generator with an installed capacity of 1 kWp for the selected locations
    using hourly time interval and obtaining a dictionary as output, in which the keys are the input locations.
    Inputs:
        gen_data                           dictionary with {'location' : location, 'capacity' : capacity, 'tilt_angle' : tilt_angle, 'azimuth' : azimuth}
    Outputs:
        result_ac_energies_resampled       dictionary in which we save the results for each time iteration in (kWh / delta t) [dict]
    """

    # set parameters for the photovoltaic module and the inverter
    module, inverter = set_system(module_name, inverter_name)

    # create a typical meteorological year for the locations in the list
    tmys = weather_frames or weather_data(
        coordinates_dataset,
        start_year=int(str(settings["start_date"])[:4]),
    )

    # calculate the productivity for the selected photovoltaic module and inverter
    result_ac_energies = simulate_module_productivity(coordinates_dataset, tmys, module, tilt_angle, azimuth, inverter)

    # calculate the productivity for a pv plant with a capacity of 1 kWp
    result_ac_energies_1kWp = simulate_1_kWp_productivity(module, result_ac_energies)

    # resample data with the correct datetime
    result_ac_energies_resampled = simulate_resampled_productivity(
        result_ac_energies_1kWp,
        interval=str(settings["delta_t"]),
        start_year=int(str(settings["start_date"])[:4]),
    )

    return  result_ac_energies_resampled


def simulate_configuration_productivity(
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    calendar_frame: pd.DataFrame,
    settings: Mapping[str, Any],
    municipalities: pd.DataFrame,
    *,
    options: PVSimulationOptions | None = None,
):

    """we calculate the productivity for each installed photovoltaic generators of the configuration under exam
       in different time interval (1 hour, daily, monthly)

    Outputs:
        output_gen_pv.csv                   .csv file
    """

    print(blue("\nGenerate production profile for user types added:", ['bold', 'underlined']))

    print("\n0. Simulation of the productivity for each generators ")
    return simulate_pv_profiles(
        user_types,
        plants,
        calendar_frame,
        settings,
        municipalities,
        options=options,
    )


def get_input_gens_analysis(
    registry_user_types: Mapping[str, Mapping[str, Any]],
    municipalities: pd.DataFrame,
):

    """Reading the data from the yaml file and save them into the internal variables of the script

    Outputs:
        locations_input
        capacity_input
        gen_data
    """
    # initializing dictrionaries andl lists to save the data of the generators of the configuration under exam
    gen_data = {}
    locations_input = []
    capacity_input = {}

    for user in registry_user_types:

        if str(registry_user_types[user]['pv']) == "nan" or registry_user_types[user]['pv'] == 0:
            pass

        else:
            location_it = str(registry_user_types[user]['location'])
            location = location_italian_to_english(location_it, municipalities)
            capacity = float(registry_user_types [user]['pv']) # installed capacitity for the given plant
            tilt_angle = float(registry_user_types[user]['tilt_angle']) # tilt angle of the modules over the horizontal surface in degrees
            azimuth = float(registry_user_types[user]['azimuth']) # azimuth angle of the modules, with respect to South

            gen_data [user] = {'location' : location, 'capacity' : capacity, 'tilt_angle' : tilt_angle, 'azimuth' : azimuth} # saving useful information in a dictionary

            locations_input.append(location) # saving all locations to be analyzed in a list

            capacity_input.setdefault(location, [])
            capacity_input[location].append(capacity) # saving the installed capacity for each location, dictionary indixed on locations

    locations_input = [*set(locations_input)] # removing duplicates
    locations_input.sort() # sorting in alphabetic order

    return locations_input, capacity_input, gen_data


def get_coordinates(address):

    """we evaluate the latitude and the longitude of a location in input as "address" (it needs just the name of the location, ex. "Roma")
    Inputs:
        address              the name of the location you want to evaluate latitude and longitude [str]
    Outputs:
        location.latitude    latitude of the location [float]
        location.longitude   longitude of the location [float]
    """

    geolocator = Nominatim(user_agent="myapplication")
    location = geolocator.geocode(address)

    return location.latitude, location.longitude


def create_coordinates_dataset(locations_input):

    """we create a dataset in which we save for each location under exam the values of latitude, longitude, name, altitude and time zone
    Inputs:
        locations_input        list with the name of the locations under exam [list]
    Outputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    """

    coordinates_dataset = [] # initialization

    for name_location in locations_input:

        try:

            latitude_location = get_coordinates(name_location)[0]
            longitude_location = get_coordinates(name_location)[1]
            altitude_location = pvlib.location.lookup_altitude(latitude_location, longitude_location)
            data_location = (latitude_location, longitude_location, name_location, altitude_location, 'Etc/GMT+2')

        except Exception as e:
            print(f"Error getting coordinates for {name_location}: {e}")
            data_location = (45.4685, 9.1824, name_location, 0, 'Etc/GMT+2')

        coordinates_dataset.append(data_location)

    print("\n2. Creation of the dataset with geographical information completed!")

    return coordinates_dataset


def set_system(
    module_name: str = "Shell_Solar_SM100_24__2003__E__",
    inverter_name: str = "Enphase_Energy_Inc___M175_24_208_Sxx__208V_",
):

    """we select the module and the inverter
    Inputs:
        -
    Outputs:
        module        module item and its parameters (we fix a module with a nominal power of 100 W)
        inverter      inverter item and its parameters (we fix an inverter who respects the limits of power, voltage and current of the selected module)
    """

    sandia_modules = pvsystem.retrieve_sam('SandiaMod') # possible dataset: CECMod, SandiaMod

    # inserting the nominal power in the sandia dataset
    sorted_sandia_modules = sandia_modules

    for column in sorted_sandia_modules:
        Pmpo = sorted_sandia_modules.loc['Impo', column] * sorted_sandia_modules.loc['Vmpo', column] # potenza nominale del modulo
        sorted_sandia_modules.loc['Pmpo', column] = Pmpo
    sorted_sandia_modules = sorted_sandia_modules.sort_values('Pmpo', axis = 1, ascending = False)

    CEC_inverters = pvsystem.retrieve_sam('cecinverter') # for example, using the CEC inverter dataset

    module = sandia_modules[module_name]
    # module = sorted_CEC_modules['MiasoleLEX_03_500W'] # choosing module from the CEC modules dataset

    # calcuting the max power power
    Pmpo_selected_mod = sorted_sandia_modules.loc['Pmpo', module.name]

    # inverter = sandia_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_'] # choosing one of the Sandia inverters
    inverter = CEC_inverters[inverter_name]

    inverter['Pnt'] = 0

    print("3. Setting of the photovoltaic system parameters completed!")

    return module, inverter


def select_desired_module(desired_pow_value):

    """Selecting the module with the desired nominal power
    Inputs:
        desired_pow_value    value of the desired power of the module in (W) [float]
    Outputs:
        module               module item and its parameters
    """

    sandia_modules = pvsystem.retrieve_sam('SandiaMod') # possible dataset: CECMod, SandiaMod

    # inserting the nominal power in the sandia dataset
    sorted_sandia_modules = sandia_modules

    for column in sorted_sandia_modules:
        Pmpo = sorted_sandia_modules.loc['Impo', column] * sorted_sandia_modules.loc['Vmpo', column] # mudule nominal rated power
        sorted_sandia_modules.loc['Pmpo', column] = Pmpo
    sorted_sandia_modules = sorted_sandia_modules.sort_values('Pmpo', axis = 1, ascending = False)

    desired_pow = desired_pow_value # power [W]
    prev_diff_pow = 1000000 # setting a high value for the difference between the desired power and the module nominal rated power, that will be overwritten in the loop

    for key in sorted_sandia_modules.keys():
        Pmpo_test = sorted_sandia_modules[key]['Pmpo']
        diff_pow = abs(Pmpo_test - desired_pow)

        if diff_pow < prev_diff_pow:
            desired_key = key
            prev_diff_pow = diff_pow
        else:
            prev_diff_pow = diff_pow

    print("Desired module key:" , desired_key, '\n')
    # print("Parameters of the desired module:\n\n", sorted_sandia_modules[desired_key])

    desired_module = sorted_sandia_modules[desired_key]

    Pmpo_selected_mod = desired_module['Pmpo']

    # si plotta a schermo la relativa potenza di picco del modulo selezionato
    print("Peak power of the desired module : ", round(Pmpo_selected_mod, 2), 'W')

    print("Individuation of the module with the desired nominal power completed!")

    return desired_module


def check_inverter(module):

    """selecting the inverter who respects the limits of power, voltage and current for the module in input
    Inputs:
        module       module item and its parameters
    Outputs:
        inverter     inverter item and its parameters
    """

    Tmax = 85 # max operating temperature [°C]
    Tmin = -40 # min operating temperature [°C]
    Tamb = 25 # ambient temperature [°C]

    Vmpp = module['Vmpo'] # max power point voltage [V]
    Voc = module['Voco'] # open circuit voltage [V]
    Isc = module['Isco'] # short circuit current [A]

    beta_volt_mp = module['Bvmpo'] / 100 # voltage temperature coefficient at max power point [%]
    beta_volt_oc = module['Bvoco'] / 100 # voltage temperature coefficient at open circuit [%]
    beta_curr_sc = module['Aisc'] / 100 # current temperature coefficient at short circuit [%]

    num_mod_per_string = 1 # number of modules per string
    num_string = 1 # number of strings

    Vmax_string = Vmpp * num_mod_per_string # max voltage per string    [V]
    Voc_string = Voc * num_mod_per_string # open circuit voltage per string [V]
    Isc_PV = Isc * num_string # short circuit current for the PV arrays [A]

    V_mod_Tmin = Vmax_string * (1-beta_volt_mp*(Tamb-Tmin))
    V_mod_Tmax = Vmax_string * (1-beta_volt_mp*(Tamb-Tmax))
    V_max_Tmin = Voc_string * (1-beta_volt_oc*(Tamb-Tmin))
    Idcmax_mod = Isc_PV * (1-beta_curr_sc*(Tamb-Tmax))
    Pdc_mod = module['Pmpo']

    CEC_inverters = pvsystem.retrieve_sam('cecinverter')
    sorted_CEC_inverters = CEC_inverters.sort_values('Paco', axis = 1, ascending = True)

    check_tot = 0

    for key in sorted_CEC_inverters.keys():

        inverter_test = sorted_CEC_inverters[key]

        Vmax_inverter = inverter_test['Mppt_high'] # max inverter temperature
        Vmin_inverter = inverter_test['Mppt_low'] # min inverter temperature
        Idcmax_inverter = inverter_test['Idcmax'] # max current inverter in DC
        Pdc_inverter = inverter_test['Pdco'] # max power inverter in DC

        # check 1 => V_Tmin > 1.2 * Vmin_inverter
        if V_mod_Tmin > 1.2 * Vmin_inverter:
            check_1 = 1
        else:
            check_1 = 0

        # check 2 => V_mod_Tmax < 0.8 * Vmax_inverter
        if V_mod_Tmax < 0.8 * Vmax_inverter:
            check_2 = 1
        else:
            check_2 = 0

        # check 3 => Vmax_Tmin > 0.8 * Vmax_inverter
        if V_max_Tmin > 0.8 * Vmax_inverter:
            check_3 = 1
        else:
            check_3 = 0

        # check 4 => 0.5 * Idcmax_mod < Idcmax_inverter
        if Idcmax_inverter > 0.5 * Idcmax_mod:
            check_4 = 1
        else:
            check_4 = 0

        # check 5 => Pdc,STC < 0.8 * Pdc, inverter
        if Pdc_mod < 0.8 * Pdc_inverter:
            check_5 = 1
        else:
            check_5 = 0

        check_tot = check_1 * check_2 * check_3 * check_4 * check_5

        if check_tot == 1:
            break

    if check_tot == 1:
        print('Result of the research: Compatible inverter found! \n')

        # looking for the inverter
        inverter_checked = sorted_CEC_inverters[key]
        print("Name of the module under exam: ", module.name, '\n')
        print("Name of the verified inverter: ", inverter_checked.name, '\n')
    else:
        print('Result of the research: No compatible inverters! \n')

    print("Individuation of the compatible inverter completed!")

    inverter_checked['Pnt'] = 0

    return inverter_checked


def weather_data(
    coordinates_dataset,
    *,
    start_year: int,
):

    """calculating a tipical meteorogical year (tmys) for the selected locations from PVGIS
    via pvlib function "pvlib.iotools.get_pvgis_tmy", with timestep of 60 minutes.
    For more info:  https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.iotools.get_pvgis_tmy.html

    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    Outputs:
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
    """

    coordinates = coordinates_dataset

    tmys = [] # initialization of the list containing the tmys data for the locations

    for location in coordinates:
        latitude, longitude, name, altitude, timezone = location
        weather = pvlib.iotools.get_pvgis_tmy(latitude, longitude, map_variables=True)[0] # Get TMY data from PVGIS
        weather.index.name = "datetime"
        weather.index = weather.index.map(lambda t: t.replace(year=start_year))

        # # Convert the time column to datetime and set it to UTC
        # weather.index = pd.to_datetime(weather.index, utc=True)

        # # Set the local timezone (for example, 'Europe/Rome')
        # local_timezone = 'Europe/Rome'
        # weather.index = weather.index.tz_convert(local_timezone)

        # Replace the first three rows with 0 (instead of NaN)
        weather = weather.shift(2)
        weather.iloc[:1] = 0

        # Convert the time column to datetime and set it to UTC
        weather.index = pd.to_datetime(weather.index, utc=True)

        # Set the local timezone (for example, 'Europe/Rome')
        local_timezone = 'Europe/Rome'
        weather.index = weather.index.tz_convert(local_timezone)

        tmys.append(weather)

    print("\n4. Creation of the datasets with meteorogical data for the selected locations completed!")

    return tmys


def weather_data_15_min(
    coordinates_dataset,
    *,
    start_year: int,
):

    """Calculating a tipical meteorogical year (tmys) for the selected locations
    via pvlib function "pvlib.location.Location.get_clearsky", with timestep of 15 minutes
    For more info:    https://pvlib-python.readthedocs.io/en/latest/_modules/pvlib/location.html#Location.get_clearsky
    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    Outputs:
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
    """

    tmys_15_min = [] # initialization of the list containing the tmys data for the locations

    for coordinates in coordinates_dataset:
        latitude, longitude, name, altitude, timezone = coordinates

        # Calculate the clear sky estimates of GHI, DNI, and/or DHI at this location
        location = location.Location(latitude, longitude) # creating a 'location' object
        times = pd.date_range('2022-01-01 00:00', '2023-01-01 00:00', freq='15min') # creating a time series with delta time of 15 min
        weather = location.get_clearsky(times, model = 'ineichen') # model = 'ineichen', 'haurwitz' or 'simplified_solis', creating a dataframe

        # alternatively, currently suppressed
        # si usa di seguito un'altra libreria sviluppata dall'istituto NREL, non sono purtroppo presenti dati per tutte le località!
        # key = <INSERIRE API KEY>
        # email_personale = <INSERIRE EMAIL PERSONALE>
        # weather = pvlib.iotools.get_psm3(latitude, longitude, api_key = key , email = email_personale , interval = 60)

        weather.index.name = "datetime" # setting index name
        weather.index = weather.index.map(lambda t: t.replace(year=start_year)) # setting the correct year to the weather dataframe
        weather = weather[~weather.index.duplicated(keep='first')] # removing duplicates
        tmys_15_min.append(weather) # appending the data for each location

    print("\nCreation of the dataset with meteorogical data with a time interval of 15 min for the selected location completed!")

    return tmys_15_min


def simulate_module_productivity(coordinates_dataset, tmys, module, tilt_angle, azimuth, inverter):

    """simulating the system under exam and calculating the results
       in different time interval (delta t, daily, monthly, yearly)
    Inputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
        tmys                   list of the meteorogical parameters for the locations under exam in a tmys [list]
        module                 module type and its parameters
        inverter               inverter type and its parameters
    Outputs:
        result_ac_energies     dictionary in which we save the results for each time iteration in (kWh) for 100 Wp photovoltaic generator [dict]
    """

    # setting the thermal model parameters
    temperature_model_parameters = PARAMS['sapm']['open_rack_glass_glass']

    result_ac_energies = {} # initialazing the result dictionary

    # calculating the annual energy production for each location
    for location, weather in zip(coordinates_dataset, tmys):

        #GEOGRAPHICAL INFORMATION
        latitude, longitude, name, altitude, timezone = location
        location = Location(
            latitude,
            longitude,
            name = name,
            altitude = altitude,
            tz = timezone,
        )

        # MOUNTING TYPE
        mount = FixedMount(surface_tilt = tilt_angle, surface_azimuth = azimuth)

        # one array case
        array = Array(
            mount = mount,
            module_parameters = module,
            temperature_model_parameters = temperature_model_parameters,
            modules_per_string = 1,
            strings = 1,
        )

        system = PVSystem(arrays = [array], inverter_parameters=inverter)

        # multiple arrays case
        # array_one = Array(
        #     mount=mount,
        #     module_parameters=module,
        #     temperature_model_parameters=temperature_model_parameters,
        #     modules_per_string = 10,
        #     strings = 2,
        # )

        # array_two = Array(
        #     mount=mount,
        #     module_parameters=module,
        #     temperature_model_parameters=temperature_model_parameters,
        #     modules_per_string = 10,
        #     strings = 4,
        # )

        #system_two_arrays = PVSystem(arrays=[array_one, array_two], inverter_parameters=inverter)

        # creating the model with the system and location characteristics
        mc = ModelChain(system, location)

        # simulating the model with the weather data
        mc.run_model(weather)

        # exporting the AC output results for the selected location
        result_ac = mc.results.ac / 1000 # [kWh]

        # saving the results in a dictionary [name : location]
        result_ac_energies[name] = result_ac # [kWh]

    print("\n5. Simulation of the productivity for a single module completed!")

    return result_ac_energies


def simulate_1_kWp_productivity(module, result_ac_energies):

    """calculating the productivity for a photovoltaic system of 1 kWp
       in different time interval (delta t, daily, monthly, yearly)
    Inputs:
        module                      module type and its parameters
        result_ac_energies          dictionary in which we save the results for each time iteration in (kWh / delta t) for 100 Wp photovoltaic generator [dict]
    Outputs:
        result_ac_energies_1kWp     dictionary in which we save the results for each time iteration in (kWh) for 1 kWp photovoltaic generator [dict]
    """

    result_ac_energies_1kWp = {} # initializing the output dictionary

    Pmpo_selected_mod = module['Pmpo']

    num_mod = round(1000/Pmpo_selected_mod, 0) # calcualating the number of modules needed for 1 kWp system

    # key: location
    for key in result_ac_energies.keys():

        result_ac_energies_1kWp[key] = result_ac_energies[key] * num_mod # results for 1 kWp [kWh]

    print("\n6. Simulation of the productivity for a generator with an installed capacity of 1 kWp completed!")

    return result_ac_energies_1kWp


def simulate_resampled_productivity(
    result_ac_energies_1kWp,
    *,
    interval: str,
    start_year: int,
):

    """resampling the time interval of the data and set it to 1 hour
       in different time interval (1 hour, daily, monthly)
    Inputs:
        result_ac_energies_1kWp_GSE         dictionary in which we save the results for each time iteration in (kWh / delta t) with an yealy limitation based on the GSE/RSE report [dict]
    Outputs:
        result_ac_energies_resampled        dictionary in which we save the results for each time iteration in (kWh / delta t) with resampled data based on the selected delta t [dict]
    """

    result_ac_energies_resampled = {} # initialization of the output dictionary

    time_interval = interval

    time_delta = pd.to_timedelta(time_interval)
    seconds = time_delta.total_seconds()
    hours = seconds / 3600

    # key: location
    for key in result_ac_energies_1kWp.keys():

        result_ac_1H = result_ac_energies_1kWp[key].copy() # [kWh]

        result_ac_1H[result_ac_1H.index[-1]+pd.Timedelta(hours = 1)] = result_ac_1H[-1]

        # if delta_t >= 1h
        if pd.to_timedelta(time_interval) >= pd.to_timedelta('1H'):
            result_ac_resampled = result_ac_1H.resample(time_interval).sum() # [kWh]

        # if delta_t < 1h
        else:
            result_ac_resampled = result_ac_1H.resample(time_interval).interpolate(method = 'linear') * hours # [kWh / 15Min]

        result_ac_energies_resampled[key] = result_ac_resampled # [kWh]

        # creating an index with the correct datetime

        result_ac_energies_resampled[key] = result_ac_energies_resampled[key].reset_index()
        result_ac_energies_resampled[key].index = result_ac_energies_resampled[key]['datetime'] # setting the index
        del result_ac_energies_resampled[key]['datetime'] # removing the created column

        result_ac_energies_resampled[key]=result_ac_energies_resampled[key][:-1]

    # erasing the leap_day values if the initial year of the simulation is a leap year
    if calendar.isleap(start_year):
        for key in result_ac_energies_resampled.keys():
            start_time = str(start_year)+'-02-28 23:45:00'
            end_time = str(start_year)+'-03-01 00:00:00'
            result_ac_energies_resampled[key] = pd.concat([result_ac_energies_resampled[key].loc[:start_time], result_ac_energies_resampled[key].loc[end_time:]])

    print("\n7. Resampling of the data respect the specified delta t completed!")

    return result_ac_energies_resampled


def simulate_gens_productivity(
    registry_user_types: Mapping[str, Mapping[str, Any]],
    municipalities: pd.DataFrame,
    settings: Mapping[str, Any],
    *,
    options: PVSimulationOptions | None = None,
):

    """calculating the productivity for each generator with different capacity
       in different time interval (1 hour, daily, monthly, yearly)
        Outputs:
            result_ac_energies_gens     dictionary with the results for an entire year for every pv plant (different capactity and plant parameters)
        """

    result_ac_energies_gens = {} # initialization of the output dictionary

    # create a list with all locations
    locations_input = []

    for user in registry_user_types.keys():
        location_it = registry_user_types[user]['location']
        location_en = location_italian_to_english(location_it, municipalities)
        locations_input.append(location_en)

    locations_input = list(set(locations_input))

    # create a dataset with the coordinates of all the locations
    selected_options = options or PVSimulationOptions()
    coordinates_dataset = _coordinates_for_locations(
        locations_input,
        selected_options,
    )

    gen_data = get_input_gens_analysis(
        registry_user_types,
        municipalities,
    )[2]

    # key: gen
    for gen in gen_data.keys():
        location = gen_data[gen]['location'] # getting location
        capacity = gen_data[gen]['capacity'] # getting installed capacity [kWp]
        tilt_angle = gen_data[gen]['tilt_angle'] # getting tilt angle [°]
        azimuth = gen_data[gen]['azimuth'] # getting azimuth [°]

        # calculate the productivity for a PV plant with a capacity of 1 kWp in the selected location with a fixed delta t (the results are derated respect the GSE/RSE annual production found in the report)
        # result_ac_energies_resampled is a dictionary where the keys are the locations in input
        result_ac_energies_resampled = simulate_1_kWp_generators(
            coordinates_dataset,
            tilt_angle,
            azimuth,
            settings=settings,
            weather_frames=_weather_for_coordinates(
                coordinates_dataset,
                int(str(settings["start_date"])[:4]),
                selected_options,
            ),
            module_name=selected_options.module_name,
            inverter_name=selected_options.inverter_name,
        )

        # obtaining ht edataframe for each location for the correct capacity
        result_ac_energies_gens[gen] = result_ac_energies_resampled[location] * capacity # [kWh]

    print("\n8. Simulation of the productivity for each generators  completed!")

    return result_ac_energies_gens


def simulate_gens_derated_productivity(
    derating_factor,
    result_ac_energies_gens,
    *,
    start_date: Any,
    project_lifetime_yrs: int,
):

    """calculating the productivity for each generator with different capacity and applying the derating factor
       in different time interval (1 hour, daily, monthly, yearly)
        Inputs:
            result_ac_energies_gens             dictionary in which we save the results for each time iteration in (kWh / delta t) [dict]
        Outputs:
            result_ac_energies_gens_derated     dictionary in which we save the results for each time iteration in (kWh / delta t) considering an annual production derating [dict]
        """

    print("\n9. Derating of the yearly production")

    result_ac_energies_gens_derated = {} # initialization of the output dictionary

    date_string = str(start_date)
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year = str(data.strftime("%Y"))
    project_life_time = project_lifetime_yrs

    # loop over the PV plants
    for gen in result_ac_energies_gens.keys():

        result_ac_energies_gens_derated.setdefault(gen, {}) # setting the key of the dictionary with the name of the generator with an empty dictionary as value

        actual_year = start_year # setting the actual year as the starting year
        derating_factor_init = 0 # initializing the derating factor for the first year to 0

        actual_result_ac_energies = result_ac_energies_gens[gen] # setting the initial values of the results, before the derating [kWh]

        # loop over years
        for year in range (0, project_life_time):

            actual_year_str = str(actual_year)

            result_ac_energies_gens_derated[gen].setdefault(actual_year_str, {}) # setting the key with the denomination of the actual year with a dictionary type value
            result_ac_energies_gens_derated[gen][actual_year_str] = actual_result_ac_energies * (1-derating_factor_init) # filling the derated values for the actual year [kWh]

            # updating the values
            actual_result_ac_energies = result_ac_energies_gens_derated[gen][actual_year_str] # [kWh]

            actual_year = int(actual_year) + 1 # updating the actual year
            derating_factor_init = derating_factor # getting the derating factor for the actual year

    print("\n\tcompleted!")

    return result_ac_energies_gens_derated


def simulate_unstacked_productivity(
    result_ac_energies_gens_derated,
    *,
    calendar_frame: pd.DataFrame,
    start_date: Any,
    project_lifetime_yrs: int,
):
    """calculating the productivity for each generator with different capacity and organizing data in an unstacked format (one column for each generators)
       in different time interval (1 hour, daily, monthly, yearly)
        Inputs:
            result_ac_energies_gens_derated          dictionary in which we save the results for each time iteration in (kWh / delta t) considering an annual production derating [dict]
        Outputs:
            result_ac_energies_to_csv_df             dataframe with results calculated for each timestep in (kWh / delta t) ready for the exportation in csv file [dataframe]
        """

    print("\n10. Formatting the dataset in an unstacked structure")

    result_ac_energies_unstacked = {} # initialization

    date_string = str(start_date)
    data = dt.datetime.strptime(date_string, "%Y-%m-%d")
    start_year_str = str(data.strftime("%Y"))
    start_year_int = int(start_year_str)
    project_life_time = project_lifetime_yrs

    for gen in result_ac_energies_gens_derated.keys():

        result_ac_energies_unstacked_df = pd.DataFrame() # initializing the dataframe with the unstacked results, with a column for eaach user

        result_ac_energies_unstacked.setdefault(gen, {}) # initializing an empty dictionary in which the results will be stored, with the name of the generator as key

        actual_year_int = start_year_int # string with the actual year (string)

        for year in range (0, project_life_time):

            actual_year_str = str(actual_year_int) # string with the actual year (string)

            df = result_ac_energies_gens_derated[gen][actual_year_str].copy()

            df.index = df.index.tz_convert('UTC')

            # Convert to string and remove timezone information
            df.index = df.index.tz_localize(None).strftime('%Y-%m-%d %H:%M:%S')

            shifted_df = df.shift(-4)
            shifted_df.fillna(0, inplace=True)

            shifted_df.index = [actual_year_str + row[4:] for row in shifted_df.index]

            result_ac_energies_unstacked_df = pd.concat([result_ac_energies_unstacked_df , shifted_df]) # iteratively merging the dataframes

            actual_year_int += 1 # updating the actual year

        result_ac_energies_unstacked[gen] = result_ac_energies_unstacked_df # [kWh]

        print('     ' + blue(str(gen)) + ' completed!')

    result_ac_energies_to_csv_df = pd.DataFrame() # creating the dataframe for the export

    for user in result_ac_energies_unstacked.keys():
        result_ac_energies_to_csv_df[user] = round(result_ac_energies_unstacked[user], 3) # [kWh]

    end_year_int = start_year_int + project_life_time

    # checking the condition is True or not
    for year in range(start_year_int, end_year_int):
        val = calendar.isleap(year)

        # adding the leap day if present in the current year
        if val == True:

            # Define the start and end of the desired range in your local time zone (UTC+1)
            start_date = (str(year)+'-02-28 00:00:00')
            end_date = (str(year)+'-03-01 00:00:00')

            # Extract the data between the specified datetime range
            leap_day = result_ac_energies_to_csv_df[(result_ac_energies_to_csv_df.index >= start_date) & (result_ac_energies_to_csv_df.index < end_date)]

            leap_day.index = [row[:8] + "29" + row[10:] for row in leap_day.index]

            start_index = (str(year)+'-02-28 23:45:00')
            end_index = (str(year)+'-03-01 00:00:00')

            df_before = result_ac_energies_to_csv_df.loc[:end_index]  # Include start_index in this case
            df_after = result_ac_energies_to_csv_df.loc[end_index:]     # Include end_index in this case

            df_before = df_before.iloc[:-1]

            df_before.index = df_before.index.str.replace(str(year) + "-02-29", str(year) + "-02-28")

            # Concatenate the DataFrames: before + new_df + after
            result_ac_energies_to_csv_df = pd.concat([df_before, leap_day, df_after])

    print ("\n\tCheck leap day completed!")

    # redefining the dateetimes used to index the dataframes using a calendar generated externally from a function (here it is removed the timezone)
    result_ac_energies_to_csv_df.index = pd.to_datetime(
        calendar_frame["datetime"]
    )
    result_ac_energies_to_csv_df.index.name = 'datetime' # fixing the name of the index

    print("\n\tcompleted!\n")

    return result_ac_energies_to_csv_df


def change_index(df, gen_data):

    """
    Change the index of a dataframe to include location and capacity of each generator.

    Parameters
    df : pandas.DataFrame to change the index of.
    gen_data : dict with the location and capacity of each generator.

    Returns
    df : pandas.DataFrame with the modified index.
    """
    index_list = []

    for index in df.index:
        loc_str = str(gen_data[index]['location'])
        cap_str = str(gen_data[index]['capacity'])

        new_index = index + ' - ' + loc_str + ' - ' + cap_str + ' kWp'

        index_list.append(new_index)

    df.set_index(pd.Index(index_list), drop=False, append=False, inplace=True, verify_integrity=True)

    return(df)


def simulate_pv_profiles(
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
    calendar_frame: pd.DataFrame,
    settings: Mapping[str, Any],
    municipalities: pd.DataFrame,
    *,
    options: PVSimulationOptions | None = None,
) -> pd.DataFrame:
    """Simulate PV production for configured user types using explicit inputs."""
    selected_options = options or PVSimulationOptions()
    calendar_index = pd.DatetimeIndex(
        pd.to_datetime(calendar_frame["datetime"]),
        name="datetime",
    )
    generators = _pv_generators(user_types, plants)
    if not generators:
        return pd.DataFrame(index=calendar_index)

    module, inverter = set_system(
        selected_options.module_name,
        selected_options.inverter_name,
    )
    start_year = int(settings["start_date"].year)
    interval = str(settings["delta_t"])
    annual_derating = float(settings["pv_derating_factor"])
    project_lifetime = int(settings["project_lifetime_yrs"])
    location_names = sorted(
        {
            location_italian_to_english(
                str(values["location"]),
                municipalities,
            )
            for values in generators.values()
        }
    )
    coordinates = _coordinates_for_locations(
        location_names,
        selected_options,
    )
    weather_frames = _weather_for_coordinates(
        coordinates,
        start_year,
        selected_options,
    )
    weather_by_location = {
        coordinates[index][2]: weather
        for index, weather in enumerate(weather_frames)
    }
    first_year_profiles: dict[str, pd.Series] = {}
    for user_id, values in generators.items():
        location_name = location_italian_to_english(
            str(values["location"]),
            municipalities,
        )
        matching_coordinates = [
            coordinate
            for coordinate in coordinates
            if coordinate[2] == location_name
        ]
        module_output = simulate_module_productivity(
            matching_coordinates,
            [weather_by_location[location_name]],
            module,
            float(values["tilt_angle"]),
            float(values["azimuth"]),
            inverter,
        )
        per_kwp = simulate_1_kWp_productivity(module, module_output)[
            location_name
        ]
        first_year = _resample_pv_energy(per_kwp, interval, start_year)
        capacity = float(values["pv"])
        first_year_profiles[user_id] = first_year * capacity

    derated = simulate_gens_derated_productivity(
        annual_derating,
        first_year_profiles,
        start_date=settings["start_date"],
        project_lifetime_yrs=project_lifetime,
    )
    output = simulate_unstacked_productivity(
        derated,
        calendar_frame=calendar_frame,
        start_date=settings["start_date"],
        project_lifetime_yrs=project_lifetime,
    )
    output = output.loc[:, list(generators)]
    output = output.clip(lower=0)
    output.attrs["pv_simulation"] = {
        "weather_source": selected_options.weather_source,
        "coordinates": {
            name: {
                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude,
                "timezone": timezone,
            }
            for latitude, longitude, name, altitude, timezone in coordinates
        },
        "module": selected_options.module_name,
        "inverter": selected_options.inverter_name,
        "annual_derating_factor": annual_derating,
    }
    return output


def _pv_generators(
    user_types: Mapping[str, Mapping[str, Any]],
    plants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    generators: dict[str, Mapping[str, Any]] = {}
    for plant in plants.values():
        capacity = float(
            plant.get("installed_capacity", plant.get("pv", 0.0)) or 0.0
        )
        if capacity <= 0:
            continue
        user_type = str(
            plant.get("user_type")
            or plant.get("denomination")
            or ""
        )
        if user_type not in user_types:
            raise ValueError(
                f"PV plant references unknown user type {user_type!r}"
            )
        values = dict(user_types[user_type])
        values.update(
            {
                "pv": capacity,
                "tilt_angle": plant.get(
                    "tilt_angle",
                    values.get("tilt_angle"),
                ),
                "azimuth": plant.get("azimuth", values.get("azimuth")),
                "location": plant.get("location", values.get("location")),
            }
        )
        generators[user_type] = values
    return generators


def _coordinates_for_locations(
    location_names: Sequence[str],
    options: PVSimulationOptions,
) -> list[Coordinates]:
    if options.coordinates is not None:
        missing = [
            name for name in location_names if name not in options.coordinates
        ]
        if missing:
            raise ValueError(f"Missing PV coordinates for locations: {missing}")
        return [options.coordinates[name] for name in location_names]
    provider = options.coordinate_provider or create_coordinates_dataset
    return provider(location_names)


def _weather_for_coordinates(
    coordinates: list[Coordinates],
    start_year: int,
    options: PVSimulationOptions,
) -> list[pd.DataFrame]:
    if options.weather is not None:
        missing = [
            coordinate[2]
            for coordinate in coordinates
            if coordinate[2] not in options.weather
        ]
        if missing:
            raise ValueError(
                f"Missing PV weather for locations: {missing}"
            )
        frames = []
        for coordinate in coordinates:
            frame = options.weather[coordinate[2]].copy()
            frame.index = pd.to_datetime(frame.index, utc=True).tz_convert(
                "Europe/Rome"
            )
            frame.index.name = "datetime"
            frames.append(frame)
        return frames
    provider = options.weather_provider or _weather_data_for_year
    return provider(coordinates, start_year)


def validate_external_pv_profiles(
    profiles: pd.DataFrame,
    calendar_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Validate and normalize externally supplied PV profiles."""
    result = profiles.copy()
    if "datetime" in result:
        result = result.set_index("datetime")
    result.index = pd.to_datetime(result.index)
    expected = pd.DatetimeIndex(pd.to_datetime(calendar_frame["datetime"]))
    if not result.index.equals(expected):
        raise ValueError("External PV profile index must match the simulation calendar")
    if (result.select_dtypes(include=[np.number]) < 0).any().any():
        raise ValueError("PV generation profiles cannot contain negative values")
    result.index.name = "datetime"
    return result


def _weather_data_for_year(
    coordinates_dataset: list[tuple[Any, ...]],
    start_year: int,
) -> list[pd.DataFrame]:
    weather_frames = []
    for latitude, longitude, _name, _altitude, _timezone in coordinates_dataset:
        weather = pvlib.iotools.get_pvgis_tmy(
            latitude,
            longitude,
            map_variables=True,
        )[0]
        weather.index.name = "datetime"
        weather.index = weather.index.map(
            lambda timestamp: timestamp.replace(year=start_year)
        )
        weather = weather.shift(2)
        weather.iloc[:1] = 0
        weather.index = pd.to_datetime(weather.index, utc=True).tz_convert(
            "Europe/Rome"
        )
        weather_frames.append(weather)
    return weather_frames


def _resample_pv_energy(
    hourly: pd.Series,
    interval: str,
    start_year: int,
) -> pd.Series:
    series = hourly.copy()
    series.loc[series.index[-1] + pd.Timedelta(hours=1)] = series.iloc[-1]
    delta = pd.to_timedelta(interval)
    if delta >= pd.Timedelta(hours=1):
        result = series.resample(interval).sum()
    else:
        result = series.resample(interval).interpolate("linear")
        result = result * (delta.total_seconds() / 3600)
    result = result.iloc[:-1]
    if calendar.isleap(start_year):
        result = result[~((result.index.month == 2) & (result.index.day == 29))]
    return result
