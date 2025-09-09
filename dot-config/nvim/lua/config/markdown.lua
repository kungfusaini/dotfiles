local M = {}

vim.api.nvim_set_hl(0, 'Folded', {
  bg = "#552506",
  bold = true,
})

vim.opt.foldenable = true
vim.opt.foldmethod = "expr"
vim.opt.foldexpr = "v:lua.vim.treesitter.foldexpr()"
vim.opt.foldlevel = 99
vim.opt.foldtext = ''
vim.opt.fillchars = { fold = ' ' }

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

-- Enter key to toggle fold under cursor
M.toggle_fold_or_insert = function()
  local line = vim.api.nvim_get_current_line()
  -- Check if we're on a fold marker
  if line:match("^#+ .+") then
    vim.cmd("normal! za")
  else
    vim.cmd("normal! a")
  end
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

-- Configure all markdown keymaps
M.setup = function()
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "markdown",
    callback = function()
      vim.keymap.set("n", "<leader>c", M.toggle_checkbox, {
        buffer = true,
        desc = "Toggle markdown checkbox"
      })

      vim.keymap.set("n", "<leader>t", M.insert_checkbox, {
        buffer = true,
        desc = "Insert checkbox preserving indentation"
      })

      vim.keymap.set("n", "<CR>", M.toggle_fold_or_insert, {
        buffer = true,
        desc = "Toggle fold or insert new line"
      })

      vim.keymap.set("n", "<leader>fa", M.fold_level_2, {
        buffer = true,
        desc = "Fold up to level 2 (h2 and below)"
      })
    end
  })
end

return M
