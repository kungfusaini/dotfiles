# My Dotfiles

This is my very cool dotfiles repo in which I wish to keep as much system configuration as possible. I have had issues in the past with a couple of things, which I hope this approach to configuration will address.
* Messing up a config and not being able to go back easily
* Wanting to just try something without installing it
* Being able to jump across systems with ease
* Having a bunch of things installed on my system that becomes tedious to track down and remove. 

Here is a list of all the dotfiles I have in this repo, as well as their respective system locations. I aim to use [nix-home-manager](https://github.com/nix-community/home-manager) to make sure all these files go to their correct place!

### Brave
This is simply a clone of `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/` with `../Service Worker/CacheStorage` removed. Yes, a bit crude, as I only care about themes, bookmarks and extensions (+ their configs) but it serves the purpose for now.

### Git
Simple git config that should live in `~/.config/git/config`

### Nix
The bread and butter of this whole thing. Nix flake config should be at `.config/nix/flake.nix`

### Obsidian
Obsidian files should go in the root of the vault in the obsidian folder, in my case:
`~/codex/.obsidian/`

I would like to create a script on my system with will update this repo, but I guess that's what home-manager does, so I will revisit this once I have all of my dotfiles done!
