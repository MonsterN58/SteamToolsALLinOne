"""Steam 工具箱后端服务 —— 网络加速 / 账号切换 / 库存游戏 / 本地令牌"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from backend.paths import get_base_dir

try:
    import winreg
except ImportError:
    winreg = None

BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STEAM_ENV_KEYS = ("STEAM_PATH", "SteamPath", "STEAMPATH")
DEFAULT_STEAM_PATHS = (
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Program Files (x86)\Steam",
)
STEAM_ID64_BASE = 76561197960265728
STEAM_DEFAULT_AVATAR_HASH = "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
STEAM_DEFAULT_AVATAR_URL = f"https://avatars.steamstatic.com/{STEAM_DEFAULT_AVATAR_HASH}_medium.jpg"


# ─── 通用工具 ──────────────────────────────────────────────


def _resolve_steam_root() -> Path:
    for key in STEAM_ENV_KEYS:
        steam_path = os.environ.get(key)
        if steam_path:
            candidate = Path(steam_path).expanduser().resolve()
            if candidate.exists():
                return candidate
    if winreg:
        for hive, subkey in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    value, _ = winreg.QueryValueEx(k, "SteamPath")
                    if value:
                        p = Path(value).expanduser().resolve()
                        if p.exists():
                            return p
            except OSError:
                continue
    for path in DEFAULT_STEAM_PATHS:
        candidate = Path(path)
        if candidate.exists():
            return candidate
    raise RuntimeError("未能自动定位 Steam 安装路径")


def _parse_vdf(text: str) -> dict:
    """简易 Valve VDF 文本解析器（支持嵌套）"""
    result: dict = {}
    stack: list[dict] = [result]
    current_key: str | None = None
    for m in re.finditer(r'"([^"]*)"|\{|\}', text):
        if m.group(1) is not None:
            value = m.group(1)
            if current_key is None:
                current_key = value
            else:
                stack[-1][current_key] = value
                current_key = None
        elif m.group(0) == "{":
            new_dict: dict = {}
            if current_key is not None:
                stack[-1][current_key] = new_dict
                stack.append(new_dict)
                current_key = None
        elif m.group(0) == "}":
            if len(stack) > 1:
                stack.pop()
    return result


def _steam_library_roots(steam_root: Path) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        n = str(p.resolve())
        if n not in seen and p.exists():
            seen.add(n)
            roots.append(p)

    add(steam_root)
    lf = steam_root / "steamapps" / "libraryfolders.vdf"
    if lf.exists():
        try:
            content = lf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return roots
        for raw in re.findall(r'"path"\s*"([^"]+)"', content):
            add(Path(raw.replace("\\\\", "\\")).expanduser())
    return roots


def _vdf_get(node: dict, key: str):
    if not isinstance(node, dict):
        return None
    key_lower = key.lower()
    for actual_key, value in node.items():
        if isinstance(actual_key, str) and actual_key.lower() == key_lower:
            return value
    return None


@functools.lru_cache(maxsize=256)
def _resolve_profile_ips(domain: str, hints: tuple[str, ...] = ()) -> tuple[str, ...]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(ip: str) -> None:
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+", ip) and ip not in seen:
            seen.add(ip)
            candidates.append(ip)

    for ip in hints:
        add(ip)

    try:
        infos = socket.getaddrinfo(domain, 443, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        infos = []

    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            add(sockaddr[0])

    return tuple(candidates[:4])


# ═══════════════════════════════════════════════════════════
#  1. 网络加速 (Accelerator)
# ═══════════════════════════════════════════════════════════

HOSTS_MARKER_START = "# ── SteamToolsManager Accelerator Start ──"
HOSTS_MARKER_END = "# ── SteamToolsManager Accelerator End ──"

if os.name == "nt":
    HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
else:
    HOSTS_PATH = Path("/etc/hosts")

# 预设加速规则（域名 → 已知候选 IP，留空时运行时自动解析）
ACCELERATION_PROFILES: dict[str, dict[str, list[str]]] = {
    "Steam 商店/社区": {
        "store.steampowered.com": ["23.40.215.49", "23.40.215.56", "104.75.142.50"],
        "steamcommunity.com": ["23.40.215.49", "23.40.215.56", "104.75.142.50"],
        "api.steampowered.com": ["23.40.215.49", "104.75.142.50"],
        "help.steampowered.com": ["23.40.215.49", "104.75.142.50"],
        "login.steampowered.com": ["23.40.215.49", "104.75.142.50"],
    },
    "Steam 静态资源": {
        "cdn.cloudflare.steamstatic.com": ["104.16.0.1", "104.16.1.1"],
        "media.steampowered.com": ["23.40.215.49", "104.75.142.50"],
        "steamcdn-a.akamaihd.net": ["23.40.215.49", "23.40.215.56"],
        "steambroadcast.akamaized.net": ["23.40.215.49"],
    },
    "GitHub 加速": {
        "github.com": ["140.82.121.4", "140.82.121.3"],
        "raw.githubusercontent.com": ["185.199.108.133", "185.199.109.133"],
        "github.githubassets.com": ["185.199.108.154", "185.199.109.154"],
        "avatars.githubusercontent.com": ["185.199.108.133", "185.199.109.133"],
    },
    "Epic Games": {
        "store.epicgames.com": [],
        "launcher-public-service-prod06.ol.epicgames.com": [],
        "account-public-service-prod.ol.epicgames.com": [],
        "cdn1.epicgames.com": [],
        "epicgames-download1.akamaized.net": [],
    },
    "Ubisoft Connect": {
        "ubisoftconnect.com": [],
        "connect.ubisoft.com": [],
        "public-ubiservices.ubi.com": [],
        "static2.cdn.ubi.com": [],
        "ubistatic3-a.akamaihd.net": [],
    },
    "EA App / Origin": {
        "www.ea.com": [],
        "accounts.ea.com": [],
        "api1.origin.com": [],
        "download.dm.origin.com": [],
        "origin-a.akamaihd.net": [],
    },
    "Riot / Valorant": {
        "auth.riotgames.com": [],
        "riot-client.secure.dyn.riotcdn.net": [],
        "valorant.secure.dyn.riotcdn.net": [],
        "lol.secure.dyn.riotcdn.net": [],
        "images.contentstack.io": [],
    },
    "Battle.net / Blizzard": {
        "battle.net": [],
        "www.blizzard.com": [],
        "cdn.blizzard.com": [],
        "us.patch.battle.net": [],
        "eu.patch.battle.net": [],
    },
    "GOG Galaxy": {
        "www.gog.com": [],
        "embed.gog.com": [],
        "api.gog.com": [],
        "images.gog-statics.com": [],
        "gog-cdn-fastly.gog.com": [],
    },
}


class AcceleratorService:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def get_profiles(self) -> dict:
        """返回所有预设加速规则"""
        profiles: dict[str, dict[str, str]] = {}
        for name, rules in ACCELERATION_PROFILES.items():
            resolved_rules: dict[str, str] = {}
            for domain, hints in rules.items():
                candidates = _resolve_profile_ips(domain, tuple(hints))
                if candidates:
                    resolved_rules[domain] = candidates[0]
            profiles[name] = resolved_rules
        return profiles

    def get_status(self) -> dict:
        """检查当前加速状态"""
        try:
            content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            active = HOSTS_MARKER_START in content
            entries: list[dict] = []
            if active:
                in_block = False
                for line in content.splitlines():
                    if HOSTS_MARKER_START in line:
                        in_block = True
                        continue
                    if HOSTS_MARKER_END in line:
                        in_block = False
                        continue
                    if in_block:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split()
                            if len(parts) >= 2:
                                entries.append({"ip": parts[0], "domain": parts[1]})
            return {"active": active, "entries": entries}
        except OSError as e:
            return {"active": False, "entries": [], "error": str(e)}

    def test_latency(self, host: str, ip: str, port: int = 443, timeout: float = 3.0) -> dict:
        """测试到指定 IP 的 TCP 连接延迟（毫秒）"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            start = time.time()
            sock.connect((ip, port))
            latency = round((time.time() - start) * 1000, 1)
            sock.close()
            return {"ip": ip, "host": host, "latency_ms": latency, "ok": True}
        except (socket.timeout, OSError):
            return {"ip": ip, "host": host, "latency_ms": -1, "ok": False}

    def test_profile_latency(self, profile_name: str) -> list[dict]:
        """测试指定配置文件中所有域名的延迟"""
        rules = ACCELERATION_PROFILES.get(profile_name, {})
        results = []
        for domain, hints in rules.items():
            for ip in _resolve_profile_ips(domain, tuple(hints)):
                results.append(self.test_latency(domain, ip))
        return results

    def enable(self, rules: dict[str, str]) -> dict:
        """启用加速（写入 hosts 文件）"""
        if not rules:
            return {"ok": False, "error": "没有提供加速规则"}
        with self._lock:
            try:
                content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = ""
            # 移除旧的加速条目
            content = self._remove_block(content)
            # 构建新条目
            block_lines = [HOSTS_MARKER_START]
            applied = 0
            for domain, ip in rules.items():
                # 安全检查：确保域名和 IP 合法
                if not re.match(r'^[a-zA-Z0-9.\-]+$', domain):
                    continue
                if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', ip):
                    continue
                block_lines.append(f"{ip} {domain}")
                applied += 1
            block_lines.append(HOSTS_MARKER_END)
            content = content.rstrip("\n") + "\n\n" + "\n".join(block_lines) + "\n"
            try:
                HOSTS_PATH.write_text(content, encoding="utf-8")
                # 刷新 DNS 缓存
                if os.name == "nt":
                    subprocess.run(
                        ["ipconfig", "/flushdns"],
                        capture_output=True,
                        creationflags=0x08000000,
                    )
                return {"ok": True, "count": applied}
            except PermissionError:
                return {
                    "ok": False,
                    "error": "权限不足，请以管理员身份运行程序以修改 hosts 文件",
                }
            except OSError as e:
                return {"ok": False, "error": str(e)}

    def disable(self) -> dict:
        """禁用加速（移除 hosts 文件中的条目）"""
        with self._lock:
            try:
                content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return {"ok": True}
            new_content = self._remove_block(content)
            try:
                HOSTS_PATH.write_text(new_content, encoding="utf-8")
                if os.name == "nt":
                    subprocess.run(
                        ["ipconfig", "/flushdns"],
                        capture_output=True,
                        creationflags=0x08000000,
                    )
                return {"ok": True}
            except PermissionError:
                return {
                    "ok": False,
                    "error": "权限不足，请以管理员身份运行程序以修改 hosts 文件",
                }
            except OSError as e:
                return {"ok": False, "error": str(e)}

    @staticmethod
    def _remove_block(content: str) -> str:
        lines = content.splitlines()
        new_lines: list[str] = []
        skip = False
        for line in lines:
            if HOSTS_MARKER_START in line:
                skip = True
                continue
            if HOSTS_MARKER_END in line:
                skip = False
                continue
            if not skip:
                new_lines.append(line)
        # 移除末尾多余空行
        result = "\n".join(new_lines)
        return result.rstrip("\n") + "\n" if result.strip() else ""


