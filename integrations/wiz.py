"""WiZ-lampen lokaal uitlezen en bedienen (UDP-poort 38899, geen account nodig)."""

from __future__ import annotations

import ipaddress
import json
import socket
import time

PORT = 38899


def _sock(timeout: float) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(timeout)
    return s


def _request(ip: str, method: str, params: dict | None = None, timeout: float = 1.0,
             port: int = PORT, retries: int = 3) -> dict:
    msg = json.dumps({"method": method, "params": params or {}}).encode()
    with _sock(timeout / retries) as s:
        for _ in range(retries):  # UDP kan een pakketje kwijtraken: een paar keer proberen
            s.sendto(msg, (ip, port))
            try:
                data, _ = s.recvfrom(4096)
            except socket.timeout:
                continue
            reply = json.loads(data.decode())
            if "error" in reply:
                raise RuntimeError(reply["error"].get("message", "WiZ-fout"))
            return reply.get("result", {})
    raise TimeoutError(f"Geen antwoord van lamp {ip}")


def get_state(ip: str, port: int = PORT) -> dict:
    """{'state': bool, 'dimming': 10-100, 'temp': kelvin, 'mac': ..., 'rssi': ...}"""
    return _request(ip, "getPilot", port=port)


def set_on(ip: str, on: bool, port: int = PORT) -> None:
    _request(ip, "setPilot", {"state": bool(on)}, port=port)


def set_brightness(ip: str, percent: int, port: int = PORT) -> None:
    _request(ip, "setPilot", {"state": True, "dimming": max(10, min(100, int(percent)))}, port=port)


def broadcast_addresses(local_ip: str) -> list[str]:
    net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    return ["255.255.255.255", str(net.broadcast_address)]


def discover(targets: list[str], timeout: float = 2.5, port: int = PORT) -> dict[str, dict]:
    """Stuur 'getPilot' naar de doelen (broadcast en/of losse adressen) en verzamel antwoorden.

    Geeft {ip: status} voor elke lamp die antwoordt.
    """
    found: dict[str, dict] = {}
    msg = json.dumps({"method": "getPilot", "params": {}}).encode()
    with _sock(0.25) as s:
        for _ in range(2):
            for t in targets:
                try:
                    s.sendto(msg, (t, port))
                except OSError:
                    pass
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                reply = json.loads(data.decode())
            except ValueError:
                continue
            if reply.get("method") == "getPilot" and "result" in reply:
                found[ip] = reply["result"]
    return found
