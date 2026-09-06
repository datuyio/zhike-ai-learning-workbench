"""把本地知识库 Markdown 语料映射为课程知识点并关联切片。

本地知识库已经具备可检索的文档和向量切片，但学习路径由 ``CourseConcept``
驱动。本脚本从 ``DocumentChunk.heading_path_json`` 与语料相对路径中提取稳定
学习主题，创建或更新课程知识点，并把对应切片写入
``DocumentChunk.concept_id``。脚本可重复执行，编码和切片关联均按稳定键
幂等更新，不会重复创建知识点。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    ConceptPrerequisite,
    Course,
    CourseConcept,
    CourseSection,
    Document,
    DocumentChunk,
    LearningPath,
    User,
)
from app.services.learning.repository import LearningRepository


LANGUAGE_DIR_RE = re.compile(r"^[a-z]{2,3}(?:[-_][a-z]{2,3})?$", re.IGNORECASE)
LANGUAGE_SUFFIX_RE = re.compile(
    r"[._-](?:en|zh[-_]?(?:cn|tw|hans|hant)|ar[-_]?(?:eg|sa)?|pt[-_]?br|es[-_]?es)$",
    re.IGNORECASE,
)
HEADING_LEADING_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*[\.·、:：\-—]?\s*")
QUESTION_HEADING_RE = re.compile(r"^\d{1,3}\.\s+")
ROOT_HEADING_TITLES = {
    "coding interview university",
    "javascript questions",
    "thealgorithms/python",
    "generative ai for beginners",
    "ml for beginners",
    "ai for beginners",
}
META_FILENAMES = {
    "agents.md",
    "code_of_conduct.md",
    "contributing.md",
    "security.md",
    "support.md",
    "troubleshooting.md",
    "changelog.md",
    "license.md",
    "license.en.md",
    "claude.md",
    "translations.md",
    "summary.md",
}
IGNORED_TOP_HEADINGS = {
    "about",
    "additional books",
    "additional detail on some subjects",
    "additional learning",
    "a note about video resources",
    "books for data structures and algorithms",
    "choose a programming language",
    "coding question practice",
    "coding problems",
    "computer science courses",
    "contribution",
    "contributing guidelines",
    "documentation",
    "don't feel you aren't smart enough",
    "don't make my mistakes",
    "even more knowledge",
    "final review",
    "for this study plan",
    "for your coding interview",
    "getting the job",
    "how to use it",
    "if you don't want to use git",
    "if you're comfortable with git",
    "interview prep books",
    "installation",
    "license",
    "more knowledge",
    "optional extra topics & resources",
    "overview",
    "papers",
    "project overview",
    "repository structure",
    "resources",
    "table of contents",
    "the daily plan",
    "topics of study",
    "usage",
    "video series",
    "what is it?",
    "what you won't see covered",
    "why use it?",
}


@dataclass
class LocalDocumentRecord:
    """本地语料文档及其切片的内存聚合。"""

    document: Document
    relative_path: str
    canonical_path: str
    repo: str
    repo_key: str
    chunks: list[DocumentChunk]


@dataclass
class CandidateSpec:
    """一个待写入知识点的来源描述。"""

    key: str
    match_kind: str
    match_value: str
    source_document_id: UUID
    source_relative_path: str
    heading_text: str | None = None
    difficulty: str = "medium"


def _reconfigure_stdout() -> None:
    """在 Windows 控制台强制使用 UTF-8 输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def _source_meta(document: Document) -> dict:
    """读取批量导入时写入的来源元数据。"""
    return document.meta_json.get("source_meta") or document.meta_json or {}


def _is_language_dir(value: str) -> bool:
    """判断路径片段是否为语言翻译目录。"""
    lowered = value.lower()
    if lowered in {"etc", "docs", "api", "src", "css", "js", "git", "ml", "ai"}:
        return False
    return bool(LANGUAGE_DIR_RE.fullmatch(value))


