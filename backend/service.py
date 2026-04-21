from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup

from backend.paths import get_base_dir

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None

BASE_DIR = get_base_dir()
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from search import search_games  # noqa: E402


ALLOWED_SUFFIXES: Iterable[str] = (".lua", ".manifest", ".json", ".vdf")
NODE_TIMEOUT = 1
SEGMENT_MIN_BYTES = 2 * 1024 * 1024
SEGMENT_WORKERS = 4
SEGMENT_CHUNK_SIZE = 8192
STEAM_ENV_KEYS = ("STEAM_PATH", "SteamPath", "STEAMPATH")
DEFAULT_STEAM_PATHS = (
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Program Files (x86)\Steam",
)
REPOSITORY_INDEX_URL = (
    "https://raw.githubusercontent.com/fairy-root/steam-depot-online/main/repositories.json"
)
GITHUB_REPO_FALLBACKS = (
    "Fairyvmos/bruh-hub",
    "bingyu50/SteamManifestCache",
    "TOP-01/SteamManifestCache",
    "bingyu50/ManifestAutoUpdate",
    "TOP-01/ManifestAutoUpdate",
    "SteamAutoCracks/ManifestHub",
)
GITHUB_PROXY_PREFIXES = (
    "https://gh.llkk.cc/https://github.com",
    "https://ghproxy.net/https://github.com",
)
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "SteamToolsManager/2.0",
}


@dataclass
class DownloadTask:
    id: str
    appid: str
    source: str
    auto_import: bool
    unlock_dlc: bool = False
    status: str = "running"
    progress: float = 0.0
    logs: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time)
    folder_name: str = ""
    game_name: str | None = None
    error: str | None = None


