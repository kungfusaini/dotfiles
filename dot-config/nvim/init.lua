require("config.lazy")

require("gitsigns").setup({
	numhl = false,
	signcolumn = false,
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

vim.keymap.set('n', 'K', function()
  local cursor_pos = vim.api.nvim_win_get_cursor(0)
  local current_line = cursor_pos[1] - 1  -- Convert to 0-indexed line number
  local diagnostics = vim.diagnostic.get(0, { lnum = current_line })

  if #diagnostics > 0 then
    vim.diagnostic.open_float()
  else
    vim.lsp.buf.hover()
  end
end, { desc = "Show documentation or diagnostics" })
