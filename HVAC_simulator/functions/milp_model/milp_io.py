import numpy as np
import pulp as plp

from HVAC_simulator.functions.hp_energy_consumption import hp_efficiency, hp_power_curve_max, defrost_op

###############################################################################################################################

def milp_intervals(n_prosumers, n_consumers, n_intervals):

    set_P= range(n_prosumers)
    set_HVAC= range(n_consumers)
    set_N   = range(1, n_intervals+1)   
    set_T   = range(2, n_intervals+2)
    set_Temp= range(1, n_intervals+2)

    # MILP model parameters
    return set_P, set_HVAC, set_N, set_T, set_Temp

###############################################################################################################################

def milp_hp_autonomous_constants(n_intervals, n_consumers, hp_users_list, hp_hvac_users_list, t_media, t_ext, rh_ext, months):

    eta=np.zeros((n_intervals, n_consumers))
    q_max=np.zeros((n_intervals, n_consumers))
    q_min=np.zeros((n_intervals, n_consumers))
    pe_defrost=np.zeros((n_intervals, n_consumers))
    q_crankcase_activation=np.zeros((n_intervals, n_consumers))

    for consumer in range(n_consumers):
        mode=hp_hvac_users_list[consumer]

        for i in range(n_intervals):
            if t_ext[i]>-8:
                
                eta[i, consumer]=hp_efficiency(hp_users_list[consumer], t_ext[i], t_media, months[i], mode)
                q_max[i, consumer]=hp_power_curve_max(hp_users_list[consumer], t_ext[i], t_media, months[i])
                
                if t_ext[i]<=5:
                    
                    pe_defrost[i, consumer], heat_cap_mult, input_pw_mult = defrost_op(t_ext[i], rh_ext[i])
                    q_max[i, consumer]=q_max[i, consumer]*heat_cap_mult
                    eta[i, consumer]=eta[i, consumer]/input_pw_mult
                else:
                    pe_defrost[i, consumer]=0

            else:
                eta[i, consumer]=1
                q_max[i, consumer]=0
                pe_defrost[i, consumer]=0
                q_crankcase_activation[i, consumer]=1

    return eta, q_max, q_min, pe_defrost, q_crankcase_activation

###############################################################################################################################

def milp_hp_centralized_constants(n_intervals, hp_users_list, hp_hvac_users_list, t_mandata, t_ext, months):

    eta=np.zeros(n_intervals)
    q_max=np.zeros(n_intervals)
    q_min=np.zeros(n_intervals)
    mode=hp_hvac_users_list[0]

    for i in range(n_intervals):
                 
        eta[i]=hp_efficiency(hp_users_list[0], t_ext[i], t_mandata, months[i], mode)
        q_max[i]=hp_power_curve_max(hp_users_list[0], t_ext[i], t_mandata, months[i])

    return eta, q_max, q_min

###############################################################################################################################

def milp_hp_centralized_storage_constants(hp_aux, t_water_tank_0):
    v_tank=hp_aux.v_tank
    rho_water=hp_aux.rho_water
    cp_water=hp_aux.cp_water

    m_water_tank=v_tank*rho_water
    h_water_tank=cp_water*m_water_tank*t_water_tank_0
        
    return m_water_tank, h_water_tank

###############################################################################################################################

def milp_energy_variables(set_P, set_N):

    e_in_vars	= {(p,n):
        plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0,
                    name="Ein_{0}_{1}".format(p,n)) for p in set_P for n in set_N } 

        # Energia immessa al quarto d'ora  
        # l'energia immessa è quella da fotovoltaico, l'utente non immette nulla in rete autonomamente ---> vincolo su energia immessa da implementare
    e_out_vars	= {(p,n):
        plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0,
                    name="Eout_{0}_{1}".format(p,n)) for p in set_P for n in set_N } 

    #----------------------------------------
        # Stato prelievo in rete 
    k_vars = {(p,n):
        plp.LpVariable(cat=plp.LpBinary,
                    name="k_{0}_{1}".format(p,n)) for p in set_P for n in set_N}

        # Stato immissione in rete 
    l_vars = {(p,n):
        plp.LpVariable(cat=plp.LpBinary,
                    name="l_{0}_{1}".format(p,n)) for p in set_P for n in set_N}

    
        # Per il calolo dell'Energia Condivisa inserisco queste nuove variabili:
        # Energia virtualmente prelevata da fotovoltaico tolte le utenze domestiche:
    e_in_virtual_vars	= {n:
        plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0,
                    name="E_in_virtual_{0}".format(n)) for n in set_N }
        
        # Energia virtualmente immessa da rete dalle utenze domestiche tolta la compenente di fotovoltaico immesso:
    e_out_virtual_vars	= {n:
        plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0,
                    name="E_out_virtual_{0}".format(n)) for n in set_N }
        
        # Stato prelievo virtuale in rete:
    a_vars = {n:
        plp.LpVariable(cat=plp.LpBinary,
                    name="a_{0}".format(n))  for n in set_N}
        
        # Stato immissione virtuale da rete:
    b_vars = {n:
        plp.LpVariable(cat=plp.LpBinary,
                    name="b_{0}".format(n))  for n in set_N}

    return e_in_vars, e_out_vars, k_vars, l_vars, e_in_virtual_vars, e_out_virtual_vars, a_vars, b_vars

