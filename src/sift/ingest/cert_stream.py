"""Certificate Transparency live-feed consumer.

Subscribes to a CertStream feed and yields newly issued domains in near real time.
Used by the early-warning radar. (PRD FR-1.3, FR-7.x)

Note: this is live network-infrastructure data (new websites appearing), NOT video
stream telemetry. See PRD Section 13.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class NewDomainEvent:
    domain: str
    issuer: str
    seen_at: float  # unix timestamp


def stream_new_domains() -> Iterator[NewDomainEvent]:
    """Yield NewDomainEvent objects from the CertStream feed.

    TODO:
      - connect to CERTSTREAM_URL
      - for each cert message, emit one event per SAN/hostname
      - be resilient to disconnects (reconnect with backoff)
    For development, also provide a replay-from-file mode so the dashboard demo
    does not require a live connection.
    """
    raise NotImplementedError
