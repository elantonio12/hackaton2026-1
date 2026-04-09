"""Deterministic IPv6 address generator within a /64 block.

Each container_id is hashed to produce a stable 64-bit suffix that is
combined with the network prefix to form a unique IPv6 address.

This simulates real IoT deployments where each sensor has its own
network identity — a core property of IPv6 at scale: the /64 block
assigned to vps2 contains 2^64 ≈ 18 quintillion addresses, enough for
any realistic city-wide deployment.
"""

import hashlib
import ipaddress
import os


def _parse_prefix(prefix: str) -> int:
    """Parse an IPv6 prefix like '2605:a140:2302:3245::' into a 128-bit int.

    The /64 prefix occupies the upper 64 bits; the lower 64 bits are zeroed.
    """
    # Accept with or without trailing ::
    if not prefix.endswith("::"):
        prefix = prefix + "::"
    addr = ipaddress.IPv6Address(prefix)
    # Zero out the lower 64 bits
    return int(addr) & ((2**128 - 1) ^ (2**64 - 1))


def _suffix_for_id(container_id: str) -> int:
    """Derive a 64-bit host suffix from the container_id via SHA-256."""
    digest = hashlib.sha256(container_id.encode("utf-8")).digest()
    # Take the first 8 bytes as the suffix
    suffix = int.from_bytes(digest[:8], "big")
    # Avoid all-zero and all-ones suffixes (reserved / anycast)
    if suffix == 0:
        suffix = 1
    if suffix == (2**64 - 1):
        suffix -= 1
    return suffix


def address_for(container_id: str, prefix: str | None = None) -> str:
    """Return a deterministic IPv6 address for a given container_id.

    The prefix defaults to the IPV6_PREFIX env var, or the vps2 /64
    block if unset.
    """
    if prefix is None:
        prefix = os.environ.get("IPV6_PREFIX", "2605:a140:2302:3245::")
    net = _parse_prefix(prefix)
    suffix = _suffix_for_id(container_id)
    return str(ipaddress.IPv6Address(net | suffix))


def pool_for(container_ids: list[str], prefix: str | None = None) -> dict[str, str]:
    """Build a {container_id: ipv6_address} mapping for a list of IDs."""
    return {cid: address_for(cid, prefix) for cid in container_ids}
