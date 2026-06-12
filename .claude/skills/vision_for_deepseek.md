---
name: vision_for_deepseek
description: Automatically invoked whenever the user uploads an image. Uses Google Gemini via AI Studio to analyze images (vision/OCR). Handles PNG, JPEG, GIF, WebP, BMP.
triggers:
  - when the user attaches, uploads, or references an image file
  - when the user asks to read, analyze, describe, or OCR an image
  - when the user pastes a screenshot
---

# Vision for DeepSeek — 2 bước: Gemini đọc ảnh → DeepSeek phân tích sâu

## Luồng xử lý

### Bước 1: Gemini đọc ảnh (Vision)
Gọi Gemini 2.5 Flash để mô tả **toàn bộ nội dung** ảnh một cách chi tiết và đầy đủ nhất:
- Toàn bộ text, số liệu, bảng biểu
- Màu sắc, bố cục, vị trí các thành phần
- UI elements, biểu đồ, đồ thị
- Bất kỳ chi tiết nào có trong ảnh

Prompt cho Gemini PHẢI yêu cầu mô tả cặn kẽ, không bỏ sót chi tiết nào.

### Bước 2: DeepSeek phân tích sâu
Sau khi có mô tả thô từ Gemini, dùng model hiện tại (DeepSeek) để:
- Diễn giải ý nghĩa, ngữ cảnh, hàm ý
- Nhận diện mẫu, bất thường, điểm chính
- Đối chiếu với kiến thức chuyên ngành
- Đưa ra kết luận và đề xuất hành động
- Trả lời câu hỏi cụ thể của user về ảnh

Trả lời user bằng **tiếng Việt** (trừ khi user yêu cầu ngôn ngữ khác).

## Endpoint

- **URL**: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSyBORMAF7b2oYWJ_h6M0NNShmjWX2OTMC3U`
- **Content-Type**: `application/json`

## Cách gửi ảnh

Ảnh phải được chuyển thành **base64** và gửi dưới dạng `inlineData`:

```json
{
  "contents": [{
    "parts": [
      {"text": "PROMPT"},
      {"inlineData": {"mimeType": "image/png", "data": "<BASE64>"}}
    ]
  }],
  "generationConfig": {"maxOutputTokens": 2000}
}
```

## Các bước thực hiện

1. **Đọc ảnh** từ đường dẫn user cung cấp bằng tool `Read`
2. **Tạo script Python** base64-encode ảnh + gọi Gemini API — prompt phải yêu cầu mô tả CHI TIẾT, KHÔNG BỎ SÓT
3. **Chạy script** → nhận mô tả thô từ Gemini
4. **Dùng DeepSeek** phân tích sâu mô tả đó: diễn giải, nhận diện mẫu, kết luận
5. **Trả kết quả** cho user bằng tiếng Việt

## Python script

```python
import base64, requests, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

IMAGE_PATH = r"<duong_dan_anh>"
PROMPT = "<cau_hoi_cua_user>"

with open(IMAGE_PATH, "rb") as f:
    img_b64 = base64.standard_b64encode(f.read()).decode()

ext = IMAGE_PATH.lower().split(".")[-1]
mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
mime = mime_map.get(ext, "image/png")

resp = requests.post(
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    params={"key": "AIzaSyBORMAF7b2oYWJ_h6M0NNShmjWX2OTMC3U"},
    headers={"Content-Type": "application/json"},
    json={
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inlineData": {"mimeType": mime, "data": img_b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 2000},
    },
    timeout=120,
)

data = resp.json()
if resp.status_code == 200:
    print(data["candidates"][0]["content"]["parts"][0]["text"])
else:
    print("ERROR:", data)
```

## Lưu ý

- Dùng `gemini-2.5-flash` — đủ nhanh và chính xác cho vision
- Hỗ trợ PNG, JPEG, GIF, WebP, BMP
- Ảnh dưới ~4MB base64 là an toàn
- Có thể gửi nhiều ảnh cùng lúc (thêm nhiều `inlineData` parts)
