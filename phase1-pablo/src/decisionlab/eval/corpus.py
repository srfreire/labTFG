"""PDF-only eval corpus adapters for web and paper search tools.

The expert-eval flow needs the pipeline to behave as if the outside world
contains only a fixed bundle of papers. This module builds a small local
corpus from one or more zip archives and exposes it through the same ports
the agents already use:

- ``web_search`` receives web-like title/url/snippet results.
- ``search_papers`` receives academic-paper-like records plus document text.

Normal production search is untouched; callers opt into this provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from decisionlab.domain.models import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_ROOT = Path("evals/corpus")
_DEFAULT_WEB_RESULTS = 10
_DEFAULT_PAPER_RESULTS = 1
_MAX_PAPER_RESULTS = 25
_DEFAULT_TEXT_CHARS = 20_000
_CACHE_VERSION = b"eval-corpus-v3"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9À-ÿ]{3,}")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass(frozen=True)
class CorpusPaper:
    """One PDF and its extracted text inside an eval corpus."""

    id: str
    title: str
    filename: str
    source_archive: str
    url: str
    pdf_path: str
    text_path: str
    snippet: str
    year: int | None = None
    doi: str | None = None
    authors: tuple[str, ...] = ()


class EvalPaperCorpus:
    """Searchable corpus loaded from zipped PDFs."""

    def __init__(self, papers: Iterable[CorpusPaper], *, root: Path) -> None:
        self.papers = tuple(papers)
        self.root = root
        if not self.papers:
            raise ValueError("EvalPaperCorpus requires at least one PDF")

    @classmethod
    def from_archives(
        cls,
        archives: Iterable[Path | str],
        *,
        cache_root: Path = _DEFAULT_CACHE_ROOT,
    ) -> EvalPaperCorpus:
        archive_paths = tuple(Path(p).expanduser().resolve() for p in archives)
        if not archive_paths:
            raise ValueError("from_archives requires at least one zip path")
        for path in archive_paths:
            if not path.exists():
                raise FileNotFoundError(f"eval corpus archive not found: {path}")
            if path.suffix.lower() != ".zip":
                raise ValueError(f"eval corpus archive must be a .zip file: {path}")

        digest = _archives_digest(archive_paths)
        root = cache_root.expanduser().resolve() / digest[:16]
        manifest = root / "manifest.json"
        if manifest.exists():
            try:
                return cls._from_manifest(manifest)
            except Exception:
                logger.warning("Eval corpus cache unreadable, rebuilding: %s", root)
                shutil.rmtree(root, ignore_errors=True)

        root.mkdir(parents=True, exist_ok=True)
        pdf_dir = root / "pdfs"
        text_dir = root / "texts"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)

        papers: list[CorpusPaper] = []
        seen_filenames: set[str] = set()
        for archive in archive_paths:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                        continue
                    source_name = Path(info.filename).name
                    filename = _dedupe_filename(source_name, seen_filenames)
                    pdf_path = pdf_dir / filename
                    pdf_path.write_bytes(zf.read(info))
                    text = _clean_text(_extract_pdf_text(pdf_path))
                    text_path = text_dir / f"{Path(filename).stem}.txt"
                    text_path.write_text(text, encoding="utf-8")
                    paper = _paper_from_paths(
                        pdf_path=pdf_path,
                        text_path=text_path,
                        source_archive=archive.name,
                        corpus_root=root,
                    )
                    papers.append(paper)

        payload = {
            "root": str(root),
            "archives": [str(p) for p in archive_paths],
            "papers": [asdict(p) for p in papers],
        }
        manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return cls(papers, root=root)

    @classmethod
    def _from_manifest(cls, manifest: Path) -> EvalPaperCorpus:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        papers = []
        for item in payload.get("papers") or []:
            item = dict(item)
            item["authors"] = tuple(item.get("authors") or ())
            papers.append(CorpusPaper(**item))
        return cls(papers, root=Path(payload["root"]))

    def web_search(self, *, max_results: int = _DEFAULT_WEB_RESULTS) -> CorpusWebSearch:
        return CorpusWebSearch(self, max_results=max_results)

    def create_search_papers(
        self,
        *,
        max_chars_per_paper: int | None = None,
    ) -> Callable[[dict], Awaitable[str]]:
        """Return a ``search_papers`` handler backed by this corpus."""

        if max_chars_per_paper is None:
            max_chars_per_paper = int(
                os.getenv("DECISIONLAB_EVAL_PAPER_MAX_CHARS", _DEFAULT_TEXT_CHARS)
            )

        async def search_papers(params: dict) -> str:
            if "query" not in params:
                raise ValueError("search_papers requires 'query' parameter")

            query = str(params["query"])
            limit = min(
                int(params.get("limit", _DEFAULT_PAPER_RESULTS)), _MAX_PAPER_RESULTS
            )
            max_chars = int(params.get("max_chars_per_paper", max_chars_per_paper))
            matches = self.search(query, limit=limit)
            if not matches:
                return f"No corpus papers found for query: {query}"

            blocks: list[str] = []
            for paper in matches:
                text = Path(paper.text_path).read_text(encoding="utf-8")
                truncated = max_chars > 0 and len(text) > max_chars
                body = text[:max_chars] if truncated else text
                metadata = [
                    f"**{paper.title}**",
                    f"  Source archive: {paper.source_archive}",
                    f"  Eval URL: {paper.url}",
                    f"  Local PDF: {paper.pdf_path}",
                    f"  Local text: {paper.text_path}",
                    f"  Authors: {', '.join(paper.authors) if paper.authors else 'N/A'}",
                    f"  Year: {paper.year or 'N/A'}",
                    f"  DOI: {paper.doi or 'N/A'}",
                    f"  Abstract/Excerpt: {paper.snippet}",
                    "  Text excerpt:",
                    body.strip() or "(empty extracted text)",
                ]
                if truncated:
                    metadata.append(
                        f"  [excerpt truncated after {max_chars} characters; "
                        "full extracted text is at Local text]"
                    )
                blocks.append("\n".join(metadata))
            return "\n\n".join(blocks)

        return search_papers

    def search(self, query: str, *, limit: int) -> list[CorpusPaper]:
        terms = _terms(query)
        scored: list[tuple[int, str, CorpusPaper]] = []
        for paper in self.papers:
            score = _score_paper(paper, terms)
            if not terms or score > 0:
                scored.append((score, paper.title.lower(), paper))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [paper for _score, _title, paper in scored[:limit]]

    def export_to(self, out_dir: Path) -> Path:
        """Copy corpus PDFs/text/manifest into an artifact bundle."""

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pdfs").mkdir(exist_ok=True)
        (out_dir / "texts").mkdir(exist_ok=True)
        for paper in self.papers:
            shutil.copy2(paper.pdf_path, out_dir / "pdfs" / Path(paper.pdf_path).name)
            shutil.copy2(
                paper.text_path, out_dir / "texts" / Path(paper.text_path).name
            )
        manifest = out_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "source_cache": str(self.root),
                    "papers": [asdict(p) for p in self.papers],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return manifest


class CorpusWebSearch:
    """``WebSearchPort`` implementation backed by an eval PDF corpus."""

    def __init__(self, corpus: EvalPaperCorpus, *, max_results: int) -> None:
        self._corpus = corpus
        self._max_results = max_results

    async def search(self, query: str) -> list[SearchResult]:
        papers = self._corpus.search(query, limit=self._max_results)
        return [
            SearchResult(
                title=paper.title,
                url=paper.url,
                snippet=_snippet_for_query(paper, query),
            )
            for paper in papers
        ]


def _archives_digest(paths: tuple[Path, ...]) -> str:
    h = hashlib.sha256()
    h.update(_CACHE_VERSION)
    for path in paths:
        h.update(str(path).encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def _dedupe_filename(filename: str, seen: set[str]) -> str:
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 2
    while candidate in seen:
        candidate = f"{stem}-{i}{suffix}"
        i += 1
    seen.add(candidate)
    return candidate


def _extract_pdf_text(pdf_path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        raise RuntimeError(
            "pdftotext is required to build an eval PDF corpus. "
            "Install poppler or pre-build the corpus on a machine that has it."
        )
    proc = subprocess.run(
        [pdftotext, "-layout", str(pdf_path), "-"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdftotext failed for {pdf_path}: {proc.stderr.strip() or proc.returncode}"
        )
    return proc.stdout


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _paper_from_paths(
    *,
    pdf_path: Path,
    text_path: Path,
    source_archive: str,
    corpus_root: Path,
) -> CorpusPaper:
    text = text_path.read_text(encoding="utf-8")
    title = _title_from_text_or_filename(text, pdf_path.name)
    doi = _first_match(_DOI_RE, text)
    year = _extract_year(text, pdf_path.name)
    snippet = _extract_abstract_or_excerpt(text)
    pid = _paper_id(source_archive, pdf_path.name)
    rel = pdf_path.relative_to(corpus_root)
    return CorpusPaper(
        id=pid,
        title=title,
        filename=pdf_path.name,
        source_archive=source_archive,
        url=f"eval-corpus://{pid}/{rel.as_posix()}",
        pdf_path=str(pdf_path),
        text_path=str(text_path),
        snippet=snippet,
        year=year,
        doi=doi,
        authors=(),
    )


def _paper_id(source_archive: str, filename: str) -> str:
    raw = f"{source_archive}:{filename}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def _title_from_text_or_filename(text: str, filename: str) -> str:
    lines = [_compact(line) for line in text.splitlines()[:90]]
    for i, line in enumerate(lines):
        if not _looks_like_title_line(line):
            continue
        parts = [line]
        for nxt in lines[i + 1 : i + 5]:
            if not _looks_like_title_continuation(nxt):
                break
            parts.append(nxt)
            if sum(len(p) for p in parts) > 140:
                break
        title = " ".join(parts)
        if 20 <= len(title) <= 180:
            return title
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


def _looks_like_title_line(line: str) -> bool:
    if not 12 <= len(line) <= 110:
        return False
    lower = line.lower()
    bad_prefixes = (
        "abstract",
        "author manuscript",
        "available in pmc",
        "competing interests",
        "correspondence",
        "copyright",
        "doi:",
        "elifesciences",
        "figure ",
        "funding:",
        "hhs public access",
        "nature reviews",
        "published",
        "received:",
        "research article",
        "reviewing editor",
    )
    if lower.startswith(bad_prefixes):
        return False
    bad_fragments = ("author manuscript", "available in pmc")
    if any(fragment in lower for fragment in bad_fragments):
        return False
    if "@" in line or "www." in lower or "http" in lower:
        return False
    alpha_words = _TOKEN_RE.findall(line)
    if len(alpha_words) < 2:
        return False
    if line.isupper():
        return False
    return not re.search(r"[*‡@]|\d[,)]|\d\*", line)


def _looks_like_title_continuation(line: str) -> bool:
    if not _looks_like_title_line(line):
        return False
    lower = line.lower()
    if lower.startswith(("antonio ", "mehdi ", "boris ", "karl ", "colin ")):
        return False
    if _looks_like_short_author_name(line):
        return False
    return not ("," in line and re.search(r"\b[A-Z]\.", line))


def _looks_like_short_author_name(line: str) -> bool:
    words = line.split()
    if not 2 <= len(words) <= 4:
        return False
    if any(len(word) <= 1 for word in words):
        return False
    return all(word[0].isupper() and word[1:].islower() for word in words)


def _extract_abstract_or_excerpt(text: str, *, limit: int = 700) -> str:
    match = re.search(
        r"\babstract\b[:\s]*(.{120,3000})", text, re.IGNORECASE | re.DOTALL
    )
    source = match.group(1) if match else text
    return _compact(source[:limit])


def _snippet_for_query(paper: CorpusPaper, query: str, *, limit: int = 700) -> str:
    text = Path(paper.text_path).read_text(encoding="utf-8")
    terms = _terms(query)
    lower = text.lower()
    pos = -1
    for term in terms:
        pos = lower.find(term)
        if pos >= 0:
            break
    if pos < 0:
        snippet = paper.snippet
    else:
        start = max(0, pos - limit // 3)
        snippet = text[start : start + limit]
    prefix = f"Corpus-only PDF result from {paper.source_archive}. "
    return prefix + _compact(snippet)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _terms(query: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(query)}


def _score_paper(paper: CorpusPaper, terms: set[str]) -> int:
    if not terms:
        return 1
    title = paper.title.lower()
    snippet = paper.snippet.lower()
    try:
        text = Path(paper.text_path).read_text(encoding="utf-8").lower()
    except OSError:
        text = ""
    score = 0
    for term in terms:
        if term in title:
            score += 8
        if term in snippet:
            score += 4
        if term in text:
            score += 1
    return score


def _first_match(regex: re.Pattern[str], text: str) -> str | None:
    match = regex.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(".,;)")


def _extract_year(text: str, filename: str) -> int | None:
    for source in (filename, text[:5000]):
        match = _YEAR_RE.search(source)
        if match:
            return int(match.group(0))
    return None
