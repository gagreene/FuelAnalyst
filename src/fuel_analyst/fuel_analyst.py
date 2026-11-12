# -*- coding: utf-8 -*-
"""
Created on Tue May 28, 15:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
import pandas as pd
from typing import Optional

from .components import error_handling
from .components import helper
from .components import table_reader
from .components import plot_attributes as pa
from .components import plants_regen as pr
from .components import trees
from .components import tree_sampling
from .components import canopy_cover as cc
from .components import woody_debris as wd
from .components import conpyro_attributes
from .components import fofem_attributes
from .components import fofem_units

# Re-export the public default configuration dictionaries.
from .components._default_configs import (
    default_tree_sampling_dict,
    default_stand_summary_dict,
    default_woody_debris_dict,
    default_conpyro_dict,
    default_fofem_consume_dict,
)


# Metrics fixed by the default dictionaries, keyed by an entry's resolved att_source.
# Attributes that are BA-weighted (ht, cbh, dcbh, fsg, flame_length, fire_intensity) are not
# listed because their comments describe allowed options rather than a fixed value.
_FIXED_STAND_SUMMARY_METRICS = {
    'dens': ['sum'],
    'ba': ['sum'],
    'cfl': ['sum'],
    'foliage': ['sum'],
    'branches': ['sum'],
    'wood': ['sum'],
    'bark': ['sum'],
    'foliage_fofem': ['sum'],
    'branches_fofem': ['sum'],
    'cbd': [],
}

# ConPyro stand attributes must each produce one column, so these fixed-name entries hold exactly
# one metric chosen from _SINGLE_METRIC_OPTIONS; anything else falls back to the default.
_SINGLE_METRIC_CONPYRO_ENTRIES = (
    'conpyro_ht_ovrstry_live',
    'conpyro_ht_midstry_live',
    'conpyro_ht_midstry_dead',
    'conpyro_cbh_ovrstry',
    'conpyro_cbh_midstry',
    'conpyro_fsg',
)
_SINGLE_METRIC_OPTIONS = ('min', 'max', 'mean')
_SINGLE_METRIC_DEFAULT = ['mean']


def _enforce_fixed_stand_summary_metrics(stand_summary_params: dict) -> dict:
    """
    Replace user-supplied metrics that the default dictionaries mark as fixed.

    Entries are matched by their resolved att_source (the entry key when att_source is
    omitted). The fixed-by-attribute rule wins over the single-metric ConPyro rule. The
    input dictionary and its nested entries are never modified.

    :param stand_summary_params: Stand-summary entries keyed by entry name.
    :return: A new dictionary in which every fixed attribute's metrics equal the fixed list and
        each single-metric ConPyro entry holds exactly one of min, max, or mean. Entries already
        correct are returned unchanged; each override is logged once as a warning with issue
        code 'fixed_metrics_overridden' or 'single_metric_overridden'.
    """
    enforced = dict(stand_summary_params)
    for name, params in stand_summary_params.items():
        requested = params.get('metrics')
        if requested is None:
            requested = []
        elif isinstance(requested, str):
            requested = [requested]
        else:
            # Repeated metrics add nothing (and would otherwise look like several metrics).
            requested = list(dict.fromkeys(requested))
        att = params.get('att_source', name)
        fixed = _FIXED_STAND_SUMMARY_METRICS.get(att)
        if fixed is not None:
            if requested == fixed:
                if params.get('metrics') != fixed:
                    # Same metrics in a non-list form (None, 'sum'); store the list silently.
                    enforced[name] = {**params, 'metrics': list(fixed)}
                continue
            error_handling.get_logger('trees').warning(
                f"Stand summary '{name}' (att_source '{att}') has fixed metrics {fixed}; "
                f"the requested metrics {requested} were replaced.",
                extra={'issue_code': 'fixed_metrics_overridden'}
            )
            enforced[name] = {**params, 'metrics': list(fixed)}
        elif name in _SINGLE_METRIC_CONPYRO_ENTRIES:
            if len(requested) == 1 and requested[0] in _SINGLE_METRIC_OPTIONS:
                if params.get('metrics') != requested:
                    enforced[name] = {**params, 'metrics': requested}
                continue
            error_handling.get_logger('trees').warning(
                f"ConPyro stand attribute '{name}' must have exactly one metric from "
                f"{list(_SINGLE_METRIC_OPTIONS)}; the requested metrics {requested} were "
                f"replaced with {_SINGLE_METRIC_DEFAULT}.",
                extra={'issue_code': 'single_metric_overridden'}
            )
            enforced[name] = {**params, 'metrics': list(_SINGLE_METRIC_DEFAULT)}
    return enforced


def _find_id_mismatches(plot_ids, form_ids) -> tuple[list, list]:
    """
    Return ordered, deduplicated IDs missing from either side of a form merge.

    :param plot_ids: Plot Attribute identifiers in first-seen order.
    :param form_ids: Component-form identifiers in first-seen order.
    :return: IDs missing from the form and IDs missing from Plot Attributes.
    """
    plot_ids = list(plot_ids)
    form_ids = list(form_ids)
    plot_id_set = set(plot_ids)
    form_id_set = set(form_ids)
    missing_from_form = list(dict.fromkeys(
        unique_id for unique_id in plot_ids if unique_id not in form_id_set
    ))
    extra_in_form = list(dict.fromkeys(
        unique_id for unique_id in form_ids if unique_id not in plot_id_set
    ))
    return missing_from_form, extra_in_form


def _log_missing_tree_mortality_inputs(plot_ids: list, reason: str) -> None:
    """
    Report requested GUI mortality inputs that lack a matching Trees parent.

    :param plot_ids: Canonical plot identities that selected Trees.
    :param reason: Missing, empty, or unmatched parent-table explanation.
    :return: None. Logs one warning per affected plot before skipping GUI input generation.
    """
    for unique_id in dict.fromkeys(plot_ids):
        error_handling.get_logger('trees').warning(
            'FOFEM GUI tree-mortality input was not generated: %s.', reason,
            extra={'unique_id': unique_id, 'issue_code': 'fofem_gui_missing_tree_parent'},
        )


def _prepare_tree_model_inputs(df: pd.DataFrame, tree_columns: list, log_drops: bool = True) -> pd.DataFrame:
    """
    Select model inputs without changing the master inventory or plain stand summaries.

    :param df: Plot data after the selected form tables have been merged.
    :param tree_columns: Tree-derived fields to ignore in the model copy when Trees is unticked.
    :param log_drops: Whether ConPyro or FOFEM consumption output was requested.
    :return: Eligible model copy; logs one reason per dropped plot and an all-dropped
        summary when applicable. The master inventory remains unchanged.
    """
    eligible, reasons = helper.get_tree_model_eligibility(df)
    result = df.copy()
    if log_drops:
        helper.log_tree_model_issues(result, eligible, reasons)
        if not eligible.any():
            error_handling.get_logger('trees').error(
                'No plots are eligible for ConPyro or FOFEM consumption; requested model-input files will be empty.',
                extra={'issue_code': 'tree_model_inputs_all_dropped'},
            )
    model = result.loc[eligible].copy()
    selected = model.get('form_select', pd.Series('trees', index=model.index)).fillna('').str.contains(r'\btrees\b')
    columns = [column for column in tree_columns if column in model]
    model[columns] = model[columns].mask(~selected, axis=0)
    return model


def _report_tree_sampling_error(error: tree_sampling.TreeSamplingError, out_dir: str) -> None:
    """
    Report an invalid sampling dictionary before aborting the run.

    :param error: Configuration validation error to log and re-raise.
    :param out_dir: Directory for the run's error report.
    :return: None; writes fuelanalyst_errors.csv and raises the original error.
    """
    error_handling.get_logger('trees').error(str(error), extra={'issue_code': error.issue_code})
    error_handling.write_report(os.path.join(out_dir, 'fuelanalyst_errors.csv'))
    raise error


def _validate_stand_summary_permutations(stand_summary_params: dict, out_dir: str) -> None:
    """Report and reject combined stand summaries with no usable tree group.

    :param stand_summary_params: Configured stand attributes and summary modes.
    :param out_dir: Directory for the run's error report.
    :return: None. Writes fuelanalyst_errors.csv before rejecting invalid input.
    """
    invalid_attributes = [
        name for name, params in stand_summary_params.items()
        if params.get('summary_permutation', 'all') == 'combined'
        and not any(part != 'total' for part in params.get('summary', []))
    ]
    if invalid_attributes:
        message = (
            "summary_permutation='combined' requires at least one summary "
            "other than 'total' for: " + ', '.join(invalid_attributes)
        )
        error_handling.get_logger('trees').error(
            message, extra={'issue_code': 'combined_summary_total_only'}
        )
        error_handling.write_report(os.path.join(out_dir, 'fuelanalyst_errors.csv'))
        raise ValueError(message)


@error_handling.run_guard
def fuel_analyst(
        in_dir: str,
        out_dir: str,
        surface_fire_intensity_model: str,
        stand_summary_params: Optional[dict] = None,
        woody_debris_params: Optional[dict] = None,
        conpyro_params: Optional[dict] = None,
        fofem_consume_params: Optional[dict] = None,
        gen_conpyro_df: bool = False,
        gen_fofem_gui_app_tree_df: bool = False,
        gen_fofem_consume_df: bool = False,
        tree_sampling_params: Optional[dict] = None
) -> None:
    """
    Process Survey123 fuel attributes and write the selected result tables.

    :param in_dir: Path to the input folder containing the survey data: one folder per form (1_Plot_Attributes, ...),
        each holding that form's tables as CSV files, an Excel workbook (.xlsx, .xlsm), or an unzipped file geodatabase
        (.gdb), as downloaded from ArcGIS Survey123 or ArcGIS Online. The format is detected for each form.
    :param out_dir: Path to the output folder where results will be saved.
    :param surface_fire_intensity_model: Model to use for surface fire intensity calculations.
    :param stand_summary_params: Dictionary containing stand summary parameters.
    :param woody_debris_params: Dictionary containing parameters for woody debris processing.
    :param conpyro_params: Dictionary containing ConPyro parameters.
    :param fofem_consume_params: Dictionary containing FOFEM consumption parameters, including
        'fofem_processing_units' ('SI' or 'Imperial'; defaults to 'SI' when the key is absent,
        for backward compatibility with dictionaries predating this option). Determines both the
        units written into the FOFEM consumption DataFrame and its output filename (see
        fofem_units.consume_filename()).
    :param gen_conpyro_df: Boolean indicating whether to generate the ConPyro DataFrame.
    :param gen_fofem_gui_app_tree_df: Boolean indicating whether to generate the FOFEM GUI app tree mortality DataFrame.
    :param gen_fofem_consume_df: Boolean indicating whether to generate the FOFEM consumption DataFrame.
    :param tree_sampling_params: Sampling DBH thresholds and optional parent protocol overrides.
        Defaults to default_tree_sampling_dict; independent of stand-summary output classes.
    :return: None. Every completed run writes master_fuel_df.csv and
        fuelanalyst_errors.csv; model-preparation outputs depend on the generation
        flags.
    """
    try:
        tree_sampling_params = tree_sampling.normalize_tree_sampling_params(
            default_tree_sampling_dict if tree_sampling_params is None else tree_sampling_params
        )
    except tree_sampling.TreeSamplingError as error:
        _report_tree_sampling_error(error, out_dir)

    # Create the list of forms to process
    form_select_list = ['plants', 'trees', 'cover', 'woody']

    # Create a dictionary to map form names to their respective directory names
    dir_dict = {
        'plot': '1_Plot_Attributes',
        'plants': '2_Plants_Regeneration',
        'trees': '3_Trees',
        'cover': '4_Canopy_Cover',
        'woody': '5_Woody_Debris'
    }

    # Create a dictionary to map form names to their display names
    form_dict = {
        'plot': 'Plot Attributes',
        'plants': 'Plants and Regeneration',
        'trees': 'Trees',
        'cover': 'Canopy Cover',
        'woody': 'Woody Debris'
    }

    # Resolve where each form's tables live (CSV folder, Excel workbook, or file geodatabase), once and only when needed
    form_sources = {}

    def get_form_source(form: str):
        """
        Resolve a form's source on first use.

        :param form: Form key ('plot', 'plants', 'trees', 'cover', or 'woody').
        :return: FormSource for the form, or None when the form folder is absent.
        """
        if form not in form_sources:
            form_sources[form] = table_reader.resolve_form_source(in_dir, dir_dict.get(form))
        return form_sources[form]

    if stand_summary_params is None:
        stand_summary_params = default_stand_summary_dict
    # Work on a copy: the ConPyro and FOFEM entries are merged into it below, which must not
    # change the caller's dictionary or the module-level default.
    stand_summary_params = dict(stand_summary_params)

    if woody_debris_params is None:
        woody_debris_params = default_woody_debris_dict
    # Work on copies: the ConPyro and FOFEM woody-debris classes are merged into the nested
    # dictionary below, which must not change the caller's dictionary or the module-level default.
    woody_debris_params = dict(woody_debris_params)
    woody_debris_params['woody_debris_classes'] = dict(woody_debris_params['woody_debris_classes'])

    if conpyro_params is None:
        conpyro_params = default_conpyro_dict

    if fofem_consume_params is None:
        fofem_consume_params = default_fofem_consume_dict

    if gen_conpyro_df:
        # Other source forms remain required; missing Trees is handled per plot as unknown.
        missing_forms = [
            form for form in form_select_list
            if form != 'trees' and get_form_source(form) is None
        ]
        if missing_forms:
            raise FileNotFoundError(
                f'Plot, Plants and Regeneration, Canopy Cover, and Woody Debris forms are required to generate the ConPyro DataFrame. '
                f'The following forms are missing:\n{missing_forms}.'
            )

        stand_summary_params.update(
            {k: v for k, v in conpyro_params['stand_attributes'].items()}
        )
        woody_debris_params['woody_debris_classes'].update(conpyro_params['woody_debris_classes'])

    if gen_fofem_consume_df:
        # Plants and Woody Debris provide required surface inputs. Trees eligibility is
        # resolved per plot; absent Trees data never supplies fabricated zero canopy fuels.
        missing_forms = [
            form for form in ['plants', 'woody']
            if get_form_source(form) is None
        ]
        if missing_forms:
            raise FileNotFoundError(
                f'Plants and Regeneration and Woody Debris are required to generate '
                f'the FOFEM consumption DataFrame. The following forms are missing:\n{missing_forms}.'
            )

        stand_summary_params.update(
            {k: v for k, v in fofem_consume_params['canopy_fuels'].items() if k != 'woody_debris_classes'}
        )
        woody_debris_params['woody_debris_classes'].update(fofem_consume_params['woody_debris_classes'])

    stand_summary_params = _enforce_fixed_stand_summary_metrics(stand_summary_params)
    _validate_stand_summary_permutations(stand_summary_params, out_dir)

    # Generate a list of columns to keep, using all columns in plot_df to begin with
    keep_columns = ['unique_id']
    tree_output_columns = []
    form_df = None
    master_tree_df = None
    conpyro_df = None
    fbp_prep_df = None
    fofem_tree_df = None
    fofem_consume_df = None
    fofem_processing_units = None

    # Process plot attributes
    plot_df, add_columns = pa.process_plot_attributes(get_form_source('plot') or os.path.join(in_dir, dir_dict.get('plot')),
                                                      os.path.join(out_dir, dir_dict.get('plot')))
    keep_columns.extend(add_columns)

    report_gui_parent_issues = gen_fofem_gui_app_tree_df

    # Process selected forms
    for form in form_select_list:
        # Get the output path for the current form
        out_path = os.path.join(out_dir, dir_dict.get(form))

        # Filter the plot_df for the current form
        mask = plot_df['form_select'].str.contains(form, na=False)

        # Get the unique IDs for the current form
        id_list = plot_df.loc[mask, 'unique_id'].tolist()

        # Nothing to do for a form that no plot selected
        if not mask.any():
            continue

        # Resolve the form's tables (CSV folder, Excel workbook, or file geodatabase); a missing folder is reported per plot
        form_source = get_form_source(form)
        if form_source is None:
            if form == 'trees' and report_gui_parent_issues:
                _log_missing_tree_mortality_inputs(id_list, 'Trees parent folder is missing')
                continue
            if form == 'trees' and (gen_conpyro_df or gen_fofem_consume_df):
                continue  # The shared model-eligibility check reports missing Trees once per plot.
            for missing_id in id_list:
                error_handling.get_logger(form).warning(
                    f'Input folder for {form_dict[form]} is missing but this plot '
                    f'selected this form; it will have no {form_dict[form]} data.',
                    extra={'unique_id': missing_id, 'issue_code': 'form_folder_missing'},
                )
            continue

        # Only process the form if there are IDs to process
        if mask.any():
            if form == 'plants':
                form_df, add_columns = pr.process_plants_regen(form_source, out_path)
            elif form == 'trees':
                if not table_reader.has_table(form_source, 'survey_0'):
                    if report_gui_parent_issues:
                        _log_missing_tree_mortality_inputs(id_list, 'Trees parent table is missing')
                    continue
                protocol_column = tree_sampling_params['protocol_column']
                literal_columns = (protocol_column,) if protocol_column is not None else ()
                tree_parents = table_reader.read_table(form_source, 'survey_0', literal_text_columns=literal_columns)
                if tree_parents.empty:
                    if report_gui_parent_issues:
                        _log_missing_tree_mortality_inputs(id_list, 'Trees parent table is empty')
                    continue
                parent_ids = helper.get_unique_id(tree_parents)['unique_id']
                if not parent_ids.isin(id_list).any():
                    if report_gui_parent_issues:
                        _log_missing_tree_mortality_inputs(id_list, 'Trees parent identifiers do not match the selected plots')
                    continue
                (form_df, add_columns,
                 master_tree_df) = trees.process_trees(form_source,
                                                       out_path,
                                                       surface_fire_intensity_model,
                                                       stand_summary_params,
                                                       gen_conpyro_df,
                                                       tree_sampling_params=tree_sampling_params,
                                                       selected_plot_ids=set(id_list),
                                                       parent_df=tree_parents)
            elif form == 'cover':
                form_df, add_columns = cc.process_canopy_cover(form_source, out_path)
            elif form == 'woody':
                form_df, add_columns = wd.process_woody_debris(form_source, out_path, plot_df[mask], woody_debris_params)

            if form == 'trees':
                tree_output_columns = list(add_columns)
                # A Trees record cannot establish observations for a plot that did not select Trees.
                form_df = form_df.loc[form_df['unique_id'].isin(id_list)]

            # Add the new columns to the keep_columns list
            keep_columns.extend(add_columns)

            # Verify that all IDs in id_list are present in the form_df, and vice versa
            missing_from_form, extra_in_form = _find_id_mismatches(
                id_list, form_df['unique_id'].values
            )
            if missing_from_form or extra_in_form:
                print(f'\tWarning:')
                for missing_id in missing_from_form:
                    if form == 'trees' and report_gui_parent_issues:
                        _log_missing_tree_mortality_inputs([missing_id], 'Trees parent row is missing')
                        continue
                    if form == 'trees' and (gen_conpyro_df or gen_fofem_consume_df):
                        continue
                    error_handling.get_logger(form).warning(
                        f'Plot is in the Plot Attributes dataset but not in {form_dict[form]}.',
                        extra={'unique_id': missing_id, 'issue_code': 'id_missing_from_form'},
                    )
                for extra_id in extra_in_form:
                    error_handling.get_logger(form).warning(
                        f'Plot is in the {form_dict[form]} dataset but not in Plot Attributes.',
                        extra={'unique_id': extra_id, 'issue_code': 'id_extra_in_form'},
                    )
            else:
                print(f'\tAll IDs from the Plot Attributes dataset are present in the {form} dataset. Merging data.')

            # Drop columns in form_df that are already in plot_df, except for unique_id
            form_df = form_df.drop(
                columns=[col for col in form_df.columns if col in plot_df.columns and col != 'unique_id']
            )

            # Merge the form_df with plot_df based on unique_id
            plot_df = pd.merge(plot_df, form_df, on='unique_id', how='left')

    model_plot_df = None
    if gen_conpyro_df or gen_fofem_consume_df:
        model_plot_df = _prepare_tree_model_inputs(plot_df, tree_output_columns)

    # ### PROCESS ConPyro DATA
    if gen_conpyro_df:
        conpyro_df, fbp_prep_df = conpyro_attributes.gen_conpyro_df(model_plot_df, conpyro_params)

    # ### PROCESS FOFEM DATA
    if gen_fofem_gui_app_tree_df and master_tree_df is not None:
        fofem_tree_df = fofem_attributes.gen_fofem_gui_app_tree_df(plot_df, master_tree_df)
    if gen_fofem_consume_df:
        fofem_processing_units = fofem_units.validate_fofem_units(
            fofem_consume_params.get('fofem_processing_units', 'SI')
        )
        fofem_consume_df = fofem_attributes.gen_fofem_consumption_df(model_plot_df, fofem_consume_params)

    # ### PROCESS OUTPUTS
    # Make the out_dir if it does not exist
    os.makedirs(out_dir, exist_ok=True)

    # Save the Master Fuel DataFrame to the output folder if it exists
    if plot_df is not None:
        master_df_path = os.path.join(out_dir, 'master_fuel_df.csv')
        print(f'\n\nSaving the Master Fuel DataFrame to: {master_df_path}')
        plot_df = plot_df[keep_columns]  # Keep only the specified columns
        helper.export_csv(plot_df, master_df_path)

    error_report_path = os.path.join(out_dir, 'fuelanalyst_errors.csv')
    print(f'Saving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=plot_df)

    # Save the Master Tree DataFrame to the output folder if it exists
    if master_tree_df is not None:
        master_tree_df_path = os.path.join(out_dir, 'master_tree_df.csv')
        print(f'Saving the Master Tree DataFrame to: {master_tree_df_path}')
        helper.export_csv(master_tree_df, master_tree_df_path)

    # Save the ConPyro DataFrame to the output folder if it exists
    if conpyro_df is not None:
        conpyro_df_path = os.path.join(out_dir, 'conpyro_df.csv')
        print(f'Saving the ConPyro DataFrame to: {conpyro_df_path}')
        helper.export_csv(conpyro_df, conpyro_df_path)

    if fbp_prep_df is not None:
        fbp_df_path = os.path.join(out_dir, 'fbp_prep_df.csv')
        print(f'Saving the FBP Prep DataFrame to: {fbp_df_path}')
        helper.export_csv(fbp_prep_df, fbp_df_path)

    # Save the FOFEM GUI App Tree Mortality DataFrame to the output folder if it exists
    if fofem_tree_df is not None:
        fofem_tree_df_path = os.path.join(out_dir, 'fofem_gui_app_tree_mortality_df.csv')
        print(f'Saving the FOFEM GUI App Tree Mortality DataFrame to: {fofem_tree_df_path}')
        helper.export_csv(fofem_tree_df, fofem_tree_df_path)

    # Save the FOFEM Consumption DataFrame to the output folder if it exists
    if fofem_consume_df is not None:
        fofem_consume_df_path = os.path.join(out_dir, fofem_units.consume_filename(fofem_processing_units))
        print(f'Saving the FOFEM Consumption DataFrame to: {fofem_consume_df_path}')
        helper.export_csv(fofem_consume_df, fofem_consume_df_path)

    return


# Test routine for Fuel Analyst
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_dir = os.path.join(examples_dir, 'data', 'Survey123_Data')
    _out_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _surface_fire_intensity_model = 'Byram'
    _stand_summary_dict = None      # Uses default stand summary settings if None
    _woody_debris_dict = None       # Uses default woody debris settings if None
    _conpyro_dict = None            # Uses default ConPyro settings if None
    _fofem_consume_dict = None      # Uses default FOFEM woody debris settings if None
    _gen_conpyro_df = True          # Whether to generate the ConPyro DataFrame
    _gen_fofem_gui_app_tree_df = False  # Whether to generate the FOFEM GUI app tree mortality DataFrame
    _gen_fofem_consume_df = True    # Whether to generate the FOFEM consumption DataFrame

    # Run the main fuel_analyst function
    fuel_analyst(in_dir=_in_dir,
                 out_dir=_out_dir,
                 surface_fire_intensity_model=_surface_fire_intensity_model,
                 stand_summary_params=_stand_summary_dict,
                 woody_debris_params=_woody_debris_dict,
                 conpyro_params=_conpyro_dict,
                 fofem_consume_params=_fofem_consume_dict,
                 gen_conpyro_df=_gen_conpyro_df,
                 gen_fofem_gui_app_tree_df=_gen_fofem_gui_app_tree_df,
                 gen_fofem_consume_df=_gen_fofem_consume_df)
