"""IEEE C37.111-1991 COMTRADE parser."""

from comtrade.parsers._base_impl import BaseComtradeParser


class Ieee1991Parser(BaseComtradeParser):
    """IEEE C37.111-1991 — partial support (no primary/secondary/PS, ASCII/BINARY)."""

    STANDARD = "IEEE"
    REVISION = "1991"
