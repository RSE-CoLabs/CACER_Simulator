import pandas as pd
import numpy as np

from pvlib import location
from pvlib import irradiance

def solar_thermal_contribution(solar_data, coordinates):

    site = location.Location(coordinates[0][0], coordinates[0][1], 
                                tz=coordinates[0][4], 
                                altitude=coordinates[0][3], 
                                name=coordinates[0][2])
        
    orientations = ['N','NE','E','SE','S','SW','W','NW']
    surface_orientations = np.arange(0,360,45)     #np.arange(start, stop, step)

    # Initialise dataframes
    surface_irradiance = pd.DataFrame()  
    surface_irradiance_roof = pd.DataFrame()
    
    solar_data['datetime'] = pd.to_datetime(solar_data['datetime'])
    solar_data['datetime'] = solar_data['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S.%f')
    times=solar_data['datetime']
        
    # Get irradiance data for all wall orientations

    for so in surface_orientations:
        si = get_irradiance(site, times, 90, so, solar_data)       #epw (energy plus weather file?) 
        si_roof = get_irradiance(site, times, 30, so, solar_data)   # tilt=30°, south-facing roof
        surface_irradiance = pd.concat([surface_irradiance, si.POA], axis=1)     # POA = Plane of Array (piano focale)
        surface_irradiance_roof = pd.concat([surface_irradiance_roof, si_roof.POA], axis=1) # POA = Plane of Array (piano focale)

    surface_irradiance.columns = orientations 
    surface_irradiance_roof.columns = orientations
    
    return surface_irradiance, surface_irradiance_roof

###############################################################################################################################

def get_irradiance(site_location, times, tilt, surface_azimuth, solar_data):
    
        # Generate clearsky data using the Ineichen model, which is the default
        # The get_clearsky method returns a dataframe with values for GHI, DNI,
        # and DHI
        #clearsky = site_location.get_clearsky(times)

        # Get solar azimuth and zenith to pass to the transposition function
        solar_position = site_location.get_solarposition(times=times)

        # Use the get_total_irradiance function to transpose the GHI to POA
        POA_irradiance = irradiance.get_total_irradiance(surface_tilt=tilt,
                                                         surface_azimuth=surface_azimuth,
                                                         ghi=solar_data['ghi'].values,
                                                         # dhi=irrad_epw['dhi'],
                                                         dhi=solar_data['dhi'].values,
                                                         # dni=irrad_epw['dni'],
                                                         dni=solar_data['dni'].values,
                                                         solar_zenith=solar_position['apparent_zenith'],
                                                         solar_azimuth=solar_position['azimuth'],
                                                         model='isotropic',
                                                         airmass=site_location.get_airmass(solar_position=solar_position))
        
        AOI = irradiance.aoi(surface_tilt=tilt,
                             surface_azimuth=surface_azimuth,
                             solar_zenith=solar_position['apparent_zenith'],
                             solar_azimuth=solar_position['azimuth'])
        
        # cleaning AOI vector
        for i in range(len(AOI)): 
            if AOI.iloc[i] > 90 or solar_position['apparent_zenith'].iloc[i] > 90:
                AOI.iloc[i] = 90
        
        # Return DataFrame with only GHI and POA
        return pd.DataFrame({'GHI': solar_data['ghi'].values,
                             'POA': POA_irradiance['poa_global'],
                             'AOI': AOI})