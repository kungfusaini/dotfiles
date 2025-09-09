local M = {}

-- Toggle checkbox function
M.toggle_checkbox = function()
  local line = vim.api.nvim_get_current_line()
  if line:match("%- %[.%]") then
    if line:match("%- %[ %]") then
      line = line:gsub("%- %[ %]", "- [x]")
    else
      line = line:gsub("%- %[x%]", "- [ ]")
    end
    vim.api.nvim_set_current_line(line)
  end
end

-- Insert checkbox preserving indentation
M.insert_checkbox = function()
  local line = vim.api.nvim_get_current_line()
  local indent = line:match("^(%s*)")
  vim.api.nvim_set_current_line(indent .. "- [ ] " .. line:gsub("^%s*", ""))
end

-- Fold up to level 2 (h2 and below)
M.fold_level_2 = function()
  -- Save current cursor position
  local cur_pos = vim.api.nvim_win_get_cursor(0)

  -- Close all folds first
  vim.cmd("normal! zM")

  -- Open level 1 folds (h1 headings)
  vim.cmd("normal! zr")

  -- Restore cursor position
  vim.api.nvim_win_set_cursor(0, cur_pos)
end

-- Toggle all H2 folds
M.toggle_all_h2_folds = function()
  local cur_pos = vim.api.nvim_win_get_cursor(0)

  vim.cmd("normal! gg")

  while true do
    local found = vim.fn.search("^## ", "W")
    if found == 0 then break end
    vim.cmd("normal! za")
  end

  -- Restore cursor position
  vim.api.nvim_win_set_cursor(0, cur_pos)
end

-- Open all folds
M.open_all_folds = function()
  vim.opt.foldlevel = 99
end

M.insert_time_heading = function()
  vim.api.nvim_put({ '## ' .. os.date('%H:%M:%S') }, 'l', true, true)
end

-- Configure all markdown keymaps
M.setup = function()
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "markdown",
    callback = function()
      vim.bo.textwidth = 110
      vim.wo.linebreak = true
      vim.bo.formatoptions = vim.bo.formatoptions .. 't'
      vim.bo.wrapmargin = 0

      -- Set window-specific options (window-local)
      vim.wo.wrap = true

      -- Fold all H2 headings on enter
      M.fold_level_2()

      vim.keymap.set("n", "<leader>c", M.toggle_checkbox, {
        buffer = true,
        desc = "Toggle markdown checkbox"
      })

      vim.keymap.set("n", "<leader>t", M.insert_checkbox, {
        buffer = true,
        desc = "Insert checkbox preserving indentation"
      })

      vim.keymap.set("n", "<leader>t", M.insert_time_heading, {
        buffer = true,
        desc = "Insert a h2 with the current time"
      })

      vim.keymap.set("n", "<leader>fa", M.toggle_all_h2_folds, {
        buffer = true,
        desc = "Toggle all H2 folds"
      })

      vim.keymap.set("n", "<leader>fA", M.open_all_folds, {
        buffer = true,
        desc = "Open all folds"
      })
    end
  })
end

return M
