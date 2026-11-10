# Curated Pegasus artwork

`media/` contains the permanent, already-rendered images used by Pegasus.
They are versioned with this configuration; builds copy them without downloading
or re-encoding images. Keep these files when cleaning the Nix store.

The initial snapshot is byte-for-byte identical to the deployed artwork built
from commit `0522fcd7185429e8ea6b22d79391748a26e03de0`. Its original fetch hashes and
ImageMagick transformations remain in that commit's
`home/packages/pegasus-artwork.nix`. The images retain their original owners'
rights; this personal configuration does not relicense them.

`artwork.SHA256SUMS` records every deployed image. Verify from this directory:

```sh
sha256sum --check artwork.SHA256SUMS
```

To update artwork, download and inspect the intended image once, prepare the final
JPEG/PNG locally, replace only the relevant `media/` file, and update its checksum
and provenance here. Do not restore build-time downloads. Keep logos transparent
and metadata paths stable. New artwork must be committed before deployment.

## Original download sources (provenance only; never fetched by the build)

- https://www.mariowiki.com/images/9/9b/MK8_Deluxe_-_Box_NA.png
- https://www.mariowiki.com/images/4/48/MK8DX_Nintendo_Wallpaper_1.jpg
- https://www.mariowiki.com/images/7/78/Mario_Kart_8_Deluxe_logo.png
- https://mario.wiki.gallery/images/1/18/MK8D_Race_Start_Screenshot.png
- https://mario.wiki.gallery/images/6/6e/MK8D_Inkling_and_Mario.png
- https://mario.wiki.gallery/images/5/54/MK8D_Isabelle_Sports_Coupe_Screenshot.png
- https://www.ssbwiki.com/images/1/15/Super_Smash_Bros_Ultimate_Box_Art.png
- https://ssb.wiki.gallery/images/7/7e/SSBU_Key_Art.png
- https://upload.wikimedia.org/wikipedia/commons/9/96/Super_Smash_Bros._Ultimate_logo.svg
- https://ssb.wiki.gallery/images/3/37/SSBU_Dr._Mario_Approaches.png
- https://ssb.wiki.gallery/images/f/fe/ScreenKOSmashUltimate.png
- https://ssb.wiki.gallery/images/8/82/SSBU-Mario_Bros.png
- https://www.mariowiki.com/images/3/30/SM3DWBF_Box_NA_Final.png
- https://www.mariowiki.com/images/a/a0/SM3DW_BF_My_Nintendo_wallpaper_B_desktop.jpg
- https://www.mariowiki.com/images/1/18/SM3DW%2BBF_logo_alt.png
- https://mario.wiki.gallery/images/f/fd/SM3DWBFUpdatedGraphics.png
- https://mario.wiki.gallery/images/6/6e/SM3DWBF_Screenshot_Snapshot_Mode_5.png
- https://mario.wiki.gallery/images/0/03/SM3DWBF_Screenshot_Snapshot_Mode_1.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/library_hero.jpg
- https://cdn.cloudflare.steamstatic.com/steam/apps/71230/library_600x900.jpg
- https://images.seeklogo.com/logo-png/3/1/crazy-taxi-logo-png_seeklogo-36313.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_bb08922b713140e0e075df587ba39f9c73612b3c.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_5ddc57dd3e43d29787eceaf42e0e30a49419a371.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/71230/ss_3e9f51f97a38e52a03749975a595754335427c4a.1920x1080.jpg
- https://www.konami.com/kde_cms/eu_publish/uploads/castlevania-key-art_with-logo.jpg
- https://www.castlevaniacrypt.com/wp-content/img/sotn/case/case-front.jpg
- https://www.castlevaniacrypt.com/wp-content/img/sotn/logos/sotn-10.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/0782d002fa65af183a2fda2fc5f963059b33eaea/library_capsule.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/bd197a6edceb35385e570c269d01e3642a252f1d/logo.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/2ea46847ba60087fb8997f8c6eadd22cdc44dc50/library_hero.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/6aafd4edc1ca27550361fb06f3832209a427e89c/ss_6aafd4edc1ca27550361fb06f3832209a427e89c.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/f7c86e4d2170ed9c539e4b6afdba2531abb47c70/ss_f7c86e4d2170ed9c539e4b6afdba2531abb47c70.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/242550/611e0af21dd4b8a6941010088043ba816a79077d/ss_611e0af21dd4b8a6941010088043ba816a79077d.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/library_600x900.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/library_hero.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/logo.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/ss_3e59753eefaba9a7704a18e902b48e8d38e95e0b.1920x1080.jpg?t=1777395376
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/ss_6e987a0678b013bfd0073a9ac4703e1f04ca4dea.1920x1080.jpg?t=1777395376
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1426210/ss_fdac523e3ea4d2f32a44449bb8c224857563bd7d.1920x1080.jpg?t=1777395376
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1687950/library_600x900.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1687950/library_hero.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1687950/logo.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/library_600x900.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/c2743b863b6dc3f197b45effc18b95a944eff604/logo.png
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/95dca23c23f718952bd30cc4a0687cc951a43468/library_hero.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_12cc6e1f4084de5bc0f66bfdbe3aaf3e59388b53.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_6c4a3cfb61f1a9677cf2ac549c2816a4e651f741.1920x1080.jpg
- https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/289070/ss_b2bf12299c38214fe520af0f724a6349d17ed330.1920x1080.jpg
