{ ... }:

{
  # Expose hardware sensor readings over D-Bus. This installs the matching udev
  # rules and service, but does not install/start an orientation controller or
  # change monitor, touch or pen transforms.
  hardware.sensor.iio.enable = true;
}
