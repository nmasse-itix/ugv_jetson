#!/usr/bin/env python3
"""Strip a laptop's NM keyfile down to what a headless fleet node should carry.

Never prints secrets: the summary redacts every key under [wifi-security] and
[802-1x]. What goes out is a profile bound to no interface, no MAC, no uuid and
no user permission -- so it applies to whichever radio the Orin presents, and
NetworkManager owns it at boot rather than a logged-in user.

Usage:
    sudo cat /etc/NetworkManager/system-connections/<ssid>.nmconnection \
      | ./sanitize-wifi-profile.py [autoconnect-priority] > wifi/<ssid>.nmconnection
"""
import configparser, sys

KEEP = {
    "connection": {"id", "type", "autoconnect", "autoconnect-priority"},
    "wifi": {"mode", "ssid", "band", "hidden"},
    "wifi-security": None,          # None = keep the whole section
    "802-11-wireless": {"mode", "ssid", "band", "hidden"},
    "802-11-wireless-security": None,
    "ipv4": {"method"},
    "ipv6": {"method"},
}
SECRET_SECTIONS = {"wifi-security", "802-11-wireless-security", "802-1x"}

src = configparser.RawConfigParser()
src.optionxform = str
src.read_string(sys.stdin.read())

out = configparser.RawConfigParser()
out.optionxform = str
for section in src.sections():
    if section not in KEEP:
        continue
    allowed = KEEP[section]
    kept = {k: v for k, v in src[section].items() if allowed is None or k in allowed}
    if kept:
        out[section] = kept

# Fleet defaults, applied after the copy so the source machine's habits do not travel.
out["connection"]["autoconnect"] = "true"
out["connection"]["autoconnect-priority"] = sys.argv[1] if len(sys.argv) > 1 else "20"
# Measured on robot B, 2026-08-21: with the radio's default power save on, ping
# from the same /24 averaged 171 ms with 122 ms of jitter (min 1.3 ms -- the link
# is fast, the station is asleep). powersave=2 (off) took it to 3.0 ms / 1.7 ms.
# Ringside streams camera frames over that link; the default is not survivable.
out["wifi"]["powersave"] = "2"
out["ipv4"] = {"method": "auto"}
out["ipv6"] = {"method": "disabled"}   # the install disables v6 on the wired NIC too

out.write(sys.stdout, space_around_delimiters=False)

print("--- profile written (secrets redacted) ---", file=sys.stderr)
for section in out.sections():
    for k, v in out[section].items():
        shown = "<redacted>" if section in SECRET_SECTIONS and k != "key-mgmt" else v
        print(f"  [{section}] {k}={shown}", file=sys.stderr)
