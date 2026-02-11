import numpy as np
from tqdm.auto import tqdm
from HVAC_simulator.functions.solar_irradiance import solar_thermal_contribution

def thermal_load_calculator(cacer_config, df_climate_data, n_intervals, months, hours, location, t_ext, monthly_range_heat = range(1, 13), monthly_range_cool = range(5, 10), scheduling_heating = range(0, 24), scheduling_cooling = range(0, 24)):

    """
    Calcola la potenza termica scambiata dalla PdC e le temperature interne per ciascun utente.
    
    Parameters
    ----------
    cacer_config : CacerConfig
        Configurazione dell'impianto di riscaldamento del calore
    df_climate_data : pandas.DataFrame
        Dati climatici per ciascun giorno dell'anno
    n_intervals : int
        Numero di intervalli temporali considerati
    months : list
        Mesi dell'anno considerati
    location : str
        Località dell'edificio
    t_ext : list
        Temperature del fluido di riscaldamento esterno per ciascun giorno dell'anno
    t_int_max : float
        Temperatura massima internamente tollerable
    t_int_min : float
        Temperatura minima internamente tollerable
    
    Returns
    -------
    phi_hc_nd_ac : numpy.ndarray
        Potenza fabbisogno termico edificio  [W]
    t_int : numpy.ndarray
        Temperaturee interne per ciascun utente [C]
    """

    monthly_range_heat_eff = [x for x in monthly_range_heat if x not in monthly_range_cool]

    t_int_min = cacer_config.th_comfort_heating # La temperatura minima internamente tollerata
    t_int_max = cacer_config.th_comfort_cooling # La temperatura massima internamente tollerata
    t_start = [cacer_config.th_comfort_heating for _ in range(3)]  # Initial indoor temperature for each user
    t_int_0, omega_s_ac_0, omega_m_ac_0 = t_start[:] # Initial indoor temperature

    # Temperature interne (aria, superficie interna ed involucro edilizione), array numero di intervalli x numero di utenti
    t_int = np.zeros((n_intervals+1, cacer_config.user_numbers))
    omega_s_ac = np.zeros((n_intervals+1, cacer_config.user_numbers))
    omega_m_ac = np.zeros((n_intervals+1, cacer_config.user_numbers)) 

    phi_hc_nd_ac = np.zeros((n_intervals, cacer_config.user_numbers)) # Potenza termica scambiata dalla PdC [W], array numero di intervalli x numero di utenti

    for user in range(cacer_config.user_numbers):

        t_int[0, user], omega_s_ac[0, user], omega_m_ac[0, user] = t_start[:]

        phi_ia, phi_st, phi_m = th_fluxes_generator(cacer_config, df_climate_data, location)

        #--------------------------------- Simulazione ---------------------------------

        for n in tqdm(range(1, n_intervals + 1), desc = f"  Iterations"):

            # Si assume che la temperatura media del terreno in profondità sia di circa 13 gradi tutto l'anno
            
            ########################################################################
            # forse si potrebbe usare l'approssimazione t_ground = T_ext !!!
            ########################################################################

            #------------------------------------------------------- Calcolo temperatura interna teorica -------------------------------------------------------

            t_int_theoretica = (cacer_config.users[user].building.A[0][0] * t_int_0 + 
                                cacer_config.users[user].building.A[0][1] * omega_s_ac_0 + 
                                cacer_config.users[user].building.A[0][2] * omega_m_ac_0 + 

                                (- cacer_config.users[user].building.H_ve * t_ext[n-1] - phi_ia[n-1, user]) * (cacer_config.users[user].building.B[0][0]) + 
                                (- phi_st[n-1, user] - cacer_config.users[user].building.H_tr_w * t_ext[n-1]) * (cacer_config.users[user].building.B[0][1]) + 
                                (- cacer_config.users[user].building.H_tr_em * t_ext[n-1] - (phi_m[n-1][user] + cacer_config.users[user].building.U_ground * cacer_config.users[user].building.A_floor * (15 - omega_m_ac_0))) * cacer_config.users[user].building.B[0][2]
                                )

            #------------------------------------------------------- Calcolo fabbisogno termico  -------------------------------------------------------

            # if the indoor temperature is outside the comfort range, the heat pump will operate to maintain the indoor temperature within the comfort range

            # in particular, if the theoretical indoor temperature is higher than the maximum comfort temperature, the heat pump will operate in cooling mode to maintain the indoor temperature at the maximum comfort temperature; 
            # if the theoretical indoor temperature is lower than the minimum comfort temperature, the heat pump will operate in heating mode to maintain the indoor temperature at the minimum comfort temperature; 
            # if the theoretical indoor temperature is within the comfort range, the heat pump will not operate and the indoor temperature will be equal to the theoretical indoor temperature

            #------------------------------------------------------- Modalità raffrescamento PdC -------------------------------------------------------

            if (t_int_theoretica > t_int_max and int(months[n-1]) in monthly_range_cool and int(hours[n-1]) in scheduling_cooling):
                    
                t_int[n, user] = t_int_max
                
                phi_hc_nd_ac[n-1, user] = (
                                            -t_int[n, user] + 
                                           cacer_config.users[user].building.A[0][0] * t_int_0 + 
                                           cacer_config.users[user].building.A[0][1] * omega_s_ac_0 + 
                                           cacer_config.users[user].building.A[0][2]* omega_m_ac_0 + 

                                           (-phi_st[n-1, user] - cacer_config.users[user].building.H_tr_w * t_ext[n-1]) * (cacer_config.users[user].building.B[0][1]) + 
                                           (-cacer_config.users[user].building.H_tr_em * t_ext[n-1] - (phi_m[n-1][user] + cacer_config.users[user].building.U_ground * cacer_config.users[user].building.A_floor * (15 - omega_m_ac_0))) * cacer_config.users[user].building.B[0][2]
                                            ) / (cacer_config.users[user].building.B[0][0]) + (-cacer_config.users[user].building.H_ve * t_ext[n-1] - phi_ia[n-1, user])
        

            #------------------------------------------------------- Modalità riscaldamento PdC -------------------------------------------------------

            elif (t_int_theoretica < t_int_min and int(months[n-1]) in monthly_range_heat_eff and int(hours[n-1]) in scheduling_heating):
                
                t_int[n, user] = t_int_min        
                
                phi_hc_nd_ac[n-1, user] = (
                                            -t_int[n, user] + 
                                           cacer_config.users[user].building.A[0][0] * t_int_0 + 
                                           cacer_config.users[user].building.A[0][1] * omega_s_ac_0 + 
                                           cacer_config.users[user].building.A[0][2]* omega_m_ac_0 + 

                                           (-phi_st[n-1, user] - cacer_config.users[user].building.H_tr_w * t_ext[n-1]) * (cacer_config.users[user].building.B[0][1]) + 
                                           (-cacer_config.users[user].building.H_tr_em * t_ext[n-1] - (phi_m[n-1][user] + cacer_config.users[user].building.U_ground * cacer_config.users[user].building.A_floor * (15 - omega_m_ac_0))) * cacer_config.users[user].building.B[0][2]
                                            ) / (cacer_config.users[user].building.B[0][0]) + (-cacer_config.users[user].building.H_ve * t_ext[n-1] - phi_ia[n-1, user])

            #------------------------------------------------------- Modalità PdC spenta -------------------------------------------------------

            else: 
                
                t_int[n,user] = t_int_theoretica
                phi_hc_nd_ac[n-1, user] = 0
                
            #------------------------------------------------------- Si riaggiornanno le variabili -------------------------------------------------------

            omega_s_ac[n, user] = (cacer_config.users[user].building.A[1][0] * t_int_0 + 
                                  cacer_config.users[user].building.A[1][1] * omega_s_ac_0 + 
                                  cacer_config.users[user].building.A[1][2] * omega_m_ac_0 + 

                                  (-cacer_config.users[user].building.H_ve * t_ext[n-1] - phi_ia[n-1,user] - phi_hc_nd_ac[n-1,user]) * (cacer_config.users[user].building.B[1][0]) + 
                                  (-phi_st[n-1,user] - cacer_config.users[user].building.H_tr_w * t_ext[n-1]) * (cacer_config.users[user].building.B[1][1]) + 
                                  (-cacer_config.users[user].building.H_tr_em * t_ext[n-1] - (phi_m[n-1][user] + cacer_config.users[user].building.U_ground * cacer_config.users[user].building.A_floor * (15 - omega_m_ac_0))) * cacer_config.users[user].building.B[1][2]
                                  )
            
            omega_m_ac[n, user] = (cacer_config.users[user].building.A[2][0] * t_int_0 + 
                                  cacer_config.users[user].building.A[2][1] * omega_s_ac_0 + 
                                  cacer_config.users[user].building.A[2][2] * omega_m_ac_0 + 

                                  (-cacer_config.users[user].building.H_ve * t_ext[n-1] - phi_ia[n-1,user] - phi_hc_nd_ac[n-1,user]) * (cacer_config.users[user].building.B[2][0]) + 
                                  (-phi_st[n-1,user]-cacer_config.users[user].building.H_tr_w * t_ext[n-1]) * (cacer_config.users[user].building.B[2][1]) + 
                                  (-cacer_config.users[user].building.H_tr_em * t_ext[n-1] - (phi_m[n-1][user] + cacer_config.users[user].building.U_ground * cacer_config.users[user].building.A_floor * (15 - omega_m_ac_0))) * cacer_config.users[user].building.B[2][2]
                                  )
            
            omega_s_ac_0, omega_m_ac_0 = map(float, (omega_s_ac[n, user], omega_m_ac[n, user]))

            t_int_0 = t_int[n, user] # temperatura interna di partenza per il prossimo intervallo
    
    print("")

    return phi_hc_nd_ac, t_int

