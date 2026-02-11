import pulp as plp

"""Questo script contiene tutti i vincoli utilizzati dal solutore MILP per il problema di ottimizzazione, 
suddivisi per tipi di variabili ottimizzate

energy: vincoli relativi all'energia

thermal_load: vincoli relativi al fabbisogno termico dell'edificio

hp: vincoli relativi all'impianto di climatizzazione a pompa di calore

"""

def milp_energy_constraints(opt_model, e_in_vars, e_out_vars, e_cast_pv, ee_tot, k_vars, l_vars, set_P, set_N, set_HVAC, prosumer_p_contr, consumer_p_contr, e_in_virtual_vars, e_out_virtual_vars, a_vars, b_vars, M, start_time_optimization, dt, cacer_type):

    constraints = {(p,n) : opt_model.addConstraint(
        plp.LpConstraint(
                    e= e_in_vars[p,n] - e_out_vars[p,n] + e_cast_pv[start_time_optimization+n-1]*dt, # - E_condominio[n-1], #-  plp.lpSum(EE_tot[n,p] for pdc in set_HVAC),
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="10_constraint_{0}_{1}".format(p,n)))
                    for p in set_P for n in set_N}
    
    if cacer_type == 'CER':
        # Vincolo (3_acons) Limitazione Energia massima consumata
        constraints = {(c,n) : opt_model.addConstraint(
            plp.LpConstraint(
                        #e= ee_tot[n,c] + E_base[c][n-1] - auc.n_consumer[c].p_contr*1100,
                        e= ee_tot[n,c] - consumer_p_contr[c]*dt,
                        sense=plp.LpConstraintLE,
                        rhs=0,
                        name="3acons_constraint_{0}_{1}".format(c,n)))
                    for c in set_HVAC for n in set_N }
        
            # Vincolo (10_b): BILANCIO ENERGETICO VIRTUALE CONSUMERS
        constraints = {n : opt_model.addConstraint(
            plp.LpConstraint(
                        # e= - E_out_virtual_vars[n] + E_in_virtual_vars[n] + plp.lpSum(E_out_vars[p,n] - E_in_vars[p,n] for p in set_P)  - plp.lpSum(E_base[c][n-1] for c in set_C) -  plp.lpSum(EE_tot[n,pdc] for pdc in set_HVAC ),
                        - e_out_virtual_vars[n] + e_in_virtual_vars[n] + plp.lpSum(e_out_vars[p,n] - e_in_vars[p,n] for p in set_P) -  plp.lpSum(ee_tot[n,pdc] for pdc in set_HVAC ),
                        sense=plp.LpConstraintEQ,
                        rhs=0,
                        name="10b_constraint_{0}".format(n)))
                        for n in set_N}
    
    elif cacer_type == 'AUC':
        # Vincolo (3_acons) Limitazione Energia massima consumata
        constraints = {(p,n) : opt_model.addConstraint(
            plp.LpConstraint(
                        #e= ee_tot[n,c] + E_base[c][n-1] - auc.n_consumer[c].p_contr*1100,
                        e= ee_tot[n] - prosumer_p_contr[p]*dt,
                        sense=plp.LpConstraintLE,
                        rhs=0,
                        name="3acons_constraint_{0}_{1}".format(p,n)))
                    for p in set_P for n in set_N }
        
        constraints = {n : opt_model.addConstraint(
            plp.LpConstraint(
                        # e= - E_out_virtual_vars[n] + E_in_virtual_vars[n] + plp.lpSum(E_out_vars[p,n] - E_in_vars[p,n] for p in set_P)  - plp.lpSum(E_base[c][n-1] for c in set_C) -  plp.lpSum(EE_tot[n,pdc] for pdc in set_HVAC ),
                        - e_out_virtual_vars[n] + e_in_virtual_vars[n] + plp.lpSum(e_out_vars[p,n] - e_in_vars[p,n] for p in set_P) -  ee_tot[n],
                        sense=plp.LpConstraintEQ,
                        rhs=0,
                        name="10b_constraint_{0}".format(n)))
                        for n in set_N}

    # Vincolo (3_aa) Limitazione Energia massima prelevata dalla rete
    constraints = {(p,n) : opt_model.addConstraint(
    plp.LpConstraint(
                e= e_in_vars[p,n]-k_vars[p,n]*prosumer_p_contr[p]*dt,
                sense=plp.LpConstraintLE,
                rhs=0,
                name="3aa_constraint_{0}_{1}".format(p,n)))
        for p in set_P for n in set_N }

    # # Vincolo (3_bb) Limitazione Energia massima immessa in rete
    constraints = {(p,n) : opt_model.addConstraint(
    plp.LpConstraint(
                e= e_out_vars[p,n]-l_vars[p,n]*M,
                sense=plp.LpConstraintLE,
                rhs=0,
                name="3bb_constraint_{0}_{1}".format(p,n)))
        for p in set_P for n in set_N }
    
    # Vincolo (3_aa) Limitazione Energia virtuale massima prelevata dalla rete
    constraints = {n : opt_model.addConstraint(
    plp.LpConstraint(
                e= e_in_virtual_vars[n]-a_vars[n]*prosumer_p_contr[p]*dt,
                sense=plp.LpConstraintLE,
                rhs=0,
                name="3cc_constraint_{0}".format(n)))
        for p in set_P  for n in set_N }

    # Vincolo (3_dd) Limitazione Energia massima immessa in rete
    constraints = {n : opt_model.addConstraint(
    plp.LpConstraint(
                e= e_out_virtual_vars[n]-b_vars[n]*prosumer_p_contr[p]*dt,
                sense=plp.LpConstraintLE,
                rhs=0,
                name="3dd_constraint_{0}".format(n)))
        for p in set_P  for n in set_N }    

    # Vincolo (3_c) Impedire immissione e prelievo in rete allo stesso tempo
    constraints = {(p,n) : opt_model.addConstraint(
    plp.LpConstraint(
                e= k_vars[p,n]+l_vars[p,n],
                sense=plp.LpConstraintLE,
                rhs=1,
                name="3c_constraint_{0}_{1}".format(p,n)))
        for p in set_P for n in set_N }
    
    # Vincolo (3_d) Impedire immissione e prelievo virtuali in rete allo stesso tempo:
    constraints = {n : opt_model.addConstraint(
    plp.LpConstraint(
                e= a_vars[n] + b_vars[n],
                sense=plp.LpConstraintLE,
                rhs=1,
                name="3d_constraint_{0}".format(n)))
        for n in set_N }

    return opt_model, constraints

