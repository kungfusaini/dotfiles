{ pkgs, ... }:

{
  # Keep Neovim as a Home Manager-owned user tool, with plugins and config
  # managed declaratively. Expose it as `vim` and as the session's default
  # editor so terminal tools such as Yazi use it automatically.
  programs.neovim = {
    enable = true;
    defaultEditor = true;
    vimAlias = true;
    plugins = [ pkgs.vimPlugins.vimtex ];

    extraConfig = ''
      " Keep runtime state in XDG directories.
      let g:netrw_home = stdpath('state')
      execute 'set undodir=' . stdpath('state') . '/undo//'
      execute 'set backupdir=' . stdpath('state') . '/backup//'
      execute 'set directory=' . stdpath('cache') . '/swap//'

      set undofile

      filetype plugin indent on
      syntax enable

      " Let LaTeX resolve project-root-relative assets when VimTeX compiles from
      " the directory containing the main .tex file. The trailing colon retains
      " TeX Live's default search path.
      let $TEXINPUTS = './/:..//:../..//:'

      " LaTeX editing: VimTeX + latexmk + Zathura live preview.
      let g:vimtex_view_method = 'zathura'
      let g:vimtex_compiler_method = 'latexmk'
      let g:vimtex_compiler_latexmk = {
            \ 'continuous' : 1,
            \ 'options' : [
            \   '-pdf',
            \   '-interaction=nonstopmode',
            \   '-synctex=1',
            \   '-file-line-error',
            \ ],
            \}

      " Start continuous compilation when VimTeX opens a LaTeX document. Do not
      " press <leader>ll on every save: that mapping toggles the compiler off.
      augroup vimtex_live_preview
        autocmd!
        autocmd User VimtexEventInitPost VimtexCompile
        " Zathura's signal monitor reloads reliably even when latexmk replaces
        " the PDF rather than modifying it in place.
        autocmd User VimtexEventCompileSuccess silent! call system("pkill -HUP -f '[/]bin/zathura'")
      augroup END
    '';
  };

  home.sessionVariables.VISUAL = "nvim";

  programs.zathura = {
    enable = true;
    options.filemonitor = "signal";
  };
}