#######################################################################################################################################################

def th_fluxes_generator(cacer_config_users, df_climate_data, location):

    """
    This function generates the thermal fluxes for each user in the building

    Parameters
    ----------
    cacer_config_users : object
        Configuration of the users
    df_climate_data : DataFrame
        Climate data
    location : list of float
        Location of the building

    Returns
    -------
    phi_ia : np.ndarray
        Thermal fluxes due to internal gains
    phi_st : np.ndarray
        Thermal fluxes due to solar irradiance
    phi_m : np.ndarray
        Thermal fluxes due to mechanical heating/cooling system
    """
    Irradiance, Irradiance_roof = solar_thermal_contribution(df_climate_data, location)

    n_intervals = df_climate_data.shape[0] # number of time intervals
    n_users = len(cacer_config_users.users) # number of users

    th_fluxes_data_matrix = [np.zeros((n_intervals, n_users)) for _ in range(3)]

    # Thermal fluxes for each user
    for user in range(n_users):

        phi_ia, phi_st, phi_m = model_th_fluxes(cacer_config_users.users[user], n_intervals, Irradiance, Irradiance_roof)

        th_fluxes_data_matrix[0][:, user] = phi_ia
        th_fluxes_data_matrix[1][:, user] = phi_st
        th_fluxes_data_matrix[2][:, user] = phi_m
        
    return th_fluxes_data_matrix[0], th_fluxes_data_matrix[1], th_fluxes_data_matrix[2] 

