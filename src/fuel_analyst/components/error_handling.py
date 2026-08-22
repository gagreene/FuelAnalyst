"""
Centralized error/warning collection for FuelAnalyst.

Components report issues through the standard `logging` module:
    logger = logging.getLogger(__name__)
    logger.warning("...", extra={'unique_id': plot_id, 'issue_code': 'some_code'})

start_run() attaches a fresh collecting handler for the duration of one
pipeline run; write_report() pivots everything collected into a single CSV
(one row per plot with >=1 issue, plus a reserved 'General Error' row for
issues with no unique_id) and detaches the handler. When the application has
not configured logging, start_run() also attaches a console StreamHandler
(formatted by _ConsoleFormatter) so output is preserved: attaching the
collector suppresses Python's logging.lastResort fallback. If an application
has already configured a non-null handler on this namespace or an ancestor,
FuelAnalyst relies on that handler instead of duplicating its output.
"""
import logging
import os
import sys
from collections import defaultdict
from functools import wraps
from typing import Optional

import pandas as pd

_LOGGER_NAME_ROOT = 'fuel_analyst'

_FORM_DISPLAY_NAMES = {
    'plot': 'Plot Attributes',
    'plants': 'Plants and Regeneration',
    'trees': 'Trees',
    'cover': 'Canopy Cover',
    'woody': 'Woody Debris',
}

_FORM_LOGGER_NAMES = {
    'plot': f'{_LOGGER_NAME_ROOT}.components.plot_attributes',
    'plants': f'{_LOGGER_NAME_ROOT}.components.plants_regen',
    'trees': f'{_LOGGER_NAME_ROOT}.components.trees',
    'cover': f'{_LOGGER_NAME_ROOT}.components.canopy_cover',
    'woody': f'{_LOGGER_NAME_ROOT}.components.woody_debris',
}

GENERAL_ERROR_ROW = 'General Error'
_IDENTITY_COLUMNS = ['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id']

_active_handler: Optional['_CollectingHandler'] = None
_console_handler: Optional[logging.StreamHandler] = None
_previous_level: Optional[int] = None


class _CollectingHandler(logging.Handler):
    """Collects LogRecords for fuel_analyst.* loggers without affecting other handlers."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _ConsoleFormatter(logging.Formatter):
    """Appends the affected plot ID to console output when a record carries one."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        unique_id = getattr(record, 'unique_id', None)
        if unique_id is not None and not pd.isna(unique_id) and unique_id != GENERAL_ERROR_ROW:
            message = f'{message} (plot: {unique_id})'
        return message


def _detach_handlers() -> None:
    """Detach run-scoped handlers and restore the previous logger level."""
    global _active_handler, _console_handler, _previous_level
    root_logger = logging.getLogger(_LOGGER_NAME_ROOT)
    if _active_handler is not None:
        root_logger.removeHandler(_active_handler)
    if _console_handler is not None:
        root_logger.removeHandler(_console_handler)
    if _previous_level is not None:
        root_logger.setLevel(_previous_level)
    _active_handler = None
    _console_handler = None
    _previous_level = None


def _form_for_record(record: logging.LogRecord) -> str:
    for form, logger_name in _FORM_LOGGER_NAMES.items():
        if record.name == logger_name or record.name.startswith(logger_name + '.'):
            return _FORM_DISPLAY_NAMES[form]
    return record.name.rsplit('.', 1)[-1]


def _has_output_handler(logger: logging.Logger) -> bool:
    """Return whether this logger's propagation chain has a non-null handler."""
    current = logger
    while current is not None:
        if any(
            not isinstance(handler, logging.NullHandler)
            for handler in current.handlers
        ):
            return True
        if not current.propagate:
            break
        current = current.parent
    return False


def get_logger(form: str) -> logging.Logger:
    """Return the canonical logger for a given form key."""
    return logging.getLogger(_FORM_LOGGER_NAMES[form])


def normalize_unique_id(unique_id):
    """Map a missing plot identifier to the report's reserved general-error row."""
    return GENERAL_ERROR_ROW if pd.isna(unique_id) else unique_id


def run_guard(function):
    """Start a run and guarantee logger cleanup if the wrapped entry point exits early."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        start_run()
        try:
            return function(*args, **kwargs)
        finally:
            if _active_handler is not None:
                _detach_handlers()

    return wrapped


def start_run() -> None:
    """Attach a fresh collecting handler for the duration of one pipeline run."""
    global _active_handler, _console_handler, _previous_level
    root_logger = logging.getLogger(_LOGGER_NAME_ROOT)
    _detach_handlers()
    external_logging_configured = _has_output_handler(root_logger)
    # Loggers default to the root logger's WARNING threshold. Without raising this
    # namespace's effective level, every .info(...) call (the fallback-note severity)
    # would be discarded by Logger.isEnabledFor() before it ever reached the handler.
    # The prior level is saved here and restored in write_report(), so collection
    # stays scoped to the active run rather than permanently changing the logger.
    _previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    _active_handler = _CollectingHandler()
    root_logger.addHandler(_active_handler)
    if not external_logging_configured:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setFormatter(_ConsoleFormatter())
        root_logger.addHandler(_console_handler)


def write_report(out_path: str, plot_df: Optional[pd.DataFrame] = None) -> None:
    """Pivot everything collected since start_run() into one CSV; detach the handler."""
    if _active_handler is None:
        raise RuntimeError('write_report() called without a matching start_run()')
    records = _active_handler.records
    try:
        identity_cols = []
        id_lookup = {}
        if plot_df is not None and 'unique_id' in plot_df.columns:
            identity_cols = [c for c in _IDENTITY_COLUMNS if c in plot_df.columns]
            # drop_duplicates() is required: run_conpyro.py passes one row per plot per
            # weather date, and to_dict('index') raises ValueError on a non-unique index.
            id_lookup = (
                plot_df.drop_duplicates('unique_id')
                .set_index('unique_id')[identity_cols]
                .to_dict('index')
            )

        forms = sorted({_form_for_record(r) for r in records})
        rows = defaultdict(lambda: {form: [] for form in forms})
        for record in records:
            row_key = normalize_unique_id(getattr(record, 'unique_id', None))
            rows[row_key][_form_for_record(record)].append(
                f'[{record.levelname}] {record.getMessage()}'
            )

        ordered_keys = ([GENERAL_ERROR_ROW] if GENERAL_ERROR_ROW in rows else []) + sorted(
            (key for key in rows if key != GENERAL_ERROR_ROW), key=str
        )

        out_rows = []
        for row_key in ordered_keys:
            row = {'unique_id': row_key}
            identity = id_lookup.get(row_key, {}) if row_key != GENERAL_ERROR_ROW else {}
            for col in identity_cols:
                row[col] = identity.get(col, '')
            for form in forms:
                messages = rows[row_key][form]
                row[form] = '\n'.join(f'{i}. {msg}' for i, msg in enumerate(messages, start=1))
            out_rows.append(row)

        report_df = pd.DataFrame(out_rows, columns=['unique_id'] + identity_cols + forms)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        report_df.to_csv(out_path, index=False)
    finally:
        _detach_handlers()
