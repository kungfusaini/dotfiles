-- In order to have hammerspoon in your config dir, you must run the following command!
-- defaults write org.hammerspoon.Hammerspoon MJConfigFile "~/.config/hammerspoon/init.lua"

local modifiers = { "cmd", "alt" }

hs.hotkey.bind(modifiers, "t", function()
	hs.task.new("/bin/zsh", nil, { "-c", "kitty --single-instance --directory /home/ssaini" }):start()
end)

hs.hotkey.bind(modifiers, "q", function()
	hs.task.new("/bin/zsh", nil, { "-c", "kitten quick-access-terminal" }):start()
end)

-- Open Daily Note
hs.hotkey.bind(modifiers, "d", function()
	hs.task.new("/bin/zsh", nil, {
		"-c",
		"kitty --single-instance --directory /home/ssaini -e zsh -i -c 'today'"
	}):start()
end)

-- Open spotify
hs.hotkey.bind(modifiers, "m", function()
	hs.task.new("/bin/zsh", nil, {
		"-c",
		"kitty --single-instance --directory /home/ssaini -e zsh -i -c 'spotify_player'"
	}):start()
end)

-- Open compass
hs.hotkey.bind(modifiers, "c", function()
	hs.task.new("/bin/zsh", nil, {
		"-c",
		"kitty --single-instance --directory /home/ssaini -e zsh -i -c 'compass'"
	}):start()
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
