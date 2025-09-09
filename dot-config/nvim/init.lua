vim.g.mapleader = "<Space>"
require("config.lazy")
require("gitsigns").setup({
  numhl = true,
  signcolumn = true,
})
vim.cmd.colorscheme("gruvbox")

require("config.markdown").setup()
require("config.folds").setup()

vim.opt.clipboard = "unnamedplus"
vim.opt["tabstop"] = 4
vim.opt["shiftwidth"] = 4
vim.opt.signcolumn = "number"

vim.wo.relativenumber = true


vim.o.statuscolumn = "%!v:lua.require('config.statuscolumn').myStatuscolumn()";

----------- Functions -----------
vim.api.nvim_create_autocmd("FileType", {
  pattern = "help",
  callback = function()
    vim.wo.statuscolumn = " "
  end,
})

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

----------- Keymaps -----------

vim.keymap.set('n', '<leader>d', function()
  vim.lsp.buf.hover()
end, { desc = "Show documentation" })

vim.keymap.set('n', '<leader>e', function()
  vim.diagnostic.open_float()
end, { desc = "Show diagnostics" })

vim.keymap.set('n', 'gd', function()
  vim.lsp.buf.definition()
end, { desc = "Go to def" })

vim.keymap.set("n", "<leader>o", "<cmd>AerialToggle right<CR>")

vim.keymap.set('n', '<leader>sp', require('spellcheck-mode').toggle_spellcheck, { desc = 'Toggle spellcheck' })
