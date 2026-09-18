"""Replay synthetic events against a running localhost demo, using only the standard library."""

import json
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://127.0.0.1:8090/api"


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(BASE + path, data=data, headers={"Content-Type": "application/json"}), timeout=30) as response:
        return json.load(response)


def main():
    customer_id = "cust-dining"
    clock = datetime.fromisoformat(request("/health")["clock"])
    customer = request(f"/customers/{customer_id}")
    if not customer["consent"]["allowed"]:
        raise SystemExit("Enable personalization for the dining demo profile before replaying.")
    ids = []
    for index, event_type in enumerate(["ad_click", "ad_click", "travel_search", "hotel_search", "travel_booking"]):
        event_id = f"replay-{uuid4().hex}"
        request(
            "/signals",
            {
                "event_id": event_id,
                "customer_id": customer_id,
                "source": "synthetic_cli_replay",
                "event_type": event_type,
                "timestamp": (clock - timedelta(seconds=5 - index)).isoformat(),
                "consent": customer["consent"],
                "synthetic": True,
                "context": {"destination": "Rome", "start_date": "2026-10-10", "end_date": "2026-10-15"},
            },
        )
        ids.append(event_id)
        detection = request("/intents/detect", {"customer_id": customer_id, "signal_ids": ids})
        if not detection["intent"]:
            raise SystemExit(str(detection["abstention_reasons"]))
        intent = detection["intent"]
        print(f"{event_type:22} score={intent['confidence']:.2f} stage={intent['intent_stage']}")
    experience = request("/companion", {"customer_id": customer_id, "intent_id": intent["intent_id"]})
    print("Experience:", experience["status"], "provider:", experience["provider_mode"])
    print("Cards:", [card["title"] for card in experience["recommended_cards"]])


if __name__ == "__main__":
    main()
