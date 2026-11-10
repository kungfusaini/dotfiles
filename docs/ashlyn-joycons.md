# Ashlyn's combined Joy-Cons

`hosts/kirax1/modules/desktop/gaming.nix` enables the packaged upstream
[joycond](https://github.com/DanielOgorchock/joycond) daemon with a local override
in `hosts/kirax1/packages/ashlyn-joycond/`.

Only these Bluetooth controllers are managed:

- Left: `58:B0:3E:4B:7E:DD`, Bluetooth alias `Ashlyn's Joy Cons (L)`.
- Right: `58:B0:3E:4B:83:C2`, Bluetooth alias `Ashlyn's Joy Cons (R)`.

After connecting both, press **L on the left and R on the right together**
(the outer shoulder buttons, not the inner rail SL/SR buttons). joycond creates
one virtual gamepad named **Ashlyn's Joy Cons**. Repeat after reconnecting if the
combined gamepad is absent. Avoid pressing both shoulder buttons on one half:
upstream joycond treats that as a request to use a standalone controller.

## Preserve the Pro Controllers

Do not enable stock joycond rules unmodified. They intercept Pro Controller
input and hidraw access, potentially changing the native identity used by
Steam Input. Our package replaces **both** rule files with exact-address
filters. Hidraw filtering runs at **71**, before `73-seat-late.rules` can queue
an ACL grant; the stock 89 rule is replaced with a comment-only file. Removing
`uaccess` only at 89 would leave an already-queued ACL grant in effect.
No Pro Controller receives the `joycond` tag or has its permissions
changed. No Steam configuration, custom mapping, emulator setting or save is
written by this setup.

The two physical gamepad halves (evdev and legacy js nodes) are root-only;
joycond reads and grabs their evdev nodes. Their exact hidraw devices are also
root-only so Steam/SDL cannot open them separately and bypass the combination.
IMU nodes are left alone. The virtual device retains upstream's IDs and normal
gamepad access. The Bluetooth aliases name the physical devices; the package's
single source substitution names the virtual device.

## Deployment and verification

Run `python3 -m unittest discover -s tests -p test_ashlyn_joycond.py -v` and build
the configured `services.joycond.package`. Its inherited udev install check
validates the installed replacement rules. Build the exact committed system
snapshot before deployment via `deploy-kirax1`.

For first rollout, reconnect **only these two Joy-Cons** after deployment so
new permissions and tags apply to fresh nodes. Reloading udev rules alone does
not revoke old open file descriptors or existing ACLs. Do not restart Steam or
reconnect a Pro Controller to apply this change.

Check `systemctl status joycond` and its journal, the `joycond` tags on the
physical event nodes, and `/proc/bus/input/devices` for the combined name.
Verify Pro Controller event/hidraw nodes retain their original access and that
the daemon holds no Pro Controller file descriptor. Test both sticks/buttons
on the combined device before claiming input works; an in-game test is a
separate final confirmation.
