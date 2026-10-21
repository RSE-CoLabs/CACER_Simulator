from __future__ import annotations

import calendar
import contextlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import io
import math
from pathlib import Path
import pickle
import random
import sys
from typing import Any, Mapping
import warnings

import holidays
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.graph_objs as go_objs
from simple_colors import blue, green, red
from tqdm.auto import tqdm
import yaml

from source.config.utilities import generate_calendar_modified


# Migrated from files/energy/input/DSM_optimizer/func/func.py:10
def print_result(perc_econd,n_devices,total_energy_shared,total_incentive,total_energy_consumption,total_energy_cost,perc_error,*param):
    print("\nGA OPT\n")
    print("Percentuale condivisione: {:.2f} %".format(float(perc_econd)*100))
    print("Percentuale condivisione per singolo dispositivo: {:.2f} %".format(float(perc_econd/n_devices)*100))
    print(f'Total energy sherred: {total_energy_shared}')
    print(f'Incentivo totale: {total_incentive}')
    print(f'Total energy consumption: {total_energy_consumption}')
    print(f'Costo totale: {total_energy_cost}')
    print("Optimization in percentuale su consumo: {:.2f}%".format(float((perc_error)*100)))
    print('popolazione {}, generazione: {}, mutazione: {}'.format(*param))


# Migrated from files/energy/input/DSM_optimizer/func/func.py:23
def stampa_result(
    dataframe,
    immission_profile,
    num_intervals,
    day,
    show_plot=True,
    output_path=None,
):

    # # print per tutti i dispositiv:
    df = pd.DataFrame({
        'immission_profile': immission_profile,

    }, index=np.arange(num_intervals))

    # # Create figure:
    x = pd.date_range(start='2018-01-01 00:00+00:00', freq='15min', inclusive='left', periods=97)
    fig = go.Figure()

    # tutte queste sono cumulate, quindi stacked area
    for column in dataframe.columns:
        fig.add_trace(go.Scatter(
            x = x, y = dataframe[column], mode='lines',
                    name = column,
                    line_shape = 'hv',
                    textposition='top center',stackgroup='one'))

    # Inserisco il profilo di immissione:
    fig.add_trace(go.Scatter(
            x = x, y = df['immission_profile'], mode='lines',
                    name = 'immission_profile',
                    line_shape = 'hv',
                    textposition='top center'))

    fig.update_yaxes(title_text = "Power (kW)")          # verificare se è effettivamente la potenza:
    fig.update_xaxes(title_text = 'Tempo (HH:MM)', dtick = 1000*60*30, range = [x[0], x[96]])
    fig.update_layout(title= f'Day {day}', xaxis_tickformat = '%H:%M', plot_bgcolor='white', legend = dict(orientation='h',yanchor="top", y = -0.4, xanchor="left", x=0.01)) #barmode='stack') # si setta la modalità di rappresentazione del grafico a barre, in questo caso avranno una visualizzazione di tipo "stack", ovvero impilate le une sulle altre

    if show_plot:
        fig.show()

    #########################################################################################################

    if output_path is not None:
        path = Path(output_path)
        path.mkdir(parents=True, exist_ok=True)
        title = "DSM optimization day " + str(day)
        fig.write_html(path / f"{title}.html")
        fig.write_image(
            path / f"{title}.png",
            width=1000,
            height=1100/13.2*5,
            scale=4,
        )


# Migrated from files/energy/input/DSM_optimizer/func/func.py:150
def stampa_best_solution_gen(fig, best_solution_gen,params, n_device):
    # create the dataframe:

    df = pd.DataFrame({
        'fitness_values': best_solution_gen,

    }, index=np.arange(len(best_solution_gen)))

    x = df.index

    fig.add_trace(go.Scatter(
            x = x, y = df['fitness_values'], mode='lines',
                    name = 'ft_p_{}_g_{}_m_{}'.format(*params),
                    line_shape = 'hv',
                    textposition='top center'))

    fig.update_yaxes(title_text = "fitness_values")
    fig.update_xaxes(title_text = 'Number of Gen')
    fig.update_layout(title= f'GA Optimization Device for {n_device} devices', plot_bgcolor='white', legend = dict(orientation='h',yanchor="top", y = -0.4, xanchor="left", x=0.01))


