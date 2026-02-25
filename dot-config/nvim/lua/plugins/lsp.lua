return {
  {
    "neovim/nvim-lspconfig",

    dependencies = {
      {

        "folke/lazydev.nvim",
        ft = "lua", -- only load on lua files
        opts = {
          library = {
            -- See the configuration section for more details
            -- Load luvit types when the `vim.uv` word is found
            { path = "${3rd}/luv/library", words = { "vim%.uv" } },
          },
        },
      },
    },
    config = function()
      local servers = { "basedpyright", "biome", "clangd", "lua_ls", "marksman", "nil_ls", "harper_ls" }

      -- Harper LSP server configuration
      vim.lsp.handlers["textDocument/publishDiagnostics"] = vim.lsp.with(
        vim.lsp.diagnostic.on_publish_diagnostics,
        {
          severity_sort = true,
          update_in_insert = false,
        }
      )

      -- Harper specific settings
      vim.lsp.config["harper_ls"] = {
        settings = {
          ["harper-ls"] = {
            userDictPath = vim.fn.stdpath("config") .. "/spell/en.utf-8.add",
            dialect = "British",
            codeActions = {
              ForceStable = true
            },
            diagnosticSeverity = "warning"
            -- colour
          }
        }
      }

      for _, name in ipairs(servers) do
        -- Loads server config from lsp/<server>.lua if present
        vim.lsp.enable(name)
      end

-- Harper LSP diagnostics toggle (silent)
local function toggle_harper_diagnostics()
  local clients = vim.lsp.get_clients({ name = "harper_ls" })
  
  if #clients == 0 then
    return -- Silent no-op if Harper not running
  end
  
  for _, client in ipairs(clients) do
    local namespace = client.name .. "-diagnostics"
    local enabled = not vim.diagnostic.is_enabled({ ns_id = namespace })
    vim.diagnostic.enable(enabled, { ns_id = namespace })
  end
end

vim.api.nvim_create_autocmd('LspAttach', {
  group = vim.api.nvim_create_augroup('my.lsp', {}),
  callback = function(args)
    local client = assert(vim.lsp.get_client_by_id(args.data.client_id))
    if not client then return end
    
    -- Autoformat on save
    if client:supports_method('textDocument/formatting') then
      vim.api.nvim_create_autocmd('BufWritePre', {
        group = vim.api.nvim_create_augroup('my.lsp', { clear = false }),
        buffer = args.buf,
        callback = function()
          vim.lsp.buf.format({ bufnr = args.buf, id = client.id, timeout_ms = 1000 })
        end,
      })
    end
    
    -- Harper specific initialization (if needed)
    if client.name == "harper_ls" then
      -- Optional: Set initial diagnostic state if desired
    end
  end,
})

-- Harper LSP diagnostics toggle keymap
vim.keymap.set('n', '<leader>sp', toggle_harper_diagnostics, { desc = "Toggle Harper diagnostics (silent)" })
      end
}
}
