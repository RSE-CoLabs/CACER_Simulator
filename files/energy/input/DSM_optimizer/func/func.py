import numpy as np
import random
import yaml
# Sezione di print: 
import pandas as pd
import plotly.graph_objects as go

###################################################################################################################################################

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

###################################################################################################################################################

def stampa_result(dataframe, immission_profile, num_intervals, day, show_plot = True):
    
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

    config = yaml.safe_load(open("config.yml", 'r'))
    path = config['forldername_graphs_DSM_optimizer']

    title = "DSM optimization day " + str(day)

    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*5, scale = 4)

    #########################################################################################################

    # print delle tipologie d'utente:
    # fig = go.Figure()
    
    # Definizione dei raggruppamenti basati sulle stringhe specifiche
    # user_types = ['single', 'coppia', 'famiglia_3p', 'famiglia_4p', 'famiglia_mag4p']

    # Dizionario per memorizzare i risultati delle somme per ogni gruppo
    # group_sums = {}

    # Iterazione sui tipi di utenti per raggruppare e sommare le colonne
    # for user_type in user_types:
    #     # Selezione delle colonne che contengono la stringa specifica
    #     columns_to_group = [col for col in dataframe.columns if user_type in col]
        
    #     # Somma delle colonne selezionate
    #     df_grouped_sum = dataframe[columns_to_group].sum(axis=1)
        
    #     # Memorizzazione del risultato nel dizionario
    #     group_sums[user_type] = df_grouped_sum

    # Creazione di un nuovo DataFrame dai risultati delle somme
    # df_grouped_sums = pd.DataFrame(group_sums)
    
    # # tutte queste sono cumulate, quindi stacked area
    # for column in df_grouped_sums.columns:
    #     fig.add_trace(go.Scatter(
    #         x = x, y = df_grouped_sums[column], mode='lines',
    #                 name = column,
    #                 line_shape = 'hv', #'spline',
    #                 textposition='top center',stackgroup='one'))
    
    # # Inserisco il profilo di immissione: 
    # fig.add_trace(go.Scatter(
    #         x = x, y = df['immission_profile'], mode='lines',
    #                 name = 'immission_profile',
    #                 line_shape = 'hv', #'spline',
    #                 textposition='top center'))

    # fig.update_yaxes(title_text = "Power (kW)")          # verificare se è effettivamente la potenza: 
    # fig.update_xaxes(title_text = 'Tempo (HH:MM)', dtick = 1000*60*30, range = [x[0], x[96]])
    # fig.update_layout(title= 'GA Optimization 2', xaxis_tickformat = '%H:%M', plot_bgcolor='white', legend = dict(orientation='h',yanchor="top", y = -0.4, xanchor="left", x=0.01)) #barmode='stack') # si setta la modalità di rappresentazione del grafico a barre, in questo caso avranno una visualizzazione di tipo "stack", ovvero impilate le une sulle altre
    # #fig.show()

    # Print con aggregati: 
    # fig = go.Figure()
     
    # df = pd.DataFrame({
    #     'autonsumption_profile': autoconsumption_profile,
    #     'pv_profile': pv_profile
    # }, index=np.arange(num_intervals))
    # # Inserisco i profili di produzione: 
    # fig.add_trace(go.Scatter(
    #         x = x, y = df['pv_profile'], mode='lines',
    #                 name = 'pv_profile',
    #                 line_shape = 'hv', #'spline',
    #                 textposition='top center'))
    
    # fig.add_trace(go.Scatter(
    #     x = x, y = df['autonsumption_profile'], mode='lines',
    #             name = 'autonsumption_profile',
    #             line_shape = 'hv', #'spline',
    #             textposition='top center',stackgroup='one'))

    # # Inserisco il profilo dei dispositivi: 
    # for column in df_grouped_sums.columns:
    #     fig.add_trace(go.Scatter(
    #         x = x, y = df_grouped_sums[column], mode='lines',
    #                 name = column,
    #                 line_shape = 'hv', #'spline',
    #                 textposition='top center',stackgroup='one'))
    
    # fig.update_yaxes(title_text = "Power (kW)")          # verificare se è effettivamente la potenza: 
    # fig.update_xaxes(title_text = 'Tempo (HH:MM)', dtick = 1000*60*30, range = [x[0], x[96]])
    # fig.update_layout(title= 'GA Optimization 2', xaxis_tickformat = '%H:%M', plot_bgcolor='white', legend = dict(orientation='h',yanchor="top", y = -0.4, xanchor="left", x=0.01)) #barmode='stack') # si setta la modalità di rappresentazione del grafico a barre, in questo caso avranno una visualizzazione di tipo "stack", ovvero impilate le une sulle altre
    # fig.update_layout(autosize=False,width=1400,height=800)
    # html_str = fig.to_html(full_html=False, include_plotlyjs='cdn')
    
    # #fig.show()

