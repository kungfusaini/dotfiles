vim.g.mapleader = "<Space>"

require("config.lazy")

require("gitsigns").setup({
  numhl = true,
  signcolumn = true,
})

vim.cmd.colorscheme("gruvbox")

vim.opt.clipboard = "unnamedplus"
vim.opt["tabstop"] = 4
vim.opt["shiftwidth"] = 4
vim.opt.foldlevel = 99
vim.opt.signcolumn = "number"

vim.wo.relativenumber = true
vim.opt.foldenable = true
vim.opt.foldmethod = "syntax"

vim.o.statuscolumn = "%!v:lua.require('config.statuscolumn').myStatuscolumn()";

vim.api.nvim_create_autocmd("BufWinLeave", {
  pattern = "*",
  callback = function()
    if vim.fn.haslocaldir() == 1 then
      vim.cmd("mkview")
    end
  end,
})

vim.api.nvim_create_autocmd("BufWinEnter", {
  pattern = "*",
  callback = function()
    vim.cmd("silent! loadview")
  end,
})

vim.keymap.set('n', '<leader>d', function()
  vim.lsp.buf.hover()
end, { desc = "Show documentation" })

vim.keymap.set('n', '<leader>e', function()
  vim.diagnostic.open_float()
end, { desc = "Show diagnostics" })
