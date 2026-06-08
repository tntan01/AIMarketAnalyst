# Hướng dẫn cài đặt, chạy và đóng gói

## Mục tiêu

Tài liệu này mô tả cách chuẩn bị môi trường phát triển, chạy ứng dụng PyQt6 và đóng gói để cài trên máy khác.

## Yêu cầu hệ thống

* Windows 10 hoặc Windows 11 64-bit.
* Python 3.11 hoặc 3.12 64-bit.
* MetaTrader 5 đã cài và đăng nhập broker nếu dùng dữ liệu thật.
* Visual C++ Redistributable nếu package `MetaTrader5` hoặc thư viện native yêu cầu.
* Kết nối internet nếu dùng AI provider hoặc tin tức.

## Cài môi trường phát triển

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu chưa có `requirements.txt`, MVP nên bắt đầu với các nhóm dependency:

```text
PyQt6
PyQt6-WebEngine
pandas
numpy
MetaTrader5
requests
python-dotenv
keyring
pytest
pyinstaller
yfinance
```

## Cấu hình runtime

Ứng dụng phải tự tạo thư mục user data khi chạy lần đầu:

```text
%APPDATA%/AI Market Analyst/
  settings.json
  journal.db
  logs/
  exports/
  cache/
```

Không lưu database, settings hoặc log vào thư mục cài đặt sau khi đóng gói.

## Chạy ứng dụng khi phát triển

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Màn hình Dashboard phải mở được dù MT5 hoặc AI chưa cấu hình. Khi thiếu cấu hình, UI hiển thị trạng thái chưa sẵn sàng và hướng dẫn người dùng vào Settings.

## Kiểm tra trước khi build

```powershell
pytest
python main.py
```

Checklist tối thiểu:

* App mở bằng `python main.py`.
* Dashboard không lỗi khi MT5 chưa mở.
* Settings lưu và đọc lại được.
* Journal database tự tạo nếu chưa tồn tại.
* Log file được tạo trong `%APPDATA%/AI Market Analyst/logs/`.
* Không có API key xuất hiện trong log.
* UI không bị tràn ở 1366x768 và 1920x1080.

## Đóng gói Windows bằng PyInstaller

Script build nên nằm trong `packaging/build_windows.ps1`.

Lệnh tham khảo:

```powershell
.\.venv\Scripts\Activate.ps1
pyinstaller packaging\pyinstaller.spec --clean --noconfirm
```

Spec phải include:

* `assets/icons`.
* `assets/fonts`.
* `assets/chart`.
* `ui/styles.qss`.
* `data/migrations`.
* Các package hidden import cần cho PyQt6, PyQt6-WebEngine và MetaTrader5.

## Kiểm tra bản đóng gói

Sau khi build, test trên máy sạch hoặc Windows user profile mới:

* Chạy được bằng double click.
* Tạo user data trong `%APPDATA%`.
* Mở Settings, lưu cấu hình, đóng app, mở lại vẫn còn cấu hình.
* Không cần mở terminal để chạy app.
* Nếu thiếu MT5, app báo lỗi dễ hiểu.
* Nếu thiếu AI key, app vẫn chạy rule-based.
* Chart trong `QWebEngineView` render được khi chạy file `.exe`.
* Export JSON hoạt động.

## Cài đặt trên máy khác

Gói phát hành nên gồm:

```text
AI-Market-Analyst/
  AI Market Analyst.exe
  assets/
  README_USER.md
  LICENSE.txt
```

Nếu dùng installer, installer chỉ đặt file app vào `Program Files` hoặc thư mục người dùng. Dữ liệu cá nhân vẫn nằm trong `%APPDATA%`.

## Lưu ý bảo mật

* Không đóng gói sẵn API key.
* Không ghi API key vào `settings.json` dạng plain text nếu có thể dùng keyring.
* Không gửi journal hoặc log ra ngoài nếu người dùng chưa đồng ý.
