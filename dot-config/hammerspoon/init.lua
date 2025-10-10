-- In order to have hammerspoon in your config dir, you must run the following command!
-- defaults write org.hammerspoon.Hammerspoon MJConfigFile "~/.config/hammerspoon/init.lua"

local modifiers = { "cmd", "alt" }

hs.hotkey.bind(modifiers, "t", function()
	hs.task.new("/bin/zsh", nil, { "-c", "kitty --single-instance --directory /home/ssaini" }):start()
end)

hs.hotkey.bind(modifiers, "q", function()
	hs.task.new("/bin/zsh", nil, { "-c", "kitten quick-access-terminal" }):start()
end)

-- Brave: open a new browser window
hs.hotkey.bind(modifiers, "b", function()
	hs.osascript.applescript([[
        tell application "Brave Browser"
            make new window
            activate
        end tell
    ]])
end)
