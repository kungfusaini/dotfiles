return {
  'kungfusaini/spellcheck-mode.nvim',
  config = function()
    require('spellcheck-mode').setup({
      keys = {
        toggle = '<leader>sp',
        next_error = 'n',
        prev_error = 'p',
        suggestions = '<Space>',
        add_to_dict = 'D'
      },
      options = {
        default_lang = 'en_gb',
        max_suggestions = 10,
        auto_enable_filetypes = {},
        spell_options = 'camel'
      }
    })
  end
}
