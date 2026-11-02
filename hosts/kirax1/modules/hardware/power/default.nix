{ pkgs, ... }:

let
  syncSource = pkgs.writeText "sync-lenovo-platform-profile-epp.c" ''
    #define _GNU_SOURCE
    #include <ctype.h>
    #include <dirent.h>
    #include <errno.h>
    #include <fcntl.h>
    #include <glob.h>
    #include <limits.h>
    #include <poll.h>
    #include <signal.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>
    #include <sys/types.h>
    #include <unistd.h>

    static char thinkpad_profile[PATH_MAX];
    static char soc_profile[PATH_MAX];

    static void trim(char *s) {
      size_t len = strlen(s);
      while (len > 0 && isspace((unsigned char)s[len - 1])) s[--len] = '\0';
      char *start = s;
      while (*start && isspace((unsigned char)*start)) start++;
      if (start != s) memmove(s, start, strlen(start) + 1);
    }

    static int read_file(const char *path, char *buf, size_t len) {
      int fd = open(path, O_RDONLY | O_CLOEXEC);
      if (fd < 0) return -1;
      ssize_t n = read(fd, buf, len - 1);
      close(fd);
      if (n <= 0) return -1;
      buf[n] = '\0';
      trim(buf);
      return 0;
    }

    static int discover_profiles(void) {
      glob_t profiles;
      if (glob("/sys/class/platform-profile/platform-profile-*", 0, NULL, &profiles) != 0) {
        return -1;
      }

      for (size_t i = 0; i < profiles.gl_pathc; i++) {
        char name_path[PATH_MAX];
        char name[128];
        snprintf(name_path, sizeof(name_path), "%s/name", profiles.gl_pathv[i]);
        if (read_file(name_path, name, sizeof(name)) != 0) continue;

        if (strcmp(name, "thinkpad-acpi-profile") == 0) {
          snprintf(thinkpad_profile, sizeof(thinkpad_profile), "%s/profile", profiles.gl_pathv[i]);
        } else if (strcmp(name, "SoC Power Slider") == 0) {
          snprintf(soc_profile, sizeof(soc_profile), "%s/profile", profiles.gl_pathv[i]);
        }
      }

      globfree(&profiles);
      return thinkpad_profile[0] == '\0' ? -1 : 0;
    }

    static int write_profile(const char *path, const char *profile) {
      int fd = open(path, O_WRONLY | O_CLOEXEC);
      if (fd < 0) return -1;
      int rc = dprintf(fd, "%s\n", profile) < 0 ? -1 : 0;
      close(fd);
      return rc;
    }

    static void signal_waybar(void) {
      DIR *dir = opendir("/proc");
      if (!dir) return;

      struct dirent *ent;
      while ((ent = readdir(dir)) != NULL) {
        char *end = NULL;
        long pid = strtol(ent->d_name, &end, 10);
        if (!end || *end != '\0' || pid <= 1) continue;

        char comm_path[256];
        snprintf(comm_path, sizeof(comm_path), "/proc/%ld/comm", pid);

        char comm[128];
        if (read_file(comm_path, comm, sizeof(comm)) != 0) continue;

        if (strcmp(comm, "waybar") == 0 || strcmp(comm, ".waybar-wrapped") == 0) {
          kill((pid_t)pid, SIGRTMIN + 8);
        }
      }

      closedir(dir);
    }

    static void apply_profile(void) {
      char profile[64];
      if (read_file(thinkpad_profile, profile, sizeof(profile)) != 0) {
        fprintf(stderr, "Could not read the ThinkPad platform profile.\n");
        return;
      }

      const char *epp = NULL;
      if (strcmp(profile, "low-power") == 0) {
        epp = "power";
      } else if (strcmp(profile, "balanced") == 0) {
        epp = "balance_performance";
      } else if (strcmp(profile, "performance") == 0) {
        epp = "performance";
      } else {
        fprintf(stderr, "Unknown ThinkPad platform profile: %s\n", profile);
        return;
      }

      if (soc_profile[0] != '\0') {
        char current[64];
        if (read_file(soc_profile, current, sizeof(current)) == 0 && strcmp(current, profile) != 0) {
          if (write_profile(soc_profile, profile) != 0) {
            fprintf(stderr, "Could not sync SoC Power Slider to %s: %s\n", profile, strerror(errno));
          }
        }
      }

      glob_t globbuf;
      if (glob("/sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference", 0, NULL, &globbuf) == 0) {
        for (size_t i = 0; i < globbuf.gl_pathc; i++) {
          int fd = open(globbuf.gl_pathv[i], O_WRONLY | O_CLOEXEC);
          if (fd >= 0) {
            dprintf(fd, "%s\n", epp);
            close(fd);
          }
        }
        globfree(&globbuf);
      }

      signal_waybar();
    }

    int main(void) {
      if (discover_profiles() != 0) {
        fprintf(stderr, "The thinkpad-acpi platform profile provider was not found.\n");
        return 1;
      }

      const char *profile_paths[] = {
        thinkpad_profile,
        soc_profile,
        "/sys/firmware/acpi/platform_profile",
      };
      struct pollfd fds[3];
      nfds_t nfds = 0;

      for (size_t i = 0; i < sizeof(profile_paths) / sizeof(profile_paths[0]); i++) {
        if (profile_paths[i][0] == '\0') continue;
        int fd = open(profile_paths[i], O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;

        char buf[128];
        lseek(fd, 0, SEEK_SET);
        read(fd, buf, sizeof(buf));

        fds[nfds].fd = fd;
        fds[nfds].events = POLLPRI | POLLERR;
        nfds++;
      }

      if (nfds == 0) {
        fprintf(stderr, "No platform profile files available to watch.\n");
        return 1;
      }

      apply_profile();

      for (;;) {
        int rc = poll(fds, nfds, -1);
        if (rc < 0) {
          if (errno == EINTR) continue;
          perror("poll");
          return 1;
        }

        int changed = 0;
        for (nfds_t i = 0; i < nfds; i++) {
          if (fds[i].revents) {
            char buf[128];
            lseek(fds[i].fd, 0, SEEK_SET);
            read(fds[i].fd, buf, sizeof(buf));
            fds[i].revents = 0;
            changed = 1;
          }
        }

        if (changed) apply_profile();
      }
    }
  '';

  syncProgram = pkgs.stdenv.mkDerivation {
    pname = "sync-lenovo-platform-profile-epp";
    version = "2.0";
    src = syncSource;
    dontUnpack = true;
    installPhase = ''
      mkdir -p $out/bin
      $CC -O2 -Wall -Wextra -o $out/bin/sync-lenovo-platform-profile-epp $src
    '';
  };

  acProfileProgram = pkgs.writeShellApplication {
    name = "lenovo-ac-platform-profile";
    runtimeInputs = [ pkgs.coreutils pkgs.gnugrep ];
    text = ''
      set -euo pipefail

      profile_file=""
      choices_file=""
      state_file=/run/lenovo-platform-profile-before-ac

      for provider in /sys/class/platform-profile/platform-profile-*; do
        [[ -r "$provider/name" ]] || continue
        if [[ "$(<"$provider/name")" == "thinkpad-acpi-profile" ]]; then
          profile_file="$provider/profile"
          choices_file="$provider/choices"
          break
        fi
      done

      if [[ -z "$profile_file" || ! -w "$profile_file" ]]; then
        exit 0
      fi

      profile_supported() {
        local wanted="$1"
        [[ -r "$choices_file" ]] || return 1
        grep -qw -- "$wanted" "$choices_file"
      }

      ac_online=0
      for supply in /sys/class/power_supply/*; do
        [[ -d "$supply" ]] || continue
        [[ -r "$supply/online" ]] || continue
        [[ "$(<"$supply/online")" == "1" ]] || continue

        if [[ -r "$supply/type" ]]; then
          type="$(<"$supply/type")"
        else
          type=""
        fi

        case "$type" in
          Mains|USB|USB_C|USB_PD)
            ac_online=1
            break
            ;;
        esac
      done

      current="$(<"$profile_file")"

      if [[ "$ac_online" == "1" ]]; then
        if [[ ! -e "$state_file" ]]; then
          printf '%s\n' "$current" > "$state_file"
        fi

        if profile_supported performance && [[ "$current" != "performance" ]]; then
          printf 'performance\n' > "$profile_file"
        fi
      else
        if [[ -r "$state_file" ]]; then
          previous="$(<"$state_file")"
          if profile_supported "$previous" && [[ "$current" != "$previous" ]]; then
            printf '%s\n' "$previous" > "$profile_file"
          fi
          rm -f "$state_file"
        fi
      fi
    '';
  };
in
{
  environment.systemPackages = [
    pkgs.powertop
    pkgs.linuxPackages.turbostat
  ];

  # The thinkpad-acpi profile is the source of truth because the ThinkPad
  # power-mode button changes that provider. Keep the separate Intel SoC Power
  # Slider provider aligned so the kernel's aggregate profile never becomes
  # "custom".
  #
  # Also keep Intel's Energy Performance Preference aligned with that mode:
  #   low-power   -> power
  #   balanced    -> balance_performance
  #   performance -> performance
  #
  # This is event-driven: the daemon blocks in poll(2) on both provider profile
  # attributes and the legacy aggregate attribute. The aggregate is required
  # because writes to an individual provider notify it, but do not necessarily
  # notify that provider's own attribute. Reassert the ThinkPad profile when any
  # of them changes and signal Waybar's custom/platform-profile module immediately.
  systemd.services.lenovo-platform-profile-epp-sync = {
    description = "Sync Intel platform profile and EPP from ThinkPad profile";
    wantedBy = [ "multi-user.target" ];
    after = [ "multi-user.target" "lenovo-ac-platform-profile.service" ];
    serviceConfig = {
      Type = "simple";
      ExecStart = "${syncProgram}/bin/sync-lenovo-platform-profile-epp";
      Restart = "always";
      RestartSec = 2;
    };
  };

  systemd.services.lenovo-ac-platform-profile = {
    description = "Switch Lenovo platform profile to performance on AC and restore on battery";
    wantedBy = [ "multi-user.target" ];
    after = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${acProfileProgram}/bin/lenovo-ac-platform-profile";
    };
  };

  # Preserve the running session before the battery reaches hardware cutoff.
  # Two percent leaves only a narrow reserve, so hibernation must be verified
  # manually after deployment before this policy is relied upon.
  services.upower = {
    enable = true;
    usePercentageForPolicy = true;
    percentageLow = 10;
    percentageCritical = 5;
    percentageAction = 2;
    criticalPowerAction = "Hibernate";
  };

  services.udev.extraRules = ''
    SUBSYSTEM=="power_supply", ACTION=="change", TAG+="systemd", ENV{SYSTEMD_WANTS}+="lenovo-ac-platform-profile.service"
  '';
}
