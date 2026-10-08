--------------------------------
---- WINDOWS AND WORKSPACES ----
--------------------------------

-- Example smart-gap rules, disabled for now.
-- hl.workspace_rule({ workspace = "w[tv1]", gaps_out = 0, gaps_in = 0 })
-- hl.workspace_rule({ workspace = "f[1]",   gaps_out = 0, gaps_in = 0 })
-- hl.window_rule({
--     name  = "no-gaps-wtv1",
--     match = { float = false, workspace = "w[tv1]" },
--     border_size = 0,
--     rounding    = 0,
-- })
-- hl.window_rule({
--     name  = "no-gaps-f1",
--     match = { float = false, workspace = "f[1]" },
--     border_size = 0,
--     rounding    = 0,
-- })

local suppressMaximizeRule = hl.window_rule({
    name  = "suppress-maximize-events",
    match = { class = ".*" },

    suppress_event = "maximize",
})
-- suppressMaximizeRule:set_enabled(false)

hl.window_rule({
    name  = "thunderbird-comms-workspace",
    match = { class = "^(thunderbird|Thunderbird)$" },

    workspace = "name:comms",
})

hl.window_rule({
    name  = "vivaldi-browser-workspace",
    match = { class = "^vivaldi.*$" },

    workspace = "name:browser",
})

hl.window_rule({
    name  = "slack-comms-workspace",
    match = { class = "^(slack|Slack)$" },

    workspace = "name:comms",
})

hl.window_rule({
    name  = "zapzap-comms-workspace",
    match = { class = "^com\\.rtosta\\.zapzap$" },

    workspace = "name:comms",
})

hl.window_rule({
    name  = "teams-comms-workspace",
    match = { class = "^teams-for-linux$" },

    workspace = "name:comms",
})

hl.window_rule({
    name  = "fix-xwayland-drags",
    match = {
        class      = "^$",
        title      = "^$",
        xwayland   = true,
        float      = true,
        fullscreen = false,
        pin        = false,
    },

    no_focus = true,
})

-- Layer rules also return a handle.
-- local overlayLayerRule = hl.layer_rule({
--     name  = "no-anim-overlay",
--     match = { namespace = "^my-overlay$" },
--     no_anim = true,
-- })
-- overlayLayerRule:set_enabled(false)

hl.window_rule({
    name  = "move-hyprland-run",
    match = { class = "hyprland-run" },

    move  = "20 monitor_h-120",
    float = true,
})
