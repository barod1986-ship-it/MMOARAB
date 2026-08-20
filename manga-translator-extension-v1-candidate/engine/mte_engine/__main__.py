from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .config import EngineSettings, PairingStore
from .constants import ENGINE_VERSION, PROTOCOL_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(prog="mte-engine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run")
    sub.add_parser("show-token")
    sub.add_parser("reset-pairing")
    sub.add_parser("version")
    sub.add_parser("diagnostics-smoke")
    args = parser.parse_args()
    command = args.command or "run"
    if command == "version":
        print(f"mte-engine {ENGINE_VERSION} protocol {PROTOCOL_VERSION}")
        return
    settings = EngineSettings.from_env()
    pairing = PairingStore(settings.data_dir)
    if command == "diagnostics-smoke":
        print(f"ok engine={ENGINE_VERSION} protocol={PROTOCOL_VERSION} bind={settings.expected_host_header}")
        return
    if command == "show-token":
        print(pairing.token)
        return
    if command == "reset-pairing":
        pairing.reset_pairing()
        print("Pairing cleared.")
        return
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=True, proxy_headers=False, forwarded_allow_ips="")


if __name__ == "__main__":
    main()
