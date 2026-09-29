# -*- coding: utf-8 -*-
"""
fuel-analyst-fofem694-runtime: the official USDA Forest Service FOFEM 6.9.4 batch runtime
(runfofem.exe), Windows x64 only, for FuelAnalyst's model_select='fof_gui' emissions backend.

Bundled here byte-for-byte from the verified upstream release; see PROVENANCE.md (installed
alongside this module) for the source URL, retrieval date, and file hashes. doc/LICENSE
states the software was developed by federal employees as part of official duties and is
public domain - a different license than FuelAnalyst's own MIT-licensed code. The Microsoft
Visual C++ Redistributable is a separately-installed Windows prerequisite this package does
not provide; see FuelAnalyst's docs/CODEBASE.md.
"""
__author__ = ['Gregory A. Greene']

import importlib.resources


def get_runtime_dir() -> str:
    """
    Resolve the absolute path to this installed package's own directory, where runfofem.exe
    and its required CSVs live alongside this module.

    :return: Absolute directory path.
    """
    return str(importlib.resources.files(__package__))
