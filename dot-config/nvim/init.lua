require("config.lazy")

vim.cmd.colorscheme("gruvbox")

vim.opt.clipboard = "unnamedplus"
vim.opt["tabstop"] = 4
vim.opt["shiftwidth"] = 4
vim.opt.foldlevel = 99

vim.wo.relativenumber = true
vim.opt.foldenable = true
vim.opt.foldmethod = "syntax"

vim.o.statuscolumn = "%!v:lua.require('config.statuscolumn').myStatuscolumn()";

vim.api.nvim_create_autocmd("BufWinLeave", {
  pattern = "*",
  callback = function()
      vim.cmd("mkview")
  end,
})

vim.api.nvim_create_autocmd("BufWinEnter", {
  pattern = "*",
  callback = function()
    vim.cmd("silent loadview")
  end,
})
