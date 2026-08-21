"""将课程体系目录同步为智课中的可学习课程。

该脚本读取 ``frontend/src/data/curriculumCatalog.json``，把每条主线创建为已发布课程，
把阶段映射为课程章节，把开源资料映射为知识点。脚本可重复执行，已存在的课程、章节和
知识点会按稳定 slug/code 更新，不会产生重复记录。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import ConceptPrerequisite, Course, CourseConcept, CourseSection


def _catalog_path() -> Path:
    """定位前端课程体系数据文件。"""
    return Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "curriculumCatalog.json"


def _slugify(value: str) -> str:
    """将中文或英文字符串转换为稳定的 ASCII 代码片段。"""
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return token[:100]


def _load_catalog() -> dict:
    with _catalog_path().open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _section_code(track_id: str, stage_code: str) -> str:
    return f"{_slugify(track_id)}__{_slugify(stage_code)}"


def _sync_course(db: Session, track: dict) -> Course:
    """按主线 slug 创建或更新课程。"""
    slug = _slugify(track["id"])
    course = db.execute(select(Course).where(Course.slug == slug)).scalar_one_or_none()
    display_config = {
        "color": track.get("color") or "slate",
        "icon": track.get("icon") or "book-open",
        "default_view": "dashboard",
        "source": "curriculum_catalog",
    }

    if course is None:
        course = Course(
            slug=slug,
            title=track["title"],
            description=track["description"],
            applicable_major="计算机 / 人工智能",
            status="published",
            is_default=False,
            display_config=display_config,
        )
        db.add(course)
        db.flush()
    else:
        course.title = track["title"]
        course.description = track["description"]
        course.applicable_major = "计算机 / 人工智能"
        course.status = "published"
        course.display_config = display_config
    return course


def _sync_stage_section(db: Session, course: Course, stage: dict, order_index: int) -> CourseSection:
    """按阶段同步课程章节。"""
    code = _section_code(course.slug, stage["stage"])
    section = db.execute(
        select(CourseSection).where(CourseSection.course_id == course.id, CourseSection.code == code)
    ).scalar_one_or_none()
    description = stage.get("goal") or stage.get("title") or ""

    if section is None:
        section = CourseSection(
            course_id=course.id,
            code=code,
            title=stage["title"],
            description=description,
            order_index=order_index,
        )
        db.add(section)
        db.flush()
    else:
        section.title = stage["title"]
        section.description = description
        section.order_index = order_index
    return section


def _sync_concept(
    db: Session,
    course: Course,
    section: CourseSection,
    resource: dict,
    recommended_order: int,
) -> CourseConcept:
    """把一项开源资料同步为课程知识点。"""
    concept = db.execute(
        select(CourseConcept).where(CourseConcept.course_id == course.id, CourseConcept.code == resource["id"])
    ).scalar_one_or_none()
    definition = resource.get("description") or ""
    difficulty = resource.get("difficulty") or "medium"
    meta_json = {
        "source": "curriculum_catalog",
        "repo": resource.get("repo"),
        "url": resource.get("url"),
        "license": resource.get("license"),
        "resource_type": resource.get("resourceType"),
        "zhike_modules": resource.get("zhikeModules") or [],
        "usage": resource.get("usage"),
    }

    if concept is None:
        concept = CourseConcept(
            course_id=course.id,
            section_id=section.id,
            code=resource["id"],
            title=resource["title"],
            definition=definition,
            difficulty=difficulty,
            recommended_order=recommended_order,
            prerequisites_json=[],
            status="published",
            meta_json=meta_json,
        )
        db.add(concept)
        # 先让主键落盘，后续建立先修关系时需要稳定的 concept_id。
        db.flush()
    else:
        concept.section_id = section.id
        concept.title = resource["title"]
        concept.definition = definition
        concept.difficulty = difficulty
        concept.recommended_order = recommended_order
        concept.status = "published"
        concept.meta_json = meta_json
    return concept


def _sync_prerequisite(
    db: Session,
    course: Course,
    concept: CourseConcept,
    prerequisite: CourseConcept,
) -> None:
    """幂等记录一个知识点对另一个知识点的先修关系。"""
    existing = db.execute(
        select(ConceptPrerequisite).where(
            ConceptPrerequisite.course_id == course.id,
            ConceptPrerequisite.concept_id == concept.id,
            ConceptPrerequisite.prerequisite_id == prerequisite.id,
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            ConceptPrerequisite(
                course_id=course.id,
                concept_id=concept.id,
                prerequisite_id=prerequisite.id,
                dependency_type="sequential",
            )
        )


def main() -> None:
    catalog = _load_catalog()
    db = SessionLocal()
    try:
        created_courses = 0
        updated_courses = 0
        concept_count = 0

        for track in catalog.get("tracks", []):
            exists = db.execute(select(Course).where(Course.slug == _slugify(track["id"]))).scalar_one_or_none()
            course = _sync_course(db, track)
            if exists is None:
                created_courses += 1
            else:
                updated_courses += 1

            recommended_order = 1
            previous_stage_concepts: list[CourseConcept] = []
            for stage_index, stage in enumerate(track.get("stages", []), start=1):
                section = _sync_stage_section(db, course, stage, stage_index)
                stage_concepts: list[CourseConcept] = []
                for resource in stage.get("resources", []):
                    concept = _sync_concept(db, course, section, resource, recommended_order)
                    stage_concepts.append(concept)
                    recommended_order += 1
                    concept_count += 1

                for previous, current in zip(stage_concepts, stage_concepts[1:]):
                    _sync_prerequisite(db, course, current, previous)
                if previous_stage_concepts and stage_concepts:
                    _sync_prerequisite(db, course, stage_concepts[0], previous_stage_concepts[-1])
                previous_stage_concepts = stage_concepts

            db.flush()

        db.commit()
        print(f"课程体系同步完成：新增课程 {created_courses} 门，更新课程 {updated_courses} 门，知识点 {concept_count} 个。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
