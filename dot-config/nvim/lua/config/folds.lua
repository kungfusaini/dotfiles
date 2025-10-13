local M = {}

local toggle_fold_or_insert = function()
  local line = vim.api.nvim_get_current_line()
  local fold_closed = vim.fn.foldclosed('.') ~= -1
  local has_fold = vim.fn.foldlevel('.') > 0

  if has_fold then
    vim.cmd("normal! za") -- Open fold
  end
end

vim.opt.foldenable = true
vim.opt.foldlevel = 0
vim.opt.foldmethod = "expr"
vim.opt.foldexpr = "v:lua.vim.treesitter.foldexpr()"
vim.opt.foldtext = ''
vim.opt.fillchars = { fold = ' ' }

vim.api.nvim_set_hl(0, 'Folded', {
  bg = "#552506",
  bold = true,
})

M.toggle_all_folds = function()
  local current_level = vim.opt.foldlevel:get()

  if current_level >= 99 then
    vim.opt.foldlevel = 0
    print("All folds closed (foldlevel=0)")
  else
    vim.opt.foldlevel = 99
    print("All folds opened (foldlevel=99)")
  end
end

M.setup = function()
  vim.keymap.set("n", "<leader>|", M.toggle_all_folds, {
    buffer = true,
    desc = "Toggle all folds"
  })

  vim.keymap.set("n", "\\", toggle_fold_or_insert, {
    buffer = true,
    desc = "Toggle fold or insert new line"
  })
end

return M
