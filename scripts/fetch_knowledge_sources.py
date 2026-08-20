"""按课程体系抓取 GitHub 开放许可 Markdown 资料，生成知识库原始语料清单，并支持本地重建。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "storage" / "knowledge-sources"
CATALOG = ROOT / "frontend" / "src" / "data" / "curriculumCatalog.json"
MANIFEST = TARGET_DIR / "manifest.json"
GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
USER_AGENT = "zhike-workshop-kb-fetcher/1.0"

# 每门课优先抓取、且许可证允许文本入库的资料；其余目录仅记录外链。
PRIORITY_REPOS = {
    "cs-foundations": [
        "PKUFlyingPig/cs-self-learning",
        "missing-semester-cn/missing-semester-cn",
        "izackwu/TeachYourselfCS-CN",
        "mtdvio/every-programmer-should-know",
    ],
    "algorithms": [
        "TheAlgorithms/Python",
        "kamyu104/LeetCode-Solutions",
        "jwasham/coding-interview-university",
    ],
    "web-engineering": [
        "bradtraversy/50projects50days",
        "lydiahallie/javascript-questions",
    ],
    "data-system": [
        "donnemartin/system-design-primer",
        "study8677/awesome-architecture",
    ],
    "ai-ml": [
        "microsoft/ML-For-Beginners",
        "microsoft/AI-For-Beginners",
        "microsoft/Data-Science-For-Beginners",
        "trekhleb/homemade-machine-learning",
        "unclestrong/DeepLearning_LHY21_Notes",
    ],
    "llm-agents": [
        "microsoft/Generative-AI-For-Beginners",
        "dair-ai/Prompt-Engineering-Guide",
        "mlabonne/llm-course",
        "huggingface/agents-course",
        "openai/openai-cookbook",
    ],
    "supplement": [
        "practical-tutorials/project-based-learning",
        "dair-ai/ML-YouTube-Courses",
    ],
}

MAX_FILES_PER_REPO = 120
MAX_FILE_BYTES = 3_000_000
SKIP_DIR_PARTS = {".github", "images", "img", "assets", "node_modules", "dist", ".git"}


def github_json(url: str) -> dict:
    """请求 GitHub API 并解析 JSON。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def default_branch(repo: str) -> str:
    """获取仓库默认分支。"""
    payload = github_json(f"{GITHUB_API}/repos/{repo}")
    return payload.get("default_branch") or "main"


def markdown_files(repo: str, branch: str) -> list[str]:
    """获取仓库内 Markdown 文件路径，按层级优先并限制数量。"""
    tree = github_json(f"{GITHUB_API}/repos/{repo}/git/trees/{branch}?recursive=1")
    paths: list[str] = []
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if not (path.endswith(".md") or path.endswith(".mdx")):
            continue
        parts = path.split("/")
        if any(part.lower() in SKIP_DIR_PARTS for part in parts[:-1]):
            continue
        if any(part in {".", ".."} for part in parts):
            continue
        paths.append(path)
    paths.sort(key=lambda item: (item.count("/"), item.lower()))
    return paths[:MAX_FILES_PER_REPO]


def fetch_file(repo: str, branch: str, path: str, destination: Path) -> dict | None:
    """抓取单个 Raw 文件并返回清单元数据；超限或失败时返回 None。"""
    quoted_path = urllib.parse.quote(path, safe="/")
    url = f"{RAW_BASE}/{repo}/{branch}/{quoted_path}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
    if len(content) > MAX_FILE_BYTES:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "sizeBytes": len(content),
        "mimeType": "text/markdown",
    }


def local_file_metadata(path: Path) -> dict:
    """读取本地 Markdown 文件并生成稳定的清单元数据。"""
    content = path.read_bytes()
    return {
        "path": path.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "sizeBytes": len(content),
        "mimeType": "text/markdown",
    }


def local_markdown_files(directory: Path) -> list[Path]:
    """扫描目录下 Markdown/MDX 文件，并按仓库相对路径排序。"""
    if not directory.exists():
        return []
    return sorted(
        (
            item
            for item in directory.rglob("*")
            if item.is_file() and item.suffix.lower() in {".md", ".mdx"}
        ),
        key=lambda item: (str(item.relative_to(directory)).count("/"), item.name.lower()),
    )


def license_for_repo(metadata: dict[str, list[dict]], repo: str) -> str:
    """从课程目录元数据中解析仓库许可证，缺失时使用 NOASSERTION。"""
    for resources in metadata.values():
        for resource in resources:
            if resource.get("repo") == repo:
                return resource.get("license") or "NOASSERTION"
    return "NOASSERTION"


def repo_directory(target_dir: Path, repo: str) -> Path:
    """返回仓库在课程方向目录中的本地存储目录。"""
    return target_dir / repo.split("/")[-1]


def inventory_source(target_dir: Path, source: dict, license_value: str | None = None) -> dict:
    """从本地磁盘重建单个来源的文件元数据。"""
    directory = repo_directory(target_dir, source["repo"])
    file_items = []
    for path in local_markdown_files(directory):
        item = local_file_metadata(path)
        item["path"] = path.relative_to(directory).as_posix()
        file_items.append(item)
    return {
        "repo": source["repo"],
        "branch": source.get("branch") or "main",
        "license": license_value or "NOASSERTION",
        "fileCount": len(file_items),
        "files": file_items,
        "errors": list(source.get("errors") or []),
        "source": "local_disk",
    }


