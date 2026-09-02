local M = {}

local state = {
  win = nil,
  buf = nil,
  actions = {},
  index = 1,
}

local function close_menu()
  if state.win and vim.api.nvim_win_is_valid(state.win) then
    vim.api.nvim_win_close(state.win, true)
  end

  if state.buf and vim.api.nvim_buf_is_valid(state.buf) then
    pcall(vim.api.nvim_buf_delete, state.buf, { force = true })
  end

  state.win = nil
  state.buf = nil
  state.actions = {}
  state.index = 1
end

local function apply_action(action)
  close_menu()

  local client = action.client_id and vim.lsp.get_client_by_id(action.client_id) or nil
  local encoding = client and client.offset_encoding or "utf-16"

  if action.edit then
    vim.lsp.util.apply_workspace_edit(action.edit, encoding)
  end

  if action.command then
    local ok, err = pcall(function()
      if client then
        client:request("workspace/executeCommand", action.command, function(request_err)
          if request_err then
            vim.notify(request_err.message or tostring(request_err), vim.log.levels.ERROR)
          end
        end)
      end
    end)

    if not ok then
      vim.notify(err, vim.log.levels.ERROR)
    end
  end
end

local function render_menu()
  if not state.buf or not vim.api.nvim_buf_is_valid(state.buf) then
    return
  end

  local lines = {}
  for i, action in ipairs(state.actions) do
    local prefix = i == state.index and "> " or "  "
    local title = action.title or "Unnamed action"
    if action.disabled then
      title = title .. " (disabled)"
    end
    lines[#lines + 1] = prefix .. "CA: " .. title
  end

  vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, lines)
  vim.api.nvim_win_set_cursor(state.win, { state.index, 0 })
end

local function move(delta)
  if #state.actions == 0 then
    return
  end

  state.index = ((state.index - 1 + delta) % #state.actions) + 1
  render_menu()
end

local function choose_current()
  local action = state.actions[state.index]
  if action then
    apply_action(action)
  end
end

local function open_menu(actions)
  close_menu()

  if #actions == 0 then
    vim.notify("No code actions available", vim.log.levels.INFO)
    return
  end

  state.actions = actions
  state.index = 1

  local width = 0
  for _, action in ipairs(actions) do
    local label = "CA: " .. (action.title or "Unnamed action")
    width = math.max(width, vim.fn.strdisplaywidth(label))
  end

  width = math.min(math.max(width + 2, 24), math.floor(vim.o.columns * 0.45))
  local height = math.min(#actions, 10)

  local cursor_col = vim.fn.wincol()
  local win_width = vim.api.nvim_win_get_width(0)
  local open_left = (win_width - cursor_col) < (width + 4) and cursor_col > width + 4

  state.buf = vim.api.nvim_create_buf(false, true)
  vim.bo[state.buf].buftype = "nofile"
  vim.bo[state.buf].bufhidden = "wipe"
  vim.bo[state.buf].swapfile = false
  vim.bo[state.buf].modifiable = true

  vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, {})

  state.win = vim.api.nvim_open_win(state.buf, true, {
    relative = "cursor",
    row = 0,
    col = open_left and (-width - 2) or 1,
    anchor = open_left and "NE" or "NW",
    width = width,
    height = height,
    style = "minimal",
    border = "rounded",
  })

  vim.wo[state.win].wrap = false
  vim.wo[state.win].cursorline = true
  vim.wo[state.win].signcolumn = "no"
  vim.wo[state.win].number = false
  vim.wo[state.win].relativenumber = false
  vim.wo[state.win].foldcolumn = "0"
  vim.wo[state.win].winhl = "Normal:NormalFloat,FloatBorder:FloatBorder,CursorLine:Visual"

  vim.keymap.set("n", "<C-n>", function()
    move(1)
  end, { buffer = state.buf, nowait = true, silent = true })
  vim.keymap.set("n", "<C-p>", function()
    move(-1)
  end, { buffer = state.buf, nowait = true, silent = true })
  vim.keymap.set("n", "<CR>", choose_current, { buffer = state.buf, nowait = true, silent = true })
  vim.keymap.set("n", "<Esc>", close_menu, { buffer = state.buf, nowait = true, silent = true })
  vim.keymap.set("n", "q", close_menu, { buffer = state.buf, nowait = true, silent = true })

  render_menu()
end

local function position_in_range(row, col, diagnostic)
  local start_row = diagnostic.lnum + 1
  local end_row = (diagnostic.end_lnum or diagnostic.lnum) + 1
  local start_col = diagnostic.col
  local end_col = diagnostic.end_col

  if row < start_row or row > end_row then
    return false
  end

  if row == start_row and col < start_col then
    return false
  end

  if row == end_row and col > end_col then
    return false
  end

  return true
end

local function to_lsp_diagnostic(diagnostic)
  if diagnostic.user_data and diagnostic.user_data.lsp then
    return diagnostic.user_data.lsp
  end

  return {
    range = {
      start = {
        line = diagnostic.lnum,
        character = diagnostic.col,
      },
      ["end"] = {
        line = diagnostic.end_lnum or diagnostic.lnum,
        character = diagnostic.end_col,
      },
    },
    message = diagnostic.message,
    severity = diagnostic.severity,
    source = diagnostic.source,
  }
end

local function get_request_range(bufnr, encoding)
  local mode = vim.api.nvim_get_mode().mode

  if mode:match("^[vV\22]") then
    local start_pos = vim.api.nvim_buf_get_mark(bufnr, "<")
    local end_pos = vim.api.nvim_buf_get_mark(bufnr, ">")
    return vim.lsp.util.make_given_range_params(start_pos, end_pos, bufnr, encoding)
  end

  local cursor = vim.api.nvim_win_get_cursor(0)
  local row = cursor[1]
  local col = cursor[2]
  local diagnostics = vim.diagnostic.get(bufnr, { lnum = row - 1 })
  local diagnostic = nil

  for _, item in ipairs(diagnostics) do
    if position_in_range(row, col, item) then
      diagnostic = item
      break
    end
  end

  diagnostic = diagnostic or diagnostics[1]

  if diagnostic then
    return vim.lsp.util.make_given_range_params(
      { diagnostic.lnum + 1, diagnostic.col },
      { (diagnostic.end_lnum or diagnostic.lnum) + 1, diagnostic.end_col },
      bufnr,
      encoding
    )
  end

  return vim.lsp.util.make_range_params(0, encoding)
end

function M.code_actions()
  local bufnr = vim.api.nvim_get_current_buf()
  local clients = vim.lsp.get_clients({ bufnr = bufnr, method = "textDocument/codeAction" })
  local encoding = (clients[1] and clients[1].offset_encoding) or "utf-16"
  local params = get_request_range(bufnr, encoding)

  params.context = {
    diagnostics = vim.tbl_map(to_lsp_diagnostic, vim.diagnostic.get(bufnr)),
  }

  vim.lsp.buf_request_all(bufnr, "textDocument/codeAction", params, function(results)
    local actions = {}

    for client_id, result in pairs(results) do
      local client = vim.lsp.get_client_by_id(client_id)
      local encoding = client and client.offset_encoding or "utf-16"

      local items = (result and result.result) or {}
      for _, action in ipairs(items) do
        action.client_id = client_id
        action.offset_encoding = encoding
        if not action.disabled then
          actions[#actions + 1] = action
        end
      end
    end

    vim.schedule(function()
      open_menu(actions)
    end)
  end)
end

function M.setup()
  vim.keymap.set({ "n", "x" }, "<leader>ca", M.code_actions, { desc = "Code Actions" })
end

return M
