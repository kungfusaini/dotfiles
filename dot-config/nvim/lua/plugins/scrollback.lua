return {
  'mikesmithgh/kitty-scrollback.nvim',
  enabled = true,
  lazy = true,
  cmd = { 'KittyScrollbackGenerateKittens', 'KittyScrollbackCheckHealth', 'KittyScrollbackGenerateCommandLineEditing' },
  event = { 'User KittyScrollbackLaunch' },
  version = '*', -- latest stable version, may have breaking changes if major version changed
  config = function()
    require('kitty-scrollback').setup()
    -- Function to set up the necessary autocmd for ksb buffers
    local function setup_ksb_redraw()
      -- Check if the current buffer is a kitty-scrollback buffer
      -- (It sets a custom variable 'kitty_scrollback_nvim' in the buffer's scope)
      if vim.b.kitty_scrollback_nvim then
        -- Create an autocmd group to manage our specific redraw command
        local augroup = vim.api.nvim_create_augroup("KSBStatusColumnRedraw", { clear = true })

        -- Set up an autocmd to run on every CursorMoved event in the current buffer
        vim.api.nvim_create_autocmd("CursorMoved", {
          group = augroup,
          buffer = vim.api.nvim_get_current_buf(),
          callback = function()
            -- Force a redraw of the status column (sc) and sign column (ss)
            vim.cmd("redrawstatus!")
          end,
        })
      end
    end

    -- Hook this function to an event that fires right after the KSB buffer is opened.
    -- The BufReadPost event is a reliable choice for the KSB kitten.
    vim.api.nvim_create_autocmd("BufReadPost", {
      pattern = "kitty-scrollback.nvim*", -- Match the KSB buffer name pattern
      callback = setup_ksb_redraw,
    })
  end,
}
