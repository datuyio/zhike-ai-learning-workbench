"""助教端路由包：聚合各领域子 router，对外暴露统一的 ta.router。

各子模块均带 prefix="/ta"，此处 include 后即得到完整助教端路由集。
"""
from fastapi import APIRouter

from . import (
    agent,
    alerts,
    announcements,
    assignments,
    classes,
    dashboard,
    diagnosis,
    grading,
    lesson_plans,
    quizzes,
    resources,
)

router = APIRouter()
router.include_router(agent.router)
router.include_router(classes.router)
router.include_router(assignments.router)
router.include_router(lesson_plans.router)
router.include_router(grading.router)
router.include_router(quizzes.router)
router.include_router(diagnosis.router)
router.include_router(resources.router)
router.include_router(alerts.router)
router.include_router(dashboard.router)
router.include_router(announcements.router)
