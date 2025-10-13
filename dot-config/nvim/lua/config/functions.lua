local M = {}
local zoom_state = {}

M.open_todays_note = function()
  local date = os.date("%Y-%m-%d")
  local file = vim.fn.expand("~/codex/Journal/") .. date .. ".md"

  if vim.fn.filereadable(file) == 0 then
    local lines = { "# " .. date, "", "" }
    vim.fn.writefile(lines, file)
  end

  vim.cmd("edit " .. file)
end

M.toggle_zoom = function()
  local current_win = vim.api.nvim_get_current_win()

  if zoom_state[current_win] then
    -- Restore
    vim.cmd('wincmd =')
    zoom_state[current_win] = false
  else
    -- Zoom
    vim.cmd('wincmd |')
    vim.cmd('wincmd _')
    zoom_state[current_win] = true
  end
end

M.setup = function()
  vim.api.nvim_create_user_command("Today", M.open_todays_note, {})
  vim.keymap.set("n", "<leader>td", M.open_todays_note, { desc = "Open today's note" })

  vim.keymap.set('n', '<leader><CR>', M.toggle_zoom, { desc = 'Toggle zoom window' })
end

return M
