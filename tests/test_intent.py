from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from agent.customer_context import CustomerService
from agent.domain import IntentSignal
from agent.repositories import Abstain, Conflict, NotFound, SQLiteRepository


def test_normalization(repository):
    data = repository.signals("cust-dining")[0].model_dump(mode="json")
    data["event_type"] = "flight_search"
    data["context"]["destination"] = "  rOmA "
    signal = IntentSignal.model_validate(data)
    assert signal.event_type == "travel_search"
    assert signal.context.destination == "Rome"


@pytest.mark.parametrize("field,value", [("end_date", "2026-10-01"), ("start_date", "bad-date")])
def test_bad_dates_rejected(repository, field, value):
    data = repository.signals("cust-dining")[0].model_dump(mode="json")
    data["context"][field] = value
    with pytest.raises(ValidationError):
        IntentSignal.model_validate(data)


def test_timezone_required(repository):
    data = repository.signals("cust-dining")[0].model_dump(mode="json")
    data["timestamp"] = "2026-09-17T10:00:00"
    with pytest.raises(ValidationError):
        IntentSignal.model_validate(data)


def test_confidence_aggregation_and_repeat_cap(repository, service):
    customer = repository.customer("cust-dining")
    signals = repository.signals(customer.customer_id)
    baseline = service.intent_engine.derive(customer, signals)
    assert baseline.confidence == 0.95
    assert baseline.intent_stage == "planning"
    repeated = [signals[0].model_copy(update={"event_id": f"repeat-{n}"}) for n in range(100)]
    result = service.intent_engine.derive(customer, signals + repeated + signals)
    assert result.confidence == 0.95
    assert sum(e.weight for e in result.evidence) == pytest.approx(0.95)


def test_booking_stage_configurable_weights(repository, service, settings):
    signal = repository.signals("cust-dining")[0].model_copy(update={"event_type": "travel_booking"})
    settings.weights["travel_booking"] = 0.8
    result = service.intent_engine.derive(repository.customer("cust-dining"), [signal])
    assert result.confidence == 0.8
    assert result.intent_stage == "booked"


def test_duplicate_ingestion_and_collision(repository):
    signal = repository.signals("cust-dining")[0]
    assert repository.add_signal(signal) is False
    with pytest.raises(Conflict):
        repository.add_signal(signal.model_copy(update={"source": "different"}))


@pytest.mark.parametrize(
    "problem", ["profile_consent", "signal_consent", "destination", "unsupported", "expired", "future", "dates"]
)
def test_signal_safety(repository, service, settings, problem):
    customer = repository.customer("cust-dining")
    signal = repository.signals(customer.customer_id)[0]
    if problem == "profile_consent":
        customer.consent.allowed = False
    elif problem == "signal_consent":
        signal.consent.allowed = False
    elif problem == "destination":
        signal.context.destination = None
    elif problem == "unsupported":
        signal.context.destination = "Paris"
    elif problem == "expired":
        signal.timestamp = settings.now() - timedelta(days=30)
    elif problem == "future":
        signal.timestamp = settings.now() + timedelta(seconds=1)
    else:
        signal.context.start_date = None
        signal.context.end_date = None
    with pytest.raises(Abstain):
        service.intent_engine.derive(customer, [signal])


def test_incompatible_trips_not_merged(repository, service):
    signals = repository.signals("cust-dining")
    signals[0].context.start_date = date(2026, 10, 11)
    with pytest.raises(Abstain, match="consistent"):
        service.intent_engine.derive(repository.customer("cust-dining"), signals)


def test_signal_ownership(repository):
    with pytest.raises(NotFound):
        repository.signals("cust-dining", ["evt-1-1"])


def test_preference_removal_survives_seed_and_restart(tmp_path):
    path = str(tmp_path / "test.sqlite3")
    repo = SQLiteRepository(path)
    repo.seed()
    CustomerService(repo).remove("cust-dining", "fine dining")
    repo.close()
    repo = SQLiteRepository(path)
    try:
        repo.seed()
        customer = repo.customer("cust-dining")
        assert "fine dining" not in customer.stated_preferences
        assert "fine dining" in customer.suppressed_preferences
        CustomerService(repo).replace("cust-dining", ["fine dining"])
        assert repo.customer("cust-dining").suppressed_preferences == ["museums"]
    finally:
        repo.close()


def test_no_protected_or_real_data_fields(repository):
    data = repository.signals("cust-dining")[0].model_dump(mode="json")
    data["context"]["religion"] = "unwanted"
    with pytest.raises(ValidationError):
        IntentSignal.model_validate(data)
    del data["context"]["religion"]
    data["synthetic"] = False
    with pytest.raises(ValidationError):
        IntentSignal.model_validate(data)
