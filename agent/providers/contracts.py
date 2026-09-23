from dataclasses import dataclass
from typing import Protocol

from agent.domain import Benefit, CardProduct, MembershipRewardOpportunity, Merchant, Offer
from agent.outing.models import DiscoveryCandidate, SearchPlan
from agent.outing.providers import EventProvider, PlaceProvider, RoutingProvider, SearchProvider

# Preserve established outing interfaces; these names expose one shared provider vocabulary.
PlacesProvider = PlaceProvider
WebDiscoveryTool = SearchProvider
__all__ = [
    "AmexExperienceProvider",
    "BenefitProvider",
    "CapabilityUnavailable",
    "CardProvider",
    "CatalogQuery",
    "EventProvider",
    "MerchantProvider",
    "OfferProvider",
    "PlacesProvider",
    "RewardProvider",
    "RoutingProvider",
    "WebDiscoveryTool",
]


class CapabilityUnavailable(Exception):
    pass


@dataclass(frozen=True)
class CatalogQuery:
    market: str
    segment: str
    destination: str


class CardProvider(Protocol):
    async def cards(self, query: CatalogQuery) -> list[CardProduct]: ...


class BenefitProvider(Protocol):
    async def benefits(self, query: CatalogQuery) -> list[Benefit]: ...


class OfferProvider(Protocol):
    async def offers(self, query: CatalogQuery) -> list[Offer]: ...


class RewardProvider(Protocol):
    async def rewards(self, query: CatalogQuery) -> list[MembershipRewardOpportunity]: ...


class MerchantProvider(Protocol):
    async def merchants(self, query: CatalogQuery) -> list[Merchant]: ...


class AmexExperienceProvider(Protocol):
    async def search(self, plan: SearchPlan) -> list[DiscoveryCandidate]: ...