# ═══════════════════════════════════════════════════════════
#  2. 账号切换 (Account Switching)
# ═══════════════════════════════════════════════════════════


class AccountService:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def list_accounts(self) -> list[dict]:
        """列出本机已登录过的 Steam 账号"""
        try:
            steam_root = _resolve_steam_root()
        except RuntimeError:
            return []
        loginusers = steam_root / "config" / "loginusers.vdf"
        if not loginusers.exists():
            return []
        try:
            text = loginusers.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        data = _parse_vdf(text)
        users_dict = data.get("users") or data.get("Users") or {}
        current_auto = self._get_auto_login_user()

        accounts: list[dict] = []
        for steam_id, info in users_dict.items():
            if not isinstance(info, dict):
                continue
            account_name = info.get("AccountName", "")
            persona = info.get("PersonaName", account_name)
            remember = info.get("RememberPassword", "0") == "1"
            most_recent = info.get("MostRecent", "0") == "1"
            timestamp = info.get("Timestamp", "0")
            avatar_hash = self._read_avatar_hash(steam_root, steam_id)
            avatar_url = self._build_avatar_url(avatar_hash)
            accounts.append({
                "steam_id": steam_id,
                "account_name": account_name,
                "persona_name": persona,
                "remember_password": remember,
                "most_recent": most_recent,
                "is_current": account_name == current_auto,
                "timestamp": int(timestamp) if timestamp.isdigit() else 0,
                "avatar_url": avatar_url,
                "default_avatar_url": STEAM_DEFAULT_AVATAR_URL,
                "avatar_hash": avatar_hash,
                "has_custom_avatar": bool(avatar_hash),
            })
        accounts.sort(key=lambda a: (-a["is_current"], -a["most_recent"], -a["timestamp"]))
        return accounts

    def get_current_account(self) -> dict:
        """获取当前自动登录账号"""
        auto_user = self._get_auto_login_user()
        return {"auto_login_user": auto_user or ""}

    def switch_account(self, steam_id: str, account_name: str) -> dict:
        """切换到指定账号"""
        with self._lock:
            try:
                steam_root = _resolve_steam_root()
            except RuntimeError as e:
                return {"ok": False, "error": str(e)}

            # 1. 关闭 Steam
            self._kill_steam()
            time.sleep(1)

            # 2. 设置 AutoLoginUser
            if winreg:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Valve\Steam",
                        0,
                        winreg.KEY_SET_VALUE,
                    ) as key:
                        winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, account_name)
                        winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)
                except OSError as e:
                    return {"ok": False, "error": f"无法修改注册表: {e}"}

            # 3. 更新 loginusers.vdf 中的 MostRecent 标志
            loginusers = steam_root / "config" / "loginusers.vdf"
            if loginusers.exists():
                try:
                    text = loginusers.read_text(encoding="utf-8", errors="ignore")
                    # 将所有 MostRecent 设为 0
                    text = re.sub(
                        r'("MostRecent"\s*")1(")',
                        r"\g<1>0\g<2>",
                        text,
                    )
                    # 将目标账号的 MostRecent 设为 1
                    # 找到目标 steam_id 的块并修改
                    pattern = re.compile(
                        rf'("{re.escape(steam_id)}".*?"MostRecent"\s*")0(")',
                        re.DOTALL,
                    )
                    text = pattern.sub(r"\g<1>1\g<2>", text, count=1)
                    loginusers.write_text(text, encoding="utf-8")
                except OSError:
                    pass

            # 4. 重启 Steam
            steam_exe = steam_root / "steam.exe"
            if steam_exe.exists():
                try:
                    subprocess.Popen(
                        [str(steam_exe), "-login", account_name],
                        cwd=str(steam_root),
                        creationflags=0x00000008 if os.name == "nt" else 0,
                    )
                except OSError:
                    pass

            return {"ok": True, "switched_to": account_name}

    @staticmethod
    def _get_auto_login_user() -> str:
        if not winreg:
            return ""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AutoLoginUser")
                return value or ""
        except OSError:
            return ""

    @staticmethod
    def _build_avatar_url(avatar_hash: str) -> str:
        cleaned = str(avatar_hash or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}", cleaned):
            return f"https://avatars.steamstatic.com/{cleaned}_medium.jpg"
        return STEAM_DEFAULT_AVATAR_URL

    @staticmethod
    def _steam_id_to_account_id(steam_id: str) -> str:
        try:
            value = int(str(steam_id).strip())
        except (TypeError, ValueError):
            return ""
        if value <= STEAM_ID64_BASE:
            return ""
        return str(value - STEAM_ID64_BASE)

    @classmethod
    def _read_avatar_hash(cls, steam_root: Path, steam_id: str) -> str:
        account_id = cls._steam_id_to_account_id(steam_id)
        if not account_id:
            return ""

        localconfig = steam_root / "userdata" / account_id / "config" / "localconfig.vdf"
        if not localconfig.exists():
            return ""

        try:
            text = localconfig.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

        parsed = _parse_vdf(text)
        root = _vdf_get(parsed, "UserLocalConfigStore")
        if not isinstance(root, dict):
            root = parsed

        friends = _vdf_get(root, "friends")
        if not isinstance(friends, dict):
            return ""

        for key in (account_id, steam_id):
            avatar_info = _vdf_get(friends, key)
            if not isinstance(avatar_info, dict):
                continue
            avatar_hash = _vdf_get(avatar_info, "avatar")
            if isinstance(avatar_hash, str) and re.fullmatch(r"[0-9a-fA-F]{40}", avatar_hash.strip()):
                return avatar_hash.strip().lower()

        return ""

    @staticmethod
    def _kill_steam() -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/IM", "steam.exe"],
                capture_output=True,
                creationflags=0x08000000,
            )
        else:
            subprocess.run(["pkill", "-f", "steam"], capture_output=True)


