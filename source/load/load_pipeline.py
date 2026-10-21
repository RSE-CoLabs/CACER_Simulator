from __future__ import annotations

import calendar
import contextlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import io
import math
from pathlib import Path
import pickle
import random
import sys
from typing import Any, Mapping
import warnings

import holidays
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.graph_objs as go_objs
from simple_colors import blue, green, red
from tqdm.auto import tqdm
import yaml

from source.config.utilities import (
    generate_calendar_modified,
    province_to_region,
    resolve_path,
)
from source.data_structures import ConfigResults, LoadResults, PipelineOptions, RunContext


# Migrated from main.py:7
def main():
    #---------------------------------------------------------------------------------------------
    # Number of users to emulate
    #---------------------------------------------------------------------------------------------

    num_user = 300
    name = "300_3" # name to add to the results files, e.g. "300_users", "500_users", etc.
    #---------------------------------------------------------------------------------------------
    # Simulation period
    #---------------------------------------------------------------------------------------------

    start_day = date(2025, 1, 1) # start day for simulation
    end_day = date(2025, 12, 31) # end day for simulation

    calendar_df, calendar_daily = create_calendar_dfs(start_day, end_day)

    data_input = import_data_load_emulator_v2()

    data_input = remove_specific_appliance(data_input, specific_appliance='induction_hob')


    dict_users, stacked_df = load_emulator_v2(num_user,
                                  data_input,
                                  calendar_df,
                                  calendar_daily,

                                  name = name,
                                  simulate_boiler=False, # if True, the boiler will be simulated
                                  all_boiler_profiles=False,

                                  show_results=False, # a progress bar and some plots with results will be shown
                                  save_all_results=False, # save the results in a pickle file, disactivate if there are too many users!!

                                  specific_appliance=None, # if not None, only the specified appliance will be simulated (e.g. 'washing_machine', 'induction_hob', 'boiler', etc.)

                                  parallelize=True, # parallelize the creation of duty cycle profiles, time-consuming part of the process
                                  max_workers=10, # number of workers to use for parallelization
                                  )


    export_mean_profile_load_emulator_v2(stacked_df, name=name, specific_appliance=None)


