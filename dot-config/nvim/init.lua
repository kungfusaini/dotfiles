require("config.lazy")

vim.cmd.colorscheme("gruvbox")

vim.opt.clipboard = "unnamedplus"
vim.opt["tabstop"] = 4
vim.opt["shiftwidth"] = 4

vim.wo.relativenumber = true

vim.o.statuscolumn = "%!v:lua.require('config.statuscolumn').myStatuscolumn()";
