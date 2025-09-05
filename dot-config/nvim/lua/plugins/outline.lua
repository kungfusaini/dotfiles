return {
  {
    'stevearc/aerial.nvim',
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
