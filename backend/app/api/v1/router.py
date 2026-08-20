from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    admin,
    admin_announcements,
    ai,
    announcements,
    assessment_report,
    assessments,
    auth,
    chatdoc_config,
    conversations,
    course_context,
    courses,
    knowledge_base,
    intent_router,
    learning_profile,
    model_gateway,
    paths,
    recommendations,
    resource_review,
    sandbox,
    resources,
    schedules,
    site_settings,
    webhooks,
    ta,
    ta_student,
    user_model_override,
)
from app.core.deps import require_admin

api_router = APIRouter()
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(courses.router, tags=["courses"])
api_router.include_router(course_context.router, tags=["course-context"])
api_router.include_router(conversations.router, tags=["conversations"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai-room"])
api_router.include_router(learning_profile.router, prefix="/learning-profile", tags=["learning-profile"])
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(resources.task_router, prefix="/resource-tasks", tags=["resources"])
api_router.include_router(announcements.router, prefix="/announcements", tags=["announcements"])
api_router.include_router(site_settings.router, prefix="/settings", tags=["site-settings"])
api_router.include_router(paths.router, tags=["learning-path"])
api_router.include_router(schedules.router, prefix="/learning-schedules", tags=["learning-schedules"])
api_router.include_router(assessments.router, prefix="/assessments", tags=["assessments"])
api_router.include_router(assessment_report.router, prefix="/assessment", tags=["assessment"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(sandbox.router, prefix="/sandbox", tags=["sandbox"])
api_router.include_router(site_settings.admin_router, prefix="/admin/settings", tags=["site-settings"])
api_router.include_router(knowledge_base.router, prefix="/admin", tags=["knowledge"], dependencies=[Depends(require_admin)])
api_router.include_router(chatdoc_config.router, prefix="/admin", tags=["chatdoc-config"], dependencies=[Depends(require_admin)])
api_router.include_router(model_gateway.router, prefix="/admin/model-providers", tags=["model-gateway"], dependencies=[Depends(require_admin)])
api_router.include_router(intent_router.router, prefix="/admin/intent-router", tags=["intent-router"], dependencies=[Depends(require_admin)])
api_router.include_router(resource_review.router, prefix="/admin/resources", tags=["resource-review"], dependencies=[Depends(require_admin)])
api_router.include_router(admin_announcements.router, prefix="/admin/announcements", tags=["admin-announcements"], dependencies=[Depends(require_admin)])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
# TA 端路由（无需 admin 权限，ta 或 admin 角色均可访问，权限由业务层 TAGate 守卫）
api_router.include_router(ta.router)
api_router.include_router(ta_student.router)
api_router.include_router(user_model_override.router, prefix="/me/model-override", tags=["user-model-override"])
