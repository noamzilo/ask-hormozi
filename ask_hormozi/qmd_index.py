from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .captions import format_timestamp, parse_frontmatter

_QUESTION_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "alex",
    "are",
    "be",
    "been",
    "being",
    "brand",
    "brands",
    "can",
    "could",
    "did",
    "do",
    "does",
    "ecom",
    "ecommerce",
    "hormozi",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "how",
    "i",
    "improve",
    "in",
    "is",
    "it",
    "may",
    "might",
    "my",
    "moremozi",
    "must",
    "of",
    "on",
    "or",
    "recommend",
    "recommends",
    "s",
    "say",
    "says",
    "should",
    "take",
    "tell",
    "the",
    "think",
    "thinks",
    "to",
    "use",
    "uses",
    "using",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def _qmd_index_path() -> Path:
    path = Path.home() / ".local" / "share" / "ask-hormozi" / "index.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _qmd(*args: str) -> list[str]:
    return ["qmd", "--index", str(_qmd_index_path()), *args]


def index_corpus(
    data_dir: Path, *, collection: str = "ask-hormozi"
) -> None:
    _require_qmd()
    data_dir = data_dir.expanduser().resolve()
    segment_root = data_dir / "segments"
    episode_root = data_dir / "episodes"
    has_segments = any(segment_root.glob("*/*.md"))
    has_episodes = any(episode_root.glob("*.md"))
    if not has_segments and not has_episodes:
        raise RuntimeError(
            f"No bundled Markdown corpus found under {data_dir}."
        )
    mask = "segments/**/*.md" if has_segments else "episodes/*.md"

    listing = _run(_qmd("collection", "list")).stdout
    if re.search(rf"^{re.escape(collection)}\s", listing, re.MULTILINE):
        _run(_qmd("collection", "remove", collection))
    _run(
        _qmd(
            "collection",
            "add",
            str(data_dir),
            "--name",
            collection,
            "--pattern",
            mask,
        )
    )
    _run(_qmd("update"))
    _run(
        _qmd(
            "context",
            "add",
            collection,
            "/",
            (
                "Timestamped transcripts from MoreMozi. "
                "Use passages as attributed source material and cite each "
                "video's timestamp_url."
            ),
        ),
        check=False,
    )


def search_corpus(
    query: str,
    *,
    data_dir: Path,
    collection: str = "ask-hormozi",
    limit: int = 8,
) -> list[dict[str, Any]]:
    _require_qmd()
    query_candidates = _bm25_query_candidates(query)
    if not query_candidates:
        raise RuntimeError("The search query has no searchable words.")
    raw_limit = max(limit * 5, 25)
    aggregated: dict[str, dict[str, Any]] = {}
    for candidate_index, search_query in enumerate(query_candidates):
        completed = _run(
            _qmd(
                "fts",
                search_query,
                "--limit",
                str(raw_limit),
                "--json",
            )
        )
        payload = json.loads(completed.stdout)
        raw_results = (
            payload.get("results", []) if isinstance(payload, dict) else payload
        )
        for result_rank, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                continue
            item = _flatten_hit(item)
            if item.get("collection") not in (None, "", collection):
                continue
            qmd_path = str(
                item.get("path")
                or item.get("file")
                or item.get("url")
                or item.get("document")
                or ""
            )
            if not qmd_path:
                continue
            aggregate = aggregated.setdefault(
                qmd_path,
                {
                    "item": item,
                    "search_hits": 0,
                    "exact_candidate": False,
                    "rrf_score": 0.0,
                },
            )
            aggregate["search_hits"] += 1
            aggregate["exact_candidate"] = (
                aggregate["exact_candidate"] or candidate_index == 0
            )
            aggregate["rrf_score"] += 1 / (60 + result_rank)

    enriched: list[dict[str, Any]] = []
    for aggregate in aggregated.values():
        result = _enrich_result(aggregate["item"], data_dir=data_dir)
        if result is None:
            continue
        result["_search_hits"] = aggregate["search_hits"]
        result["_exact_candidate"] = aggregate["exact_candidate"]
        result["_rrf_score"] = aggregate["rrf_score"]
        enriched.append(result)

    ranked = _rank_search_results(enriched, query=query)
    selected = _select_diverse_results(ranked, limit=limit)
    return [
        {
            key: value
            for key, value in result.items()
            if not key.startswith("_")
        }
        for result in selected
    ]


