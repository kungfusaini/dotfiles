{ ... }:

{
  services.pulseaudio.enable = false;
  security.rtkit.enable = true;

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;

    # Use high-quality A2DP for normal playback, automatically switch to the
    # negotiated HFP headset codec while the Bluetooth mic is in use, and
    # restore A2DP when the recording stream closes.
    wireplumber.extraConfig."10-bluetooth-headset" = {
      "wireplumber.settings" = {
        "bluetooth.autoswitch-to-headset-profile" = true;
      };

      "monitor.bluez.properties" = {
        # Keep WirePlumber's default A2DP/HFP roles and codec negotiation.
        # mSBC is an HFP fallback; this does not override supported LC3-SWB.
        "bluez5.enable-sbc-xq" = true;
        "bluez5.enable-msbc" = true;
      };

      "monitor.bluez.rules" = [
        {
          matches = [
            { "device.name" = "~bluez_card.*"; }
          ];
          actions.update-props = {
            "bluez5.auto-connect" = [ "a2dp_sink" ];
            "bluez5.a2dp.ldac.quality" = "hq";
          };
        }
      ];
    };
  };
}
