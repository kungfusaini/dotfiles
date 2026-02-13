vim.g.mapleader = "<Space>"
require("config.lazy")
require("gitsigns").setup({
  numhl = true,
  signcolumn = true,
})
require("config.markdown").setup()
require("config.folds").setup()
require("config.functions").setup()


----------- Options -----------
vim.cmd.colorscheme("gruvbox")

vim.opt.clipboard = "unnamedplus"
vim.opt["tabstop"] = 4
vim.opt["shiftwidth"] = 4
vim.opt.signcolumn = "number"

vim.wo.relativenumber = true

vim.o.statuscolumn = "%!v:lua.require('config.statuscolumn').myStatuscolumn()";

vim.opt.wrap = true
vim.opt.linebreak = true
vim.opt.breakindent = true
vim.opt.showbreak = "↳ "

-- Remap j and k for using visual lines
vim.keymap.set('n', 'j', "v:count == 0 ? 'gj' : 'j'", { expr = true, silent = true })
vim.keymap.set('n', 'k', "v:count == 0 ? 'gk' : 'k'", { expr = true, silent = true })

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
    -- Only save view if the buffer has a name
    if vim.fn.haslocaldir() == 1 and vim.fn.bufname('') ~= '' then
      vim.cmd("mkview")
    end
  end,
})

vim.api.nvim_create_autocmd("BufWinEnter", {
  pattern = "*",
  callback = function()
    -- Check if the buffer has a name before loading view
    if vim.fn.bufname('') ~= '' then
      vim.cmd("silent! loadview")
    end
  end,
})
----------- Keymaps -----------

vim.keymap.set('n', '<leader>d', function()
  vim.lsp.buf.hover()
end, { desc = "Show documentation" })

vim.keymap.set('n', '<leader>e', function()
  vim.diagnostic.open_float()
end, { desc = "Show diagnostics" })

vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action, { desc = "Code Actions" })

-- Jump to next diagnostic (error/hint/suggestion)
vim.keymap.set('n', ']d', vim.diagnostic.goto_next, { desc = "Next Diagnostic" })

-- Jump to previous diagnostic
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev, { desc = "Prev Diagnostic" })

vim.keymap.set('n', 'gd', function()
  vim.lsp.buf.definition()
end, { desc = "Go to def" })

vim.keymap.set("n", "<leader>o",
  "<cmd>AerialToggle right<CR>")

vim.keymap.set('n', '<leader>gd', function()
    if next(require('diffview.lib').views) == nil then
      vim.cmd('DiffviewOpen')
    else
      vim.cmd('DiffviewClose')
    end
  end,
  { desc = "Toggle Diffview" })

vim.keymap.set('n', '<leader>lu', function()
  vim.cmd('Lazy update')
end, { desc = "Update Lazy Plugins" })

--------------------------------
