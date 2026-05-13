import pandapower as pp
import pandapower.plotting as plot
import pandapower.networks as nw
import plotly.express as px
import plotly.graph_objs as go
import plotly.io as pio
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize
from matplotlib.colors import rgb2hex
import folium
from folium.plugins import HeatMap
import branca.colormap as bcm
import math
import pandas as pd
import os
import yaml
from ruamel.yaml import YAML
import contextlib
import ipywidgets as widgets
from IPython.display import display, clear_output

from src.Functions_General import clear_folder_content

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# remove all images from previous simulations
def delete_images():
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    clear_folder_content(folder)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# remove all saved network from previous simulations
def delete_network():
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["folder_network"]
    clear_folder_content(folder)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def create_network(name, f_hz, flag_gen = False):

    delete_images()

    # initializing distribution network
    network = pp.create_empty_network(name, f_hz)

    create_buses(network)

    create_ext_grid(network)

    create_trafos(network)

    create_lines(network)

    create_switch(network)

    create_loads(network, relax_flag = False)

    if flag_gen:
        create_static_gens(network)

    # create_gens(network)

    # create_storages(network)

    print("\nAll components created!\n")

    network_to_save = pp.copy.deepcopy(network)
    save_network(network_to_save, name)

    return network

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# getting bus data from excel (those are the nodes of the network)
def create_buses(network):
  config = yaml.safe_load(open("config.yml", 'r'))
  filename = config["filename_data"]
  bus_data = pd.read_excel(filename, sheet_name = "bus")

  # drop all previous elements
  network.bus.drop(network.bus.index, inplace=True)

  #adding bus to the network
  for k in range(len(bus_data)):

      if math.isnan(bus_data["x"][k]) and math.isnan(bus_data["y"][k]):
        geodata = None
      else:
        long = bus_data["y"][k]
        lat = bus_data["x"][k]
        geodata = (long, lat)

      pp.create_bus(net = network, # distribution network object
                    name = bus_data["name"][k], # name of the base
                    vn_kv = bus_data["base kv"][k], # grid voltage level [kV]
                    
                    geodata = geodata, # coordinates used for plotting
                    
                    min_vm_pu = bus_data["vmin"][k], # min bus voltage in p.u.
                    max_vm_pu = bus_data["vmax"][k], # max bus voltage in p.u.
                    
                    # type = bus_data["type"][k] # Type of the bus. “n” - node, “b” - busbar, “m” - muff
                    )

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# getting external grid data from excel ("slack bus")
def create_ext_grid(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    ext_grd_data = pd.read_excel(filename, sheet_name = "ext_grid")

    # drop all previous elements
    network.ext_grid.drop(network.ext_grid.index, inplace=True)

    #adding external grid to the network
    for k in range(len(ext_grd_data)):

        pp.create_ext_grid   (net = network, # distribution network object
                            name = ext_grd_data["name"][k], # name of the external grid
                            
                            bus = network.bus[network.bus["name"]==ext_grd_data["bus"][k]].index[0], # bus where the slack is connected
                            
                            # vm_pu = ext_grd_data["voltage"][k] # voltage at the slack node in p.u.
                            
                            # all the next parameters are useful for a short circuit calculation

                            # s_sc_max_mva = ext_grd_data["s_sc_max_mva"][k] # maximal short circuit apparent power to calculate internal impedance of ext_grid for short circuit calculations
                            # s_sc_min_mva = ext_grd_data["s_sc_min_mva"][k] # minimal short circuit apparent power to calculate internal impedance of ext_grid for short circuit calculations	
                            # rx_max = ext_grd_data["rx_max"][k] # maximal R/X-ratio to calculate internal impedance of ext_grid for short circuit calculations	
                            # rx_min = ext_grd_data["rx_min"][k] # minimal R/X-ratio to calculate internal impedance of ext_grid for short circuit calculations
                            )

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

#getting transformer data from excel
def create_trafos(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    transf_data = pd.read_excel(filename, sheet_name = "branch(trafo)")

    # drop all previous elements
    network.trafo.drop(network.trafo.index, inplace=True)

    #adding transformer to network
    for k in range(len(transf_data)):

        # print ("Trafo number: " + str(k+1)+ "\n")

        # indexes of the buses to which the transformer is connected
        FromBus = network.bus[
            network.bus["name"]==transf_data["name from"][k]
            ].index[0]
        # print ("From bus: " + str(FromBus) + "\n")

        ToBus = network.bus[
            network.bus["name"]==transf_data["name to"][k]
            ].index[0]
        # print ("To bus: " + str(ToBus) + "\n")

        # pandapower function for creating a bus from parameters
        pp.create_transformer_from_parameters(net = network, # distribution network object
                                            name = transf_data["name"][k], # name of the trasformer
                                            
                                            hv_bus = FromBus, # the bus on the high - voltage side on which the trasformer will be connected (FromBus)
                                            lv_bus = ToBus, # the bus on the low - voltage side on which the trasformer will be connected (ToBus)
                                            
                                            sn_mva = transf_data["Snom [MVA]"][k], # rated apparent power (S = radq(P^2 + Q^2))
                                            
                                            max_loading_percent = 100.0, # maximum current loading (only needed for OPF)
                                            
                                            vn_hv_kv = network.bus["vn_kv"][FromBus], # rated voltage on high voltage side [kV]
                                            vn_lv_kv = network.bus["vn_kv"][ToBus], # rated voltage on low voltage side [kV]
                                            
                                            vk_percent = transf_data["short circuit [%]"][k], # relative short-circuit voltage (Irated_trafo_side / Isc_max_trafo_side)

                                            vkr_percent = transf_data["short circuit [%]"][k] * transf_data["short circuit power factor"][k], # real part of relative short-circuit voltage (sc_voltage_perc * sc_pow_factor)

                                            pfe_kw = transf_data["pfe_kw"][k], # iron losses [kW]
                                            
                                            i0_percent = transf_data["i0_percent"][k], # open loop losses in percent of rated current (I0)

                                            # all the next parameters are not imported from external file

                                            tap_side = "lv", # the side where is positioned the tap changer (to change the ratios in distrinct steps)
                                            
                                            # tap_pos = transf_data["tap_pos [%]"][k],
                                            
                                            # tap_neutral = 0, # tap position where the transformer ratio is equal to the ratio of the rated voltages
                                            
                                            # tap_min = - (math.ceil(transf_data["num_tap_pos"][k] / 2 - 1)) * transf_data["tap_step_percent [%]"][k],

                                            # tap_max = (math.ceil(transf_data["num_tap_pos"][k] / 2 - 1)) * transf_data["tap_step_percent [%]"][k],
                                        
                                            # tap_step_percent = transf_data["tap_step_percent [%]"][k], # tap step size for voltage magnitude in percent

                                            ) 

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# getting line data from excel
def create_lines(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    line_data = pd.read_excel(filename, sheet_name = "branch(line)")

    # drop all previous elements
    network.line.drop(network.line.index, inplace=True)

    # adding lines to the network
    for k in range(len(line_data)):

        # indexes of the buses to which the line is connected
        From_Bus = network.bus[
            network.bus["name"]==line_data["name from"][k]
            ].index[0]
        To_Bus = network.bus[
            network.bus["name"]==line_data["name to"][k]
            ].index[0]

        # creating lines in the network using the data read from excel
        pp.create_line_from_parameters(net = network, # distribution network object
                                    name = line_data["name"][k], # name of the line
                                    
                                    from_bus = From_Bus, # ID of the bus on one side which the line will be connected with
                                    to_bus = To_Bus, # ID of the bus on the other side which the line will be connected with
                                    
                                    length_km = 1.0, # length of the line in km (this need to be change in future!)
                                    
                                    r_ohm_per_km = line_data["r [ohm]"][k], # line resistance in ohm per km
                                    x_ohm_per_km = line_data["x [ohm]"][k], # line reactance in ohm per km
                                    
                                    c_nf_per_km = 0.0, # line capacitance in nano Farad per km
                                    
                                    max_i_ka = line_data["rate [kA]"][k],
                                    
                                    max_loading_percent = 60
                                    
                                    ) # maximum thermal current in kilo Ampere

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# getting load data from excel
# the load buses are PQ buses, so we need to specify active and reactive power
def create_switch(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    switch_data = pd.read_excel(filename , sheet_name = "switch")

    # drop all previous elements
    network.switch.drop(network.switch.index, inplace=True)

    # adding loads to the network
    # we observe that for loads is applied the consumer convection
    for k in range(len(switch_data)):

        # indexes of the bus to which the load is connected
        Bus = network.bus[
            network.bus["name"]==switch_data["bus name"][k]
            ].index[0]

        # if switch_data["et"][k] == 'b': # bus
        #     element = network.bus[
        #         network.bus["name"]==switch_data["element"][k]
        #         ].index[0]
        # elif switch_data["et"][k] == 't': # trafo
        #     element = network.trafo[
        #         network.trafo["name"]==switch_data["element"][k]
        #         ].index[0]
        # else:
        #     element = network.line[
        #         network.line["name"]==switch_data["element"][k]
        #         ].index[0] # line

        element = network.bus[
                network.bus["name"]==switch_data["element"][k]
                ].index[0]

        # creating loads inside the network using the read data from excel
        pp.create_switch( net = network, # distribution network object
                        name = switch_data["name"][k], # name of the switch
                        
                        bus = Bus, # bus where is connected the switch
                        element = element, # index of the element: bus id if et == “b” (bus - bus switch), line id if et == “l” (bus-line switch), trafo id if et == “t” (bus-trafo switch)
                        
                        # et = switch_data["et"][k], # "b"
                        et = 'b',

                        # closed = True, # switch position: False = open, True = closed
                        closed = switch_data["stato"][k],

                        # type = "DS" # indicates the type of switch: “LS” = Load Switch, “CB” = Circuit Breaker, “LBS” = Load Break Switch or “DS” = Disconnecting Switch
                        )

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# getting load data from excel
# the load buses are PQ buses, so we need to specify active and reactive power
def create_loads(network, relax_flag = False):

    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    load_data = pd.read_excel(filename , sheet_name = "load")

    # drop all previous elements
    network.load.drop(network.load.index, inplace=True)

    # adding loads to the network
    # we observe that for loads is applied the consumer convection
    for k in range(len(load_data)):

        # indexes of the bus to which the load is connected
        Bus = network.bus[
            network.bus["name"]==load_data["bus name"][k]
            ].index[0]
        
        power_factor = load_data["power factor"][k]

        if power_factor == "-":
            power_factor = 1

        # creating loads inside the network using the read data from excel
        pp.create_load( net = network, # distribution network object
                        name = load_data["name"][k], # name of the load
                        
                        bus = Bus, # bus where is connected the load
                        
                        p_mw = load_data["p_mw"][k], # real power of the load (postive value -> load; negative value -> generation)
                        q_mvar = load_data["p_mw"][k] * math.tan (math.acos(power_factor)), # reactive power of the load (real power * power factor)
                        
                        )


    ############################################################################################################################################################################

    if relax_flag:

        network.poly_cost.drop(index = network.poly_cost.index, inplace = True) # we delete all the polynomial cost function parameters

        costLoadRelaxation = 10000     # we fix an high cost for the use of this loads €/MWh

        # creating flexible part for load relaxation (100% to take into account 0% of DSM previously defined)
        for k in range(len(load_data)):

            # index of the bus to which the load is connected
            indexBus = network.load["bus"][k]

            # index of the baseline load to which this flexibility is connetced
            indexLoad = network.load.index[k]

            # we observe that for the loads it is applied the consumer convection and so a negative load means a load generator
            indexFlexLoad = pp.create_load(net = network,
                                                name = "(fake_)" + load_data["name"][k],
                                                index_load = indexLoad,
                                                bus = indexBus,
                                                p_mw = 0.0,
                                                q_mvar = 0.0,
                                                max_p_mw = 0.0, # Maximum active power load - necessary for controllable loads in for OPF
                                                min_p_mw = -load_data["p_mw"][k], # Minimum active power load - necessary for controllable loads in for OPF
                                                max_q_mvar = 0.0, min_q_mvar = 0.0,
                                                controllable = True)

            # adding cost to load relaxation (useful to relax constraints in order to have an always converging optimization) for each users and create a polynomial costs function
            pp.create_poly_cost(net = network,
                                        et = "load", # (string) - Type of element [“gen”, “sgen”, “ext_grid”, “load”, “dcline”, “storage”] are possible
                                        element = indexFlexLoad, # (int) - ID of the element in the respective element table
                                        cp1_eur_per_mw = -costLoadRelaxation) # cost of the load relaxation

############################################################################################################################################################################

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# # getting gen data from excel
# the load buses are PV buses, so we need to specify active power and voltage
def create_static_gens(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    gen_data = pd.read_excel(filename, sheet_name = "gen")

    # drop all previous elements
    network.gen.drop(network.gen.index, inplace=True)

    # adding gens to the network
    for k in range(len(gen_data)):

        # indexes of the bus to which the load is connected
        Bus = network.bus[
            network.bus["name"]==gen_data["bus name"][k]
            ].index[0]

        # creating gens inside the network using the read data from excel
        # we observe that for generators is applied the generator convection
        pp.create_sgen(network,
                    Bus, # The bus id to which the generator is connected
                    
                    p_mw = gen_data["p_mw"][k], # The real power of the generator (positive for generation!)
                    
                    # vm_pu = 1.0, # The voltage set point of the generator
                    
                    # sn_mva = gen_data["sn_mva"][k], # Nominal power of the generator
                    
                    name = gen_data["name"][k],
                    
                    # scaling = 1.0, # scaling factor which for the active power of the generator (P_gen = p_mw * scaling)
                    
                    # max_q_mvar = 0, # Maximum reactive power injection - necessary for OPF
                    # min_q_mvar = gen_data["p_mw"][k] * math.tan (math.acos(gen_data["power factor"][k])), # Minimum reactive power injection - necessary for OPF
                    
                    # min_p_mw = 0, # Minimum active power injection - necessary for OPF
                    # max_p_mw = gen_data["sn_mva"][k], # Maximum active power injection - necessary for OPF

                    )

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# # getting gen data from excel
# the load buses are PV buses, so we need to specify active power and voltage
def create_gens(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    gen_data = pd.read_excel(filename, sheet_name = "gen")

    # drop all previous elements
    network.gen.drop(network.gen.index, inplace=True)

    # adding gens to the network
    for k in range(len(gen_data)):

        # indexes of the bus to which the load is connected
        Bus = network.bus[
            network.bus["name"]==gen_data["bus name"][k]
            ].index[0]

        # creating gens inside the network using the read data from excel
        # we observe that for generators is applied the generator convection
        pp.create_gen(network,
                    Bus, # The bus id to which the generator is connected
                    
                    p_mw = gen_data["p_mw"][k], # The real power of the generator (positive for generation!)
                    vm_pu = 1.0, # The voltage set point of the generator
                    
                    sn_mva = gen_data["sn_mva"][k], # Nominal power of the generator
                    
                    name = gen_data["name"][k],
                    
                    scaling = 1.0, # scaling factor which for the active power of the generator (P_gen = p_mw * scaling)
                    
                    max_q_mvar = 0, # Maximum reactive power injection - necessary for OPF
                    min_q_mvar = gen_data["p_mw"][k] * math.tan (math.acos(gen_data["power factor"][k])), # Minimum reactive power injection - necessary for OPF
                    
                    min_p_mw = 0, # Minimum active power injection - necessary for OPF
                    max_p_mw = gen_data["sn_mva"][k], # Maximum active power injection - necessary for OPF
                    
                    #   controllable=nan, # Whether this generator is controllable by the optimal powerflow
                    #   vn_kv=nan, # Rated voltage of the generator for short-circuit calculation
                    #   xdss_pu=nan, # Subtransient generator reactance for short-circuit calculation
                    #   rdss_pu=nan, # Subtransient generator resistance for short-circuit calculation
                    #   cos_phi=nan, # Rated cosine phi of the generator for short-circuit calculation
                    #   in_service=True # True for in_service or False for out of service
                    )

    # print(network.gen)
    # print("")
    # print("Gens created!")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_gens_in_net(network, title):
        pio.renderers.default = 'browser'

        fig = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2) # we save the plot object of the network as a fig object in way to manipulate it

        index = network.gen.bus # we set the bus of the network linked to a generator

        # we add the trace with evidenced flexible load
        fig.add_trace(go.Scatter(x=network.bus_geodata.loc[index, 'x'], # x position of buses inside the network
                                y=network.bus_geodata.loc[index, 'y'], # y position of buses inside the network
                                name="gens_buses",
                                # text = ,
                                # textposition = "top center",
                                mode='markers',
                                marker = dict(color = 'orange',
                                        line = dict(color = 'orange'),
                                        size = 14,
                                        symbol = "square",
                                        )
                                )
                        )

        config = yaml.safe_load(open("config.yml", 'r'))
        folder = config["forldername_graphs_PF_analysis"]
        output_file = folder + title
        fig.write_html(output_file + ".html") # si salva in formato .html

        fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# # getting storage data from excel
def create_storages(network):
    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    storage_data = pd.read_excel(filename, sheet_name = "storage")

    # drop all previous elements
    network.storage.drop(network.storage.index, inplace=True)

    # adding storages to the network
    for k in range(len(storage_data)):

        # indexes of the bus to which the storage is connected
        Bus = network.bus[
            network.bus["name"]==storage_data["bus name"][k]
            ].index[0]

        # creating storages inside the network using the read data from excel
        # we observe that for storages is applied the consumer convection
        pp.create_storage(network,
                                Bus, # The bus id to which the storage is connected
                                p_mw = storage_data["p_mw"][k], # The momentary active power of the storage (positive for charging, negative for discharging)
                                max_e_mwh = storage_data["max_e_mwh"][k], # The maximum energy content of the storage (maximum charge level)
                                q_mvar = 0, # The reactive power of the storage
                                sn_mva = storage_data["sn_mva"][k], # Nominal power of the storage [MW]
                                soc_percent = storage_data["soc_percent"][k], # The state of charge of the storage
                                min_e_mwh = 0.0, # The minimum energy content of the storage (minimum charge level)
                                name = storage_data["name"][k], # The name for this storage
                                scaling = 1.0, # An optional scaling factor to be set customly
                                in_service = True, # True for in_service or False for out of service
                                max_p_mw = 0, # Maximum active power injection - necessary for a controllable storage in OPF
                                min_p_mw = storage_data["sn_mva"][k], # Minimum active power injection - necessary for a controllable storage in OPF
                                max_q_mvar = storage_data["p_mw"][k] * math.tan (math.acos(storage_data["power factor"][k])), # Maximum reactive power injection - necessary for a controllable storage in OPF
                                min_q_mvar = 0, # Minimum reactive power injection - necessary for a controllable storage in OPF
                                #   controllable=nan # Whether this storage is controllable by the optimal powerflow
                                )

    # print(network.storage)
    # print("")
    # print("Storages created!")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_storages_in_net(network, title):
        pio.renderers.default = 'browser'

        fig = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2) # we save the plot object of the network as a fig object in way to manipulate it

        index = network.storage.bus # we set the bus of the network linked to a generator

        # we add the trace with evidenced flexible load
        fig.add_trace(go.Scatter(x=network.bus_geodata.loc[index, 'x'], # x position of buses inside the network
                                y=network.bus_geodata.loc[index, 'y'], # y position of buses inside the network
                                name="storages_buses",
                                # text = ,
                                # textposition = "top center",
                                mode='markers',
                                marker = dict(color = 'pink',
                                        line = dict(color = 'pink'),
                                              size = 14,
                                              symbol = "square",
                                                     )
                                )
                        )

        config = yaml.safe_load(open("config.yml", 'r'))
        folder = config["forldername_graphs_PF_analysis"]
        output_file = folder + title
        fig.write_html(output_file + ".html") # si salva in formato .html

        fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# we can also save the network
def save_network(network_to_save, name_net):

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["folder_network"]

    path = folder + name_net + ".p"
    pp.to_pickle(network_to_save, path)  # absolute path

    print (network_to_save)
    # print(" ")
    # print("Network saved!")

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# we can also save the network
def load_network(name_net):

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["folder_network"]

    # recall the network from picle file
    path = folder + name_net + ".p"
    network_loaded = pp.from_pickle(path) #relative path

    print (network_loaded)
    # print(" ")
    # print("Network loaded!")

    return network_loaded

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_network(network, title):

    fig = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2); # for other informations use this link: https://pandapower.readthedocs.io/en/v2.0.0/plotting/plotly/built-in_plots.html
    # fig = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2, on_map = True, projection='epsg:6875'); # plot map in background (INCOMPLETED!)

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    output_file = folder + title
    fig.write_html(output_file + ".html") # si salva in formato .html

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_network_vlevel(network, title):

    fig = plot.plotly.vlevel_plotly(network, aspectratio=(2, 1), figsize=2); # for other informations use this link: https://pandapower.readthedocs.io/en/v2.0.0/plotting/plotly/built-in_plots.html

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    output_file = folder + title
    fig.write_html(output_file + ".html") # si salva in formato .html

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_loads_in_net(network, title):
        pio.renderers.default = 'browser'

        fig = plot.simple_plotly(network, aspectratio=(2, 1), figsize=2) # we save the plot object of the network as a fig object in way to manipulate it

        index = network.load.bus # we set the bus of the network linked to a generator

        # we add the trace with evidenced flexible load
        fig.add_trace(go.Scatter(x=network.bus_geodata.loc[index, 'x'], # x position of buses inside the network
                                y=network.bus_geodata.loc[index, 'y'], # y position of buses inside the network
                                name="loads_buses",
                                # text = ,
                                # textposition = "top center",
                                mode='markers',
                                marker = dict(color = 'yellowgreen',
                                        line = dict(color = 'yellowgreen'),
                                        size = 14,
                                        symbol = "square",
                                        )
                                )
                        )

        config = yaml.safe_load(open("config.yml", 'r'))
        folder = config["forldername_graphs_PF_analysis"]
        output_file = folder + title
        fig.write_html(output_file + ".html") # si salva in formato .html

        fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_map(dataframe, zoom_start = 14, flag_tiles = True):

    lat_m = dataframe['x'].mean()
    lon_m = dataframe['y'].mean()

    if flag_tiles:
        # create map with tiles
        map = folium.Map(location=[lat_m, lon_m], zoom_start = zoom_start)
    else:
        # create map without tiles
        map = folium.Map(location=[lat_m, lon_m], zoom_start = zoom_start, tiles=None)

    return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_bus(map, dataframe, icon_size):
  #reporting number of waypoints
  no_waypoints = len(dataframe)

  # add markers to map
  for i in range(no_waypoints):
    coordinates = [dataframe['x'].loc[i], dataframe['y'].loc[i]]

    name = str(dataframe['name'].loc[i])

    voltage_level = dataframe['base kv'].loc[i]
    # LV
    if voltage_level < 1:
      color = 'red'
    # MV
    elif voltage_level <= 35:
      color = 'blue'
    # HV
    else:
      color = 'yellow'

    folium.Marker(coordinates, popup = name, icon=folium.Icon(color = color, icon = 'home', icon_size = icon_size)).add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_bus_colormap(map, dataframe, name_param, icon):

  #reporting number of waypoints
  no_waypoints = len(dataframe)

  values_param = dataframe[name_param]

  vmin = values_param.min()
  vmax = values_param.max()

  colormap = bcm.LinearColormap(colors=['yellow','red'], vmin=vmin, vmax=vmax)

  # add markers to map
  for i, p in zip(range(no_waypoints), values_param):
    coordinates = [dataframe['x'].loc[i], dataframe['y'].loc[i]]

    name = str(dataframe['name'].loc[i])

    folium.Marker(coordinates, popup = name, icon=folium.Icon(color = 'white', icon_color=str(colormap(p)), icon = icon)
                  ).add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_bus_colormap_circle(map, dataframe, name_param):

    #reporting number of waypoints
    no_waypoints = len(dataframe)

    values_param = dataframe[name_param]

    vmin = values_param.min()
    vmax = values_param.max()

    colormap = bcm.LinearColormap(colors=['yellow', 'red'], vmin=vmin, vmax=vmax)

    # add markers to map
    for i, p in zip(range(no_waypoints), values_param):
        coordinates = [dataframe['x'].loc[i], dataframe['y'].loc[i]]

        name = str(dataframe['name'].loc[i]) + "\n" + str(name_param) + ": " + str(round(p, 2))

        incr_p = p / vmin

        folium.CircleMarker(
            coordinates,
            radius=5,
            popup=name,
            color=colormap(p),
            fill_color=colormap(p),
            fill_opacity=1
        ).add_to(map)

    return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_bus_circle_marker(map, dataframe):

    #reporting number of waypoints
    no_waypoints = len(dataframe)

    # add markers to map
    for i in range(no_waypoints):
        coordinates = [dataframe['x'].loc[i], dataframe['y'].loc[i]]

        name = str(dataframe['name'].loc[i])

        #------------------------------------------------------------------------

        # voltage_level = dataframe['base kv'].loc[i]
        # # LV
        # if voltage_level < 1:
        #     color = 'red'
        # # MV
        # elif voltage_level <= 35:
        #     color = 'blue'
        # # HV
        # else:
        #     color = 'yellow'

        #------------------------------------------------------------------------

        user_type = dataframe['user_type'].loc[i]
        # consumer
        if user_type == 'consumer':
            color = 'green'
        # no load
        elif user_type == "no_load":
            color = 'grey'
        # ext grid
        else:
            color = 'blue'
        
        #------------------------------------------------------------------------

        folium.CircleMarker(
            coordinates,
            radius=2,
            popup=name,
            color=color,
            fill_color=color,
            fill_opacity=1
        ).add_to(map)

    return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_bus_heatmap(map, dataframe, name_param):

  #reporting number of waypoints
  no_waypoints = len(dataframe)

  data_list = []

  values_param = dataframe[name_param]

  # add markers to map
  for i in range(no_waypoints):
    data = [dataframe['x'].loc[i], dataframe['y'].loc[i], values_param[i]]

    data_list.append(data)

  HeatMap(data_list,
          # radius=30,
          # blur=20
          ).add_to(map)

  # folium.plugins.Fullscreen(position='topright').add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def v_level_bus(voltage):

    if voltage < 1:
      v_level = 'LV'
    elif voltage <= 35:
      v_level = 'MV'
    else:
      v_level = 'HV'

    return v_level

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_line(map):
  config = yaml.safe_load(open("config.yml", 'r'))
  filename = config["filename_data"]
  bus_df = pd.read_excel(filename , sheet_name = "bus")
  line_df = pd.read_excel(filename , sheet_name = "branch(line)")

  lines_num = len(line_df)

  for line in range(lines_num):

    bus_from = line_df['name from'].loc[line]
    bus_to = line_df['name to'].loc[line]

    coordinates_p1 = [float(bus_df[bus_df['name'] == bus_from]['x']), float(bus_df[bus_df['name'] == bus_from]['y'])]
    coordinates_p2 = [float(bus_df[bus_df['name'] == bus_to]['x']), float(bus_df[bus_df['name'] == bus_to]['y'])]

    coord_list = [coordinates_p1, coordinates_p2]

    name = line_df['name'].loc[line]

    v_level_bus_from = v_level_bus(int(bus_df[bus_df['name'] == bus_from]['base kv']))
    v_level_bus_to = v_level_bus(int(bus_df[bus_df['name'] == bus_to]['base kv']))

    if v_level_bus_from == v_level_bus_to == 'LV':
      color = 'red'
    elif v_level_bus_from == v_level_bus_to == 'MV':
      color = 'blue'
    else:
      color = 'yellow'

    folium.PolyLine(coord_list, color = color, weight = 2.5, opacity = 1, popup = name).add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_line_colormap(map, name_param):

  config = yaml.safe_load(open("config.yml", 'r'))
  filename = config["filename_data"]
  bus_df = pd.read_excel(filename , sheet_name = "bus")
  line_df = pd.read_excel(filename , sheet_name = "branch(line)")

  lines_num = len(line_df)

  values_param = line_df[name_param]

  vmin = values_param.min()
  vmax = values_param.max()

  colormap = bcm.LinearColormap(colors = ['yellow', 'red'], vmin = vmin, vmax = vmax)

  for line, p in zip(range(lines_num), values_param):

    bus_from = line_df['name from'].loc[line]
    bus_to = line_df['name to'].loc[line]

    coordinates_p1 = [float(bus_df[bus_df['name'] == bus_from]['x']), float(bus_df[bus_df['name'] == bus_from]['y'])]
    coordinates_p2 = [float(bus_df[bus_df['name'] == bus_to]['x']), float(bus_df[bus_df['name'] == bus_to]['y'])]

    coord_list = [coordinates_p1, coordinates_p2]

    name = str(line_df['name'].loc[line]) + "\n" + str(name_param) + ": " + str(round(p, 2))

    incr_p = p / vmin

    folium.PolyLine(coord_list, color = colormap(p), weight = 2.5, opacity = 1, popup = name).add_to(map)

    # rotation operates with movements in clockwise
    # coordinates_medium = [(float(bus_df[bus_df['name'] == bus_from]['x']) + float(bus_df[bus_df['name'] == bus_to]['x'])) / 2 , (float(bus_df[bus_df['name'] == bus_from]['y']) +  float(bus_df[bus_df['name'] == bus_to]['y'])) / 2 ]
    # alfa = math.atan()
    # folium.RegularPolygonMarker(location=coordinates_medium, color = colormap(p), fill_color=colormap(p), number_of_sides=3, radius=5, rotation = 90).add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_line_colormap_1(map, name_param):

    name_param = 'value'

    config = yaml.safe_load(open("config.yml", 'r'))
    filename = config["filename_data"]
    bus_df = pd.read_excel(filename , sheet_name = "bus")
    line_df = pd.read_excel(filename , sheet_name = "branch(line)")

    lines_num = len(line_df)

    values_param = line_df[name_param]

    # cmapR = cm.get_cmap('RdYlGn')
    cmapR = cm.get_cmap('RdYlGn_r')
    norm = Normalize(vmin=line_df['value'].min(), vmax=line_df['value'].max())

    line_df['Color'] = line_df['value'].apply(lambda r: rgb2hex(cmapR(norm(r))))

    # dstyle = df.style.background_gradient(cmap=cmapR, subset=['value'])
    # dstyle.to_html('sample.html')

    for line, p in zip(range(lines_num), values_param):

        bus_from = line_df['name from'].loc[line]
        bus_to = line_df['name to'].loc[line]

        coordinates_p1 = [float(bus_df[bus_df['name'] == bus_from]['x']), float(bus_df[bus_df['name'] == bus_from]['y'])]
        coordinates_p2 = [float(bus_df[bus_df['name'] == bus_to]['x']), float(bus_df[bus_df['name'] == bus_to]['y'])]

        coord_list = [coordinates_p1, coordinates_p2]

        name = str(line_df['name'].loc[line]) + "\n" + str(name_param) + ": " + str(round(p, 2))

        folium.PolyLine(coord_list, color = line_df['Color'].loc[line], weight = 2.5, opacity = 1, popup = name).add_to(map)

    return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_add_trafo(map):
  config = yaml.safe_load(open("config.yml", 'r'))
  filename = config["filename_data"]
  bus_df = pd.read_excel(filename , sheet_name = "bus")
  trafo_df = pd.read_excel(filename , sheet_name = "branch(trafo)")

  trafo_num = len(trafo_df)

  for trafo in range(trafo_num):

    bus_from = trafo_df['name from'].loc[trafo]
    bus_to = trafo_df['name to'].loc[trafo]

    coordinates_p1 = [float(bus_df[bus_df['name'] == bus_from]['x']), float(bus_df[bus_df['name'] == bus_from]['y'])]
    coordinates_p2 = [float(bus_df[bus_df['name'] == bus_to]['x']), float(bus_df[bus_df['name'] == bus_to]['y'])]

    coord_list = [coordinates_p1, coordinates_p2]

    name = trafo_df['name'].loc[trafo]

    v_level_bus_from = v_level_bus(int(bus_df[bus_df['name'] == bus_from]['base kv']))
    v_level_bus_to = v_level_bus(int(bus_df[bus_df['name'] == bus_to]['base kv']))

    if (v_level_bus_from == 'MV' and v_level_bus_to == 'LV') or (v_level_bus_from == 'LV' and v_level_bus_to == 'MV'):
      color = 'green'
    else:
      color = 'darkgreen'

    folium.PolyLine(coord_list, color = color, weight = 2.5, opacity = 1, popup = name).add_to(map)

  return map

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_network_with_results(network, title):

    # Suppress the plot output
    with suppress_plotly_display():
        # we plot on graph the bus voltage of buses and the line loading for each lines as a colormap
        fig = plot.plotly.pf_res_plotly(network, aspectratio=(2, 1), figsize=2);

    
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    
    output_file = folder + title
    
    fig.write_html(output_file + ".html") # si salva in formato .html
    fig.write_image(output_file + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    return fig

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# heatmap con seaborn
def heatmap_mplt_lib(values):

    values = pd.DataFrame(values)

    title = values.columns.values[0]

    values.rename(columns = {values.columns.values[0] : ''}, inplace = True)

    fig, ax = plt.subplots(figsize=(22,4))
    fig = sns.heatmap(values.transpose(copy=True), square = False, annot=False, linewidths=0, ax = ax)

    fig.set_title(label = title)

    return fig

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# heatmap con plotly
def heatmap_plotly(path, dtick, tick_size, values):

    df = pd.DataFrame(values)
    title = df.columns.values[0]

    df.rename(columns = {df.columns.values[0] : ''}, inplace = True)

    fig = px.imshow(df.transpose(), title = title, color_continuous_scale='sunset')

    fig.update_layout(
        xaxis = dict(
            tickmode = 'linear',
            tick0 = -1,
            dtick = dtick,
            tickfont = dict(size = tick_size)
        ))

    # we save graph as a .html graph and as a afgjhgjhgjk 
    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    return fig

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Line loading plot
def plot_line_loading(network):
    
    base_loading = network.res_line["loading_percent"]

    title = 'Base Case Line Loading'

    fig = px.bar(x=base_loading.index,
                y=base_loading,
                title= title)
    
    #------------------------------------------------------
    
    s1 = network.switch['name'].values
    s2 = network.line['name'].values

    common_elements = set(s1) & set(s2)
    num_switch_in_lines = len(common_elements)

    num_lines_with_switch = len(network.line)

    num_lines_without_switch = num_lines_with_switch - num_switch_in_lines

    #------------------------------------------------------

    fig.update_layout(
                    xaxis_title= 'Lines',
                    xaxis = dict(
                        tickmode = 'linear',
                        tick0 = -1,
                        dtick = 1,
                        range=[-1, num_lines_without_switch],
                        ),
                    yaxis_title= 'Loading Percentage [%]',

                    template ="plotly_white", # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]
                    )
    
    #------------------------------------------------------
    
    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    output_file = folder + title
    
    fig.write_html(output_file + ".html") # si salva in formato .html
    fig.write_image(output_file + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Line losses plot
def plot_line_losses(network):
    base_losses = network.res_line['pl_mw']

    title = 'Base Case Line Losses'

    fig = px.bar(x=base_losses.index,
                y=base_losses,
                title= title)
    
    #------------------------------------------------------
    
    s1 = network.switch['name'].values
    s2 = network.line['name'].values

    common_elements = set(s1) & set(s2)
    num_switch_in_lines = len(common_elements)

    num_lines_with_switch = len(network.line)

    num_lines_without_switch = num_lines_with_switch - num_switch_in_lines

    #------------------------------------------------------

    fig.update_layout(
                    xaxis_title= 'Lines',
                    xaxis = dict(
                        tickmode = 'linear',
                        tick0 = -1,
                        dtick = 1,
                        range=[-1, num_lines_without_switch],
                    ),
                    yaxis_title= 'Losses [MW]',
                    template ="plotly_white", # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]
                )
    #------------------------------------------------------

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    output_file = folder + title

    fig.write_html(output_file + ".html") # si salva in formato .html
    fig.write_image(output_file + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# bus voltages in p.u. plot
def plot_voltage(network):
    base_voltage = network.res_bus['vm_pu']

    title = 'Base Case Voltage Profile'

    fig = px.scatter(x=base_voltage.index,
                    y=base_voltage,
                    title= title)

    fig.update_layout(xaxis_title='Bus',
                    yaxis_title= 'Voltage [p.u.]')

    fig.update_layout(
        xaxis = dict(
            tickmode = 'linear',
            tick0 = -1,
            dtick = 1,
        ))

    fig.update_layout(template ="plotly_white") # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]

    x_lim = base_voltage.index.size

    fig.update_xaxes(range=[-1, x_lim])

    config = yaml.safe_load(open("config.yml", 'r'))
    folder = config["forldername_graphs_PF_analysis"]
    output_file = folder + title
    fig.write_html(output_file + ".html") # si salva in formato .html
    fig.write_image(output_file + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# analysis of the base case
def result_analysis(network):
    loads = network.res_bus["p_mw"] # loads of the bus in [MW]
    peak_bus = network.bus.loc[loads.idxmax(),'name'] # name of the bus whit maximum load
    peak_load = loads.max() # maximum load in the network for the buses [mW]
    print("Peak load:", round(peak_load * 1000, 2), "kW at", peak_bus)
    # print("\n")

    peak_voltage = network.res_bus.loc[loads.idxmax(),'vm_pu'] # maximum voltage for the buses in the network [p.u.]
    print("Voltage at peak:", round(peak_voltage, 2), "p.u. at", peak_bus)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# defining voltage check
def voltage_check(network):

    # checking for voltage violations in the results in the bus with min value of each bus
    # if violations adding it to a variable
    if "min_vm_pu" in network.res_bus.columns and "max_vm_pu" in network.res_bus.columns:
        voltage_violations = network.res_bus [
                        (network.res_bus["vm_pu"] < network.bus["min_vm_pu"])| # checking if vm_pu < min_vm_pu
                        (network.res_bus["vm_pu"] > network.bus ["max_vm_pu"])] # checking if vm_pu > max_vm_pu
    else:
        min_vm_pu = 0.95
        max_vm_pu = 1.05

        voltage_violations = network.res_bus [
                        (network.res_bus["vm_pu"] < min_vm_pu)| # checking if vm_pu < min_vm_pu
                        (network.res_bus["vm_pu"] > max_vm_pu)] # checking if vm_pu > max_vm_pu

    return voltage_violations

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# defining the function for voltage analysis
def voltage_analysis(network):

    #voltage check
    check = voltage_check (network)

    # checking and printing the violated buses
    if len(check)==0:
        print('No voltage violations')
    else:
        print("List of all the bus that have a violations in the voltage limits: \n")
        print(check)

        return check

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_voltage_analysis(network):

    if "min_vm_pu" in network.res_bus.columns and "max_vm_pu" in network.res_bus.columns:
        # index of buses with voltage violations
        busVoltageIssue = network.res_bus[
                (network.res_bus["vm_pu"]<network.bus["min_vm_pu"]) | 
                (network.res_bus["vm_pu"]>network.bus["max_vm_pu"])
                ].index
    else:
        min_vm_pu = 0.95
        max_vm_pu = 1.05
        # index of buses with voltage violations
        busVoltageIssue = network.res_bus[
                (network.res_bus["vm_pu"]<min_vm_pu) | 
                (network.res_bus["vm_pu"]>max_vm_pu)
                ].index
    
    #--------------------------------------------------------------------------------------------

    fig = go.Figure()

    #--------------------------------------------------------------------------------------------

    x = network.res_bus.index

    y = network.res_bus["vm_pu"]

    fig.add_trace(go.Scatter(x=x, 
                        y=y,
                        mode='markers',
                        marker_color = 'blue',
                        name = 'Bus',
                        )
                    )
    
    #--------------------------------------------------------------------------------------------

    x = network.res_bus["vm_pu"][busVoltageIssue].index

    y = network.res_bus["vm_pu"][busVoltageIssue]

    fig.add_trace(go.Scatter(x=x, 
                        y=y,
                        mode='markers',
                        marker_color = 'red', 
                        name = 'Bus with voltage issue',
                        )
                    )
    
    #--------------------------------------------------------------------------------------------

    last_x = max(network.res_bus["vm_pu"].index)
    x = [-1, last_x+1]

    y = [0.95, 0.95]

    fig.add_trace(go.Scatter(x = x, 
                            y = y, 
                            mode='lines',
                            marker_color = 'red', 
                            line = dict(dash = 'dash'),
                            name = 'lower limit'
                            )
                    )

    #--------------------------------------------------------------------------------------------

    y = [1.05, 1.05]

    fig.add_trace(go.Scatter(x = x, 
                            y = y, 
                            mode='lines',
                            marker_color = 'red', 
                            line = dict(dash = 'dash'),
                            name = 'upper limit'
                            )
                    )        
    
    #--------------------------------------------------------------------------------------------

    title = "Voltage of buses"

    # updating of title, xlabel and ylabel
    fig.update_layout(
        title_text = title, 
        xaxis = dict(title = "bus"
                    ),
        yaxis = dict(title = "voltage [p.u.]"
                    ))


    # updating of delta_x and relative format
    fig.update_xaxes(
                    dtick = 1,
    #                 tickformat = tickformat,
    #                 # ticklabelmode = "period",
                    tickfont = dict(size = 5)
                    )
    
    fig.update_layout(template ="plotly_white") # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]

    fig.update_layout(xaxis=dict(range=[-1, last_x+1]))

    config = yaml.safe_load(open("config.yml", 'r'))
    path = config["forldername_graphs_PF_analysis"]

    # we save graph as a .html graph and as a afgjhgjhgjk 
    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_line_overloaded(network, max_loading_percent):

    # index of lines overloaded
    lineOverloaded = network.res_line[network.res_line["loading_percent"]>max_loading_percent].index
    
    #--------------------------------------------------------------------------------------------

    fig = go.Figure()

    #--------------------------------------------------------------------------------------------

    line_loading_df = network.res_line.loc[:, ["loading_percent"]].copy()
    line_loading_df.iloc[lineOverloaded] = 0

    x = line_loading_df["loading_percent"].index

    y = line_loading_df["loading_percent"]

    fig.add_trace(go.Bar(x=x, 
                        y=y,
                        marker_color = 'blue',
                        name = 'Lines',
                        )
                    )
    
    #--------------------------------------------------------------------------------------------

    x = network.res_line["loading_percent"][lineOverloaded].index

    y = network.res_line["loading_percent"][lineOverloaded]

    fig.add_trace(go.Bar(x=x, 
                        y=y,
                        marker_color = 'red', 
                        name = 'Lines overloaded',
                        )
                    )  
    
    #--------------------------------------------------------------------------------------------

    last_x = max(network.res_line["loading_percent"].index)
    x = [-1, last_x+1]

    y = [max_loading_percent, max_loading_percent]

    fig.add_trace(go.Scatter(x = x, 
                            y = y, 
                            mode='lines',
                            marker_color = 'red', 
                            line = dict(dash = 'dash'),
                            name = 'limit'
                            )
                    )

    #--------------------------------------------------------------------------------------------
    
    s1 = network.switch['name'].values
    s2 = network.line['name'].values

    common_elements = set(s1) & set(s2)
    num_switch_in_lines = len(common_elements)

    num_lines_with_switch = len(network.line)

    num_lines_without_switch = num_lines_with_switch - num_switch_in_lines

    #--------------------------------------------------------------------------------------------

    title = "Loading of lines"

    # updating of delta_x and relative format
    fig.update_xaxes(
                    dtick = 1,
                    # tickformat = tickformat,
                    # ticklabelmode = "period",
                    tickfont = dict(size = 5)
                    )

    # updating of title, xlabel and ylabel
    fig.update_layout(
                    title_text = title, 
                    xaxis = dict(title = "line",
                                range=[-1, num_lines_without_switch]
                                ),
                    yaxis = dict(title = "loading [%]"
                                ),
                    template ="plotly_white", # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]
                    barmode='stack',
                    )
    
    #--------------------------------------------------------------------------------------------

    config = yaml.safe_load(open("config.yml", 'r'))
    path = config["forldername_graphs_PF_analysis"]

    # we save graph as a .html graph
    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def plot_trafo_overloaded(network):

    # index of overloaded transformers
    trafoOverloaded = network.res_trafo[network.res_trafo["loading_percent"] > 100.0].index
    
    #--------------------------------------------------------------------------------------------

    fig = go.Figure()

    #--------------------------------------------------------------------------------------------

    trafo_loading_df = network.res_trafo.loc[:, ["loading_percent"]].copy()
    trafo_loading_df.iloc[trafoOverloaded] = 0

    x = trafo_loading_df.index

    y = trafo_loading_df["loading_percent"]

    fig.add_trace(go.Bar(x=x, 
                        y=y,
                        marker_color = 'blue',
                        name = 'Trafos',
                        )
                    )
    
    #--------------------------------------------------------------------------------------------

    x = network.res_trafo["loading_percent"][trafoOverloaded].index

    y = network.res_trafo["loading_percent"][trafoOverloaded]

    fig.add_trace(go.Bar(x=x, 
                        y=y,
                        marker_color = 'red', 
                        name = 'Trafos overloaded',
                        )
                    )  
    
    #--------------------------------------------------------------------------------------------

    last_x = max(network.res_trafo["loading_percent"].index)
    x = [-1,last_x+1]

    y = [100, 100]

    fig.add_trace(go.Scatter(x = x, 
                            y = y, 
                            mode='lines',
                            marker_color = 'red', 
                            line = dict(dash = 'dash'),
                            name = 'limit'
                            )
                    )

    #--------------------------------------------------------------------------------------------

    title = "Loading of trafos"

    # updating of title, xlabel and ylabel
    fig.update_layout(
        title_text = title, 
        xaxis = dict(title = "transformer"
                    ),
        yaxis = dict(title = "loading [%]"
                    ))


    # updating of delta_x and relative format
    fig.update_xaxes(
                    dtick = 1,
    #                 tickformat = tickformat,
    #                 # ticklabelmode = "period",
                    tickfont = dict(size = 10)
                    )
    
    fig.update_layout(template ="plotly_white") # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]

    fig.update_layout(barmode='stack')

    config = yaml.safe_load(open("config.yml", 'r'))
    path = config["forldername_graphs_PF_analysis"]

    # we save graph as a .html graph
    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def add_to_file_yml(path, filename, key, value):
    yaml = YAML()
    yaml.preserve_quotes = True

    # Read the YAML file
    with open(path, 'r', encoding='utf-8') as file:
        data = yaml.load(file)

    # Ensure the structure exists
    if filename:
        if filename not in data:
            data[filename] = {}
        data[filename][key] = value
    else:
        data[key] = value

    # Write back to the file without losing comments
    with open(path, 'w', encoding='utf-8') as file:
        yaml.dump(data, file)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def rename_network(network, name):
    network.name = name

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# we create a function to plot data over columns with specified parameters
def get_html_graph_bar_by_columns(df, title, y_parameter, xaxis_label, yaxis_label, dtick, tick_size, path):

    x = df.index # x values

    fig = go.Figure()

    # plot of different distributions over the columns
    for column in df.columns:
        y = df[column]/y_parameter

        fig = px.bar(x=x, 
                y=y,
                )

    # updating of title, xlabel and ylabel
    fig.update_layout(
        title_text = title, 
        xaxis = dict(title = xaxis_label
                    ),
        yaxis = dict(title = yaxis_label
                    ))


    # updating of delta_x and relative format
    fig.update_xaxes(
                    dtick = dtick,
    #                 tickformat = tickformat,
    #                 # ticklabelmode = "period",
                    tickfont = dict(size = tick_size)
                    )
    
    fig.update_layout(template ="plotly_white") # ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn", "simple_white", "none"]

    # we save graph as a .html graph and as a afgjhgjhgjk 
    fig.write_html(path + title + ".html")
    fig.write_image(path + title + ".png", width=1000, height=1100/13.2*6, scale = 5) # si salva in formato .png

    fig.show()

    return fig

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Create a context manager to suppress plotly display
@contextlib.contextmanager
def suppress_plotly_display():
    import plotly.io as pio
    old_show = pio.show
    pio.show = lambda *args, **kwargs: None
    try:
        yield
    finally:
        pio.show = old_show

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def select_and_load_grid(run_powerflow=True):
    """
    Creates an interactive dropdown menu to select a standard pandapower grid.

    Parameters
    ----------
    run_powerflow : bool, default=True
        If True, automatically runs power flow after loading the grid.

    Returns
    -------
    dropdown : ipywidgets.Dropdown
        Interactive dropdown widget.
    output : ipywidgets.Output
        Output widget displaying grid information.
    """

    # Dictionary of available grids
    grid_dict = {
        "IEEE 9 Bus": nw.case9,
        "IEEE 14 Bus": nw.case14,
        "IEEE 30 Bus": nw.case30,
        "IEEE 57 Bus": nw.case57,
        "IEEE 118 Bus": nw.case118,
        "IEEE 300 Bus": nw.case300,
        "CIGRE LV": nw.create_cigre_network_lv,
        "CIGRE MV": nw.create_cigre_network_mv,
        "CIGRE HV": nw.create_cigre_network_hv,
        "Simple Four Bus": nw.simple_four_bus_system,
    }

    # Dropdown widget
    dropdown = widgets.Dropdown(
        options=list(grid_dict.keys()),
        value="IEEE 14 Bus",
        description="Grid:",
        style={"description_width": "initial"},
        layout=widgets.Layout(width="300px")
    )

    # Output widget
    output = widgets.Output()

    def load_grid(change=None):
        with output:
            clear_output(wait=True)

            # Load selected network
            grid_name = dropdown.value
            net = grid_dict[grid_name]()

            # Run power flow
            if run_powerflow:
                pp.runpp(net)

            # Print information
            print("=" * 50)
            print(f"Selected Grid: {grid_name}")
            print("=" * 50)

            print("\n--- Network Size ---")
            print(f"Buses:         {len(net.bus)}")
            print(f"Lines:         {len(net.line)}")
            print(f"Transformers:  {len(net.trafo)}")
            print(f"Loads:         {len(net.load)}")
            print(f"Generators:    {len(net.gen)}")
            print(f"Static Gens:   {len(net.sgen)}")
            print(f"External Grid: {len(net.ext_grid)}")

            if run_powerflow:

                print("\n--- Power Flow Results ---")
                print(f"Total Load P [MW]: {net.res_load.p_mw.sum():.2f}")

                if len(net.res_load):
                    print(f"Total Load Q [MVAr]: {net.res_load.q_mvar.sum():.2f}")

                if len(net.res_gen):
                    print(f"Total Generation P [MW]: {net.res_gen.p_mw.sum():.2f}")

                print("\n--- Voltage Statistics ---")
                print(f"Min Voltage [pu]:  {net.res_bus.vm_pu.min():.3f}")
                print(f"Max Voltage [pu]:  {net.res_bus.vm_pu.max():.3f}")
                print(f"Mean Voltage [pu]: {net.res_bus.vm_pu.mean():.3f}")

                if len(net.res_line):
                    print("\n--- Line Loading ---")
                    print(
                        f"Max Line Loading [%]: "
                        f"{net.res_line.loading_percent.max():.2f}"
                    )

                print("\n--- First 5 Bus Results ---")
                print(net.res_bus.head())

            # Store net in widget for external access
            dropdown.net = net

    # Update when selection changes
    dropdown.observe(load_grid, names='value')

    # Initial load
    load_grid()

    # Display widgets
    display(dropdown, output)

    return dropdown, output

# Example usage:
# dropdown, output = select_and_load_grid()

# # Access currently selected network
# net = dropdown.net

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------