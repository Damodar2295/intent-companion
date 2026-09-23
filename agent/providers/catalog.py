from agent.providers.contracts import CapabilityUnavailable


class SQLiteCatalogProvider:
    """Typed catalog access; business eligibility and values remain in existing services."""

    def __init__(self, repository):
        self.repository = repository

    def catalog(self, market, segment, destination):
        return self.repository.catalog(market, segment, destination)

    def select(self, query, kind):
        return [item for item in self.catalog(query.market, query.segment, query.destination) if item.kind == kind]

    async def cards(self, query):
        return self.select(query, "card")

    async def benefits(self, query):
        return self.select(query, "benefit")

    async def offers(self, query):
        return self.select(query, "offer")

    async def rewards(self, query):
        return self.select(query, "reward")

    async def merchants(self, query):
        return self.select(query, "merchant")


class UnavailableAmexExperienceProvider:
    async def search(self, plan):
        raise CapabilityUnavailable("AMEX experience inventory is not configured")
