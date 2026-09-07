"""IEEE C37.111-2013 / dual-logo COMTRADE parser."""

from comtrade.parsers._base_impl import BaseComtradeParser


class Ieee2013Parser(BaseComtradeParser):
    """IEEE C37.111-2013 — ASCII/BINARY/BINARY32/FLOAT32 + CFF."""

    STANDARD = "IEEE"
    REVISION = "2013"
