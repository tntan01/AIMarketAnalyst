# Windows Packaging Notes

Recommended path:

1. Build with PyInstaller using `packaging/pyinstaller.spec`.
2. Verify MT5 terminal dependency on target machine.
3. Keep API keys in OS credential storage instead of plain JSON.
4. Ship `assets`, `config/*.json`, and `prompts` with the app bundle.
5. Create an installer after the PyInstaller bundle is stable.
