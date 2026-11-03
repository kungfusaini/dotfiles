# Sensor-service-only readiness check

`hosts/kirax1/modules/hardware/sensors.nix` enables NixOS's
`hardware.sensor.iio` integration. This installs iio-sensor-proxy, its D-Bus
policy, udev classification/activation rules and systemd unit. It does not
add an orientation client, change display/touch/pen transforms, start the
keyboard preview, or enter the tablet workspace.

Do not launch tablet mode or apply a transform without a separate explicit
request from Sumeet, including during validation.

## Non-privileged validation

```sh
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/sensor-service.nix { inherit config; }'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

## After separately approved deployment

1. Record the current Hyprland instance, active workspace and monitor/input
   transforms. They must remain unchanged throughout this check.
2. Check the current IIO device named `accel_3d`, not a hard-coded device index.
   Confirm `IIO_SENSOR_PROXY_TYPE` includes `iio-buffer-accel`. If its metadata
   predates the newly installed rules, arrange a targeted privileged udev change
   event for that sensor only and settle; do not broadly trigger other devices
   or reboot/log out. Never change sensor driver bindings for this check.
3. Ensure Mewtion is not using the accelerometer. Its buffered reader and
   iio-sensor-proxy may compete for the same scan buffer. Do not disable or
   restart a running Mewtion session just to proceed; report the conflict.
4. Confirm the sensor service started after classification. This package is
   activated through udev/systemd, not a D-Bus activation file; a D-Bus query
   alone cannot start an inactive service. Query
   `net.hadess.SensorProxy.HasAccelerometer` over system D-Bus once it is running.
   A real `true` result is required; merely seeing files in sysfs is not proof
   of a usable service.
5. Run the deployed `monitor-sensor --accel` with a bounded timeout (for example
   10 seconds). It claims the sensor, prints orientation readings and releases
   the claim when it exits. No rotation command is involved. Do not ask Sumeet
   to fold or turn the machine during this initial stationary detection check.
6. Confirm service logs identify a buffered accelerometer and check that the
   buffer is released when the last client exits. Verify no new system/user
   failures and unchanged Hyprland instance/workspace/transforms.

The ThinkPad's existing Mewtion patch documents stale raw HID sysfs readings;
iio-sensor-proxy 3.9 prefers its buffered accelerometer driver before its raw
poll driver. If the buffered path fails, report it rather than adding a raw
polling rotation script. Sensor recognition, stable readings and physical
orientation mapping are separate acceptance steps.

A later controller must gate readings/rotation to the explicitly requested
active tablet posture, release the sensor when unused, handle headless mode
and suspend/resume, target only the internal display/touch/pen, and restore
saved transforms on exit. None of that controller is implemented here.

Reference: [SensorProxy API](https://hadess.pages.freedesktop.org/iio-sensor-proxy/gdbus-net.hadess.SensorProxy.html).
