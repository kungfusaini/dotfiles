---------------------
---- KEYBINDINGS ----
---------------------

local terminal      = "kitty"
local fileManager   = "dolphin"
local menu          = "wofi --show drun"
local commsWorkspace   = "name:comms"
local browserClient    = "vivaldi"
local browserWorkspace = "name:browser"
local mainMod          = "SUPER"

hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + Return", hl.dsp.exec_cmd(terminal))
local closeWindowBind = hl.bind(mainMod .. " + W", hl.dsp.window.close())
-- closeWindowBind:set_enabled(false)

-- Browser workspace: Super+B jumps to browser and starts Vivaldi if needed.
hl.bind(mainMod .. " + B", hl.dsp.focus({ workspace = browserWorkspace }))
hl.bind(mainMod .. " + B", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/hypr-browser-workspace-launch"))
hl.bind(mainMod .. " + SHIFT + B", hl.dsp.window.move({ workspace = browserWorkspace }))

-- Comms workspace: Super+C jumps to comms and starts/collects comms apps if needed.
hl.bind(mainMod .. " + C", hl.dsp.focus({ workspace = commsWorkspace }))
hl.bind(mainMod .. " + C", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/hypr-comms-workspace-launch"))
hl.bind(mainMod .. " + SHIFT + C", hl.dsp.window.move({ workspace = commsWorkspace }))

-- Group/tab controls. In the comms workspace this cycles Mail/Slack/WhatsApp/Teams.
hl.bind(mainMod .. " + G", hl.dsp.group.toggle())
hl.bind(mainMod .. " + TAB", hl.dsp.group.next())
hl.bind(mainMod .. " + SHIFT + TAB", hl.dsp.group.prev())
hl.bind(mainMod .. " + bracketright", hl.dsp.group.next())
hl.bind(mainMod .. " + bracketleft", hl.dsp.group.prev())
hl.bind(mainMod .. " + SHIFT + G", hl.dsp.group.lock_active({ action = "toggle" }))

hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(fileManager))
-- Toggle true fullscreen for the focused window (not split/tiled or floating window mode).
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen())
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(menu))

-- Voxtype dictation push-to-talk; keyd makes the Copilot key plain F23.
hl.bind("F23", hl.dsp.exec_cmd("voxtype record start"))
hl.bind("F23", hl.dsp.exec_cmd("voxtype record stop"), { release = true })

-- Open Pi agent in a terminal with Super + Copilot/F23.
hl.bind(mainMod .. " + F23", hl.dsp.exec_cmd(terminal .. " -e pi"))

hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())
hl.bind(mainMod .. " + J", hl.dsp.layout("togglesplit"))

-- Move focus with mainMod + arrow keys
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

-- Switch workspaces with mainMod + [0-9]
-- Move active window to a workspace with mainMod + SHIFT + [0-9]
for i = 1, 10 do
    local key = i % 10 -- 10 maps to key 0
    hl.bind(mainMod .. " + " .. key,         hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

-- Special workspace / scratchpad
hl.bind(mainMod .. " + S",         hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))

-- Scroll through existing workspaces with mainMod + scroll
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Move/resize windows with mainMod + LMB/RMB and dragging
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Laptop multimedia keys for volume and LCD brightness
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })
hl.bind("XF86MonBrightnessUp",  hl.dsp.exec_cmd("brightnessctl set 10%+"),                        { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown",hl.dsp.exec_cmd("brightnessctl set 10%-"),                        { locked = true, repeating = true })

-- Requires playerctl
hl.bind("XF86AudioNext",  hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay",  hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev",  hl.dsp.exec_cmd("playerctl previous"),   { locked = true })
