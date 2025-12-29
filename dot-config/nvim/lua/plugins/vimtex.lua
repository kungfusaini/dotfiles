return {
  "lervag/vimtex",
  lazy = false,
  init = function()
    vim.g.vimtex_view_method = "sioyek"
  end,

  config = function()
    -- Doesn't work :(
    vim.api.nvim_create_autocmd('User', {
      pattern = 'VimtexEventViewReverse',
      command = "call b:vimtex.viewer.xdo_focus_vim()"
    })
  end,
}
