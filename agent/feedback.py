"""Feedback survives intent regeneration through stable owner/trip or owner/goal keys."""

import json


def consumer_key(intent):
    return json.dumps(
        [
            "consumer",
            intent.customer_id,
            intent.destination,
            str(intent.start_date),
            str(intent.end_date),
            intent.purpose,
        ]
    )


def business_key(intent):
    return json.dumps(["business", intent.business_id, intent.goal_id])


def status(repository, key):
    with repository.lock:
        row = repository.db.execute("SELECT status FROM intent_feedback WHERE id=?", (key,)).fetchone()
    return row[0] if row else "unconfirmed"


def save(repository, key, action):
    value = {"confirm": "confirmed", "dismiss": "dismissed", "restore": "unconfirmed"}[action]
    with repository.lock, repository.db:
        repository.db.execute(
            "INSERT INTO intent_feedback VALUES (?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status",
            (key, value),
        )
    return value
