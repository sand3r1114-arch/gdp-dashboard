"""Scan het lokale (wifi-)netwerk naar verbonden apparaten.

Werkt zonder root/admin-rechten en zonder extra pakketten:

1. Bepaal het eigen IP-adres en het subnet (standaard een /24, bv. 192.168.1.0/24).
2. Probeer elk adres in het subnet te bereiken (ping + korte TCP-poging).
   Daardoor vult het besturingssysteem zijn ARP-tabel met MAC-adressen.
3. Lees de ARP-tabel uit: elk adres met een MAC-adres is een apparaat.
4. Verrijk elk apparaat met hostnaam, fabrikant (via de IEEE OUI-lijst),
   open poorten en een gok naar het type apparaat.

Scan alleen netwerken waarvan je de eigenaar bent of waarvoor je toestemming hebt.
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import io
import ipaddress
import json
import platform
import re
import socket
import subprocess
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

SYSTEM = platform.system()  # "Windows", "Darwin" (macOS) of "Linux"

# Poorten die veel zeggen over wat voor apparaat iets is.
COMMON_PORTS: dict[int, str] = {
    22: "SSH",
    53: "DNS",
    80: "HTTP",
    443: "HTTPS",
    445: "SMB (bestanden delen)",
    548: "AFP (Mac bestanden)",
    554: "RTSP (camera)",
    631: "IPP (printer)",
    1400: "Sonos",
    1883: "MQTT (smart home)",
    5000: "UPnP / Synology",
    7000: "AirPlay",
    8008: "Chromecast",
    8009: "Chromecast",
    8080: "HTTP (alternatief)",
    8123: "Home Assistant",
    9100: "Printer",
    62078: "iPhone / iPad",
}

# Poorten om "is hier iemand?" te testen; ook een geweigerde verbinding betekent "ja".
PROBE_PORTS = (80, 443, 22, 445, 62078, 8009)

MAC_RE = re.compile(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{1,2}(?:[:-][0-9A-Fa-f]{1,2}){5})(?![0-9A-Fa-f])")
IP_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")

OUI_SOURCES = (
    ("ieee", "https://standards-oui.ieee.org/oui/oui.csv"),
    ("manuf", "https://www.wireshark.org/download/automated/data/manuf"),
)


@dataclass
class Device:
    ip: str
    mac: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    open_ports: list[int] = field(default_factory=list)
    randomized_mac: bool = False
    is_gateway: bool = False
    is_self: bool = False
    device_type: str = "Onbekend"
    icon: str = "❔"

    @property
    def key(self) -> str:
        """Stabiele sleutel om een apparaat terug te herkennen tussen scans."""
        return self.mac or f"ip:{self.ip}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


@dataclass
class ScanResult:
    network: str
    local_ip: str
    gateway: str | None
    started_at: float
    duration_s: float
    devices: list[Device]

    def to_dict(self) -> dict:
        return {
            "network": self.network,
            "local_ip": self.local_ip,
            "gateway": self.gateway,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "devices": [d.to_dict() for d in self.devices],
        }


# --------------------------------------------------------------------------- #
# Hulpfuncties die geen netwerk nodig hebben (en dus goed te testen zijn).


def normalize_mac(mac: str) -> str:
    """'0:1A-2b:3:4d:5E' -> '00:1a:2b:03:4d:5e'."""
    parts = re.split(r"[:-]", mac.strip())
    return ":".join(p.zfill(2) for p in parts).lower()


def is_randomized_mac(mac: str) -> bool:
    """Telefoons en laptops gebruiken vaak een 'privé' (willekeurig) MAC-adres.

    Dat herken je aan het 'locally administered'-bit in de eerste byte.
    """
    first = int(normalize_mac(mac).split(":")[0], 16)
    return bool(first & 0x02) and not first & 0x01


def _is_usable_mac(mac: str) -> bool:
    first = int(mac.split(":")[0], 16)
    if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return False
    return not first & 0x01  # multicast-adressen overslaan


def parse_arp_table(text: str) -> dict[str, str]:
    """Haal IP -> MAC uit de uitvoer van `arp -a`, `ip neigh` of /proc/net/arp.

    Werkt voor Windows, macOS en Linux omdat we per regel gewoon zoeken naar
    één IP-adres en één MAC-adres.
    """
    table: dict[str, str] = {}
    for line in text.splitlines():
        lower = line.lower()
        if "incomplete" in lower or "failed" in lower:
            continue
        ip_match = IP_RE.search(line)
        mac_match = MAC_RE.search(line)
        if not ip_match or not mac_match:
            continue
        mac = normalize_mac(mac_match.group(1))
        if _is_usable_mac(mac):
            table[ip_match.group(1)] = mac
    return table


def parse_default_gateway(text: str) -> str | None:
    """Vind de standaardgateway (je router) in `ip route`, `route -n get default`
    of `route print 0.0.0.0`."""
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"default via (\S+)", s)  # Linux
        if m:
            return m.group(1)
        m = re.match(r"gateway:\s*(\S+)", s)  # macOS
        if m:
            return m.group(1)
        m = re.match(r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})", s)  # Windows
        if m:
            return m.group(1)
    return None


def parse_oui_ieee_csv(text: str) -> dict[str, str]:
    """IEEE oui.csv: Registry,Assignment,Organization Name,Organization Address."""
    out: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        prefix = (row.get("Assignment") or "").strip().lower()
        name = (row.get("Organization Name") or "").strip()
        if len(prefix) == 6 and name:
            out[prefix] = name
    return out


def parse_oui_manuf(text: str) -> dict[str, str]:
    """Wireshark manuf: '00:00:0C<TAB>Cisco<TAB>Cisco Systems, Inc'."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2 or "/" in parts[0]:
            continue  # kleinere blokken (/28, /36) overslaan
        prefix = parts[0].replace(":", "").replace("-", "").lower()
        if len(prefix) == 6:
            out[prefix] = (parts[2] if len(parts) > 2 and parts[2] else parts[1]).strip()
    return out


