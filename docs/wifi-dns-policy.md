# Scoped Wi-Fi DNS workaround (kirax1)

`hosts/kirax1/modules/core/networking.nix` packages the host-side
`hosts/kirax1/scripts/system/wifi-dns-policy.py` as a serialized NM-event/startup oneshot and a
15-second inactive timer (1-second accuracy, 20-second service timeout). The
NM dispatcher requests that service without blocking network activation;
VPN actions trigger it too. The timer covers external exit-node/VPN route
changes even when NetworkManager's connectivity state stays `full`. It is not run from the checkout.

Only `wlp0s20f3` networks advertising exclusively the diagnosed unreliable DHCP
servers (`18.135.144.127`, `13.41.170.91`) qualify. After NetworkManager reports
full connectivity, and routes to both replacement resolvers use Wi-Fi, the
policy sets that resolved link's servers to `1.1.1.1` and `9.9.9.9`.

It changes no connection profile, DHCP data, search/routing domain, Tailscale
link or other interface. Captive-browser keeps reading original DHCP DNS from
NM. Portal/limited/unknown connectivity, a VPN/exit-node route, or unreadable
routing restores original DHCP servers when the current values match this
policy. Foreign overrides and other DHCP server lists are left alone. Repeated
events are idempotent. This narrow rule is not a general guarantee that public
DNS works on every network or that route transitions are instantaneous. Events
and periodic checks converge to fresh routing state; scheduling/execution add
to the timer cadence.

Validation:

```sh
python -m unittest discover -s tests -p test_wifi_dns_policy.py -v
nix eval --raw .#nixosConfigurations.kirax1.config.system.build.toplevel.drvPath
```

Deployment requires the ordinary operator-run rebuild. Source evaluation is
not deployment proof. Afterwards inspect `resolvectl dns wlp0s20f3`, verify
repeated DNS/API reads and Tailscale routing, and check the oneshot/dispatcher
journal. Portal and VPN transitions require verification when those states are
available; unit mocks do not establish live transition behavior.
