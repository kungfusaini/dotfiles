{ pkgs, ... }:

let
  syncSource = pkgs.writeText "sync-lenovo-platform-profile-epp.c" ''
    #define _GNU_SOURCE
    #include <ctype.h>
    #include <dirent.h>
    #include <errno.h>
    #include <fcntl.h>
    #include <glob.h>
    #include <poll.h>
    #include <signal.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>
    #include <sys/types.h>
    #include <unistd.h>

    static const char *profile_paths[] = {
      "/sys/firmware/acpi/platform_profile",
      "/sys/class/platform-profile/platform-profile-0/profile",
      "/sys/class/platform-profile/platform-profile-1/profile",
      "/sys/class/platform-profile/platform-profile-2/profile",
      "/sys/class/platform-profile/platform-profile-3/profile",
    };

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

    static int read_profile(char *profile, size_t len) {
      for (size_t i = 0; i < sizeof(profile_paths) / sizeof(profile_paths[0]); i++) {
        if (read_file(profile_paths[i], profile, len) == 0) return 0;
      }
      return -1;
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
      if (read_profile(profile, sizeof(profile)) != 0) {
        fprintf(stderr, "No platform profile support found; nothing to sync.\n");
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
        fprintf(stderr, "Unknown platform profile: %s\n", profile);
        return;
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
      struct pollfd fds[sizeof(profile_paths) / sizeof(profile_paths[0])];
      nfds_t nfds = 0;

      for (size_t i = 0; i < sizeof(profile_paths) / sizeof(profile_paths[0]); i++) {
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
        return 0;
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
    version = "1.0";
    src = syncSource;
    dontUnpack = true;
    installPhase = ''
      mkdir -p $out/bin
      $CC -O2 -Wall -Wextra -o $out/bin/sync-lenovo-platform-profile-epp $src
    '';
  };
in
{
  # The Lenovo/Firmware platform profile is the source of truth. The ThinkPad
  # power-mode button cycles /sys/firmware/acpi/platform_profile through:
  # low-power, balanced, performance.
  #
  # Keep Intel's Energy Performance Preference aligned with that hardware mode:
  #   low-power   -> power
  #   balanced    -> balance_performance
  #   performance -> performance
  #
  # This is event-driven: the daemon blocks in poll(2) on the kernel platform
  # profile sysfs attributes and only wakes when the platform profile changes.
  # It also signals Waybar's custom/platform-profile module immediately.
  systemd.services.lenovo-platform-profile-epp-sync = {
    description = "Sync Intel EPP from Lenovo platform profile";
    wantedBy = [ "multi-user.target" ];
    after = [ "multi-user.target" ];
    serviceConfig = {
      Type = "simple";
      ExecStart = "${syncProgram}/bin/sync-lenovo-platform-profile-epp";
      Restart = "always";
      RestartSec = 2;
    };
  };
}