###############################################################################################################################

def milp_thermal_constraints(opt_model, hp_users_list, set_HVAC, t_int, omega_s_ac, omega_m_ac, set_T, t_start_dayahead, set_Temp, t_ext, start_time_optimization, phi_ia, phi_st, phi_m, phi_hc_nd_ac, T_MAX, T_MIN, constraints):

        
        constraints = {(n,p) : opt_model.addConstraint(
        plp.LpConstraint(
                    e=t_int[n,p] - ((hp_users_list[p].building.A[0][0])*t_int[n-1,p] +(hp_users_list[p].building.A[0][1])*omega_s_ac[n-1,p]+(hp_users_list[p].building.A[0][2])*omega_m_ac[n-1,p] +(-hp_users_list[p].building.H_ve*t_ext[start_time_optimization+n-2]-phi_ia[start_time_optimization+n-2][p]-phi_hc_nd_ac[n-1,p])*(hp_users_list[p].building.B[0][0])+(-phi_st[start_time_optimization+n-2][p]-hp_users_list[p].building.H_tr_w*t_ext[start_time_optimization+n-2])*(hp_users_list[p].building.B[0][1])+(-hp_users_list[p].building.H_tr_em*t_ext[start_time_optimization+n-2] -(phi_m[start_time_optimization+n-2][p]+hp_users_list[p].building.U_ground*hp_users_list[p].building.A_floor*(15-omega_m_ac[n-1,p])))*(hp_users_list[p].building.B[0][2])),
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="30_constraint_{0}_{1}".format(n,p)))
                    # for n in range(2,n_intervals+1)}
                    for n in set_T for p in set_HVAC}
        
        constraints = {(n,p) : opt_model.addConstraint(
        plp.LpConstraint(
                    e=omega_s_ac[n,p] - ((hp_users_list[p].building.A[1][0])*t_int[n-1,p] +(hp_users_list[p].building.A[1][1])*omega_s_ac[n-1,p]+(hp_users_list[p].building.A[1][2])*omega_m_ac[n-1,p]+(-hp_users_list[p].building.H_ve*t_ext[start_time_optimization+n-2]-phi_ia[start_time_optimization+n-2][p]-phi_hc_nd_ac[n-1,p])*(hp_users_list[p].building.B[1][0])+(-phi_st[start_time_optimization+n-2][p]-hp_users_list[p].building.H_tr_w*t_ext[start_time_optimization+n-2])*(hp_users_list[p].building.B[1][1])+(-hp_users_list[p].building.H_tr_em*t_ext[start_time_optimization+n-2]-(phi_m[start_time_optimization+n-2][p]+hp_users_list[p].building.U_ground*hp_users_list[p].building.A_floor*(15-omega_m_ac[n-1,p])))*(hp_users_list[p].building.B[1][2])),
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="31_constraint_{0}_{1}".format(n,p)))
                    # for n in range(2,n_intervals+1)}
                    for n in set_T for p in set_HVAC}
        
        constraints = {(n,p) : opt_model.addConstraint(
        plp.LpConstraint(
                    e=omega_m_ac[n,p] - (hp_users_list[p].building.A[2][0]*t_int[n-1,p] +hp_users_list[p].building.A[2][1]*omega_s_ac[n-1,p]+hp_users_list[p].building.A[2][2]*omega_m_ac[n-1,p] +(-hp_users_list[p].building.H_ve*t_ext[start_time_optimization+n-2]-phi_ia[start_time_optimization+n-2][p]-phi_hc_nd_ac[n-1,p])*(hp_users_list[p].building.B[2][0])+(-phi_st[start_time_optimization+n-2][p]-hp_users_list[p].building.H_tr_w*t_ext[start_time_optimization+n-2])*(hp_users_list[p].building.B[2][1])+(-hp_users_list[p].building.H_tr_em * t_ext[start_time_optimization+n-2] -(phi_m[start_time_optimization+n-2][p]+hp_users_list[p].building.U_ground*hp_users_list[p].building.A_floor*(15-omega_m_ac[n-1,p])))*hp_users_list[p].building.B[2][2]),
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="32_constraint_{0}_{1}".format(n,p)))
                    # for n in range(2,n_intervals+1)}
                    for n in set_T for p in set_HVAC}
        
        constraints = {p: opt_model.addConstraint(
        plp.LpConstraint(
                    e= t_int[1,p] - t_start_dayahead[p][2],
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="20a_constraint_{0}".format(p)))
                    for p in set_HVAC}
        
        constraints = {p: opt_model.addConstraint(
        plp.LpConstraint(
                    e= omega_s_ac[1,p] - t_start_dayahead[p][1],
                    rhs=0,
                    name="20e_constraint_{0}".format(p)))
                    for p in set_HVAC}
        
        constraints = {p: opt_model.addConstraint(
        plp.LpConstraint(
                    e= omega_m_ac[1,p] - t_start_dayahead[p][0],
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="20f_constraint_{0}".format(p)))
                    for p in set_HVAC}

        constraints = {(n,p) : opt_model.addConstraint(
        plp.LpConstraint(
                    e=t_int[n,p] - T_MAX,            # T_max_00 è l'array di T_max_0 per gli istanti in cui utente è presente
                    sense=plp.LpConstraintLE,
                    rhs=0,
                    name="34b_constraint_{0}_{1}".format(n,p)))
                for n in set_Temp for p in set_HVAC}
        
        constraints = {(n,p) : opt_model.addConstraint(
        plp.LpConstraint(
                    e=t_int[n,p] - T_MIN,             # T_min_00 è l'array di T_min_0 per gli istanti in cui utente è presente    
                    sense=plp.LpConstraintGE,
                    rhs=0,
                    name="34c_constraint_{0}_{1}".format(n,p)))
                for n in set_Temp for p in set_HVAC}
        
        return opt_model, constraints

