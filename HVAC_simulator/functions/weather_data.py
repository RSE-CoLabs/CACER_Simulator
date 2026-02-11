import datetime as dt
import pvlib
from geopy.geocoders import Nominatim
import yaml
import pandas as pd
from simple_colors import blue

from src.Functions_General import clear_folder_content
from src.Functions_Energy_Model import suppress_printing

def weather_data_generator():

    """
    Function to generate weather data based on project configuration

    Parameters
    ----------
    config_file : dict
        project configuration file
    coordinates : list
        list containing the geographical coordinates of the locations under exam
    wheater_data_directory : str
        directory where the weather data will be saved
    wheather_data_name : str
        name of the csv file where the weather data will be saved

    Returns
    -------
    climate_data_file : pandas.DataFrame
        dataframe containing the weather data of the locations under exam
    """

    print(blue("Generating weather data for a typical meteorological year (TMY):", ['bold', 'underlined']))

    config = yaml.safe_load(open("config.yml", 'r'))

    suppress_printing(clear_folder_content, config['folder_weather_data']) # clearing the weather data directory

    location = config['provincia_it'] # getting the location from the configuration file
    coordinates = suppress_printing(create_coordinates_dataset, [location])

    date_string = str(config['start_date']) # project start date
    data = dt.datetime.strptime(date_string, "%Y-%m-%d") # converting to correct format

    # start_year = int(data.strftime("%Y")) # start year
    # duration = int(config['project_lifetime_yrs'])
    # end_year = start_year + duration

    start_year = 2005
    end_year = 2023

    latitude, longitude, name, altitude, timezone = coordinates[0]

    climate_data_file = pvlib.iotools.get_pvgis_tmy(latitude, longitude, 
                                                    # startyear = start_year, 
                                                    # endyear = end_year, 
                                                    map_variables=True, 
                                                    outputformat="csv")[0] # Get TMY data from PVGIS

    climate_data_file.index.name = "datetime"

    climate_data_file.index = climate_data_file.index.tz_convert(None)

    first_year = config['start_date'].year
    climate_data_file.index = climate_data_file.index.map(lambda t: t.replace(year=int(first_year))) # Set index year to start_year

    climate_data_file = climate_data_file.sort_index()

    delta_t = config['delta_t'] # time step in minutes

    if delta_t == "15Min":

        climate_data_file = climate_data_file.resample('15min').mean()
        climate_data_file = climate_data_file.interpolate(
            method='time',     # uses datetime spacing
            limit_direction='both'
        )

        # extend index by 45 minutes
        full_index = pd.date_range(
            start=climate_data_file.index.min(),
            end=climate_data_file.index.max() + pd.Timedelta(minutes=45),
            freq='15min'
        )

        climate_data_file = climate_data_file.reindex(full_index)
        climate_data_file.loc[pd.Timestamp(str(first_year+1)+'-01-01 00:00')] = climate_data_file.loc[pd.Timestamp(str(first_year)+'-01-01 00:00')]
        climate_data_file = climate_data_file.sort_index()
        climate_data_file.interpolate(method='time', inplace=True)
        climate_data_file = climate_data_file.iloc[:-1]
        climate_data_file.index.name = 'datetime'
        
    weather_data_filename = config['filename_weather_data']
    climate_data_file.to_csv(weather_data_filename)

    print(f"**** TMY data extracted and saved! ****\n")

    return climate_data_file

#######################################################################################################################################################################

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
    altitude_location = pvlib.location.lookup_altitude(location.latitude, location.longitude)

    return location, altitude_location

#######################################################################################################################################################################

def create_coordinates_dataset(locations_input):

    """we create a dataset in which we save for each location under exam the values of latitude, longitude, name, altitude and time zone
    Inputs:
        locations_input        list with the name of the locations under exam [list]
    Outputs:
        coordinates_dataset    list of the parameters for each location under exam [list]
    """

    coordinates_dataset = [] # initialization

    for name_location in locations_input:

        location, altitude_location = get_coordinates(name_location)

        data_location = (location.latitude, location.longitude, name_location, altitude_location, 'Etc/GMT+2')

        coordinates_dataset.append(data_location)

    return coordinates_dataset

#######################################################################################################################################################################

def build_year_profile(year, df_noleap, feb28):
    base = df_noleap.copy()
    base.index = base.index.map(lambda t: t.replace(year=year))

    if pd.Timestamp(year=year, month=1, day=1).is_leap_year:
        feb29_copy = feb28.copy()
        feb29_copy.index = feb29_copy.index.map(
            lambda t: t.replace(year=year, month=2, day=29)
        )
        base = pd.concat([base, feb29_copy]).sort_index()

    return base

#######################################################################################################################################################################

