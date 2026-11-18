-- Execute only generated configuration against an inert recording API.
-- No compositor, environment import, subprocess, input or application writes.
local calls = {}
local function descriptor(path)
    return setmetatable({}, {
        __index = function(_, name) return descriptor(path .. "." .. name) end,
        __call = function(_, ...) return {operation=path, args={...}} end,
    })
end
hl = setmetatable({dsp=descriptor("dsp")}, {
    __index = function(_, name)
        return function(...)
            local args = {...}
            if name == "on" then
                assert(args[1] == "hyprland.start", "Unexpected event hook")
                args[2]()
            else
                calls[#calls+1] = {name=name, args=args}
            end
        end
    end,
})
local function encode(value)
    local kind = type(value)
    if kind == "nil" then return "null" end
    if kind == "boolean" or kind == "number" then return tostring(value) end
    if kind == "string" then
        return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
            if c == '"' or c == '\\' then return '\\' .. c end
            return string.format('\\u%04x', string.byte(c))
        end) .. '"'
    end
    assert(kind == "table", "Unexpected value: " .. kind)
    local list = {}
    if #value > 0 then
        for i=1,#value do list[#list+1] = encode(value[i]) end
        return '[' .. table.concat(list, ',') .. ']'
    end
    for key,item in pairs(value) do list[#list+1] = encode(key) .. ':' .. encode(item) end
    table.sort(list)
    return '{' .. table.concat(list, ',') .. '}'
end
dofile(assert(arg[1], "configuration path required"))
io.write(encode(calls), '\n')
