return {
  "nvim-treesitter/nvim-treesitter",
  build = function()
    if require("nvim-treesitter.install").status().pending then
      require("nvim-treesitter.install").update({ with_sync = true })()
    end
  end,
  config = function()
    require("nvim-treesitter.configs").setup({
      ensure_installed = {
        "cpp",
        "java",
        "lua",
        "python",
        "markdown",
        "markdown_inline",
      },
      sync_install = false,
      ignore_install = {},
      auto_install = true,
      highlight = {
        enable = true,
        additional_vim_regex_highlighting = { "markdown" },
      },
      folds = {
        enable = true,
      },
      modules = {},
    })
  end
}
