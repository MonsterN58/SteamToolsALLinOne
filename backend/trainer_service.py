from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import stat
import string
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

from backend.paths import get_base_dir

try:
    import cloudscraper
except ImportError:  # pragma: no cover - optional dependency at runtime
    cloudscraper = None

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

BASE_DIR = get_base_dir()
TRAINER_CACHE_DIR = BASE_DIR / ".trainer_cache"
TRAINER_RUNTIME_DIR = BASE_DIR / ".trainer_runtime"
TRAINER_LIST_CACHE = TRAINER_CACHE_DIR / "trainer_list.json"
TRAINER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TRAINER_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

FLING_ARCHIVE_URL = "https://archive.flingtrainer.com/"
FLING_AZ_URL = "https://flingtrainer.com/all-trainers-a-z/"
FLING_BASE = "https://flingtrainer.com"
REQUEST_TIMEOUT = 20
TRAINER_LIST_TTL = 86400

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": FLING_ARCHIVE_URL,
}

ARCHIVE_SUFFIXES = (".zip", ".rar", ".7z", ".exe", ".ct", ".cetrainer")
LAUNCH_SUFFIXES = (".exe", ".ct", ".cetrainer")


@dataclass
class TrainerDownloadTask:
    id: str
    trainer_url: str
    game_name: str
    display_title: str = ""
    download_url: str = ""
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    cache_path: str = ""
    executable_path: str = ""
    original_filename: str = ""
    runtime_path: str = ""
    pid: Optional[int] = None
    auto_launch: bool = False
    security: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)


