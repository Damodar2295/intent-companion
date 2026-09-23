"""Fetch only explicitly configured official hosts. No general URL/proxy endpoint."""

import asyncio
import ipaddress
import json
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from agent.outing.providers import ProviderError


class JSONLDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.text = ""
        self.records = []

    def handle_starttag(self, tag, attrs):
        self.active = tag == "script" and dict(attrs).get("type") == "application/ld+json"
        if self.active:
            self.text = ""

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            try:
                value = json.loads(self.text)
                self.records.extend(value if isinstance(value, list) else [value])
            except ValueError:
                pass
            self.active = False


async def public_url(url, hosts):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ProviderError("Official source is not allowlisted")
    addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ProviderError("Official source must resolve to public addresses")
    return parsed


async def fetch_jsonld(url, hosts):
    """Pin verified DNS address to prevent rebinding; no redirects, cookies, or credentials."""
    parsed = await public_url(url, hosts)
    addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    address = addresses[0][4][0]
    if not all(ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ProviderError("Unsafe official source")
    endpoint = httpx.URL(url).copy_with(host=address)
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:  # noqa: SIM117
            async with client.stream(
                "GET",
                endpoint,
                headers={"Host": parsed.hostname},
                extensions={"sni_hostname": parsed.hostname.encode()},
            ) as response:
                response.raise_for_status()
                if response.is_redirect or "text/html" not in response.headers.get("content-type", ""):
                    raise ProviderError("Official source must return HTML directly")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 512_000:
                        raise ProviderError("Official source exceeds extraction limit")
        parser = JSONLDParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        return parser.records
    except (httpx.HTTPError, OSError):
        raise ProviderError("Official page unavailable") from None


class OfficialPages:
    def __init__(self, settings):
        self.settings = settings

    async def discover(self, candidates):
        from agent.outing.models import DiscoveryCandidate, Location
        from agent.outing.verification import evidence

        results = []
        urls = list(
            dict.fromkeys(
                url
                for c in candidates
                for url in [c.url, *c.official_urls]
                if urlparse(url).hostname in self.settings.official_hosts
            )
        )[:5]
        for url in urls:
            records = await fetch_jsonld(url, self.settings.official_hosts)
            flattened = []
            for record in records:
                if isinstance(record, dict):
                    flattened.extend(record.get("@graph", [record]))
            for item in flattened:
                if not isinstance(item, dict) or item.get("@type") != "Event":
                    continue
                venue = item.get("location", {})
                if not isinstance(venue, dict):
                    continue
                geo, address = venue.get("geo", {}), venue.get("address", {})
                if not isinstance(geo, dict) or not isinstance(address, dict):
                    continue
                try:
                    loc = Location(lat=geo["latitude"], lng=geo["longitude"])
                    from datetime import datetime

                    start, end = datetime.fromisoformat(item["startDate"]), datetime.fromisoformat(item["endDate"])
                    if start.tzinfo is None or end.tzinfo is None:
                        continue
                except (ValueError, KeyError, TypeError):
                    continue
                fields = {
                    "name": item.get("name"),
                    "location": loc.model_dump(),
                    "address": ", ".join(str(address[k]) for k in ("streetAddress", "addressLocality") if k in address),
                    "schedule.start": start.isoformat(),
                    "schedule.end": end.isoformat(),
                }
                if not fields["name"] or not fields["address"]:
                    continue
                import hashlib

                identity = hashlib.sha256((url + start.isoformat() + str(fields["name"])).encode()).hexdigest()[:20]
                results.append(
                    DiscoveryCandidate(
                        candidate_id="official:" + identity,
                        name=fields["name"],
                        category="EVENT",
                        provider="official",
                        url=url,
                        evidence=[
                            evidence("official", k, v, url, "OFFICIAL_ORGANIZER", self.settings.now(), self.settings)
                            for k, v in fields.items()
                        ],
                    )
                )
        return results
