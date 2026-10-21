from __future__ import annotations

def BESS(E_terminal_theor, SOCkwh_tm1, ε_roundtrip_halfcycle, battery_min_kwh, battery_max_kwh, flag_battery_to_grid=0, battery_to_grid_capacity=0):
    """
    The function makes a simplified model of a Battery Energy Storage System, as it does not take into account of any voltage, temperature, C-rate and other battery parameters.
    Terminology:
        gross                       before applying the half cycle roundtrip efficiency losses
        net                         after applying the half cycle roundtrip efficiency losses
        theroetical                 before checking applying the DoD lower limit, assuming infinite battery capacity
        real                        after checking the battery upper (100% SOC) and lower limits (DoD)

    Inputs:
        E_terminal_theor            energy flux theoretically available at the battery terminals, given by the PV production at that timestep. Sign convention: charging (+) and discharging (-)
        SOCkwh_tm1                  battery State Of Charge at the t-1 timestep, expressed in kWh
        ε_roundtrip_halfcycle       roundtrip efficiency of a half cycle (assuming same losses for charge and discharge)
        battery_min_kwh             minimum acceptable value of kWh in the battery, above which the battery goes in protection and stops the discharge. It's related to the Dept of Discharge lower limit
                                    (f.i. in this case DoD = 80%, means 20% is the lower boundary), set by the installer/manufacturer in the BMS. Expressed in kWh
        battery_max_kwh             max value of kWh in the battery, here assumed equal to the rated capacity (100% SOC)
        flag_battery_to_grid        flag. If 1, battery injects power into the grid to share with other REC users. If 0, only self-consumption. Default is 0, no battery-to-grid injection
        battery_to_grid_capacity    max kWh limit that the battery can inject into the grid in the delta t interval. It'r related to the discharge C-rate. It's the limit set by the inverter to the grid, configured by the user. Default is 0
    Outputs:
        E_terminal_real             real energy flow at the battery, as a result of losses . <0 se scarica cedendo energia al sistema, >0 se carica assorbendo dal sistema
        E_losses                    transformation losses at the battery terminals for receiving or injecting that energy
        SOC_kWh                     updated State Of Charge at timestep t, in kWh
        SOC_perc                    updated State Of Charge at timestep t, in %
    """


    E_charge_theor_gross = max(0, E_terminal_theor) # if charging (+), if discharging is 0
    # Ecarica_teor_lor = max(0, Emors_teor) # flusso_carica_teorica_lorda_kwh
    E_discharge_theor_gross = min(0, E_terminal_theor - battery_to_grid_capacity * flag_battery_to_grid) # if discharging (-), if charging is 0
    # Escarica_teor_net = min(0, Emors_teor - battery_to_grid_capacity * flag_battery_to_grid) # flusso_scarica_teorico_netto_kwh
    E_halfcycle_theor = E_charge_theor_gross * ε_roundtrip_halfcycle + E_discharge_theor_gross / ε_roundtrip_halfcycle # Flusso mezzociclo teorico (kWh)
    # Emez_teor = Ecarica_teor_lor * ε_roundtrip_halfcycle + Escarica_teor_net / ε_roundtrip_halfcycle # Flusso mezzociclo teorico (kWh)

    # updating SOC checking the upper and lower boundaries
    if SOCkwh_tm1 + E_halfcycle_theor > battery_max_kwh: # in this case, we are charging and going beyond the upper limit, so we need to cap the new SOC to 100%
        SOCkWh = battery_max_kwh
    elif SOCkwh_tm1 + E_halfcycle_theor <= battery_min_kwh: # in this case we are discharging and going below the lower limit, so we need to cap the new SOC to 1-DoD
        SOCkWh = battery_min_kwh
    else: SOCkWh = SOCkwh_tm1 + E_halfcycle_theor # se non siamo in nessuna delle due condizioni limite, il nuovo stato di carica è semplicemente la somma del vecchio e del flusso in ingresso (+ o -)

    SOCperc = SOCkWh / battery_max_kwh

    E_halfcycle_real = SOCkWh - SOCkwh_tm1
    E_charge_real_net = max(0,E_halfcycle_real) # Flusso carica reale netto (kWh)
    E_charge_real_brut = E_charge_real_net / ε_roundtrip_halfcycle # Flusso carica reale lordo (kWh)
    E_discharge_real_brut = min(0,E_halfcycle_real) # Flusso scarica reale lordo (kWh)
    E_discharge_real_net = E_discharge_real_brut * ε_roundtrip_halfcycle # Flusso scarica reale netto (kWh)

    E_terminal_real = E_charge_real_brut + E_discharge_real_net # Flusso reale ai morsetti (kWh)
    E_loss = abs(E_charge_real_net - E_charge_real_brut) + abs(E_discharge_real_brut - E_discharge_real_net)

    return E_terminal_real, E_loss, E_discharge_real_net, SOCkWh, SOCperc
