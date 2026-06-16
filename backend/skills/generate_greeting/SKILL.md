---
name: generate_greeting
version: 1.0.0
description: 为指定岗位批量生成个性化打招呼语，写入数据库
skill_type: llm
model: deepseek-chat
---

## Purpose
读取岗位 JD + 用户档案，调用 DeepSeek LLM 生成 100-150 字的个性化打招呼语，
批量处理后将结果写回数据库，状态更新为 MATCHED。

## Inputs
| Parameter | Type  | Required | Description              |
|-----------|-------|----------|--------------------------|
| job_ids   | int[] | Yes      | 需要生成打招呼语的岗位 ID |

## Outputs
| Field         | Type | Description        |
|---------------|------|--------------------|
| success_count | int  | 成功生成的数量      |
| failed_ids    | int[]| 生成失败的岗位 ID  |

## Notes
- 并发度 semaphore=5，避免 API 限速
- 自动重试 3 次（指数退避）
- 字数约束：100-150 字，适合 BOSS 直聘打招呼框