###################################################################################################################################################

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
    fig.update_layout(title= f'GA Optimization Device for {n_device} devices', plot_bgcolor='white', legend = dict(orientation='h',yanchor="top", y = -0.4, xanchor="left", x=0.01)) #barmode='stack') # si setta la modalità di rappresentazione del grafico a barre, in questo caso avranno una visualizzazione di tipo "stack", ovvero impilate le une sulle altre

###################################################################################################################################################

def intervallo_funzionamento(start,end,n):
    giorno = np.zeros(n,int)
    for i in range(start,end):
        giorno[i]=1 
    return giorno

###################################################################################################################################################

# Funzione per generare un profilo di consumo casuale di lunghezza specificata
def generate_random_consumption_profile(length):
    return np.random.rand(length)

###################################################################################################################################################

def first_nonzero_index(arr):
    """funzione per trovare l'indice del primo elemento non nullo di un array

    Args:
        arr (array): array di numpy

    Returns:
        int: indice del primo elemento non nullo, 0 se l'array è vuoto
    """
    nonzero_indices = np.nonzero(arr)[0]
    return nonzero_indices[0] if nonzero_indices.size > 0 else 0

###################################################################################################################################################

# Function to calculate total energy cost for a device on/off schedule
# Precedente
# def calculate_device_cost(device_schedule, immission_profile, max_power_contract, energy_cost_per_hour):
    
    # total_energy_cost = 0
    # total_energy_consumption = 0
    # total_energy_shared      = 0
    # incentivo = 0.11
    # total_cost = 0
    
    # num_intervals = len(device_schedule[0])
    # for t in range(num_intervals):
    #     total_power = sum(device[t] for device in device_schedule)
        
                
    #     for device in device_schedule:
    #         # Verifica del vincolo di potenza contrattuale massima
    #         if device[t] > max_power_contract:
    #             return float('inf')  # Penalità per violazione del vincolo
        
    #     total_energy_cost = total_power*energy_cost_per_hour[t]
    #     total_energy_shared = min(total_power, immission_profile[t])*incentivo
            
    #     # # Se supero energia immessa:
    #     # if total_power > immission_profile[t]:
    #     #     total_energy_cost += total_power

    #     # Calcolo del costo considerando l'immissione nel profilo
    #     total_cost += total_energy_cost - total_energy_shared
    # return total_cost

###################################################################################################################################################

# Post rev. NO check
# def calculate_device_cost(device_schedule, immission_profile, energy_cost_per_hour):
#     device_schedule = np.array(device_schedule)
#     total_power = device_schedule.sum(axis=0)

#     total_energy_cost = total_power * np.array(energy_cost_per_hour)
#     total_energy_shared = np.minimum(total_power, immission_profile) * 0.11
#     total_cost = total_energy_cost.sum() - total_energy_shared.sum()   
#     return total_cost

###################################################################################################################################################

def calculate_device_cost(device_schedule, immission_profile, energy_cost_per_hour):
    
    # device_schedule = np.asarray(device_schedule)
    # total_power = device_schedule.sum(axis=0)
    total_power = np.sum(device_schedule, axis=0)
    total_energy_cost = np.dot(total_power, energy_cost_per_hour)
    
    total_energy_shared = np.dot(np.minimum(total_power, immission_profile), 0.11)
    
    total_cost = total_energy_cost.sum() - total_energy_shared.sum()
    return total_cost

# Objective function to calculate total energy cost for all solutions
# def objective_function(solutions):
#     total_costs = []
#     for solution in solutions:
#         total_cost = np.sum(calculate_device_cost(solution, consumption_profiles))
#         total_costs.append(total_cost)
#     return total_costs

