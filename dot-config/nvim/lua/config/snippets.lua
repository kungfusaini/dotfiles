-- Custom snippets configuration
local snippets = {}

-- Markdown snippets
snippets.markdown = {
  emph = {
    prefix = "emph",
    body = "{{< emph >}}$1{{< /emph >}}",
    description = "Emphasis shortcode"
  }
}

return snippets