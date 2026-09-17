"""Explicit preference changes override historical personalization evidence."""

from agent.domain import CustomerContext, Preference
from agent.repositories import Repository


class CustomerService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def remove(self, customer_id: str, preference: Preference) -> CustomerContext:
        customer = self.repository.customer(customer_id)
        customer.stated_preferences = [p for p in customer.stated_preferences if p != preference]
        customer.suppressed_preferences = sorted(set(customer.suppressed_preferences) | {preference})
        self.repository.save_customer(customer)
        return customer

    def replace(self, customer_id: str, preferences: list[Preference]) -> CustomerContext:
        customer = self.repository.customer(customer_id)
        # Suppress old signal-derived preferences as well as removed profile preferences.
        previous = set(customer.stated_preferences)
        for signal in self.repository.signals(customer_id):
            previous.update(signal.context.preferences)
        customer.suppressed_preferences = sorted((set(customer.suppressed_preferences) | previous) - set(preferences))
        customer.stated_preferences = sorted(set(preferences))
        self.repository.save_customer(customer)
        return customer
