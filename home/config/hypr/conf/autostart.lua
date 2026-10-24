-------------------
---- AUTOSTART ----
-------------------

hl.on("hyprland.start", function ()
    local home = os.getenv("HOME")

    hl.exec_cmd("nix shell nixpkgs#swaybg -c swaybg -i " .. home .. "/Pictures/Wallpapers/Bliss-HD.png -m fill")

    -- Reloads can briefly overlap with the old Waybar process; wait before
    -- checking so exactly one replacement is started when needed.
    hl.exec_cmd("sleep 1; pgrep -x waybar >/dev/null || waybar")
    hl.exec_cmd(home .. "/.config/nixos/hosts/kirax1/scripts/desktop/tablet-osk daemon")
end)
