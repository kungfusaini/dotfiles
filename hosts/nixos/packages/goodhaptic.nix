{ stdenv
, fetchFromGitHub
, gettext
, meson
, ninja
, pkg-config
, wrapGAppsHook4
, gtk4
, libadwaita
}:

# Goodix haptic touchpad utility. Upstream currently targets similar
# Goodix pads, but the ThinkPad GXTP5420 exposes the same HID reports.
stdenv.mkDerivation rec {
  pname = "goodhaptic";
  version = "1.1-unstable-2026-07-23";

  src = fetchFromGitHub {
    owner = "nwkyz";
    repo = "goodhaptic";
    rev = "4837e08f623e506859366803a7591a8cddae07ba";
    hash = "sha256-ZcdIW3mmzTMAeyZyMSXUk6bIh5S+dTCJ2dYa2KGlZoU=";
  };

  nativeBuildInputs = [
    gettext
    meson
    ninja
    pkg-config
    wrapGAppsHook4
  ];

  buildInputs = [
    gtk4
    libadwaita
  ];

  # Restrict the chooser to this laptop's Goodix GXTP5420 haptic touchpad only.
  # GXTP5420 also uses different feature report IDs from the GXTP5100 device
  # that goodhaptic targets upstream:
  #   0x08 = haptic strength 0-100
  #   0x0b = click force threshold 1-3
  postPatch = ''
    substituteInPlace src/haptic.c \
      --replace-fail '            /* read HID name from uevent */' '            char sys_dev_path[320];
            snprintf(sys_dev_path, sizeof(sys_dev_path),
                     "/sys/class/hidraw/%s/device", de->d_name);
            char dev_link[512];
            ssize_t dev_link_len = readlink(sys_dev_path, dev_link, sizeof(dev_link) - 1);
            if (dev_link_len < 0)
                continue;
            dev_link[dev_link_len] = 0;
            if (!strstr(dev_link, "0018:27C6:0F95"))
                continue;

            /* read HID name from uevent */'

    substituteInPlace src/haptic.c \
      --replace-fail '    buf[0] = 0x09;
    buf[1] = value;' '    buf[0] = 0x08;
    buf[1] = value;'

    substituteInPlace src/haptic.c \
      --replace-fail '    unsigned char buf[2];
    buf[0] = 0x08;
    buf[1] = value;

    int ret = ioctl(fd, HIDIOCSFEATURE(sizeof(buf)), buf);
    close(fd);
    return ret;
}


/*
 * haptic_get_capability' '    unsigned char buf[2];
    buf[0] = 0x0b;
    buf[1] = value;

    int ret = ioctl(fd, HIDIOCSFEATURE(sizeof(buf)), buf);
    close(fd);
    return ret;
}


/*
 * haptic_get_capability'
  '';
}