###############################################################################################################################

def milp_thermal_variables(set_Temp, set_HVAC, set_N):

    phi_hc_nd_ac = {
        (n, u): plp.LpVariable(
            cat=plp.LpContinuous,
            name=f"phi_hc_nd_ac_{n}_{u}".format(n,u)) for u in set_HVAC   for n in set_N
        }
    
    omega_m_ac	= {(n,u):                                                                                     # [C] Temperatura media al nodo m; la media è valutata rispetto ai valori di temperatura istantanea al nodo m, all'istante t e all'istante t-1
        plp.LpVariable(cat=plp.LpContinuous,
                            name="omega_m_ac_{0}_{1}".format(n,u)) for n in set_Temp  for u in set_HVAC}
                            
    omega_s_ac	= {(n,u):                                                                                     # [C] Temperatura media al nodo s; valutata rispetto alla temperatura al nodo m. E' un valore derivato dalla combinazione tra la temperatura dell'aria e la temperatura media radiante
        plp.LpVariable(cat=plp.LpContinuous,
                            name="omega_s_ac_{0}_{1}".format(n,u)) for n in set_Temp  for u in set_HVAC}

    t_int	= {(n,u):                                                                                         # [C] Temperatura interna effettiva, cioè temperatura dell'aria all'interno della zona climatizzata
        plp.LpVariable(cat=plp.LpContinuous,
                            #lowBound=T_min_0, #upBound=T_max_0,
                            name="t_int_{0}_{1}".format(n,u)) for n in set_Temp  for u in set_HVAC}
    
    return phi_hc_nd_ac, omega_m_ac, omega_s_ac, t_int

###############################################################################################################################

def milp_hp_autonomous_variables(set_HVAC, set_N):

        q_hp = {(n, u): 
            plp.LpVariable(
                cat=plp.LpContinuous,
                name=f"q_hp_{n}_{u}".format(n,u)) for u in set_HVAC   for n in set_N
        }

        # Potenza elettrica assorbita dalla PdC
        ee_binary = {(n,u): 
            plp.LpVariable(cat=plp.LpBinary,
                    name="ee_binary_{0}_{1}".format(n,u)) for n in set_N for u in set_HVAC}
        
        # Potenza elettrica PdC 
        ee_tot = {(n,u):                                                                                              # [Wh] Energia elettrica consumata dalla PdC al quarto d'ora
            plp.LpVariable(cat=plp.LpContinuous,
                        lowBound=0,
                        name="ee_tot_{0}_{1}".format(n,u)) for n in set_N for u in set_HVAC}

        q_heater    = {(n, u): 
            plp.LpVariable(
                    cat=plp.LpContinuous,
                    lowBound=0,
                    name=f"Q_heater_{n}_{u}".format(n,u)) for u in set_HVAC   for n in set_N }
        
        q_crankcase   = {(n, u): 
            plp.LpVariable(
                    cat=plp.LpContinuous,
                    lowBound=0, 
                    name=f"Q_crankcase_{n}_{u}".format(n,u)) for u in set_HVAC   for n in set_N }
        
        return q_hp, ee_binary, ee_tot, q_heater, q_crankcase

###############################################################################################################################

