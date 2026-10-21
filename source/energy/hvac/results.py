import pandas as pd

def df_results_generator(th_load, hp_energy_heating, hp_energy_cooling, dt, df_climate_data, n_intervals, df_total_results, start_time_optimization=0):

        th_load = th_load * dt / 1000
        hp_energy_heating = hp_energy_heating * dt / 1000                                                       
        hp_energy_cooling = hp_energy_cooling * dt / 1000
        hp_energy = hp_energy_heating + hp_energy_cooling                                                      
        
        df_results = pd.DataFrame({'datetime' : df_climate_data['datetime'].iloc[start_time_optimization : n_intervals + start_time_optimization], 
                                 'thermal load [kWh]' : th_load, 
                                 'energy consumption [kWh]' : hp_energy,
                                 'energy consumption heating [kWh]' : hp_energy_heating,
                                 'energy consumption cooling [kWh]' : hp_energy_cooling}
                                 )
        
        df_total_results = pd.concat([df_total_results, df_results], axis=0, ignore_index=True)

        return df_total_results

########################################################################################################

def users_list_generator(hp_users_type, n_intervals, P_CONTRACT_USER, M):

    n_prosumers = 0
    user_name_list=[]
    hp_users_list=[]
    prosumer_p_contr=[]
    consumer_p_contr=[]
    hp_hvac_users_list=[]

    df_total_results=pd.DataFrame()

    for config in range(len(hp_users_type)):
        user_name=hp_users_type[config].user_name
        if hp_users_type[config].user_type == 'prosumer':
            n_prosumers=n_prosumers+1

            if hp_users_type[config].p_contr=='P>6':
                p_contract=M
            else:
                p_contract=P_CONTRACT_USER
            prosumer_p_contr.append(p_contract)

        for user in range (hp_users_type[config].user_numbers):
            
            hp_users_list.append(hp_users_type[config].users[user])
            hp_hvac_users_list.append(hp_users_type[config].hvac_type)
            consumer_p_contr.append(P_CONTRACT_USER)
        

        for _ in range(n_intervals):
            user_name_list.append(user_name)

    return df_total_results, user_name_list, n_prosumers, hp_users_list, prosumer_p_contr, consumer_p_contr, hp_hvac_users_list

########################################################################################################