# ═══════════════════════════════════════════════════════════
#  3. 库存游戏 (Game Library)
# ═══════════════════════════════════════════════════════════


IDLE_STATUS_FILE = "status.json"
IDLE_STOP_FILE = "stop.flag"


def _idle_dir(appid: str) -> Path:
    return DATA_DIR / "idle" / appid


def _write_idle_status(idle_path: Path, status: str, error: str = "") -> None:
    idle_path.mkdir(parents=True, exist_ok=True)
    payload = {"status": status}
    if error:
        payload["error"] = error
    (idle_path / IDLE_STATUS_FILE).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run_idle_helper(appid: str, idle_dir_str: str, api_dll_str: str = "", steam_root_str: str = "") -> int:
    """独立进程中初始化 Steam API，以便 Steam 正确记录该 AppID 处于运行中。"""
    import ctypes as _ct

    idle_path = Path(idle_dir_str).expanduser().resolve()
    stop_file = idle_path / IDLE_STOP_FILE
    api_dll = Path(api_dll_str).expanduser().resolve() if api_dll_str else None
    steam_root = Path(steam_root_str).expanduser().resolve() if steam_root_str else None

    try:
        if stop_file.exists():
            stop_file.unlink()
    except OSError:
        pass

    try:
        if api_dll is None or not api_dll.exists():
            _write_idle_status(idle_path, "error", "未找到可用的 steam_api.dll")
            return 2

        _write_idle_status(idle_path, "starting")
        (idle_path / "steam_appid.txt").write_text(appid, encoding="utf-8")

        old_cwd = Path.cwd()
        old_appid = os.environ.get("SteamAppId")
        old_gameid = os.environ.get("SteamGameId")
        old_path = os.environ.get("PATH", "")
        dll_handles = []
        api = None

        try:
            os.chdir(str(idle_path))
            os.environ["SteamAppId"] = appid
            os.environ["SteamGameId"] = appid

            extra_paths = [str(api_dll.parent)]
            if steam_root and steam_root.exists():
                extra_paths.append(str(steam_root))
            os.environ["PATH"] = os.pathsep.join(extra_paths + [old_path])

            if hasattr(os, "add_dll_directory"):
                for directory in extra_paths:
                    try:
                        dll_handles.append(os.add_dll_directory(directory))
                    except OSError:
                        continue

            loader = _ct.WinDLL if os.name == "nt" else _ct.CDLL
            api = loader(str(api_dll))
            if hasattr(api, "SteamAPI_Init"):
                api.SteamAPI_Init.restype = _ct.c_bool
            if hasattr(api, "SteamAPI_RunCallbacks"):
                api.SteamAPI_RunCallbacks.restype = None
            if hasattr(api, "SteamAPI_Shutdown"):
                api.SteamAPI_Shutdown.restype = None

            if not bool(api.SteamAPI_Init()):
                _write_idle_status(idle_path, "error", "SteamAPI_Init 失败，请确认 Steam 已登录且游戏含官方 steam_api.dll")
                return 3

            _write_idle_status(idle_path, "running")
            while not stop_file.exists():
                try:
                    api.SteamAPI_RunCallbacks()
                except Exception:
                    pass
                time.sleep(2)
            return 0
        finally:
            if api is not None:
                try:
                    api.SteamAPI_Shutdown()
                except Exception:
                    pass
            for handle in dll_handles:
                try:
                    handle.close()
                except Exception:
                    pass
            if old_appid is None:
                os.environ.pop("SteamAppId", None)
            else:
                os.environ["SteamAppId"] = old_appid
            if old_gameid is None:
                os.environ.pop("SteamGameId", None)
            else:
                os.environ["SteamGameId"] = old_gameid
            os.environ["PATH"] = old_path
            os.chdir(str(old_cwd))
    except Exception as exc:  # noqa: BLE001
        _write_idle_status(idle_path, "error", str(exc))
        return 1

