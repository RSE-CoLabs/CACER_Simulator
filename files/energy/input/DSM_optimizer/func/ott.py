import numpy as np
import pandas as pd
import plotly.graph_objects as go
from files.energy.input.DSM_optimizer.func.func import genetic_algorithm, stampa_result

###################################################################################################################################################

def ottimizzazione(immission_profile, consumption_profiles,num_intervals, day, create_plot = True, show_plot = True):
    
    ##### Trovare valori permessi immissione nei quali andare a inserire elettrodomestici:
    # Trovare gli indici dei valori maggiori di zero
       
    allowed_intervals = np.where(np.array(immission_profile) > 0)[0].tolist()
    max_power_contract = 3

    # Grid search parameters
    n_devices = len(consumption_profiles)
    
    # consumo totale:
    #consumption_total = sum([sum(consumption_profile) for consumption_profile in consumption_profiles])
    consumption_total = sum(map(np.sum, consumption_profiles))
    # Define energy cost (e.g., cost per kWh)
    # energy_cost_per_hour = [0.3]* num_intervals #- intervallo_funzionamento(35,60,96)*0.2 # Electricity price per kWh
    energy_cost_per_hour = np.full(num_intervals, 0.3)
    # Generation profile
    # # Trova il valore massimo
    # max_value = max(pv_profile)

    # # Normalizza la lista
    # normalized_profile = [x / max_value for x in pv_profile]

    # # scalo in funzione della taglia: 
    # taglia_FV = max(2,1*(math.ceil(n_devices/4)))
    # #taglia_FV = consumption_total/(sum(normalized_profile)*0.04*n_devices)   # la taglia deve rendere il rapporto tra cosnumo singolo dispositivo e totale energia immessa = 0.6
        
    # generation_profile = [x * taglia_FV for x in normalized_profile]   
    
    # Immission profile
    # """ Questa parte è da modificare quando avremo la produzione fotovoltaica"""
    # immission_profile = [
    #     max(0, generation_profile[i] - immission_profile[i])
    #     for i in range(num_intervals)
    # ]
    
    # Calcoliamo il rapporto tra il consumo e l'immissionee, per valutare percentuale possibili condivisione sul totale: 

    # immission_total = sum(immission_profile)
    immission_total = np.sum(immission_profile)
    
    perc_econd= min(consumption_total, immission_total)/immission_total  # varia tra 0 e 1 
    perc_error = 0
    perc_error_1 = 0
    
    # Calcoliamo il rapporto tra il consumo e l'immissionee, per valutare percentuale possibili condivisione sul totale: 
    
    if perc_econd/n_devices < 0.04 and perc_econd < 0.65:  
        # Grid search parameters
        population_size = min(50,max(10,n_devices*2))
        generations = 20
        mutation_rate = 0.05
        
    elif perc_econd/n_devices < 0.06 and perc_econd < 0.55:
        # Grid search parameters
        population_size = min(50,n_devices*3)
        generations = max(20,min(50,n_devices*2))
        mutation_rate = 0.05
    
    elif perc_econd/n_devices < 0.01 and perc_econd > 0.65:
        # Grid search parameters
        """"da mnodificare---->"""
        population_size = 20
        generations = 20
        mutation_rate = 0.05
    
    else:
        # Grid search parameters
        population_size = min(50,n_devices*3)
        generations = max(20,min(50,n_devices*6))
        mutation_rate = 0.05

    # print(f"\nNUMBER DEVICE(S): {n_devices}")
    
    #################### SOLUTIONS:####################
    # Creazione del dizionario di input alla funzione.

    params = {
            "num_intervals": num_intervals,
            "population_size": population_size,
            "generations": generations,
            "mutation_rate": mutation_rate,
            "consumption_profiles": consumption_profiles,
            "immission_profile": immission_profile,
            "max_power_contract": max_power_contract,
            "energy_cost_per_hour": energy_cost_per_hour,
            "allowed_intervals": allowed_intervals
        }

    # vera e propria funzione di ottimizzazione:
    best_solution = genetic_algorithm(**params)
    param = [population_size, generations, mutation_rate]
    
    # funzione per il plot
    #################### PLOT:####################    
    # create the dataframe devices:
    # Possiamo differenziarlo in funzione della tipologia di utenza e del nome del dispositivo: ad esempio user_n_single_washing_machine ecc..
    # magari creo una funzione ad hoc per questo, vediamo dopo  ? 
    
    ##############
    # Creazione delle colonne in modo compatto
    u = 0
    #columns = [f'user_{u}_{key}' for key, count in sched_dev.items() for _ in range(1, count + 1)]
    columns = []    
    for count in range(int(n_devices/2)):
        for key in ['washing_machine','dish_washer']:
            columns.append(f'user_{u}_{key}')
        u = u +1

    # Creazione del DataFrame
    df_plot = pd.DataFrame(data=np.transpose(best_solution[0]),
                        index=np.arange(num_intervals),
                        columns=columns)
    
    # df_plot = pd.DataFrame(data=np.transpose(best_solution[0]),
    #                     index=np.arange(num_intervals),
    #                     columns=[f'user_{u=u+1}_{key}' for u in range(1, n_devices + 1) for key in sched_dev.keys()])
    
    ##############

    # Crea il DataFrame immissione:
    df = pd.DataFrame({
        'immission_profile': immission_profile,
        
    }, index=np.arange(num_intervals))

    # Voglio calcolarmi l'energia totale condivisa. Con ritorno economico dato da incentivo totale: 
    # max(immissione[t], sum(prelievo utenze domestiche[t])*incentivo for 
    # Calcolare la somma degli elementi su ogni riga per il primo DataFrame
    sum_df1_1 = df_plot.sum(axis=1)
    # Sottrarre il valore corrispondente del secondo DataFrame
    energy_shared_1 = np.minimum(sum_df1_1.values, df['immission_profile'].values)
    
    # Creare un nuovo DataFrame con una colonna chiamata 'energy_shared'
    #df_energy_shared_1 = pd.DataFrame({'energy_shared': energy_shared_1})
    #print(f'Vector of energy sherred: {df_energy_shared}')
    #total_energy_shared_1 = df_energy_shared_1['energy_shared'].sum()
    total_energy_shared_1 = np.sum(energy_shared_1)
    total_incentive_1 = total_energy_shared_1*0.11
    total_energy_consumption_1 = np.sum(sum_df1_1)
    total_energy_cost_1 = total_energy_consumption_1*0.3    
    #total_immission_energy_1 = df['immission_profile'].sum()
    total_immission_energy_1 = np.sum(immission_profile)
    perc_error_1 = total_energy_shared_1/min(total_immission_energy_1,total_energy_consumption_1)
    
    if  perc_error_1<=1:  
                 
        e_cond_i = 0
        e_cond_f =  0 
        e_cons_profile = np.zeros(96)
        
        # Crea il DataFrame dispositivi in surplus:
        df_user_over = pd.DataFrame({                        
                                    }, 
                                    index=np.arange(num_intervals))
        # Ciclo
        for column in df_plot.columns:
            e_cons_profile += df_plot[column]
            #e_cond_f = sum([min(immission_profile[t], e_cons_profile[t])for t in range(len(e_cons_profile))])
            e_cond_f = np.sum(np.minimum(immission_profile, e_cons_profile))
            
            if e_cond_f == e_cond_i:
                df_user_over[column] = df_plot[column]
                e_cons_profile -= df_plot[column]
            
            #if e_cond_f < sum(e_cons_profile):
            if e_cond_f < np.sum(e_cons_profile):
                
                df_user_over[column] = df_plot[column]
                e_cons_profile -= df_plot[column]
                e_cond_f = e_cond_i
            
            e_cond_i = e_cond_f

        
        if not df_user_over.dropna().empty:
            df_total_new =df_plot.drop(columns= df_user_over.columns)
                       
            df_total_new_sum = df_total_new.sum(axis=1)
            
            # Trasformiamo per vettorializzare:
            # Calcolo del nuovo profilo di immissione utilizzando Pandas
            #immission_profile_series = pd.Series(immission_profile)
            # Calcolo del nuovo profilo di immissione
            #immission_profile_new = (immission_profile_series - df_total_new_sum).clip(lower=0).tolist()
            immission_profile_new = np.clip(immission_profile - df_total_new_sum.values, 0, None)
            
            ##### Trovare valori permessi immissione nei quali andare a inserire elettrodomestici:
            # Trovare valori permessi di immissione
            allowed_intervals = np.where(np.array(immission_profile) > 0)[0].tolist()

            # Trasposizione e filtraggio dei profili di consumo
            consumption_profiles = [df_user_over.transpose().values[t][df_user_over.transpose().values[t] > 0] for t in range(len(df_user_over.columns))]

            
            population_size = min(50,len(consumption_profiles)*20)
            generations     = min(50,len(consumption_profiles)*20)
            
            params = {
                "num_intervals": num_intervals,
                "population_size": population_size,
                "generations": generations,
                "mutation_rate": mutation_rate,
                "consumption_profiles": consumption_profiles,
                "immission_profile": immission_profile_new,
                "max_power_contract": max_power_contract,
                "energy_cost_per_hour": energy_cost_per_hour,
                "allowed_intervals": allowed_intervals
            }
             
            # second GA
            best_solution_2 = genetic_algorithm(**params)
            param = [population_size, generations, mutation_rate]
            # create the dataframe devices:
            df_user_opt_2 = pd.DataFrame(data=np.transpose(best_solution_2[0]),
                        index=np.arange(num_intervals),
                        columns= df_user_over.columns)
   
            df_total_new = pd.concat([df_total_new, df_user_opt_2], axis=1)
            sum_df1 = df_total_new.sum(axis=1)
            # Sottrarre il valore corrispondente del secondo DataFrame
            energy_shared = np.minimum(sum_df1.values, df['immission_profile'].values)
            # Creare un nuovo DataFrame con una colonna chiamata 'energy_shared'
            # df_energy_shared = pd.DataFrame({'energy_shared': energy_shared})
            # total_energy_shared = df_energy_shared['energy_shared'].sum()
            total_energy_shared = np.sum(energy_shared)
            total_incentive = total_energy_shared*0.11
            #total_energy_consumption = sum_df1.sum()
            total_energy_consumption = np.sum(sum_df1)
            total_energy_cost = total_energy_consumption*0.3
            #total_immission_energy = df['immission_profile'].sum()
            #total_immission_energy = total_immission_energy_1.copy()
            perc_error = total_energy_shared/min(total_immission_energy_1,total_energy_consumption)
            
           
    # teniamo solo quello con percentuale condivisione migliore, quindi: 
    if perc_error < perc_error_1:
        #print("Return first")
        if create_plot:
            stampa_result(df_plot, immission_profile, num_intervals, day, show_plot)
        #print_result(perc_econd,n_devices,total_energy_shared_1,total_incentive_1,total_energy_consumption_1,total_energy_cost_1,perc_error_1,*param)
        #perc_condivisione_utilizzo = total_energy_shared_1/total_energy_consumption_1
        return df_plot
    
    else:
        #print("Return second")
        if create_plot:
            stampa_result(df_total_new, immission_profile, num_intervals, day, show_plot)
        #print_result(perc_econd,n_devices,total_energy_shared,total_incentive,total_energy_consumption,total_energy_cost,perc_error,*param)
        #perc_condivisione_utilizzo = total_energy_shared/total_energy_consumption # type: ignore
        return df_total_new
    
