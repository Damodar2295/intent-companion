"""Replay the importable Postman collection and its JS assertions against an isolated database."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "postman/IntentCompanion.postman_collection.json"
ENVIRONMENT = ROOT / "postman/IntentCompanion.postman_environment.json"


def entries():
    return [item for folder in json.loads(COLLECTION.read_text())["item"] for item in folder["item"]]


JS_RUNNER = """
const fs = require('node:fs');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const values = input.variables;
const pm = {
  response: { code: input.status, text: () => input.text, json: () => JSON.parse(input.text) },
  environment: { set: (k,v) => { values[k] = v; }, get: k => values[k] },
  test: (_name, fn) => fn(),
  expect: value => ({ to: { eql: expected => assert.deepStrictEqual(value, expected) } })
};
vm.runInNewContext(input.script, {pm}, {timeout:1000});
process.stdout.write(JSON.stringify(values));
"""


def test_postman_collection_executes_all_assertions(client):
    node = shutil.which("node")
    if node is None:
        pytest.fail("Node is required to execute Postman test scripts")
    variables = {v["key"]: v["value"] for v in json.loads(ENVIRONMENT.read_text())["values"]}
    variables["baseUrl"] = ""

    def expand(text):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(variables[m[1]]), text)

    for item in entries():
        request = item["request"]
        payload = json.loads(expand(request["body"]["raw"])) if "body" in request else None
        response = client.request(request["method"], expand(request["url"]), json=payload)
        script = "\n".join(item["event"][0]["script"]["exec"])
        result = subprocess.run(
            [node, "-e", JS_RUNNER],
            input=json.dumps(
                {"status": response.status_code, "text": response.text, "variables": variables, "script": script}
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{item['name']}: {result.stderr}"
        variables.update(json.loads(result.stdout))
    assert variables["intentId"] and variables["businessIntentId"] and variables["outingId"]


def test_collection_covers_existing_api_routes(client):
    known = set()

    def collect(routes, prefix=""):
        for route in routes:
            # Recent FastAPI releases retain included routers lazily instead of flattening app.routes.
            if hasattr(route, "original_router"):
                collect(route.original_router.routes, prefix + route.include_context.prefix)
                continue
            path = prefix + getattr(route, "path", "")
            if path.startswith("/api/"):
                for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
                    known.add((method, re.sub(r"\{[^}]+\}", "{}", path)))

    collect(client.app.routes)
    assert ("GET", "/api/health") in known
    included = {
        (
            item["request"]["method"],
            re.sub(r"\{\{[^}]+\}\}", "{}", item["request"]["url"].replace("{{baseUrl}}", "").split("?")[0]),
        )
        for item in entries()
    }
    assert known <= included
    # Versioned Phase 4 intent routes are real; no collection request may advertise a future endpoint.
    assert all(
        any(
            method == known_method and re.fullmatch(re.escape(known_path).replace(r"\{\}", r"[^/]+"), path)
            for known_method, known_path in known
        )
        for method, path in included
    )
