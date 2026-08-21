# nix/packages.nix — Sparkii Agent package built with uv2nix
{ inputs, ... }:
{
  perSystem =
    {
      pkgs,
      lib,
      ...
    }:
    let

      sandbox = pkgs.callPackage ./sandbox.nix { };

      minimal = pkgs.callPackage ./sparkii-agent.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
        # Only embed clean revs — dirtyRev doesn't represent any upstream
        # commit, so comparing it would always claim "update available".
        rev = inputs.self.rev or null;
      };

      # All platform-portable optional integrations pre-built.
      full = minimal.override {
        extraDependencyGroups = [
          "anthropic"
          "azure-identity"
          "bedrock"
          "daytona"
          "edge-tts"
          "exa"
          "fal"
          "firecrawl"
          "hindsight"
          "honcho"
          "modal"
          "parallel-web"
          "tts-premium"
          "vercel"
          "voice"
        ];
      };
    in
    {
      packages = {
        default = full;

        inherit sandbox;

        inherit minimal;
      };
    };
}
