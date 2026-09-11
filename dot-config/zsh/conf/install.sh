#!/usr/bin/env zsh
# This script will install all required zsh packages
cd "${0:A:h}/plugins"
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git
git clone https://github.com/zsh-users/zsh-autosuggestions
git clone https://github.com/jeffreytse/zsh-vi-mode

