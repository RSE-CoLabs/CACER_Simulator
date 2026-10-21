from __future__ import annotations

import numpy as np
import pandas as pd
import pandapower as pp
from tqdm.auto import tqdm

def load_time_series(
    profiles: pd.DataFrame,
    resample_interval: str | None = "1h",
) -> pd.DataFrame:
    df = profiles.copy()
    if "datetime" in df:
        df = df.set_index("datetime")
    df.index = pd.to_datetime(df.index)
    if resample_interval is not None:
        df = df.resample(resample_interval).sum()
    return df


def preprocess_profiles(
    load_df: pd.DataFrame,
    network,
    data_simulation: pd.DataFrame,
):
    load_df = load_df.dropna(subset=["id_pod"])

    missing_pods = [
        pod for pod in load_df["id_pod"]
        if pod not in data_simulation.columns
    ]

    if missing_pods:

        print("\nWARNING: Missing PODs in time series:\n")

        for pod in missing_pods:
            print(pod)

    mapping_df = load_df[
        ["name", "id_pod", "power factor"]
    ].copy()

    ts_transposed = data_simulation.T

    mapping_df.set_index("id_pod", inplace=True)

    df_P = mapping_df.join(
        ts_transposed,
        how="inner"
    )

    df_P["load_name"] = df_P["name"]

    df_P.set_index("load_name", inplace=True)

    df_P = df_P.reindex(network.load["name"])

    power_factor = (
        df_P["power factor"]
        .replace("-", 1)
        .fillna(1)
        .astype(float)
        .clip(lower=0.01, upper=1)
    )

    time_delta = (
        data_simulation.index[1] - data_simulation.index[0]
    ).seconds / 60

    df_P = df_P.drop(columns=["name", "power factor"])

    # kWh/timestep -> kW
    df_P = df_P / (time_delta / 60)

    # kW -> MW
    df_P = df_P / 1000

    tan_phi = np.tan(np.arccos(power_factor.values))

    df_Q = df_P.mul(tan_phi, axis=0)

    return df_P, df_Q


def initialize_result_buffers(network, n_timesteps):

    dtype = np.float32

    buffers = {

        "ext_p": np.zeros(
            (n_timesteps, len(network.ext_grid)),
            dtype=dtype
        ),

        "ext_q": np.zeros(
            (n_timesteps, len(network.ext_grid)),
            dtype=dtype
        ),

        "bus_vm": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "bus_p": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "bus_q": np.zeros(
            (n_timesteps, len(network.bus)),
            dtype=dtype
        ),

        "line_loading": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_pl": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_ql": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_p_to": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_q_to": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_p_from": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "line_q_from": np.zeros(
            (n_timesteps, len(network.line)),
            dtype=dtype
        ),

        "trafo_loading": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "trafo_pl": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "trafo_ql": np.zeros(
            (n_timesteps, len(network.trafo)),
            dtype=dtype
        ),

        "load_p": np.zeros(
            (n_timesteps, len(network.load)),
            dtype=dtype
        )
    }

    if len(network.gen) > 0:

        buffers["gen_p"] = np.zeros(
            (n_timesteps, len(network.gen)),
            dtype=dtype
        )

    return buffers


def run_single_power_flow(network, p_mw, q_mvar, first_run):

    network.load["p_mw"] = p_mw
    network.load["q_mvar"] = q_mvar

    kwargs = dict(
        net=network,
        algorithm="nr",
        init="flat" if first_run else "results",
        tolerance_mva=1e-6,
        max_iteration=20,
        numba=False,
        verbose=False
    )

    # recycle only after first successful PF
    if not first_run:

        kwargs["recycle"] = {
            "trafo": True,
            "gen": True,
            "bus_pq": True,
            "Ybus": True
        }

    pp.runpp(**kwargs)