def load_catalog_metadata() -> dict[str, list[dict]]:
    """读取课程目录中的资源元数据，按 track_id 分组。"""
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for track in payload.get("tracks", []):
        resources = []
        for stage in track.get("stages", []):
            resources.extend(stage.get("resources", []))
        grouped[track["id"]] = resources
    return grouped


def rebuild_from_disk(existing: dict, metadata: dict[str, list[dict]]) -> dict:
    """使用本地文件重建清单，并保留既有来源和抓取错误信息。"""
    manifest: dict = {
        "schemaVersion": "1.1",
        "updatedAt": "2026-08-18",
        "targetDir": str(TARGET_DIR.relative_to(ROOT)),
        "tracks": {},
    }
    for track_id in PRIORITY_REPOS:
        track_payload = existing.get("tracks", {}).get(track_id, {})
        sources = []
        existing_by_repo = {
            source.get("repo"): source
            for source in track_payload.get("sources", [])
            if source.get("repo")
        }
        for repo in PRIORITY_REPOS[track_id]:
            source = existing_by_repo.get(repo, {"repo": repo})
            sources.append(
                inventory_source(
                    TARGET_DIR / track_id,
                    source,
                    license_for_repo(metadata, source["repo"]),
                )
            )
        manifest["tracks"][track_id] = {
            "catalogResources": track_payload.get("catalogResources")
            or metadata.get(track_id, []),
            "sources": sources,
        }
    return manifest


def fetch_track(
    track_id: str,
    repos: list[str],
    metadata: dict[str, list[dict]],
    *,
    missing_only: bool,
    dry_run: bool,
) -> list[dict]:
    """抓取单个课程方向的仓库语料并返回清单条目。"""
    track_dir = TARGET_DIR / track_id
    entries: list[dict] = []
    for repo in repos:
        try:
            branch = default_branch(repo)
            candidate_files = markdown_files(repo, branch)
            remote_files = set(candidate_files)
            local_files = local_markdown_files(repo_directory(track_dir, repo))
            if missing_only:
                local_names = {item.name for item in local_files}
                candidate_files = [
                    item
                    for item in candidate_files
                    if item.split("/")[-1] not in local_names
                    or not (repo_directory(track_dir, repo) / Path(*item.split("/"))).exists()
                ]
            fetched: list[dict] = []
            errors: list[str] = []
            for relative_path in candidate_files:
                local_path = repo_directory(track_dir, repo) / Path(*relative_path.split("/"))
                if dry_run:
                    continue
                try:
                    item = fetch_file(repo, branch, relative_path, local_path)
                    if item:
                        fetched.append(item)
                except Exception as exc:  # noqa: BLE001 - 单文件失败不中断整批抓取
                    errors.append(f"{relative_path}: {exc}")
                time.sleep(0.1)
            if missing_only and not fetched:
                fetched = []
                for path in local_files:
                    item = local_file_metadata(path)
                    item["path"] = path.relative_to(repo_directory(track_dir, repo)).as_posix()
                    fetched.append(item)
            entries.append(
                {
                    "repo": repo,
                    "branch": branch,
                    "license": license_for_repo(metadata, repo),
                    "fileCount": len(fetched),
                    "files": fetched,
                    "errors": errors[:10],
                    "remoteFileCount": len(remote_files),
                    "source": "github" if not dry_run else "github_dry_run",
                }
            )
            print(f"[{track_id}] {repo}: {len(fetched)} 个 Markdown 文件")
        except Exception as exc:  # noqa: BLE001 - 仓库失败也不中断整批抓取
            entries.append({"repo": repo, "error": str(exc), "source": "github"})
            print(f"[{track_id}] {repo}: 失败 - {exc}", file=sys.stderr)
        time.sleep(0.2)
    return entries


def build_args() -> argparse.Namespace:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="抓取或重建开源课程 Markdown 语料清单。")
    parser.add_argument("--from-disk", action="store_true", help="只扫描本地文件，不访问 GitHub。")
    parser.add_argument("--missing-only", action="store_true", help="仅抓取本地缺失文件。")
    parser.add_argument("--dry-run", action="store_true", help="只计算远端文件列表，不写入文件。")
    parser.add_argument("--tracks", nargs="*", default=[], help="仅处理指定课程方向。")
    parser.add_argument("--repos", nargs="*", default=[], help="仅处理指定仓库，格式为 owner/repo。")
    return parser.parse_args()


def main() -> int:
    """执行抓取或本地重建，并写出 manifest.json。"""
    args = build_args()
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    metadata = load_catalog_metadata()

    if args.from_disk:
        existing_manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
        manifest = rebuild_from_disk(existing_manifest, metadata)
    else:
        selected_tracks = set(args.tracks or PRIORITY_REPOS)
        selected_repos = set(args.repos)
        manifest: dict = {
            "schemaVersion": "1.1",
            "updatedAt": "2026-08-18",
            "targetDir": str(TARGET_DIR.relative_to(ROOT)),
            "tracks": {},
        }
        for track_id, repos in PRIORITY_REPOS.items():
            if track_id not in selected_tracks:
                continue
            repos = [repo for repo in repos if not selected_repos or repo in selected_repos]
            if not repos:
                continue
            manifest["tracks"][track_id] = {
                "catalogResources": metadata.get(track_id, []),
                "sources": fetch_track(
                    track_id,
                    repos,
                    metadata,
                    missing_only=args.missing_only,
                    dry_run=args.dry_run,
                ),
            }

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"清单已写入 {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
