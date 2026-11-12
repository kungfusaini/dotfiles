# nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
#   'config: import ./tests/x11-socket-audit.nix { inherit config; }'
{ config }:
let
  rules = config.security.audit.rules;
  settings = config.security.auditd.settings;
  expected = map
    (arch: "-a always,exit -F arch=${arch} -S unlink,unlinkat,rename,renameat,renameat2,rmdir -F dir=/tmp/.X11-unix/ -k x11_socket_changes")
    [ "b64" "b32" ];
in
assert config.security.audit.enable == true;
assert config.security.auditd.enable;
assert rules == expected;
assert builtins.elem "systemd-tmpfiles-setup.service" config.systemd.services.audit-rules-nixos.after;
assert config.systemd.services.auditd.serviceConfig.LogsDirectoryMode == "0700";
assert settings.log_group == "root";
assert settings.max_log_file == 8 && settings.num_logs == 4;
assert settings.max_log_file_action == "ROTATE";
assert settings.admin_space_left_action == "SUSPEND";
assert settings.disk_full_action == "SUSPEND" && settings.disk_error_action == "SUSPEND";
{
  inherit rules;
  logFile = settings.log_file;
  rotationMiB = settings.max_log_file;
  retainedLogs = settings.num_logs;
}