# Migrated from files/energy/input/DSM_optimizer/func/func.py:172
def intervallo_funzionamento(start,end,n):
    giorno = np.zeros(n,int)
    for i in range(start,end):
        giorno[i]=1
    return giorno


# Migrated from files/energy/input/DSM_optimizer/func/func.py:181
def generate_random_consumption_profile(length):
    return np.random.rand(length)


# Migrated from files/energy/input/DSM_optimizer/func/func.py:186
def first_nonzero_index(arr):
    """funzione per trovare l'indice del primo elemento non nullo di un array

    Args:
        arr (array): array di numpy

    Returns:
        int: indice del primo elemento non nullo, 0 se l'array è vuoto
    """
    nonzero_indices = np.nonzero(arr)[0]
    return nonzero_indices[0] if nonzero_indices.size > 0 else 0


# Migrated from files/energy/input/DSM_optimizer/func/func.py:245
def calculate_device_cost(device_schedule, immission_profile, energy_cost_per_hour):

    # device_schedule = np.asarray(device_schedule)
    # total_power = device_schedule.sum(axis=0)
    total_power = np.sum(device_schedule, axis=0)
    total_energy_cost = np.dot(total_power, energy_cost_per_hour)

    total_energy_shared = np.dot(np.minimum(total_power, immission_profile), 0.11)

    total_cost = total_energy_cost.sum() - total_energy_shared.sum()
    return total_cost


# Migrated from files/energy/input/DSM_optimizer/func/func.py:269
def generate_random_solution(num_intervals, consumption_profiles, allowed_intervals, possible_starts):
    solution = []
    for profile in consumption_profiles:
        # Seleziona casualmente un punto di inizio nel profilo di consumo
        # Integro ora il vincolo sugli istanti di tempo permessi:
        start_index = random.choice(possible_starts)
        # start_index = np.random.randint(0, num_intervals - len(profile))
        # Costruisci il programma di utilizzo del dispositivo utilizzando il profilo di consumo
        device_schedule = [0] * num_intervals
        device_schedule[start_index:start_index + len(profile)] = profile
        solution.append(device_schedule)
    return solution


# Migrated from files/energy/input/DSM_optimizer/func/func.py:297
def mutate_solution(solution, mutation_rate, consumption_profiles, allowed_intervals, num_intervals, possible_starts):
    for i, device_schedule in enumerate(solution):
        if np.random.rand() < mutation_rate:
            # Seleziona casualmente un nuovo punto di inizio per il profilo di consumo
            # Integro ora il vincolo sugli istanti di tempo permessi:
            profile = consumption_profiles[i]
            new_start_index = random.choice(possible_starts)
            #new_start_index = np.random.randint(0, len(device_schedule) - len(profile))
            # Aggiorna il programma di utilizzo del dispositivo
            new_device_schedule = [0] * len(device_schedule)
            new_device_schedule[new_start_index:new_start_index + len(profile)] = profile
            solution[i] = new_device_schedule
    return solution


