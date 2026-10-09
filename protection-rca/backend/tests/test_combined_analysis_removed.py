"""Combined RCA product removed — endpoint must not exist."""

from __future__ import annotations

import importlib

from fastapi.routing import APIRoute


def test_combined_analysis_route_absent():
    mod = importlib.import_module("app.api.analysis")
    paths = {
        getattr(r, "path", "")
        for r in mod.router.routes
        if isinstance(r, APIRoute)
    }
    assert "/combined-analysis" not in paths
    assert not any("combined-analysis" in p for p in paths)


def test_combined_analysis_module_gone():
    try:
        importlib.import_module("app.services.combined_analysis")
        raise AssertionError("combined_analysis module should be deleted")
    except ModuleNotFoundError:
        pass


def test_dual_end_87l_module_gone():
    try:
        importlib.import_module("electrical_analysis.dual_end_87l")
        raise AssertionError("dual_end_87l module should be deleted")
    except ModuleNotFoundError:
        pass
