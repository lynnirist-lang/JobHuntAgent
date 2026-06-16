---
name: apply_job
version: 1.0.0
description: 对冷却期满的 PENDING_SEND 岗位执行实际投递（点击立即沟通 + 发送打招呼）
skill_type: automation
requires: browser_context
---

## Purpose
对状态为 PENDING_SEND 且 cooldown_until < now() 的岗位，通过 Patchright 模拟
点击"立即沟通"按钮并发送打招呼语，完成后更新状态为 SENT。

## Inputs
| Parameter | Type  | Required | Description                    |
|-----------|-------|----------|--------------------------------|
| job_ids   | int[] | Yes      | 要投递的岗位 ID 列表（已过冷却期）|

## Outputs
| Field         | Type     | Description        |
|---------------|----------|--------------------|
| success_count | int      | 成功投递数量        |
| success_ids   | int[]    | 成功投递的岗位 ID  |
| failed_ids    | int[]    | 失败的岗位 ID      |
| stopped_reason| string   | 提前停止原因（若有）|

## Semi-Auto Flow
1. 用户在 UI 批准岗位 → status = APPROVED
2. 用户点击「启动投递」→ status = PENDING_SEND + cooldown_until = now() + 30min
3. 用户可在冷却期内点「撤销」→ status 回退为 APPROVED
4. APScheduler 每5分钟调用本 Skill → 发送 cooldown 已过的岗位

## Notes
- 单日投递上限由 daily_apply_limit 设置控制
- 每次投递之间有 Gaussian 随机延迟（防风控）
- 连续失败 3 次触发停止保护