def lookup_vendor(mac: str | None, oui_db: dict[str, str]) -> str | None:
    if not mac or not oui_db or is_randomized_mac(mac):
        return None
    return oui_db.get(normalize_mac(mac).replace(":", "")[:6])


# Trefwoorden -> (type, icoon). Volgorde is belangrijk: eerste treffer wint.
_HOSTNAME_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("iphone", "ipad"), "iPhone / iPad", "📱"),
    (("android", "galaxy", "pixel", "oneplus", "xiaomi", "redmi", "huawei", "phone"), "Telefoon", "📱"),
    (("macbook", "imac", "mac-mini", "macmini", "laptop", "desktop-", "-pc", "thinkpad"), "Computer", "💻"),
    (("chromecast", "google-home", "googlehome", "nest"), "Google / Chromecast", "📺"),
    (("tv", "bravia", "webos", "tizen", "firetv", "fire-tv", "appletv", "apple-tv", "roku"), "TV / mediaspeler", "📺"),
    (("echo", "alexa", "amazon"), "Amazon Echo / Fire", "🔊"),
    (("sonos", "homepod"), "Speaker", "🔊"),
    (("hue", "philips-hue"), "Philips Hue bridge", "💡"),
    (("shelly", "tasmota", "esp", "sonoff", "tuya", "smartplug", "wled"), "Smart home (IoT)", "🔌"),
    (("playstation", "ps4", "ps5", "xbox", "nintendo", "switch"), "Spelcomputer", "🎮"),
    (("printer", "hp", "epson", "brother", "canon"), "Printer", "🖨️"),
    (("nas", "synology", "diskstation", "qnap"), "NAS", "🗄️"),
    (("raspberry", "raspberrypi", "pi-hole", "pihole"), "Raspberry Pi", "🍓"),
    (("homeassistant", "home-assistant", "hassio"), "Home Assistant", "🏠"),
    (("ring", "doorbell", "camera", "cam", "reolink", "arlo"), "Camera / deurbel", "📷"),
    (("fritz", "repeater", "extender", "deco", "orbi", "eero", "router", "ubnt", "unifi"), "Netwerk (router/repeater)", "📶"),
]

_VENDOR_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("espressif", "tuya", "shelly", "itead", "sonoff"), "Smart home (IoT)", "🔌"),
    (("raspberry",), "Raspberry Pi", "🍓"),
    (("signify", "philips lighting"), "Philips Hue bridge", "💡"),
    (("sonos",), "Speaker", "🔊"),
    (("amazon",), "Amazon Echo / Fire", "🔊"),
    (("google",), "Google / Chromecast", "📺"),
    (("synology", "qnap"), "NAS", "🗄️"),
    (("ring llc", "reolink", "hikvision", "dahua", "arlo"), "Camera / deurbel", "📷"),
    (("nintendo", "sony interactive", "microsoft"), "Spelcomputer", "🎮"),
    (("hewlett", "hp inc", "brother", "seiko epson", "canon"), "Printer", "🖨️"),
    (("avm", "ubiquiti", "tp-link", "netgear", "zyxel", "arcadyan", "sagemcom", "technicolor",
      "huawei technologies", "asustek", "linksys", "mikrotik"), "Netwerk (router/repeater)", "📶"),
    (("lg electronics", "samsung", "tcl", "hisense", "vizio", "roku"), "TV / mediaspeler", "📺"),
    (("apple",), "Apple-apparaat", ""),
    (("intel", "liteon", "azurewave", "dell", "lenovo", "asus", "realtek"), "Computer", "💻"),
]


