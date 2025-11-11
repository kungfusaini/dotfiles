return {
  "hanschen/vim-ipython-cell",
  ft = "python",
  config = function()
    vim.api.nvim_create_autocmd("FileType", {
      pattern = "python",
      callback = function()
        vim.keymap.set('n', '<Leader><CR>', ':IPythonCellExecuteCell<CR>', {
          desc = "IPython: Execute current cell",
          buffer = true
        })
        vim.keymap.set('n', '<Leader><S-CR>', ':IPythonCellRun<CR>', {
          desc = "IPython: Execute whole file",
          buffer = true
        })
      end,
      once = true,
      group = vim.api.nvim_create_augroup("IPythonCellMaps", { clear = true }),
    })
  end,
}
