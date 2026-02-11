import math
import numpy as np
from tqdm.auto import tqdm

def hp_energy_consumption(cacer_config, phi_hc_nd_ac, n_intervals, months, hours, t_ext, t_int, rh_ext, delta_t, monthly_range_heat = range(1, 13), monthly_range_cool = range(5, 10), scheduling = range(0, 24)):

    """
    This function calculates the energy consumption of the heat pump system

    Parameters
    ----------
    cacer_config : object
        Configuration of the heat pump system
    phi_hc_nd_ac : np.ndarray
        Thermal fluxes to Node I
    n_intervals : int
        Number of time intervals
    months : list
        Months of the year
    t_ext : np.ndarray
        Temperature of the exterior air
    t_int : np.ndarray
        Temperature of the interior air
    rh_ext : np.ndarray
        Relative humidity of the exterior air
    delta_t : str
        Time interval

    Returns
    -------
    hp_energy_consumption_array : np.ndarray
        Energy consumption of the heat pump system
    """

    #--------------------------------------- AUTONOMOUS HP SYSTEM ---------------------------------------

    if cacer_config.hvac_type == 'autonomous':
        
        hp_energy_consumption_array = np.zeros((n_intervals, cacer_config.user_numbers))
        
        for user in range(cacer_config.user_numbers):
            
            for n in tqdm(range(n_intervals), desc = f"  Iterations"):

                hp_energy_consumption_array[n, user] = hp_performances_autonomous(cacer_config.users[user], 
                                                                                  phi_hc_nd_ac[n, user], 
                                                                                  t_ext[n], 
                                                                                  t_int[n, user], 
                                                                                  rh_ext[n], 
                                                                                  months[n],
                                                                                  hours[n], 
                                                                                  cacer_config.hvac_type,
                                                                                  monthly_range_heat,
                                                                                  monthly_range_cool,
                                                                                  scheduling)

    #--------------------------------------- CENTRALIZED HP SYSTEM ---------------------------------------

    else:

        hp_energy_consumption_array = np.empty(n_intervals, cacer_config.user_numbers)

        # ????
        if delta_t == "1H":
            time_interval = 3600 # 1 hour
        else:
            time_interval = 900 # 15 minutes

        total_th_load = np.zeros(n_intervals)

        compressor_status = 0
        
        t_cut_in = cacer_config.users[0].hp_aux.t_cut_in # [C] Temperatura di cut-in del compressore
        t_cut_off = t_cut_in + cacer_config.users[0].hp_aux.t_dead_band # [C] Temperatura di cut-off del compressore
        t_water_tank = t_cut_off # [C] Temperatura iniziale dell'acqua nel serbatoio

        # Sum over all users of the thermal load
        for i in range(phi_hc_nd_ac.shape[1]):
            total_th_load = total_th_load + phi_hc_nd_ac[:, i]
        
        for n in tqdm(range(n_intervals), desc = "Simulate centralized heat pump system over each time interval"):
            
            hp_energy_consumption_array[n], t_water_tank, compressor_status = hp_performances_centralized(cacer_config.users[0], 
                                                                                                          t_ext[n], 
                                                                                                          t_water_tank, 
                                                                                                          rh_ext[n], 
                                                                                                          months[n], 
                                                                                                          cacer_config.hvac_type, 
                                                                                                          total_th_load[n], 
                                                                                                          t_cut_off, 
                                                                                                          t_cut_off, 
                                                                                                          t_cut_in, 
                                                                                                          time_interval, 
                                                                                                          compressor_status
                                                                                                          )

    print("")

    return hp_energy_consumption_array

##################################################################################################################################################################################################

