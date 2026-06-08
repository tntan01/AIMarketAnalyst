---
name: ai-box
description: Use when the user needs an LLM to analyze images, perform real-time Google search for current information, or any multimodal task via the API AI Box endpoint. Activates for image analysis, OCR, news search, fact-checking, or any prompt requiring up-to-date external data.
---

When the user asks the LLM to analyze images or search for current/real-time information, use the API AI Box endpoint. This service provides an OpenAI-compatible API with access to Google Gemini models capable of vision and Google Search.

## Endpoint & Auth

- **Base URL**: `https://api.ai-box.vn/v1`
- **Chat Completions**: `POST /v1/chat/completions`
- **Auth header**: `Authorization: Bearer sk-lnpqpiHzylopocvUeqS2MrX96PP8trBWx1kQM36ppxEpzd2R`
- **Content-Type**: `application/json`

## Recommended Model

- **Model ID**: `gemini-3-flash-thinking`
- All-in-one: vision (image analysis) + Google Search (real-time web search)
- No separate `-vision` or `-search` suffix needed
- Responds well in Vietnamese and English

## Image Analysis (Vision)

Images must be sent as **base64 data URLs** inside the standard OpenAI vision content part:

```json
{
  "model": "gemini-3-flash-thinking",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "YOUR PROMPT HERE"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64_DATA>"}}
      ]
    }
  ],
  "max_tokens": 2000
}
```

### Image Requirements

- **Format**: PNG, JPEG, GIF, WebP, BMP (PNG recommended for screenshots)
- **Data URL format**: `data:image/<format>;base64,<data>`
- **Size**: Under ~100KB base64 is safe; larger may increase latency
- HTTP/HTTPS URLs are NOT processed as images — always use base64

## Google Search (Real-time Information)

Simply chat normally — the model performs Google Search automatically when the prompt asks for current information. No special parameters needed.

```json
{
  "model": "gemini-3-flash-thinking",
  "messages": [
    {"role": "user", "content": "Tim tin tuc Viet Nam moi nhat hom nay"}
  ],
  "max_tokens": 2000
}
```

## Usage Examples

### Python — Image Analysis

```python
import base64, requests

with open("image.png", "rb") as f:
    img_b64 = base64.standard_b64encode(f.read()).decode()

resp = requests.post(
    "https://api.ai-box.vn/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-lnpqpiHzylopocvUeqS2MrX96PP8trBWx1kQM36ppxEpzd2R",
        "Content-Type": "application/json",
    },
    json={
        "model": "gemini-3-flash-thinking",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Phân tích chi tiết bức ảnh này."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]
        }],
        "max_tokens": 2000,
    },
)
print(resp.json()["choices"][0]["message"]["content"])
```

### Python — Search

```python
import requests

resp = requests.post(
    "https://api.ai-box.vn/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-lnpqpiHzylopocvUeqS2MrX96PP8trBWx1kQM36ppxEpzd2R",
        "Content-Type": "application/json",
    },
    json={
        "model": "gemini-3-flash-thinking",
        "messages": [{"role": "user", "content": "Tin tức mới nhất hôm nay"}],
        "max_tokens": 1500,
    },
)
print(resp.json()["choices"][0]["message"]["content"])
```

## Best Practices

- **Prompt language**: Match the user's language. The model handles Vietnamese and English well.
- **Search specificity**: For news, include date ("hôm nay 03/06/2026") for better results. Add "kèm nguồn" to request cited sources.
- **Image detail**: Be explicit — "phân tích chuyên sâu" for deep analysis, "mô tả ngắn gọn" for brief.
- **Image format**: PNG for screenshots/text; JPEG for photos.
- **Multiple images**: Include multiple `image_url` parts — the model processes them in order.
- **Timeout**: Vision and search requests may take 10-60 seconds depending on image size and search complexity.
