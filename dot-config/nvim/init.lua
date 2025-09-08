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

-- Markdown Functions

vim.api.nvim_create_autocmd("FileType", {
  pattern = "markdown",
  callback = function()
    vim.keymap.set("n", "<leader>c", ":lua require('toggle-checkbox').toggle()<CR>", {
      buffer = true,
      desc = "Toggle markdown checkbox"
    })
  end
})

vim.api.nvim_create_autocmd("FileType", {
  pattern = "markdown",
  callback = function()
    vim.keymap.set("n", "<leader>t", function()
      local line = vim.api.nvim_get_current_line()
      local indent = line:match("^(%s*)")
      vim.api.nvim_set_current_line(indent .. "- [ ] " .. line:gsub("^%s*", ""))
    end, { buffer = true, desc = "Insert checkbox preserving indentation" })
  end
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
