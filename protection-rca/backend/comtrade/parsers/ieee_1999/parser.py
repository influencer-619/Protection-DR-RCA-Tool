"""IEEE C37.111-1999 COMTRADE parser."""

from comtrade.parsers._base_impl import BaseComtradeParser


class Ieee1999Parser(BaseComtradeParser):
    """IEEE C37.111-1999 — full CFG/DAT ASCII + BINARY support."""

    STANDARD = "IEEE"
    REVISION = "1999"