def hp_performances_autonomous(hp_user, phi_hc_nd_ac, t_ext, t_int, rh_ext, month, hour, mode, monthly_range_heat = range(1, 13), monthly_range_cool = range(5, 10), scheduling = range(0, 24)):
    
    """
    This function calculates the energy consumption of the heat pump system
    for a given user, in autonomous mode.

    Parameters
    ----------
    hp_user : object
        Configuration of the user
    phi_hc_nd_ac : float
        Thermal power to Node I
    t_ext : float
        Temperature of the exterior air
    t_int : float
        Temperature of the interior air
    rh_ext : float
        Relative humidity of the exterior air
    month : int
        Month of the year
    mode : str
        HVAC mode ('heating' or 'cooling')

    Returns
    -------
    p_el : float
        Energy consumption of the heat pump system
    """

    #--------------------------------- Controlli iniziali ---------------------------------

    monthly_range_heat_eff  = [x for x in monthly_range_heat if x not in monthly_range_cool]

    if (phi_hc_nd_ac == 0 
        or (int(month) not in monthly_range_cool and phi_hc_nd_ac < 0)
        or (int(month) not in monthly_range_heat_eff and phi_hc_nd_ac > 0)
        or (int(hour) not in scheduling)
        ):
        
        return 0

    else:
        
        #--------------------------------- Temperatura esterna > -8 °C ---------------------------------
        
        if t_ext > -8: 

            eta = hp_efficiency(hp_user, t_ext, t_int, month, mode, phi_hc_nd_ac, monthly_range_cool) # [-] Efficienza PdC autonoma (COP = thermal load / electric load)
            
            q_max = hp_power_curve_max(hp_user, t_ext, t_int, month, phi_hc_nd_ac, monthly_range_cool) # [W] Potenza termica massima erogabile

            # si pongono in valore assoluto il carico termico dell'edificio e la potenza termica massima erogabile
            if phi_hc_nd_ac < 0 or q_max < 0:  
                phi_hc_nd_ac = - phi_hc_nd_ac
                q_max = - q_max

            #--------------------------------- External temperature in range (-8; 5] °C ---------------------------------

            if t_ext <= 5: 

                # Su Design Builder è attiva l'opzione timed-defrost sotto i 5 gradi
                pe_defrost, heat_cap_mult, input_pw_mult = defrost_op(t_ext, rh_ext)    # [W] Potenza elettrica aggiuntiva per defrost
                
                q_max = q_max * heat_cap_mult # [W] Potenza massima di pompa di calore corretta per defrost
                
                eta = eta / input_pw_mult # [-] Efficienza corretta per defrost (COP = thermal load / electric load)

            #--------------------------------- External temperature in range (5; : ) °C ---------------------------------
            
            else:
                
                pe_defrost = 0 # the defrost is not active
            
            #--------------------------------- Electric power consumption calculation ---------------------------------

            ##################################################################################
            # Annullare la potenza quando non è attivo il periodo di riscaldamento o di raffrescamento!!!
            # Questo lo si può fare anche esternamente annuallando phi_hc_nd_ac, attenzione però perchè rimane pe_defros e q_max!!!
            ##################################################################################

            # [W] Fabbisogno termico <= Potenza massima PdC
            if phi_hc_nd_ac <= q_max: 
                
                # eta = thermal power / thermal load [-]
                p_el = phi_hc_nd_ac / eta + pe_defrost # [W]
            
            # [W] Fabbisogno termico > Potenza massima PdC
            else:

                # q_max / eta = electri load at the maximum thermal load [W]
                # phi_hc_nd_ac - q_max = electrical load with auxiliary generator (eta = 1)
                # pe_defrost = electrical load due to defrost

                p_el = (q_max / eta + (phi_hc_nd_ac - q_max)) + pe_defrost # [W]
        
        #--------------------------------- Temperatura esterna <= -8 °C ---------------------------------

        else:
            
            q_max = hp_user.hp_aux.q_heater # [W] Potenza massima di pompa di calore
            
            eta = 1 # ????
            
            pe_defrost = 0 # the defrost is not active
            
            # in this case the p_el is equal to the thermal load ????
            
            ##################################################################################################
            # così però non si tiene conto della potenza massima erogabile dal sistema di pompa di calore...
            ##################################################################################################

            p_el = phi_hc_nd_ac / eta # [W]

    return p_el

