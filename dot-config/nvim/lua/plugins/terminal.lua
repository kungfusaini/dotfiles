return {
  {
    "numToStr/FTerm.nvim",
    config = function()
      vim.keymap.set('n', '<leader>/', '<CMD>lua require("FTerm").toggle()<CR>')
      vim.keymap.set('t', '<leader>/', '<C-\\><C-n><CMD>lua require("FTerm").toggle()<CR>')
    end
  },
}
