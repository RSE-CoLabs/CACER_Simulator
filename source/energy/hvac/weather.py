import datetime as dt
import pvlib
from geopy.geocoders import Nominatim
import pandas as pd

def weather_data_generator(
    latitude: float,
    longitude: float,
    first_year: int,
    simulation_interval: str,
):

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

    climate_data_file = pvlib.iotools.get_pvgis_tmy(latitude, longitude, 
                                                    # startyear = start_year, 
                                                    # endyear = end_year, 
                                                    map_variables=True, 
                                                    outputformat="csv")[0] # Get TMY data from PVGIS

    climate_data_file.index.name = "datetime"

    climate_data_file.index = climate_data_file.index.tz_convert(None)

    climate_data_file.index = climate_data_file.index.map(lambda t: t.replace(year=int(first_year))) # Set index year to start_year

    climate_data_file = climate_data_file.sort_index()

    if simulation_interval == "15Min":

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

    geolocator = Nominatim(user_agent="cacer-simulator")
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

        try:
            location, altitude_location = get_coordinates(name_location)
            data_location = (location.latitude, location.longitude, name_location, altitude_location, 'Etc/GMT+2')

        except Exception as e:
            print(f"Error getting coordinates for {name_location}: {e}")
            data_location = (45.4685, 9.1824, name_location, 0, 'Etc/GMT+2')
        
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

def generate_future_temperature_data(
    weather_data: pd.DataFrame,
    delta_T_future=1,
    T_mean_2020=15.8,
):
    df_weather_data_tmy = weather_data.copy()

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

def future_weather_data_generator(
    weather_data: pd.DataFrame,
    delta_T_future=1,
    T_mean_2020=15.8,
):
    df_weather_data_tmy = weather_data.copy()

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

    df_T_future = generate_future_temperature_data(
        weather_data,
        delta_T_future,
        T_mean_2020,
    )

    df_future['temp_air'] = df_T_future['temp_air_scaled']

    #--------------------------------------------------------------------------------------------------------------------

    return df_future

#####################################################################################################################################################################

def select_years_future_weather_data(
    future_weather: pd.DataFrame,
    start_year: int,
    n_years: int,
):
    df = future_weather.copy()
    df.index = pd.to_datetime(df.index)
    end_year = start_year + n_years -1 

    df_filtered = df[(df.index.year >= start_year) & (df.index.year <= end_year)]
    return df_filtered





