##################################################################################################################################################################################################

def hp_performances_centralized(hp_user, t_ext, t_water_tank, rh_ext, month, mode, total_th_load, T_cut_off, T_cut_in, time_interval, compressor_status, monthly_range_heat = (1, 12), monthly_range_cool = (5, 9)):

    """
    Calcola le prestazioni del sistema di pompa di calore centralizzato.

    Parameters
    ----------
    hp_user : HpUserConfig
        Configurazione utente del sistema di pompa di calore
    t_ext : float
        Temperatura esterna dell'aria [C]
    t_water_tank : float
        Temperatura dell'acqua nel serbatoio [C]
    rh_ext : float
        Umidita relativa esterna dell'aria [%]
    month : int
        Mese dell'anno considerato
    mode : str
        Modalita' di funzionamento del sistema di pompa di calore
        'heating' o 'cooling'
    total_th_load : float
        Carico termico totale dell'edificio [W]
    T_cut_off : float
        Temperatura di cut-off del compressore [C]
    T_cut_in : float
        Temperatura di cut-in del compressore [C]
    time_interval : float
        Intervallo di tempo considerato per la simulazione [s]
    compressor_status : int
        Stato del compressore (0: spento, 1: acceso)

    Returns
    -------
    p_el : float
        Consumo elettrico del sistema di pompa di calore [W]
    t_water_tank : float
        Temperatura dell'acqua nel serbatoio [C]
    compressor_status : int
        Stato del compressore (0: spento, 1: acceso)
    """
    Pel_fans = hp_user.hp_aux.pel_fans # [W] Consumo elettrico ventilatori PdC centralizzata, da simulazione di Design Builder
    eta_fans = hp_user.hp_aux.eta_fans # [W/W] Efficienza ventilatori PdC centralizzata, da simulazione di Design Builder
    
    Pel_pumps = hp_user.hp_aux.pel_pumps # [W] Consumo elettrico pompe di calore, da simulazione di Design Builder
    eta_pumps = hp_user.hp_aux.eta_pumps # [W/W] Efficienza pompe del sistema, da simulazione di Design Builder
    
    cp_water = hp_user.hp_aux.cp_water # [J/(kg.K)]
    m_water_tank = hp_user.hp_aux.v_tank*hp_user.hp_aux.rho_water
    
    q_heater = hp_user.hp_aux.q_heater

    t_ext_wb = wet_bulb_temperature(t_ext, rh_ext) # [C] Temperatura bulbo umido esterno
    eta = hp_efficiency(hp_user, t_ext_wb, t_water_tank, month, mode) # [-] Efficienza PdC centralizzata
    Q_max = hp_power_curve_max(hp_user, t_ext, t_water_tank, month) # [W] Potenza massima di pompa di calore

    
    ##################################################################################
    # Attivare anche limitazione su phi_hc_nd_ac
    ##################################################################################

    # Calcolo consumo elettrico PdC centralizzata
    if int(month)>=monthly_range_cool[0] and int(month)<= monthly_range_cool[1]:
        
        # Modalità raffrescamento PdC centralizzata
        if total_th_load<0:
            total_th_load=-total_th_load
        p_el=(total_th_load)/eta+Pel_fans*eta_fans+Pel_pumps*eta_pumps
    
    else:
        # Modalità riscaldamento PdC centralizzata
        if hp_user.hp_aux.thermal_storage==True:
            
            # Gestione accumulo termico
            if total_th_load>Q_max and compressor_status==1:
                p_el=q_heater+Pel_fans*eta_fans+Pel_pumps*eta_pumps
                
                if t_water_tank>=T_cut_off:
                    compressor_status=0 # Spegnimento compressore
            
            elif total_th_load<=Q_max and compressor_status==1:
                p_el= Q_max/eta+Pel_fans*eta_fans+Pel_pumps*eta_pumps
                t_water_tank= t_water_tank+(Q_max-total_th_load)/(m_water_tank*cp_water/time_interval)
                
                if t_water_tank>=T_cut_off:
                    compressor_status=0 # Spegnimento compressore
            
            elif compressor_status==0:
                p_el=Pel_pumps*eta_pumps
                t_water_tank= t_water_tank-(total_th_load)/(m_water_tank*cp_water/time_interval)
                
                if t_water_tank<=T_cut_in:
                    compressor_status=1 # Accensione compressore
        else:
            p_el = (total_th_load)/eta+Pel_fans*eta_fans+Pel_pumps*eta_pumps

    return p_el, t_water_tank, compressor_status

