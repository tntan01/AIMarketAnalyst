$ErrorActionPreference = "Stop"

python -m pip install -r ..\requirements.txt
pyinstaller .\pyinstaller.spec --clean --noconfirm
