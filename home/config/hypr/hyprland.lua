-- Main Hyprland Lua config
-- Split config files live in ~/.config/hypr/conf/

local config_dir = os.getenv("HOME") .. "/.config/hypr/conf"

local hypr_plugin_dir = os.getenv("HYPR_PLUGIN_DIR")
if hypr_plugin_dir then
    hl.plugin.load(hypr_plugin_dir .. "/lib/libhyprgrass.so")
end

local function source(file)
    dofile(config_dir .. "/" .. file)
end

source("monitors.lua")
source("autostart.lua")
source("env.lua")
source("permissions.lua")
source("appearance.lua")
source("layouts.lua")
source("misc.lua")
source("input.lua")
source("keybindings.lua")
source("rules.lua")
