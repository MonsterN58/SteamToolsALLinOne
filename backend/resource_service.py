"""GBE Fork 资源管理服务 —— 检测与下载 Steam 模拟器 DLL。"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import requests

from backend.paths import get_assets_dir

BASE_DIR = get_assets_dir()

EMU_DLL_DIR = BASE_DIR / "resources" / "crack" / "emu_dlls"
STABLE_DIR = EMU_DLL_DIR / "stable"
EXPERIMENTAL_DIR = EMU_DLL_DIR / "experimental"

GBE_FORK_REPO = "Detanup01/gbe_fork"
GITHUB_API = "https://api.github.com"

# GitHub 代理前缀（国内加速）
GITHUB_PROXY_PREFIXES = (
    "https://gh.llkk.cc/https://github.com",
    "https://ghproxy.net/https://github.com",
)

GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "SteamToolsManager/2.0",
}

# ── 下载进度状态 ─────────────────────────────────────────────
_progress: dict[str, Any] = {"status": "idle", "progress": 0, "message": ""}
_progress_lock = threading.Lock()


def _set_progress(status: str, progress: int, message: str) -> None:
    with _progress_lock:
        _progress.update({"status": status, "progress": progress, "message": message})


def get_download_progress() -> dict:
    """返回当前下载进度。"""
    with _progress_lock:
        return dict(_progress)


# ── 资源检测 ──────────────────────────────────────────────────

def check_resources() -> dict:
    """检测 GBE Fork DLL 资源是否存在。"""
    STABLE_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENTAL_DIR.mkdir(parents=True, exist_ok=True)

    stable = sorted(f.name for f in STABLE_DIR.iterdir() if f.suffix.lower() == ".dll")
    experimental = sorted(f.name for f in EXPERIMENTAL_DIR.iterdir() if f.suffix.lower() == ".dll")

    # 至少有一个 steam_api*.dll 才算就绪
    ready = any("steam_api" in n.lower() for n in stable)

    return {
        "ready": ready,
        "stable": stable,
        "experimental": experimental,
        "stable_dir": str(STABLE_DIR),
        "experimental_dir": str(EXPERIMENTAL_DIR),
    }


# ── 异步下载 ──────────────────────────────────────────────────

def start_download_gbe_fork() -> dict:
    """启动后台线程从 GitHub 下载 GBE Fork DLL 资源。"""
    with _progress_lock:
        if _progress.get("status") in ("fetching", "downloading", "extracting"):
            return {"ok": True, "message": "下载已在进行中"}

    t = threading.Thread(target=_download_worker, daemon=True)
    t.start()
    return {"ok": True, "message": "已启动下载"}


def _download_worker() -> None:
    """后台下载 GBE Fork 最新 release 并解压。"""
    try:
        _set_progress("fetching", 0, "正在查询 GBE Fork 最新版本…")

        # 1. 获取最新 release 信息
        release_info = _fetch_latest_release()
        if not release_info:
            _set_progress("error", 0, "无法获取 GBE Fork 最新版本信息，请检查网络连接")
            return

        tag = release_info.get("tag_name", "unknown")
        assets = release_info.get("assets", [])

        # 2. 查找 Windows release 和 debug 资产
        win_release_asset = None
        win_debug_asset = None
        for asset in assets:
            name = asset.get("name", "")
            if name == "emu-win-release.7z":
                win_release_asset = asset
            elif name == "emu-win-debug.7z":
                win_debug_asset = asset

        if not win_release_asset:
            _set_progress("error", 0, f"未找到 Windows Release 资产（版本 {tag}）")
            return

        release_size_mb = win_release_asset.get("size", 0) / (1024 * 1024)
        _set_progress("fetching", 5, f"找到版本 {tag}，Release 约 {release_size_mb:.1f} MB，开始下载…")

        # 3. 下载稳定版 (emu-win-release.7z)
        release_url = win_release_asset.get("browser_download_url", "")
        release_data = _download_with_proxy(release_url, "稳定版", total_size=win_release_asset.get("size", 0))
        if release_data is None:
            return  # 错误已在函数内设置

        # 4. 下载实验版 (emu-win-debug.7z)，可选
        debug_data = None
        if win_debug_asset:
            debug_size_mb = win_debug_asset.get("size", 0) / (1024 * 1024)
            _set_progress("downloading", 50, f"正在下载实验版（约 {debug_size_mb:.1f} MB）…")
            debug_url = win_debug_asset.get("browser_download_url", "")
            debug_data = _download_with_proxy(debug_url, "实验版", total_size=win_debug_asset.get("size", 0), base_progress=50, progress_range=30)

        # 5. 解压
        _set_progress("extracting", 80, "正在解压稳定版…")
        _extract_and_place(release_data, STABLE_DIR, "stable")

        if debug_data:
            _set_progress("extracting", 90, "正在解压实验版…")
            _extract_and_place(debug_data, EXPERIMENTAL_DIR, "experimental")

        # 6. 完成
        _set_progress("done", 100, f"GBE Fork {tag} 下载完成，DLL 已就绪")

    except Exception as exc:
        _set_progress("error", 0, f"下载失败: {exc}")


def _fetch_latest_release() -> dict | None:
    """从 GitHub API 获取 GBE Fork 最新 release 信息。"""
    url = f"{GITHUB_API}/repos/{GBE_FORK_REPO}/releases/latest"
    try:
        resp = requests.get(url, headers=GITHUB_HEADERS, timeout=(10, 30))
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


def _download_with_proxy(
    url: str,
    label: str,
    total_size: int = 0,
    base_progress: int = 5,
    progress_range: int = 45,
) -> bytes | None:
    """下载文件，优先直连，失败后尝试代理。返回下载的字节数据。"""
    # 构造下载 URL 列表：先直连，再代理
    urls_to_try: list[tuple[str, str, dict | None]] = [
        (f"{label}（直连）", url, GITHUB_HEADERS),
    ]
    for idx, prefix in enumerate(GITHUB_PROXY_PREFIXES, start=1):
        proxied_url = url.replace("https://github.com", prefix)
        urls_to_try.append((f"{label}（代理{idx}）", proxied_url, None))

    last_error = ""
    for attempt_label, download_url, headers in urls_to_try:
        try:
            _set_progress("downloading", base_progress, f"正在下载 {attempt_label}…")
            resp = requests.get(download_url, headers=headers, stream=True, timeout=(15, 120))
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue

            content_length = int(resp.headers.get("content-length", 0)) or total_size
            downloaded = 0
            chunks: list[bytes] = []

            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if content_length > 0:
                        pct = base_progress + int((downloaded / content_length) * progress_range)
                        size_mb = downloaded / (1024 * 1024)
                        _set_progress("downloading", pct, f"正在下载 {attempt_label}（{size_mb:.1f} MB）…")

            return b"".join(chunks)

        except requests.RequestException as exc:
            last_error = str(exc)
            continue

    _set_progress("error", 0, f"所有下载通道均失败: {last_error}")
    return None


def _extract_and_place(data: bytes, target_dir: Path, subdir_name: str) -> None:
    """解压 7z 数据并将 DLL 放入目标目录。

    GBE Fork 的 7z 内部结构示例：
      emu-win-release/
        experimental/
          x64/steam_api64.dll
          x32/steam_api.dll
        regular/
          x64/steam_api64.dll
          x32/steam_api.dll
        steamclient_experimental/
          steamclient64.dll
          steamclient.dll
        ...
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    # 写入临时 7z 文件
    tmp_7z = target_dir / f"_tmp_download.7z"
    tmp_extract = target_dir / f"_tmp_extract"
    try:
        tmp_7z.write_bytes(data)

        # 尝试用 py7zr 解压
        try:
            import py7zr
            with py7zr.SevenZipFile(str(tmp_7z), "r") as z:
                z.extractall(path=str(tmp_extract))
        except Exception:
            # 回退到 7z 命令行
            try:
                subprocess.run(
                    ["7z", "x", str(tmp_7z), f"-o{tmp_extract}", "-y"],
                    capture_output=True, timeout=120, check=True,
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                # 最后尝试用 7za
                try:
                    subprocess.run(
                        ["7za", "x", str(tmp_7z), f"-o{tmp_extract}", "-y"],
                        capture_output=True, timeout=120, check=True,
                    )
                except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                    _set_progress("error", 0, f"解压失败（需要 py7zr 或 7z/7za）: {exc}")
                    return

        # 在解压目录中查找 DLL 并复制到目标目录
        _place_dlls_from_extract(tmp_extract, target_dir, subdir_name)

    finally:
        # 清理临时文件
        if tmp_7z.exists():
            tmp_7z.unlink()
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)