###################################################################################################################################################

# Funzione per generare una soluzione casuale rispettando il profilo di consumo di ciascun dispositivo
# PRE rev. 
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

###################################################################################################################################################

# def generate_random_solution(num_intervals, consumption_profiles, allowed_intervals, possible_starts):
#     solution = np.zeros((len(consumption_profiles), num_intervals))
#     profile_lengths = np.array([len(profile) for profile in consumption_profiles])
    
#     for i, profile in enumerate(consumption_profiles):
#         start_index = np.random.choice(possible_starts)
#         solution[i, start_index:start_index + profile_lengths[i]] = profile
    
#     return solution

###################################################################################################################################################

# #Mutation function to randomly modify an existing solution
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

###################################################################################################################################################

# def mutate_solution(solution, mutation_rate, consumption_profiles, allowed_intervals, num_intervals, possible_starts):
#     profile_lengths = np.array([len(profile) for profile in consumption_profiles])
    
#     for i, device_schedule in enumerate(solution):
#         if np.random.rand() < mutation_rate:
#             profile = consumption_profiles[i]
#             new_start_index = np.random.choice(possible_starts)
#             solution[i, :] = 0
#             solution[i, new_start_index:new_start_index + profile_lengths[i]] = profile
    
#     return solution

###################################################################################################################################################

# PRE 
#Algoritmo genetico
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

###################################################################################################################################################

# POST using Concurrency: too slow

# from concurrent.futures import ProcessPoolExecutor
# def calculate_fitness(solution, immission_profile, energy_cost_per_hour):
#     return calculate_device_cost(solution, immission_profile, energy_cost_per_hour)

###################################################################################################################################################

# def fitness_wrapper(args):
#     solution, immission_profile, energy_cost_per_hour = args
#     return calculate_fitness(solution, immission_profile, energy_cost_per_hour)

###################################################################################################################################################

# # # # POST rev No Check
# def genetic_algorithm(num_intervals, population_size, generations, mutation_rate, consumption_profiles, immission_profile, max_power_contract, energy_cost_per_hour, allowed_intervals):
#     population = [generate_random_solution(num_intervals, consumption_profiles, allowed_intervals, immission_profile) for _ in range(population_size)]
    
#     best_solution_gen_value = []
    
#     with ProcessPoolExecutor() as executor:
#         for generation in range(generations):
#             fitness_values = list(executor.map(fitness_wrapper, [(sol, immission_profile, energy_cost_per_hour) for sol in population]))
            
#             parents = [population[i] for i in np.argsort(fitness_values)[:int(population_size / 2)]]
            
#             children = []
#             for _ in range(population_size - len(parents)):
#                 parent1, parent2 = random.sample(parents, 2)
#                 crossover_point = np.random.randint(num_intervals)
#                 if len(parent1) != len(parent2):
#                     parent1, parent2 = np.broadcast_to(parent1, (len(parent2), len(parent2[0]))), np.broadcast_to(parent2, (len(parent1), len(parent1[0])))
#                 child = np.concatenate((parent1[:crossover_point], parent2[crossover_point:]), axis=0)
#                 children.append(child)
            
#             population = parents + children
#             population = parents + children
#             population = [mutate_solution(solution, mutation_rate, consumption_profiles, allowed_intervals, num_intervals, immission_profile) for solution in population]
            
#             best_solution = min(population, key=lambda sol: fitness_wrapper((sol, immission_profile, energy_cost_per_hour)))
#             population[0] = best_solution
            
#             if generation % 5 == 0:
#                 for i in range(len(population)):
#                     if np.random.rand() < 0.1:
#                         population[i] = generate_random_solution(num_intervals, consumption_profiles, allowed_intervals, immission_profile)
            
#             best_solution_gen_value.append(min(fitness_values))
    
#     fitness_values = [fitness_wrapper((sol, immission_profile, energy_cost_per_hour)) for sol in population]
    
#     best_solution_index = np.argmin(fitness_values)
#     best_solution = population[best_solution_index]
#     best_cost = fitness_values[best_solution_index]
    
#     return best_solution, best_cost, best_solution_gen_value

###################################################################################################################################################



###################################################################################################################################################



###################################################################################################################################################



###################################################################################################################################################