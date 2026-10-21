from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import math
import pandas as pd
import pandapower as pp


@dataclass(frozen=True, slots=True)
class NetworkInputs:
    buses: pd.DataFrame
    external_grid: pd.DataFrame
    transformers: pd.DataFrame
    lines: pd.DataFrame
    switches: pd.DataFrame
    loads: pd.DataFrame
    generators: pd.DataFrame
    storage: pd.DataFrame


def create_network(
    name: str,
    f_hz: float,
    inputs: NetworkInputs,
    flag_gen: bool = False,
):

    # initializing distribution network
    network = pp.create_empty_network(name, f_hz)

    create_buses(network, inputs.buses)

    create_ext_grid(network, inputs.external_grid)

    create_trafos(network, inputs.transformers)

    create_lines(network, inputs.lines)

    create_switch(network, inputs.switches)

    create_loads(network, inputs.loads, relax_flag=False)

    if flag_gen:
        create_static_gens(network, inputs.generators)

    # create_gens(network)

    # create_storages(network)

    print("\nAll components created!\n")

    return network


def create_buses(network, bus_data: pd.DataFrame):

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


def create_ext_grid(network, ext_grd_data: pd.DataFrame):

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


def create_trafos(network, transf_data: pd.DataFrame):

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


def create_lines(network, line_data: pd.DataFrame):

    # drop all previous elements
    network.line.drop(network.line.index, inplace=True)

    # adding lines to the network
    for k in range(len(line_data)):

        if line_data["r [ohm]"][k] == 0 and line_data["x [ohm]"][k] == 0:
            continue

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

                                    )


def create_switch(network, switch_data: pd.DataFrame):

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


def create_loads(network, load_data: pd.DataFrame, relax_flag: bool = False):

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
                                        cp1_eur_per_mw = -costLoadRelaxation)


def create_static_gens(network, gen_data: pd.DataFrame):

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


def create_gens(network, gen_data: pd.DataFrame):

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


def create_storages(network, storage_data: pd.DataFrame):

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


def v_level_bus(voltage):

    if voltage < 1:
      v_level = 'LV'
    elif voltage <= 35:
      v_level = 'MV'
    else:
      v_level = 'HV'

    return v_level
