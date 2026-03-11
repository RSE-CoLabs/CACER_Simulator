from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any

class BuildingProperties(BaseModel):
    
    ks_gla: float = Field(..., description="Frazione della superficie lorda utile occupata da vetri")
    ks_opa: float = Field(..., description="Frazione della superficie opaca dispersa sul totale")
    ks_infra: float = Field(..., description="Coefficiente per infrastrutture specifico")
    Volume: float = Field(..., description="Volume totale edificio riscaldato/raffrescato [m²]")
    A_heated: float = Field(..., description="Superficie calpestabile riscaldata/raffrescata [m²]")
    #A_walls: float = Field(..., description="Superficie pareti esterne [m²]")
    A_walls: list[float] = Field(..., description="Area delle pareti esterne [m]")
    # n_floors: int = Field(..., description="Numero di piani riscaldati/raffrescati")
    U_walls: float = Field(..., description="Trasmittanza termica delle pareti [W/m²K]")
    U_windows: float = Field(..., description="Trasmittanza termica dei serramenti [W/m²K]")
    U_roof: float = Field(..., description="Trasmittanza termica del tetto [W/m²K]")
    U_ground: float = Field(..., description="Trasmittanza termica del pavimento [W/m²K]")
    A_windows: list[float] = Field(..., description="Superficie finestrata per orientamento")
    #A_windows: float = Field(..., description="Superficie finestrata [m^2]")
    # height: float = Field(..., description="Altezza utile dell’edificio [m]")
    ACR: float = Field(..., description="Tasso di ricambio dell’aria [1/h]")
    C_m_walls: float = Field(..., description="Capacità termica pareti [J/K*m^2]")
    C_m_roof: float = Field(..., description="Capacità termica soffitto [J/K*m^2]")
    C_m_floor: float = Field(..., description="Capacità termica pavimento [J/K*m^2]")
    C_m_partitions: float = Field(..., description="Capacità termica partizioni [J/K*m^2]")
    A_partitions: float = Field(..., description="Superficie partizione riscaldata/raffrescata [m²]")
    Reflectance: float = Field(..., description="Riflettanza pareti, per il calcolo di K_s")
    F_f: float = Field(..., description="Frazione della finestra formata da vetro")
    C_s: float = Field(..., description="Stima capacità termica pareti divisorie (cartongesso)")
    A_s: float = Field(..., description="Superficie elementi leggeri edificio")
    A_window_frame: float = Field(..., description="Superficie telaio finestre")

    # esempi di validazione per i valori 
    # @field_validator('Volume', 'A_heated', 'A_walls', 'C_m')
    # def must_be_positive(cls, v, info):
    #     if isinstance(v, list):
    #         if not all(x >= 0 for x in v):
    #             raise ValueError(f"{info.field_name} must be a list of non-negative numbers")
    #     elif not isinstance(v, (int, float)) or v < 0:
    #         raise ValueError(f"{info.field_name} must be a non-negative number")
    #     return v

    @field_validator('ks_gla', 'ks_opa', 'ks_infra', 'Volume', 'A_heated', 'U_walls', 'U_windows', 'U_roof', 'U_ground', 'C_m_walls', 'C_m_roof', 'C_m_floor')
    def must_be_non_negative(cls, v, info):
        if v < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return v
    
