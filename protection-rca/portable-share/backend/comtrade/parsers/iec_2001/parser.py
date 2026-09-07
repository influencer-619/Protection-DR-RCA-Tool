"""IEC 60255-24:2001 COMTRADE parser (IEEE 1999 equivalent)."""

from comtrade.parsers._base_impl import BaseComtradeParser


class Iec2001Parser(BaseComtradeParser):
    """IEC 60255-24:2001 — content-equivalent to IEEE 1999."""

    STANDARD = "IEC"
    REVISION = "2001"