class SteamToolsService:
    def __init__(self) -> None:
        self.base_dir = BASE_DIR
        self.download_dir = self.base_dir / "download"
        self.log_dir = self.base_dir / "log"
        self.config_path = self.base_dir / "config.json"
        self.principle_doc = self.base_dir / "软件原理说明.md"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._tasks: dict[str, DownloadTask] = {}
        self._game_name_cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def get_settings(self) -> dict:
        defaults = {
            "download_source": "auto",
            "auto_import": False,
            "unlock_dlc": False,
            "search_enhance": False,
            "patch_emulator_mode": 0,
            "patch_use_experimental": False,
            "patch_default_username": "Player",
            "patch_default_language": "schinese",
            "lan_default_port": 47584,
            "denuvo_auto_backup": True,
        }
        if self.config_path.exists():
            import json

            with self.config_path.open("r", encoding="utf-8") as file:
                settings = json.load(file)
            source = settings.get("download_source", "auto")
            if source not in {"auto", "domestic", "overseas"}:
                source = "auto"
            result = {**defaults}
            result["download_source"] = source
            result["auto_import"] = bool(settings.get("auto_import", False))
            result["unlock_dlc"] = bool(settings.get("unlock_dlc", False))
            result["search_enhance"] = bool(settings.get("search_enhance", False))
            result["patch_emulator_mode"] = int(settings.get("patch_emulator_mode", 0))
            result["patch_use_experimental"] = bool(settings.get("patch_use_experimental", False))
            result["patch_default_username"] = str(settings.get("patch_default_username", "Player"))
            result["patch_default_language"] = str(settings.get("patch_default_language", "schinese"))
            result["lan_default_port"] = int(settings.get("lan_default_port", 47584))
            result["denuvo_auto_backup"] = bool(settings.get("denuvo_auto_backup", True))
            return result
        return defaults

    def save_settings(self, settings: dict) -> dict:
        import json

        source = settings.get("download_source", "auto")
        if source not in {"auto", "domestic", "overseas"}:
            source = "auto"
        data = {
            "download_source": source,
            "auto_import": bool(settings.get("auto_import", False)),
            "unlock_dlc": bool(settings.get("unlock_dlc", False)),
            "search_enhance": bool(settings.get("search_enhance", False)),
            "patch_emulator_mode": int(settings.get("patch_emulator_mode", 0)),
            "patch_use_experimental": bool(settings.get("patch_use_experimental", False)),
            "patch_default_username": str(settings.get("patch_default_username", "Player")),
            "patch_default_language": str(settings.get("patch_default_language", "schinese")),
            "lan_default_port": int(settings.get("lan_default_port", 47584)),
            "denuvo_auto_backup": bool(settings.get("denuvo_auto_backup", True)),
        }
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        return data

    def search(self, term: str, limit: int = 10, translate_fallback: bool = True) -> list[dict]:
        items = search_games(term, limit=limit, translate_fallback=translate_fallback)
        return [
            {
                "name": item.get("name") or "",
                "appid": str(item.get("appid") or ""),
                "image": item.get("image") or "",
            }
            for item in items
        ]

    def start_download_task(self, appid: str, source: str, auto_import: bool, unlock_dlc: bool = False) -> str:
        appid = appid.strip()
        if not appid:
            raise ValueError("AppID 不能为空")
        if source not in {"auto", "domestic", "overseas"}:
            raise ValueError("source 必须是 auto、domestic 或 overseas")
        if not re.fullmatch(r"\d+", appid):
            raise ValueError("AppID 必须是数字")

        task_id = uuid.uuid4().hex
        task = DownloadTask(
            id=task_id,
            appid=appid,
            source=source,
            auto_import=auto_import,
            unlock_dlc=unlock_dlc,
        )
        with self._lock:
            self._tasks[task_id] = task
        threading.Thread(target=self._run_download_task, args=(task_id,), daemon=True).start()
        return task_id

    def get_task_snapshot(self, task_id: str, offset: int = 0) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("任务不存在")
            logs = task.logs[offset:]
            return {
                "id": task.id,
                "appid": task.appid,
                "status": task.status,
                "progress": round(task.progress, 2),
                "logs": logs,
                "next_offset": offset + len(logs),
                "folder_name": task.folder_name,
                "game_name": task.game_name,
                "error": task.error,
                "updated_at": task.updated_at,
            }

    def open_download_folder(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(self.download_dir)

    def open_principle_doc(self) -> None:
        if not self.principle_doc.exists():
            raise FileNotFoundError(f"未找到文档：{self.principle_doc}")
        self._open_path(self.principle_doc)

    def _open_path(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)

    def _run_download_task(self, task_id: str) -> None:
        task = self._must_get_task(task_id)
        self._append_log(task, f"开始执行 {task.source} 源下载，AppID = {task.appid}")
        try:
            name, _, folder_name = self._collect_game_info(task, task.appid)
            task.game_name = name
            task.folder_name = folder_name

            success = self._run_download_flow(task, task.source, task.appid, folder_name)
            if success and task.auto_import:
                self._append_log(task, "下载完成，开始自动入库...")
                if self._auto_import_lua(task, task.appid):
                    self._append_log(task, "自动入库完成。")
                else:
                    self._append_log(task, "自动入库未完成。")

                if task.unlock_dlc:
                    self._append_log(task, "开始复制 manifest 到 depotcache（解锁 DLC）...")
                    copied, skipped = self._copy_manifests_to_depotcache(task, task.appid)
                    self._append_log(task, f"DLC manifest 已复制 {copied} 个，跳过 {skipped} 个（已存在）。")

            with self._lock:
                if success:
                    task.status = "success"
                    task.progress = 100.0
                    task.updated_at = time()
                else:
                    task.status = "error"
                    task.error = task.error or "任务失败，请查看日志。"
                    task.updated_at = time()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                task.status = "error"
                task.error = str(exc)
                task.updated_at = time()
            self._append_log(task, f"任务异常：{exc}")

    def _run_download_flow(self, task: DownloadTask, source: str, appid: str, folder_name: str) -> bool:
        folder_name = folder_name or appid
        download_root = self.download_dir
        download_root.mkdir(parents=True, exist_ok=True)
        if source == "auto":
            success = self._handle_github_repository_download(
                task, appid, folder_name, download_root, prefer_proxy=True
            )
        elif source == "domestic":
            success = self._handle_domestic_download(task, appid, folder_name, download_root)
        else:
            success = self._handle_overseas_download(task, appid, folder_name, download_root)

        if success:
            self._append_log(task, "任务完成。")
        else:
            self._append_log(task, "任务失败，请查看日志。")
        return success

    def _handle_domestic_download(
        self, task: DownloadTask, appid: str, folder_name: str, download_root: Path
    ) -> bool:
        base_url = (
            "https://gh.llkk.cc/https://github.com/SteamAutoCracks/ManifestHub"
            f"/archive/refs/heads/{appid}.zip"
        )
        zip_path = download_root / f"{appid}.zip"
        if self._check_domestic_url(task, base_url):
            self._append_log(task, "国内代理源连接正常，开始下载文件...")
            if self._download_file_stream(task, base_url, zip_path):
                target_dir = download_root / folder_name
                if self._extract_and_cleanup(task, zip_path, target_dir):
                    return True
        self._append_log(task, "国内代理源不可用，切换到 GitHub 仓库池。")
        return self._handle_github_repository_download(
            task, appid, folder_name, download_root, prefer_proxy=True
        )

    def _handle_overseas_download(
        self, task: DownloadTask, appid: str, folder_name: str, download_root: Path
    ) -> bool:
        node = self._find_first_valid_node(appid)
        if node is None:
            self._append_log(task, "没有可用的国外节点，切换到 GitHub 仓库池。")
            return self._handle_github_repository_download(
                task, appid, folder_name, download_root, prefer_proxy=False
            )
        self._append_log(task, f"使用节点 {node} 下载")
        download_url = self._get_overseas_download_url(appid, node)
        zip_path = download_root / f"{appid}_src{node}.zip"
        headers = {
            "Host": "api-psi-eight-12.vercel.app",
            "Sec-Ch-Ua": '"Chromium";v="141", "Not?A_Brand";v="8"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://api-psi-eight-12.vercel.app/",
            "Accept-Encoding": "gzip, deflate, br",
            "Priority": "u=0, i",
        }
        if not self._download_file_stream(task, download_url, zip_path, headers=headers, timeout=(5, 30)):
            self._append_log(task, "国外节点下载失败，切换到 GitHub 仓库池。")
            return self._handle_github_repository_download(
                task, appid, folder_name, download_root, prefer_proxy=False
            )
        target_dir = download_root / folder_name
        if self._extract_and_cleanup(task, zip_path, target_dir):
            return True
        self._append_log(task, "国外节点压缩包无效，切换到 GitHub 仓库池。")
        return self._handle_github_repository_download(
            task, appid, folder_name, download_root, prefer_proxy=False
        )

    def _handle_github_repository_download(
        self,
        task: DownloadTask,
        appid: str,
        folder_name: str,
        download_root: Path,
        prefer_proxy: bool,
    ) -> bool:
        repositories = self._load_manifest_repositories(task)
        if not repositories:
            task.error = "没有可用的 GitHub Manifest 仓库，请稍后再试。"
            self._append_log(task, task.error)
            return False

        self._append_log(task, f"开始检查 GitHub 仓库池，共 {len(repositories)} 个候选源。")
        for repo in repositories:
            self._append_log(task, f"检查 GitHub 源：{repo}")
            if not self._github_ref_exists(repo, appid):
                continue

            self._append_log(task, f"找到可用源：{repo}，开始下载。")
            for label, url, headers in self._github_download_urls(repo, appid, prefer_proxy):
                zip_path = download_root / f"{appid}_{self._sanitize_filename(repo)}_{label}.zip"
                if zip_path.exists():
                    try:
                        zip_path.unlink()
                    except OSError:
                        pass
                self._append_log(task, f"尝试 {label} 下载通道...")
                if not self._download_file_stream(task, url, zip_path, headers=headers, timeout=(8, 60)):
                    continue
                target_dir = download_root / folder_name
                if self._extract_and_cleanup(task, zip_path, target_dir):
                    self._append_log(task, f"已接入 GitHub 源：{repo}")
                    return True

        task.error = (
            "没有找到包含该 AppID 的有效 GitHub 源。可尝试更换 AppID，"
            "或等待上游 Manifest 仓库更新。"
        )
        self._append_log(task, task.error)
        return False

    def _load_manifest_repositories(self, task: DownloadTask) -> list[str]:
        repositories: list[str] = []

        def add(repo: str) -> None:
            repo = repo.strip().strip("/")
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
                return
            if repo.lower() not in {item.lower() for item in repositories}:
                repositories.append(repo)

        for repo in GITHUB_REPO_FALLBACKS:
            add(repo)

        try:
            resp = requests.get(REPOSITORY_INDEX_URL, timeout=(5, 10), headers=GITHUB_HEADERS)
            resp.raise_for_status()
            index = resp.json()
            if isinstance(index, dict):
                for repo, repo_type in index.items():
                    if str(repo_type).lower() in {"branch", "decrypted"}:
                        add(str(repo))
        except (requests.RequestException, ValueError) as exc:
            self._append_log(task, f"读取在线仓库索引失败，使用内置候选源：{exc}")

        return repositories

    def _github_ref_exists(self, repo: str, appid: str) -> bool:
        url = f"https://api.github.com/repos/{repo}/contents"
        try:
            resp = requests.get(url, params={"ref": appid}, timeout=(5, 10), headers=GITHUB_HEADERS)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _github_download_urls(
        self, repo: str, appid: str, prefer_proxy: bool
    ) -> list[tuple[str, str, dict[str, str] | None]]:
        direct = (
            "GitHub",
            f"https://api.github.com/repos/{repo}/zipball/{appid}",
            GITHUB_HEADERS,
        )
        proxied = [
            (
                f"代理{idx}",
                f"{prefix}/{repo}/archive/refs/heads/{appid}.zip",
                None,
            )
            for idx, prefix in enumerate(GITHUB_PROXY_PREFIXES, start=1)
        ]
        if prefer_proxy:
            return [*proxied, direct]
        return [direct, *proxied]

    def _extract_and_cleanup(self, task: DownloadTask, zip_path: Path, target_dir: Path) -> bool:
        try:
            self._process_downloaded_archive(task, zip_path, target_dir)
        except RuntimeError as exc:
            self._append_log(task, str(exc))
            return False
        else:
            self._append_log(task, f"下载完成，保留的文件已保存至 {target_dir}")
        finally:
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError as exc:
                    self._append_log(task, f"无法删除压缩包 {zip_path}: {exc}")
        return True

    def _process_downloaded_archive(self, task: DownloadTask, zip_path: Path, target_dir: Path) -> None:
        archive_path = zip_path
        target_root = target_dir
        staging_dir = target_root.with_name(target_root.name + "_staging")

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        target_root.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(staging_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise RuntimeError(f"{archive_path} 不是有效的压缩包: {exc}") from exc

        kept_count = 0
        for file_path in staging_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            dest = target_root / file_path.name
            try:
                shutil.move(str(file_path), str(dest))
                kept_count += 1
            except OSError as exc:
                self._append_log(task, f"移动 {file_path} -> {dest} 失败: {exc}")

        shutil.rmtree(staging_dir, ignore_errors=True)
        if kept_count == 0:
            raise RuntimeError("压缩包中没有可入库的 lua / manifest / json / vdf 文件。")

    def _check_domestic_url(self, task: DownloadTask, url: str) -> bool:
        try:
            resp = requests.head(url, timeout=(5, 5), allow_redirects=True)
            if resp.status_code == 404:
                self._append_log(task, "国内代理源没有该游戏，准备尝试其他源。")
                return False
            resp.raise_for_status()
            return True
        except requests.RequestException:
            pass

        try:
            headers = {"Range": "bytes=0-0"}
            with requests.get(url, headers=headers, stream=True, timeout=(5, 5)) as resp:
                if resp.status_code == 404:
                    self._append_log(task, "国内代理源没有该游戏，准备尝试其他源。")
                    return False
                resp.raise_for_status()
                resp.raw.read(1)
                return True
        except requests.RequestException as exc:
            self._append_log(task, f"国内代理源检查失败：{exc}")
            return False

    def _download_file_stream(
        self,
        task: DownloadTask,
        url: str,
        save_path: Path,
        headers: dict | None = None,
        timeout: float | tuple[float, float] = 30,
    ) -> bool:
        self._append_log(task, "开始下载...")
        req_headers = headers.copy() if headers else {}
        total_bytes = 0
        supports_ranges = False

        try:
            try:
                head_resp = requests.head(url, headers=req_headers, timeout=10)
                head_resp.raise_for_status()
                total_bytes = int(head_resp.headers.get("content-length") or 0)
                supports_ranges = head_resp.headers.get("accept-ranges", "").lower() == "bytes"
            except (requests.RequestException, ValueError, TypeError):
                total_bytes = 0

            if supports_ranges and total_bytes >= SEGMENT_MIN_BYTES:
                self._append_log(task, "使用分段并发下载加速。")
                ok = self._download_with_segments(task, url, save_path, total_bytes, req_headers, timeout)
                if ok:
                    self._set_progress(task, 100)
                    return True
                self._append_log(task, "分段下载失败，切换为普通下载。")

            ok = self._download_single_stream(task, url, save_path, req_headers, timeout, total_bytes)
            if ok:
                self._set_progress(task, 100)
            return ok
        except Exception as exc:  # noqa: BLE001
            self._set_progress(task, 0)
            self._append_log(task, f"下载失败：{exc}")
            return False

    def _download_single_stream(
        self,
        task: DownloadTask,
        url: str,
        save_path: Path,
        headers: dict[str, str],
        timeout: float | tuple[float, float],
        total_bytes: int,
    ) -> bool:
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                if total_bytes <= 0:
                    try:
                        total_bytes = int(resp.headers.get("content-length") or 0)
                    except (TypeError, ValueError):
                        total_bytes = 0

                downloaded = 0
                last_percent = 0.0
                with save_path.open("wb") as file_handle:
                    for chunk in resp.iter_content(chunk_size=SEGMENT_CHUNK_SIZE):
                        if not chunk:
                            continue
                        file_handle.write(chunk)
                        if total_bytes > 0:
                            downloaded += len(chunk)
                            percent = min(100.0, downloaded * 100.0 / total_bytes)
                            if percent - last_percent >= 1 or downloaded == total_bytes:
                                last_percent = percent
                                self._set_progress(task, percent)
            return True
        except (requests.RequestException, OSError) as exc:
            self._append_log(task, f"下载失败：{exc}")
            return False

    def _download_with_segments(
        self,
        task: DownloadTask,
        url: str,
        save_path: Path,
        total_bytes: int,
        headers: dict[str, str],
        timeout: float | tuple[float, float],
    ) -> bool:
        segment_count = max(1, min(SEGMENT_WORKERS, math.ceil(total_bytes / SEGMENT_MIN_BYTES)))
        segment_size = math.ceil(total_bytes / segment_count)
        part_paths: list[Path | None] = [None] * segment_count
        progress_lock = threading.Lock()
        downloaded = 0
        last_percent = 0.0

        def cleanup_parts() -> None:
            for path_obj in part_paths:
                if path_obj and path_obj.exists():
                    try:
                        path_obj.unlink()
                    except OSError:
                        pass

        def download_part(idx: int, start: int, end: int) -> bool:
            nonlocal downloaded, last_percent
            part_headers = dict(headers)
            part_headers["Range"] = f"bytes={start}-{end}"
            part_path = Path(f"{save_path}.part{idx}")
            try:
                with requests.get(url, headers=part_headers, stream=True, timeout=timeout) as resp:
                    resp.raise_for_status()
                    status_ok = resp.status_code == 206 or (
                        resp.status_code == 200 and start == 0 and end >= total_bytes - 1
                    )
                    if not status_ok:
                        return False
                    with part_path.open("wb") as part_file:
                        for chunk in resp.iter_content(chunk_size=SEGMENT_CHUNK_SIZE):
                            if not chunk:
                                continue
                            part_file.write(chunk)
                            with progress_lock:
                                downloaded += len(chunk)
                                percent = min(100.0, downloaded * 100.0 / total_bytes)
                                if percent - last_percent >= 1 or downloaded == total_bytes:
                                    last_percent = percent
                                    self._set_progress(task, percent)
                part_paths[idx] = part_path
                return True
            except (requests.RequestException, OSError):
                return False

        with ThreadPoolExecutor(max_workers=segment_count) as executor:
            futures = []
            for idx in range(segment_count):
                start = idx * segment_size
                end = min(total_bytes - 1, start + segment_size - 1)
                futures.append(executor.submit(download_part, idx, start, end))
            all_ok = all(f.result() for f in futures)

        if not all_ok or any(path is None for path in part_paths):
            cleanup_parts()
            return False

        try:
            with save_path.open("wb") as target:
                for path_obj in part_paths:
                    if path_obj is None:
                        return False
                    with path_obj.open("rb") as part_file:
                        shutil.copyfileobj(part_file, target, SEGMENT_CHUNK_SIZE * 2)
        except OSError:
            cleanup_parts()
            return False

        cleanup_parts()
        return True

    def _find_first_valid_node(self, appid: str, total_nodes: int = 6) -> int | None:
        with ThreadPoolExecutor(max_workers=total_nodes) as executor:
            future_map = {
                executor.submit(self._check_overseas_node, appid, node): node
                for node in range(total_nodes)
            }
            for future in as_completed(future_map):
                node = future_map[future]
                if future.result():
                    return node
        return None

    def _check_overseas_node(self, appid: str, node: int) -> bool:
        url = self._get_overseas_download_url(appid, node)
        try:
            response = requests.get(url, timeout=NODE_TIMEOUT)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _get_overseas_download_url(self, appid: str, node: int) -> str:
        base32_id = self._base32_encode(appid)
        return f"https://api-psi-eight-12.vercel.app/download?id={base32_id}&src={node}"

    def _auto_import_lua(self, task: DownloadTask, appid: str) -> bool:
        try:
            self._copy_lua_to_steam(task, appid)
            return True
        except (FileNotFoundError, RuntimeError) as exc:
            self._append_log(task, str(exc))
            return False

    def _copy_manifests_to_depotcache(self, task: DownloadTask, appid: str) -> tuple[int, int]:
        """将下载目录中的所有 .manifest 文件复制到 Steam depotcache 目录。

        Returns:
            (copied, skipped) 元组，分别表示新复制和跳过（已存在）的文件数。
        """
        try:
            game_folder = self._find_downloaded_game_folder(appid)
            steam_root = self._resolve_steam_root()
            depotcache_dir = steam_root / "config" / "depotcache"
            depotcache_dir.mkdir(parents=True, exist_ok=True)
        except (FileNotFoundError, RuntimeError) as exc:
            self._append_log(task, f"无法定位 manifest 目录或 Steam 路径：{exc}")
            return 0, 0

        copied = 0
        skipped = 0
        for manifest_file in game_folder.glob("*.manifest"):
            dest = depotcache_dir / manifest_file.name
            if dest.exists():
                skipped += 1
            else:
                try:
                    shutil.copy2(manifest_file, dest)
                    copied += 1
                    self._append_log(task, f"  已复制 {manifest_file.name}")
                except OSError as exc:
                    self._append_log(task, f"  复制 {manifest_file.name} 失败：{exc}")
        return copied, skipped

    def _find_downloaded_game_folder(self, appid: str) -> Path:
        """返回 download/ 下对应 appid 的游戏目录。"""
        lua_name = f"{appid}.lua"
        for match in self.download_dir.rglob(lua_name):
            if match.is_file() and match.parent != self.download_dir:
                return match.parent
        raise FileNotFoundError(f"未找到 AppID {appid} 的下载目录")

    def _copy_lua_to_steam(self, task: DownloadTask, appid: str) -> None:
        lua_file = self._find_lua_file(appid)
        steam_root = self._resolve_steam_root()
        target_dir = self._stplugin_dir(steam_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / lua_file.name
        shutil.copy2(lua_file, destination)
        self._append_log(task, f"已将 {lua_file} 拷贝到 {destination}")

    def list_imported_games(self) -> dict:
        steam_root = self._resolve_steam_root()
        stplugin_dir = self._stplugin_dir(steam_root)
        depotcache_dirs = self._depotcache_dirs(steam_root)
        items = []
        if stplugin_dir.exists():
            for lua_file in sorted(stplugin_dir.glob("*.lua"), key=lambda item: item.name.lower()):
                appid = self._appid_from_lua(lua_file)
                manifests = self._manifest_pairs_from_lua(lua_file)
                existing_manifests = [
                    str(path)
                    for depot_id, manifest_id in manifests
                    for path in self._manifest_paths(depotcache_dirs, depot_id, manifest_id)
                    if path.is_file()
                ]
                items.append(
                    {
                        "appid": appid,
                        "name": self._resolve_imported_game_name(appid),
                        "lua_path": str(lua_file),
                        "manifest_count": len(manifests),
                        "existing_manifest_count": len(existing_manifests),
                        "updated_at": lua_file.stat().st_mtime,
                    }
                )
        return {
            "steam_root": str(steam_root),
            "stplugin_dir": str(stplugin_dir),
            "items": items,
        }

    def list_installed_games(self) -> dict:
        steam_root = self._resolve_steam_root()
        items: list[dict] = []
        seen_appids: set[str] = set()
        for library_root in self._steam_library_roots(steam_root):
            steamapps_dir = library_root / "steamapps"
            if not steamapps_dir.exists():
                continue
            for manifest in sorted(steamapps_dir.glob("appmanifest_*.acf")):
                parsed = self._parse_app_manifest(manifest)
                appid = parsed.get("appid", "")
                if not appid or appid in seen_appids:
                    continue
                seen_appids.add(appid)
                installdir = parsed.get("installdir", "")
                install_path = steamapps_dir / "common" / installdir if installdir else None
                name = parsed.get("name") or self._resolve_imported_game_name(appid)
                items.append(
                    {
                        "appid": appid,
                        "name": name,
                        "installdir": installdir,
                        "install_path": str(install_path) if install_path else "",
                        "library_path": str(library_root),
                        "manifest_path": str(manifest),
                        "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                        "updated_at": manifest.stat().st_mtime,
                    }
                )
        items.sort(key=lambda item: item["name"].lower())
        return {
            "steam_root": str(steam_root),
            "items": items,
        }

    def delete_imported_game(self, appid: str) -> dict:
        if not re.fullmatch(r"\d+", appid):
            raise ValueError("AppID 必须是数字")
        steam_root = self._resolve_steam_root()
        stplugin_dir = self._stplugin_dir(steam_root)
        lua_file = stplugin_dir / f"{appid}.lua"
        if not lua_file.exists():
            raise FileNotFoundError(f"未找到已入库文件：{lua_file}")
        return self._delete_import_artifacts(steam_root, lua_file)

    def clear_all_imports(self) -> dict:
        steam_root = self._resolve_steam_root()
        stplugin_dir = self._stplugin_dir(steam_root)
        summary = {"lua_deleted": 0, "manifest_deleted": 0, "errors": []}
        if not stplugin_dir.exists():
            return summary
        for lua_file in sorted(stplugin_dir.glob("*.lua"), key=lambda item: item.name.lower()):
            result = self._delete_import_artifacts(steam_root, lua_file, missing_ok=True)
            summary["lua_deleted"] += result["lua_deleted"]
            summary["manifest_deleted"] += result["manifest_deleted"]
            summary["errors"].extend(result["errors"])
        return summary

    def _delete_import_artifacts(
        self, steam_root: Path, lua_file: Path, missing_ok: bool = False
    ) -> dict:
        depotcache_dirs = self._depotcache_dirs(steam_root)
        result = {
            "appid": self._appid_from_lua(lua_file),
            "lua_deleted": 0,
            "manifest_deleted": 0,
            "errors": [],
        }
        manifests = self._manifest_pairs_from_lua(lua_file) if lua_file.exists() else []
        if lua_file.exists():
            if self._safe_unlink_under(steam_root, lua_file, result["errors"]):
                result["lua_deleted"] += 1
        elif not missing_ok:
            result["errors"].append(f"未找到 {lua_file}")

        for depot_id, manifest_id in manifests:
            for manifest_path in self._manifest_paths(depotcache_dirs, depot_id, manifest_id):
                if manifest_path.is_file() and self._safe_unlink_under(
                    steam_root, manifest_path, result["errors"]
                ):
                    result["manifest_deleted"] += 1
        return result

    def _safe_unlink_under(self, root: Path, path: Path, errors: list[str]) -> bool:
        try:
            root_resolved = root.resolve()
            path_resolved = path.resolve()
            path_resolved.relative_to(root_resolved)
            path_resolved.unlink()
            return True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"删除 {path} 失败：{exc}")
            return False

    @staticmethod
    def _stplugin_dir(steam_root: Path) -> Path:
        return steam_root / "config" / "stplug-in"

    @staticmethod
    def _depotcache_dirs(steam_root: Path) -> tuple[Path, Path]:
        return (
            steam_root / "config" / "depotcache",
            steam_root / "depotcache",
        )

    @staticmethod
    def _manifest_paths(depotcache_dirs: Iterable[Path], depot_id: str, manifest_id: str) -> list[Path]:
        file_name = f"{depot_id}_{manifest_id}.manifest"
        return [directory / file_name for directory in depotcache_dirs]

    @staticmethod
    def _manifest_pairs_from_lua(lua_file: Path) -> list[tuple[str, str]]:
        try:
            content = lua_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        return re.findall(r"setManifestid\(\s*(\d+)\s*,\s*[\"'](\d+)[\"']", content)

    @staticmethod
    def _appid_from_lua(lua_file: Path) -> str:
        if re.fullmatch(r"\d+", lua_file.stem):
            return lua_file.stem
        try:
            content = lua_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return lua_file.stem
        match = re.search(r"addappid\(\s*(\d+)", content)
        return match.group(1) if match else lua_file.stem

    def _find_downloaded_game_name(self, appid: str) -> str | None:
        if not self.download_dir.exists():
            return None
        file_name = f"{appid}.lua"
        for match in self.download_dir.rglob(file_name):
            if match.is_file() and match.parent != self.download_dir:
                return match.parent.name
        return None

    def _resolve_imported_game_name(self, appid: str) -> str:
        local_name = self._find_downloaded_game_name(appid)
        if local_name:
            self._game_name_cache[appid] = local_name
            return local_name
        cached_name = self._game_name_cache.get(appid)
        if cached_name:
            return cached_name
        steam_name = self._fetch_game_name_for_import(appid)
        if steam_name:
            self._game_name_cache[appid] = steam_name
            return steam_name
        return "未知游戏"

    def _fetch_game_name_for_import(self, appid: str) -> str | None:
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": appid, "cc": "CN", "l": "schinese", "filters": "basic"}
        try:
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            payload = resp.json().get(str(appid))
        except (requests.RequestException, ValueError, TypeError):
            payload = None
        if payload and payload.get("success"):
            name = payload.get("data", {}).get("name")
            if name:
                return str(name)

        base32_id = self._base32_encode(appid)
        proxy_url = f"https://api-psi-eight-12.vercel.app/proxy?id={base32_id}"
        try:
            resp = requests.get(proxy_url, timeout=8)
            resp.raise_for_status()
        except requests.RequestException:
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
        game_info_div = soup.find("div", class_="game-info")
        title = game_info_div.find("h2") if game_info_div else None
        name = title.get_text(strip=True) if title else ""
        return name or None

    def _find_lua_file(self, appid: str) -> Path:
        file_name = f"{appid}.lua"
        search_paths = [self.download_dir / file_name, self.base_dir / file_name]
        for path in search_paths:
            if path.is_file():
                return path
        if self.download_dir.exists():
            for match in self.download_dir.rglob(file_name):
                if match.is_file():
                    return match
        raise FileNotFoundError(f"未找到 {file_name}，请确认文件位于 download 目录或当前目录下。")

    def _resolve_steam_root(self) -> Path:
        for key in STEAM_ENV_KEYS:
            steam_path = os.environ.get(key)
            if steam_path:
                candidate = Path(steam_path).expanduser().resolve()
                if candidate.exists():
                    return candidate
        registry_path = self._read_steam_path_from_registry()
        if registry_path and registry_path.exists():
            return registry_path
        for path in DEFAULT_STEAM_PATHS:
            candidate = Path(path)
            if candidate.exists():
                return candidate
        raise RuntimeError("未能自动定位 Steam 安装路径，请设置 STEAM_PATH 或手动指定。")

    def _steam_library_roots(self, steam_root: Path) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()

        def add_root(path: Path) -> None:
            normalized = str(path.resolve())
            if normalized not in seen and path.exists():
                seen.add(normalized)
                roots.append(path)

        add_root(steam_root)
        library_file = steam_root / "steamapps" / "libraryfolders.vdf"
        if not library_file.exists():
            return roots
        try:
            content = library_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return roots
        for raw_path in re.findall(r'"path"\s*"([^"]+)"', content):
            candidate = Path(raw_path.replace('\\\\', '\\')).expanduser()
            add_root(candidate)
        return roots

    @staticmethod
    def _parse_app_manifest(manifest_path: Path) -> dict[str, str]:
        try:
            content = manifest_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {}
        pairs = dict(re.findall(r'"([^"]+)"\s*"([^"]*)"', content))
        return {
            "appid": pairs.get("appid", ""),
            "name": pairs.get("name", ""),
            "installdir": pairs.get("installdir", ""),
        }

    def _read_steam_path_from_registry(self) -> Optional[Path]:
        if winreg is None:
            return None
        registry_keys = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        )
        for hive, subkey in registry_keys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "SteamPath")
                    if value:
                        return Path(value).expanduser().resolve()
            except OSError:
                continue
        return None

    def _collect_game_info(self, task: DownloadTask, appid: str) -> tuple[str | None, str | None, str]:
        name = None
        header_url = None

        api_name, api_img = self._fetch_game_info(task, appid)
        if api_name:
            name = api_name
        if api_img:
            header_url = api_img

        if not name or not header_url:
            proxy_name, proxy_img = self._fetch_game_info_from_proxy(task, appid)
            name = name or proxy_name
            header_url = header_url or proxy_img

        folder_name = self._sanitize_filename(name) if name else appid
        return name, header_url, folder_name

    def _fetch_game_info(self, task: DownloadTask, appid: str) -> tuple[str | None, str | None]:
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": appid, "cc": "CN", "l": "schinese"}
        try:
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as exc:
            self._append_log(task, f"获取游戏信息失败：{exc}")
            return None, None

        payload = resp.json().get(str(appid))
        if not payload or not payload.get("success"):
            return None, None
        data = payload.get("data", {})
        return data.get("name"), data.get("header_image")

    def _fetch_game_info_from_proxy(self, task: DownloadTask, appid: str) -> tuple[str | None, str | None]:
        base32_id = self._base32_encode(appid)
        url = f"https://api-psi-eight-12.vercel.app/proxy?id={base32_id}"
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
        except requests.RequestException as exc:
            self._append_log(task, f"获取代理页面失败：{exc}")
            return None, None

        soup = BeautifulSoup(resp.content, "html.parser")
        game_info_div = soup.find("div", class_="game-info")
        if not game_info_div:
            return None, None

        name = None
        header_url = None
        title = game_info_div.find("h2")
        if title:
            name = title.get_text(strip=True)
        img_tag = game_info_div.find("img")
        if img_tag and img_tag.get("src"):
            header_url = img_tag["src"]
        return name, header_url

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
        return cleaned or "steam_app"

    @staticmethod
    def _base32_encode(input_str: str) -> str:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        bits = "".join(bin(ord(c))[2:].zfill(8) for c in input_str)
        result = []
        for i in range(0, len(bits), 5):
            chunk = bits[i : i + 5].ljust(5, "0")
            result.append(alphabet[int(chunk, 2)])
        return "".join(result)

    def _must_get_task(self, task_id: str) -> DownloadTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("任务不存在")
            return task

    def _append_log(self, task: DownloadTask, message: str) -> None:
        with self._lock:
            task.logs.append(message)
            task.updated_at = time()

    def _set_progress(self, task: DownloadTask, value: float) -> None:
        with self._lock:
            task.progress = max(0.0, min(100.0, float(value)))
            task.updated_at = time()
