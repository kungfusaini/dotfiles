local statuscolumn = {};


statuscolumn.setHl = function ()
	-- Gradient from colordesiner.io
  local colors = { "#caa6f7", "#c1a6f1", "#b9a5ea", "#b1a4e4", "#aba3dc", "#a5a2d4", "#9fa0cc", "#9b9ec4", "#979cbc", "#949ab3" };

  for i, color in ipairs(colors) do
    vim.api.nvim_set_hl(0, "Gradient_" .. i, { fg = color });
  end
end

statuscolumn.border = function ()
-- lua tables start at 1 but relnum starts at 0, so we add 1 to it to get the highlight group
  if vim.v.relnum < 9 then
    return "%#Gradient_" .. (vim.v.relnum + 1) .. "#┃";
  else
    return "%#Gradient_10#┃";
  end
end



statuscolumn.number = function()
  -- If relative number is 0 (current line), show absolute line number instead
  local num = (vim.v.relnum == 0) and vim.v.lnum or vim.v.relnum
  return tostring(num)
end


statuscolumn.folds = function ()
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

statuscolumn.myStatuscolumn = function ()
  local text = "";

  statuscolumn.setHl();

  text = table.concat({
	  statuscolumn.folds(),
	  statuscolumn.number({ mode = "hybrid"}),
	  statuscolumn.border(),
	})
  return text;
end

return statuscolumn;
