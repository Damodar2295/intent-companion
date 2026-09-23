"""Bounded offline mock and quote decoders. No location facts or dates are invented."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from agent.search.models import CategoryQuote, PlanInterpretation

CATEGORY_TERMS = {
    "DINING": r"\b(?:dining|dinner|restaurant|food|lunch)\b",
    "SHOPPING": r"\b(?:shopping|shop|boutique)\b",
    "CULTURE": r"\b(?:museum|museums|gallery|culture|art)\b",
    "EVENT": r"\b(?:event|events|concert|party|nightlife)\b",
    "ATTRACTION": r"\b(?:explore|attraction|sightseeing|interesting)\b",
    "EXPERIENCE": r"\b(?:experience|experiences)\b",
}
TIME = r"(?:\d{1,2}:\d{2}(?:\s*[ap]m)?|\d{1,2}\s*[ap]m)"
DURATION = r"\b(?:\d{1,3}|one|two|three|four|five|six)\s+(?:hours?|minutes?)\b"
BUDGET = (
    r"\b(?:budget|under|up to)\s+(?:(?:EUR|USD|GBP)\s*)?\d+(?:\.\d{1,2})?(?:\s*(?:EUR|USD|GBP|euros|dollars|pounds))?\b"
)
TRANSPORT = r"\b(?:walking|walk|driving|drive|transit)\b"
LOCATION = r"\b(?:near my hotel|near the hotel|near me)\b"
VALUE = r"\b(?:amex|benefits?|offers?|rewards?)\b"


def matches(pattern, text):
    return [m.group() for m in re.finditer(pattern, text, re.IGNORECASE)]


def implied_task(text):
    if re.search(VALUE, text, re.IGNORECASE) and not re.search(
        r"\b(?:plan|outing|evening|tonight|tomorrow|near|find somewhere|go|visit)\b", text, re.IGNORECASE
    ):
        return "BENEFIT_LOOKUP"
    return "OUTING_PLANNING"


def interpret_mock(text):
    categories = []
    for category, pattern in CATEGORY_TERMS.items():
        found = matches(pattern, text)
        if found:
            categories.append(CategoryQuote(category=category, quote=found[0]))
    explicit = re.search(r"\bdestination:\s*([^;\n.]+)", text, re.IGNORECASE)
    cities = [explicit[1].strip()] if explicit else matches(r"\b(?:Rome|Roma|FCO|Paris|Milan|Milano|New York)\b", text)
    dates = matches(r"\b(?:\d{4}-\d{2}-\d{2}|today|tonight|tomorrow)\b", text)
    times = matches(TIME, text)
    durations = matches(DURATION, text)
    budgets = matches(BUDGET, text)
    transports = matches(TRANSPORT, text)
    locations = matches(LOCATION, text)
    values = matches(VALUE, text)
    ambiguous = any(len(set(v)) > 1 for v in (cities, dates, durations, budgets, transports)) or len(times) > 2
    if re.search(
        r"\b(?:not|without|no)\s+(?:\w+\s+)?(?:dining|dinner|shopping|museum|amex|walking)\b", text, re.IGNORECASE
    ):
        ambiguous = True
    return PlanInterpretation(
        task=implied_task(text),
        categories=categories,
        destination_quote=cities[0] if len(cities) == 1 else None,
        date_quote=dates[0] if dates else None,
        start_time_quote=times[0] if times else None,
        end_time_quote=times[1] if len(times) == 2 else None,
        duration_quote=durations[0] if durations else None,
        budget_quote=budgets[0] if budgets else None,
        transport_quote=transports[0] if transports else None,
        location_quote=locations[0] if locations else None,
        value_quote=values[0] if values else None,
        clarification="Ambiguous request" if ambiguous else None,
    )


def parse_time(value):
    value = value.strip().lower().replace(" ", "")
    for fmt in ("%H:%M", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(value, fmt).time()  # noqa: DTZ007 — destination-local wall time
        except ValueError:
            continue
    raise ValueError("Provide an unambiguous local time")


def parse_date(value, today):
    if value.lower() in {"today", "tonight"}:
        return today
    if value.lower() == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(value)


def parse_duration(value):
    if not re.fullmatch(DURATION, value, re.IGNORECASE):
        raise ValueError("Unsupported duration")
    amount, unit = value.lower().split()
    numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    count = numbers[amount] if amount in numbers else int(amount)
    result = count * 60 if unit.startswith("hour") else count
    if not 15 <= result <= 720:
        raise ValueError("Duration must be between 15 and 720 minutes")
    return result


def parse_budget(value):
    if not re.fullmatch(BUDGET, value, re.IGNORECASE):
        raise ValueError("Unsupported budget")
    amount = Decimal(re.search(r"\d+(?:\.\d+)?", value)[0])
    currencies = [
        key
        for key, pattern in {
            "EUR": r"\b(?:EUR|euros)\b",
            "USD": r"\b(?:USD|dollars)\b",
            "GBP": r"\b(?:GBP|pounds)\b",
        }.items()
        if re.search(pattern, value, re.IGNORECASE)
    ]
    if amount <= 0 or len(currencies) > 1:
        raise ValueError("Ambiguous budget")
    return amount, currencies[0] if currencies else None


def parse_transport(value):
    return {"walking": "WALK", "walk": "WALK", "driving": "DRIVE", "drive": "DRIVE", "transit": "TRANSIT"}[
        value.lower()
    ]
