# My Dotfiles

This is my very cool dotfiles repo in which I wish to keep as much system configuration as possible. I have had issues in the past with a couple of things, which I hope this approach to configuration will address.
* Messing up a config and not being able to go back easily
* Wanting to just try something without installing it
* Being able to jump across systems with ease
* Having a bunch of things installed on my system that becomes tedious to track down and remove. 

It is managed by using the gnu util [stow](https://www.gnu.org/software/stow/)

Here is a list of all the dotfiles I have in this repo.

### Brave
This is simply a clone of important files in `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/`, namely History, Bookmarks and Extensions. Backing up extensions like this is a bit silly since I am only interested in what extensions I need and their configs, but this will suffice for now.

### Git
Simple git config that should live in `~/.config/git/config`

### Nix
The bread and butter of this whole thing. Nix flake config should be at `.config/nix/flake.nix`

### Obsidian
Obsidian files should go in the root of the vault in the obsidian folder, in my case:
`~/codex/.obsidian/`

### Stats
This is the config for the macos app stats. You will have to load this config manually using the import feature


