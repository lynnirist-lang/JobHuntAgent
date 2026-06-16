"""策略配置 API。"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from ..core.settings_store import AgentSettings, load_settings, save_settings

router = APIRouter(tags=["策略配置"])


class SettingsUpdateRequest(BaseModel):
    settings: AgentSettings


@router.get("/settings", summary="读取策略配置")
async def get_settings_endpoint():
    return load_settings().model_dump()


@router.put("/settings", summary="保存策略配置")
async def update_settings(body: SettingsUpdateRequest):
    save_settings(body.settings)
    return {"message": "策略配置已保存"}


@router.post("/settings/reset", summary="重置为默认策略配置")
async def reset_settings():
    """将所有策略配置重置为系统默认值并持久化。"""
    save_settings(AgentSettings())
    return {"message": "已重置为默认策略配置", "settings": AgentSettings().model_dump()}


class SearchUpdateRequest(BaseModel):
    keywords: Optional[List[str]] = None
    city: Optional[str] = None
    salary_code: Optional[str] = None


@router.patch("/settings/search", summary="更新搜索配置")
async def update_search_settings(body: SearchUpdateRequest):
    """更新搜索关键词、城市、薪资等参数，其余配置保持不变。"""
    settings = load_settings()
    if body.keywords is not None:
        settings.search.keywords = body.keywords
    if body.city is not None:
        settings.search.city = body.city
    if body.salary_code is not None:
        settings.search.salary_code = body.salary_code
    save_settings(settings)
    return {"message": "搜索配置已保存"}