###############################################################################################################################

def milp_hp_autonomous_constraints(opt_model, phi_hc_nd_ac, q_crankcase, q_heater, q_hp, q_min, q_max, ee_tot, ee_binary, mode_pdc, set_N, set_HVAC, dt, eta, pe_defrost, hp_users_list, start_time_optimization, q_crankcase_activation, constraints):
        
    constraints = {
            (n, p): opt_model.addConstraint(
                plp.LpConstraint(
                    e=phi_hc_nd_ac[n, p] 
                    - ((q_hp[n, p]+q_crankcase[n, p]+q_heater[n, p])
                        if mode_pdc[start_time_optimization+n-1] == "heating"
                        else  (q_hp[n, p])),
                    
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name=f"37a_constraint_{n}_{p}"
                )
            )
            for n in set_N for p in set_HVAC
        }
        
    constraints = {
            (n, p): opt_model.addConstraint(
                plp.LpConstraint(
                    e=ee_tot[n, p] 
                    - (
                        (q_hp[n, p] * (1 / eta[start_time_optimization+n-1][p])+pe_defrost[start_time_optimization+n-1, p]+q_crankcase[n, p]+q_heater[n, p]) *(dt)
                        if mode_pdc[start_time_optimization+n-1] == "heating"
                        else  (-q_hp[n, p] * (1 / eta[start_time_optimization+n-1][p])) *(dt)
                    ),
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name=f"37b_constraint_{n}_{p}"
                )
            )
            for n in set_N for p in set_HVAC
        }

    constraints = {
            (n, p): opt_model.addConstraint(
                plp.LpConstraint(
                    e=q_heater[n, p]
                    - hp_users_list[p].hp_aux.q_heater*(1-q_crankcase_activation[start_time_optimization+n-1,p])
                    ,
                    sense=plp.LpConstraintLE,
                    rhs=0,
                    name=f"Q_heater_upper_bound_{n}_{p}"
                )
            )
            for n in set_N for p in set_HVAC
        }

    constraints = {
            (n, p): opt_model.addConstraint(
                plp.LpConstraint(
                    e=q_crankcase[n, p]
                    - hp_users_list[p].hp_aux.q_heater*q_crankcase_activation[start_time_optimization+n-1,p]
                    ,
                    sense=plp.LpConstraintLE,
                    rhs=0,
                    name=f"Q_crankase_upper_bound_{n}_{p}"
                )
            )
            for n in set_N for p in set_HVAC
        }

    constraints = {
            (n,p): opt_model.addConstraint(
                plp.LpConstraint(
                    e=q_hp[n,p] -
                    (ee_binary[n,p] * q_min[start_time_optimization+n-1][p] if mode_pdc[start_time_optimization+n-1] == "heating"
                    else (ee_binary[n,p] * q_max[start_time_optimization+n-1][p])),
                    sense=plp.LpConstraintGE,
                    rhs=0,
                    name="EE_lower_bound_{0}_{1}".format(n,p)
                )
            ) for n in set_N for p in set_HVAC
        }
        
    constraints = {
        (n,p): opt_model.addConstraint(
            plp.LpConstraint(
                    e=q_hp[n,p] - 
                    (ee_binary[n,p] * q_max[start_time_optimization+n-1][p] if mode_pdc[start_time_optimization+n-1] == "heating"
                    else (ee_binary[n,p] * q_min[start_time_optimization+n-1][p])),
                    sense=plp.LpConstraintLE,
                    rhs=0,
                    name="EE_upper_bound_{0}_{1}".format(n,p)
                )
            ) 
            for n in set_N for p in set_HVAC
        }

    return opt_model, constraints

