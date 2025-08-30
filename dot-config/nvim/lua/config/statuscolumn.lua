local statuscolumn = {};

statuscolumn.setHl = function()
  -- Gradient from colordesiner.io
  local colors = {
    "#f96c00",
    "#d5761d",
    "#b57934",
    "#98784b",
    "#7e7463",
  };

  for i, color in ipairs(colors) do
    vim.api.nvim_set_hl(0, "Gradient_" .. i, { fg = color });
  end

  vim.api.nvim_set_hl(0, "CurrentLineNum", { fg = "#f96c00" }) -- Orange
  vim.api.nvim_set_hl(0, "LspErrorIcon", { fg = "#FC4934" })   -- Red
  vim.api.nvim_set_hl(0, "LspWarnIcon", { fg = "#ffbf00" })    -- Orange
  vim.api.nvim_set_hl(0, "LspInfoIcon", { fg = "#83A598" })    -- Blue
  vim.api.nvim_set_hl(0, "LspHintIcon", { fg = "#B8BB27" })    -- Green
  vim.api.nvim_set_hl(0, "GitSignsAdd", { fg = "#B8BB27" })    -- Green
  vim.api.nvim_set_hl(0, "GitSignsChange", { fg = "#FABE30" }) -- Yellow
  vim.api.nvim_set_hl(0, "GitSignsDelete", { fg = "#FC4934" }) -- Red
end

statuscolumn.border = function()
  -- lua tables start at 1 but relnum starts at 0, so we add 1 to it to get the highlight group
  if vim.v.relnum < 4 then
    return "%#Gradient_" .. (vim.v.relnum + 1) .. "#┃ ";
  else
    return "%#Gradient_5#┃";
  end
end

statuscolumn.git_hl = function()
  local git_status = vim.b.gitsigns_status

  if git_status then
    if git_status[1] == "a" then
      return "%#GitSignsAdd#"
    elseif git_status[1] == "M" then
      return "%#GitSignsChange#"
    elseif git_status[1] == "D" then
      return "%#GitSignsDelete#"
    end
  end
  return "" -- Just return empty string, don't reset
end

statuscolumn.number = function()
  local num = (vim.v.relnum == 0) and vim.v.lnum or vim.v.relnum
  local padding_width = 4
  local num_str = tostring(num)
  local padding = string.rep(" ", padding_width - #num_str)

  if vim.v.relnum == 0 then
    local git_hl = statuscolumn.git_hl()
    -- Apply git highlight to padding, special highlight to number
    return git_hl .. padding .. "%#CurrentLineNum#" .. num_str
  else
    return statuscolumn.git_hl() .. padding .. num_str
  end
end

statuscolumn.folds = function()
  local foldlevel = vim.fn.foldlevel(vim.v.lnum);
  local foldlevel_before = vim.fn.foldlevel((vim.v.lnum - 1) >= 1 and vim.v.lnum - 1 or 1);
  local foldlevel_after = vim.fn.foldlevel((vim.v.lnum + 1) <= vim.fn.line("$") and (vim.v.lnum + 1) or vim.fn.line("$"));

  local foldclosed = vim.fn.foldclosed(vim.v.lnum);
  -- Line has nothing to do with folds so we will skip it
  if foldlevel == 0 then
    return " ";
  end
  -- Line is a closed fold(I know second condition feels unnecessary but I will still add it)
  if foldclosed ~= -1 and foldclosed == vim.v.lnum then
    return "▶";
  end
  if foldlevel > foldlevel_before then
    return "▽"
  end

  -- The line is the last line in the fold
  if foldlevel > foldlevel_after then
    return "╰";
  end

  -- Line is in the middle of an open fold
  return "╎";
end

statuscolumn.diag = function()
  local diagnostics = vim.diagnostic.get(0, { lnum = vim.v.lnum - 1 })
  local highest_severity = 5 -- Initialize with a value higher than any severity level
  local symbol = " "

  if #diagnostics > 0 then
    for _, diagnostic in ipairs(diagnostics) do
      if diagnostic.severity < highest_severity then
        highest_severity = diagnostic.severity --[[@as integer]]
      end
    end

    -- Then, use the highest severity level to determine the symbol to display
    if highest_severity <= vim.diagnostic.severity.ERROR then
      symbol = "%#LspErrorIcon#%*"
    elseif highest_severity <= vim.diagnostic.severity.WARN then
      symbol = "%#LspWarnIcon#!%*"
    elseif highest_severity <= vim.diagnostic.severity.INFO then
      symbol = "%#LspInfoIcon#i%*"
    elseif highest_severity <= vim.diagnostic.severity.HINT then
      symbol = "%#LspHintIcon#%*"
    end
  end

  return symbol;
end

statuscolumn.myStatuscolumn = function()
  statuscolumn.setHl();

  local text = table.concat({
    statuscolumn.diag(),
    statuscolumn.number(),
    statuscolumn.folds(),
    statuscolumn.border(),
  })
  return text;
end

return statuscolumn;
