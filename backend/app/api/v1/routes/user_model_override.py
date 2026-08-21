"""学生端个人模型覆盖配置接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.schemas.model_gateway import (
    ModelProviderUpsert,
    ProviderTestResponse,
    UserModelOverrideDeleteResponse,
    UserModelOverrideRead,
    UserModelOverrideUpsert,
)
from app.services.model_gateway.router import ModelGateway
from app.services.model_gateway.user_override_service import UserModelOverrideService

router = APIRouter()


@router.get("", response_model=UserModelOverrideRead)
async def get_user_model_override(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserModelOverrideRead:
    """读取当前用户保存的个人模型覆盖配置。"""
    return UserModelOverrideRead.model_validate(UserModelOverrideService(db).get_override(current_user.id))


@router.put("", response_model=UserModelOverrideRead)
async def save_user_model_override(
    payload: UserModelOverrideUpsert,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserModelOverrideRead:
    """创建或更新当前用户的个人模型覆盖配置。"""
    try:
        result = UserModelOverrideService(db).upsert_override(current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserModelOverrideRead.model_validate(result)


@router.delete("", response_model=UserModelOverrideDeleteResponse)
async def delete_user_model_override(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserModelOverrideDeleteResponse:
    """删除当前用户的个人模型覆盖配置。"""
    deleted = UserModelOverrideService(db).delete_override(current_user.id)
    return UserModelOverrideDeleteResponse(status="deleted" if deleted else "not_found")


@router.post("/test", response_model=ProviderTestResponse)
async def test_user_model_override(
    payload: UserModelOverrideUpsert,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProviderTestResponse:
    """使用待保存的个人配置测试模型连接，不写入数据库。"""
    draft = ModelProviderUpsert(
        provider=payload.provider,
        display_name=payload.provider,
        provider_type="chat",
        base_url=payload.base_url,
        protocol="openai_compatible",
        api_key=payload.api_key,
        chat_model=payload.chat_model,
        supports_stream=True,
    )
    result = await ModelGateway(db).test_connection_draft(draft, actor_external_id=current_user.id)
    return ProviderTestResponse.model_validate(result)
