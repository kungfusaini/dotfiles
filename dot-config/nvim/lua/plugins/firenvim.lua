return {
  'glacambre/firenvim',
  build = ":call firenvim#install(0)",
  config = function()
    vim.g.firenvim_config = {
      localSettings = {
        ['.*'] = {
          takeover = 'never',
          content = 'text',
        },
      },
    }

    if vim.g.started_by_firenvim then
      local max_height = 20
      local id = vim.api.nvim_create_augroup("ExpandLinesOnTextChanged", { clear = true })

      vim.api.nvim_create_autocmd({ "TextChanged", "TextChangedI" }, {
        group = id,
        callback = function()
          local height = vim.api.nvim_win_text_height(0, {}).all

          if height > vim.o.lines then
            if height < max_height then
              vim.o.lines = height
            else
              vim.o.lines = max_height
            end
          end
        end
      })
    end
  end
}