##################################################################################################################################################################################################

def hp_efficiency(hp_user, t_ext, t_int, month, mode, phi_hc_nd_ac, monthly_range_cool = range(5, 10)):

    """
    Calcola l'efficienza del sistema di pompa di calore.
    
    Parameters
    ----------
    hp_user : HpUserConfig
        Configurazione utente del sistema di pompa di calore
    t_ext : float
        Temperatura esterna dell'aria [C]
    t_int : float
        Temperatura interna dell'edificio [C]
    month : int
        Mese dell'anno considerato
    mode : str
        Modalita' di funzionamento del sistema di pompa di calore
        'heating' o 'cooling'
    
    Returns
    -------
    eta : float
        Efficienza del sistema di pompa di calore
    """

    # active cooling
    if (int(month) in monthly_range_cool and phi_hc_nd_ac < 0):
        
        hp_params = hp_user.hp_cooling.hp_parameters # parameter of the heat pump in the cooling mode    
        f_seasonal_eta = hp_user.hp_cooling.f_seasonal_eta # seasonal efficiency
    
    # active heating
    else:
        
        hp_params = hp_user.hp_heating.hp_parameters # parameter of the heat pump in the heating mode
        f_seasonal_eta = hp_user.hp_heating.f_seasonal_eta # seasonal efficiency

    #########################################################################################################

    # we extract a curve for evaluating the efficiency of the heat pump
    
    x=t_ext # [°C]
    y=t_int # [°C]

    alpha = [hp_params[f'alpha{i}_eff'] for i in range(1, 10)]
    efficiency = hp_operating_curve(1, alpha, x, y, hp_params['q_eff'])

    ##################################################################################################
    # Perchè dovrebbe essere il contrario?
    ##################################################################################################

    if mode == 'centralized':
        eta = f_seasonal_eta * efficiency

    # Formula COP definita da Design builder per PdC aria-aria 
    # Inverso dell'EIR (Energy Input Ratio) = COP = thermal load / electricity load
    # EIR = 1 / COP = electricity load / thermal load
    else:     
        eta = f_seasonal_eta / efficiency     # Formula COP definita da Design builder per PdC aria-aria (Inverso dell'EIR (Energy Input Ratio))
    
    return eta

##################################################################################################################################################################################################

def hp_power_curve_max(hp_user, t_ext, t_int, month, phi_hc_nd_ac, monthly_range_cool = range(5, 10)):

    """
    Calcola la potenza massima erogabile dal sistema di pompa di calore
    in funzione delle temperature esterna e interna dell'edificio e del mese dell'anno.
    
    Parameters
    ----------
    hp_user : HpUserConfig
        Configurazione utente del sistema di pompa di calore
    t_ext : float
        Temperatura esterna dell'aria [C]
    t_int : float
        Temperatura interna dell'edificio [C]
    month : int
        Mese dell'anno considerato
    
    Returns
    -------
    Q_max : float
        Potenza massima erogabile dal sistema di pompa di calore [W]
    Q_min : float
        Potenza minima erogabile dal sistema di pompa di calore [W]
    """

    # active cooling
    if (int(month) in monthly_range_cool and phi_hc_nd_ac < 0):
        
        x = wet_bulb_temperature(t_int, rh=50) # [°C]
        y = t_ext # [°C]
        
        hp_params = hp_user.hp_cooling.hp_parameters # parameter of the heat pump in the cooling mode

    # active heating
    else:

        x = t_ext # [°C]
        y = t_int # [°C]
        
        hp_params = hp_user.hp_heating.hp_parameters # parameter of the heat pump in the heating mode

    alpha = [hp_params[f'alpha{i}_power'] for i in range(1, 10)]
    Q_max = hp_operating_curve(hp_params['p_th_nom'], alpha, x, y, q = hp_params['q_power'])
    
    return Q_max

