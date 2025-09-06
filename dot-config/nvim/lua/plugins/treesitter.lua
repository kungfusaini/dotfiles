return {
  "nvim-treesitter/nvim-treesitter",
  build = function()
    require("nvim-treesitter.install").update({ with_sync = true })()
  end,
  config = function()
    require("nvim-treesitter.configs").setup({
      ensure_installed = { "markdown", "markdown_inline" },

      sync_install = false,

      ignore_install = {},

      auto_install = true,

      highlight = {
        enable = true,
        additional_vim_regex_highlighting = { "markdown" },
      },

      modules = {},
    })
  end
}
