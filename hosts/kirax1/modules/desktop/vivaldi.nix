{ ... }:

let
  googleSearchPolicy = builtins.toJSON {
    DefaultSearchProviderEnabled = true;
    DefaultSearchProviderName = "Google";
    DefaultSearchProviderKeyword = "google.com";
    DefaultSearchProviderSearchURL = "https://www.google.com/search?q={searchTerms}";
  };
in
{
  # Chromium/Vivaldi managed policy: force Google as the address-bar search engine.
  # Verify after rebuild at: vivaldi://policy
  environment.etc."opt/vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;

  # Some Vivaldi/Linux builds look here instead; harmless if unused.
  environment.etc."vivaldi/policies/managed/default-search.json".text = googleSearchPolicy;
}