class TrainerService:
    def __init__(self) -> None:
        self._tasks: dict[str, TrainerDownloadTask] = {}
        self._lock = threading.Lock()
        self._running: dict[str, subprocess.Popen] = {}
        self._ensure_hidden_storage()
        self._setup_archive_tools()

    def search_trainer(self, game_name: str) -> list[dict]:
        keyword = game_name.strip()
        if not keyword:
            return []

        trainers = self._refresh_trainer_list()
        results = [item for item in trainers if self._fuzzy_match(keyword, str(item.get("game_name") or ""))]
        if not results:
            translated = self._translate_keyword(keyword)
            if translated and translated != keyword:
                results = [item for item in trainers if self._fuzzy_match(translated, str(item.get("game_name") or ""))]

        keyword_norm = self._normalize_search(keyword)
        results.sort(key=lambda item: self._search_sort_key(item, keyword_norm))
        return [self._public_search_item(item, keyword) for item in results[:50]]

    def get_trainer_detail(self, trainer_url: str) -> dict:
        trainer = self._trainer_by_url(trainer_url) or {
            "game_name": self._title_from_url(trainer_url),
            "trainer_name": self._title_from_url(trainer_url),
            "url": trainer_url,
            "source": "main" if "flingtrainer.com" in trainer_url else "archive",
            "author": "FLiNG",
            "version": "",
        }
        links = self._get_all_download_urls(trainer)
        return {
            "title": trainer.get("trainer_name") or f"{trainer.get('game_name', '未知游戏')} Trainer",
            "url": trainer.get("url") or trainer_url,
            "options": "",
            "version": trainer.get("version") or "",
            "updated": "",
            "image": "",
            "download_links": links,
        }

    def get_trainer_versions(self, game_name: str) -> dict:
        """为前端返回一个可直接渲染的修改器目录树。"""
        requested_game = game_name.strip()
        if not requested_game:
            return {
                "requested_game": "",
                "resolved_game": "",
                "match_status": "none",
                "items": [],
                "alternatives": [],
            }

        primary = self._resolve_primary_trainer(requested_game)
        if not primary:
            return {
                "requested_game": requested_game,
                "resolved_game": "",
                "match_status": "none",
                "items": [],
                "alternatives": [],
            }

        resolved_game = str(primary.get("game_name") or requested_game)
        match_status = "exact" if self._normalize_search(requested_game) == self._normalize_search(resolved_game) else "approx"
        items: list[dict] = []
        seen_urls: set[str] = set()

        primary_url = str(primary.get("url") or "")
        if primary_url:
            primary_links = self._prepare_catalog_links(self._get_all_download_urls(primary), primary=True)
            if primary_links:
                seen_urls.add(primary_url)
                items.append(
                    self._build_catalog_item(
                        requested_game=requested_game,
                        resolved_game=resolved_game,
                        trainer=primary,
                        source_label="官方最新版" if str(primary.get("source") or "") != "archive" else "推荐版本",
                        detail=self._extract_version_hint(
                            str(primary.get("trainer_name") or primary.get("title") or ""),
                            requested_game,
                            resolved_game,
                        ) or ("来自 FLiNG 官网" if str(primary.get("source") or "") != "archive" else "来自 FLiNG Archive"),
                        download_links=primary_links,
                    )
                )

        archive_index = 0
        for item in self._search_archive_version_pages(resolved_game):
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            if not self._is_same_trainer_family(resolved_game, str(item.get("game_name") or "")):
                continue

            links = self._prepare_catalog_links(self._get_all_download_urls(item), primary=False)
            if not links:
                continue

            seen_urls.add(url)
            archive_index += 1
            source_label = self._extract_version_hint(
                str(item.get("trainer_name") or item.get("title") or ""),
                requested_game,
                resolved_game,
            ) or f"历史版本 {archive_index}"

            items.append(
                self._build_catalog_item(
                    requested_game=requested_game,
                    resolved_game=resolved_game,
                    trainer=item,
                    source_label=source_label,
                    detail="来自 FLiNG Archive",
                    download_links=links,
                )
            )
            if archive_index >= 4:
                break

        return {
            "requested_game": requested_game,
            "resolved_game": resolved_game,
            "match_status": match_status,
            "items": items,
            "alternatives": self._build_alternatives(requested_game, resolved_game),
        }

    def _resolve_primary_trainer(self, game_name: str) -> Optional[dict]:
        ranked: list[tuple[float, dict]] = []
        for item in self._refresh_trainer_list():
            score = self._version_match_score(game_name, str(item.get("game_name") or ""))
            if score <= 0:
                continue
            if str(item.get("source") or "") == "main":
                score += 0.05
            ranked.append((score, item))

        if not ranked:
            for item in self._search_archive_version_pages(game_name):
                score = self._version_match_score(game_name, str(item.get("game_name") or ""))
                if score <= 0:
                    continue
                ranked.append((score, item))

        if not ranked:
            return None

        ranked.sort(key=lambda pair: (-pair[0], self._normalize_search(str(pair[1].get("game_name") or ""))))
        return ranked[0][1]

    def _build_catalog_item(
        self,
        requested_game: str,
        resolved_game: str,
        trainer: dict,
        source_label: str,
        detail: str,
        download_links: list[dict],
    ) -> dict:
        return {
            "title": requested_game,
            "display_name": requested_game,
            "resolved_game": resolved_game,
            "source": str(trainer.get("source") or ""),
            "source_label": source_label,
            "detail": detail,
            "url": str(trainer.get("url") or ""),
            "author": str(trainer.get("author") or "FLiNG"),
            "download_links": download_links,
        }

    def _prepare_catalog_links(self, links: list[dict], primary: bool) -> list[dict]:
        prepared: list[dict] = []
        seen_urls: set[str] = set()
        for index, link in enumerate(links, start=1):
            url = str(link.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            file_type = str(link.get("type") or "").upper()
            if primary:
                base_label = "立即下载" if len(links) == 1 else ("主下载" if index == 1 else f"备用链接 {index - 1}")
            else:
                base_label = "下载" if len(links) == 1 else ("主下载" if index == 1 else f"备用链接 {index - 1}")
            label = f"{base_label} ({file_type})" if file_type and file_type != "FILE" else base_label
            prepared.append(
                {
                    "label": label,
                    "url": url,
                    "type": str(link.get("type") or "file"),
                }
            )
        return prepared

    def _build_alternatives(self, requested_game: str, resolved_game: str) -> list[dict]:
        resolved_key = self._normalize_search(resolved_game)
        alternatives: list[dict] = []
        seen: set[str] = {resolved_key}
        for item in self.search_trainer(requested_game):
            name = str(item.get("game_name") or "")
            norm = self._normalize_search(name)
            if not norm or norm in seen:
                continue
            score = self._version_match_score(requested_game, name)
            if score < 0.78:
                continue
            seen.add(norm)
            alternatives.append({"game_name": name, "score": score})
            if len(alternatives) >= 3:
                break
        return alternatives

    def _is_same_trainer_family(self, base_game: str, candidate_game: str) -> bool:
        return self._version_match_score(base_game, candidate_game) >= 0.88

    def _collect_version_candidates(self, game_name: str) -> list[dict]:
        candidates: list[tuple[float, dict]] = []

        for item in self._refresh_trainer_list():
            score = self._version_match_score(game_name, str(item.get("game_name") or ""))
            if score <= 0:
                continue
            candidates.append((score, item))

        for item in self._search_archive_version_pages(game_name):
            score = self._version_match_score(game_name, str(item.get("game_name") or ""))
            if score <= 0:
                continue
            candidates.append((score, item))

        if not candidates:
            fallback = self.search_trainer(game_name)
            for item in fallback[:1]:
                candidates.append((self._score_value(game_name, str(item.get("game_name") or "")), item))

        candidates.sort(
            key=lambda pair: (
                -pair[0],
                self._normalize_search(str(pair[1].get("game_name") or "")),
                str(pair[1].get("url") or ""),
            )
        )

        if not candidates:
            return []

        best_score = candidates[0][0]
        min_score = max(0.78, best_score - 0.04)
        items: list[dict] = []
        seen_title_keys: set[tuple[str, str]] = set()
        for score, item in candidates:
            if score < min_score or len(items) >= 8:
                continue
            title_key = (
                self._normalize_search(str(item.get("game_name") or "")),
                self._normalize_search(str(item.get("title") or item.get("trainer_name") or "")),
            )
            if title_key in seen_title_keys:
                continue
            seen_title_keys.add(title_key)
            items.append(item)
        return items

    def _search_archive_version_pages(self, game_name: str) -> list[dict]:
        query = game_name.strip()
        if not query:
            return []
        try:
            resp = self._http_get(f"{FLING_ARCHIVE_URL}search?q={query.replace(' ', '+')}", timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return []

        items: list[dict] = []
        seen_urls: set[str] = set()
        for link in soup.find_all("a", target="_self"):
            raw = self._clean_version_title(link.get_text(" ", strip=True))
            href = str(link.get("href") or "").strip()
            if not raw or not href:
                continue
            parsed_name = self._parse_game_name(raw)
            page_url = urljoin(FLING_ARCHIVE_URL, href)
            if page_url in seen_urls:
                continue
            seen_urls.add(page_url)
            items.append(
                {
                    "game_name": parsed_name or query,
                    "trainer_name": raw,
                    "title": raw,
                    "url": page_url,
                    "source": "archive",
                    "version": "",
                    "author": "FLiNG",
                }
            )
        return items

    def _get_all_download_urls(self, trainer: dict) -> list[dict]:
        """获取训练器页面上所有可用的下载链接（支持多镜像/多版本）。"""
        url = str(trainer.get("url") or "")
        source = str(trainer.get("source") or "")
        if not url:
            return []

        found_urls: list[str] = []
        seen: set[str] = set()

        def _add(u: str) -> None:
            if u and u not in seen:
                seen.add(u)
                found_urls.append(u)

        # 如果 URL 本身就是直接下载链接
        if self._looks_like_download(url):
            _add(url)
            return [self._make_link_entry(trainer, u) for u in found_urls]

        # 抓取页面，收集所有下载链接
        try:
            resp = self._http_get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # target="_self" 链接（FLiNG 特征）
            for link in soup.find_all("a", target="_self"):
                href = str(link.get("href") or "").strip()
                if not href:
                    continue
                abs_href = urljoin(url, href)
                if source == "archive" or "flingtrainer.com" in abs_href or "/downloads/" in abs_href:
                    _add(abs_href)

            # 通用下载链接检测
            for link in soup.find_all("a", href=True):
                href = str(link["href"]).strip()
                text = link.get_text(" ", strip=True).lower()
                abs_href = urljoin(url, href)
                if (
                    self._looks_like_download(abs_href)
                    or "/downloads/" in abs_href
                    or "download" in abs_href.lower()
                    or "download" in text
                    or "下载" in text
                ):
                    _add(abs_href)

            # JS 重定向 / 内联链接
            for script in soup.find_all("script"):
                content = script.string or script.get_text() or ""
                for pattern in (
                    r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
                    r'["\']([^"\']*flingtrainer[^"\']*\.(?:zip|rar|7z|exe)[^"\']*)["\']',
                    r'["\'](https?://[^"\']*/downloads/[^"\']+)["\']',
                ):
                    for m in re.findall(pattern, content, re.I):
                        val = m[0] if isinstance(m, tuple) else m
                        if val:
                            _add(urljoin(url, val))

        except Exception:
            pass

        # 如果主站没找到，尝试从 archive 搜索
        if not found_urls:
            game_name = str(trainer.get("game_name") or "")
            if game_name:
                try:
                    archive_url = f"{FLING_ARCHIVE_URL}search?q={game_name.replace(' ', '+')}"
                    resp2 = self._http_get(archive_url, timeout=10)
                    if resp2.status_code == 200:
                        soup2 = BeautifulSoup(resp2.text, "html.parser")
                        for link in soup2.find_all("a", target="_self"):
                            href = str(link.get("href") or "").strip()
                            if href:
                                _add(urljoin(FLING_ARCHIVE_URL, href))
                except Exception:
                    pass

        return [self._make_link_entry(trainer, u) for u in found_urls]

    def _make_link_entry(self, trainer: dict, url: str) -> dict:
        return {
            "label": self._download_label(trainer, url),
            "url": url,
            "size": "",
            "updated": "",
            "type": self._download_type(url),
        }

    def start_download(
        self,
        trainer_url: str,
        game_name: str,
        download_url: str = "",
        download_label: str = "",
        auto_launch: bool = False,
    ) -> str:
        tid = uuid.uuid4().hex
        trainer = self._trainer_by_url(trainer_url) or {
            "game_name": game_name.strip(),
            "trainer_name": download_label.strip() or f"{game_name.strip()} Trainer",
            "url": trainer_url,
            "source": "main" if "flingtrainer.com" in trainer_url else "archive",
            "author": "FLiNG",
            "version": "",
        }
        task = TrainerDownloadTask(
            id=tid,
            trainer_url=trainer_url,
            game_name=game_name.strip(),
            display_title=download_label.strip() or str(trainer.get("trainer_name") or game_name),
            auto_launch=auto_launch,
        )
        with self._lock:
            self._tasks[tid] = task
        threading.Thread(
            target=self._do_download,
            args=(tid, trainer, download_url),
            daemon=True,
        ).start()
        return tid

    def start_latest_trainer(self, game_name: str) -> dict:
        game_name = game_name.strip()
        if not game_name:
            raise ValueError("请先选择或输入游戏名称")

        cached = self.get_cached_trainer(game_name)
        if cached:
            return self.launch_from_cache(game_name)

        results = self.search_trainer(game_name)
        if not results:
            raise FileNotFoundError("没有找到匹配的修改器")

        trainer = self._trainer_by_url(str(results[0].get("url") or "")) or results[0]
        tid = self.start_download(
            trainer_url=str(trainer.get("url") or ""),
            game_name=game_name,
            download_url="",
            download_label=str(trainer.get("trainer_name") or trainer.get("title") or game_name),
            auto_launch=True,
        )
        return {
            "task_id": tid,
            "title": trainer.get("trainer_name") or trainer.get("title") or game_name,
            "version": {"label": trainer.get("version") or "latest", "url": trainer.get("url") or ""},
        }

    def launch_trainer(self, tid: str) -> dict:
        task = self._get_task(tid)
        if not task:
            raise KeyError("任务不存在")
        if task.status != "done":
            raise ValueError("修改器尚未下载完成")
        cache_dir = Path(task.cache_path)
        if not task.cache_path or not cache_dir.exists():
            raise FileNotFoundError("修改器缓存不存在")

        launch_path = Path(task.executable_path) if task.executable_path else self._find_launchable(cache_dir)
        if launch_path and launch_path.suffix.lower() not in LAUNCH_SUFFIXES:
            launch_path = self._find_launchable(cache_dir)
        if not launch_path or not launch_path.exists():
            raise FileNotFoundError("没有找到可启动的修改器文件")
        try:
            launch_path.relative_to(cache_dir)
        except ValueError as exc:
            raise FileNotFoundError("修改器缓存路径无效") from exc

        self._kill_trainer(tid)
        runtime_dir = self._create_runtime_dir(task.game_name)
        self._copy_tree_contents(cache_dir, runtime_dir)
        runtime_launch = runtime_dir / launch_path.relative_to(cache_dir)
        if not runtime_launch.exists():
            runtime_launch = self._find_launchable(runtime_dir)
        if not runtime_launch:
            raise FileNotFoundError("运行目录中没有找到可启动文件")

        proc = self._open_trainer_process(runtime_launch, runtime_dir)
        task._proc = proc
        task.pid = proc.pid if proc else None
        task.runtime_path = str(runtime_launch)
        if proc:
            with self._lock:
                self._running[tid] = proc
            threading.Thread(target=self._watch_runtime_process, args=(tid, proc), daemon=True).start()
        return {"task_id": tid, "pid": task.pid, "message": "修改器已启动"}

    def launch_from_cache(self, game_name: str) -> dict:
        metadata = self.get_cached_trainer(game_name)
        if metadata is None:
            raise FileNotFoundError("本地没有该修改器缓存")
        tid = self._find_task_id_by_game(game_name) or uuid.uuid4().hex
        with self._lock:
            task = self._tasks.get(tid)
            if task is None:
                task = TrainerDownloadTask(
                    id=tid,
                    trainer_url=str(metadata.get("trainer_url") or ""),
                    game_name=game_name,
                    display_title=str(metadata.get("display_title") or game_name),
                    download_url=str(metadata.get("download_url") or ""),
                    status="done",
                    progress=100.0,
                    message="已加载本地缓存，可直接启动",
                    cache_path=str(metadata.get("cache_path") or ""),
                    executable_path=str(metadata.get("executable_path") or ""),
                    original_filename=str(metadata.get("original_filename") or ""),
                    security=metadata.get("security") or {},
                )
                self._tasks[tid] = task
            else:
                task.status = "done"
                task.progress = 100.0
                task.message = "已加载本地缓存，可直接启动"
                task.download_url = str(metadata.get("download_url") or "")
                task.cache_path = str(metadata.get("cache_path") or "")
                task.executable_path = str(metadata.get("executable_path") or "")
                task.original_filename = str(metadata.get("original_filename") or "")
                task.security = metadata.get("security") or {}
        return self.launch_trainer(tid)

    def stop_trainer(self, tid: str) -> dict:
        self._kill_trainer(tid)
        return {"message": "修改器已关闭"}

    def stop_all_trainers(self) -> None:
        with self._lock:
            tids = list(self._running.keys())
        for tid in tids:
            self._kill_trainer(tid)
        self._cleanup_runtime_storage()

    def get_task(self, tid: str) -> dict:
        task = self._get_task(tid)
        if not task:
            raise KeyError("任务不存在")
        is_running = bool(task._proc and task._proc.poll() is None)
        return {
            "id": task.id,
            "game_name": task.game_name,
            "trainer_url": task.trainer_url,
            "download_url": task.download_url,
            "display_title": task.display_title,
            "status": task.status,
            "progress": round(task.progress, 1),
            "message": task.message,
            "has_exe": bool(self._valid_launch_path(task.executable_path)),
            "is_running": is_running,
            "pid": task.pid if is_running else None,
            "security": task.security,
            "created_at": task.created_at,
        }

    def list_tasks(self) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        items = [self.get_task(task.id) for task in tasks]
        items.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return items

    def get_cached_trainer(self, game_name: str) -> Optional[dict]:
        metadata_path = self._metadata_path(game_name)
        if not metadata_path.exists():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not metadata.get("cache_path"):
            return None
        cache_path = Path(str(metadata.get("cache_path") or ""))
        if not cache_path.exists():
            return None
        metadata["cache_path"] = str(cache_path)
        executable_path = Path(str(metadata.get("executable_path") or ""))
        if not self._valid_launch_path(executable_path):
            executable_path = self._find_launchable(cache_path)
            if not executable_path:
                return None
            metadata["executable_path"] = str(executable_path)
        return metadata

    def list_cached_trainers(self) -> list[dict]:
        items: list[dict] = []
        for metadata_file in TRAINER_CACHE_DIR.rglob("trainer.json"):
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            game_name = str(metadata.get("game_name") or "")
            if not game_name:
                continue
            cached = self.get_cached_trainer(game_name)
            if not cached:
                continue
            tid = self._find_task_id_by_game(game_name)
            task = self._tasks.get(tid) if tid else None
            is_running = bool(task and task._proc and task._proc.poll() is None)
            items.append(
                {
                    "game_name": game_name,
                    "display_title": cached.get("display_title") or game_name,
                    "original_filename": cached.get("original_filename") or "",
                    "trainer_url": cached.get("trainer_url") or "",
                    "cached_at": float(cached.get("cached_at") or 0),
                    "task_id": tid,
                    "is_running": is_running,
                    "pid": task.pid if is_running else None,
                }
            )
        items.sort(key=lambda item: item.get("cached_at", 0), reverse=True)
        return items

    def delete_cached_trainer(self, game_name: str) -> dict:
        metadata = self.get_cached_trainer(game_name)
        if metadata is None:
            raise FileNotFoundError("本地没有该修改器缓存")

        tid = self._find_task_id_by_game(game_name)
        if tid:
            self._kill_trainer(tid)
            with self._lock:
                self._tasks.pop(tid, None)

        cache_dir = self._game_cache_dir(game_name)
        shutil.rmtree(cache_dir, ignore_errors=True)
        return {"message": "修改器缓存已删除", "game_name": game_name}

    def _do_download(self, tid: str, trainer: dict, download_url: str) -> None:
        task = self._get_task(tid)
        if task is None:
            return
        task.status = "downloading"
        task.message = "正在获取下载链接..."
        task.progress = 5.0

        try:
            direct_url = download_url or self._get_direct_download_url(trainer)
            if not direct_url:
                raise RuntimeError("无法获取下载链接，请稍后重试")
            task.download_url = direct_url
            task.message = "正在下载修改器文件..."
            temp_file, original_filename = self._download_payload(task, direct_url)
            package_sha256 = self._sha256_file(temp_file)
            task.progress = 86.0
            task.message = "正在解压与整理文件..."
            cache_dir, executable_path, filename = self._store_downloaded_trainer(task, trainer, temp_file, original_filename)
            task.cache_path = str(cache_dir)
            task.executable_path = str(executable_path) if executable_path else ""
            task.original_filename = filename
            task.security = self._build_security_report(
                direct_url=direct_url,
                trainer=trainer,
                package_sha256=package_sha256,
                executable_path=executable_path,
            )
            self._write_security_metadata(task.game_name, task.security)
            task.progress = 100.0
            task.status = "done"
            task.message = "下载完成，可直接启动"
            if task.auto_launch:
                task.message = "下载完成，正在启动修改器..."
                self.launch_trainer(tid)
                task.message = "修改器已启动"
        except Exception as exc:  # noqa: BLE001
            task.status = "error"
            task.message = f"下载失败: {exc}"

    def _refresh_trainer_list(self, force: bool = False) -> list[dict]:
        if not force:
            cached = self._load_list_cache()
            if cached:
                return cached

        archive = self._fetch_archive_list()
        main = self._fetch_main_list()
        merged: dict[str, dict] = {}
        for item in archive:
            merged[str(item["game_name"]).lower()] = item
        for item in main:
            merged[str(item["game_name"]).lower()] = item
        trainers = list(merged.values())
        if trainers:
            self._save_list_cache(trainers)
        return trainers

    def _load_list_cache(self) -> Optional[list[dict]]:
        try:
            if not TRAINER_LIST_CACHE.exists():
                return None
            data = json.loads(TRAINER_LIST_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(data.get("ts") or 0) < TRAINER_LIST_TTL:
                trainers = data.get("trainers")
                return trainers if isinstance(trainers, list) else None
        except Exception:
            return None
        return None

    @staticmethod
    def _save_list_cache(trainers: list[dict]) -> None:
        TRAINER_LIST_CACHE.write_text(
            json.dumps({"ts": time.time(), "trainers": trainers}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _fetch_archive_list(self) -> list[dict]:
        try:
            resp = self._http_get(FLING_ARCHIVE_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return []

        results: list[dict] = []
        ignored = {"Dying Light The Following Enhanced Edition", "Monster Hunter World", "Street Fighter V", "World War Z"}
        for link in soup.find_all("a", target="_self"):
            raw = link.get_text(strip=True)
            if not raw:
                continue
            game_name = self._parse_game_name(raw)
            if not game_name or game_name in ignored:
                continue
            href = link.get("href", "")
            results.append(
                {
                    "game_name": game_name,
                    "trainer_name": f"[FLiNG] {game_name} Trainer",
                    "title": f"[FLiNG] {game_name} Trainer",
                    "url": urljoin(FLING_ARCHIVE_URL, href) if href else "",
                    "source": "archive",
                    "version": "",
                    "author": "FLiNG",
                }
            )
        return results

    def _fetch_main_list(self) -> list[dict]:
        try:
            resp = self._http_get(FLING_AZ_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return []

        results: list[dict] = []
        for section in soup.find_all(class_="letter-section"):
            for li in section.find_all("li"):
                for link in li.find_all("a"):
                    raw = link.get_text(strip=True)
                    game_name = raw.rsplit(" Trainer", 1)[0].strip()
                    if not game_name:
                        continue
                    results.append(
                        {
                            "game_name": game_name,
                            "trainer_name": f"[FLiNG] {game_name} Trainer",
                            "title": f"[FLiNG] {game_name} Trainer",
                            "url": link.get("href", ""),
                            "source": "main",
                            "version": "",
                            "author": "FLiNG",
                        }
                    )
        return results

    def _get_direct_download_url(self, trainer: dict) -> Optional[str]:
        url = str(trainer.get("url") or "")
        source = str(trainer.get("source") or "")
        game_name = str(trainer.get("game_name") or "")
        if not url:
            return None

        if source == "archive":
            if self._looks_like_download(url):
                return url
            try:
                resp = self._http_get(url, timeout=REQUEST_TIMEOUT)
                soup = BeautifulSoup(resp.text, "html.parser")
                found = self._find_download_href(soup, url, archive=True)
                if found:
                    return found
            except Exception:
                return None

        try:
            resp = self._http_get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            found = self._find_download_href(soup, url, archive=False)
            if found:
                return found
        except Exception:
            pass
        if game_name:
            try:
                archive_url = f"{FLING_ARCHIVE_URL}search?q={game_name.replace(' ', '+')}"
                resp2 = self._http_get(archive_url, timeout=10)
                if resp2.status_code == 200:
                    return self._find_download_href(BeautifulSoup(resp2.text, "html.parser"), FLING_ARCHIVE_URL, archive=True)
            except Exception:
                pass
        return None

    def _find_download_href(self, soup: BeautifulSoup, page_url: str, archive: bool) -> Optional[str]:
        for link in soup.find_all("a", target="_self"):
            href = str(link.get("href") or "").strip()
            if not href:
                continue
            if archive or "flingtrainer.com" in href or "/downloads/" in href:
                return urljoin(page_url, href)
        for link in soup.find_all("a", href=True):
            href = str(link["href"]).strip()
            text = link.get_text(" ", strip=True).lower()
            if self._looks_like_download(href) or "/downloads/" in href or "download" in href.lower() or "download" in text or "下载" in text:
                return urljoin(page_url, href)
        meta = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
        if meta and meta.get("content"):
            match = re.search(r"url=([^\s\"']+)", str(meta["content"]), re.I)
            if match:
                return urljoin(page_url, match.group(1))
        for script in soup.find_all("script"):
            content = script.string or script.get_text() or ""
            for pattern in (
                r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']',
                r'["\']([^"\']*flingtrainer[^"\']*\.(?:zip|rar|7z|exe)[^"\']*)["\']',
                r'["\'](https?://[^"\']*/downloads/[^"\']+)["\']',
            ):
                for match in re.findall(pattern, content, re.I):
                    value = match[0] if isinstance(match, tuple) else match
                    if value:
                        return urljoin(page_url, value)
        return None

    def _download_payload(self, task: TrainerDownloadTask, download_url: str) -> tuple[Path, str]:
        resp = self._http_get(download_url, stream=True, timeout=120)
        resp.raise_for_status()
        if self._is_html_response(resp):
            resolved = self._resolve_html_download(resp, download_url)
            if not resolved or resolved == download_url:
                raise RuntimeError("下载链接返回网页，无法解析实际文件")
            resp = self._http_get(resolved, stream=True, timeout=120)
            resp.raise_for_status()
            download_url = resolved

        filename = self._find_filename(resp, download_url)
        temp_dir = Path(tempfile.mkdtemp(prefix="stm-trainer-download-"))
        temp_file = temp_dir / self._safe_filename(filename)
        total = int(resp.headers.get("content-length") or 0)
        downloaded = 0
        with temp_file.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    task.progress = min(84.0, max(8.0, downloaded / total * 84.0))
        temp_file = self._fix_extension_from_signature(temp_file)
        return temp_file, temp_file.name

    def _store_downloaded_trainer(
        self,
        task: TrainerDownloadTask,
        trainer: dict,
        temp_file: Path,
        original_filename: str,
    ) -> tuple[Path, Optional[Path], str]:
        game_dir = self._game_cache_dir(task.game_name)
        shutil.rmtree(game_dir, ignore_errors=True)
        content_dir = game_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        extracted_dir = temp_file.parent / "extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        self._extract_or_copy(temp_file, extracted_dir)
        self._flatten_single_wrapper_dir(extracted_dir)
        self._copy_tree_contents(extracted_dir, content_dir)
        executable_path = self._find_launchable(content_dir)
        if not executable_path:
            raise RuntimeError("下载包中没有找到可启动的修改器文件")

        metadata = {
            "game_name": task.game_name,
            "display_title": task.display_title or trainer.get("trainer_name") or task.game_name,
            "original_filename": original_filename,
            "trainer_url": task.trainer_url or trainer.get("url") or "",
            "download_url": task.download_url,
            "source": trainer.get("source") or "",
            "author": trainer.get("author") or "FLiNG",
            "version": trainer.get("version") or "",
            "cache_path": str(content_dir),
            "executable_path": str(executable_path),
            "cached_at": time.time(),
        }
        self._metadata_path(task.game_name).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.rmtree(temp_file.parent, ignore_errors=True)
        self._hide_path(game_dir)
        return content_dir, executable_path, executable_path.name

    def _extract_or_copy(self, source: Path, dest: Path) -> None:
        ext = source.suffix.lower()
        if ext == ".zip" or zipfile.is_zipfile(source):
            try:
                with zipfile.ZipFile(source, "r") as archive:
                    archive.extractall(dest)
                return
            except zipfile.BadZipFile:
                pass
        if ext in {".rar", ".7z"} or self._has_archive_signature(source):
            tool_path, tool_name = self._find_archive_tool()
            if not tool_path:
                raise RuntimeError("请安装 7-Zip 或 WinRAR 来解压该修改器")
            if tool_name == "winrar":
                cmd = [tool_path, "x", "-y", str(source), str(dest)]
            else:
                cmd = [tool_path, "x", "-y", f"-o{dest}", str(source)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=self._no_window_flag(), timeout=90)
            return
        shutil.copy2(source, dest / source.name)

    @staticmethod
    def _flatten_single_wrapper_dir(directory: Path) -> None:
        while True:
            entries = [item for item in directory.iterdir() if item.name != "__MACOSX"]
            if len(entries) != 1 or not entries[0].is_dir():
                return
            wrapper = entries[0]
            temp = directory / f".flatten-{uuid.uuid4().hex}"
            wrapper.rename(temp)
            for item in temp.iterdir():
                shutil.move(str(item), str(directory / item.name))
            shutil.rmtree(temp, ignore_errors=True)

    def _find_launchable(self, directory: Path) -> Optional[Path]:
        if directory.is_file():
            return directory if directory.suffix.lower() in LAUNCH_SUFFIXES else None
        candidates: list[Path] = []
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in LAUNCH_SUFFIXES and path.stat().st_size > 0:
                candidates.append(path)
        if not candidates:
            return None
        candidates.sort(key=lambda path: self._launch_rank(path))
        return candidates[0]

    @staticmethod
    def _valid_launch_path(value: str | Path) -> bool:
        if not value:
            return False
        path = Path(value)
        return path.is_file() and path.suffix.lower() in LAUNCH_SUFFIXES and path.stat().st_size > 0

    @staticmethod
    def _launch_rank(path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        if path.suffix.lower() == ".exe":
            suffix_rank = 0
        elif path.suffix.lower() == ".cetrainer":
            suffix_rank = 1
        else:
            suffix_rank = 2
        trainer_rank = 0 if "trainer" in name or "fling" in name else 1
        return (suffix_rank, trainer_rank, len(name), name)

    def _open_trainer_process(self, launch_path: Path, cwd: Path) -> Optional[subprocess.Popen]:
        if launch_path.suffix.lower() != ".exe":
            os.startfile(str(launch_path))  # type: ignore[attr-defined]
            return None
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0
        return subprocess.Popen([str(launch_path)], cwd=str(cwd), creationflags=creationflags)

    def _kill_trainer(self, tid: str) -> None:
        with self._lock:
            proc = self._running.pop(tid, None)
        if proc and proc.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    proc.terminate()
                    proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        task = self._get_task(tid)
        if task:
            task._proc = None
            task.pid = None
            runtime_path = task.runtime_path
            task.runtime_path = ""
            if runtime_path:
                shutil.rmtree(Path(runtime_path).parent, ignore_errors=True)

    def _watch_runtime_process(self, tid: str, proc: subprocess.Popen) -> None:
        try:
            proc.wait()
        except Exception:
            return
        with self._lock:
            if self._running.get(tid) is proc:
                self._running.pop(tid, None)
        task = self._get_task(tid)
        if task and task._proc is proc:
            runtime_path = task.runtime_path
            task._proc = None
            task.pid = None
            task.runtime_path = ""
            if runtime_path:
                shutil.rmtree(Path(runtime_path).parent, ignore_errors=True)

    def _trainer_by_url(self, trainer_url: str) -> Optional[dict]:
        if not trainer_url:
            return None
        for trainer in self._refresh_trainer_list():
            if str(trainer.get("url") or "").rstrip("/") == trainer_url.rstrip("/"):
                return trainer
        return None

    def _public_search_item(self, item: dict, keyword: str) -> dict:
        title = str(item.get("trainer_name") or item.get("title") or f"{item.get('game_name', '')} Trainer")
        return {
            "title": title,
            "trainer_name": title,
            "game_name": item.get("game_name") or "",
            "url": item.get("url") or "",
            "options": "",
            "version": item.get("version") or "",
            "updated": "",
            "source": item.get("source") or "",
            "author": item.get("author") or "FLiNG",
            "score": self._score_value(keyword, str(item.get("game_name") or "")),
        }

    def _http_get(self, url: str, headers: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT, **kwargs) -> requests.Response:
        merged_headers = dict(HEADERS)
        if headers:
            merged_headers.update(headers)
        if cloudscraper is not None:
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                scraper = cloudscraper.create_scraper(ssl_context=ctx)
                resp = scraper.get(url, headers=merged_headers, timeout=timeout, verify=False, **kwargs)
                return self._fix_response_encoding(resp)
            except Exception:
                pass
        resp = requests.get(url, headers=merged_headers, timeout=timeout, verify=False, **kwargs)
        return self._fix_response_encoding(resp)

    @staticmethod
    def _fix_response_encoding(resp: requests.Response) -> requests.Response:
        content_type = str(resp.headers.get("content-type") or "").lower()
        if any(marker in content_type for marker in ("text/", "html", "xml", "json")):
            apparent = getattr(resp, "apparent_encoding", "") or ""
            if apparent and apparent.lower() != "ascii":
                resp.encoding = apparent
        return resp

    def _resolve_html_download(self, resp: requests.Response, page_url: str) -> Optional[str]:
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._find_download_href(soup, page_url, archive="archive.flingtrainer.com" in page_url)

    @staticmethod
    def _is_html_response(resp: requests.Response) -> bool:
        content_type = resp.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            return True
        prefix = resp.content[:200].lstrip().lower()
        return prefix.startswith(b"<!doctype") or prefix.startswith(b"<html")

    @staticmethod
    def _find_filename(resp: requests.Response, download_url: str) -> str:
        disposition = resp.headers.get("content-disposition", "")
        if "filename*=" in disposition:
            value = disposition.split("filename*=", 1)[1].strip().strip('";')
            if value.upper().startswith("UTF-8''"):
                value = value[7:]
            return unquote(value)
        match = re.search(r'filename="?([^";]+)"?', disposition)
        if match:
            return unquote(match.group(1).strip())
        parsed = urlparse(resp.url or download_url)
        return unquote(Path(parsed.path).name) or "trainer.zip"

    @staticmethod
    def _fix_extension_from_signature(path: Path) -> Path:
        if path.suffix.lower() in ARCHIVE_SUFFIXES:
            return path
        try:
            header = path.read_bytes()[:8]
        except OSError:
            return path
        suffix = ""
        if header.startswith(b"PK\x03\x04"):
            suffix = ".zip"
        elif header.startswith(b"Rar!"):
            suffix = ".rar"
        elif header.startswith(b"7z\xbc\xaf\x27\x1c"):
            suffix = ".7z"
        elif header.startswith(b"MZ"):
            suffix = ".exe"
        if not suffix:
            return path
        fixed = path.with_name(path.name + suffix)
        path.rename(fixed)
        return fixed

    @staticmethod
    def _has_archive_signature(path: Path) -> bool:
        try:
            header = path.read_bytes()[:8]
        except OSError:
            return False
        return header.startswith((b"Rar!", b"7z\xbc\xaf\x27\x1c"))

    @staticmethod
    def _looks_like_download(url: str) -> bool:
        lowered = url.lower().split("?", 1)[0]
        return lowered.endswith(ARCHIVE_SUFFIXES) or "/files/" in lowered or "/downloads/" in lowered

    @staticmethod
    def _download_type(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
        return suffix or "file"

    @staticmethod
    def _download_label(trainer: dict, url: str) -> str:
        parsed = urlparse(url)
        filename = unquote(Path(parsed.path).name)
        readable = re.sub(r"\.(zip|rar|7z|exe|ct|cetrainer)$", "", filename, flags=re.IGNORECASE)
        readable = re.sub(r"[_-]+", " ", readable).strip()
        if readable and len(readable) <= 72 and all(32 <= ord(char) < 127 for char in readable):
            return readable

        host = parsed.netloc.lower()
        if "archive.flingtrainer.com" in host:
            return "Archive 下载"
        if "flingtrainer.com" in host:
            return "官网下载安装"
        if host:
            return f"{host.split('.')[0]} 下载"
        return str(trainer.get("trainer_name") or trainer.get("game_name") or "下载链接")

    def _create_runtime_dir(self, game_name: str) -> Path:
        runtime_dir = Path(tempfile.mkdtemp(prefix=f"stm-{self._safe_slug(game_name)}-", dir=str(TRAINER_RUNTIME_DIR)))
        self._hide_path(runtime_dir)
        return runtime_dir

    @staticmethod
    def _copy_tree_contents(source: Path, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            target = dest / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.chmod(stat.S_IWRITE)
                    target.unlink()
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

    def _cleanup_runtime_storage(self) -> None:
        for directory in TRAINER_RUNTIME_DIR.iterdir():
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)

    def _ensure_hidden_storage(self) -> None:
        self._hide_path(TRAINER_CACHE_DIR)
        self._hide_path(TRAINER_RUNTIME_DIR)

    @staticmethod
    def _hide_path(path: Path) -> None:
        if sys.platform != "win32" or not path.exists():
            return
        subprocess.run(["attrib", "+h", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _setup_archive_tools() -> None:
        extra_paths = [
            r"C:\Program Files\7-Zip",
            r"C:\Program Files (x86)\7-Zip",
            r"C:\Program Files\WinRAR",
            r"C:\Program Files (x86)\WinRAR",
        ]
        current_path = os.environ.get("PATH", "")
        for path in extra_paths:
            if os.path.isdir(path) and path not in current_path:
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")

    @staticmethod
    def _find_archive_tool() -> tuple[Optional[str], Optional[str]]:
        for path in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
            if os.path.isfile(path):
                return path, "7z"
        for path in [r"C:\Program Files\WinRAR\UnRAR.exe", r"C:\Program Files (x86)\WinRAR\UnRAR.exe"]:
            if os.path.isfile(path):
                return path, "winrar"
        found = shutil.which("7z") or shutil.which("7za")
        if found:
            return found, "7z"
        found = shutil.which("UnRAR")
        if found:
            return found, "winrar"
        return None, None

    @staticmethod
    def _no_window_flag() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    @staticmethod
    def _parse_game_name(raw: str) -> str:
        name = re.sub(
            r"\s+v[\d.]+.*"
            r"|\.v[\d].*"
            r"|\s+\d+\.\d+\.\d+.*"
            r"|\s+Plus\s+\d+.*"
            r"|Build\s+\d+.*"
            r"|\d+\.\d+-Update.*"
            r"|Update\s+\d+.*"
            r"|\(Update\s.*"
            r"|\s+Early\s+Access.*"
            r"|\.Early\.Access.*"
            r"|-FLiNG$"
            r"|\s+Fixed$"
            r"|\s+Updated.*",
            "",
            raw,
            flags=re.IGNORECASE,
        )
        name = name.replace("_", ": ").strip()
        if name == "Bright.Memory.Episode.1":
            return "Bright Memory: Episode 1"
        return name

    @staticmethod
    def _clean_version_title(raw: str) -> str:
        title = re.sub(r"\s+", " ", raw or "").strip()
        title = title.replace("_", " ")
        return re.sub(r"\s*-\s*FLiNG$", "", title, flags=re.IGNORECASE).strip()

    def _extract_version_hint(self, raw_title: str, requested_game: str, resolved_game: str) -> str:
        hint = self._clean_version_title(raw_title)
        candidates = [requested_game, resolved_game, self._parse_game_name(hint)]
        for name in candidates:
            cleaned_name = str(name or "").strip()
            if not cleaned_name:
                continue
            hint = re.sub(re.escape(cleaned_name), "", hint, flags=re.IGNORECASE)
        hint = re.sub(r"\b(fling|trainer|mrantifun|plus|update|build|archive|download)\b", "", hint, flags=re.IGNORECASE)
        hint = re.sub(r"[\[\](){}]", " ", hint)
        hint = re.sub(r"\s+", " ", hint).strip(" -_:.,")
        if not hint or "�" in hint:
            return ""
        return hint[:48].strip()

    @staticmethod
    def _to_roman(n: int) -> str:
        if n == 0:
            return "0"
        values = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
        result = ""
        for value, symbol in values:
            while n >= value:
                result += symbol
                n -= value
        return result

    def _normalize_search(self, value: str) -> str:
        punct = string.punctuation
        try:
            import importlib

            punct += str(importlib.import_module("zhon.hanzi").punctuation)
        except ImportError:
            pass
        value = re.sub(r"\d+", lambda match: self._to_roman(int(match.group())), value)
        return "".join(char for char in value if char not in punct and not char.isspace()).lower()

    def _semantic_tokens(self, value: str) -> set[str]:
        tokens: set[str] = set()
        for token in re.findall(r"[a-z0-9]+", value.lower()):
            if token.isdigit():
                tokens.add(token)
                tokens.add(self._to_roman(int(token)).lower())
                continue
            tokens.add(token)
        return tokens

    @staticmethod
    def _sequence_tokens(tokens: set[str]) -> set[str]:
        roman_tokens = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"}
        return {token for token in tokens if token.isdigit() or token in roman_tokens}

    def _version_match_score(self, keyword: str, target: str) -> float:
        keyword_norm = self._normalize_search(keyword)
        target_norm = self._normalize_search(target)
        if not keyword_norm or not target_norm:
            return 0.0

        keyword_tokens = self._semantic_tokens(keyword)
        target_tokens = self._semantic_tokens(target)
        if keyword_tokens and target_tokens:
            keyword_seq = self._sequence_tokens(keyword_tokens)
            target_seq = self._sequence_tokens(target_tokens)
            if keyword_seq and target_seq and not (keyword_seq & target_seq):
                return 0.0

        shared = keyword_tokens & target_tokens
        if keyword_tokens and target_tokens and not shared:
            return 0.0

        overlap = len(shared) / max(1, len(keyword_tokens)) if keyword_tokens else 0.0
        base = self._score_value(keyword, target)
        if keyword_norm == target_norm:
            base += 0.2
        elif keyword_norm in target_norm or target_norm in keyword_norm:
            base += 0.12

        if base < 0.72 and overlap < 0.66:
            return 0.0
        return round(base + overlap * 0.08, 4)

    def _fuzzy_match(self, keyword: str, target: str, threshold: int = 76) -> bool:
        keyword_norm = self._normalize_search(keyword)
        target_norm = self._normalize_search(target)
        if not keyword_norm or not target_norm:
            return False
        if keyword_norm in target_norm or target_norm in keyword_norm:
            return True
        keyword_tokens = self._latin_tokens(keyword)
        target_tokens = self._latin_tokens(target)
        if keyword_tokens and target_tokens and not self._has_meaningful_token_overlap(keyword_tokens, target_tokens):
            return False
        try:
            from fuzzywuzzy import fuzz

            return fuzz.partial_ratio(keyword_norm, target_norm) >= threshold
        except ImportError:
            return self._simple_ratio(keyword_norm, target_norm) >= 0.58

    @staticmethod
    def _latin_tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 3}

    @staticmethod
    def _has_meaningful_token_overlap(left: set[str], right: set[str]) -> bool:
        for left_token in left:
            for right_token in right:
                if left_token == right_token or left_token in right_token or right_token in left_token:
                    return True
        return False

    @staticmethod
    def _simple_ratio(left: str, right: str) -> float:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, left, right).ratio()

    def _score_value(self, keyword: str, target: str) -> float:
        keyword_norm = self._normalize_search(keyword)
        target_norm = self._normalize_search(target)
        if keyword_norm == target_norm:
            return 1.0
        if keyword_norm and keyword_norm in target_norm:
            return 0.9
        return round(self._simple_ratio(keyword_norm, target_norm), 4)

    def _search_sort_key(self, item: dict, keyword_norm: str) -> tuple[int, str]:
        name = self._normalize_search(str(item.get("game_name") or ""))
        if name == keyword_norm:
            rank = 0
        elif keyword_norm and keyword_norm in name:
            rank = 1
        else:
            rank = 2
        return rank, name

    @staticmethod
    def _is_chinese(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", value))

    def _translate_keyword(self, keyword: str) -> str:
        keyword = keyword.strip()
        if not keyword:
            return keyword
        from_lang, to_lang = ("zh-Hans", "en") if self._is_chinese(keyword) else ("en", "zh-Hans")
        try:
            url = "https://cn.bing.com/translator?ref=TThis&text=&from=zh-Hans&to=en"
            resp = self._http_get(url, timeout=10)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            dev_element = soup.find("div", id="tta_outGDCont")
            ig_match = re.search(r'IG:"(\w+)"', html)
            token_match = re.findall(r'var params_AbusePreventionHelper = \[(\d+),"([^"]+)",\d+\];', html)
            if not dev_element or not ig_match or not token_match:
                return keyword
            data_iid = dev_element.attrs.get("data-iid", "")
            data = {
                "fromLang": from_lang,
                "to": to_lang,
                "token": token_match[0][1],
                "key": token_match[0][0],
                "text": keyword,
                "tryFetchingGenderDebiasedTranslations": "true",
            }
            post_url = f"https://cn.bing.com/ttranslatev3?isVertical=1&&IG={ig_match.group(1)}&IID={data_iid}"
            result = requests.post(post_url, data=data, headers=HEADERS, timeout=10)
            payload = result.json()
            return str(payload[0]["translations"][0]["text"])
        except Exception:
            return keyword

    @staticmethod
    def _title_from_url(url: str) -> str:
        stem = Path(urlparse(url).path).stem
        return unquote(stem).replace("-", " ").replace("_", " ").strip().title() or "未知修改器"

    def _find_task_id_by_game(self, game_name: str) -> Optional[str]:
        normalized = self._normalize_name(game_name)
        with self._lock:
            for task_id, task in self._tasks.items():
                if self._normalize_name(task.game_name) == normalized:
                    return task_id
        return None

    def _get_task(self, tid: str) -> Optional[TrainerDownloadTask]:
        with self._lock:
            return self._tasks.get(tid)

    def _game_cache_dir(self, game_name: str) -> Path:
        slug = self._safe_slug(game_name)
        digest = hashlib.md5(game_name.strip().encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        return TRAINER_CACHE_DIR / f"{slug}-{digest}"

    def _metadata_path(self, game_name: str) -> Path:
        return self._game_cache_dir(game_name) / "trainer.json"

    def _write_security_metadata(self, game_name: str, security: dict) -> None:
        metadata_path = self._metadata_path(game_name)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        metadata["security"] = security
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_security_report(
        self,
        direct_url: str,
        trainer: dict,
        package_sha256: str,
        executable_path: Optional[Path],
    ) -> dict:
        host = (urlparse(direct_url).netloc or "").lower()
        executable_sha256 = self._sha256_file(executable_path) if executable_path and executable_path.exists() else ""
        official_source = host.endswith("flingtrainer.com") or host.endswith("archive.flingtrainer.com")
        source_name = "FLiNG 官网" if str(trainer.get("source") or "") != "archive" else "FLiNG Archive"
        summary = "已记录来源与文件哈希，建议首次运行前自行用杀毒软件复查。"
        if not official_source and host:
            summary = f"当前下载直链来自 {host}，不是标准 FLiNG 域名，建议先人工确认再运行。"
        return {
            "source_name": source_name,
            "download_host": host,
            "official_source": official_source,
            "package_sha256": package_sha256,
            "executable_sha256": executable_sha256,
            "checked_at": time.time(),
            "summary": summary,
        }

    @staticmethod
    def _sha256_file(path: Optional[Path]) -> str:
        if not path or not path.exists() or not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @staticmethod
    def _safe_slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug[:40] or "trainer"

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]+', "_", value).strip().strip(".")
        return name or "trainer.zip"
