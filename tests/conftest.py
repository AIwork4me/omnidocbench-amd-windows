"""Shared pytest configuration: skip Windows-PowerShell tests on other OSes.

Tests that execute PowerShell (orchestrator harness, backend proof, PS
libraries) are marked ``win32``; on non-Windows runners they are skipped so
the pure-Python suite can run on Ubuntu CI.
"""
from __future__ import annotations

import sys

import pytest


def pytest_collection_modifyitems(config, items):
    if sys.platform.startswith("win"):
        return
    skip_win32 = pytest.mark.skip(reason="requires Windows PowerShell (win32)")
    for item in items:
        if "win32" in item.keywords:
            item.add_marker(skip_win32)