def _place_dlls_from_extract(extract_root: Path, target_dir: Path, subdir_name: str) -> None:
    """从解压目录中查找并放置 DLL 文件。

    根据子目录名称决定放置策略：
    - stable: 放置 regular/x64 和 regular/x32 下的 DLL
    - experimental: 放置 experimental/x64 和 experimental/x32 下的 DLL
    同时，steamclient 相关 DLL 也需要放置。
    """
    # 遍历解压目录，查找所有 DLL
    dll_map: dict[str, Path] = {}  # dll_name -> source_path

    for dll_path in extract_root.rglob("*.dll"):
        dll_name = dll_path.name
        rel_path = dll_path.relative_to(extract_root)
        rel_str = str(rel_path).lower().replace("\\", "/")

        if subdir_name == "stable":
            # 稳定版：取 regular 目录下的 DLL
            if "regular" in rel_str:
                dll_map[dll_name] = dll_path
            # 同时取 steamclient 相关（非 experimental 目录）
            elif "steamclient" in dll_name.lower() and "experimental" not in rel_str:
                dll_map[dll_name] = dll_path
        elif subdir_name == "experimental":
            # 实验版：取 experimental 目录下的 steam_api DLL
            if "experimental" in rel_str and "steamclient" not in dll_name.lower():
                dll_map[dll_name] = dll_path
            # steamclient_experimental 目录下的 steamclient DLL
            elif "steamclient_experimental" in rel_str:
                dll_map[dll_name] = dll_path

    # 如果上面的精确匹配没找到，回退到全部 DLL
    if not dll_map:
        for dll_path in extract_root.rglob("*.dll"):
            dll_name = dll_path.name
            # 优先 x64 版本
            if dll_name not in dll_map:
                dll_map[dll_name] = dll_path

    # 复制 DLL 到目标目录
    for dll_name, src_path in dll_map.items():
        dst = target_dir / dll_name
        shutil.copy2(src_path, dst)
