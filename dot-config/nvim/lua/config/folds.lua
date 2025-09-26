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

M.open_all_folds = function()
  vim.opt.foldlevel = 99
end

M.setup = function()
  vim.keymap.set("n", "<leader>fA", M.open_all_folds, {
    buffer = true,
    desc = "Open all folds"
  })

  vim.keymap.set("n", "'", toggle_fold_or_insert, {
    buffer = true,
    desc = "Toggle fold or insert new line"
  })
end


return M
