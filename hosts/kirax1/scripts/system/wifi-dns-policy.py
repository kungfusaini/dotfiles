"""Narrow DNS workaround for kirax1's observed unreliable DHCP resolvers.

Never alter connection profiles, DHCP data or resolved routing/search domains.
Captive-browser continues to use NM's original DHCP DNS. Other networks and
foreign per-link DNS overrides are left alone. Runs only via the packaged NM
dispatcher/startup integration, not from the checkout.
"""
import ipaddress
import json
import os
import subprocess
import sys

DEVICE = "wlp0s20f3"
UNRELIABLE = {"18.135.144.127", "13.41.170.91"}
REPLACEMENTS = ["1.1.1.1", "9.9.9.9"]


def output(*command):
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=3,
                          env={**os.environ, "LC_ALL": "C"}).stdout.strip()


def apply(interface="", action="connectivity-change"):
    if action not in ("up", "dhcp4-change", "dhcp6-change", "dns-change", "connectivity-change", "vpn-up", "vpn-down"):
        return False
    if action not in ("vpn-up", "vpn-down") and interface not in ("", "none", DEVICE):
        return False
    # nmcli 1.56 joins array members with ' | '; IPv6 can occupy another line.
    raw = output("nmcli", "-e", "no", "-g", "IP4.DNS,IP6.DNS", "device", "show", DEVICE)
    dhcp = [str(ipaddress.ip_address(value.strip())) for line in raw.splitlines()
            for value in line.split("|") if value.strip()]
    if not dhcp or not set(dhcp) <= UNRELIABLE:
        return False
    rows = json.loads(output("resolvectl", "--json=short", "dns", DEVICE))
    current = [server["addressString"] for row in rows if row["ifname"] == DEVICE for server in row["servers"]]
    if set(current) not in (set(dhcp), set(REPLACEMENTS)):
        return False  # Another DNS/VPN controller owns this link; do not replace it.
    desired = dhcp
    try:
        full = output("nmcli", "-g", "CONNECTIVITY", "general") == "full"
        direct = full and all(json.loads(output("ip", "-json", "route", "get", server))[0]["dev"] == DEVICE
                              for server in REPLACEMENTS)
        if direct:
            desired = REPLACEMENTS
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        pass  # Unknown connectivity/routing: restore the original DHCP choice.
    if current == desired:
        return False
    output("resolvectl", "dns", DEVICE, *desired)
    return True


def main():
    try:
        changed = apply(*sys.argv[1:])
        if changed:
            print("kirax1 Wi-Fi DNS policy reconciled (profiles and routing domains unchanged)")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        print("kirax1 Wi-Fi DNS policy could not read/reconcile link state", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
