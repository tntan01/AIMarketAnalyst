# Tạo shortcut desktop khởi động app từ mã nguồn (pythonw — không cửa sổ console).
# Icon của shortcut lấy từ assets/icons/app.ico.
# Dùng: powershell -NoProfile -ExecutionPolicy Bypass -File tools\create_desktop_shortcut.ps1

$root = Split-Path -Parent $PSScriptRoot
$ws = New-Object -ComObject WScript.Shell
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'AI Market Analyst.lnk'
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$sc.Arguments = 'main.py'
$sc.WorkingDirectory = $root
$sc.IconLocation = (Join-Path $root 'assets\icons\app.ico') + ', 0'
$sc.Description = 'AI Market Analyst'
$sc.Save()
Write-Output "created: $lnk"
