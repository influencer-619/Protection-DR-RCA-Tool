"""Registry of protection element modules."""

from __future__ import annotations

from importlib import import_module
from typing import Dict

from protection.models import ProtectionElement

_MODULE_BY_CODE = {
    "21": "el_21",
    "21G": "el_21g",
    "21P": "el_21p",
    "32R": "el_32r",
    "46": "el_46",
    "50": "el_50",
    "50P": "el_50p",
    "51": "el_51",
    "51P": "el_51p",
    "50N": "el_50n",
    "51N": "el_51n",
    "67": "el_67",
    "67N": "el_67n",
    "67P": "el_67p",
    "27": "el_27",
    "59": "el_59",
    "68": "el_68",
    "78": "el_78",
    "81U": "el_81u",
    "81O": "el_81o",
    "81R": "el_81r",
    "87T": "el_87t",
    "87L": "el_87l",
    "87B": "el_87b",
    "87G": "el_87g",
    "87RGF": "el_87rgf",
    "50BF": "el_50bf",
    "79": "el_79",
    "86": "el_86",
    "25": "el_25",
}

ELEMENT_REGISTRY: Dict[str, ProtectionElement] = {}


def _load() -> None:
    if ELEMENT_REGISTRY:
        return
    for code, name in _MODULE_BY_CODE.items():
        mod = import_module(f"protection.elements.{name}")
        ELEMENT_REGISTRY[code] = mod.ELEMENT


def get_element(code: str) -> ProtectionElement | None:
    _load()
    return ELEMENT_REGISTRY.get(code)


def all_elements() -> Dict[str, ProtectionElement]:
    _load()
    return dict(ELEMENT_REGISTRY)
