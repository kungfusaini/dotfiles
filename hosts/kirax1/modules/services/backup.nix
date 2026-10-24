{ config, pkgs, ... }:

let
  backupMount = "/mnt/kirax1-backup";
  backupUuid = "7BF6-D6FE";
  backupSerial = "S6PYNL0Y412139W";
  backupUnit = "restic-backups-kirax1-local.service";

  mkNotification = name: urgency: icon: summary: body:
    pkgs.writeShellScript name ''
      if [[ -S /run/user/1000/bus ]]; then
        ${pkgs.util-linux}/bin/runuser -u sumeet -- \
          ${pkgs.coreutils}/bin/env \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
            ${pkgs.libnotify}/bin/notify-send \
              --app-name="Kirax1 Backup" \
              --urgency=${urgency} \
              --icon=${icon} \
              ${builtins.toJSON summary} \
              ${builtins.toJSON body} \
          || true
      fi
    '';

  notifyStart = mkNotification
    "kirax1-backup-start-notification"
    "normal"
    "drive-harddisk"
    "Backup drive inserted"
    "Backing up this laptop to Shared Data…";

  notifyComplete = mkNotification
    "kirax1-backup-complete-notification"
    "normal"
    "emblem-default"
    "Backup complete"
    "Shared Data was safely unmounted and can now be unplugged.";

  notifyFailure = mkNotification
    "kirax1-backup-failure-notification"
    "critical"
    "dialog-error"
    "Backup failed"
    "Shared Data has been left mounted. Check the system backup log.";
in
{
  sops = {
    defaultSopsFile = ../../../../sops/kirax1.yaml;
    age.keyFile = "/home/sumeet/.config/sops/age/keys.txt";
    secrets.restic-kirax1-password = {
      owner = "root";
      group = "root";
      mode = "0400";
    };
  };

  fileSystems.${backupMount} = {
    device = "/dev/disk/by-uuid/${backupUuid}";
    fsType = "exfat";
    options = [
      "noauto"
      "nofail"
      "uid=0"
      "gid=0"
      "fmask=0077"
      "dmask=0077"
      "x-systemd.automount"
      "x-systemd.idle-timeout=2min"
      "x-systemd.device-timeout=5s"
    ];
  };

  services.restic.backups.kirax1-local = {
    repository = "${backupMount}/restic-kirax1";
    passwordFile = config.sops.secrets.restic-kirax1-password.path;
    paths = [ "/home/sumeet" ];
    exclude = [
      "/home/sumeet/.cache"
      "/home/sumeet/.local/share/Trash"
      "/home/sumeet/mnt"
      "/home/sumeet/matrix/models"
      "/home/sumeet/.local/state/kirax1-backup-test"
      "**/node_modules"
      "**/.venv"
      "**/venv"
      "**/__pycache__"
      "**/.direnv"
    ];
    extraBackupArgs = [
      "--one-file-system"
      "--exclude-caches"
      "--tag=automatic-usb"
    ];
    pruneOpts = [
      "--keep-daily 7"
      "--keep-weekly 8"
      "--keep-monthly 12"
      "--keep-yearly 3"
    ];
    initialize = true;
    timerConfig = null;
    inhibitsSleep = true;
    runCheck = true;
    checkOpts = [ ];
    progressFps = 0.1;
  };

  # Trigger only for this filesystem on this physical SSD.
  services.udev.extraRules = ''
    ACTION=="add", SUBSYSTEM=="block", ENV{DEVTYPE}=="partition", ENV{ID_FS_UUID}=="${backupUuid}", ENV{ID_SERIAL_SHORT}=="${backupSerial}", TAG+="systemd", ENV{SYSTEMD_WANTS}+="${backupUnit}"
  '';

  systemd.services.restic-backups-kirax1-local = {
    unitConfig.RequiresMountsFor = [ backupMount ];
    environment.GOGC = "50";
    onSuccess = [ "kirax1-backup-complete.service" ];
    onFailure = [ "kirax1-backup-failure.service" ];
    preStart = ''
      ${notifyStart}
    '';
  };

  systemd.services.kirax1-backup-complete = {
    description = "Unmount the Kirax1 backup drive and report success";
    serviceConfig.Type = "oneshot";
    script = ''
      ${pkgs.coreutils}/bin/sync
      ${pkgs.util-linux}/bin/umount ${backupMount}
      ${notifyComplete}
    '';
  };

  systemd.services.kirax1-backup-failure = {
    description = "Report a failed Kirax1 backup";
    serviceConfig.Type = "oneshot";
    script = ''
      ${notifyFailure}
    '';
  };

  environment.systemPackages = [
    pkgs.age
    pkgs.sops
  ];
}