#######################################################################################################################################################

def model_th_fluxes(user, n_intervals, Irradiance, Irradiance_roof):

    """
    This function models the thermal fluxes for a given user

    Parameters
    ----------
    user : object
        Configuration of the user
    n_intervals : int
        Number of time intervals
    Irradiance : np.ndarray
        Solar irradiance on the exterior surfaces of the building
    Irradiance_roof : np.ndarray
        Solar irradiance on the roof of the building

    Returns
    -------
    phi_ia : np.ndarray
        Thermal fluxes to Node I
    phi_st : np.ndarray
        Thermal fluxes to Node S
    phi_m : np.ndarray
        Thermal fluxes to Node M
    """
    phi_0=np.ones(n_intervals)*200      # Da modificare, i carichi interni andrebbero associati all'archetipo di edificio

    # Thermal fluxes
    phi_sol_gla = user.building.ks_gla * (np.sum(np.multiply(Irradiance, user.building.glazed_area), axis=1).values)
    phi_sol_opa = user.building.ks_opa * (np.sum(np.multiply(Irradiance, user.building.opaque_area), axis=1).values) + user.building.ks_opa * (np.sum(np.multiply(Irradiance_roof, user.building.opaque_area_roof), axis=1).values)
    phi_sol_infrared = np.sum(user.building.ks_infra * (user.building.opaque_area))
    
    phi_sol_tot = phi_sol_gla + phi_sol_opa - phi_sol_infrared

    phi_ia = 0.5 * phi_0
    phi_m = user.building.k_a * (0.5 * phi_0 + 0.5 * phi_sol_tot)       
    phi_st  = (1 - user.building.k_a - user.building.k_s) * (0.5 * phi_0 + 0.5 * phi_sol_tot) 

    return phi_ia, phi_st, phi_m