class LibraryService:
    def __init__(self) -> None:
        self._idle_procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def list_games(self) -> list[dict]:
        """扫描所有 Steam 库文件夹中的已安装游戏"""
        try:
            steam_root = _resolve_steam_root()
        except RuntimeError:
            return []
        roots = _steam_library_roots(steam_root)
        games: list[dict] = []
        seen_appids: set[str] = set()

        for root in roots:
            steamapps = root / "steamapps"
            if not steamapps.exists():
                continue
            for manifest in steamapps.glob("appmanifest_*.acf"):
                try:
                    info = self._parse_manifest(manifest)
                    if not info.get("appid") or info["appid"] in seen_appids:
                        continue
                    seen_appids.add(info["appid"])
                    info["library_path"] = str(root)
                    info["manifest_path"] = str(manifest)
                    info["header_url"] = (
                        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{info['appid']}/header.jpg"
                    )
                    games.append(info)
                except Exception:
                    continue

        games.sort(key=lambda g: g.get("name", "").lower())
        return games

    def get_game_detail(self, appid: str) -> dict:
        """获取单个游戏的详细信息"""
        games = self.list_games()
        for g in games:
            if g["appid"] == appid:
                # 尝试获取更多信息
                install_dir = Path(g.get("install_path", ""))
                size = 0
                if install_dir.exists():
                    try:
                        for f in install_dir.rglob("*"):
                            if f.is_file():
                                size += f.stat().st_size
                    except OSError:
                        pass
                g["actual_size_bytes"] = size
                g["actual_size"] = self._format_size(size)
                return g
        return {}

    def idle_game(self, appid: str) -> dict:
        """模拟运行游戏（挂游戏时间/掉落卡片）— 使用独立 helper 进程初始化 Steam API。"""
        with self._lock:
            if appid in self._idle_procs:
                proc = self._idle_procs[appid]
                if proc.poll() is None:
                    return {"ok": True, "status": "already_running", "appid": appid}

            try:
                steam_root = _resolve_steam_root()
            except RuntimeError as exc:
                return {"ok": False, "error": str(exc)}

            api_dll: Optional[Path] = None
            games = self.list_games()
            for g in games:
                if g["appid"] == appid:
                    install_path = Path(g.get("install_path", ""))
                    api_dll = self._find_game_api_dll(install_path)
                    break

            if api_dll is None:
                return {"ok": False, "error": "未找到游戏目录中的 steam_api.dll，无法启动挂机"}

            idle_path = _idle_dir(appid)
            idle_path.mkdir(parents=True, exist_ok=True)
            self._safe_unlink(idle_path / IDLE_STOP_FILE)
            self._safe_unlink(idle_path / IDLE_STATUS_FILE)
            (idle_path / "steam_appid.txt").write_text(appid, encoding="utf-8")

            command = self._idle_helper_command(appid, idle_path, api_dll, steam_root)
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=self._no_window_flag(),
                )
            except OSError as exc:
                return {"ok": False, "error": f"启动挂机 helper 失败：{exc}"}

            ok, error = self._wait_idle_ready(proc, idle_path)
            if not ok:
                self._kill_idle_process(proc)
                return {"ok": False, "error": error or "挂机初始化失败"}

            self._idle_procs[appid] = proc
            return {"ok": True, "status": "started", "appid": appid, "pid": proc.pid}

    def stop_idle(self, appid: str) -> dict:
        """停止挂机"""
        with self._lock:
            proc = self._idle_procs.pop(appid, None)
            if proc and proc.poll() is None:
                stop_file = _idle_dir(appid) / IDLE_STOP_FILE
                stop_file.parent.mkdir(parents=True, exist_ok=True)
                stop_file.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._kill_idle_process(proc)
                self._safe_unlink(stop_file)
                return {"ok": True, "stopped": appid}
            return {"ok": True, "message": "未在运行"}

    def stop_all_idle(self) -> dict:
        """停止所有挂机"""
        with self._lock:
            for appid, proc in list(self._idle_procs.items()):
                if proc.poll() is None:
                    stop_file = _idle_dir(appid) / IDLE_STOP_FILE
                    stop_file.parent.mkdir(parents=True, exist_ok=True)
                    stop_file.write_text("stop", encoding="utf-8")
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._kill_idle_process(proc)
            self._idle_procs.clear()
            return {"ok": True}

    def get_idle_status(self) -> list[dict]:
        """获取所有挂机状态"""
        result = []
        for appid, proc in list(self._idle_procs.items()):
            running = proc.poll() is None
            result.append({"appid": appid, "running": running, "pid": proc.pid})
            if not running:
                self._idle_procs.pop(appid, None)
        return result

    @staticmethod
    def _find_game_api_dll(install_path: Path) -> Optional[Path]:
        if not install_path.exists():
            return None
        for dll_name in ("steam_api64.dll", "steam_api.dll"):
            direct = install_path / dll_name
            if direct.exists():
                return direct
        for dll_name in ("steam_api64.dll", "steam_api.dll"):
            for candidate in install_path.rglob(dll_name):
                if candidate.is_file():
                    return candidate
        return None

    @staticmethod
    def _idle_helper_command(appid: str, idle_path: Path, api_dll: Path, steam_root: Path) -> list[str]:
        args = [
            "--idle-helper",
            "--appid",
            appid,
            "--idle-dir",
            str(idle_path),
            "--api-dll",
            str(api_dll),
            "--steam-root",
            str(steam_root),
        ]
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]
        return [sys.executable, "-m", "backend.server", *args]

    @staticmethod
    def _wait_idle_ready(proc: subprocess.Popen, idle_path: Path, timeout: float = 4.0) -> tuple[bool, str]:
        status_file = idle_path / IDLE_STATUS_FILE
        deadline = time.time() + timeout
        while time.time() < deadline:
            if status_file.exists():
                try:
                    payload = json.loads(status_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    payload = {}
                status = str(payload.get("status") or "")
                if status == "running":
                    return True, ""
                if status == "error":
                    return False, str(payload.get("error") or "挂机初始化失败")
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        return False, "挂机初始化超时，Steam 未确认该游戏进入运行状态"

    @staticmethod
    def _kill_idle_process(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                proc.kill()
        except OSError:
            pass

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    @staticmethod
    def _no_window_flag() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    @staticmethod
    def _parse_manifest(path: Path) -> dict:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {}
        pairs = dict(re.findall(r'"([^"]+)"\s*"([^"]*)"', content))
        appid = pairs.get("appid", "")
        name = pairs.get("name", "")
        installdir = pairs.get("installdir", "")
        size = pairs.get("SizeOnDisk", "0")
        state = pairs.get("StateFlags", "0")
        build_id = pairs.get("buildid", "")
        last_updated = pairs.get("LastUpdated", "0")

        # 计算安装路径
        steamapps_dir = path.parent
        install_path = steamapps_dir / "common" / installdir if installdir else ""

        return {
            "appid": appid,
            "name": name,
            "installdir": installdir,
            "install_path": str(install_path) if install_path else "",
            "size_on_disk": int(size) if size.isdigit() else 0,
            "size_display": LibraryService._format_size(int(size) if size.isdigit() else 0),
            "state_flags": int(state) if state.isdigit() else 0,
            "build_id": build_id,
            "last_updated": int(last_updated) if last_updated.isdigit() else 0,
        }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"


# ═══════════════════════════════════════════════════════════
#  4. 本地令牌 (Authenticator)
# ═══════════════════════════════════════════════════════════

STEAM_GUARD_CHARS = "23456789BCDFGHJKMNPQRTVWXY"
TOKENS_FILE = DATA_DIR / "authenticators.json"


class AuthenticatorService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: list[dict] = []
        self._load()

    def _load(self) -> None:
        if TOKENS_FILE.exists():
            try:
                data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
                self._tokens = data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError):
                self._tokens = []

    def _save(self) -> None:
        TOKENS_FILE.write_text(
            json.dumps(self._tokens, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_tokens(self) -> list[dict]:
        """列出所有令牌（不含密钥）"""
        result = []
        for t in self._tokens:
            result.append({
                "id": t["id"],
                "name": t["name"],
                "type": t["type"],
                "issuer": t.get("issuer", ""),
                "digits": t.get("digits", 6),
                "period": t.get("period", 30),
            })
        return result

    def get_code(self, token_id: str) -> dict:
        """获取指定令牌的当前验证码"""
        for t in self._tokens:
            if t["id"] == token_id:
                code = self._generate_code(t)
                remaining = t.get("period", 30) - (int(time.time()) % t.get("period", 30))
                return {
                    "code": code,
                    "remaining_seconds": remaining,
                    "period": t.get("period", 30),
                }
        return {"error": "令牌不存在"}

    def get_all_codes(self) -> list[dict]:
        """获取所有令牌的当前验证码"""
        results = []
        for t in self._tokens:
            code = self._generate_code(t)
            remaining = t.get("period", 30) - (int(time.time()) % t.get("period", 30))
            results.append({
                "id": t["id"],
                "name": t["name"],
                "type": t["type"],
                "issuer": t.get("issuer", ""),
                "code": code,
                "remaining_seconds": remaining,
                "period": t.get("period", 30),
            })
        return results

    def add_token(
        self,
        name: str,
        secret: str,
        token_type: str = "totp",
        issuer: str = "",
        digits: int = 6,
        period: int = 30,
        algorithm: str = "SHA1",
    ) -> dict:
        """添加新令牌"""
        normalized_secret = secret.strip()
        with self._lock:
            for token in self._tokens:
                if token.get("type") == token_type and str(token.get("secret") or "").strip() == normalized_secret:
                    return {"ok": True, "id": token["id"], "duplicate": True}

            # 验证密钥
            try:
                if token_type == "steam":
                    base64.b64decode(normalized_secret)
                else:
                    self._decode_base32(normalized_secret)
            except Exception:
                return {"ok": False, "error": "密钥格式无效"}

            token = {
                "id": str(uuid.uuid4()),
                "name": name,
                "secret": normalized_secret,
                "type": token_type,
                "issuer": issuer,
                "digits": 5 if token_type == "steam" else digits,
                "period": period,
                "algorithm": algorithm,
                "created_at": int(time.time()),
            }
            self._tokens.append(token)
            self._save()
            return {"ok": True, "id": token["id"]}

    def remove_token(self, token_id: str) -> dict:
        """删除令牌"""
        with self._lock:
            original_len = len(self._tokens)
            self._tokens = [t for t in self._tokens if t["id"] != token_id]
            if len(self._tokens) < original_len:
                self._save()
                return {"ok": True}
            return {"ok": False, "error": "令牌不存在"}

    def import_uri(self, uri: str) -> dict:
        """从 otpauth:// URI 导入令牌"""
        parsed = self._parse_otpauth_uri(uri)
        if not parsed:
            return {"ok": False, "error": "无效的 otpauth URI"}
        return self.add_token(**parsed)

    def import_steam_json(self, json_str: str) -> dict:
        """从 Steam Desktop Authenticator (SDA) JSON 导入"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return {"ok": False, "error": "无效的 JSON 格式"}

        shared_secret = data.get("shared_secret", "")
        account_name = data.get("account_name", "")
        if not shared_secret:
            return {"ok": False, "error": "JSON 中缺少 shared_secret 字段"}

        return self.add_token(
            name=account_name or "Steam Guard",
            secret=shared_secret,
            token_type="steam",
            issuer="Steam",
        )

    def scan_local_tokens(self) -> dict:
        """扫描本机常见目录中的 Steam Desktop Authenticator maFiles。"""
        scanned = 0
        imported = 0
        skipped = 0
        sources: list[str] = []

        for token_file in self._candidate_local_token_files():
            parsed = self._parse_local_token_file(token_file)
            if not parsed:
                continue
            scanned += 1
            result = self.add_token(**parsed)
            if result.get("ok") and result.get("duplicate"):
                skipped += 1
            elif result.get("ok"):
                imported += 1
            else:
                skipped += 1
            sources.append(str(token_file))

        return {
            "ok": True,
            "found": scanned,
            "imported": imported,
            "skipped": skipped,
            "sources": sources[:20],
        }

    @staticmethod
    def _candidate_local_token_files() -> list[Path]:
        candidate_dirs: list[Path] = []
        seen_dirs: set[str] = set()

        def add_dir(path: Path) -> None:
            try:
                resolved = str(path.expanduser().resolve())
            except OSError:
                resolved = str(path)
            if resolved in seen_dirs or not path.exists() or not path.is_dir():
                return
            seen_dirs.add(resolved)
            candidate_dirs.append(path)

        appdata = os.environ.get("APPDATA")
        local_appdata = os.environ.get("LOCALAPPDATA")
        home = Path.home()

        for base in filter(None, [appdata, local_appdata]):
            root = Path(base)
            add_dir(root / "Steam Desktop Authenticator" / "maFiles")
            add_dir(root / "SDA" / "maFiles")

        for root in (home / "Documents", home / "Desktop", home / "Downloads"):
            add_dir(root / "Steam Desktop Authenticator" / "maFiles")
            add_dir(root / "SDA" / "maFiles")
            if root.exists():
                for child in root.iterdir():
                    if child.is_dir():
                        add_dir(child / "maFiles")

        files: list[Path] = []
        seen_files: set[str] = set()
        for directory in candidate_dirs:
            for pattern in ("*.maFile", "*.json"):
                for file_path in directory.glob(pattern):
                    if not file_path.is_file():
                        continue
                    key = str(file_path)
                    if key in seen_files:
                        continue
                    seen_files.add(key)
                    files.append(file_path)
        return files

    @staticmethod
    def _parse_local_token_file(path: Path) -> Optional[dict]:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            return None

        session = data.get("Session") if isinstance(data.get("Session"), dict) else {}
        shared_secret = str(data.get("shared_secret") or "").strip()
        if not shared_secret:
            return None

        account_name = (
            str(data.get("account_name") or "").strip()
            or str(session.get("AccountName") or "").strip()
            or path.stem
        )
        return {
            "name": account_name or "Steam Guard",
            "secret": shared_secret,
            "token_type": "steam",
            "issuer": "Steam",
        }

    def _generate_code(self, token: dict) -> str:
        token_type = token.get("type", "totp")
        secret = token["secret"]
        period = token.get("period", 30)
        digits = token.get("digits", 6)
        algorithm = token.get("algorithm", "SHA1")

        if token_type == "steam":
            return self._generate_steam_guard(secret)
        elif token_type == "hotp":
            counter = token.get("counter", 0)
            return self._generate_hotp(secret, counter, digits, algorithm)
        else:
            return self._generate_totp(secret, period, digits, algorithm)

    @staticmethod
    def _generate_steam_guard(shared_secret_b64: str) -> str:
        """生成 Steam Guard 验证码"""
        try:
            shared_secret = base64.b64decode(shared_secret_b64)
        except Exception:
            return "ERROR"
        timestamp = int(time.time())
        time_counter = timestamp // 30
        time_bytes = struct.pack(">Q", time_counter)
        hmac_result = hmac.new(shared_secret, time_bytes, hashlib.sha1).digest()
        offset = hmac_result[19] & 0x0F
        code_int = struct.unpack(">I", hmac_result[offset : offset + 4])[0] & 0x7FFFFFFF
        code = ""
        for _ in range(5):
            code += STEAM_GUARD_CHARS[code_int % len(STEAM_GUARD_CHARS)]
            code_int //= len(STEAM_GUARD_CHARS)
        return code

    @staticmethod
    def _generate_totp(
        secret_b32: str, period: int = 30, digits: int = 6, algorithm: str = "SHA1"
    ) -> str:
        """生成标准 TOTP 验证码"""
        try:
            key = AuthenticatorService._decode_base32(secret_b32)
        except Exception:
            return "ERROR"
        timestamp = int(time.time())
        time_counter = timestamp // period
        time_bytes = struct.pack(">Q", time_counter)
        hash_func = getattr(hashlib, algorithm.lower(), hashlib.sha1)
        hmac_result = hmac.new(key, time_bytes, hash_func).digest()
        offset = hmac_result[-1] & 0x0F
        code_int = struct.unpack(">I", hmac_result[offset : offset + 4])[0] & 0x7FFFFFFF
        code = str(code_int % (10 ** digits)).zfill(digits)
        return code

    @staticmethod
    def _generate_hotp(
        secret_b32: str, counter: int = 0, digits: int = 6, algorithm: str = "SHA1"
    ) -> str:
        """生成 HOTP 验证码"""
        try:
            key = AuthenticatorService._decode_base32(secret_b32)
        except Exception:
            return "ERROR"
        counter_bytes = struct.pack(">Q", counter)
        hash_func = getattr(hashlib, algorithm.lower(), hashlib.sha1)
        hmac_result = hmac.new(key, counter_bytes, hash_func).digest()
        offset = hmac_result[-1] & 0x0F
        code_int = struct.unpack(">I", hmac_result[offset : offset + 4])[0] & 0x7FFFFFFF
        code = str(code_int % (10 ** digits)).zfill(digits)
        return code

    @staticmethod
    def _parse_otpauth_uri(uri: str) -> Optional[dict]:
        """解析 otpauth:// URI"""
        pattern = re.match(
            r"otpauth://(totp|hotp)/([^?]+)\?(.+)", uri, re.IGNORECASE
        )
        if not pattern:
            return None
        token_type = pattern.group(1).lower()
        label = pattern.group(2)
        params_str = pattern.group(3)

        # 解析参数
        params: dict[str, str] = {}
        for pair in params_str.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k.lower()] = v

        name = label.split(":")[-1] if ":" in label else label
        # URL 解码
        from urllib.parse import unquote
        name = unquote(name)

        secret = params.get("secret", "")
        if not secret:
            return None

        return {
            "name": name,
            "secret": secret,
            "token_type": token_type,
            "issuer": unquote(params.get("issuer", "")),
            "digits": int(params.get("digits", "6")),
            "period": int(params.get("period", "30")),
            "algorithm": params.get("algorithm", "SHA1").upper(),
        }

    @staticmethod
    def _decode_base32(secret: str) -> bytes:
        """解码 Base32 密钥（容忍格式问题）"""
        secret = secret.upper().replace(" ", "").replace("-", "")
        # 补齐 padding
        padding = 8 - len(secret) % 8
        if padding != 8:
            secret += "=" * padding
        return base64.b32decode(secret)
