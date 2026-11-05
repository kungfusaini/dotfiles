{ pkgs }:

let
  fetch = _name: url: sha256: pkgs.fetchurl {
    inherit url sha256;
  };
  fetchWithUserAgent = _name: url: sha256: pkgs.fetchurl {
    inherit url sha256;
    curlOptsList = [ "-A" "Pegasus-config/1.0 (personal launcher metadata)" ];
  };

  marioKartCover = fetch "mario-kart-8-deluxe-cover.png"
    "https://www.mariowiki.com/images/9/9b/MK8_Deluxe_-_Box_NA.png"
    "1nhrbll1wr0xwhya69i6frrdlafsr7ygrg285mfnk6i711waf2a3";
  marioKartBackground = fetch "mario-kart-8-deluxe-background.jpg"
    "https://www.mariowiki.com/images/4/48/MK8DX_Nintendo_Wallpaper_1.jpg"
    "1ghxnp8wlxq5lanznk8qkj2pd3q3g9az2fbbl204ry9aw7nss72k";
  marioKartLogo = fetch "mario-kart-8-deluxe-logo.png"
    "https://www.mariowiki.com/images/7/78/Mario_Kart_8_Deluxe_logo.png"
    "1h1cdkzbnmiwcidlxvk39izi1ssvnj35ws8bf3x1k7kak5k8bfwy";
  marioKartScreenshot1 = fetch "mario-kart-8-deluxe-screenshot-1.png"
    "https://mario.wiki.gallery/images/1/18/MK8D_Race_Start_Screenshot.png"
    "0mc2immhr4li2a0f5qglndicqc7jh246vc6k4xk7xa4933c6fk4a";
  marioKartScreenshot2 = fetch "mario-kart-8-deluxe-screenshot-2.png"
    "https://mario.wiki.gallery/images/6/6e/MK8D_Inkling_and_Mario.png"
    "1fz2j4rasaghfyi2py23zm8s9war7fgwnnay1z4814z8046s808s";
  marioKartScreenshot3 = fetch "mario-kart-8-deluxe-screenshot-3.png"
    "https://mario.wiki.gallery/images/5/54/MK8D_Isabelle_Sports_Coupe_Screenshot.png"
    "0v142fdpxyz3hjvy3qzxfv3ls6grlhi97ww0dshidszi0cap301f";

  smashCover = fetch "super-smash-bros-ultimate-cover.png"
    "https://www.ssbwiki.com/images/1/15/Super_Smash_Bros_Ultimate_Box_Art.png"
    "1w4rgc5xqx5p0ifjz3scmzvs4wakfa5jdbij5q5jf762jazcfsg4";
  smashKeyArt = fetch "super-smash-bros-ultimate-key-art.png"
    "https://ssb.wiki.gallery/images/7/7e/SSBU_Key_Art.png"
    "119lna4914x9h5iszs6wy6k3iyfrk8a5k867sg9irgd69zzyxgcp";
  smashLogo = fetchWithUserAgent "super-smash-bros-ultimate-logo.svg"
    "https://upload.wikimedia.org/wikipedia/commons/9/96/Super_Smash_Bros._Ultimate_logo.svg"
    "14356350vxv65jpv75pdb9dqyyfbj95l5xnfw9pvxh82nrr276aq";
  smashScreenshot1 = fetchWithUserAgent "super-smash-bros-ultimate-screenshot-1.png"
    "https://ssb.wiki.gallery/images/3/37/SSBU_Dr._Mario_Approaches.png"
    "1ki0x35m4diy63biabx4dby0c001qfwi93j5a88krfqcml6213ah";
  smashScreenshot2 = fetchWithUserAgent "super-smash-bros-ultimate-screenshot-2.png"
    "https://ssb.wiki.gallery/images/f/fe/ScreenKOSmashUltimate.png"
    "10m1vqh4nlacmnrjbqqz9mkdqfyc2prizyqjr3zcc1mv4ammkqcn";
  smashScreenshot3 = fetchWithUserAgent "super-smash-bros-ultimate-screenshot-3.png"
    "https://ssb.wiki.gallery/images/8/82/SSBU-Mario_Bros.png"
    "0dawakr2410nq8n4j6q1arwvdfyszsv9kaywzpk0shngfxn7xsah";

  mario3dWorldCover = fetch "super-mario-3d-world-bowsers-fury-cover.png"
    "https://www.mariowiki.com/images/3/30/SM3DWBF_Box_NA_Final.png"
    "14zdmk9nirvsani3p9nzghdgvbc14rs6j5pd00wls0ffrjlknm02";
  mario3dWorldKeyArt = fetch "super-mario-3d-world-bowsers-fury-key-art.jpg"
    "https://www.mariowiki.com/images/a/a0/SM3DW_BF_My_Nintendo_wallpaper_B_desktop.jpg"
    "0zhkqdzinkzyzrziqb2f0zg0hpgk14dkfzhi1jc20s60zsz0qky9";
  mario3dWorldLogo = fetch "super-mario-3d-world-bowsers-fury-logo.png"
    "https://www.mariowiki.com/images/1/18/SM3DW%2BBF_logo_alt.png"
    "120lk20nf79zn09q8mrcvyd1g9jg4737qfdxr5xqdcx9kvqwvjkp";
  mario3dWorldScreenshot1 = fetch "super-mario-3d-world-bowsers-fury-screenshot-1.png"
    "https://mario.wiki.gallery/images/f/fd/SM3DWBFUpdatedGraphics.png"
    "09vvyqhhgzc5dbqxawd2zr7rifmydsq0dz5q6gg0vk24547ljghl";
  mario3dWorldScreenshot2 = fetch "super-mario-3d-world-bowsers-fury-screenshot-2.png"
    "https://mario.wiki.gallery/images/6/6e/SM3DWBF_Screenshot_Snapshot_Mode_5.png"
    "0g85mmgzvp9mb1bggk4hkp6g3c6y7vb165idvb75jv3pqy2blc4a";
  mario3dWorldScreenshot3 = fetch "super-mario-3d-world-bowsers-fury-screenshot-3.png"
    "https://mario.wiki.gallery/images/0/03/SM3DWBF_Screenshot_Snapshot_Mode_1.png"
    "1vdw7nslppk9kzf7w7ip1x4r7fqrahblizsvm03bimw5bpw4rnh4";

  crazyTaxiKeyArt = fetch "crazy-taxi-key-art.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/library_hero.jpg"
    "0r5z03mmzp2bw9s4ik2yh75hma6isfkiib8vwlaar30zlc9fwx63";
  crazyTaxiCover = fetch "crazy-taxi-cover.jpg"
    "https://cdn.cloudflare.steamstatic.com/steam/apps/71230/library_600x900.jpg"
    "19ylykdgnzd53w5q00bkg7yl8zvgixb8mkk8frfw9v6zv61zajfp";
  crazyTaxiLogo = fetch "crazy-taxi-logo-source.png"
    "https://images.seeklogo.com/logo-png/3/1/crazy-taxi-logo-png_seeklogo-36313.png"
    "06d5d9rdyndi63k10akbzvc27nx2jrbhsgvx80dijxrdj1r2azqw";
  crazyTaxiScreenshot1 = fetch "crazy-taxi-screenshot-1.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_bb08922b713140e0e075df587ba39f9c73612b3c.1920x1080.jpg"
    "11az8g561j7km41znajr2gid6ma2dbrx924jd9im6dzajfr7lrxx";
  crazyTaxiScreenshot2 = fetch "crazy-taxi-screenshot-2.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_5ddc57dd3e43d29787eceaf42e0e30a49419a371.1920x1080.jpg"
    "14469ldrzkwn1737m4hszpsx23j4b9mzqzsff7qh4whyha5zx86s";
  crazyTaxiScreenshot3 = fetch "crazy-taxi-screenshot-3.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_3e9f51f97a38e52a03749975a595754335427c4a.1920x1080.jpg"
    "0ca1700lnd0xv2wgjxjbmkvvn2yybyz8q8jj3lyi4p4c2pglqka2";

  # Official Konami promotional key art; crop away the baked-in bottom logo.
  symphonyKeyArt = fetch "symphony-of-the-night-key-art.jpg"
    "https://www.konami.com/kde_cms/eu_publish/uploads/castlevania-key-art_with-logo.jpg"
    "sha256-t/Eg7ju7xJW/ctjN2nGfbyr8BWUY2mysXud0l3ThujU=";
  symphonyCover = fetch "symphony-of-the-night-cover.jpg"
    "https://www.castlevaniacrypt.com/wp-content/img/sotn/case/case-front.jpg"
    "sha256-Sxz7kJaeEenFurVG+NdG0SXSLSeAwwnG3RaQs6dMEus=";
  symphonyLogo = fetch "symphony-of-the-night-logo.png"
    "https://www.castlevaniacrypt.com/wp-content/img/sotn/logos/sotn-10.png"
    "sha256-elVdNocbipqVQ5Roc0fa8L/Hk+IMuiBJIcydtk7uZLc=";

  raymanCover = fetchWithUserAgent "rayman-legends-cover.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/0782d002fa65af183a2fda2fc5f963059b33eaea/library_capsule.jpg"
    "15gkb7ydypdc51nihyaxag6xl9q5rkfqlp0qpb63q13a0x1innac";
  raymanLogo = fetchWithUserAgent "rayman-legends-logo.png"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/bd197a6edceb35385e570c269d01e3642a252f1d/logo.png"
    "1s9w23gf069g56x5b6x8dzxfhgn7h1aqwgdl72893nwy01hqpylm";
  raymanBackground = fetch "rayman-legends-background.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/2ea46847ba60087fb8997f8c6eadd22cdc44dc50/library_hero.jpg"
    "1130ydkywf192lvzdgac8yavk2fvlpac532h1x0yn6bawv7cd0r8";
  raymanScreenshot1 = fetch "rayman-legends-screenshot-1.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/6aafd4edc1ca27550361fb06f3832209a427e89c/ss_6aafd4edc1ca27550361fb06f3832209a427e89c.1920x1080.jpg"
    "0dqa62q8kx6p9wb5bknqs1508lxssqcajnv4a8a5483an0w71ccp";
  raymanScreenshot2 = fetch "rayman-legends-screenshot-2.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/f7c86e4d2170ed9c539e4b6afdba2531abb47c70/ss_f7c86e4d2170ed9c539e4b6afdba2531abb47c70.1920x1080.jpg"
    "158y1kh3qay5bym8gg4yyn63pwn9h8fhsj2n59b3al1vpfs27k4v";
  raymanScreenshot3 = fetch "rayman-legends-screenshot-3.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/611e0af21dd4b8a6941010088043ba816a79077d/ss_611e0af21dd4b8a6941010088043ba816a79077d.1920x1080.jpg"
    "1s5xylizl4nqcm16lmn99pay6yfcp9b3b63c99j1l60idj4vl14m";

  civilizationCover = fetch "civilization-vi-cover.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/library_600x900.jpg"
    "0d7sni1a10h4wcy4k0k36d4a6k9a7chcl154j94pmkvi3i429969";
  civilizationLogo = fetch "civilization-vi-logo.png"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/c2743b863b6dc3f197b45effc18b95a944eff604/logo.png"
    "0g69xaycakgznjnq2vg5ckgmai7pby4gq5cwgq2ps6dr9dyi9bp5";
  civilizationBackground = fetch "civilization-vi-background.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/95dca23c23f718952bd30cc4a0687cc951a43468/library_hero.jpg"
    "06m7qphjm0bdfvmvndarc3g13ncr3pcq8pkgzlgalpyml5kga7dd";
  civilizationScreenshot1 = fetch "civilization-vi-screenshot-1.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_12cc6e1f4084de5bc0f66bfdbe3aaf3e59388b53.1920x1080.jpg"
    "006sw222lzfhjnb8a2pqs4asgv42fy61az3kik0q77imvjiplqks";
  civilizationScreenshot2 = fetch "civilization-vi-screenshot-2.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_6c4a3cfb61f1a9677cf2ac549c2816a4e651f741.1920x1080.jpg"
    "1ln6vvzj3y49qmyq2gzk49jisg8yrjsw98kn8l6pnir47w7b9sk2";
  civilizationScreenshot3 = fetch "civilization-vi-screenshot-3.jpg"
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_b2bf12299c38214fe520af0f724a6349d17ed330.1920x1080.jpg"
    "0mwabhjp37mzj6vi02fd5hq2lzi5fh9qa1g6x0qbsqdw2gybphd6";