class HeatPumpProperties(BaseModel):

    maker: str = Field(..., description="Produttore PdC utilizzato")
    model: str = Field(..., description="Modello di PdC utilizzato")
    Voltage: int = Field(..., description="Differenza di potenziale di alimentazione della PdC [V]")
    I_c: float = Field(..., description="Intensità di corrente di avvio PdC [A]")
    phase: float = Field(..., description="Fase di alimentazione della PdC [Hz]")
    starting_time: int = Field(..., description="Durata transitorio di avviamento della PdC [min]")
    thermal_storage: bool = Field(..., description="Presenza di stoccaggio termico della PdC")
    heating_mode: Dict[str, Any] = Field(..., description="Parametri modalità riscaldamento della PdC")
    cooling_mode: Dict[str, Any] = Field(..., description="Parametri modalità raffrescamento della PdC")
    auxiliaries: Dict[str, Any] = Field(..., description="Parametri ausiliari della PdC")
    
    class Config:
        arbitrary_types_allowed = True


    @field_validator('I_c')
    def validate_I_c(cls, v):
        if v <= 0:
            raise ValueError("Corrente di accensione deve essere maggiore di 0")
        return v

    @field_validator('Voltage')
    def validate_Voltage(cls, v):
        if v <= 0:
            raise ValueError("Tensione di alimentazione deve essere maggiore di 0")
        return v

    @field_validator('phase')
    def validate_phase(cls, v):
        if v <= 0:
            raise ValueError("Fase non valida")
        return v

    @field_validator('starting_time')
    def validate_starting_time(cls, v):
        if v <= 0:
            raise ValueError("Tempo di avvio deve essere maggiore di 0")
        return v
    
    @field_validator('heating_mode')
    def validate_heating_mode(cls, v):
        required_keys = ['alpha1_eff', 'alpha2_eff', 'alpha3_eff', 'alpha4_eff', 'alpha5_eff', 'alpha6_eff', 'alpha7_eff', 'alpha8_eff', 'alpha9_eff', 'q_eff','alpha1_power', 'alpha2_power', 'alpha3_power', 'alpha4_power', 'alpha5_power', 'alpha6_power', 'alpha7_power', 'alpha8_power', 'alpha9_power', 'q_power', 'r_sq', 'p_th_max', 'p_th_min', 'p_th_nom', 'p_nom', 'T_setpoint_max', 'f_min_EE', 'f_seasonal_eta']
        for key in required_keys:
            if key not in v:
                raise ValueError(f"Heating mode must have '{key}'")
        for key, value in v.items():
            if not isinstance(value, (float, int)):
                raise ValueError(f"{key} in heating mode must be a number")
        if v['p_th_max'] <= v['p_th_min']:
            raise ValueError("Potenza termica massima deve essere maggiore della potenza termica minima")
        if v['r_sq'] < 0 or v['r_sq'] > 1:
            raise ValueError("R quadro deve essere compreso tra 0 e 1")
        if v['T_setpoint_max'] < 0:
            raise ValueError("Temperatura di setpoint massima deve essere non negativa")
        return v
    
    @field_validator('cooling_mode')
    def validate_cooling_mode(cls, v):
        required_keys = ['alpha1_eff', 'alpha2_eff', 'alpha3_eff', 'alpha4_eff', 'alpha5_eff', 'alpha6_eff', 'alpha7_eff', 'alpha8_eff', 'alpha9_eff', 'q_eff', 'alpha1_power', 'alpha2_power', 'alpha3_power', 'alpha4_power', 'alpha5_power', 'alpha6_power', 'alpha7_power', 'alpha8_power', 'alpha9_power', 'q_power', 'r_sq', 'p_th_max', 'p_th_min', 'p_th_nom', 'p_nom', 'T_setpoint_max', 'f_min_EE', 'f_seasonal_eta']
        for key in required_keys:
            if key not in v:
                raise ValueError(f"Cooling mode must have '{key}'")
        for key, value in v.items():
            if not isinstance(value, (float, int)):
                raise ValueError(f"{key} in heating mode must be a number")
        if v['p_th_max'] >= v['p_th_min']:
            raise ValueError("Potenza termica massima deve essere minore della potenza termica minima")
        if v['r_sq'] < 0 or v['r_sq'] > 1:
            raise ValueError("R quadro deve essere compreso tra 0 e 1")
        if v['T_setpoint_max'] < 0:
            raise ValueError("Temperatura di setpoint massima deve essere non negativa")
        return v
    
    @field_validator('auxiliaries')
    def validate_auxiliaries(cls, v):
        required_keys = ['Pel_fans', 'eta_fans', 'Pel_pumps', 'eta_pumps', 'V_tank', 'cp_water', 'rho_water', 'q_heater', 'T_cut_in', 'T_dead_band']
        for key in required_keys:
            if key not in v:
                raise ValueError(f"Auxiliaries must have '{key}'")
        for key, value in v.items():
            if not isinstance(value, (float, int)):
                raise ValueError(f"{key} in auxiliaries must be a number")
        return v

    
    