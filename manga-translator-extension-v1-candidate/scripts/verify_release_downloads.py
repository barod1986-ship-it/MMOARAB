from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024


def valid_public_https(url: str, allowed_hosts: set[str]) -> tuple[str, str]:
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise SystemExit(f'unsafe production download URL: {url}')
    host=parsed.hostname.lower().rstrip('.')
    if host not in allowed_hosts or host == 'localhost' or host.endswith('.local'):
        raise SystemExit(f'host not allowlisted: {host}')
    try:
        ipaddress.ip_address(host)
        raise SystemExit(f'IP literals are forbidden: {host}')
    except ValueError:
        pass
    for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        address=ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved:
            raise SystemExit(f'host resolved to non-public address: {host} -> {address}')
    return host, parsed.path


class LockedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts=allowed_hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        valid_public_https(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def main() -> int:
    parser=argparse.ArgumentParser(description='Download production Engine artifacts from reviewed HTTPS links and verify exact SHA-256 bytes.')
    parser.add_argument('manifest', nargs='?', default='release-control/production-downloads.json')
    args=parser.parse_args()
    data=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    allowed=set(data.get('allowedHosts', []))
    artifacts=data.get('artifacts', [])
    if not artifacts:
        raise SystemExit('no production Engine download artifacts are configured')
    opener=urllib.request.build_opener(LockedRedirects(allowed))
    for artifact in artifacts:
        url=str(artifact['url']); valid_public_https(url, allowed)
        expected=str(artifact['sha256']).lower().removeprefix('sha256:')
        expected_bytes=int(artifact['bytes'])
        if expected_bytes <= 0 or expected_bytes > MAX_ARTIFACT_BYTES:
            raise SystemExit(f'invalid artifact size: {artifact.get("id")}')
        h=hashlib.sha256(); total=0
        req=urllib.request.Request(url, headers={'User-Agent':'mte-release-verifier/1'}, method='GET')
        with opener.open(req, timeout=30) as response:
            final=str(response.geturl()); valid_public_https(final, allowed)
            while True:
                chunk=response.read(1024*1024)
                if not chunk: break
                total += len(chunk)
                if total > expected_bytes or total > MAX_ARTIFACT_BYTES:
                    raise SystemExit(f'artifact exceeded expected size: {artifact.get("id")}')
                h.update(chunk)
        if total != expected_bytes or h.hexdigest() != expected:
            raise SystemExit(f'production download verification failed: {artifact.get("id")}')
        print(f'ok {artifact.get("id")}: {total} bytes sha256:{expected}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
