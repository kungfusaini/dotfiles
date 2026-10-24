---------------
---- INPUT ----
---------------

hl.config({
    input = {
        kb_layout  = "gb",
        kb_variant = "",
        kb_model   = "",
        kb_options = "",
        kb_rules   = "",

        follow_mouse = 1,

        sensitivity    = 0, -- global pointer sensitivity
        force_no_accel = false,

        touchpad = {
            natural_scroll = false,
        },

        -- Let normal touchscreen taps/clicks reach clients.
        touchdevice = {
            enabled = true,
        },

        virtualkeyboard = {
            share_states = 2,
            release_pressed_on_close = true,
        },
    },

    gestures = {
        -- Hyprland's built-in 3-finger workspace swipe is trackpad-only unless
        -- this is enabled. Hyprgrass still handles the actual touchscreen gestures.
        workspace_swipe_touch = true,
        workspace_swipe_cancel_ratio = 0.15,
    },
})

hl.gesture({
    fingers = 3,
    direction = "horizontal",
    action = "workspace",
})

if hl.plugin.hyprgrass then
    hl.config({
        plugin = {
            hyprgrass = {
                sensitivity = 4.0,
                long_press_delay = 400,
                resize_on_border_long_press = true,
                edge_margin = 10,
            },
        },
    })

    -- Touchscreen gestures. The plain hl.gesture above is for touchpads; the
    -- hyprgrass API is needed for actual touchscreen input.
    hl.plugin.hyprgrass.gesture({
        pattern = { kind = "swipe", fingers = 3, direction = "horizontal" },
        action = "workspace",
        scale = 1.0,
    })

    hl.plugin.hyprgrass.bind({
        pattern = { kind = "tap", fingers = 3 },
        action = hl.dsp.window.float({ action = "toggle" }),
    })

    hl.plugin.hyprgrass.bind({
        pattern = { kind = "longpress", fingers = 3 },
        action = hl.dsp.window.drag(),
        mouse = true,
    })

    -- Swipe up from bottom edge toggles the on-screen keyboard.
    hl.plugin.hyprgrass.bind({
        pattern = { kind = "edge", origin = "down", direction = "up" },
        action = hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/nixos/hosts/kirax1/scripts/desktop/tablet-osk toggle"),
    })

    -- 3-finger swipe down hides it quickly if it is in the way.
    hl.plugin.hyprgrass.bind({
        pattern = { kind = "swipe", fingers = 3, direction = "down" },
        action = hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/nixos/hosts/kirax1/scripts/desktop/tablet-osk hide"),
    })
end

-- TrackPoint tuning
-- Device name from `hyprctl devices`: tpps/2-elan-trackpoint
hl.device({
    name          = "tpps/2-elan-trackpoint",
    sensitivity   = -0.50, -- -1.0 to 1.0; raise/lower this to taste
    accel_profile = "adaptive",
    scroll_method = "on_button_down",
    scroll_button = 274,   -- middle TrackPoint button scrolling
})