def milp_hp_centralized_variables(set_N):

    q_hp = {
        n: plp.LpVariable(
            cat=plp.LpContinuous,
            name=f"Q_hp_{n}".format(n))  for n in set_N
    }
    # Potenza elettrica assorbita dalla PdC
    ee_binary = {n: 
    plp.LpVariable(cat=plp.LpBinary,
                #lowBound=0, upBound=1,
                name="EE_binary_{0}".format(n)) for n in set_N}
    
    # Potenza elettrica 
    ee_tot = {n:                                                                                              # [Wh] Energia elettrica consumata dalla PdC al quarto d'ora
    plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0,
                    name="EE_tot_{0}".format(n)) for n in set_N }
        
    return q_hp, ee_binary, ee_tot

###############################################################################################################################

def milp_hp_centralized_storage_variables(set_N, set_Temp, h_water_tank_0):

    # Status avviamento compressore PdC centralizzata
    k_compressor_on = {n: 
    plp.LpVariable(cat=plp.LpBinary,
                name="k_compressor_on_{0}".format(n)) for n in set_N}
    
    # # Status spegnimento compressore PdC centralizzata
    k_compressor_off = {n: 
    plp.LpVariable(cat=plp.LpBinary,
                name="k_compressor_off_{0}".format(n)) for n in set_N}
    
    # # Status del compressore centralizzato (ON/OFF)
    k_compressor_status = {n: 
    plp.LpVariable(cat=plp.LpInteger,
                    lowBound=0, upBound=1,
                name="k_compressor_status_{0}".format(n)) for n in set_N}
    
    # Temperatura media sistema accumulo acqua calda PdC centralizzata
    t_water_tank = {n: 
    plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=54, upBound=62,
                name="T_water_tank_{0}".format(n)) for n in set_Temp}

    # # Entalpia media sistema accumulo acqua calda PdC centralizzata
    delta_h = {n: 
    plp.LpVariable(cat=plp.LpContinuous,
                    lowBound=0, upBound=h_water_tank_0,
                name="delta_h_{0}".format(n)) for n in set_N}
        
    return k_compressor_on, k_compressor_off, k_compressor_status, t_water_tank, delta_h

###############################################################################################################################

def milp_results (set_HVAC, set_N, phi_hc_nd_ac, ee_tot, omega_m_ac, omega_s_ac, t_int, t_start_dayahead, n_intervals, cacer_type):
    
    th_load = np.zeros(n_intervals)
    hp_energy = np.zeros(n_intervals)

    results_phi_hc_nd_ac = {}
    results_hp_energy_consumption = {}
    
    results_omega_m_ac = {}
    results_omega_s_ac = {}
    results_t_int = {}

    if cacer_type == 'AUC':
        results_hp_energy_consumption_array=np.zeros(n_intervals)
        results_hp_energy_consumption = [ee_tot[(time)].varValue for time in set_N]
        hp_energy=np.array(results_hp_energy_consumption)

    for user in set_HVAC:

        # Estrai i valori delle variabili (specifici per questo utente)
        results_phi_hc_nd_ac[user] = [phi_hc_nd_ac[(time,user)].varValue for time in set_N]
        
        if cacer_type == 'CER':
            results_hp_energy_consumption[user] = [ee_tot[(time,user)].varValue for time in set_N]
            results_hp_energy_consumption_array=np.array(results_hp_energy_consumption[user])
            hp_energy=hp_energy+results_hp_energy_consumption_array[:]
        
        results_omega_m_ac[user] = [omega_m_ac[(time,user)].varValue for time in set_N]
        results_omega_s_ac[user] = [omega_s_ac[(time,user)].varValue for time in set_N]
        results_t_int[user] = [t_int[(time,user)].varValue for time in set_N]

        t_start_dayahead[user][2] = results_t_int[user][-1]
        t_start_dayahead[user][1] = results_omega_s_ac[user][-1]
        t_start_dayahead[user][0] = results_omega_m_ac[user][-1]
        
        results_phi_hc_nd_ac_array=np.array(results_phi_hc_nd_ac[user])
        th_load = th_load+results_phi_hc_nd_ac_array[:]

        return th_load, hp_energy, t_start_dayahead
    
###############################################################################################################################

def milp_hp_storage_results(k_compressor_status, t_water_tank, set_N):
    
    results_k_compressor_status = {}
    results_t_water_tank = {}
    
    results_k_compressor_status =[k_compressor_status[(time)].varValue for time in set_N]
    k_compressor_status_0=results_k_compressor_status[-1]
    
    results_t_water_tank = [t_water_tank[(time)].varValue for time in set_N]
    t_water_tank_0=results_t_water_tank[-1]

    return k_compressor_status_0, t_water_tank_0