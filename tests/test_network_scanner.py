import home_store
import network_scanner as ns

WINDOWS_ARP = """
Interface: 192.168.1.23 --- 0x7
  Internet Address      Physical Address      Type
  192.168.1.1           3c-a6-2f-11-22-33     dynamic
  192.168.1.40          30-05-5c-aa-bb-cc     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""

MAC_ARP = """? (192.168.1.1) at 3c:a6:2f:11:22:33 on en0 ifscope [ethernet]
? (192.168.1.12) at 0:1a:2b:3:4d:5e on en0 ifscope [ethernet]
? (192.168.1.13) at (incomplete) on en0 ifscope [ethernet]
"""

LINUX_PROC_ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         3c:a6:2f:11:22:33     *        wlan0
192.168.1.77     0x1         0x0         00:00:00:00:00:00     *        wlan0
"""

LINUX_IP_NEIGH = """192.168.1.20 dev wlan0 lladdr ba:7e:21:0c:9d:12 STALE
192.168.1.21 dev wlan0 FAILED
fe80::1 dev wlan0 lladdr 3c:a6:2f:11:22:33 router REACHABLE
"""


def test_parse_arp_windows():
    assert ns.parse_arp_table(WINDOWS_ARP) == {
        "192.168.1.1": "3c:a6:2f:11:22:33",
        "192.168.1.40": "30:05:5c:aa:bb:cc",
    }


def test_parse_arp_macos_pads_and_skips_incomplete():
    assert ns.parse_arp_table(MAC_ARP) == {
        "192.168.1.1": "3c:a6:2f:11:22:33",
        "192.168.1.12": "00:1a:2b:03:4d:5e",
    }


def test_parse_arp_linux():
    assert ns.parse_arp_table(LINUX_PROC_ARP + LINUX_IP_NEIGH) == {
        "192.168.1.1": "3c:a6:2f:11:22:33",
        "192.168.1.20": "ba:7e:21:0c:9d:12",
    }


def test_default_gateway_all_platforms():
    assert ns.parse_default_gateway("default via 192.168.1.1 dev wlan0 proto dhcp") == "192.168.1.1"
    assert ns.parse_default_gateway("   route to: default\n    gateway: 192.168.178.1\n") == "192.168.178.1"
    win = "Active Routes:\nNetwork Destination        Netmask          Gateway       Interface  Metric\n" \
          "          0.0.0.0          0.0.0.0      10.0.0.138      10.0.0.12     35\n"
    assert ns.parse_default_gateway(win) == "10.0.0.138"
    assert ns.parse_default_gateway("nothing here") is None


def test_randomized_mac():
    assert ns.is_randomized_mac("ba:7e:21:0c:9d:12")
    assert ns.is_randomized_mac("5E-2A-91-77-01-3C")
    assert not ns.is_randomized_mac("3c:a6:2f:11:22:33")


def test_oui_parsers_and_lookup():
    ieee = 'Registry,Assignment,Organization Name,Organization Address\n' \
           'MA-L,3CA62F,AVM GmbH,"Berlin DE"\n'
    manuf = "# comment\n00:11:32\tSynology\tSynology Incorporated\n00:55:DA:00/28\tX\tY\n"
    db = {**ns.parse_oui_ieee_csv(ieee), **ns.parse_oui_manuf(manuf)}
    assert db == {"3ca62f": "AVM GmbH", "001132": "Synology Incorporated"}
    assert ns.lookup_vendor("3C-A6-2F-00-00-01", db) == "AVM GmbH"
    assert ns.lookup_vendor("ba:7e:21:0c:9d:12", db) is None  # privé-MAC heeft geen fabrikant


def test_builtin_vendor_without_download():
    assert ns.lookup_vendor("00:11:32:aa:bb:cc") == "Synology Incorporated"
    assert "AVM" in ns.lookup_vendor("3c:a6:2f:11:22:33", {})
    assert ns.lookup_vendor("3c:a6:2f:11:22:33", {"3ca62f": "AVM GmbH"}) == "AVM GmbH"  # download wint
    assert ns.guess_device_type(None, ns.lookup_vendor("3c:a6:2f:11:22:33"))[0].startswith("Netwerk")


def test_guess_device_type():
    assert ns.guess_device_type(None, None, is_gateway=True)[0] == "Router"
    assert ns.guess_device_type(None, None, [62078])[0] == "iPhone / iPad"
    assert ns.guess_device_type("DESKTOP-AB12CD.fritz.box", None)[0] == "Computer"
    assert ns.guess_device_type(None, "Espressif Inc.")[0] == "Smart home (IoT)"
    assert ns.guess_device_type(None, "Apple, Inc.")[0] == "Apple-apparaat"
    assert ns.guess_device_type(None, None, randomized_mac=True)[0].startswith("Telefoon")
    assert ns.guess_device_type(None, None) == ("Onbekend", "❔")


def test_merge_scan_tracks_new_and_seen():
    store = {}
    scan = {"started_at": 100.0, "devices": [
        {"key": "aa:aa:aa:aa:aa:aa", "ip": "192.168.1.5", "mac": "aa:aa:aa:aa:aa:aa"},
        {"key": "ip:192.168.1.1", "ip": "192.168.1.1", "is_gateway": True},
    ]}
    assert home_store.merge_scan(store, scan) == ["aa:aa:aa:aa:aa:aa", "ip:192.168.1.1"]
    assert store["ip:192.168.1.1"]["trusted"] is True
    store["aa:aa:aa:aa:aa:aa"]["name"] = "Telefoon"
    scan2 = {"started_at": 200.0, "devices": [scan["devices"][0] | {"ip": "192.168.1.6"}]}
    assert home_store.merge_scan(store, scan2) == []
    e = store["aa:aa:aa:aa:aa:aa"]
    assert (e["name"], e["first_seen"], e["last_seen"], e["ip"]) == ("Telefoon", 100.0, 200.0, "192.168.1.6")
    rows = home_store.build_rows(store, scan2)
    assert [r["online"] for r in rows] == [True, False]


def test_demo_data_is_consistent():
    scan, store = home_store.demo_data(now=1_000_000.0)
    rows = home_store.build_rows(store, scan)
    assert len(rows) == len(home_store._DEMO)
    assert sum(r["online"] for r in rows) == len(home_store._DEMO) - 1
