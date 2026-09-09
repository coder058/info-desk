"""Read-only, allowlisted government connectors. No arbitrary URL fetch tool."""
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

# SOURCE: official EIA RSS directory, Federal Register API docs, OFAC program page.
FEEDS = {
    "eia": {"name": "EIA · Today in Energy", "url": "https://www.eia.gov/rss/todayinenergy.xml", "format": "rss", "host": "www.eia.gov", "coverage": "Publisher RSS summaries, not full articles"},
    "federal-register": {"name": "Federal Register · OFAC notices", "url": "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=foreign-assets-control-office&order=newest&per_page=10", "format": "json", "host": "www.federalregister.gov", "coverage": "Most recent notice metadata and abstracts; not complete legal texts"},
    "ofac-live": {"name": "OFAC · Venezuela licenses", "url": "https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions", "format": "html", "host": "ofac.treasury.gov", "coverage": "Current general-license titles; not the full license conditions"},
}
# UNCALIBRATED GUESS: courtesy polling floor and resource budgets, not provider SLAs.
POLL_SECONDS = 60
MAX_RESPONSE_BYTES = 2_000_000
SOURCE_TIMEOUT_SECONDS = 15


def clean_html(value):
    soup = BeautifulSoup(value or "", "html.parser")
    for tag in soup(["script", "style", "iframe", "object"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def safe_document_url(value, source_id):
    url = urlsplit(value)
    if url.hostname != FEEDS[source_id]["host"] or url.username or url.password or url.port not in (None, 443):
        raise ValueError("Source supplied a document URL outside its allowlist")
    if url.scheme not in {"http", "https"}:
        raise ValueError("Unsupported document URL scheme")
    return urlunsplit(("https", url.netloc, url.path, url.query, ""))


def parse_feed(source_id, body):
    spec = FEEDS[source_id]
    documents = []
    if spec["format"] == "rss":
        tree = ElementTree.fromstring(body)
        for item in tree.findall("./channel/item"):
            title = clean_html(item.findtext("title"))
            description = clean_html(item.findtext("description"))
            published = item.findtext("pubDate")
            if published:
                published = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
            documents.append({"title": title, "url": safe_document_url(item.findtext("link") or "", source_id),
                "body": f"{title}\n{description}", "published_at": published, "coverage": spec["coverage"]})
    elif spec["format"] == "json":
        import json
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("Missing Federal Register results array")
        for row in data["results"]:
            title, abstract = clean_html(row["title"]), clean_html(row.get("abstract"))
            published = row.get("publication_date")
            if published:
                datetime.fromisoformat(published)
            documents.append({"title": title, "url": safe_document_url(row["html_url"], source_id),
                "body": f"{title}\n{abstract}".strip(), "published_at": published,
                "coverage": spec["coverage"] if abstract else "Notice title only; publisher abstract is missing"})
    else:
        soup = BeautifulSoup(body, "html.parser")
        licenses = []
        for anchor in soup.find_all("a"):
            if re.match(r"Venezuela General License\s+\d", anchor.get_text(" ", strip=True)):
                parent = anchor.find_parent("li")
                if parent:
                    licenses.append(" ".join(parent.get_text(" ", strip=True).split()))
        if not licenses:
            raise ValueError("OFAC license-list contract changed or response was not a license page")
        documents.append({"title": "Venezuela-related general licenses", "url": spec["url"],
            "body": "\n".join(dict.fromkeys(licenses)), "published_at": None, "coverage": spec["coverage"]})
    if not documents or any(not doc["title"] or not doc["body"] for doc in documents):
        raise ValueError("No valid documents in source response")
    return documents


def next_check(headers):
    delay = POLL_SECONDS
    retry = headers.get("retry-after")
    if retry:
        try:
            delay = max(delay, float(retry))
        except ValueError:
            try:
                delay = max(delay, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    cache = re.search(r"(?:^|,)\s*max-age=(\d+)", headers.get("cache-control", ""))
    if cache:
        delay = max(delay, int(cache.group(1)))
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()


class Connector:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or httpx.Client(timeout=SOURCE_TIMEOUT_SECONDS, follow_redirects=False,
            headers={"User-Agent": "InfoDesk/0.3 (+https://github.com/coder058/info-desk)"})

    def refresh(self, source_id):
        spec = FEEDS[source_id]
        previous = self.store.latest_checks().get(source_id)
        if previous and datetime.fromisoformat(previous["next_check_at"]) > datetime.now(timezone.utc):
            return {"source_id": source_id, "status": "cooldown", "detail": "Cached source state; no new HTTP request", "changes": [], "check": previous}
        headers = {}
        if previous and previous.get("etag"):
            headers["If-None-Match"] = previous["etag"]
        if previous and previous.get("last_modified"):
            headers["If-Modified-Since"] = previous["last_modified"]
        started = time.perf_counter()
        response_headers = {}
        status, detail, changes = "error", "Source request failed", []
        try:
            with self.client.stream("GET", spec["url"], headers=headers) as response:
                response_headers = response.headers
                if response.status_code == 304:
                    if not any(doc["source_id"] == source_id for doc in self.store.documents()):
                        raise ValueError("304 response without a stored document")
                    status, detail = "unchanged", "HTTP 304 — publisher reports unchanged content"
                else:
                    response.raise_for_status()
                    # Redirects are not followed; source adapters must be explicitly reviewed.
                    if response.status_code != 200:
                        raise ValueError(f"Unexpected HTTP status {response.status_code}")
                    content = bytearray()
                    for part in response.iter_bytes():
                        content.extend(part)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise ValueError("Source response exceeded the size budget")
                    documents = parse_feed(source_id, bytes(content))
                    changes = [self.store.ingest(source_id, doc) for doc in documents]
                    status, detail = "ok", f"HTTP 200 — checked {len(documents)} documents"
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ElementTree.ParseError, DefusedXmlException) as exc:
            detail = str(exc)
        self.store.add_check(source_id, status, detail, (time.perf_counter()-started)*1000,
            next_check(response_headers),
            response_headers.get("etag", (previous or {}).get("etag") if status == "unchanged" else None),
            response_headers.get("last-modified", (previous or {}).get("last_modified") if status == "unchanged" else None))
        return {"source_id": source_id, "status": status, "detail": detail, "changes": changes,
                "check": self.store.latest_checks()[source_id]}

    def close(self):
        self.client.close()
