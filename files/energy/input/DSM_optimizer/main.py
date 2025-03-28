# Import Librerie
import yaml
import pandas as pd
from files.energy.input.DSM_optimizer.func.ott import ottimizzazione
import numpy as np 
from simple_colors import *

def crea_lista_consumi(directory, n_user):
    
    # Caricamento dataframe profili di consumo 
    df  =   pd.read_csv(directory + 'appliance_load_profile.csv')
    
    # Filtra i valori positivi di consumo per le colonne 'washing_machine_1' e 'dish_washer_1'
    df_washing_machine = df['dish_washer'][df['dish_washer'] > 0].tolist()
    df_dish_washer = df['washing_machine'][df['washing_machine'] > 0].tolist()

    # Moltiplica i profili di consumo per la potenza in funzione della tipologia di utenza:
    lista_consumi = [df_washing_machine, df_dish_washer] * n_user

    return lista_consumi   

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


def ott_year(df_immission, n_devices, create_plot = True, show_plot = True):
    
    freq = '15min'
    config = yaml.safe_load(open("config.yml", 'r'))
    directory = config["foldername_DSM_optimizer_data"]
    
    # Ora dobbiamo fare ottimizzazione per ognuno dei 36 giorni che abbiamo, bisogna fare anche la media sull'immissione: 
    output_dictionary = {}
    num_intervals = 96
    consumption_profiles = crea_lista_consumi(directory, n_devices)
    
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

