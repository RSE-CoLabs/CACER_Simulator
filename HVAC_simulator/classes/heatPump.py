from HVAC_simulator.classes.models import HeatPumpProperties

class HeatPumpModel():

    def __init__(self, hp_properties):

        self.properties = HeatPumpProperties(**hp_properties)

        self.maker=self.properties.maker
        self.model=self.properties.model
        self.I_c=self.properties.I_c         #[A]        # Corrente di accensione compressore pompa di calore Daikin Piacenza [vedi dati costruttore]
        self.Voltage=self.properties.Voltage   #[V]         # Tensione di alimentazione compressore pompa di calore Daikin Piacenza [vedi dati costruttore]
        self.phase=self.properties.phase         # Fase carico circuito monofase a 50 Hz, valore standard
        self.starting_time=self.properties.starting_time          # [min] Tempo in minuti, impiegato dal compressore per andare a regime (stimato sperimentalmente)
        self.thermal_storage=self.properties.thermal_storage

class CoolingModeHeatPump(HeatPumpModel):
    def __init__(self,hp_properties):
        super().__init__(hp_properties)

        self.hp_parameters=self.properties.cooling_mode
        self.f_min_EE=self.hp_parameters['f_min_EE']
        self.f_seasonal_eta=self.hp_parameters['f_seasonal_eta']
        self.P_th_max=self.hp_parameters['p_th_max']
        self.P_th_min=self.hp_parameters['p_th_min']
        self.T_setpoint_max=self.hp_parameters['T_setpoint_max']


class HeatingModeHeatPump(HeatPumpModel):
    def __init__(self,hp_properties):
        super().__init__(hp_properties)

        self.hp_parameters=self.properties.heating_mode
        self.f_min_EE=self.hp_parameters['f_min_EE']
        self.f_seasonal_eta=self.hp_parameters['f_seasonal_eta']
        self.P_th_max=self.hp_parameters['p_th_max']
        self.P_th_min=self.hp_parameters['p_th_min']
        self.T_setpoint_max=self.hp_parameters['T_setpoint_max']


class HeatPumpAuxiliaries(HeatPumpModel):
    def __init__(self,hp_properties):
        super().__init__(hp_properties)

        self.aux_parameters=self.properties.auxiliaries
        self.pel_fans=self.aux_parameters['Pel_fans']
        self.eta_fans=self.aux_parameters['eta_fans']
        self.pel_pumps=self.aux_parameters['Pel_pumps']
        self.eta_pumps=self.aux_parameters['eta_pumps']
        self.v_tank=self.aux_parameters['V_tank']
        self.cp_water=self.aux_parameters['cp_water']
        self.rho_water=self.aux_parameters['rho_water']
        self.q_heater=self.aux_parameters['q_heater']
        self.t_cut_in=self.aux_parameters['T_cut_in']
        self.t_dead_band=self.aux_parameters['T_dead_band']

        

        














                    


    








