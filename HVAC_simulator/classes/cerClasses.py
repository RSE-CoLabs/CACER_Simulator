import yaml
from simple_colors import blue, green, red
from tqdm.auto import tqdm

from HVAC_simulator.classes.heatPump import HeatingModeHeatPump, CoolingModeHeatPump, HeatPumpAuxiliaries
from HVAC_simulator.classes.buildingModel import BuildingModel
from HVAC_simulator.functions.io import read_settings

#############################################################################################################################################

class Cacer:
      
    def __init__(self, config_directory):

        print(blue(f"Creating user class for thermal load simulation:\n", ["bold", "underlined"]))

        hp_users = []
        config = yaml.safe_load(open("config.yml", 'r'))
        registry_user_types_yaml_filename = config['filename_registry_user_types_yml']
        registry_user_types = yaml.safe_load(open(registry_user_types_yaml_filename, 'r'))

        self.cacer_type=config['type_of_cacer']
        self.simulation_interval=config['delta_t']
        cacer_users_registry=list(registry_user_types.keys())

        for user_type in cacer_users_registry:
            print(f"User type:", f"{blue(user_type)}")
            if registry_user_types[user_type]['heat_load'] == True:
                hp_users.append(HpUserConfig(registry_user_types[user_type], user_type, self.simulation_interval))
                print(f"- Load simulation activated ->", green(f"Class created!\n"))
            else:
                print(f"- Load simulation not activated ->", red(f"Skipped!\n"))
        
        self.hp_users_type = hp_users

#############################################################################################################################################

class HpUserConfig:

    def __init__(self,  user_properties, user_type, simulation_interval):
        
        print(f"- Creating HpUserConfig...")

        self.user_name = user_type
        self.user_type = user_properties['type'] 
        # self.user_numbers = user_properties['num'] # number of users of this type, but for now we set it to 1 for all user types
        self.user_numbers = 1 
        self.p_contr = user_properties['power_range']
        self.condominium=user_properties['condominium']
        self.location = user_properties['location']
        self.denomination = user_properties['denomination']
        self.hvac_type = user_properties['hvac_type']
        self.th_comfort_heating = user_properties['th_comfort_heating']
        self.th_comfort_cooling = user_properties['th_comfort_cooling']

        if self.hvac_type == 'autonomous':
            hp_config_file='heat_pump_autonomous.yml'
        
        else:
            hp_config_file='heat_pump_centralized.yml'
        
        config = yaml.safe_load(open("config.yml", 'r'))
        registry_users_types = yaml.safe_load(open(config["filename_registry_user_types_yml"], 'r'))
        registry_users = yaml.safe_load(open(config["filename_registry_users_yml"], 'r'))

        registry_users_types.keys()
        user_type_list = [key for key in registry_users_types.keys() if registry_users_types[key]['heat_load'] == True]

        dict_users = {}
        for u in user_type_list:
            users_list = [key for key in registry_users.keys() if registry_users[key]['user_type'] == u]
            dict_users[u] = users_list

        user_list = []

        ######################################################
        # ????
        ######################################################

        # La seguente porzione di codice è da rivedere...
        for i in range(user_properties['num']):

            if i==1:
                building_file='building_floor_east.yml'
            
            elif i==2:
                building_file='building_floor_west.yml'
            
            elif i==self.user_numbers:
                building_file='building_roof_east.yml'
            
            elif i==self.user_numbers + 1:
                building_file='building_roof_west.yml'

            elif i % 2 != 0:
                building_file='building_east.yml'
            
            else: 
                building_file='building_west.yml'

            # ???
            user_list.append(User(building_file,
                                hp_config_file, 
                                # dict_users[user_type][i], # si usa l'id dello user
                                user_type, # si usa lo user type (es. household_small) come nome dello user
                                simulation_interval
                                )
                            )
            
        print(f"  HpUserConfig created successfully!\n")
        
        self.users = user_list

#############################################################################################################################################

class User():
    def __init__(self, building_file, hp_config_file, name, simulation_interval):
        
        self.name = name

        config = yaml.safe_load(open("config.yml", 'r'))

        # Load building properties
        filename_building_properties = config['building_properties_folder'] + '\\' + building_file
        building_properties = yaml.safe_load(open(filename_building_properties, 'r'))
        self.building = BuildingModel(building_properties, simulation_interval)  
        
        # Load heat pump properties
        config = yaml.safe_load(open("config.yml", 'r'))
        filename_hp_properties = config['hp_properties_folder'] + '\\' + hp_config_file
        hp_properties = yaml.safe_load(open(filename_hp_properties, 'r'))

        # Load heat pump modes
        self.hp_heating = HeatingModeHeatPump(hp_properties) # Heating mode
        self.hp_cooling = CoolingModeHeatPump(hp_properties) # Cooling mode
        self.hp_aux = HeatPumpAuxiliaries(hp_properties) # Heat pump auxiliaries