###############################################################################################################################

def milp_hp_centralized_constraints(opt_model, phi_hc_nd_ac, q_hp, q_min, q_max, ee_tot, ee_binary, mode_pdc, set_N, set_HVAC, dt, eta, start_time_optimization, hp_aux, constraints):
        
    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e= plp.lpSum(phi_hc_nd_ac[n, p] for p in set_HVAC) - q_hp[n],       # Modificato 11-08-2025
                sense=plp.LpConstraintEQ,
                rhs=0,
                name="37a_constraint_{0}".format(n))
            )
        for n in set_N
    }

    # Vincoli per potenza termica minima e massima della PdC
    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(                      
                e=q_hp[n] -
                (ee_binary[n] * q_min[start_time_optimization+n-1] if mode_pdc[start_time_optimization+n-1] == "heating"
                else (ee_binary[n] * q_max[start_time_optimization+n-1])),
                sense=plp.LpConstraintGE,
                rhs=0,
                name=f"37_constraint_pemin{n}")
            )

        for n in set_N
    }

    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=q_hp[n] -
                (ee_binary[n] * q_max[start_time_optimization+n-1] if mode_pdc[start_time_optimization+n-1] == "heating"
                else (ee_binary[n] * q_min[start_time_optimization+n-1])),
                sense=plp.LpConstraintLE,
                rhs=0,
                name=f"37_constraint_pemax{n}")
            )

        for n in set_N
    }

    constraints = {
        n: opt_model.addConstraint(
            plp.LpConstraint(
                e= ee_tot[n]+((-q_hp[n] * (1 / eta[start_time_optimization+n-1])- hp_aux.pel_fans/hp_aux.eta_fans - hp_aux.pel_pumps/hp_aux.eta_pumps) * dt
                if mode_pdc[start_time_optimization+n-1] == "heating"
                    else  (q_hp[n] * (1 / eta[start_time_optimization+n-1])- hp_aux.pel_fans/hp_aux.eta_fans - hp_aux.pel_pumps/hp_aux.eta_pumps) *dt),
                sense=plp.LpConstraintEQ,
                rhs=0,
                name=f"37b_constraint_{n}"
            )
        )
        for n in set_N
            }

    return opt_model, constraints