def _normalize_readme_stem(stem: str) -> str:
    """去掉 README 或索引文件的语言后缀，保留普通主题文件名。"""
    lowered = stem.lower()
    if lowered.startswith(("readme", "index", "license", "contributing", "security", "support", "troubleshooting", "agents")):
        return re.sub(r"[._-][a-z]{2,3}(?:[-_][a-z]{2,3})?$", "", stem)
    return LANGUAGE_SUFFIX_RE.sub("", stem)


def _canonical_relative_path(value: str) -> str:
    """把中文、英文和翻译路径归一化到同一条逻辑语料路径。"""
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if not parts:
        return ""
    if parts[0].lower() == "translations" and len(parts) > 1:
        parts = parts[1:]
    if parts and parts[0].lower() == "en":
        parts = parts[1:]
    for index, part in enumerate(parts[:-1]):
        if part.lower() == "units" and _is_language_dir(parts[index + 1]):
            parts = parts[: index + 1] + parts[index + 2 :]
            break
    if parts and _is_language_dir(parts[0]):
        parts = parts[1:]
    if not parts:
        return ""

    filename = parts[-1]
    path = PurePosixPath(filename)
    stem = path.stem
    suffix = path.suffix
    normalized_stem = _normalize_readme_stem(stem)
    parts[-1] = f"{normalized_stem}{suffix if suffix else '.md'}"
    return "/".join(parts)