def generate_future_temperature_data(delta_T_future = 1, T_mean_2020 = 15.8):

    config = yaml.safe_load(open("config.yml", 'r'))
    df_weather_data_tmy = pd.read_csv(config['filename_weather_data'], index_col=0, parse_dates=True) # Load TMY weather data from file

    #--------------------------------------------------------------------------------------------------------------------

    # delta_T_future = 1 # °C, a simple assumption for the future temperature increase 
    # T_mean_2020 = 15.8 # °C, mean temperature in the base year (2020)

    #--------------------------------------------------------------------------------------------------------------------

    df = df_weather_data_tmy[['temp_air']]

    #--------------------------------------------------------------------------------------------------------------------

    df.index = df.index.map(lambda t: t.replace(year=2020)) # Set index year to start_year

    # extract Feb 28 and Feb 29
    feb28 = df[(df.index.month == 2) & (df.index.day == 28)]

    feb29 = feb28.copy()
    feb29.index = feb29.index.map(
        lambda t: t.replace(day=29)
    )

    df_2020_leap = pd.concat([df, feb29]).sort_index()

    # build a non-leap-year profile (drop Feb 29)
    df_noleap = df_2020_leap[~((df_2020_leap.index.month == 2) & (df_2020_leap.index.day == 29))]

    #--------------------------------------------------------------------------------------------------------------------

    df_future = pd.concat(
        [build_year_profile(y, df_noleap, feb28) for y in range(2020, 2061)]
    )

    #--------------------------------------------------------------------------------------------------------------------

    anno_base = 2020
    anno_target = 2040

    trend_annuo_breve_termine = delta_T_future / (anno_target - anno_base) # °C/anno

    df_future = df_future.reset_index()

    df_future.rename(columns={"index": "datetime"}, inplace=True)
    df_future["year"] = df_future["datetime"].dt.year

    df_future.set_index('datetime', inplace=True)

    df_future["delta_T"] = (df_future["year"] - anno_base) * trend_annuo_breve_termine + (max(T_mean_2020 - df_future['temp_air'].mean(), 0))
    df_future["temp_air_scaled"] = df_future["temp_air"] + df_future["delta_T"]

    #--------------------------------------------------------------------------------------------------------------------

    df_future.drop(columns=["year", "delta_T", "temp_air"], inplace=True)

    return df_future

#######################################################################################################################################################################

def future_weather_data_generator():
    
    print(blue("Generating future weather data (2020-2060):", ['bold', 'underlined']))

    config = yaml.safe_load(open("config.yml", 'r'))
    df_weather_data_tmy = pd.read_csv(config['filename_weather_data'], index_col=0, parse_dates=True) # Load TMY weather data from file

    #--------------------------------------------------------------------------------------------------------------------

    df = df_weather_data_tmy

    #--------------------------------------------------------------------------------------------------------------------

    df.index = df.index.map(lambda t: t.replace(year=2020)) # Set index year to start_year

    # extract Feb 28 and Feb 29
    feb28 = df[(df.index.month == 2) & (df.index.day == 28)]

    feb29 = feb28.copy()
    feb29.index = feb29.index.map(
        lambda t: t.replace(day=29)
    )

    df_2020_leap = pd.concat([df, feb29]).sort_index()

    # build a non-leap-year profile (drop Feb 29)
    df_noleap = df_2020_leap[~((df_2020_leap.index.month == 2) & (df_2020_leap.index.day == 29))]

    #--------------------------------------------------------------------------------------------------------------------

    df_future = pd.concat(
        [build_year_profile(y, df_noleap, feb28) for y in range(2020, 2061)]
    )

    #--------------------------------------------------------------------------------------------------------------------

    print("- Generating future temperature data (2020-2060)...")

    df_T_future = generate_future_temperature_data()

    df_future['temp_air'] = df_T_future['temp_air_scaled']

    #--------------------------------------------------------------------------------------------------------------------

    df_future.to_csv(config['folder_weather_data'] + 'weather_data_future_2020_2060.csv')

    print(f"**** Future weather data (2020-2060) extracted and saved! ****\n")

#####################################################################################################################################################################

def select_years_future_weather_data():

    print(blue("Selecting years from future weather data:", ['bold', 'underlined']))

    config = yaml.safe_load(open('config.yml'))
    df = pd.read_csv(config['filename_future_weather_data'], index_col=0)

    df.index = pd.to_datetime(df.index)

    start_year = int(config['start_date'].year)
    n_years = config['project_lifetime_yrs']
    end_year = start_year + n_years -1 

    print(f"- starting year: {start_year}")
    print(f"- ending year: {end_year}")

    # filtro le righe del DataFrame
    df_filtered = df[(df.index.year >= start_year) & (df.index.year <= end_year)]

    df_filtered.to_csv(config['folder_weather_data'] + 'weather_data_selected_years.csv')

    print("**** Done! ****")






