def store_timestep_results(network, buffers, i):

    buffers["ext_p"][i] = network.res_ext_grid["p_mw"].values
    buffers["ext_q"][i] = network.res_ext_grid["q_mvar"].values

    buffers["bus_vm"][i] = network.res_bus["vm_pu"].values
    buffers["bus_p"][i] = network.res_bus["p_mw"].values
    buffers["bus_q"][i] = network.res_bus["q_mvar"].values

    buffers["line_loading"][i] = network.res_line["loading_percent"].values
    buffers["line_pl"][i] = network.res_line["pl_mw"].values
    buffers["line_ql"][i] = network.res_line["ql_mvar"].values

    buffers["line_p_to"][i] = network.res_line["p_to_mw"].values
    buffers["line_q_to"][i] = network.res_line["q_to_mvar"].values

    buffers["line_p_from"][i] = network.res_line["p_from_mw"].values
    buffers["line_q_from"][i] = network.res_line["q_from_mvar"].values

    buffers["trafo_loading"][i] = network.res_trafo["loading_percent"].values
    buffers["trafo_pl"][i] = network.res_trafo["pl_mw"].values
    buffers["trafo_ql"][i] = network.res_trafo["ql_mvar"].values

    buffers["load_p"][i] = network.res_load["p_mw"].values

    if "gen_p" in buffers:
        buffers["gen_p"][i] = network.res_gen["p_mw"].values


def run_time_series_pf(
    network,
    time_index,
    df_P,
    df_Q,
    buffers
):

    first_run = True

    count_no_convergence = 0

    for i, t in enumerate(
        tqdm(
            time_index,
            desc="Time series power flow",
            unit="timestep"
        )
    ):

        try:

            run_single_power_flow(
                network=network,
                p_mw=df_P[t].values,
                q_mvar=df_Q[t].values,
                first_run=first_run
            )

            first_run = False

            store_timestep_results(
                network,
                buffers,
                i
            )

        except pp.LoadflowNotConverged:

            count_no_convergence += 1

            print(f"WARNING: PF not converged at {t}")

    print(
        f"\n - Number of timestep without convergence: "
        f"{count_no_convergence}"
    )

    return buffers


def build_result_dataframes(
    network,
    time_index,
    buffers
):

    results = {

        "extgridActivePowerTime": pd.DataFrame(
            buffers["ext_p"],
            index=time_index,
            columns=network.ext_grid["name"]
        ),

        "extgridReactivePowerTime": pd.DataFrame(
            buffers["ext_q"],
            index=time_index,
            columns=network.ext_grid["name"]
        ),

        "busVoltageTime": pd.DataFrame(
            buffers["bus_vm"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "busActivePowerTime": pd.DataFrame(
            buffers["bus_p"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "busReactivePowerTime": pd.DataFrame(
            buffers["bus_q"],
            index=time_index,
            columns=network.bus["name"]
        ),

        "lineLoadingTime": pd.DataFrame(
            buffers["line_loading"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActiveLossesTime": pd.DataFrame(
            buffers["line_pl"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactiveLossesTime": pd.DataFrame(
            buffers["line_ql"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActivePowerTimeTo": pd.DataFrame(
            buffers["line_p_to"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactivePowerTimeTo": pd.DataFrame(
            buffers["line_q_to"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineActivePowerTimeFrom": pd.DataFrame(
            buffers["line_p_from"],
            index=time_index,
            columns=network.line["name"]
        ),

        "lineReactivePowerTimeFrom": pd.DataFrame(
            buffers["line_q_from"],
            index=time_index,
            columns=network.line["name"]
        ),

        "trafoLoadingTime": pd.DataFrame(
            buffers["trafo_loading"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "trafoActiveLossesTime": pd.DataFrame(
            buffers["trafo_pl"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "trafoReactiveLossesTime": pd.DataFrame(
            buffers["trafo_ql"],
            index=time_index,
            columns=network.trafo["name"]
        ),

        "loadPowerTime": pd.DataFrame(
            buffers["load_p"],
            index=time_index,
            columns=network.load["name"]
        )
    }

    if "gen_p" in buffers:

        results["genPowerTime"] = pd.DataFrame(
            buffers["gen_p"],
            index=time_index,
            columns=network.gen["name"]
        )

    return results


def load_flow_simulator(
    network,
    load_mapping: pd.DataFrame,
    energy_exchange: pd.DataFrame,
    *,
    resample_interval: str | None = "1h",
):
    data_simulation = load_time_series(
        energy_exchange,
        resample_interval=resample_interval,
    )
    df_P, df_Q = preprocess_profiles(
        load_df=load_mapping,
        network=network,
        data_simulation=data_simulation
    )

    buffers = initialize_result_buffers(
        network=network,
        n_timesteps=len(data_simulation)
    )

    buffers = run_time_series_pf(
        network=network,
        time_index=data_simulation.index,
        df_P=df_P,
        df_Q=df_Q,
        buffers=buffers
    )

    result_TS_PF = build_result_dataframes(
        network=network,
        time_index=data_simulation.index,
        buffers=buffers
    )

    return result_TS_PF
