# CLAUDE.md — AI Market Analyst

## Vision Rule

**When the user attaches, uploads, or references an image file** (screenshot, photo, diagram, chart, etc.), follow the skill at `.claude/skills/vision_for_deepseek.md`.

### Step 1 — Gemini đọc ảnh (Vision)
- Read the image file to confirm it exists
- Write a Python script to base64-encode the image and call Gemini 2.5 Flash via Google AI Studio
- API details and script template are in `.claude/skills/vision_for_deepseek.md`
- The prompt to Gemini MUST ask for an exhaustive, detailed description: all text, objects, colors, layout, numbers, charts, UI elements, etc.
- Run the script — Gemini returns a detailed description of everything in the image

### Step 2 — DeepSeek phân tích sâu
- Take Gemini's raw description as input
- Use the current model (DeepSeek) to do a THOROUGH deep analysis:
  - Interpret the meaning, context, and implications
  - Identify patterns, anomalies, key insights
  - Cross-reference with domain knowledge
  - Provide actionable conclusions
  - Answer any specific questions the user had about the image
- Return the full analysis to the user in Vietnamese (unless user requests otherwise)

This applies to ALL image formats: PNG, JPEG, GIF, WebP, BMP.
