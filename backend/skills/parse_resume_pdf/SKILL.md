---
name: parse_resume_pdf
version: 1.0.0
description: 解析上传的 PDF 简历，提取结构化信息并填充到 UserProfile
skill_type: llm
model: deepseek-chat
requires: pdfplumber
---

## Purpose
接收 PDF 文件路径，用 pdfplumber 提取文本，再用 DeepSeek LLM 将非结构化
文本解析为标准 UserProfile JSON 格式，供用户确认后保存。

## Inputs
| Parameter | Type   | Required | Description           |
|-----------|--------|----------|-----------------------|
| pdf_path  | string | Yes      | 上传的 PDF 临时文件路径 |

## Outputs
| Field   | Type        | Description                     |
|---------|-------------|---------------------------------|
| profile | UserProfile | 解析出的档案（需用户确认后才保存）|
| raw_text| string      | PDF 提取的原始文本               |

## Notes
- 解析结果不会自动保存，需前端展示给用户确认后调用 POST /api/profile 保存
- LLM 温度 0.2（保守，减少幻觉）
- PDF 超过 50 页时只取前 20 页
