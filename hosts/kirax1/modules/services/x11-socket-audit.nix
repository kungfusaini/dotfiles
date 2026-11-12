{ ... }:

{
  # Diagnose disappearing XWayland socket paths without changing X11 transport
  # or repairing sockets automatically. Include both native and compat callers.
  security.audit = {
    enable = true;
    rules = map
      (arch: "-a always,exit -F arch=${arch} -S unlink,unlinkat,rename,renameat,renameat2,rmdir -F dir=/tmp/.X11-unix/ -k x11_socket_changes")
      [ "b64" "b32" ];
  };

  # The directory watch requires the directory to exist, including at boot.
  systemd.services.audit-rules-nixos.after = [ "systemd-tmpfiles-setup.service" ];

  security.auditd = {
    enable = true;
    settings = {
      log_file = "/var/log/audit/audit.log";
      log_group = "root";
      max_log_file = 8;
      num_logs = 4;
      max_log_file_action = "ROTATE";
      space_left_action = "SYSLOG";
      admin_space_left_action = "SUSPEND";
      disk_full_action = "SUSPEND";
      disk_error_action = "SUSPEND";
    };
  };
}
