{ pkgs, unstable, ... }:

let
  wifiDnsPolicy = pkgs.writeShellApplication {
    name = "kirax1-wifi-dns-policy";
    runtimeInputs = with pkgs; [ networkmanager systemd iproute2 ];
    text = ''
      exec ${pkgs.python3}/bin/python3 ${../../scripts/system/wifi-dns-policy.py} "$@"
    '';
  };

  wifiDnsDispatcher = pkgs.writeShellApplication {
    name = "kirax1-wifi-dns-dispatcher";
    runtimeInputs = [ pkgs.systemd ];
    text = ''
      case "''${2:-}" in
        up|down|dhcp4-change|dhcp6-change|dns-change|connectivity-change|vpn-up|vpn-down)
          # Serialize event/timer/startup reconciliation through one service.
          systemctl start --no-block kirax1-wifi-dns-policy.service
          ;;
      esac
    '';
  };

  captivePortalWatcher = pkgs.writeShellApplication {
    name = "captive-portal-watcher";
    runtimeInputs = with pkgs; [ coreutils gawk networkmanager systemd ];
    text = ''
      last_key=""
      last_opened=0

      wifi_key() {
        nmcli -t -f NAME,TYPE,DEVICE connection show --active \
          | awk -F: '$2 == "wifi" { print $1 ":" $3; exit }'
      }

      maybe_open_portal() {
        # Force an immediate check, then read NetworkManager's current state.
        state="$(nmcli networking connectivity check 2>/dev/null || true)"
        if [ "$state" != "portal" ]; then
          return 0
        fi

        # NetworkManager can report "portal" a moment before the Wi-Fi
        # connection is fully visible. Wait briefly so we do not launch bound to
        # an unknown/stale connection.
        key=""
        for _ in $(seq 1 15); do
          key="$(wifi_key)"
          [ -n "$key" ] && break
          sleep 1
        done
        key="''${key:-unknown}"

        # Avoid window spam, but allow a retry if the first browser was closed
        # before the captive portal login completed.
        now="$(date +%s)"
        if [ "$key" = "$last_key" ] && [ $((now - last_opened)) -lt 60 ]; then
          return 0
        fi
        last_key="$key"
        last_opened="$now"

        systemd-cat -t captive-portal-watcher echo "Captive portal detected on $key; launching captive-browser"
        /run/current-system/sw/bin/captive-browser &
      }

      maybe_open_portal

      while true; do
        nmcli monitor | while IFS= read -r _event; do
          sleep 2
          maybe_open_portal
        done
        sleep 2
      done
    '';
  };
in
{
  networking.hostName = "kirax1";

  networking.networkmanager = {
    enable = true;
    dns = "systemd-resolved";
    # Only the diagnosed DHCP resolver pair is replaced, after portal login.
    # Keep NM's original DHCP values for captive-browser and preserve resolved's
    # per-link routing domains (including Tailscale's more-specific routes).
    dispatcherScripts = [ { source = "${wifiDnsDispatcher}/bin/kirax1-wifi-dns-dispatcher"; } ];
    settings.connectivity = {
      enabled = true;
      uri = "http://nmcheck.gnome.org/check_network_status.txt";
      response = "NetworkManager is online";
      interval = 30;
    };
  };

  services.resolved.enable = true;

  # Reconcile an already-connected link after switching generations as well as
  # on subsequent NM events. Does not reconnect/rewrite any Wi-Fi profile.
  systemd.services.kirax1-wifi-dns-policy = {
    description = "Scoped workaround for unreliable Wi-Fi DHCP DNS";
    wantedBy = [ "multi-user.target" ];
    after = [ "NetworkManager.service" "systemd-resolved.service" ];
    serviceConfig = {
      Type = "oneshot";
      TimeoutStartSec = 20;
      ExecStart = "${wifiDnsPolicy}/bin/kirax1-wifi-dns-policy";
    };
  };

  # Tailscale exit-node/externally managed VPN routes can change without an NM
  # event. Recheck fresh state at a bounded cadence; never keep an active oneshot
  # that would prevent timer/event-triggered re-execution.
  systemd.timers.kirax1-wifi-dns-policy = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "20s";
      OnUnitInactiveSec = "15s";
      AccuracySec = "1s";
    };
  };

  services.nordvpn = {
    enable = true;
    package = unstable.nordvpn;
  };

  # Required for VPN traffic when the firewall is enabled.
  networking.firewall.checkReversePath = "loose";

  services.tailscale.enable = true;

  programs.captive-browser = {
    enable = true;
    interface = "wlp0s20f3";
    # Return only the DNS IP so captive-browser cannot accidentally pick up
    # another address from nmcli output. Fall back to the gateway for portals
    # that do not advertise DNS separately.
    dhcp-dns = ''
      ${pkgs.networkmanager}/bin/nmcli -g IP4.DNS dev show wlp0s20f3 | ${pkgs.coreutils}/bin/head -n1
      ${pkgs.networkmanager}/bin/nmcli -g IP4.GATEWAY dev show wlp0s20f3 | ${pkgs.coreutils}/bin/head -n1
    '';
    # Force X11/XWayland and disable GPU compositing; the default Chromium
    # command was logging Wayland/Vulkan errors on Hyprland.
    browser = ''
      env XDG_CONFIG_HOME="$PREV_CONFIG_HOME" ${pkgs.chromium}/bin/chromium \
        --user-data-dir=''${XDG_DATA_HOME:-$HOME/.local/share}/chromium-captive \
        --proxy-server="socks5://$PROXY" \
        --host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE localhost" \
        --no-first-run --new-window --incognito --no-default-browser-check \
        --ozone-platform=x11 --disable-gpu \
        http://neverssl.com/
    '';
  };

  systemd.user.services.captive-portal-watcher = {
    description = "Open a dedicated captive portal browser when NetworkManager detects a portal";
    wantedBy = [ "graphical-session.target" ];
    partOf = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    serviceConfig = {
      ExecStart = "${captivePortalWatcher}/bin/captive-portal-watcher";
      Restart = "always";
      RestartSec = 5;
    };
  };
}
