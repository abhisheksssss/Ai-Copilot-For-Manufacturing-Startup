import json
import socket
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


_DNS_CACHE: dict[str, str] = {}


def resolve_db_hostaddr(db_url: str) -> str:
    """
    If db_url points to a remote PostgreSQL host and local DNS cannot resolve it
    (common with Indian ISPs like JioFiber on AWS/Neon CNAMEs returning RCODE_REFUSED),
    queries DNS-over-HTTPS (Google/Cloudflare) to obtain the IPv4 address and
    injects `hostaddr=<ip>` into the connection string.
    
    This allows libpq/psycopg to connect directly via IP while preserving the
    hostname for SSL SNI and certificate verification.
    """
    if not db_url or not (db_url.startswith("postgresql") or db_url.startswith("postgres")):
        return db_url

    try:
        parsed = urlparse(db_url)
        hostname = parsed.hostname
        if not hostname or hostname in ("localhost", "127.0.0.1"):
            return db_url

        query_dict = parse_qs(parsed.query)
        if "hostaddr" in query_dict:
            return db_url

        # Check if already resolved in process cache
        if hostname in _DNS_CACHE:
            resolved_ip = _DNS_CACHE[hostname]
            params = [(k, v[0]) for k, v in query_dict.items()]
            params.append(("hostaddr", resolved_ip))
            new_query = urlencode(params)
            new_parts = list(parsed)
            new_parts[4] = new_query
            return urlunparse(new_parts)

        # Query public DNS-over-HTTPS (Google or Cloudflare) to get the authoritative IP
        resolved_ip = None
        doh_endpoints = [
            f"https://dns.google/resolve?name={hostname}&type=A",
            f"https://cloudflare-dns.com/dns-query?name={hostname}&type=A",
        ]

        for doh_url in doh_endpoints:
            try:
                req = urllib.request.Request(
                    doh_url,
                    headers={"Accept": "application/dns-json", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read().decode())
                    for ans in data.get("Answer", []):
                        if ans.get("type") == 1 and ans.get("data"):
                            ip_candidate = ans["data"].strip()
                            # Validate IP format
                            try:
                                socket.inet_aton(ip_candidate)
                                resolved_ip = ip_candidate
                                break
                            except OSError:
                                continue
                if resolved_ip:
                    break
            except Exception:
                continue

        if resolved_ip:
            _DNS_CACHE[hostname] = resolved_ip
            print(f"[DNS Fallback] Resolved '{hostname}' -> {resolved_ip}. Injecting hostaddr.")
            params = [(k, v[0]) for k, v in query_dict.items()]
            params.append(("hostaddr", resolved_ip))
            new_query = urlencode(params)
            new_parts = list(parsed)
            new_parts[4] = new_query
            return urlunparse(new_parts)

    except Exception as err:
        print(f"[DNS Fallback Warning] Host resolution helper encountered: {err}")

    return db_url
