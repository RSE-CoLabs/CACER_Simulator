import numpy as np
from HVAC_simulator.classes.models import BuildingProperties

class BuildingModel:
    def __init__(self, building_properties, simulation_interval):

        #-----INPUT FISSI-----
        N_NODES = 3
        H_TR_IS = 3.45 # Sostituito il 23/07/2025; il valore è pari al coefficiente convettivo superficie più interna Design Builder; 3.45     # 22/05/2024 [W/(m^2*k)] è considerata costante e pari a 3.45, vedi UNI 13790 Paragrafo 7.2.2.2, pagina 26     
        H_TR_MS = 9.1      # 22/05/2024 [W/(m^2*k)] coefficiente di scambio termico tra i nodi m-s, pari a 9.1, vedi UNI 13790, Paragrafo 12.2.2, pagina 62
        CP_AIR = 1000      # 22/05/2024 per il calcolo della capacità termica aria secca, UNI 13790, paragrafo 9.3.1
        RHO_AIR = 1.2      # 22/05/2024 per il calcolo della capacità termica aria secca, UNI 13790, paragrafo 9.3.1
        
        #-----PARAMETRI EDIFICIO-----
        props = BuildingProperties(**building_properties)

        # Proprietà principali
        self.ks_gla = props.ks_gla
        self.ks_opa = props.ks_opa
        self.ks_infra = props.ks_infra
        self.A_floor = props.A_heated
        self.A_partitions = props.A_partitions
        self.F_f=props.F_f

        # Parametri termici
        self.U_walls = props.U_walls
        self.U_windows = props.U_windows
        self.U_roof = props.U_roof
        self.U_ground = props.U_ground
        ACR = props.ACR                 

        # R_at = 4.5     # Commentato il 23/07/2025; 22/05/2024 Rapporto adimensionale tra area superfici interne e area pavimento, può essere assunto costante e pari a 4.5, vedi UNI 13790 Paragrafo 7.2.2.2; definire perché sia pari a 4
        # cp_furn= 0 #1500      # [J/kg*K] Stima capacità termica dell'arredo
        # rho_furn= 0 #700      # [kg/m^3] Stima densità dell'arredo
        # vol_furn= 0 #0.05      # [-] Stima % volume totale occupato dell'arredo
        
        if simulation_interval=='1H':
            tau=3600        # Costante di tempo pari a 3600 secondi  
        else:
            tau=900         # Costante di tempo pari a 900 secondi     

        self.opaque_area = np.array(props.A_walls)*self.U_walls+np.array(props.A_windows)*(1-self.F_f)*props.A_window_frame
        
        self.opaque_area_roof = self.A_floor/8*np.ones(8)*self.U_roof  # Si assume che il tetto sia suddiviso in 8 parti uguali, una per ogni orientamento
        self.glazed_area = np.array(props.A_windows)
     
        A_t=np.sum(props.A_walls)+2*self.A_floor+self.A_partitions # +np.sum(self.glazed_area)    # Sostituito il 23/07/2025 186.2 [m^2] UNI 13790, Paragrafo 7.2.2.2
        self.V_heated= props.Volume # [m^3] Volume totale interno dell'edificio

        # (1) Coupling conductance H_tr_is [W/K]
        self.H_tr_is =  H_TR_IS*A_t       # [W/(m^2*k)] è considerata costante e pari a 3.45, vedi UNI 13790 Paragrafo 7.2.2.2, pagina 26 
        
        # (2) Transmittance of glazed elements H_tr_w [W/K]
        self.H_tr_w = (props.U_windows)*np.sum(props.A_windows)  #/self.F_f     # [W/k] Coefficiente di scambio termico delle superficie trasparenti props.A_windows
        self.H_tr_op = props.U_walls*np.sum(props.A_walls) +(self.U_roof)*self.A_floor #+ np.sum(props.A_windows)*(1-self.F_f)*9.5#+ self.A_partitions*0.342*0.5*0    la partizione è trascurabile ai fini dello scambio termico, così come il pavimento      # [W/k] Coefficiente di scambio termico delle superficie opache

        A_m= np.sum(props.A_walls)+2*self.A_floor # +self.A_partitions +  2*self.A_floor   # Sostituito il 23/07/2025

        # Distribution of free heat gains to temp nodes
        self.k_a = A_m/A_t
        self.k_s = self.H_tr_w/(9.1*A_t)   

        # (4) Coupling conductance H_tr_ms [W/K]
        self.H_tr_ms = H_TR_MS*A_m   
        
        # (5) Coupling conductance H_tr_em [W/K]
        self.H_tr_em = 1/(1/self.H_tr_op - 1/self.H_tr_ms) # EM Commentata

        # (6) Ventilation conductance H_ve [W/K]
        h_ve = RHO_AIR*CP_AIR*self.V_heated/3600
        self.H_ve = h_ve*ACR
        
        # () Additional capacity for internal partitions and furniture
        self.C_m = props.C_m_walls*(np.sum(props.A_walls)+self.A_partitions) + (props.C_m_roof + props.C_m_floor)*self.A_floor
        #self.C_m = props.C_m_walls*(np.sum(props.A_walls)+self.A_partitions)
        self.C_s = props.A_s*props.C_s 
        
        # () Additional capacity for indoor air
        self.C_i = CP_AIR*RHO_AIR*self.V_heated       

        #--------MATRICI E VETTORI PER LA SIMULAZIONE--------

        A_matrix = np.zeros([3,3])
        A_matrix[0,0] = -(self.H_tr_is + self.H_ve)- self.C_i/tau        
        A_matrix[0,1] = self.H_tr_is      
        A_matrix[1,0] = self.H_tr_is     
        A_matrix[1,1] = -(self.H_tr_is + self.H_tr_w + self.H_tr_ms)- self.C_s/tau
        A_matrix[1,2] = self.H_tr_ms
        A_matrix[2,1] = self.H_tr_ms      
        A_matrix[2,2] = - self.H_tr_em - self.H_tr_ms - self.C_m/tau

        A_inv=np.linalg.inv(A_matrix)
        
        f=np.array([[-self.C_i/tau, 0, 0], [0, -self.C_s/tau, 0], [0, 0, -self.C_m/tau]])        
        self.A = np.dot(A_inv, f)

        b=np.eye(N_NODES)
        self.B = np.dot(A_inv,b)