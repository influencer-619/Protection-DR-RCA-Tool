"""IEC 60255-24:2013 COMTRADE parser (IEEE 2013 dual-logo)."""

from comtrade.parsers._base_impl import BaseComtradeParser


class Iec2013Parser(BaseComtradeParser):
    """IEC 60255-24:2013 — dual-logo with IEEE C37.111-2013."""

    STANDARD = "IEC"
    REVISION = "2013"