def _clean_heading(value: str, keep_leading_number: bool = False) -> str:
    """清理标题中的 Markdown 标记、编号前缀和常见装饰符号。"""
    cleaned = value or ""
    cleaned = re.sub(r"[#*_>`~\[\](){}|]", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[\u2600-\u27BF\uFE0F]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -·.:")
    if not keep_leading_number:
        cleaned = HEADING_LEADING_NUMBER_RE.sub("", cleaned)
    return cleaned.strip()[:120] or "未命名主题"


def _normalize_heading_key(value: str) -> str:
    """用于比较标题是否属于同一知识点。"""
    keep_number = bool(QUESTION_HEADING_RE.match(value))
    return _clean_heading(value, keep_leading_number=keep_number).casefold().replace(" ", "")


IGNORED_HEADING_KEYS = {_normalize_heading_key(item) for item in IGNORED_TOP_HEADINGS}


def _heading_candidates_for_path(chunk: DocumentChunk) -> list[str]:
    """从切片标题路径中提取可作为知识点的标题。"""
    path = chunk.heading_path_json or []
    if not path:
        return []
    first = str(path[0])
    if first.strip().casefold() in ROOT_HEADING_TITLES and len(path) > 1:
        topic = str(path[1])
        if _normalize_heading_key(topic) not in IGNORED_HEADING_KEYS:
            return [topic]
        return []
    question_headings = [str(item) for item in path if QUESTION_HEADING_RE.match(str(item))]
    if question_headings:
        return [question_headings[-1]]
    if _normalize_heading_key(first) not in IGNORED_HEADING_KEYS:
        return [first]
    return []


def _title_from_heading(record: LocalDocumentRecord) -> str | None:
    """优先从原始语料切片中读取标题。"""
    ordered = sorted(record.chunks, key=lambda chunk: (chunk.reading_order_index or chunk.chunk_index))
    for chunk in ordered:
        for heading in _heading_candidates_for_path(chunk):
            cleaned = _clean_heading(heading, keep_leading_number=bool(QUESTION_HEADING_RE.match(heading)))
            if cleaned and cleaned not in {"未命名主题", "Answer", "Answers"}:
                return cleaned
    return None


def _title_from_path(relative_path: str) -> str:
    """从文件或目录名构造可读标题。"""
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
    if not parts:
        return "本地课程资料"
    filename = PurePosixPath(parts[-1]).stem
    filename = LANGUAGE_SUFFIX_RE.sub("", filename)
    filename = re.sub(r"^\d+\s*[-_.]\s*", "", filename)
    if filename.lower() == "readme" and len(parts) > 1:
        filename = re.sub(r"^\d+\s*[-_.]\s*", "", parts[-2])
    cleaned = filename.replace("_", " ").replace("-", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return "本地课程资料"
    if not re.search(r"[\u4e00-\u9fff]", cleaned):
        cleaned = " ".join(word if word.isupper() else word.capitalize() for word in cleaned.split())
    return _clean_heading(cleaned)[:120]


def _slugify(value: str) -> str:
    """生成仅含英文数字和下划线的稳定代码片段。"""
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return token[:80]


def _stable_hash(value: str) -> str:
    """为中文或复杂路径生成可复现的短哈希。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _natural_key(value: str) -> list[object]:
    """把数字片段转换为整数，保证章节按自然顺序排列。"""
    return [int(token) if token.isdigit() else token.lower() for token in re.split(r"(\d+)", value)]


def _is_meta_file(relative_path: str) -> bool:
    """过滤仓库维护文件，不把它们变成独立学习主题。"""
    return PurePosixPath(relative_path).name.lower() in META_FILENAMES


def _is_root_readme(relative_path: str) -> bool:
    """判断是否位于仓库根目录的 README。"""
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
    return len(parts) == 1 and PurePosixPath(parts[0]).stem.lower() == "readme"


def _looks_like_learning_dir(canonical_path: str) -> bool:
    """判断 README 是否属于编号课程、课时或学习目录。"""
    parts = [part for part in canonical_path.split("/") if part][:-1]
    if not parts:
        return False
    if any(re.search(r"(^|[-_])\d+([._-]|$)", part) for part in parts):
        return True
    return any(part.lower() in {"lessons", "tutorial", "units", "guides", "notes_md"} for part in parts)


def _direct_spec(record: LocalDocumentRecord, match_kind: str, match_value: str) -> CandidateSpec:
    """构造一个按文件或目录聚合的知识点来源。"""
    return CandidateSpec(
        key=f"{match_kind}:{match_value}",
        match_kind=match_kind,
        match_value=match_value,
        source_document_id=record.document.id,
        source_relative_path=record.relative_path,
    )


def _heading_specs(record: LocalDocumentRecord, limit: int = 80) -> list[CandidateSpec]:
    """把大型路线图 README 的章节拆成可学习知识点。"""
    by_key: dict[str, CandidateSpec] = {}
    for chunk in sorted(record.chunks, key=lambda item: item.chunk_index):
        for heading in _heading_candidates_for_path(chunk):
            keep_number = bool(QUESTION_HEADING_RE.match(heading))
            cleaned = _clean_heading(heading, keep_leading_number=keep_number)
            normalized = _normalize_heading_key(heading)
            if not cleaned or normalized in IGNORED_HEADING_KEYS or normalized in by_key:
                continue
            by_key[normalized] = CandidateSpec(
                key=f"heading:{_stable_hash(normalized)}",
                match_kind="heading",
                match_value=normalized,
                source_document_id=record.document.id,
                source_relative_path=record.relative_path,
                heading_text=cleaned,
            )
            if len(by_key) >= limit:
                return list(by_key.values())
    return list(by_key.values())


def _specs_for_document(record: LocalDocumentRecord) -> list[CandidateSpec]:
    """根据仓库结构和课程目录规则提取知识点候选。"""
    relative_path = record.relative_path
    canonical_path = record.canonical_path
    if _is_meta_file(relative_path) or not canonical_path:
        return []

    repo_key = record.repo_key
    parts = [part for part in canonical_path.split("/") if part]
    stem = PurePosixPath(canonical_path).stem.lower()

    if _is_root_readme(relative_path) and repo_key in {"coding_interview_university", "javascript_questions"}:
        return _heading_specs(record)

    if stem == "readme":
        parent = str(PurePosixPath(canonical_path).parent)
        readme_repos = {
            "agents-course",
            "homemade-machine-learning",
            "openai_cookbook",
            "python",
        }
        if parent != "." and (_looks_like_learning_dir(canonical_path) or repo_key in readme_repos):
            return [_direct_spec(record, "dir", parent)]

    if repo_key == "awesome_architecture":
        if parts[0] == "tutorial" and len(parts) == 2 and stem not in {"readme", "术语表", "演进触发信号"}:
            return [_direct_spec(record, "file", canonical_path)]
        if parts[0] in {"templates", "cases"}:
            return [_direct_spec(record, "dir", parts[0])]

    if repo_key == "cs_self_learning" and parts[0] == "docs" and len(parts) == 3:
        return [_direct_spec(record, "file", canonical_path)]

    if repo_key == "deeplearning_lhy21_notes" and parts[0] == "notes_md" and stem not in {"readme", "summary"}:
        return [_direct_spec(record, "file", canonical_path)]

    if repo_key == "prompt_engineering_guide" and parts[0] == "guides" and stem != "readme":
        return [_direct_spec(record, "file", canonical_path)]
    if repo_key == "prompt_engineering_guide" and canonical_path == "guides/readme.md":
        return []

    if repo_key == "leetcode_solutions" and re.fullmatch(r"\d{4}-\d{4}", stem):
        return [_direct_spec(record, "file", canonical_path)]

    if repo_key == "openai_cookbook" and canonical_path.startswith("articles/"):
        return [_direct_spec(record, "file", canonical_path)]

    return []


def _load_records(db: Session, course: Course) -> list[LocalDocumentRecord]:
    """按课程聚合本地文档和可用切片。"""
    rows = db.execute(
        select(Document, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(
            Document.course_id == course.id,
            Document.source_type == "local_pgvector",
            Document.deleted_at.is_(None),
            DocumentChunk.lifecycle_status == "active",
        )
        .order_by(Document.filename, DocumentChunk.chunk_index)
    ).all()
    by_document: dict[UUID, LocalDocumentRecord] = {}
    for document, chunk in rows:
        meta = _source_meta(document)
        repo = str(meta.get("repo") or "")
        relative_path = str(meta.get("relative_path") or document.filename)
        record = by_document.get(document.id)
        if record is None:
            record = LocalDocumentRecord(
                document=document,
                relative_path=relative_path,
                canonical_path=_canonical_relative_path(relative_path),
                repo=repo,
                repo_key=_slugify(repo.rsplit("/", 1)[-1]),
                chunks=[],
            )
            by_document[document.id] = record
        record.chunks.append(chunk)
    return list(by_document.values())


def _existing_concepts(db: Session, course: Course) -> list[CourseConcept]:
    """读取当前课程已发布知识点，用于更新和来源映射。"""
    return list(
        db.execute(
            select(CourseConcept)
            .where(CourseConcept.course_id == course.id, CourseConcept.status == "published")
            .order_by(CourseConcept.recommended_order, CourseConcept.created_at)
        ).scalars().all()
    )


def _repo_order(concepts: Iterable[CourseConcept], repo: str) -> int:
    """按已有目录资源顺序稳定排列同一课程的多个仓库。"""
    for concept in concepts:
        if (concept.meta_json or {}).get("repo") == repo:
            return int(concept.recommended_order or 0)
    return 9999


def _match_spec(record: LocalDocumentRecord, spec: CandidateSpec) -> bool:
    """判断文档是否属于指定候选聚合。"""
    if spec.match_kind == "file":
        return record.canonical_path == spec.match_value
    if spec.match_kind == "dir":
        return record.canonical_path == spec.match_value or record.canonical_path.startswith(f"{spec.match_value}/")
    return spec.match_kind == "heading" and record.document.id == spec.source_document_id


def _heading_values_for_chunk(chunk: DocumentChunk) -> set[str]:
    """返回切片可归属的标题键，用于大型 README 的细粒度关联。"""
    return {_normalize_heading_key(item) for item in _heading_candidates_for_path(chunk)}


def _record_preference(record: LocalDocumentRecord) -> tuple[int, int, int, int, int, str]:
    """优先使用课程 README 和中文原始文件确定主题标题。"""
    filename = PurePosixPath(record.canonical_path).name
    stem = PurePosixPath(filename).stem.lower()
    is_readme = stem == "readme"
    is_assignment = stem in {"assignment", "template", "index"}
    is_english = filename.lower().endswith((".en.md", "-en.md", "_en.md"))
    is_translation = record.relative_path.startswith("translations/") or _is_language_dir(
        record.relative_path.split("/", 1)[0]
    )
    return (
        0 if is_readme else 1,
        1 if is_assignment else 0,
        1 if is_english else 0,
        1 if is_translation else 0,
        len(record.relative_path),
        record.relative_path,
    )


def _group_specs(
    records: list[LocalDocumentRecord],
    specs: list[CandidateSpec],
    existing_concepts: list[CourseConcept],
) -> list[dict]:
    """把来源候选合并为稳定、可排序、可幂等的知识点组。"""
    grouped: dict[str, dict] = {}
    for spec in specs:
        source_record = next((record for record in records if record.document.id == spec.source_document_id), None)
        repo = source_record.repo if source_record else ""
        repo_key = source_record.repo_key if source_record else "unknown"
        group = grouped.setdefault(
            spec.key,
            {
                "key": spec.key,
                "repo": repo,
                "repo_key": repo_key,
                "match_kind": spec.match_kind,
                "match_value": spec.match_value,
                "heading_text": spec.heading_text,
                "source_document_ids": set(),
                "specs": [],
            },
        )
        group["specs"].append(spec)
        for record in records:
            if _match_spec(record, spec):
                group["source_document_ids"].add(record.document.id)

    results: list[dict] = []
    for group in grouped.values():
        matching_records = [
            record for record in records if record.document.id in group["source_document_ids"]
        ]
        source_record = min(matching_records, key=_record_preference) if matching_records else None
        if source_record is None:
            continue
        title = group["heading_text"] or _title_from_heading(source_record) or _title_from_path(source_record.relative_path)
        difficulty = "medium"
        for concept in existing_concepts:
            if (concept.meta_json or {}).get("repo") == group["repo"]:
                difficulty = concept.difficulty or "medium"
                break
        results.append(
            {
                **group,
                "title": title,
                "difficulty": difficulty,
                "sort_key": (
                    _repo_order(existing_concepts, group["repo"]),
                    *_natural_key(group["match_value"]),
                    _natural_key(title),
                ),
            }
        )
    return sorted(results, key=lambda item: item["sort_key"])


def _ensure_local_section(
    db: Session,
    course: Course,
    repo: str,
    repo_key: str,
    concepts_by_repo: dict[str, CourseConcept],
    existing_sections: list[CourseSection],
) -> CourseSection:
    """为本地仓库主题创建稳定的课程章节。"""
    code = f"local__{_slugify(repo_key)}__{_stable_hash(repo)}"
    section = next((item for item in existing_sections if item.code == code), None)
    resource_concept = concepts_by_repo.get(repo)
    title = resource_concept.title if resource_concept else repo.rsplit("/", 1)[-1].replace("-", " ").title()
    description = f"来自 {repo} 的本地学习主题，自动关联知识库切片。"
    max_order = max((item.order_index or 0 for item in existing_sections), default=0)
    order_index = max_order + 1 + len(existing_sections)
    if section is None:
        section = CourseSection(
            course_id=course.id,
            code=code,
            title=title[:200],
            description=description,
            order_index=order_index,
            meta_json={"auto_generated": True, "source": "local_documents", "repo": repo},
        )
        db.add(section)
        db.flush()
        existing_sections.append(section)
    else:
        section.title = title[:200]
        section.description = description
        section.order_index = order_index
    return section


def _ensure_concept(
    db: Session,
    course: Course,
    section: CourseSection,
    repo: str,
    repo_key: str,
    group: dict,
    order_index: int,
) -> CourseConcept:
    """创建或更新知识点，编码由稳定哈希保证可重复执行。"""
    code = f"local_{_slugify(repo_key)}_{_stable_hash(group['key'])}"
    concept = db.execute(
        select(CourseConcept).where(CourseConcept.course_id == course.id, CourseConcept.code == code)
    ).scalar_one_or_none()
    meta_json = {
        "auto_generated": True,
        "source": "local_documents",
        "repo": repo,
        "relative_path": group["match_value"],
        "candidate_key": group["key"],
    }
    if concept is None:
        concept = CourseConcept(
            course_id=course.id,
            section_id=section.id,
            code=code,
            title=group["title"],
            definition=f"来自 {repo} 的本地学习主题，与知识库切片直接关联。",
            difficulty=group["difficulty"],
            recommended_order=order_index,
            prerequisites_json=[],
            status="published",
            meta_json=meta_json,
        )
        db.add(concept)
        db.flush()
    else:
        concept.section_id = section.id
        concept.title = group["title"]
        concept.definition = f"来自 {repo} 的本地学习主题，与知识库切片直接关联。"
        concept.difficulty = group["difficulty"]
        concept.recommended_order = order_index
        concept.status = "published"
        concept.meta_json = meta_json
    return concept


def _sync_prerequisites(
    db: Session,
    course: Course,
    concept: CourseConcept,
    previous_concept: CourseConcept | None,
    resource_concept: CourseConcept | None,
) -> None:
    """建立并收敛先修关系，清理已不再属于当前映射的旧边。"""
    target_ids = {prerequisite.id for prerequisite in (resource_concept, previous_concept) if prerequisite is not None and prerequisite.id != concept.id}
    existing_rows = db.execute(
        select(ConceptPrerequisite).where(
            ConceptPrerequisite.course_id == course.id,
            ConceptPrerequisite.concept_id == concept.id,
        )
    ).scalars().all()
    for row in existing_rows:
        if row.prerequisite_id not in target_ids:
            db.delete(row)
    prerequisite_codes: list[str] = []
    for prerequisite in (resource_concept, previous_concept):
        if prerequisite is None or prerequisite.id == concept.id:
            continue
        if prerequisite.code in prerequisite_codes:
            continue
        prerequisite_codes.append(prerequisite.code)
        existing = next((row for row in existing_rows if row.prerequisite_id == prerequisite.id), None)
        if existing is None:
            db.add(
                ConceptPrerequisite(
                    course_id=course.id,
                    concept_id=concept.id,
                    prerequisite_id=prerequisite.id,
                    dependency_type="strong",
                )
            )
    concept.prerequisites_json = prerequisite_codes


def _archive_stale_generated_concepts(db: Session, course: Course, active_codes: set[str]) -> int:
    """归档不再由本地语料候选生成的知识点，并移除其旧先修边。"""
    generated = db.execute(select(CourseConcept).where(CourseConcept.course_id == course.id)).scalars().all()
    archived = 0
    for concept in generated:
        meta = concept.meta_json or {}
        if meta.get("source") != "local_documents" or not meta.get("auto_generated") or concept.code in active_codes:
            continue
        if concept.status != "archived":
            concept.status = "archived"
            archived += 1
        stale_edges = db.execute(
            select(ConceptPrerequisite).where(ConceptPrerequisite.concept_id == concept.id)
        ).scalars().all()
        for edge in stale_edges:
            db.delete(edge)
    return archived


def _reverse_chunk_mapping(mapping: dict[UUID, UUID]) -> dict[UUID, list[UUID]]:
    """把切片到概念映射按概念聚合，减少 SQL 更新批次。"""
    result: dict[UUID, list[UUID]] = defaultdict(list)
    for chunk_id, concept_id in mapping.items():
        result[concept_id].append(chunk_id)
    return result


def _sync_chunks(
    db: Session,
    records: list[LocalDocumentRecord],
    groups: list[dict],
    concept_by_group: dict[str, CourseConcept],
    overview_by_repo: dict[str, CourseConcept],
) -> tuple[int, int, int]:
    """把切片批量关联到主题知识点或仓库总览知识点。"""
    chunk_mapping: dict[UUID, UUID] = {}
    for group in groups:
        concept = concept_by_group[group["key"]]
        for record in records:
            if record.document.id not in group["source_document_ids"]:
                continue
            for chunk in record.chunks:
                if group["match_kind"] == "heading":
                    if group["match_value"] not in _heading_values_for_chunk(chunk):
                        continue
                chunk_mapping[chunk.id] = concept.id

    overview_mapped = 0
    for record in records:
        overview = overview_by_repo.get(record.repo)
        if overview is None:
            continue
        for chunk in record.chunks:
            if chunk.id not in chunk_mapping:
                chunk_mapping[chunk.id] = overview.id
                overview_mapped += 1

    changed = 0
    for concept_id, chunk_ids in _reverse_chunk_mapping(chunk_mapping).items():
        existing_ids = {
            str(row[0])
            for row in db.execute(
                select(DocumentChunk.id).where(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.concept_id == concept_id,
                )
            ).all()
        }
        target_ids = [chunk_id for chunk_id in chunk_ids if str(chunk_id) not in existing_ids]
        if not target_ids:
            continue
        db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.id.in_(target_ids))
            .values(concept_id=concept_id)
        )
        changed += len(target_ids)
    return len(chunk_mapping), changed, overview_mapped


def _ensure_overview_concepts(
    db: Session,
    course: Course,
    records: list[LocalDocumentRecord],
    concepts_by_repo: dict[str, CourseConcept],
    sections_by_repo: dict[str, CourseSection],
    existing_sections: list[CourseSection],
    order_index: int,
) -> tuple[dict[str, CourseConcept], int]:
    """为没有目录知识点的仓库创建资料总览知识点。"""
    overview_by_repo = dict(concepts_by_repo)
    for repo in sorted({record.repo for record in records}):
        if repo in overview_by_repo:
            continue
        repo_key = next(record.repo_key for record in records if record.repo == repo)
        section = sections_by_repo.get(repo)
        if section is None:
            section = _ensure_local_section(db, course, repo, repo_key, concepts_by_repo, existing_sections)
            sections_by_repo[repo] = section
        group = {
            "key": f"overview:{repo}",
            "title": f"{repo.rsplit('/', 1)[-1]} 资料总览",
            "difficulty": "basic",
            "match_value": repo,
        }
        overview_by_repo[repo] = _ensure_concept(db, course, section, repo, repo_key, group, order_index)
        order_index += 1
    return overview_by_repo, order_index


def _sync_course(db: Session, course: Course, dry_run: bool, rebuild_paths: bool) -> dict:
    """同步单门课程的本地语料知识点和切片关联。"""
    records = _load_records(db, course)
    existing_concepts = _existing_concepts(db, course)
    specs = [spec for record in records for spec in _specs_for_document(record)]
    groups = _group_specs(records, specs, existing_concepts)
    concepts_by_repo = {
        repo: concept
        for repo in {record.repo for record in records}
        for concept in existing_concepts
        if (concept.meta_json or {}).get("repo") == repo
    }
    existing_sections = list(
        db.execute(select(CourseSection).where(CourseSection.course_id == course.id)).scalars().all()
    )

    summary = {
        "course": course.slug,
        "documents": len(records),
        "chunks": sum(len(record.chunks) for record in records),
        "candidates": len(groups),
        "groups": [
            {
                "title": group["title"],
                "repo": group["repo"],
                "documents": len(group["source_document_ids"]),
                "match_kind": group["match_kind"],
            }
            for group in groups
        ],
    }
    if dry_run:
        return summary

    max_order = max((concept.recommended_order or 0 for concept in existing_concepts), default=0)
    order_index = max_order + 1
    active_codes: set[str] = set()
    concept_by_group: dict[str, CourseConcept] = {}
    previous_by_repo: dict[str, CourseConcept] = {}
    sections_by_repo: dict[str, CourseSection] = {}

    for group in groups:
        repo = group["repo"]
        section = sections_by_repo.get(repo)
        if section is None:
            section = _ensure_local_section(db, course, repo, group["repo_key"], concepts_by_repo, existing_sections)
            sections_by_repo[repo] = section
        concept = _ensure_concept(db, course, section, repo, group["repo_key"], group, order_index)
        previous = previous_by_repo.get(repo)
        _sync_prerequisites(db, course, concept, previous, concepts_by_repo.get(repo))
        concept_by_group[group["key"]] = concept
        previous_by_repo[repo] = concept
        active_codes.add(concept.code)
        order_index += 1

    overview_by_repo, order_index = _ensure_overview_concepts(
        db,
        course,
        records,
        concepts_by_repo,
        sections_by_repo,
        existing_sections,
        order_index,
    )
    active_codes.update(concept.code for concept in overview_by_repo.values())
    linked_count, changed_chunks, overview_mapped = _sync_chunks(
        db,
        records,
        groups,
        concept_by_group,
        overview_by_repo,
    )
    archived = _archive_stale_generated_concepts(db, course, active_codes)
    if rebuild_paths:
        stale_paths = db.execute(
            select(LearningPath).where(
                LearningPath.course_id == course.id,
                LearningPath.status == "active",
            )
        ).scalars().all()
        for path in stale_paths:
            path.status = "archived"
    db.commit()

    if rebuild_paths:
        admin = db.execute(select(User).where(User.role_code == "admin").order_by(User.created_at)).scalars().first()
        if admin is not None:
            LearningRepository(db).generate_path(course.slug, admin.external_id)

    summary.update(
        {
            "linked_chunks": linked_count,
            "changed_chunks": changed_chunks,
            "overview_mapped_chunks": overview_mapped,
            "archived_stale_concepts": archived,
        }
    )
    return summary


def _load_courses(db: Session, selected: set[str]) -> list[Course]:
    """选择需要同步的课程，默认仅处理本地语料覆盖的课程主线。"""
    local_course_slugs = {
        "ai_ml",
        "algorithms",
        "cs_foundations",
        "data_system",
        "llm_agents",
        "supplement",
        "web_engineering",
    }
    query = select(Course).where(Course.slug.in_(selected or local_course_slugs)).order_by(Course.slug)
    return list(db.execute(query).scalars().all())


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步本地知识库文档到课程知识点并关联切片。")
    parser.add_argument("--courses", nargs="*", default=[], help="仅同步指定课程 slug。")
    parser.add_argument("--dry-run", action="store_true", help="只统计候选主题，不写数据库。")
    parser.add_argument("--rebuild-paths", action="store_true", help="同步后为管理员重建学习路径。")
    return parser.parse_args()


def main() -> int:
    """执行同步流程并输出汇总。"""
    _reconfigure_stdout()
    args = _build_args()
    db = SessionLocal()
    try:
        courses = _load_courses(db, set(args.courses))
        if not courses:
            print("没有找到需要同步的本地知识库课程。")
            return 1
        results = []
        for course in courses:
            result = _sync_course(db, course, dry_run=args.dry_run, rebuild_paths=args.rebuild_paths)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.dry_run:
            print(
                "同步完成：课程 "
                + ", ".join(f"{item['course']}={item['candidates']}" for item in results)
                + "。"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())