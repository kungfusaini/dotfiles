local M = {}

-- Helper function to convert string to kebab-case (filename format)
local function to_kebab_case(str)
  local result = str:lower()
  result = result:gsub("%s+", "-")
  result = result:gsub("[^%w%-]", "")
  result = result:gsub("-+", "-")
  result = result:gsub("^%-", "")
  result = result:gsub("%-$", "")
  return result
end

-- Helper function to convert string to title case
local function to_title_case(str)
  local result = str:gsub("%-", " ")
  result = result:gsub("(%w+)", function(word)
    return word:sub(1,1):upper() .. word:sub(2):lower()
  end)
  return result
end

-- Extract wiki-link from cursor position
local function extract_wiki_link()
  local line = vim.api.nvim_get_current_line()
  local col = vim.api.nvim_win_get_cursor(0)[2] + 1
  
  -- Find wiki-link at cursor position
  local start_pos, end_pos, note_name = line:find("%[%[([^%]]+)%]%]", col)
  if not start_pos or col < start_pos or col > end_pos then
    -- Try to find any wiki-link on the line
    start_pos, end_pos, note_name = line:find("%[%[([^%]]+)%]%]")
    if not start_pos then
      return nil
    end
  end
  
  return note_name
end

-- Create note from wiki-link under cursor
M.create_note_interactive = function()
  local note_name = extract_wiki_link()
  if not note_name then
    vim.notify("No wiki-link found under cursor", vim.log.levels.WARN)
    return
  end
  
  -- Convert note name to filename format (kebab-case)
  local filename = to_kebab_case(note_name)
  
  -- Convert note name to title format (Title Case)
  local title = to_title_case(note_name)
  
  -- Get current file's directory
  local current_dir = vim.fn.expand('%:p:h')
  if current_dir == "" then
    current_dir = vim.fn.getcwd() -- fallback to current working dir
  end
  
  -- Get filename from user with pre-populated value
  local user_filename = vim.fn.input("Create note: ", filename)
  if user_filename == "" then
    return -- User cancelled
  end
  
  -- Ensure .md extension
  if not user_filename:match("%.md$") then
    user_filename = user_filename .. ".md"
  end
  
  -- Construct full path
  local full_path = current_dir .. "/" .. user_filename
  
  -- Check if file already exists
  if vim.fn.filereadable(full_path) == 1 then
    vim.notify("File already exists: " .. full_path, vim.log.levels.WARN)
    return
  end
  
  -- Create the file with H1 title
  local file = io.open(full_path, "w")
  if file then
    file:write("# " .. title)
    file:close()
    vim.notify("Created note: " .. full_path, vim.log.levels.INFO)
    
    -- Open the new file
    vim.cmd("edit " .. full_path)
  else
    vim.notify("Failed to create file: " .. full_path, vim.log.levels.ERROR)
  end
end

return M