# Migrated from files/energy/input/DSM_optimizer/func/func.py:329
def genetic_algorithm(num_intervals, population_size, generations, mutation_rate, consumption_profiles,immission_profile, max_power_contract, energy_cost_per_hour, allowed_intervals):

    # calcolo possibili istanti attivazione:
    for profile in consumption_profiles:
        possible_starts = [i for i in allowed_intervals if i + len(profile)-1 <= allowed_intervals[-1]] #ultimo valore di allowed intervals
        possible_starts = sorted(possible_starts, key=lambda x: -sum(immission_profile[x:x + len(profile)]))

    # Inizializza la popolazione iniziale di soluzioni casuali
    population = [generate_random_solution(num_intervals, consumption_profiles, allowed_intervals, possible_starts) for _ in range(population_size)]

    # per analisi, eliminare poi:
    best_solution_gen_value =[]

    # Esegui le iterazioni per un numero fisso di generazioni
    for generation in range(generations):
        # Calcola il valore di fitness per ogni soluzione nella popolazione
        # fitness_values = objective_function(population, consumption_profiles)
        fitness_values = [np.sum(calculate_device_cost(solution, immission_profile, energy_cost_per_hour)) for solution in population]

        # Seleziona i genitori in base al loro valore di fitness
        parents = [population[i] for i in np.argsort(fitness_values)[:int(population_size/2)]]

        # Genera nuovi individui attraverso incrocio (crossover)
        children = []
        for _ in range(population_size - len(parents)):
            parent1, parent2 = random.sample(parents, 2)
            crossover_point = np.random.randint(num_intervals)
            child = parent1[:crossover_point] + parent2[crossover_point:]
            #child = np.concatenate((parent1[:, :crossover_point], parent2[:, crossover_point:]), axis=1)
            children.append(child)

        # Aggiorna la popolazione con nuovi individui generati attraverso crossover e mutazione
        population = parents + children
        population = [mutate_solution(solution, mutation_rate, consumption_profiles, allowed_intervals, num_intervals, possible_starts) for solution in population]

        # Elitismo: conserva la migliore soluzione
        best_solution = min(population, key=lambda sol: calculate_device_cost(sol, immission_profile, energy_cost_per_hour))
        population[0] = best_solution

        # Introduci diversità ogni 10 generazioni
        if generation % 5 == 0:
            for i in range(len(population)):
                if np.random.rand() < 0.1:
                    population[i] = generate_random_solution(num_intervals, consumption_profiles,allowed_intervals, possible_starts)


        # Per analisi ---> da eliminare poi
        best_solution_gen_value.append(fitness_values[np.argmin(fitness_values)])

    # Calcola il valore di fitness per ogni soluzione nella popolazione finale
    fitness_values = [np.sum(calculate_device_cost(solution, immission_profile, energy_cost_per_hour)) for solution in population]

    # Trova e restituisci la migliore soluzione
    best_solution_index = np.argmin(fitness_values)
    best_solution = population[best_solution_index]
    best_cost = fitness_values[best_solution_index]

    return best_solution, best_cost, best_solution_gen_value


# Migrated from files/energy/input/DSM_optimizer/func/ott.py:8
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


# Migrated from files/energy/input/DSM_optimizer/main.py:8
def crea_lista_consumi(appliance_profiles, n_user):

    df = appliance_profiles

    # Filtra i valori positivi di consumo per le colonne 'washing_machine_1' e 'dish_washer_1'
    df_washing_machine = df['dish_washer'][df['dish_washer'] > 0].tolist()
    df_dish_washer = df['washing_machine'][df['washing_machine'] > 0].tolist()

    # Moltiplica i profili di consumo per la potenza in funzione della tipologia di utenza:
    lista_consumi = [df_washing_machine, df_dish_washer] * n_user

    return lista_consumi


# Migrated from files/energy/input/DSM_optimizer/main.py:22
def aggiorna_start_time_dict(user_dict, primi_positivi, cont):
    # day_index = f'day_{cont+1}'  # Crea l'indice come 'day_0', 'day_1', ecc.
    day_index = cont

    for idx, (key, value) in enumerate(primi_positivi.items()):
        # Dividi la stringa della colonna in 'user', numero utente, e tipo di appliance
        parts = key.split('_')  # ['user', '0', 'washing', 'machine']
        user = f"{parts[0]}_{parts[1]}"  # Crea user_0, user_1, etc.
        appliance = f"{parts[2]}_{parts[3]}"  # Crea washing_machine o dish_washer

        # Se l'utente non è ancora nel dizionario, crea un nuovo DataFrame vuoto per quell'utente
        if user not in user_dict:
            user_dict[user] = pd.DataFrame(columns=['washing_machine', 'dish_washer'])

        # Aggiungi una riga con i valori per 'washing_machine' e 'dish_washer' per il giorno corrente
        if appliance == 'washing_machine':
            if day_index not in user_dict[user].index:
                user_dict[user].loc[day_index] = [value, None]  # Inizializza la riga per il giorno
            else:
                user_dict[user].at[day_index, 'washing_machine'] = value  # Aggiungi washing machine value
        elif appliance == 'dish_washer':
            if day_index not in user_dict[user].index:
                user_dict[user].loc[day_index] = [None, value]  # Inizializza la riga per il giorno
            else:
                user_dict[user].at[day_index, 'dish_washer'] = value  # Aggiungi dish washer value

    return user_dict


