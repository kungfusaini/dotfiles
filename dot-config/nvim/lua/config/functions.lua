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

M.open_latest_previous_note = function()
  local journal_dir = vim.fn.expand("~/codex/Journal/")
  local today = os.date("%Y-%m-%d")
  
  local files = vim.fn.glob(journal_dir .. "*.md", false, true)
  table.sort(files, function(a, b) return a > b end)
  
  for _, file in ipairs(files) do
    local filename = vim.fn.fnamemodify(file, ":t:r")
    if filename ~= today then
      vim.cmd("edit " .. file)
      return
    end
  end
  
  vim.notify("No previous notes found", vim.log.levels.WARN)
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
  vim.keymap.set("n", "<leader>yd", M.open_latest_previous_note, { desc = "Open latest previous note" })

  vim.keymap.set('n', '<leader><CR>', M.toggle_zoom, { desc = 'Toggle zoom window' })
end

return M
