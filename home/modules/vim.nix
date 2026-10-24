{ pkgs, ... }:

{
  # Keep Vim as a Home Manager-owned user tool, with plugins and config managed
  # declaratively instead of via an ad-hoc ~/.config/vim/vimrc file.
  home.packages = [
    pkgs.vim-full
  ];

  xdg.configFile."vim/pack/nix/start/vimtex".source = pkgs.vimPlugins.vimtex;

  programs.zathura = {
    enable = true;
    options.filemonitor = "signal";
  };

  xdg.configFile."vim/vimrc".text = ''
    " XDG-friendly Vim defaults.
    " Keep runtime state out of $HOME.

    let s:state_home = empty($XDG_STATE_HOME) ? expand('~/.local/state') : $XDG_STATE_HOME
    let s:cache_home = empty($XDG_CACHE_HOME) ? expand('~/.cache') : $XDG_CACHE_HOME

    let g:netrw_home = s:state_home . '/vim'

    set runtimepath^=~/.config/vim
    set packpath^=~/.config/vim

    execute 'set viminfo+=n' . s:state_home . '/vim/viminfo'
    execute 'set undodir=' . s:state_home . '/vim/undo//'
    execute 'set backupdir=' . s:state_home . '/vim/backup//'
    execute 'set directory=' . s:cache_home . '/vim/swap//'

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
}