# Migrated from files/energy/input/DSM_optimizer/main.py:51
def ott_year(
    df_immission,
    n_devices,
    appliance_profiles,
    create_plot=True,
    show_plot=True,
):

    freq = '15min'

    # Ora dobbiamo fare ottimizzazione per ognuno dei 36 giorni che abbiamo, bisogna fare anche la media sull'immissione:
    output_dictionary = {}
    num_intervals = 96
    consumption_profiles = crea_lista_consumi(appliance_profiles, n_devices)

    # output for profile emulator
    start_time_dict = {}

    # Ora per iterare sui giorni:
    for cont, (day, daily_data) in enumerate(df_immission.groupby(df_immission.index.date)):
        # Prendiamo i 96 valori per ogni giorno
        # consumo_giornaliero = daily_data['consumo'].values
        immissione_giornaliera = daily_data.values

        if (immissione_giornaliera == 0).all().all():
            print("\n--------------------------------------------------------------------------------------------")
            print(red("Day " + str(cont) + " skipped!", ['bold']))
            print("--------------------------------------------------------------------------------------------\n")

        else:
            try:
                # Vera e propria ottimizzazione:
                df_dev_scheduled = ottimizzazione(immission_profile=immissione_giornaliera,
                                                        consumption_profiles=consumption_profiles,
                                                        num_intervals=num_intervals,
                                                        day = cont,
                                                        create_plot = create_plot,
                                                        show_plot = show_plot
                                                        )

                if not show_plot:
                    print("\n--------------------------------------------------------------------------------------------")
                    print(green("Day " + str(cont) + " optimized!",  ['bold']))
                    print("--------------------------------------------------------------------------------------------\n")


                # Crea output
                # trovo per ogni utente e per ogni elettrodomestico il primo istante di attivazione
                # Trova il primo istante in cui ogni colonna ha un valore positivo
                primi_positivi = df_dev_scheduled.gt(0).idxmax()
                start_time_dict = aggiorna_start_time_dict(start_time_dict, primi_positivi, cont)
            except:
                print("\n--------------------------------------------------------------------------------------------")
                print(red("Day " + str(cont) + " not optimized; check injected energy in this day, maybe too low!", ['bold']))
                print("--------------------------------------------------------------------------------------------\n")

    return start_time_dict


