# nix/checks.nix — Build-time verification tests for the kernel package.
#
# Checks are Linux-only: the full Python venv (via uv2nix) includes
# transitive deps like onnxruntime that lack compatible wheels on
# aarch64-darwin. The package and devShell still work on macOS.
#
# Product-surface checks (CLI subcommands, TUI bundle, desktop, NixOS /
# Home Manager module evaluation, config merge round-trip) live in the
# sparkii-frontends repo, where the `sparkii` binary and the module files
# exist.
{ inputs, ... }: {
  perSystem = { pkgs, lib, self', ... }:
    let
      sparkii-agent = self'.packages.default;
    in
    {
      checks = {
        # Cross-platform evaluation — catches "not supported for interpreter"
        # errors (e.g. sphinx dropping python311) without needing a darwin builder.
        # Evaluation is pure and instant; it doesn't build anything.
        cross-eval = let
          targetSystems = builtins.filter
            (s: inputs.self.packages ? ${s})
            [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
          tryEvalPkg = sys:
            let pkg = inputs.self.packages.${sys}.default;
            in builtins.tryEval (builtins.seq pkg.drvPath true);
          results = map (sys: { inherit sys; result = tryEvalPkg sys; }) targetSystems;
          failures = builtins.filter (r: !r.result.success) results;
          failMsg = lib.concatMapStringsSep "\n" (r: "  - ${r.sys}") failures;
        in pkgs.runCommand "sparkii-cross-eval" { } (
          if failures != [] then
            throw "Package fails to evaluate on:\n${failMsg}"
          else ''
            echo "PASS: package evaluates on all ${toString (builtins.length targetSystems)} platforms"
            mkdir -p $out
            echo "ok" > $out/result
          ''
        );

        # Verify the default package builds successfully (cross-platform).
        # On Linux the runtime checks below already depend on the package,
        # but this ensures darwin builders also build it during flake check.
        build-package = pkgs.runCommand "sparkii-build-package" { } ''
          echo "PASS: package built at ${sparkii-agent}"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify the devShell builds successfully (cross-platform).
        build-devshell = pkgs.runCommand "sparkii-build-devshell" { } ''
          echo "PASS: devShell built at ${self'.devShells.default}"
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify the kernel binary exists, is executable and reports a version.
        package-contents = pkgs.runCommand "sparkii-package-contents" { } ''
          set -e
          echo "=== Checking binaries ==="
          test -x ${sparkii-agent}/bin/sparkii-agent || (echo "FAIL: sparkii-agent binary missing"; exit 1)
          echo "PASS: All binaries present"

          echo "=== Checking version ==="
          ${sparkii-agent}/bin/sparkii-agent version 2>&1 | grep -qi "sparkii" || (echo "FAIL: version check"; exit 1)
          echo "PASS: Version check"

          echo "=== All checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify bundled skills are present in the package
        bundled-skills = pkgs.runCommand "sparkii-bundled-skills" { } ''
          set -e
          echo "=== Checking bundled skills ==="
          test -d ${sparkii-agent}/share/sparkii-agent/skills || (echo "FAIL: skills directory missing"; exit 1)
          echo "PASS: skills directory exists"

          # -L: skills/ is a symlink to the filtered source store path
          SKILL_COUNT=$(find -L ${sparkii-agent}/share/sparkii-agent/skills -name "SKILL.md" | wc -l)
          test "$SKILL_COUNT" -gt 0 || (echo "FAIL: no SKILL.md files found in skills directory"; exit 1)
          echo "PASS: $SKILL_COUNT bundled skills found"

          grep -q "SPARKII_BUNDLED_SKILLS" ${sparkii-agent}/bin/sparkii-agent || \
            (echo "FAIL: SPARKII_BUNDLED_SKILLS not in wrapper"; exit 1)
          echo "PASS: SPARKII_BUNDLED_SKILLS set in wrapper"

          # Optional skills ship via the wrapper too (pythonSrc excludes
          # them from the wheel, so the env var is the only path in nix).
          test -d ${sparkii-agent}/share/sparkii-agent/optional-skills || \
            (echo "FAIL: optional-skills directory missing"; exit 1)
          OPT_COUNT=$(find -L ${sparkii-agent}/share/sparkii-agent/optional-skills -name "SKILL.md" | wc -l)
          test "$OPT_COUNT" -gt 0 || (echo "FAIL: no SKILL.md files in optional-skills"; exit 1)
          grep -q "SPARKII_OPTIONAL_SKILLS" ${sparkii-agent}/bin/sparkii-agent || \
            (echo "FAIL: SPARKII_OPTIONAL_SKILLS not in wrapper"; exit 1)
          echo "PASS: $OPT_COUNT optional skills found, SPARKII_OPTIONAL_SKILLS set in wrapper"

          echo "=== All bundled skills checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify bundled plugins (memory, context_engine, platforms/*) are present
        bundled-plugins = pkgs.runCommand "sparkii-bundled-plugins" { } ''
          set -e
          echo "=== Checking bundled plugins ==="
          test -d ${sparkii-agent}/share/sparkii-agent/plugins || (echo "FAIL: plugins directory missing"; exit 1)
          echo "PASS: plugins directory exists"

          grep -q "SPARKII_BUNDLED_PLUGINS" ${sparkii-agent}/bin/sparkii-agent || \
            (echo "FAIL: SPARKII_BUNDLED_PLUGINS not in wrapper"; exit 1)
          echo "PASS: SPARKII_BUNDLED_PLUGINS set in wrapper"

          echo "=== All bundled plugins checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify bundled i18n locale catalogs are present and resolvable.
        bundled-locales = pkgs.runCommand "sparkii-bundled-locales" { } ''
          set -e
          echo "=== Checking bundled locales ==="
          test -d ${sparkii-agent}/share/sparkii-agent/locales || (echo "FAIL: locales directory missing"; exit 1)
          echo "PASS: locales directory exists"

          LOC_COUNT=$(find -L ${sparkii-agent}/share/sparkii-agent/locales -name "*.yaml" | wc -l)
          test "$LOC_COUNT" -ge 16 || (echo "FAIL: expected >=16 catalogs, found $LOC_COUNT"; exit 1)
          echo "PASS: $LOC_COUNT locale catalogs found"

          test -f ${sparkii-agent}/share/sparkii-agent/locales/en.yaml || (echo "FAIL: en.yaml missing"; exit 1)
          echo "PASS: en.yaml present"

          grep -q "SPARKII_BUNDLED_LOCALES" ${sparkii-agent}/bin/sparkii-agent || \
            (echo "FAIL: SPARKII_BUNDLED_LOCALES not in wrapper"; exit 1)
          echo "PASS: SPARKII_BUNDLED_LOCALES set in wrapper"

          echo "=== All bundled locales checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify bundled optional-mcps catalog is present.
        bundled-mcps = pkgs.runCommand "sparkii-bundled-mcps" { } ''
          set -e
          echo "=== Checking bundled optional-mcps ==="
          test -d ${sparkii-agent}/share/sparkii-agent/optional-mcps || (echo "FAIL: optional-mcps directory missing"; exit 1)
          echo "PASS: optional-mcps directory exists"

          MANIFEST_COUNT=$(find -L ${sparkii-agent}/share/sparkii-agent/optional-mcps -name "manifest.yaml" | wc -l)
          test "$MANIFEST_COUNT" -gt 0 || (echo "FAIL: no manifest.yaml files found"; exit 1)
          echo "PASS: $MANIFEST_COUNT catalog manifests found"

          grep -q "SPARKII_OPTIONAL_MCPS" ${sparkii-agent}/bin/sparkii-agent || \
            (echo "FAIL: SPARKII_OPTIONAL_MCPS not in wrapper"; exit 1)
          echo "PASS: SPARKII_OPTIONAL_MCPS set in wrapper"

          echo "=== All bundled optional-mcps checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify extraPythonPackages PYTHONPATH injection
        extra-python-packages = let
          testPkg = pkgs.python312Packages.pyfiglet;
          sparkiiWithExtra = sparkii-agent.override {
            extraPythonPackages = [ testPkg ];
          };
        in pkgs.runCommand "sparkii-extra-python-packages" { } ''
          set -e
          echo "=== Checking extraPythonPackages PYTHONPATH injection ==="

          grep -q "PYTHONPATH" ${sparkiiWithExtra}/bin/sparkii-agent || \
            (echo "FAIL: PYTHONPATH not in wrapper"; exit 1)
          echo "PASS: PYTHONPATH present in wrapper"

          grep -q "${testPkg}" ${sparkiiWithExtra}/bin/sparkii-agent || \
            (echo "FAIL: test package path not in PYTHONPATH"; exit 1)
          echo "PASS: test package path found in wrapper"

          echo "=== Checking base package has no PYTHONPATH ==="
          if grep -q "PYTHONPATH" ${sparkii-agent}/bin/sparkii-agent; then
            echo "FAIL: base package should not have PYTHONPATH"; exit 1
          fi
          echo "PASS: base package clean"

          echo "=== All extraPythonPackages checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';

        # Verify extraDependencyGroups passes through to python.nix
        extra-dependency-groups = let
          sparkiiWithGroups = sparkii-agent.override {
            extraDependencyGroups = [ "honcho" ];
          };
        in pkgs.runCommand "sparkii-extra-dependency-groups" { } ''
          set -e
          echo "=== Checking extraDependencyGroups override evaluates ==="

          # Eval-only: verify the override produces valid derivation paths
          # without building the full venv (which is expensive and redundant
          # since the mechanism is just list concatenation into python.nix).
          echo "derivation: ${sparkiiWithGroups}"
          echo "venv: ${sparkiiWithGroups.sparkiiVenv}"
          echo "PASS: extraDependencyGroups override evaluates cleanly"

          echo "=== All extraDependencyGroups checks passed ==="
          mkdir -p $out
          echo "ok" > $out/result
        '';
      };
    };
}