def guess_device_type(
    hostname: str | None,
    vendor: str | None,
    open_ports: list[int] | None = None,
    randomized_mac: bool = False,
    is_gateway: bool = False,
    is_self: bool = False,
) -> tuple[str, str]:
    """Maak een redelijke gok naar het soort apparaat. Geeft (type, icoon)."""
    ports = set(open_ports or [])
    host = (hostname or "").lower()
    vend = (vendor or "").lower()

    if is_self:
        return "Deze computer", "💻"
    if is_gateway:
        return "Router", "📶"
    if 62078 in ports:
        return "iPhone / iPad", "📱"
    if 1400 in ports:
        return "Speaker", "🔊"
    if 8123 in ports:
        return "Home Assistant", "🏠"
    if ports & {8008, 8009}:
        return "Google / Chromecast", "📺"
    if ports & {9100, 631}:
        return "Printer", "🖨️"
    if 554 in ports:
        return "Camera / deurbel", "📷"

    if host:
        for keywords, kind, icon in _HOSTNAME_RULES:
            if any(k in host for k in keywords):
                return kind, icon
    if vend:
        for keywords, kind, icon in _VENDOR_RULES:
            if any(k in vend for k in keywords):
                if kind == "Apple-apparaat":
                    return ("Computer", "💻") if ports & {22, 445, 548, 7000} else ("Apple-apparaat", "🍏")
                return kind, icon
    if randomized_mac:
        return "Telefoon / tablet / laptop (privé-MAC)", "📱"
    if ports & {445, 548}:
        return "Computer", "💻"
    return "Onbekend", "❔"


# --------------------------------------------------------------------------- #
# Functies die het netwerk / besturingssysteem gebruiken.


def _run(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        flags = 0x08000000 if SYSTEM == "Windows" else 0  # CREATE_NO_WINDOW
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            errors="replace", creationflags=flags,
        )
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def get_local_ip() -> str:
    """Het IP-adres van deze computer op het thuisnetwerk.

    Een UDP-'verbinding' verstuurt niets; het laat alleen zien welke
    netwerkkaart het systeem zou gebruiken.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def guess_network(local_ip: str, prefix: int = 24) -> str:
    return str(ipaddress.ip_network(f"{local_ip}/{prefix}", strict=False))


def get_default_gateway() -> str | None:
    if SYSTEM == "Windows":
        return parse_default_gateway(_run(["route", "print", "0.0.0.0"]))
    if SYSTEM == "Darwin":
        return parse_default_gateway(_run(["route", "-n", "get", "default"]))
    return parse_default_gateway(_run(["ip", "route"]))


def read_arp_table() -> dict[str, str]:
    if SYSTEM == "Linux":
        text = ""
        try:
            text = Path("/proc/net/arp").read_text()
        except OSError:
            pass
        text += "\n" + _run(["ip", "neigh"])
        return parse_arp_table(text)
    if SYSTEM == "Darwin":
        return parse_arp_table(_run(["arp", "-a", "-n"]))
    return parse_arp_table(_run(["arp", "-a"]))


def _ping(ip: str, timeout_ms: int) -> bool:
    if SYSTEM == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    elif SYSTEM == "Darwin":
        cmd = ["ping", "-c", "1", "-W", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, round(timeout_ms / 1000))), ip]
    try:
        flags = 0x08000000 if SYSTEM == "Windows" else 0
        res = subprocess.run(cmd, capture_output=True, timeout=timeout_ms / 1000 + 2, creationflags=flags)
        # Windows geeft soms 0 terug bij "Destination host unreachable"; check op TTL.
        return res.returncode == 0 and (SYSTEM != "Windows" or b"TTL=" in res.stdout.upper())
    except (OSError, subprocess.SubprocessError):
        return False


def _tcp_state(ip: str, port: int, timeout: float) -> str:
    """'open', 'closed' (host leeft wel, poort dicht) of 'none' (geen antwoord)."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return "open"
    except ConnectionRefusedError:
        return "closed"
    except OSError:
        return "none"


def _probe_host(ip: str, timeout_ms: int) -> bool:
    if _ping(ip, timeout_ms):
        return True
    for port in PROBE_PORTS[:3]:
        if _tcp_state(ip, port, timeout_ms / 1000) != "none":
            return True
    return False


def _reverse_dns(ip: str) -> str | None:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return None
    return None if name == ip else name


def _scan_ports(ip: str, ports: list[int], timeout: float) -> list[int]:
    return sorted(p for p in ports if _tcp_state(ip, p, timeout) == "open")