def render_markdown_results(
    query: str, results: list[dict[str, Any]]
) -> str:
    if not results:
        return f"No indexed Alex Hormozi passages matched: {query}\n"

    lines = [f"# Alex Hormozi sources for: {query}", ""]
    for index, result in enumerate(results, start=1):
        timestamp = format_timestamp(int(result["start_seconds"]))
        lines.extend(
            [
                f"## {index}. {result['title']} — {timestamp}",
                "",
                result["context"],
                "",
                f"Source: [{result['title']} at {timestamp}]"
                f"({result['citation_url']})",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _flatten_hit(item: dict[str, Any]) -> dict[str, Any]:
    doc = item.get("doc")
    if not isinstance(doc, dict):
        return item
    merged = dict(doc)
    merged.update({k: v for k, v in item.items() if k != "doc"})
    return merged


def _enrich_result(
    item: Any, *, data_dir: Path
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    qmd_path = str(
        item.get("path")
        or item.get("file")
        or item.get("url")
        or item.get("document")
        or ""
    )
    match = re.search(
        r"(?:^|/)segments/([^/]+)/(\d{6})(?:\.md|-md)(?:$|[:#])",
        qmd_path,
    )
    if not match:
        return _enrich_catalog_result(item, data_dir=data_dir, qmd_path=qmd_path)

    episode_id, start_token = match.groups()
    segment_root = data_dir.expanduser().resolve() / "segments"
    segment_path = segment_root / episode_id / f"{start_token}.md"
    if not segment_path.exists() and segment_root.exists():
        matching_directories = [
            path
            for path in segment_root.iterdir()
            if path.is_dir()
            and _qmd_token_matches(path.name, episode_id)
        ]
        if matching_directories:
            segment_path = matching_directories[0] / f"{start_token}.md"
    if not segment_path.exists():
        return None
    content = segment_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(content)
    body = content.split("\n---\n", 1)[-1].strip()
    context = body.split("\n\nSource:", 1)[0].strip()
    context_lines = context.splitlines()
    if context_lines and context_lines[0].startswith("# "):
        context = "\n".join(context_lines[1:]).strip()
    if not _has_substantive_context(context):
        return None
    score = item.get("score")
    return {
        "title": metadata.get("title") or episode_id,
        "episode_id": metadata.get("episode_id") or episode_id,
        "published": metadata.get("published") or "",
        "start_seconds": int(metadata.get("start_seconds") or start_token),
        "end_seconds": int(metadata.get("end_seconds") or start_token),
        "context": context,
        "episode_url": metadata.get("episode_url")
        or f"https://www.youtube.com/watch?v={episode_id}",
        "citation_url": metadata.get("timestamp_url")
        or (
            f"https://www.youtube.com/watch?v={episode_id}"
            f"&t={int(start_token)}s"
        ),
        "transcript_source": metadata.get("transcript_source") or "",
        "score": score,
        "qmd_path": qmd_path,
    }


def _enrich_catalog_result(
    item: dict[str, Any], *, data_dir: Path, qmd_path: str
) -> dict[str, Any] | None:
    match = re.search(
        r"(?:^|/)episodes/([^/]+?)(?:\.md|-md)(?:$|[:#])",
        qmd_path,
    )
    if not match:
        return None
    episode_token = match.group(1)
    episode_path = data_dir.expanduser().resolve() / "episodes" / (
        f"{episode_token}.md"
    )
    if not episode_path.exists():
        matching_files = [
            path
            for path in (data_dir.expanduser().resolve() / "episodes").glob("*.md")
            if _qmd_token_matches(path.stem, episode_token)
        ]
        if not matching_files:
            return None
        episode_path = matching_files[0]
    metadata = parse_frontmatter(episode_path.read_text(encoding="utf-8"))
    episode_id = str(metadata.get("episode_id") or episode_token)
    title = str(metadata.get("title") or episode_id)
    episode_url = str(
        metadata.get("episode_url")
        or f"https://www.youtube.com/watch?v={episode_id}"
    )
    return {
        "title": title,
        "episode_id": episode_id,
        "published": "",
        "start_seconds": 0,
        "end_seconds": 0,
        "context": (
            f"Catalog entry for {title}. No authorized transcript passage "
            "is bundled for this video."
        ),
        "episode_url": episode_url,
        "citation_url": episode_url,
        "transcript_source": "youtube_catalog",
        "score": item.get("score"),
        "qmd_path": qmd_path,
    }


def _sanitize_bm25_query(query: str) -> str:
    words_only = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
    words = re.sub(r"\s+", " ", words_only).strip().split()
    meaningful = [
        word for word in words if word.lower() not in _QUESTION_STOPWORDS
    ]
    return " ".join(meaningful or words)


def _bm25_query_candidates(query: str) -> list[str]:
    sanitized = _sanitize_bm25_query(query)
    words = sanitized.split()
    if not words:
        return []

    candidates = [sanitized]
    for size in (3, 2):
        if len(words) <= size:
            continue
        starts = (0, len(words) - size, (len(words) - size) // 2)
        for start in starts:
            candidate = " ".join(words[start : start + size])
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _has_substantive_context(context: str) -> bool:
    without_stage_directions = re.sub(r"\[[^\]]+\]", " ", context)
    words = re.findall(r"\w+", without_stage_directions, flags=re.UNICODE)
    return len(words) >= 12 and len(" ".join(words)) >= 80


def _qmd_token_matches(local_name: str, qmd_token: str) -> bool:
    return local_name.lower().replace("_", "-") == qmd_token.lower()


def _select_diverse_results(
    results: list[dict[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for result in results:
        episode_id = str(result.get("episode_id") or "")
        if counts.get(episode_id, 0) >= 2:
            continue
        selected.append(result)
        counts[episode_id] = counts.get(episode_id, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def _rank_search_results(
    results: list[dict[str, Any]], *, query: str
) -> list[dict[str, Any]]:
    query_terms = {
        term.lower() for term in _sanitize_bm25_query(query).split()
    }

    def match_count(text: str) -> int:
        text_terms = {
            term.lower()
            for term in re.findall(r"\w+", text, flags=re.UNICODE)
        }
        return sum(
            any(
                candidate == term
                or (
                    len(term) >= 5
                    and len(candidate) >= 5
                    and candidate[:4] == term[:4]
                )
                for candidate in text_terms
            )
            for term in query_terms
        )

    def rank_key(result: dict[str, Any]) -> tuple[Any, ...]:
        raw_score = result.get("score")
        return (
            bool(result.get("_exact_candidate")),
            int(result.get("_search_hits") or 0),
            match_count(str(result.get("title") or "")),
            match_count(str(result.get("context") or "")),
            float(result.get("_rrf_score") or 0),
            float(raw_score) if isinstance(raw_score, (int, float)) else 0.0,
        )

    return sorted(results, key=rank_key, reverse=True)


def _require_qmd() -> None:
    if shutil.which("qmd") is None:
        raise RuntimeError(
            "qmd is required but was not found on PATH. Run ./setup.sh or "
            "install it from https://github.com/qntx-labs/qmd."
        )


def _run(
    command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"{' '.join(command[:2])} failed: {detail or 'unknown error'}"
        )
    return completed