# Migrated from src/Functions_Load_Emulator_and_DSM.py:612
def create_all_user_appliance_DSM_start_time(
    DSM_emulated_users_list,
    num_days,
    calendario,
    flag_daily_activation=True,
    flag_multi_use=True,
    *,
    appliance_load_df,
    usage_probability_DSM_df,
    num_daily_usage_probability_df,
    week_usage_probability_df,
    start_time_dict,
):
    """Create all user DSM (Demand Side Management) appliance start time.

        In particular, we use the dictionary created before for a noDSM case and modify the start time of specified appliances with
        a different daily usage probability concentrate in the productivity period (we set equal to zeros all usage probabilities
        out of the productivity period in way to be sure that the activation of the flex appliaces is inside this period).

    Inputs:
        num_days (float): number of days to simulate
        calendario (dataframe): calendar
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.

    Outputs:
        all_user_appliance_start_time_dict_1: dictionary with the start time for the first use of the appliance
        all_user_appliance_start_time_dict_2: dictionary with the start time for the second use of the appliance (if activated)
        all_user_appliance_start_time_dict_3: dictionary with the start time for the third use of the appliance (if activated)
    """

    num_timestep_load_profile = (appliance_load_df != 0).sum() # we calculate the number of timesteps for each appliance

    wm_week_usage_probability_df = week_usage_probability_df.loc['washing_machines'].copy() # extract the weekly usage probability for the washing machine

    boolean_list = [True, False] # list of boolean values
    time_list = np.arange(0, 96 , 1).tolist() # we create a list with all timesteps
    num_of_uses_list = np.arange(1, 4 , 1).tolist() # we create a list with all number of uses

    # split dictionaries in different part (dict_1 are the start time for the first activation; dict_2 are the start time for the second activation, etc.)
    start_time_dict_1 = start_time_dict[0] # number of uses equal to 1
    start_time_dict_2 = start_time_dict[1] # number of uses equal to 2
    start_time_dict_3 = start_time_dict[2] # number of uses equal to 3

    # copy the dictionaries
    start_time_DSM_dict_1 = start_time_dict_1.copy() # number of uses equal to 1
    start_time_DSM_dict_2 = start_time_dict_2.copy() # number of uses equal to 2
    start_time_DSM_dict_3 = start_time_dict_3.copy() # number of uses equal to 3

    ##################################################################################################
    ##################################################################################################

    appliances_flex_list = ['washing_machine', "dish_washer"] # set the list for the flexible appliances; name appliances --> ["washing_machine", "dish_washer", "microwaves", "tv", "oven"]

    ##################################################################################################
    ##################################################################################################

    for user in tqdm(DSM_emulated_users_list, desc = "Generate all user appliance DSM start time"):

        for appliance in appliances_flex_list:

            # we extract a random value for the start time for each appliance for every day for the user under exam and save all values in a specific df
            start_time_DSM_df_1 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 1)
            start_time_DSM_df_2 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 2)
            start_time_DSM_df_3 = pd.DataFrame(index = np.arange(num_days), columns = appliances_flex_list) # create an empty df to save the start timestep for each day that we would like to create (num_uses = 3)

            ##################################################################################################

            for day in range(num_days):

                activation_probability_flag = True # we initialize the flag probability for the daily usage for the selected day and appliance

                # if the appliance is in list (only washing machine for the moment) and the external flag is setted to true, we modifify with a probability the daily activation of the appliance
                if appliance in ["washing_machine"] and flag_daily_activation:

                    day_type = calendario.iloc[day]['day_flag'] # Working_day; Saturday; Sunday
                    activation_wm_probability = wm_week_usage_probability_df[day_type]
                    activation_wm_probability_list = [activation_wm_probability, 100 - activation_wm_probability]
                    activation_probability_flag = random.choices(boolean_list, weights = activation_wm_probability_list, k = 1)[0] # we randomly choose the start time for the selected appliance

                #############################################################################

                # if the appliance is activated in the selected days
                if activation_probability_flag:

                    num_of_uses_selected = 1

                    # number of uses equal to 1

                    probability_1 = usage_probability_DSM_df[appliance].tolist() # we import the usage probability for the selected appliance

                    timestep_selected_1 = random.choices(time_list, weights = probability_1, k = 1)[0] # we randomly choose the start time for the selected appliance
                    start_time_DSM_df_1[appliance][day] = timestep_selected_1 # we save the start time for the selected day

                    ##################################################################################################

                    # if the external flag for the multiple usages during the day is true
                    if flag_multi_use:

                        num_of_uses = num_daily_usage_probability_df[appliance].tolist() # we import the number of uses probability for the selected appliance
                        num_of_uses_selected = random.choices(num_of_uses_list, weights = num_of_uses, k = 1)[0] # we randomly choose the number of uses for the selected appliance

                        # number of uses equal to 2

                        if num_of_uses_selected > 1:

                            # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                            index = timestep_selected_1
                            delta = num_timestep_load_profile[appliance]
                            probability_2 = set_values_to_zero(probability_1, index, delta)

                            # we check if the probability is different from zero
                            if not all(x == 0 for x in probability_2):

                                timestep_selected_2 = random.choices(time_list, weights = probability_2, k = 1)[0] # we randomly choose the start time for the selected appliance
                                start_time_DSM_df_2[appliance][day] = timestep_selected_2 # we save the start time for the selected day

                                assert (timestep_selected_1 != timestep_selected_2), "The timesteps are equal!"
                                assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]), "The timesteps are equal!"

                            else:
                                warnings.warn("All values in probability are zeros in the case with 2 number of uses!", UserWarning)
                                print("")

                        #############################################################################

                        # number of uses equal to 3

                        if num_of_uses_selected > 2:

                            # we set to zero the probability for the selected appliance in the selected day for all timesteps in the range [index - delta, index + delta] in way to consider the previous activations of the appliance
                            index = timestep_selected_2
                            delta = num_timestep_load_profile[appliance]
                            probability_3 = set_values_to_zero(probability_2, index, delta)

                            # we check if the probability is different from zero
                            if not all(x == 0 for x in probability_3):

                                timestep_selected_3 = random.choices(time_list, weights = probability_3, k = 1)[0] # we randomly choose the start time for the selected appliance
                                start_time_DSM_df_3[appliance][day] = timestep_selected_3 # we save the start time for the selected day

                                assert (timestep_selected_1 != timestep_selected_2 or timestep_selected_1 != timestep_selected_3 or timestep_selected_2 != timestep_selected_3), "The timesteps are equal!"
                                assert (abs(timestep_selected_1 - timestep_selected_2) > num_timestep_load_profile[appliance]  or abs(timestep_selected_1 - timestep_selected_3) > num_timestep_load_profile[appliance]  or abs(timestep_selected_2 - timestep_selected_3) > num_timestep_load_profile[appliance] ), "The timesteps are equal!"

                            else:
                                warnings.warn("All values in probability are zeros in the case with 3 number of uses!", UserWarning)
                                print("")

            ##################################################################################################

            # we set the new dataframe with the start time in the DSM case for the selected appliance
            start_time_DSM_dict_1[user][appliance] = start_time_DSM_df_1[appliance] # number of uses equal to 1
            start_time_DSM_dict_2[user][appliance] = start_time_DSM_df_2[appliance] # number of uses equal to 2
            start_time_DSM_dict_3[user][appliance] = start_time_DSM_df_3[appliance] # number of uses equal to 3

    ##################################################################################################

    # create an aggregated dictionary with all the start time for the different number of uses
    start_time_DSM_dict = {}

    start_time_DSM_dict[0] = start_time_DSM_dict_1 # number of uses equal to 1
    start_time_DSM_dict[1] = start_time_DSM_dict_2 # number of uses equal to 2
    start_time_DSM_dict[2] = start_time_DSM_dict_3 # number of uses equal to 3

    print("\n     All users start time DSM completed!")

    return (start_time_DSM_dict_1, start_time_DSM_dict_2, start_time_DSM_dict_3)


