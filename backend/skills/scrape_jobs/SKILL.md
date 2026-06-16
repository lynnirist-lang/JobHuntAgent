---
name: scrape_jobs
version: 1.0.0
description: 从BOSS直聘爬取符合条件的岗位，去重后入库
skill_type: automation
requires: browser_context
---

## Purpose
根据关键词、城市、薪资范围爬取BOSS直聘岗位信息，自动去重入库，返回新增岗位ID列表。

## Inputs
| Parameter   | Type     | Required | Default | Description       |
|-------------|----------|----------|---------|-------------------|
| keywords    | string[] | Yes      | -       | 搜索关键词列表    |
| city        | string   | Yes      | -       | 目标城市（中文）  |
| salary_code | string   | No       | ""      | 薪资范围代码      |
| max_pages   | int      | No       | 3       | 最大爬取页数      |

## Outputs
| Field          | Type     | Description              |
|----------------|----------|--------------------------|
| new_count      | int      | 本次新增岗位数            |
| new_job_ids    | int[]    | 新增岗位的数据库 ID 列表  |
| errors         | string[] | 爬取过程中的错误信息      |
| stopped_reason | string   | 提前停止的原因（若有）    |

## Notes
- 使用 Patchright（undetected Playwright）规避反爬
- boss_job_id 去重，已存在的岗位不重复入库
- 遇到验证码会自动等待用户手动通过后继续