# Migrated from src/Functions_Load_Emulator_and_DSM.py:961
def run_load_emulator_v1(
    config: Mapping[str, Any],
    registry_users: Mapping[str, Mapping[str, Any]],
    flag_last_dict=False,
    flag_optDSM=False,
    flag_all_appliance=True,
    flag_daily_activation=True,
    flag_multi_use=True,
):
    """Create emulated load profile (and eventually DSM emulated load profile) for all emulated users setted in the user CACER.xlsx external file.

    Inputs:
        flag_last_dict (bool, optional): if true we use the last simulated appliance start time to create the load profile. Defaults to False.
        flag_optDSM (bool, optional): if true we use the optimized simulated appliance start time to create the load profile. Defaults to False.
        flag_all_appliance (bool, optional): if false we use as input file the modified appliance load profile. Defaults to True.
        flag_daily_activation (bool, optional): if false we dont'use a daily usage activation for some specified appliances. Defaults to True.
        flag_multi_use (bool, optional): if true we activate the possibility to have multiple activations for the selected appliances during the day. Defaults to True.

    Outputs:
        all_user_df: This dataframe has an unstacked structure and is created with timestep on rows (entire time range) and users
    """

    print(blue("\nCreate load profile for emulated users:", ['bold', 'underlined']), '\n')

    emulated_users_list = [registry_users[user_id]['user_type']
                            for user_id in registry_users
                            if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer')]

    num_users = int(len(emulated_users_list)) # we calculate the number of users to simulate

    ########################################################################

    # if there is some DSM user in registry_users_types.yml we create also the DSM load profile
    DSM_emulated_users_list = [registry_users[user_id]['user_type']
                                for user_id in registry_users
                                if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer') and (registry_users[user_id]['flag_DSM'] == True)]

    if DSM_emulated_users_list != []:
        flag_simpleDSM = True
    else:
        flag_simpleDSM = False

    ########################################################################

    if num_users == 0:

        print('**** No emulated users found! ****')

    else:
        start_day = config['start_date']
        project_lifetime = config['project_lifetime_yrs']
        end_day = start_day.replace(year = start_day.year + project_lifetime) - timedelta(days=1)

        ########################################################################

        print(blue("\n - Load user emulator:", ['bold']))
        print('-----------------------------------------\n-----------------------------------------')

        load_profile_emulator(emulated_users_list, start_day, end_day, flag_last_dict, flag_optDSM, flag_all_appliance, flag_daily_activation, flag_multi_use)

        ########################################################################

        if flag_simpleDSM and not flag_optDSM:

            print(blue("\n - DSM load user emulator:", ['bold']))
            print('-----------------------------------------\n-----------------------------------------')

            DSM_load_profile_emulator(emulated_users_list, DSM_emulated_users_list, start_day, end_day, flag_all_appliance, flag_daily_activation, flag_multi_use)

    return


# Migrated from src/Functions_Load_Emulator_v2.py:758
def save_dictionary_to_pickle(dictionary, filename):

    with open(filename, "wb") as f:
        pickle.dump(dictionary, f)

    print(green(f"\n  **** Dictionary saved to {filename} ****"))


# Migrated from src/Functions_Load_Emulator_v2.py:1974
def import_data_load_emulator_v2(settings, repository_root):

    #---------------------------------------------------------------------------------------------
    # 0. Import paths
    #---------------------------------------------------------------------------------------------

    path_metadata = resolve_path(repository_root, settings['filename_metadata_v2'])
    path_usage_probability = resolve_path(repository_root, settings['filename_usage_probability_v2'])
    path_multi_usage_probability = resolve_path(repository_root, settings['filename_multi_usage_probability_v2'])
    path_appliances_load_profiles = resolve_path(repository_root, settings['filename_appliances_load_profiles_v2'])
    path_base_load_profiles = resolve_path(repository_root, settings['filename_base_load_profiles_v2'])
    path_boiler_profiles = resolve_path(repository_root, settings['filename_boiler_profiles_v2'])

    results = {}

    #---------------------------------------------------------------------------------------------
    # 1. Import appliances load profiles
    #---------------------------------------------------------------------------------------------

    dict_appliances_load = pd.read_excel(path_appliances_load_profiles, sheet_name = None, index_col = 0)

    list_unique_load_profile = list(pd.read_excel(path_metadata, sheet_name = 'clusters_equipment', index_col = 0).columns)
    # list_unique_load_profile = create_list_unique_load_profiles(dict_appliances_load)

    dict_appliances_load_info = create_dict_appliances_load_info(list_unique_load_profile, dict_appliances_load)

    # list of appliances for each profile type
    list_appliances_sp = create_list_profile_type('s_profile', dict_appliances_load_info)
    list_appliances_blp = create_list_profile_type('blp_profile', dict_appliances_load_info)
    list_appliances_blnp = create_list_profile_type('blnp_profile', dict_appliances_load_info)
    list_appliances_dc = create_list_profile_type('dc_profile', dict_appliances_load_info)

    #---------------------------------------------------------------------------------------------
    # 2. Import base load profiles statistics
    #---------------------------------------------------------------------------------------------

    dict_base_load_stats = pd.read_excel(path_base_load_profiles, sheet_name = None, index_col = 0)

    #---------------------------------------------------------------------------------------------
    # 3. Import usage probability
    #---------------------------------------------------------------------------------------------

    dict_usage_probability = pd.read_excel(path_usage_probability, sheet_name = None, index_col = 0)

    df_usage_probability_wd = dict_usage_probability['working_day']
    df_usage_probability_we = dict_usage_probability['weekend']

    #---------------------------------------------------------------------------------------------
    # 4. Import multi usage probability
    #---------------------------------------------------------------------------------------------

    dict_multi_usage_probability = pd.read_excel(path_multi_usage_probability, sheet_name = None, index_col = 0)

    df_multi_usage_probability_wd = dict_multi_usage_probability['working_day']
    df_multi_usage_probability_we = dict_multi_usage_probability['weekend']

    #---------------------------------------------------------------------------------------------
    # 5. Import metadata load emulator
    #---------------------------------------------------------------------------------------------

    dict_metadata_load_emulator = pd.read_excel(path_metadata, sheet_name = None, index_col = 0)

    df_clusters_distribution = dict_metadata_load_emulator['clusters_distribution']
    df_clusters_equipment = dict_metadata_load_emulator['clusters_equipment']
    df_clusters_equipment_multi = dict_metadata_load_emulator['clusters_equipment_multi']
    df_monthly_usage_probability = dict_metadata_load_emulator['monthly_usage_probability']

    #---------------------------------------------------------------------------------------------
    # 6. Import boiler profiles
    #---------------------------------------------------------------------------------------------

    dict_boiler_profiles = pd.read_excel(path_boiler_profiles, sheet_name = None, index_col = 0)

    #---------------------------------------------------------------------------------------------
    # 6. Return all results
    #---------------------------------------------------------------------------------------------

    results = {'dict_appliances_load': dict_appliances_load,
               'dict_appliances_load_info': dict_appliances_load_info,

               'list_appliances_sp': list_appliances_sp,
               'list_appliances_blp': list_appliances_blp,
               'list_appliances_blnp': list_appliances_blnp,
               'list_appliances_dc': list_appliances_dc,

               'dict_base_load_stats': dict_base_load_stats,

               'df_usage_probability_wd': df_usage_probability_wd,
               'df_usage_probability_we': df_usage_probability_we,

               'dict_multi_usage_probability': dict_multi_usage_probability,
               'df_multi_usage_probability_wd': df_multi_usage_probability_wd,
               'df_multi_usage_probability_we': df_multi_usage_probability_we,

               'df_clusters_distribution': df_clusters_distribution,
               'df_clusters_equipment': df_clusters_equipment,
               'df_clusters_equipment_multi': df_clusters_equipment_multi,

               'df_monthly_usage_probability': df_monthly_usage_probability,

               'dict_boiler_profiles': dict_boiler_profiles}

    return results


# Migrated from src/Functions_Load_Emulator_v2.py:2082
def load_emulator_v2(
    num_user,
    data_input,
    calendar_df,
    calendar_daily,
    name=None,
    simulate_boiler=True,
    all_boiler_profiles=True,
    show_results=False,
    save_all_results=False,
    specific_appliance=None,
    parallelize=True,
    max_workers=1,
    results_path: Path | None = None,
):

    n_iterations = 12
    run_base_load = specific_appliance is None
    run_blp_profiles = specific_appliance is None or specific_appliance in data_input['list_appliances_blp']
    run_blnp_profiles = specific_appliance is None or specific_appliance in data_input['list_appliances_blnp']
    use_parallel = parallelize and (max_workers is None or max_workers > 1)

    with tqdm(total=n_iterations) as pbar:

        #---------------------------------------------------------------------------------------------
        # 0. Assign clusters to users and create dict_user
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Assign clusters to users")

        dict_users = assign_cluster_to_users(num_user, data_input['df_clusters_distribution'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 1. Assign appliances to users
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Assign appliances to users")

        if run_base_load:

            dict_users = assign_equipment_to_users(num_user, dict_users, data_input['df_clusters_equipment'], data_input['df_clusters_equipment_multi'])

        else:

            for u in dict_users.keys():

                dict_users[u]['appliances'] = {specific_appliance: {'number': 1},}

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 2. Evaluate daily activation matrix
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create daily activation matrix")

        dict_users = suppress_printing(create_daily_activation_matrix,
                                       dict_users,
                                       calendar_daily,
                                       data_input['dict_multi_usage_probability'],
                                       data_input['df_monthly_usage_probability'],
                                       )

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 3. Calculate scheduled consumption for appliance with "duty cycle profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with duty cycle profiles")

        # ---------------------------------------------------------------------------------------------
        # Create consumption for appliances with duty cycle profiles
        # ---------------------------------------------------------------------------------------------

        dc_args = (
            dict_users,
            data_input['list_appliances_dc'],
            data_input['dict_appliances_load'],
            data_input['dict_appliances_load_info'],
            calendar_df,
            calendar_daily,
            data_input['df_usage_probability_wd'],
            data_input['df_usage_probability_we'],
            pbar
        )

        if use_parallel:
            # Modifica PAOLO 07/05:
            # parallelizzazione della creazione dei profili duty cycle,
            # parte più time-consuming del processo di emulazione.
            dict_users = suppress_printing(
                create_dc_profiles_parallel,
                *dc_args,
                max_workers
            )
        else:
            dict_users = suppress_printing(
                create_dc_profiles,
                *dc_args
            )
            pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 4. Calculate scheduled consumption for appliance with "spike profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with spike profiles")

        dict_users = suppress_printing(create_spike_profiles,
                                       dict_users,
                                       data_input['list_appliances_sp'],
                                       data_input['dict_appliances_load'],
                                       data_input['dict_appliances_load_info'],
                                       calendar_df,
                                       calendar_daily,
                                       data_input['df_usage_probability_wd'],
                                       data_input['df_usage_probability_we'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 5. Calculate base load
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create base load")

        if run_base_load:

            dict_users = suppress_printing(create_base_load_profiles,
                                           dict_users,
                                           calendar_df,
                                           calendar_daily,
                                           data_input['dict_base_load_stats'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 6. Calculate scheduled consumption for appliance with "continuous with pattern profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with continuous pattern profiles")

        if run_blp_profiles:

            if use_parallel:
                dict_users = suppress_printing_keep_tqdm(
                    create_base_load_with_pattern_profiles_parallel,
                    dict_users,
                    data_input['list_appliances_blp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df,
                    max_workers,
                    show_user_progress=True
                )
            else:
                dict_users = suppress_printing(
                    create_base_load_with_pattern_profiles,
                    dict_users,
                    data_input['list_appliances_blp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df
                )
        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 7. Calculate scheduled consumption for appliance with "continuous without pattern profiles"
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for appliances with continuous no pattern profiles")

        if run_blnp_profiles:

            if use_parallel:
                dict_users = suppress_printing_keep_tqdm(
                    create_base_load_without_pattern_profiles_parallel,
                    dict_users,
                    data_input['list_appliances_blnp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df,
                    max_workers,
                    show_user_progress=True
                )
            else:
                dict_users = suppress_printing(
                    create_base_load_without_pattern_profiles,
                    dict_users,
                    data_input['list_appliances_blnp'],
                    data_input['dict_appliances_load'],
                    data_input['dict_appliances_load_info'],
                    calendar_df
                )

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 8. Calculate scheduled consumption for lighting
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for lighting")

        dict_users = suppress_printing(create_light_profiles,
                                       dict_users,
                                       calendar_df,
                                       calendar_daily,
                                       data_input['df_usage_probability_wd'],
                                       data_input['df_usage_probability_we'],
                                       data_input['dict_appliances_load'],
                                       data_input['dict_appliances_load_info'])

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 9. Calculate scheduled consumption for boiler
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Create consumption for boiler")

        if simulate_boiler:

            dict_users = suppress_printing(create_boiler_profiles,
                                        dict_users,
                                        calendar_df,
                                        calendar_daily,
                                        data_input['dict_boiler_profiles'],
                                        all_boiler_profiles)

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------
        # 10. Calculate total consumption for each user
        #---------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Aggregate load profile")

        if show_results:
            dict_users = aggregate_load_profile(dict_users, calendar_df, show_plot = True)
        else:
            dict_users = suppress_printing(aggregate_load_profile, dict_users, calendar_df, show_plot = False)

        pbar.update(1)

        #---------------------------------------------------------------------------------------------
        # 11. Save results
        #---------------------------------------------------------------------------------------------

        pbar.set_description("Save results")

        if save_all_results:
            if results_path is None:
                raise ValueError(
                    "save_all_results requires an explicit results_path"
                )
            suppress_printing(
                save_dictionary_to_pickle,
                dict_users,
                results_path / "dict_users_emulator_v2.pkl",
            )

        stacked_df = export_csv_emulator_v2(dict_users)

        pbar.update(1)

        pbar.set_description("Finished")

    return dict_users, stacked_df


# Migrated from src/Functions_Load_Emulator_v2.py:2340
def export_csv_emulator_v2(dict_users):

    csv_df = pd.DataFrame(index = dict_users['user_0']['appliances']['total_consumption'].index, columns = dict_users.keys())

    for u in dict_users.keys():
        csv_df[u] = dict_users[u]['appliances']['total_consumption'].copy()

    return csv_df


# Migrated from src/Functions_Load_Emulator_v2.py:2360
def export_emulated_load_profile_v2(
    dict_users,
    emulated_users_list,
    output_path: Path,
):

    csv_df = pd.DataFrame(index = dict_users['user_0']['appliances']['total_consumption'].index, columns = dict_users.keys())

    for u in dict_users.keys():
        csv_df[u] = dict_users[u]['appliances']['total_consumption'].copy()

    csv_df.columns = emulated_users_list
    csv_df.to_csv(output_path)


# Migrated from src/Functions_Load_Emulator_v2.py:2387
def run_load_emulator_v2(
    config: Mapping[str, Any],
    registry_users: Mapping[str, Mapping[str, Any]],
    simulate_boiler=True,
    all_boiler_profiles=True,
    show_results=False,
    save_all_results=False,
    specific_appliance=None,
    parallelize=True,
    max_workers=1,
):

    print(blue("\nCreate load profile for emulated users:", ['bold', 'underlined']), '\n')

    emulated_users_list = [registry_users[user_id]['user_type']
                        for user_id in registry_users
                            if (registry_users[user_id]['load_profile_id'] == 'emulated profile') and not (registry_users[user_id]['type'] == 'producer')]

    num_users = int(len(emulated_users_list)) # we calculate the number of users to simulate

    start_day = config['start_date']
    project_lifetime = config['project_lifetime_yrs']
    end_day = start_day.replace(year = start_day.year + project_lifetime) - timedelta(days=1)

    if num_users == 0:

        print('**** No emulated users found! ****')

    else:

        print('Recap:\n')
        print(f'    - Number of emulated users: {num_users}')
        print(f'    - Start day: {start_day}')
        print(f'    - End day: {end_day}')
        print(f'    - Project lifetime: {project_lifetime} years')

        #---------------------------------------------------------------------------------------------
        # 0. Create calendar
        #---------------------------------------------------------------------------------------------

        print(blue("\n0. Creating calendar:"), '\n')

        calendar_df, calendar_daily = create_calendar_dfs(start_day, end_day)

        print("     **** Calendar created! *****")

        #---------------------------------------------------------------------------------------------
        # 1. Import data: all input needed for the emulator
        #---------------------------------------------------------------------------------------------

        print(blue("\n1. Importing data:"), '\n')

        data_input = import_data_load_emulator_v2()

        print("     **** Data imported! *****")

        #---------------------------------------------------------------------------------------------
        # 2. Run emulator: create and exoport dict_users
        #---------------------------------------------------------------------------------------------

        print(blue("\n2. Running emulator:"), '\n')

        dict_users, stacked_df = load_emulator_v2(num_users,
                                data_input,
                                calendar_df,
                                calendar_daily,
                                show_results, # a progress bar and some plots with results will be shown
                                save_all_results, # save the results in a pickle file, disactivate if there are too many users!!
                                specific_appliance
                                )

        print("     **** Users emulated! *****")

        #---------------------------------------------------------------------------------------------
        # 3. Build the aggregate emulator result.
        #---------------------------------------------------------------------------------------------

        print(blue("\n3. Export results:"), '\n')

        export_emulated_load_profile_v2(dict_users, specific_appliance)

        print("     **** Results exported! *****")

        print("\n       **** Emulated load profiles exported! ****\n")

        return dict_users


# Migrated from src/Functions_Load_Emulator_v2.py:2469
def export_mean_profile_load_emulator_v2(
    stacked_df,
    output_path: Path,
):

    mean_profile = stacked_df.mean(axis=1)

    mean_profile = pd.DataFrame(mean_profile)

    mean_profile.columns = ['mean_profile']

    mean_profile.to_csv(output_path)

    print("     **** Mean profile exported! ****")


from source.load.DSM import DSM_load_profile_emulator
from source.load.profiles import (
    aggregate_load_profile,
    assign_cluster_to_users,
    assign_equipment_to_users,
    create_base_load_profiles,
    create_base_load_with_pattern_profiles,
    create_base_load_with_pattern_profiles_parallel,
    create_base_load_without_pattern_profiles,
    create_base_load_without_pattern_profiles_parallel,
    create_boiler_profiles,
    create_calendar_dfs,
    create_dc_profiles,
    create_dc_profiles_parallel,
    create_dict_appliances_load_info,
    create_light_profiles,
    create_list_profile_type,
    create_spike_profiles,
    load_profile_emulator,
    load_profile_all_users,
    remove_specific_appliance,
    suppress_printing,
)
from source.load.scheduling import create_daily_activation_matrix

suppress_printing_keep_tqdm = suppress_printing


LOAD_MODES = {"emulator_v1", "emulator_v2", "external"}


def run_load_pipeline(
    run_context: RunContext,
    config_results: ConfigResults,
    upstream_results: Any | None = None,
    options: PipelineOptions | None = None,
) -> LoadResults:
    selected_options = options or run_context.options.load
    supplied_profiles = _supplied_profiles(
        selected_options.settings.get("profiles", upstream_results)
    )

    if not selected_options.enabled:
        if supplied_profiles is None:
            raise ValueError(
                "The load pipeline can only be disabled when downstream load "
                "profiles are supplied explicitly"
            )
        return LoadResults(
            profiles={"load": supplied_profiles},
            metadata={
                "domain": "load",
                "enabled": False,
                "mode": "disabled",
                "status": "completed",
            },
        )

    mode = _load_mode(selected_options, config_results)
    if mode == "external":
        profiles = (
            supplied_profiles
            if supplied_profiles is not None
            else _load_external_profiles(run_context, selected_options.settings)
        )
        schedules: Mapping[str, Any] = {}
    else:
        emulated_profiles, schedules = _run_emulator(
            mode,
            run_context,
            config_results,
            selected_options.settings,
        )
        profiles = _assemble_user_profiles(
            run_context,
            config_results,
            emulated_profiles,
        )

    artifact = run_context.load_output / "load_profiles.csv"
    profiles.to_csv(artifact)
    artifacts = [artifact]
    dsm_profiles = schedules.get("dsm_profiles")
    if isinstance(dsm_profiles, pd.DataFrame):
        dsm_artifact = run_context.load_output / "dsm_load_profiles.csv"
        dsm_profiles.to_csv(dsm_artifact)
        artifacts.append(dsm_artifact)
    return LoadResults(
        profiles={"load": profiles},
        schedules=schedules,
        artifacts=tuple(artifacts),
        metadata={
            "domain": "load",
            "enabled": True,
            "mode": mode,
            "version": selected_options.version,
            "status": "completed",
        },
    )


def _load_mode(
    options: PipelineOptions,
    config_results: ConfigResults,
) -> str:
    configured = options.version or config_results.configuration.get(
        "load_emulator_version",
        "version_1",
    )
    aliases = {
        "version_1": "emulator_v1",
        "version_2": "emulator_v2",
        "v1": "emulator_v1",
        "v2": "emulator_v2",
    }
    mode = aliases.get(str(configured), str(configured))
    if mode not in LOAD_MODES:
        raise ValueError(
            f"Unsupported load mode {configured!r}; expected one of "
            f"{sorted(LOAD_MODES)}"
        )
    return mode


def _supplied_profiles(value: Any) -> pd.DataFrame | None:
    if value is None:
        return None
    if isinstance(value, LoadResults):
        value = value.profiles.get("load")
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return None


def _load_external_profiles(
    run_context: RunContext,
    settings: Mapping[str, Any],
) -> pd.DataFrame:
    configured_path = settings.get("path")
    if configured_path is None:
        raise ValueError(
            "External load mode requires a DataFrame in settings['profiles'] "
            "or a CSV path in settings['path']"
        )
    path = resolve_path(run_context.repository_root, configured_path)
    if not path.is_file():
        raise FileNotFoundError(f"External load profile not found: {path}")
    frame = pd.read_csv(path, index_col=0)
    frame.index.name = frame.index.name or "datetime"
    return frame


def _run_emulator(
    mode: str,
    run_context: RunContext,
    config_results: ConfigResults,
    options: Mapping[str, Any],
) -> tuple[pd.DataFrame, Mapping[str, Any]]:
    if config_results.normalized is None:
        raise ValueError("The load emulator requires normalized configuration results")

    users = {
        user_id: values
        for user_id, values in config_results.normalized.registries.users.items()
        if values["load_profile_id"] == "emulated profile"
        and values["type"] != "producer"
    }
    if run_context.random_seed is not None:
        random.seed(run_context.random_seed)
        np.random.seed(run_context.random_seed)

    if not users:
        calendar_frame = config_results.normalized.calendars.calendar
        empty = pd.DataFrame(index=pd.to_datetime(calendar_frame["datetime"]))
        empty.index.name = "datetime"
        return empty, {}

    settings = config_results.configuration
    if mode == "emulator_v1":
        return _run_emulator_v1(run_context, settings, users, options)
    return _run_emulator_v2(run_context, settings, users, options)


def _run_emulator_v1(
    run_context: RunContext,
    settings: Mapping[str, Any],
    users: Mapping[str, Mapping[str, Any]],
    options: Mapping[str, Any],
) -> tuple[pd.DataFrame, Mapping[str, Any]]:
    appliance_path = resolve_path(
        run_context.repository_root,
        settings["filename_appliances_load"],
    )
    probability_path = resolve_path(
        run_context.repository_root,
        settings["filename_usage_probability"],
    )
    appliance_load = pd.read_excel(
        appliance_path,
        header=0,
        index_col=0,
        sheet_name="load_profile",
    )
    probabilities = pd.read_excel(
        probability_path,
        header=0,
        index_col=0,
        sheet_name=None,
    )
    start_day = settings["start_date"]
    end_day = start_day.replace(
        year=start_day.year + int(settings["project_lifetime_yrs"])
    ) - timedelta(days=1)
    emulated_user_types = [values["user_type"] for values in users.values()]
    profiles, start_times, daily_profiles = load_profile_emulator(
        emulated_user_types,
        start_day,
        end_day,
        bool(options.get("reuse_start_times", False)),
        bool(options.get("optimized_dsm", False)),
        bool(options.get("all_appliances", True)),
        bool(options.get("daily_activation", True)),
        bool(options.get("multiple_daily_uses", True)),
        appliance_load_df=appliance_load,
        usage_probability_df=probabilities["daily_usage_probability"],
        num_daily_usage_probability_df=probabilities["num_of_uses"],
        week_usage_probability_df=probabilities["week_usage_probability"],
        prior_start_times=options.get("start_times"),
    )
    schedules: dict[str, Any] = {
        "appliance_start_times": start_times,
        "daily_profiles": daily_profiles,
    }
    dsm_users = [
        values["user_type"]
        for values in users.values()
        if bool(values["flag_DSM"])
    ]
    if dsm_users:
        dsm_profiles, dsm_start_times, dsm_daily_profiles = (
            DSM_load_profile_emulator(
                emulated_user_types,
                dsm_users,
                start_day,
                end_day,
                bool(options.get("all_appliances", True)),
                bool(options.get("daily_activation", True)),
                bool(options.get("multiple_daily_uses", True)),
                appliance_load_df=appliance_load,
                usage_probability_DSM_df=probabilities[
                    "daily_usage_probability_DSM"
                ],
                num_daily_usage_probability_df=probabilities["num_of_uses"],
                week_usage_probability_df=probabilities[
                    "week_usage_probability"
                ],
                start_time_dict=start_times,
            )
        )
        schedules.update(
            {
                "dsm_profiles": dsm_profiles,
                "dsm_appliance_start_times": dsm_start_times,
                "dsm_daily_profiles": dsm_daily_profiles,
            }
        )
    return profiles, schedules


def _run_emulator_v2(
    run_context: RunContext,
    settings: Mapping[str, Any],
    users: Mapping[str, Mapping[str, Any]],
    options: Mapping[str, Any],
) -> tuple[pd.DataFrame, Mapping[str, Any]]:
    start_day = settings["start_date"]
    end_day = start_day.replace(
        year=start_day.year + int(settings["project_lifetime_yrs"])
    ) - timedelta(days=1)
    calendar_frame, daily_calendar = create_calendar_dfs(start_day, end_day)
    data_input = import_data_load_emulator_v2(
        settings,
        run_context.repository_root,
    )
    specific_appliance = options.get("specific_appliance")
    if specific_appliance is not None:
        data_input = remove_specific_appliance(data_input, specific_appliance)
    emulated, profiles = load_emulator_v2(
        len(users),
        data_input,
        calendar_frame,
        daily_calendar,
        simulate_boiler=bool(options.get("simulate_boiler", True)),
        all_boiler_profiles=bool(options.get("all_boiler_profiles", True)),
        show_results=bool(options.get("show_results", False)),
        save_all_results=False,
        specific_appliance=specific_appliance,
        parallelize=bool(options.get("parallelize", True)),
        max_workers=int(options.get("max_workers", 1)),
    )
    profiles = profiles.copy()
    profiles.columns = [values["user_type"] for values in users.values()]
    return profiles, {"users": emulated}


def _assemble_user_profiles(
    run_context: RunContext,
    config_results: ConfigResults,
    emulated_profiles: pd.DataFrame,
) -> pd.DataFrame:
    if config_results.normalized is None:
        raise ValueError("Normalized configuration is required to build load profiles")

    settings = config_results.configuration
    user_types = config_results.normalized.registries.user_types
    profile_ids = {
        values["load_profile_id"]
        for values in user_types.values()
        if bool(values["consuming"])
    }
    arera_profiles = None
    if "arera" in profile_ids:
        arera_profiles = pd.read_csv(
            resolve_path(
                run_context.repository_root,
                settings["filename_user_load_arera"],
            )
        )

    real_profiles = None
    if "real profile" in profile_ids:
        real_path = settings.get("filename_load")
        if real_path is None:
            raise ValueError("filename_load is required for real load profiles")
        real_profiles = pd.read_csv(
            resolve_path(run_context.repository_root, real_path),
            index_col="datetime",
        )
        real_profiles.index = pd.to_datetime(real_profiles.index)

    standard_ids = {"arera", "real profile", "emulated profile", None}
    custom_ids = sorted(profile_ids.difference(standard_ids))
    custom_profiles = None
    weekly_factors = None
    yearly_factor = None
    if custom_ids:
        workbook_path = resolve_path(
            run_context.repository_root,
            settings["filename_carico_input"],
        )
        custom_profiles = {
            profile_id: pd.read_excel(
                workbook_path,
                sheet_name=profile_id,
                usecols="A:N",
                index_col=0,
            )
            for profile_id in custom_ids
        }
        weekly_factors = {
            profile_id: pd.read_excel(
                workbook_path,
                sheet_name=profile_id,
                usecols="P:S",
                index_col=0,
            )
            for profile_id in custom_ids
        }
        yearly_factor = pd.read_excel(
            workbook_path,
            sheet_name="Yearly_Variation",
            index_col=0,
        )

    municipalities = config_results.data_structures["municipalities"]
    region = province_to_region(settings["provincia_it"], municipalities)
    return load_profile_all_users(
        config_results.normalized.calendars.calendar,
        user_types,
        region=region,
        delta_t=settings["delta_t"],
        rand_factor=settings["rand_factor"],
        user_load_arera=arera_profiles,
        real_profile_df=real_profiles,
        emulated_load_profile_df=(
            emulated_profiles if not emulated_profiles.empty else None
        ),
        custom_profiles=custom_profiles,
        weekly_factors=weekly_factors,
        yearly_factor=yearly_factor,
    )