##################################################################################################################################################################################################

def defrost_op(t_ext, rh_ext):

    """ Vedi EnergyPlus engineering reference per le formule sotto riportate """

    ah_ratio=ah_ratio_calculator(t_ext, rh_ext)     # Air-humidity Ratio
 
    # Vedi EnergyPlus engineering reference per le formule sotto riportate
    
    T_coil=0.82*(t_ext)-8.589       # [C] Temperatura coil esterno PdC aria-aria, da EnergyPlus
    ah_ratio_coil=ah_ratio_calculator(T_coil, 100)  # [-] Air-humidity Ratio coil esterno PdC aria-aria, da EnergyPlus
    delta=float(ah_ratio-ah_ratio_coil)
    delta_ah=max(10^-6, delta)     # [-] Differenza tra Air-humidity Ratio coil esterno PdC aria-aria e Air-humidity Ratio vapore acqueo a t_ext
    heat_cap_mult=0.909-107.33*delta_ah
    input_pw_mult=0.9-36.45*delta_ah
    
    #Q_defrost = 0.01*0.05833*(7.222-t_ext)*(5.9645/1.01667)*1000        # [W] Capacità termica aggiuntiva dovuta a Defrost
    Pe_defrost=(5.9645/1.01667)*0.05833*1000        # [W] Potenza elettrica aggiuntiva per defrost, da moltiplicare poi per l'RTF della PdC

    return Pe_defrost, heat_cap_mult, input_pw_mult

##################################################################################################################################################################################################

# Pressione di saturazione vapore acqueo a t_ext (Arden-Buck equation)

def ah_ratio_calculator(t_ext, rh_ext):

    P = 100094    # [Pa] Pressione atmosferica, da file climatico preso da Design Builder, valore costante

    P_sat = Psat_calculator(t_ext)      # [Pa] Pressione di saturazione vapore acqueo a t_ext (Arden-Buck equation)
    ah_ratio = 0.62198 * ((rh_ext / 100 * P_sat)) / ( P - (rh_ext / 100 * P_sat))     # Air-humidity Ratio

    return ah_ratio

##################################################################################################################################################################################################

def Psat_calculator(t_ext):

    P_sat = 611.21 * math.exp((18.678 - t_ext / 234.5) * (t_ext / (t_ext + 257.14)))      # [Pa] Pressione di saturazione vapore acqueo a t_ext (Arden-Buck equation)

    return P_sat

##################################################################################################################################################################################################

def wet_bulb_temperature(T_db, rh):

        T_wb = (T_db * math.atan(0.151977 * (rh + 8.313659) ** 0.5) +
        math.atan(T_db + rh) -
        math.atan(rh - 1.676331) +
        0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh) -
        4.686035)

        return T_wb

##################################################################################################################################################################################################

def hp_operating_curve(nominal_value, alpha, x, y, q):

    operating_value = nominal_value*(
        alpha[0] * x +
        alpha[1] * x**2 +
        alpha[2] * x**3 +
        alpha[3] * y +
        alpha[4] * y**2 +
        alpha[5] * y**3 +
        alpha[6] * y*x +
        alpha[7] * y*x**2 +
        alpha[8] * x*y**2 +
        q)
    
    return operating_value

                