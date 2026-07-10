return {
  "nvim-treesitter/nvim-treesitter",
  branch = "main",  -- Use main branch for Neovim 0.12 compatibility
  build = ":TSUpdate",
  lazy = false,
  config = function()
    -- New main branch setup for Neovim 0.12
    require("nvim-treesitter").setup({
      install_dir = vim.fn.stdpath("data") .. "/site",
    })
    
    -- Enable treesitter highlighting for markdown files
    vim.api.nvim_create_autocmd("FileType", {
      pattern = { "markdown", "markdown_inline" },
      callback = function()
        vim.treesitter.start()
      end,
    })
  end
}
