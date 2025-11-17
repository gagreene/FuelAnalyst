"""
Fuel Analyst Package

A forest fuel load analysis and FOFEM data processing package.
"""

__version__ = "1.0.0"
__author__ = "Gregory A. Greene"

# Import main module for easy access
from . import fuel_analyst
from .fuel_analyst import (
    fuel_analyst,
    default_stand_summary_dict,
    default_woody_debris_dict,
    default_fofem_consume_dict,
)

__all__ = [
    "fuel_analyst",
    "default_stand_summary_dict",
    "default_woody_debris_dict",
    "default_fofem_consume_dict",
]

