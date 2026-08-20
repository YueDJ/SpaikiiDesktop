from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    # The launchers live in a dedicated bin/ dir on PATH — NOT the whole
    # venv\Scripts (which would shadow the user's python, #83797).
    assert "%LOCALAPPDATA%\\sparkii\\sparkii-agent\\bin" in doc
    assert (
        "Get-Command sparkii        # should print "
        "C:\\Users\\<you>\\AppData\\Local\\sparkii\\sparkii-agent\\bin\\sparkii.exe"
    ) in doc
    # Installer exposes $InstallDir\bin, and must copy the launchers into it.
    assert '$sparkiiBin = "$InstallDir\\bin"' in install
    assert "sparkii.exe" in install and "sparkii-acp.exe" in install
    # Guard against a regression back to putting venv\Scripts on PATH.
    assert '$sparkiiBin = "$InstallDir\\venv\\Scripts"' not in install
