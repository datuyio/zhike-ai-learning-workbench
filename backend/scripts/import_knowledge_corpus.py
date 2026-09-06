"""把开源课程 Markdown 语料批量导入本地 pgvector 知识库。

脚本读取 ``storage/knowledge-sources/manifest.json``，按课程主线映射到已同步的课程，
调用本地解析、向量化与入库服务。每次运行都按文件内容哈希幂等去重，默认跳过许可证
不明确的内容，避免把不可再分发语料直接托管到知识库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Course, Document, User
from app.services.knowledge.local_knowledge import LocalKnowledgeError, LocalKnowledgeService, parse_markdown


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "storage" / "knowledge-sources" / "manifest.json"
SKIPPED_LICENSES = {"", "NOASSERTION", "未声明", "UNLICENSED"}


def _slugify(value: str) -> str:
    """把课程主线标识转换为数据库课程 slug。"""
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return token[:100]


def _course_slug(track_id: str) -> str:
    return _slugify(track_id)


def _repo_dir(repo: str) -> str:
    return repo.split("/")[-1]


def _load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _iter_files(manifest: dict) -> list[dict]:
    """展开清单元数据，兼容旧的字符串文件列表格式。"""
    rows: list[dict] = []
    for track_id, track_payload in manifest.get("tracks", {}).items():
        for source in track_payload.get("sources", []):
            if source.get("error"):
                continue
            for raw_file in source.get("files", []):
                if isinstance(raw_file, str):
                    raw_file = {"path": raw_file}
                rows.append(
                    {
                        "track_id": track_id,
                        "course_slug": _course_slug(track_id),
                        "repo": source.get("repo") or "",
                        "branch": source.get("branch") or "main",
                        "license": source.get("license") or "NOASSERTION",
                        "source_type": source.get("source") or "manifest",
                        **raw_file,
                    }
                )
    return rows


def _local_path(row: dict) -> Path:
    target_dir = MANIFEST_PATH.parent
    return (
        target_dir
        / row["track_id"]
        / _repo_dir(row["repo"])
        / Path(*row["path"].split("/"))
    )


def _admin_user(db) -> User:
    """查找管理用户作为批量导入操作者。"""
    user = db.execute(select(User).where(User.role_code == "admin").order_by(User.created_at)).scalars().first()
    if user is None:
        raise RuntimeError("未找到管理员用户，无法记录批量导入操作者。")
    return user


def _source_meta(row: dict, path: Path) -> dict:
    return {
        "manifest_schema": "1.1",
        "track_id": row["track_id"],
        "repo": row["repo"],
        "branch": row["branch"],
        "license": row["license"],
        "relative_path": row["path"],
        "local_path": str(path.resolve()),
        "sha256": row.get("sha256"),
        "size_bytes": row.get("sizeBytes"),
        "fetched_from": row.get("source_type"),
    }


def _ensure_course(db, course_slug: str) -> Course:
    course = db.execute(select(Course).where(Course.slug == course_slug)).scalar_one_or_none()
    if course is None:
        raise RuntimeError(f"课程尚未同步，请先运行 seed_curriculum_catalog.py：{course_slug}")
    return course


def _allowed_license(license_value: str, include_unlicensed: bool) -> bool:
    return include_unlicensed or license_value.strip() not in SKIPPED_LICENSES


def _is_empty_markdown_error(exc: LocalKnowledgeError) -> bool:
    return "Markdown 未提取到可检索文本" in str(exc)


def _document_exists(db, course: Course, content_hash: str) -> bool:
    document = db.execute(
        select(Document).where(
            Document.course_id == course.id,
            Document.content_hash == content_hash,
            Document.source_type == "local_pgvector",
            Document.deleted_at.is_(None),
        )
    ).scalars().first()
    return document is not None


def _run(
    *,
    dry_run: bool,
    include_unlicensed: bool,
    limit: int | None,
    tracks: set[str],
    repos: set[str],
    offset: int,
) -> dict:
    manifest = _load_manifest()
    rows = _iter_files(manifest)
    if tracks:
        rows = [row for row in rows if row["track_id"] in tracks]
    if repos:
        rows = [row for row in rows if row["repo"] in repos]
    rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]

    db = SessionLocal()
    admin = _admin_user(db)
    service = LocalKnowledgeService(db)
    summary = {
        "total": len(rows),
        "imported": 0,
        "duplicates": 0,
        "skipped_license": 0,
        "skipped_empty": 0,
        "missing": 0,
        "failed": 0,
        "chunks": 0,
        "failures": [],
    }

    try:
        for index, row in enumerate(rows, start=1):
            course = _ensure_course(db, row["course_slug"])
            if not _allowed_license(row["license"], include_unlicensed):
                summary["skipped_license"] += 1
                continue

            path = _local_path(row)
            if not path.is_file():
                summary["missing"] += 1
                summary["failures"].append({"path": row["path"], "error": "missing"})
                continue

            content = path.read_bytes()
            # manifest 哈希基于 GitHub 原始字节生成；本地 core.autocrlf=true 会把检出文本转成
            # CRLF，但被 git 判定为二进制（或未标记文本）的文件保持不变。因此这里同时用
            # 原始字节与规范化 LF 内容做双候选匹配，取能命中 manifest 哈希的内容入库。
            normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            content_hash = hashlib.sha256(content).hexdigest()
            if content_hash == row.get("sha256"):
                ingest_content = content
            else:
                content_hash = hashlib.sha256(normalized).hexdigest()
                if content_hash == row.get("sha256"):
                    ingest_content = normalized
                else:
                    summary["failed"] += 1
                    summary["failures"].append({"path": row["path"], "error": "hash_mismatch"})
                    continue

            if not dry_run and _document_exists(db, course, content_hash):
                summary["duplicates"] += 1
                continue

            if dry_run:
                try:
                    chunks = parse_markdown(ingest_content)
                except LocalKnowledgeError as exc:
                    if _is_empty_markdown_error(exc):
                        summary["skipped_empty"] += 1
                    else:
                        summary["failed"] += 1
                        summary["failures"].append({"path": row["path"], "error": str(exc)})
                    continue
                summary["imported"] += 1
                summary["chunks"] += len(chunks)
                continue

            try:
                result = service.ingest(
                    course.slug,
                    row["path"],
                    "text/markdown",
                    ingest_content,
                    str(admin.id),
                    source_meta_json=_source_meta(row, path),
                    source_path=str(path),
                )
            except LocalKnowledgeError as exc:
                db.rollback()
                if "文档已存在" in str(exc):
                    summary["duplicates"] += 1
                elif _is_empty_markdown_error(exc):
                    summary["skipped_empty"] += 1
                else:
                    summary["failed"] += 1
                    summary["failures"].append({"path": row["path"], "error": str(exc)})
                    print(f"[{index}/{len(rows)}] 失败：{row['path']} - {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - 单文件失败不中断整批任务
                db.rollback()
                summary["failed"] += 1
                summary["failures"].append({"path": row["path"], "error": str(exc)})
                print(f"[{index}/{len(rows)}] 失败：{row['path']} - {exc}")
                continue

            summary["imported"] += 1
            summary["chunks"] += int(result.get("chunk_count") or 0)
            if index % 20 == 0 or index == len(rows):
                print(
                    f"进度 {index}/{len(rows)}，已导入 {summary['imported']} 份，"
                    f"切片 {summary['chunks']} 个，失败 {summary['failed']} 份。"
                )
    finally:
        db.close()
    return summary


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量导入开源课程 Markdown 语料到本地知识库。")
    parser.add_argument("--dry-run", action="store_true", help="只解析和统计，不写数据库。")
    parser.add_argument("--include-unlicensed", action="store_true", help="允许导入 NOASSERTION/未声明许可内容。")
    parser.add_argument("--tracks", nargs="*", default=[], help="仅处理指定课程主线。")
    parser.add_argument("--repos", nargs="*", default=[], help="仅处理指定仓库，格式为 owner/repo。")
    parser.add_argument("--limit", type=int, default=None, help="最多处理文件数，用于验证。")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 个文件，用于断点重跑。")
    return parser.parse_args()


def main() -> int:
    args = _build_args()
    summary = _run(
        dry_run=args.dry_run,
        include_unlicensed=args.include_unlicensed,
        limit=args.limit,
        tracks=set(args.tracks),
        repos=set(args.repos),
        offset=args.offset,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
