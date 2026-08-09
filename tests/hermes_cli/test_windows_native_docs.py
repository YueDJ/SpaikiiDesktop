from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\sparkii\\sparkii-agent\\venv\\Scripts" in doc
    assert "Get-Command sparkii        # should print C:\\Users\\<you>\\AppData\\Local\\sparkii\\sparkii-agent\\venv\\Scripts\\sparkii.exe" in doc
    assert '$sparkiiBin = "$InstallDir\\venv\\Scripts"' in install