def scan_network(
    network: str | None = None,
    scan_ports: bool = True,
    oui_db: dict[str, str] | None = None,
    timeout_ms: int = 800,
    workers: int = 128,
    progress=None,
) -> ScanResult:
    """Scan het netwerk. `progress(fractie, tekst)` wordt aangeroepen voor voortgang."""
    started = time.time()
    report = progress or (lambda frac, msg: None)
    local_ip = get_local_ip()
    net = ipaddress.ip_network(network or guess_network(local_ip), strict=False)
    if net.num_addresses > 4096:
        raise ValueError(f"Netwerk {net} is te groot (max /20, 4096 adressen).")
    gateway = get_default_gateway()
    hosts = [str(h) for h in net.hosts() if str(h) != local_ip]

    # Stap 1: iedereen 'aanporren' zodat de ARP-tabel gevuld wordt.
    alive: set[str] = set()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_host, ip, timeout_ms): ip for ip in hosts}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            if fut.result():
                alive.add(futures[fut])
            if i % 8 == 0 or i == len(hosts):
                report(0.7 * i / max(1, len(hosts)), f"Adressen controleren… {i}/{len(hosts)}")

    # Stap 2: ARP-tabel lezen. Apparaten die ping blokkeren staan hier toch in.
    arp = {ip: mac for ip, mac in read_arp_table().items() if ipaddress.ip_address(ip) in net}
    found = sorted(alive | set(arp), key=lambda ip: tuple(int(x) for x in ip.split(".")))

    devices = [Device(ip=ip, mac=arp.get(ip)) for ip in found]
    self_mac = uuid.getnode()  # bit 40 gezet = Python kon het echte MAC niet vinden
    self_hex = f"{self_mac:012x}"
    devices.append(Device(
        ip=local_ip,
        mac=None if (self_mac >> 40) & 0x01 else ":".join(self_hex[i:i + 2] for i in range(0, 12, 2)),
        hostname=socket.gethostname(),
        is_self=True,
    ))

    # Stap 3: verrijken met hostnaam en open poorten.
    report(0.75, f"{len(devices)} apparaten gevonden, namen en poorten ophalen…")
    port_list = sorted(COMMON_PORTS)
    with cf.ThreadPoolExecutor(max_workers=min(64, workers)) as pool:
        names = {d.ip: pool.submit(_reverse_dns, d.ip) for d in devices}
        port_futs = {
            d.ip: pool.submit(_scan_ports, d.ip, port_list, min(0.6, timeout_ms / 1000))
            for d in devices if scan_ports and not d.is_self
        }
        for d in devices:
            d.hostname = d.hostname or names[d.ip].result()
            if d.ip in port_futs:
                d.open_ports = port_futs[d.ip].result()

    for d in devices:
        d.is_gateway = d.ip == gateway
        d.randomized_mac = bool(d.mac) and is_randomized_mac(d.mac)
        d.vendor = lookup_vendor(d.mac, oui_db or {})
        d.device_type, d.icon = guess_device_type(
            d.hostname, d.vendor, d.open_ports, d.randomized_mac, d.is_gateway, d.is_self
        )

    devices.sort(key=lambda d: tuple(int(x) for x in d.ip.split(".")))
    report(1.0, "Klaar")
    return ScanResult(str(net), local_ip, gateway, started, time.time() - started, devices)


# --------------------------------------------------------------------------- #
# Fabrikantenlijst (OUI) downloaden en bewaren.


def load_oui_db(path: Path) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def download_oui_db(path: Path, timeout: float = 30.0) -> int:
    """Download de lijst met MAC-fabrikanten en sla hem op. Geeft het aantal regels."""
    errors = []
    for kind, url in OUI_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (thuis-dashboard)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            db = parse_oui_ieee_csv(text) if kind == "ieee" else parse_oui_manuf(text)
            if len(db) > 1000:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(db), encoding="utf-8")
                return len(db)
            errors.append(f"{url}: te weinig regels ({len(db)})")
        except Exception as exc:  # noqa: BLE001 - we proberen gewoon de volgende bron
            errors.append(f"{url}: {exc}")
    raise RuntimeError("Kon fabrikantenlijst niet downloaden:\n" + "\n".join(errors))


if __name__ == "__main__":
    # Snel testen vanaf de opdrachtregel: python network_scanner.py
    db = load_oui_db(Path(__file__).parent / "thuis_data" / "oui.json")
    result = scan_network(oui_db=db, progress=lambda f, m: print(f"\r{m:<60}", end=""))
    print(f"\n\nNetwerk {result.network} (router: {result.gateway}), {result.duration_s:.1f}s\n")
    for d in result.devices:
        print(f"{d.icon} {d.ip:<15} {d.mac or '-':<17} {d.device_type:<28} {d.hostname or ''} {d.vendor or ''}")