# Migrated from src/Functions_Load_Emulator_and_DSM.py:897
def DSM_load_profile_emulator(
    emulated_users_list,
    DSM_emulated_users_list,
    start_day,
    end_day,
    flag_all_appliance=True,
    flag_daily_activation=True,
    flag_multi_use=True,
    *,
    appliance_load_df,
    usage_probability_DSM_df,
    num_daily_usage_probability_df,
    week_usage_probability_df,
    start_time_dict,
):
    """Simulate all user load profile with DSM (Demand Side Management).
    Inputs:
        emulated_users_list (list): list of users to simulate
        DSM_emulated_users_list (list): list of users to simulate with DSM
        start_day (datetime): start day for simulation
        end_day (datetime): end day for simulation
        flag_all_appliance (bool, optional): if false we use as input file the modified appliance load profile. Defaults to True.
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.
    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users
    """

    num_days = (end_day - start_day).days + 1 # we calculate the number of days to simulate

    #########################################################################

    print("\n1 - Generate calendar:\n")

    calendario = generate_calendar_modified(start_day, end_day)

    print('\n-----------------------------------------\n')

    #########################################################################

    print("2 - Generate start time DSM dictionary:\n")

    output_DSM = create_all_user_appliance_DSM_start_time(
        DSM_emulated_users_list,
        num_days,
        calendario,
        flag_daily_activation,
        flag_multi_use,
        appliance_load_df=appliance_load_df,
        usage_probability_DSM_df=usage_probability_DSM_df,
        num_daily_usage_probability_df=num_daily_usage_probability_df,
        week_usage_probability_df=week_usage_probability_df,
        start_time_dict=start_time_dict,
    )

    start_time_DSM_dict_1 = output_DSM[0]
    start_time_DSM_dict_2 = output_DSM[1]
    start_time_DSM_dict_3 = output_DSM[2]

    print('\n-----------------------------------------\n')

    #########################################################################

    print("3 - Generate all user profile DSM dictionary:\n")

    flag_DSM = True

    all_user_load_profile_dict = create_all_user_load_profile(
        start_time_DSM_dict_1,
        start_time_DSM_dict_2,
        start_time_DSM_dict_3,
        emulated_users_list,
        num_days,
        flag_DSM,
        flag_all_appliance,
        appliances_load_df=appliance_load_df,
    )

    print('\n-----------------------------------------\n')

    #########################################################################

    print("4 - Generate all user profiles DSM dataframe and export csv:\n")

    all_user_df = create_single_user_load_profile_df(all_user_load_profile_dict, calendario, flag_DSM)

    #########################################################################

    print('\n-----------------------------------------\n-----------------------------------------')
    print ('        Simulation completed!')
    print('-----------------------------------------\n-----------------------------------------')

    return all_user_df, output_DSM, all_user_load_profile_dict


from source.load.profiles import (
    create_all_user_load_profile,
    create_single_user_load_profile_df,
    set_values_to_zero,
)