###############################################################################################################################

def milp_hp_centralized_storage_constraints(opt_model, ee_tot, phi_hc_nd_ac, delta_h, t_water_tank, k_compressor_status, k_compressor_off, k_compressor_on, 
                                            hp_aux, start_time_optimization, set_HVAC, set_T, set_N, set_S, q_max, eta, M, t_water_tank_0, k_compressor_status_0, m_water_tank, dt):
            
    t_cut_off=hp_aux.t_cut_in+hp_aux.t_dead_band

    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=plp.lpSum(phi_hc_nd_ac[n-1, p] for p in set_HVAC) - delta_h[n-1],
                sense=plp.LpConstraintEQ,
                rhs=0,
                name=f"47a_constraint_{n}")
            )

        for n in set_T
    }

    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=delta_h[n-1]- m_water_tank*hp_aux.cp_water*(t_water_tank[n-1] - t_water_tank[n])*(1/(3600*dt)) - (k_compressor_status[n-1]*(q_max[start_time_optimization+n-2])),
                sense=plp.LpConstraintEQ,
                rhs=0,
                name=f"47b_constraint_{n}")
            )

        for n in set_T
    }


    constraints = {
        n: opt_model.addConstraint(
            plp.LpConstraint(
                e= ee_tot[n]-(k_compressor_status[n]*(hp_aux.pel_fans/hp_aux.eta_fans+q_max[start_time_optimization+n-1]*(1 /eta[start_time_optimization+n-1]))+ hp_aux.pel_pumps/hp_aux.eta_pumps)*(dt), #(k_compressor_status[n]*(Pel_fans/eta_fans+ Q_max[n-1] * (1 / eta[n-1]))+ Pel_pumps/eta_pumps) * (dt),
                sense=plp.LpConstraintEQ,
                rhs=0,
                name=f"47e_constraint_{n}"
            )
        )
        for n in set_N
    }


    constraints = {
        opt_model.addConstraint(
            plp.LpConstraint(
                        e= t_water_tank[1]-t_water_tank_0,
                        sense=plp.LpConstraintEQ,
                        rhs=0,
                        name="48a_constraint"
                    )
                )
            }
    
    constraints = {
        opt_model.addConstraint(
            plp.LpConstraint(
                    e= k_compressor_status[1]-k_compressor_status_0,
                    sense=plp.LpConstraintEQ,
                    rhs=0,
                    name="49a_constraint"
                )
            )
        }
    
    constraints = {
        opt_model.addConstraint(
            plp.LpConstraint(
                        e= k_compressor_off[1]-k_compressor_status_0,
                        sense=plp.LpConstraintEQ,
                        rhs=0,
                        name="49b_constraint"
                    )
                )
            }
    
    constraints = {
        opt_model.addConstraint(
            plp.LpConstraint(
                        e= k_compressor_on[1]-k_compressor_status_0,
                        sense=plp.LpConstraintEQ,
                        rhs=0,
                        name="49c_constraint"
                    )
                )
            }

# # Vincolo spegnimento compressore (40a e 40b)
    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=t_water_tank[n] - t_cut_off - M*k_compressor_off[n],
                sense=plp.LpConstraintLE,
                rhs=0,
                name=f"50a_constraint_{n}")
            )
        for n in set_S
    }

    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=t_water_tank[n] - t_cut_off + M*(1-k_compressor_off[n]) +1e-6,
                sense=plp.LpConstraintGE,
                rhs=0,
                name=f"50b_constraint_{n}")
            )
        for n in set_S
    }

# Vincolo accensione compressore (41a e 41b)
    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=t_water_tank[n] - hp_aux.t_cut_in + M*k_compressor_on[n],
                sense=plp.LpConstraintGE,
                rhs=0,
                name=f"51a_constraint_{n}")
            )
        for n in set_S
    }

    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=t_water_tank[n] - hp_aux.t_cut_in - M*(1-k_compressor_on[n])-1e-6,
                sense=plp.LpConstraintLE,
                rhs=0,
                name=f"51b_constraint_{n}")
            )
        for n in set_S
    }

# Vincolo per impostare lo stato del compressore (42)
    constraints = {n: opt_model.addConstraint(
            plp.LpConstraint(
                e=k_compressor_status[n] - (k_compressor_on[n] + k_compressor_status[n-1]- k_compressor_off[n]),
                sense=plp.LpConstraintEQ,
                rhs=0,
                name=f"52_constraint_{n}")
            )
        for n in set_S
    }
    return opt_model, constraints