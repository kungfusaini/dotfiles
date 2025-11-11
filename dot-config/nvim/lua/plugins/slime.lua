return {
  "jpalardy/vim-slime",
  init = function()
    vim.g.slime_no_mappings = 1
    -- Remapping the <Plug> using the Lua API
    vim.keymap.set('x', '<leader><CR>', '<Plug>SlimeRegionSend', { desc = "Slime: Send Selection" })

    vim.g.slime_target = "tmux"
    vim.g.slime_default_config = {
      socket_name = "default",
      target_pane = ":.1",
    }

    vim.g.slime_callbacks = {
      python = {
        before = {
          function()
            return "%cpaste\n"
          end,
        },
        after = {
          function()
            return "--\n"
          end,
        },
      },
    }
  end
}