in
pkgs.runCommand "pegasus-curated-artwork" {
  nativeBuildInputs = [ pkgs.imagemagick ];
} ''
  mkdir -p \
    "$out/switch/mario-kart-8-deluxe" \
    "$out/switch/super-smash-bros-ultimate" \
    "$out/switch/super-mario-3d-world-bowsers-fury" \
    "$out/ps2/crazy-taxi" \
    "$out/pc/symphony-of-the-night" \
    "$out/steam/rayman-legends" \
    "$out/steam/civilization-vi"

  make_box() {
    magick "$1" -resize '900x1457>' -strip -quality 90 "$2"
  }
  make_background() {
    magick "$1" -resize '1920x1080^' -gravity center -extent 1920x1080 \
      -strip -quality 90 "$2"
  }
  make_logo() {
    magick "$1" -resize '1200x600>' -strip "$2"
  }
  make_screenshot() {
    magick "$1" -resize '1920x1080>' -strip -quality 88 "$2"
  }

  make_box ${marioKartCover} "$out/switch/mario-kart-8-deluxe/boxFront.jpg"
  make_background ${marioKartBackground} "$out/switch/mario-kart-8-deluxe/background.jpg"
  make_logo ${marioKartLogo} "$out/switch/mario-kart-8-deluxe/logo.png"
  make_screenshot ${marioKartScreenshot1} "$out/switch/mario-kart-8-deluxe/screenshot-1.jpg"
  make_screenshot ${marioKartScreenshot2} "$out/switch/mario-kart-8-deluxe/screenshot-2.jpg"
  make_screenshot ${marioKartScreenshot3} "$out/switch/mario-kart-8-deluxe/screenshot-3.jpg"

  make_box ${smashCover} "$out/switch/super-smash-bros-ultimate/boxFront.jpg"
  magick -background none ${smashLogo} -resize '1200x600>' \
    -fuzz 4% -transparent white -channel RGB -negate +channel -strip \
    "$out/switch/super-smash-bros-ultimate/logo.png"
  # Crop the baked-in title at the bottom; gameOS overlays our transparent logo.
  magick ${smashKeyArt} -gravity north -crop '2740x1010+0+0' +repage \
    -resize '1920x1080^' -gravity center -extent 1920x1080 \
    -strip -quality 90 "$out/switch/super-smash-bros-ultimate/background.jpg"
  make_screenshot ${smashScreenshot1} "$out/switch/super-smash-bros-ultimate/screenshot-1.jpg"
  make_screenshot ${smashScreenshot2} "$out/switch/super-smash-bros-ultimate/screenshot-2.jpg"
  make_screenshot ${smashScreenshot3} "$out/switch/super-smash-bros-ultimate/screenshot-3.jpg"

  make_box ${mario3dWorldCover} "$out/switch/super-mario-3d-world-bowsers-fury/boxFront.jpg"
  make_background ${mario3dWorldKeyArt} "$out/switch/super-mario-3d-world-bowsers-fury/background.jpg"
  make_logo ${mario3dWorldLogo} "$out/switch/super-mario-3d-world-bowsers-fury/logo.png"
  make_screenshot ${mario3dWorldScreenshot1} "$out/switch/super-mario-3d-world-bowsers-fury/screenshot-1.jpg"
  make_screenshot ${mario3dWorldScreenshot2} "$out/switch/super-mario-3d-world-bowsers-fury/screenshot-2.jpg"
  make_screenshot ${mario3dWorldScreenshot3} "$out/switch/super-mario-3d-world-bowsers-fury/screenshot-3.jpg"

  make_box ${crazyTaxiCover} "$out/ps2/crazy-taxi/boxFront.jpg"
  magick ${crazyTaxiLogo} -crop '520x170+40+205' +repage \
    -fuzz 5% -transparent '#fdb827' -trim +repage -resize '1200x600>' \
    -strip "$out/ps2/crazy-taxi/logo.png"
  make_screenshot ${crazyTaxiScreenshot1} "$out/ps2/crazy-taxi/screenshot-1.jpg"
  make_screenshot ${crazyTaxiScreenshot2} "$out/ps2/crazy-taxi/screenshot-2.jpg"
  make_screenshot ${crazyTaxiScreenshot3} "$out/ps2/crazy-taxi/screenshot-3.jpg"
  make_background ${crazyTaxiKeyArt} "$out/ps2/crazy-taxi/background.jpg"

  make_box ${symphonyCover} "$out/pc/symphony-of-the-night/boxFront.jpg"
  magick ${symphonyKeyArt} -crop '3330x1740+34+34' +repage \
    -resize '1920x1080^' -gravity center -extent 1920x1080 \
    -strip -quality 90 "$out/pc/symphony-of-the-night/background.jpg"
  make_logo ${symphonyLogo} "$out/pc/symphony-of-the-night/logo.png"

  make_box ${raymanCover} "$out/steam/rayman-legends/boxFront.jpg"
  make_background ${raymanBackground} "$out/steam/rayman-legends/background.jpg"
  make_logo ${raymanLogo} "$out/steam/rayman-legends/logo.png"
  make_screenshot ${raymanScreenshot1} "$out/steam/rayman-legends/screenshot-1.jpg"
  make_screenshot ${raymanScreenshot2} "$out/steam/rayman-legends/screenshot-2.jpg"
  make_screenshot ${raymanScreenshot3} "$out/steam/rayman-legends/screenshot-3.jpg"

  make_box ${civilizationCover} "$out/steam/civilization-vi/boxFront.jpg"
  make_background ${civilizationBackground} "$out/steam/civilization-vi/background.jpg"
  make_logo ${civilizationLogo} "$out/steam/civilization-vi/logo.png"
  make_screenshot ${civilizationScreenshot1} "$out/steam/civilization-vi/screenshot-1.jpg"
  make_screenshot ${civilizationScreenshot2} "$out/steam/civilization-vi/screenshot-2.jpg"
  make_screenshot ${civilizationScreenshot3} "$out/steam/civilization-vi/screenshot-3.jpg"
''
