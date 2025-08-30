return {

  {
    'saghen/blink.cmp',
    dependencies = { 'rafamadriz/friendly-snippets' },

    version = '1.*',

    opts = {
      keymap = {
        preset = 'none',

        ['<C-space>'] = { 'select_and_accept' },
        ['<C-e>'] = { 'hide' },
        ['<C-p>'] = { 'select_prev', 'fallback' },
        ['<C-n>'] = { 'select_next', 'fallback' },
        ['<C-b>'] = { 'scroll_documentation_up', 'fallback' },
        ['<C-f>'] = { 'scroll_documentation_down', 'fallback' }

      },

      appearance = {
        nerd_font_variant = 'mono'
      },

      completion = {
        accept = { auto_brackets = { enabled = false }, },
        documentation = { auto_show = true, auto_show_delay_ms = 500, },
      },
      sources = {
        default = { 'lsp', 'path', 'snippets', 'buffer' },
      },

      signature = {
        enabled = true,
        window = {
          show_documentation = false,
        }
      },
    },
  }
}
