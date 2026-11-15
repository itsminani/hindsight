"""Choose the price provider from settings: Tiingo with an API key, demo prices without one."""

from hindsight.config import Settings
from hindsight.integrations.demo_prices import DemoPriceProvider
from hindsight.integrations.interfaces import PriceProvider
from hindsight.integrations.tiingo import TiingoPriceProvider


def price_provider_from(settings: Settings) -> PriceProvider:
    """The provider the API and the worker share. Logged at startup so it's never a surprise."""
    if settings.tiingo_api_key:
        return TiingoPriceProvider(settings.tiingo_api_key)
    return DemoPriceProvider()
