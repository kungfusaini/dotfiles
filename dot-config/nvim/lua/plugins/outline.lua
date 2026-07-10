return {
  {
    'stevearc/aerial.nvim',
    branch = 'nvim-0.11',
    opts = {},
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      "nvim-tree/nvim-web-devicons"
    },
    config = function()
      require("aerial").setup({
        layout = {
          win_opts = {
            statuscolumn = "",
            winhighlight = "Normal:Normal",
          },
        },
        keymaps = {}
      })
    end
  }
}
