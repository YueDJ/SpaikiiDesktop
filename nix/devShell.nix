# nix/devShell.nix — Kernel dev shell.
#
# The frontend surfaces (CLI, gateway, TUI, desktop, website) live in the
# sparkii-frontends repo and add their own npm machinery on top of this
# Python kernel dev shell.
{ ... }:
{
  perSystem =
    { pkgs, self', ... }:
    let
      sparkiiAgentDevShellHook = self'.packages.default.passthru.devShellHook;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = with pkgs; [
          self'.packages.sandbox
          uv
        ]
        ++ self'.packages.default.passthru.devDeps;
        shellHook = ''
          ${sparkiiAgentDevShellHook}

          # for the devshell to pick up the src
          export SPARKII_PYTHON_SRC_ROOT=$(git rev-parse --show-toplevel)

          # Let `uv run --active --no-sync` reuse Nix's provisioned Python
          # environment instead of creating an empty project .venv.
          export VIRTUAL_ENV="$(dirname "$(dirname "$(readlink -f "$(command -v python)")")")"

          echo "Sparkii Agent dev shell in $SPARKII_PYTHON_SRC_ROOT"
          echo "Ready. Run 'sparkii' or 'sandbox sparkii' to start."
        '';
      };
    };
}
