return
{
  'MeanderingProgrammer/render-markdown.nvim',
  dependencies = { 'nvim-treesitter/nvim-treesitter' },
  opts = {},
  config = function()
    vim.api.nvim_set_hl(0, "RenderMarkdownH1Bg", { bg = "#3c3836", fg = "#fb4934" }) -- Red text on grey bg
    vim.api.nvim_set_hl(0, "RenderMarkdownH2Bg", { bg = "#3c3836", fg = "#b8bb26" }) -- Green text on grey bg
    vim.api.nvim_set_hl(0, "RenderMarkdownH3Bg", { bg = "#3c3836", fg = "#fabd2f" }) -- Yellow text on grey bg
    vim.api.nvim_set_hl(0, "RenderMarkdownH4Bg", { bg = "#3c3836", fg = "#83a598" }) -- Blue text on grey bg
    vim.api.nvim_set_hl(0, "RenderMarkdownH5Bg", { bg = "#3c3836", fg = "#d3869b" }) -- Purple text on grey bg
    vim.api.nvim_set_hl(0, "RenderMarkdownH6Bg", { bg = "#3c3836", fg = "#8ec07c" }) -- Aqua text on grey bg
  end
}
