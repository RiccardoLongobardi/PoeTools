"""Data source layer.

Unico punto di contatto con l'esterno. Il resto del codice parla solo con
l'interfaccia `DataSource` (vedi `base.py`), non sa nulla di poe.ninja né
di qualsiasi altro provider.
"""

from backend.datasource.base import CurrencyInfo, DataSource, ExchangeQuote
from backend.datasource.poe_ninja import PoeNinjaSource

__all__ = ["CurrencyInfo", "DataSource", "ExchangeQuote", "PoeNinjaSource"]
