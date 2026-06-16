---
name: adapt_resume
version: 1.0.0
description: 根据指定岗位 JD，对用户现有经历进行针对性措辞调整（不编造内容）
skill_type: llm
model: deepseek-chat
---

## Purpose
读取岗位 JD 和用户真实经历，使用 LLM 对 bullet point 措辞进行重新表述，
突出与 JD 最相关的部分。只改写，不新增，不删除用户实际没有的经历。

## Inputs
| Parameter | Type | Required | Description    |
|-----------|------|----------|----------------|
| job_id    | int  | Yes      | 目标岗位 ID    |

## Outputs
| Field       | Type         | Description              |
|-------------|--------------|--------------------------|
| experiences | Experience[] | 改写后的工作/实习经历列表 |
| projects    | Project[]    | 改写后的项目经历列表      |
| focus_points| string[]     | 此次适配的关键侧重点      |

## Constraints
- 不得新增用户没有的公司、项目、技术栈
- 只能对已有内容进行重新表述和重新排序
- 每条 bullet 控制在 30-60 字
- 结果仅供参考，不自动保存到用户档案
