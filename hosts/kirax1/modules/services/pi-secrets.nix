{ ... }:

{
  # Decrypted at activation time by sops-nix. The plaintext key is readable only
  # by Sumeet and is consumed directly by the Pi NanoGPT extension.
  sops.secrets.nanogpt-api-key = {
    sopsFile = ../../../../sops/kirax1.yaml;
    owner = "sumeet";
    group = "users";
    mode = "0400";
  };
}
