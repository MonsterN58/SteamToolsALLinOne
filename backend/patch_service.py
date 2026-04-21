"""Steam 补丁注入、联机配置、D加密虚拟机 服务层。

功能：
1. 免 Steam 补丁注入 —— 替换 steam_api.dll / steamclient.dll，写入 steam_settings 配置
2. 局域网联机配置 —— 自定义广播 IP、自动接受邀请、白名单、监听端口
3. D 加密虚拟机补丁 —— 从 .7z 归档中解压补丁并覆盖游戏目录（带备份）
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from backend.paths import get_assets_dir

BASE_DIR = get_assets_dir()

# 补丁资源根目录
RESOURCES_DIR = BASE_DIR / "resources" / "crack"
# Steamless CLI 路径
STEAMLESS_CLI = BASE_DIR / "resources" / "tools" / "Steamless.CLI.exe"

# steam_api DLL 文件名（用于可行性检测）
STEAM_API_DLLS = ("steam_api.dll", "steam_api64.dll")
STEAMCLIENT_DLLS = ("steamclient.dll", "steamclient64.dll")


class PatchService:
    """补丁注入与联机配置服务。"""

    @staticmethod
    def _pe_has_section(path: Path, section_name: str) -> bool | None:
        """Return whether a PE file has a section, or None when the file is not parseable."""
        try:
            with path.open("rb") as fp:
                dos_header = fp.read(0x40)
                if len(dos_header) < 0x40 or dos_header[:2] != b"MZ":
                    return None
                pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
                fp.seek(pe_offset)
                pe_header = fp.read(24)
                if len(pe_header) < 24 or pe_header[:4] != b"PE\0\0":
                    return None
                section_count = struct.unpack_from("<H", pe_header, 6)[0]
                optional_header_size = struct.unpack_from("<H", pe_header, 20)[0]
                fp.seek(pe_offset + 24 + optional_header_size)
                expected = section_name.encode("ascii")[:8].ljust(8, b"\0")
                for _ in range(section_count):
                    section = fp.read(40)
                    if len(section) < 40:
                        return None
                    if section[:8] == expected:
                        return True
                return False
        except OSError:
            return None

    # ── 自动检测 AppID ────────────────────────────────────────

    def detect_appid(self, game_path: str) -> dict:
        """从游戏目录中自动检测 Steam AppID。

        检测来源（按优先级）：
        1. steam_appid.txt（游戏根目录）
        2. steam_settings/steam_appid.txt
        3. steam_settings/configs.app.ini 中的 [app::dlcs] 段前的配置
        4. 遍历 exe 文件的资源段尝试读取（部分游戏在 manifest 中包含 AppID）
        """
        p = Path(game_path)
        if not p.is_dir():
            return {"appid": "", "source": "", "message": "目录不存在"}

        # 1. 根目录 steam_appid.txt
        appid_file = p / "steam_appid.txt"
        if appid_file.is_file():
            content = appid_file.read_text(encoding="utf-8", errors="ignore").strip()
            if content.isdigit():
                return {"appid": content, "source": "steam_appid.txt", "message": f"从 steam_appid.txt 读取到 AppID: {content}"}

        # 2. steam_settings/steam_appid.txt
        settings_appid = p / "steam_settings" / "steam_appid.txt"
        if settings_appid.is_file():
            content = settings_appid.read_text(encoding="utf-8", errors="ignore").strip()
            if content.isdigit():
                return {"appid": content, "source": "steam_settings/steam_appid.txt", "message": f"从 steam_settings/steam_appid.txt 读取到 AppID: {content}"}

        # 3. 从 exe 文件版本信息中提取（部分 Steam 游戏在 ProductCode 中包含 AppID）
        for exe_file in p.glob("*.exe"):
            appid = self._try_extract_appid_from_exe(exe_file)
            if appid:
                return {"appid": appid, "source": f"{exe_file.name}", "message": f"从 {exe_file.name} 检测到 AppID: {appid}"}

        return {"appid": "", "source": "", "message": "未能自动检测到 AppID，请手动输入"}

    @staticmethod
    def _try_extract_appid_from_exe(exe_path: Path) -> str:
        """尝试从 exe 文件中提取 Steam AppID。

        方法：读取 exe 附近或内部 PE 版本资源中的 Steam AppID。
        很多 Steam 游戏在 exe 文件旁边会有 steam_appid.txt，已在上面检测。
        这里尝试从 PE 的版本信息字符串中查找类似 AppId 的数字。
        """
        try:
            # 尝试用 subprocess 调用 Windows API 获取文件版本信息
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command",
                 f"(Get-Item '{exe_path}').VersionInfo | ConvertTo-Json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                info = json.loads(result.stdout)
                # 检查 ProductName、FileDescription 等字段
                # 部分游戏在 InternalName 或 OriginalFilename 中包含 appid
                for key in ("InternalName", "OriginalFilename", "ProductName", "FileDescription"):
                    val = str(info.get(key, "")).strip()
                    # 尝试从字符串中提取纯数字（6-7 位数的 Steam AppID）
                    import re
                    matches = re.findall(r'\b(\d{4,8})\b', val)
                    for m in matches:
                        # 排除常见非 AppID 数字（如年份、版本号等）
                        num = int(m)
                        if 1000 <= num <= 99999999 and not (2000 <= num <= 2099):
                            return m
        except Exception:
            pass
        return ""

    # ── 可行性检测 ──────────────────────────────────────────

    def check_feasibility(self, game_path: str, emulator_mode: int = 0) -> dict:
        """检测游戏目录是否满足补丁注入条件。

        返回 dict:
            feasible: bool
            details: list[str]  — 检测结果描述
            found_dlls: list[str] — 找到的目标 DLL
        """
        p = Path(game_path)
        details: list[str] = []
        found: list[str] = []

        if not p.is_dir():
            return {"feasible": False, "details": ["目录不存在"], "found_dlls": []}

        target_dlls = STEAM_API_DLLS if emulator_mode == 0 else STEAMCLIENT_DLLS
        for dll in target_dlls:
            if (p / dll).exists():
                found.append(dll)
                details.append(f"找到 {dll}")

        if not found:
            target_desc = "steam_api.dll / steam_api64.dll" if emulator_mode == 0 else "steamclient.dll / steamclient64.dll"
            details.append(f"未找到 {target_desc}")

        # 检查可写权限
        try:
            test_file = p / ".stm_write_test"
            test_file.write_text("t")
            test_file.unlink()
            details.append("目录可写")
        except OSError:
            details.append("目录不可写，请以管理员身份运行")
            return {"feasible": False, "details": details, "found_dlls": found}

        return {"feasible": len(found) > 0, "details": details, "found_dlls": found}

    def get_basic_status(self, game_path: str, emulator_mode: int = 0) -> dict:
        """读取磁盘上的基础配置状态，避免前端切页后丢失已应用状态。"""
        p = Path(game_path)
        details: list[str] = []
        found_dlls: list[str] = []

        if not p.is_dir():
            return {
                "applied": False,
                "appid": "",
                "details": ["目录不存在"],
                "found_dlls": [],
            }

        settings_dir = p / "steam_settings"
        settings_appid = settings_dir / "steam_appid.txt"
        root_appid = p / "steam_appid.txt"
        main_ini = settings_dir / "configs.main.ini"

        appid = ""
        for appid_file in (settings_appid, root_appid):
            if appid_file.is_file():
                content = appid_file.read_text(encoding="utf-8", errors="ignore").strip()
                if content.isdigit():
                    appid = content
                    break

        target_dlls = STEAM_API_DLLS if emulator_mode == 0 else STEAMCLIENT_DLLS
        for dll in target_dlls:
            if (p / dll).is_file():
                found_dlls.append(dll)

        if settings_dir.is_dir():
            details.append("找到 steam_settings 目录")
        else:
            details.append("未找到 steam_settings 目录")

        if appid:
            details.append(f"找到 AppID: {appid}")
        else:
            details.append("未找到 steam_appid.txt")

        if main_ini.is_file():
            details.append("找到 configs.main.ini")

        if found_dlls:
            details.append(f"找到目标 DLL: {', '.join(found_dlls)}")

        applied = settings_dir.is_dir() and bool(appid)
        return {
            "applied": applied,
            "appid": appid,
            "details": details,
            "found_dlls": found_dlls,
            "settings_dir": str(settings_dir),
        }

    # ── 基础补丁注入 ─────────────────────────────────────────

    def apply_basic_config(
        self,
        game_path: str,
        steam_app_id: str,
        use_experimental: bool = False,
        emulator_mode: int = 0,
    ) -> dict:
        """应用基础免 Steam 补丁配置。

        1. 在 game_path 下创建 steam_settings 目录
        2. 写入 steam_appid.txt
        3. 备份并替换目标 DLL（如果资源存在）
        """
        p = Path(game_path)
        if not p.is_dir():
            return {"success": False, "message": "游戏目录不存在"}

        dll_dir_name = "experimental" if use_experimental else "stable"
        dll_resource_dir = RESOURCES_DIR / "emu_dlls" / dll_dir_name
        target_dlls = STEAM_API_DLLS if emulator_mode == 0 else STEAMCLIENT_DLLS

        # 只替换游戏目录中实际存在的 DLL（64位游戏通常只有 steam_api64.dll，32位只有 steam_api.dll）
        existing_dlls = [dll_name for dll_name in target_dlls if (p / dll_name).exists()]
        if not existing_dlls:
            target_desc = " / ".join(target_dlls)
            return {
                "success": False,
                "message": f"游戏目录中未找到可替换的 {target_desc}，请确认选择的是 DLL 所在目录。",
                "replaced_dlls": [],
                "missing_targets": list(target_dlls),
            }

        missing_resources = [dll_name for dll_name in existing_dlls if not (dll_resource_dir / dll_name).is_file()]
        if missing_resources:
            expected = ", ".join(str(dll_resource_dir / name) for name in missing_resources)
            return {
                "success": False,
                "message": (
                    "缺少替换 DLL 资源，已停止应用基础配置。"
                    "请将你有权使用的对应 DLL 放入项目资源目录后重试："
                    f"{expected}"
                ),
                "replaced_dlls": [],
                "missing_resources": missing_resources,
                "resource_dir": str(dll_resource_dir),
            }

        settings_dir = p / "steam_settings"
        settings_dir.mkdir(exist_ok=True)

        # 双路径写入 steam_appid.txt（根目录 + steam_settings/）
        appid = steam_app_id.strip()
        (p / "steam_appid.txt").write_text(appid, encoding="utf-8")
        (settings_dir / "steam_appid.txt").write_text(appid, encoding="utf-8")

        # 写入 configs.main.ini（强制局域网模式）
        main_ini = settings_dir / "configs.main.ini"
        if not main_ini.exists():
            main_ini.write_text(
                "# GBE Fork main config\nforce_lan_only=1\nenable_lan_broadcast=1\n",
                encoding="utf-8",
            )

        # 写入空的 custom_broadcasts.txt（如不存在）
        broadcasts_file = settings_dir / "custom_broadcasts.txt"
        if not broadcasts_file.exists():
            broadcasts_file.write_text("", encoding="utf-8")

        replaced: list[str] = []
        for dll_name in existing_dlls:
            src_dll = dll_resource_dir / dll_name
            dst_dll = p / dll_name
            # 备份原始 DLL
            bak = dst_dll.with_suffix(dst_dll.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(dst_dll, bak)
            shutil.copy2(src_dll, dst_dll)
            replaced.append(dll_name)

        msg_parts = [f"steam_settings 已创建，AppID={steam_app_id}"]
        msg_parts.append(f"已替换: {', '.join(replaced)}")

        return {"success": True, "message": "；".join(msg_parts), "replaced_dlls": replaced}

    # ── Steamless 脱壳 ───────────────────────────────────────

    def unpack_game_exe(self, exe_path: str) -> dict:
        """使用 Steamless.CLI 脱壳游戏可执行文件。"""
        p = Path(exe_path)
        if not p.is_file():
            return {"success": False, "message": "文件不存在"}

        if not STEAMLESS_CLI.is_file():
            return {"success": False, "message": "Steamless.CLI 未找到，请将其放置在 resources/tools/ 下"}

        has_bind_section = self._pe_has_section(p, ".bind")
        # 仅当可以确定没有 .bind 段时给出提示，但不阻止尝试（部分变体使用不同段名）
        pre_warn = ""
        if has_bind_section is None:
            return {"success": False, "message": "该文件不是有效的 Windows PE 可执行文件，无法脱壳"}
        if has_bind_section is False:
            pre_warn = "提示：未检测到 .bind 段，可能无 SteamStub 壳，将尝试强制脱壳。"

        # 备份
        bak = p.with_suffix(p.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(p, bak)

        try:
            def run_steamless(extra_args: list[str] | None = None) -> tuple[subprocess.CompletedProcess[str], str]:
                args = [str(STEAMLESS_CLI)]
                if extra_args:
                    args.extend(extra_args)
                args.append(str(p))
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(STEAMLESS_CLI.parent),
                )
                output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
                return result, output

            def find_unpacked_file() -> Path | None:
                # Steamless 输出文件名：原文件名 + ".unpacked.exe" 或 ".unpacked" + 原扩展名
                candidate_names = [
                    p.name + ".unpacked.exe",
                    p.stem + ".unpacked" + p.suffix,
                    p.stem + ".unpacked.exe",
                ]
                search_dirs = [p.parent, STEAMLESS_CLI.parent]
                for search_dir in search_dirs:
                    for name in candidate_names:
                        candidate = search_dir / name
                        if candidate.exists():
                            return candidate
                return None

            attempts: list[tuple[str, subprocess.CompletedProcess[str], str]] = []
            for label, extra_args in (("常规模式", None), ("实验模式", ["--exp"])):
                result, output = run_steamless(extra_args)
                attempts.append((label, result, output))
                unpacked = find_unpacked_file()
                if unpacked is not None:
                    shutil.move(str(unpacked), str(p))
                    suffix = "" if label == "常规模式" else "（实验模式）"
                    prefix = f"{pre_warn}\n" if pre_warn else ""
                    return {"success": True, "message": f"{prefix}脱壳成功{suffix}，原文件已备份为 .bak"}

            combined_output = "\n".join(output for _, _, output in attempts if output)
            if "All unpackers failed to unpack file" in combined_output or not combined_output:
                msg = "Steamless 未能脱壳该文件。"
                if pre_warn:
                    msg += pre_warn
                else:
                    msg += "请确认选择的是实际游戏主程序，而不是 launcher/updater，或当前 Steamless 版本不支持该壳版本。"
                return {"success": False, "message": msg}

            failed_attempts = [
                f"{label}退出码={result.returncode}" for label, result, _ in attempts if result.returncode != 0
            ]
            status_hint = f"（{'; '.join(failed_attempts)}）" if failed_attempts else ""
            return {
                "success": False,
                "message": f"脱壳未生成输出文件{status_hint}。Steamless 输出: {combined_output or '无输出'}",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "脱壳超时（120s）"}
        except Exception as exc:
            return {"success": False, "message": f"脱壳失败: {exc}"}

    # ── 局域网联机配置 ───────────────────────────────────────

    def save_lan_config(self, game_path: str, config: dict) -> dict:
        """保存局域网联机配置到 steam_settings 目录。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        # custom_broadcasts.txt — GBE Fork 格式
        broadcasts = config.get("customBroadcasts", [])
        broadcasts_txt = "\n".join(str(b).strip() for b in broadcasts if str(b).strip())
        (settings_dir / "custom_broadcasts.txt").write_text(broadcasts_txt, encoding="utf-8")

        # 监听端口写入 configs.user.ini 的 [user::steamid] 或单独文件
        port = str(config.get("listenPort", "")).strip()
        port_file = settings_dir / "force_listen_port.txt"
        if port and port != "47584":
            port_file.write_text(port, encoding="utf-8")
        elif port_file.exists():
            port_file.unlink()

        # auto_accept_invite.txt — GBE Fork 格式
        # 文件不存在 = 不自动接受; 存在且空 = 接受所有; 存在且有内容 = 白名单
        auto_accept = config.get("autoAcceptInvite", "none")
        invite_file = settings_dir / "auto_accept_invite.txt"
        if auto_accept == "all":
            invite_file.write_text("", encoding="utf-8")
        elif auto_accept == "whitelist":
            whitelist = config.get("whitelist", [])
            invite_file.write_text(
                "\n".join(str(w).strip() for w in whitelist if str(w).strip()),
                encoding="utf-8",
            )
        else:  # none
            if invite_file.exists():
                invite_file.unlink()

        return {"success": True, "message": "局域网联机配置已保存"}

    def load_lan_config(self, game_path: str) -> dict:
        """读取局域网联机配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        config: dict[str, Any] = {
            "customBroadcasts": [],
            "listenPort": 47584,
            "autoAcceptInvite": "none",
            "whitelist": [],
        }
        if not settings_dir.is_dir():
            return config

        bcf = settings_dir / "custom_broadcasts.txt"
        if bcf.exists():
            config["customBroadcasts"] = [
                line.strip() for line in bcf.read_text(encoding="utf-8").splitlines() if line.strip()
            ]

        pf = settings_dir / "force_listen_port.txt"
        if pf.exists():
            try:
                config["listenPort"] = int(pf.read_text(encoding="utf-8").strip())
            except ValueError:
                pass

        invite_file = settings_dir / "auto_accept_invite.txt"
        if invite_file.exists():
            content = invite_file.read_text(encoding="utf-8").strip()
            if content:
                config["autoAcceptInvite"] = "whitelist"
                config["whitelist"] = [line.strip() for line in content.splitlines() if line.strip()]
            else:
                config["autoAcceptInvite"] = "all"

        return config

    # ── DLC 配置 ─────────────────────────────────────────────

    def save_dlc_config(self, game_path: str, config: dict) -> dict:
        """保存 DLC 配置到 configs.app.ini（GBE Fork 格式）。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        config_path = settings_dir / "configs.app.ini"

        # 读取现有配置，保留 [app::dlcs] 以外的部分
        before = ""
        after = ""
        if config_path.exists():
            in_dlcs = False
            found_dlcs = False
            for line in config_path.read_text(encoding="utf-8").splitlines():
                trimmed = line.strip()
                if trimmed == "[app::dlcs]":
                    in_dlcs = True
                    found_dlcs = True
                elif in_dlcs and trimmed.startswith("[") and trimmed.endswith("]"):
                    in_dlcs = False
                    after += line + "\n"
                elif in_dlcs:
                    pass  # skip old dlcs section
                elif found_dlcs:
                    after += line + "\n"
                else:
                    before += line + "\n"

        unlock_all = config.get("unlockAll", True)
        dlcs = config.get("dlcs", [])

        dlcs_section = "[app::dlcs]\n"
        dlcs_section += f"unlock_all={'1' if unlock_all else '0'}\n"
        for dlc in dlcs:
            app_id = str(dlc.get("appId", "")).strip()
            name = str(dlc.get("name", "")).strip()
            if app_id:
                dlcs_section += f"{app_id}={name}\n" if name else f"{app_id}=\n"
        dlcs_section += "\n"

        if not before.strip():
            before = "# default=public\nbranch_name=public\n\n[app::paths]\n\n"

        config_path.write_text(before + dlcs_section + after, encoding="utf-8")
        return {"success": True, "message": "DLC 配置已保存"}

    def load_dlc_config(self, game_path: str) -> dict:
        """读取 DLC 配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        config: dict[str, Any] = {"unlockAll": True, "dlcs": []}
        config_path = settings_dir / "configs.app.ini"
        if not config_path.is_file():
            return config

        in_dlcs = False
        for line in config_path.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t == "[app::dlcs]":
                in_dlcs = True
                continue
            if in_dlcs:
                if t.startswith("["):
                    break
                if "=" in t and not t.startswith("#"):
                    key, _, val = t.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key == "unlock_all":
                        config["unlockAll"] = val == "1"
                    elif key:
                        config["dlcs"].append({"appId": key, "name": val})
        return config

    # ── 用户配置 ─────────────────────────────────────────────

    def save_user_config(self, game_path: str, config: dict) -> dict:
        """保存用户配置到 configs.user.ini（GBE Fork 格式）。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        lines: list[str] = []
        if config.get("username"):
            lines.append(f"user_name={config['username']}")
        if config.get("language"):
            lines.append(f"language={config['language']}")
        if config.get("steamId"):
            lines.append(f"account_id={config['steamId']}")
        if config.get("savesFolderName"):
            lines.append(f"saves_folder_name={config['savesFolderName']}")
        if config.get("localSavePath"):
            lines.append(f"local_save_path={config['localSavePath']}")

        (settings_dir / "configs.user.ini").write_text("\n".join(lines), encoding="utf-8")
        return {"success": True, "message": "用户配置已保存"}

    def load_user_config(self, game_path: str) -> dict:
        """读取用户配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        cfg_file = settings_dir / "configs.user.ini"
        result: dict[str, Any] = {}
        if not cfg_file.is_file():
            return result
        for line in cfg_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip()
        # Normalize keys to camelCase used by frontend
        return {
            "username": result.get("user_name", ""),
            "language": result.get("language", "schinese"),
            "steamId": result.get("account_id", ""),
            "savesFolderName": result.get("saves_folder_name", ""),
            "localSavePath": result.get("local_save_path", ""),
        }

    # ── 主配置 ───────────────────────────────────────────────

    def save_main_config(self, game_path: str, config: dict) -> dict:
        """保存模拟器主配置到 configs.main.ini（GBE Fork 格式）。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        lines: list[str] = []
        bool_keys = {
            "newAppTicket": "new_app_ticket",
            "gcToken": "gc_token",
            "offlineMode": "offline",
            "disableNetworking": "disable_networking",
            "disableCloud": "disable_cloud",
            "enableLogging": "enable_logging",
            "disableAccountLimit": "disable_account_limit",
            "forceOffline": "force_offline",
        }
        for js_key, ini_key in bool_keys.items():
            val = config.get(js_key)
            if val is not None:
                lines.append(f"{ini_key}={'1' if val else '0'}")

        if config.get("logLevel") is not None:
            lines.append(f"log_level={config['logLevel']}")

        if config.get("encryptedAppTicket"):
            lines.append(f"encrypted_app_ticket={config['encryptedAppTicket']}")

        (settings_dir / "configs.main.ini").write_text("\n".join(lines), encoding="utf-8")
        return {"success": True, "message": "主配置已保存"}

    def load_main_config(self, game_path: str) -> dict:
        """读取模拟器主配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        cfg_file = settings_dir / "configs.main.ini"
        raw: dict[str, str] = {}
        if cfg_file.is_file():
            for line in cfg_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#") and not line.startswith("["):
                    key, _, val = line.partition("=")
                    raw[key.strip()] = val.strip()

        ini_to_js = {
            "new_app_ticket": "newAppTicket",
            "gc_token": "gcToken",
            "offline": "offlineMode",
            "disable_networking": "disableNetworking",
            "disable_cloud": "disableCloud",
            "enable_logging": "enableLogging",
            "disable_account_limit": "disableAccountLimit",
            "force_offline": "forceOffline",
        }
        result: dict[str, Any] = {}
        for ini_key, js_key in ini_to_js.items():
            if ini_key in raw:
                result[js_key] = raw[ini_key] == "1"
        if "log_level" in raw:
            result["logLevel"] = raw["log_level"]
        if "encrypted_app_ticket" in raw:
            result["encryptedAppTicket"] = raw["encrypted_app_ticket"]
        return result

    # ── D加密虚拟机补丁 ──────────────────────────────────────

    def check_denuvo_feasibility(self, game_path: str) -> dict:
        """检测游戏目录是否可以应用 D 加密虚拟机补丁。"""
        p = Path(game_path)
        if not p.is_dir():
            return {"feasible": False, "details": ["目录不存在"]}

        details: list[str] = []

        # 查找 exe 文件
        exes = list(p.glob("*.exe"))
        if exes:
            details.append(f"找到 {len(exes)} 个 exe 文件")
            # 检测是否有 Denuvo 特征段 (.arch, .denuvo)
            denuvo_found = False
            for exe in exes:
                for section in (".arch", ".denuvo"):
                    has = self._pe_has_section(exe, section)
                    if has:
                        details.append(f"检测到 Denuvo 特征段 ({section}) 于 {exe.name}")
                        denuvo_found = True
                        break
            if not denuvo_found:
                details.append("未检测到典型 Denuvo 特征段（仍可尝试应用补丁）")
        else:
            details.append("未找到 exe 文件")

        # 检查已有备份
        backup_dir = p / ".stm_backup"
        if backup_dir.is_dir():
            backup_files = list(backup_dir.rglob("*"))
            file_count = sum(1 for f in backup_files if f.is_file())
            if file_count > 0:
                details.append(f"检测到已有备份 ({file_count} 个文件)，可恢复")

        # 检查可写
        try:
            test_file = p / ".stm_write_test"
            test_file.write_text("t")
            test_file.unlink()
            details.append("目录可写")
        except OSError:
            details.append("目录不可写")
            return {"feasible": False, "details": details}

        return {"feasible": True, "details": details}

    def apply_denuvo_patch(self, game_path: str, archive_path: str) -> dict:
        """从 .7z / .zip / .rar 归档应用 D 加密虚拟机补丁到游戏目录。

        步骤：
        1. 备份游戏目录中将被覆盖的文件
        2. 解压归档到游戏目录
        """
        game_dir = Path(game_path)
        archive = Path(archive_path)

        if not game_dir.is_dir():
            return {"success": False, "message": "游戏目录不存在"}
        if not archive.is_file():
            return {"success": False, "message": "补丁文件不存在"}

        suffix = archive.suffix.lower()
        if suffix not in (".7z", ".zip", ".rar"):
            return {"success": False, "message": f"不支持的归档格式: {suffix}，请使用 .7z、.zip 或 .rar 文件"}

        # 创建备份目录
        backup_dir = game_dir / ".stm_backup"
        backup_dir.mkdir(exist_ok=True)

        try:
            names: list[str] = []

            if suffix == ".7z":
                import py7zr
                with py7zr.SevenZipFile(str(archive), "r") as z:
                    names = [n for n in z.getnames() if not n.endswith("/")]
            elif suffix == ".zip":
                import zipfile
                with zipfile.ZipFile(str(archive), "r") as z:
                    names = [n for n in z.namelist() if not n.endswith("/")]
            elif suffix == ".rar":
                try:
                    import rarfile
                    with rarfile.RarFile(str(archive), "r") as z:
                        names = [n for n in z.namelist() if not n.endswith("/")]
                except ImportError:
                    return {"success": False, "message": "解压 .rar 需要安装 rarfile 包：pip install rarfile"}

            if not names:
                return {"success": False, "message": "归档文件为空或无法读取内容"}

            # 检测归档内是否有公共根目录前缀（某些补丁7z会多套一层目录）
            common_prefix = ""
            if len(names) > 1:
                parts = [n.replace("\\", "/").split("/") for n in names]
                if all(len(p) > 1 for p in parts):
                    first_dir = parts[0][0]
                    if all(p[0] == first_dir for p in parts):
                        common_prefix = first_dir + "/"

            backed_up: list[str] = []
            for name in names:
                rel_name = name[len(common_prefix):] if common_prefix else name
                if not rel_name:
                    continue
                target = game_dir / rel_name
                if target.is_file():
                    bak_path = backup_dir / rel_name
                    bak_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, bak_path)
                    backed_up.append(rel_name)

            # 解压到临时目录再移动（处理公共前缀）
            if common_prefix:
                import tempfile
                with tempfile.TemporaryDirectory() as tmp_dir:
                    if suffix == ".7z":
                        import py7zr
                        with py7zr.SevenZipFile(str(archive), "r") as z:
                            z.extractall(path=tmp_dir)
                    elif suffix == ".zip":
                        import zipfile
                        with zipfile.ZipFile(str(archive), "r") as z:
                            z.extractall(path=tmp_dir)
                    elif suffix == ".rar":
                        import rarfile
                        with rarfile.RarFile(str(archive), "r") as z:
                            z.extractall(path=tmp_dir)
                    # 从临时目录的公共前缀子目录复制到游戏目录
                    src_dir = Path(tmp_dir) / common_prefix.rstrip("/")
                    if src_dir.is_dir():
                        for item in src_dir.rglob("*"):
                            if item.is_file():
                                rel = item.relative_to(src_dir)
                                dest = game_dir / rel
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(item, dest)
            else:
                # 直接解压到游戏目录
                if suffix == ".7z":
                    import py7zr
                    with py7zr.SevenZipFile(str(archive), "r") as z:
                        z.extractall(path=str(game_dir))
                elif suffix == ".zip":
                    import zipfile
                    with zipfile.ZipFile(str(archive), "r") as z:
                        z.extractall(path=str(game_dir))
                elif suffix == ".rar":
                    import rarfile
                    with rarfile.RarFile(str(archive), "r") as z:
                        z.extractall(path=str(game_dir))

            effective_count = len(names) - (1 if common_prefix else 0)
            msg_parts = [f"补丁已应用，覆盖 {effective_count} 个文件"]
            if backed_up:
                msg_parts.append(f"已备份 {len(backed_up)} 个原始文件到 .stm_backup/")
            if common_prefix:
                msg_parts.append(f"已自动去除归档根目录前缀: {common_prefix.rstrip('/')}")

            return {"success": True, "message": "；".join(msg_parts), "files": names, "backed_up": backed_up}

        except Exception as exc:
            return {"success": False, "message": f"补丁应用失败: {exc}"}

    def restore_backup(self, game_path: str) -> dict:
        """从备份恢复游戏文件。"""
        game_dir = Path(game_path)
        backup_dir = game_dir / ".stm_backup"

        if not backup_dir.is_dir():
            return {"success": False, "message": "没有找到备份"}

        restored: list[str] = []
        for root, _dirs, files in os.walk(backup_dir):
            for fname in files:
                bak_file = Path(root) / fname
                rel = bak_file.relative_to(backup_dir)
                target = game_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bak_file, target)
                restored.append(str(rel))

        # 清理备份目录
        shutil.rmtree(backup_dir, ignore_errors=True)

        return {"success": True, "message": f"已恢复 {len(restored)} 个文件", "restored": restored}

    # ── 成就配置 ─────────────────────────────────────────────

    def save_achievements_config(self, game_path: str, config: dict) -> dict:
        """保存成就配置到 steam_settings/achievements.json (GBE Fork 格式)。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        achievements = config.get("achievements", [])
        out = []
        for ach in achievements:
            out.append({
                "name": str(ach.get("name", "")).strip(),
                "displayName": str(ach.get("displayName", "")).strip(),
                "description": str(ach.get("description", "")).strip(),
                "hidden": 1 if ach.get("hidden") else 0,
                "icon": str(ach.get("icon", "")).strip(),
                "icon_gray": str(ach.get("iconGray", "")).strip(),
            })

        (settings_dir / "achievements.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"success": True, "message": f"已保存 {len(out)} 个成就"}

    def load_achievements_config(self, game_path: str) -> dict:
        """读取成就配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        f = settings_dir / "achievements.json"
        if not f.is_file():
            return {"achievements": []}
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            achievements = []
            for a in (raw if isinstance(raw, list) else []):
                achievements.append({
                    "name": a.get("name", ""),
                    "displayName": a.get("displayName", a.get("display_name", "")),
                    "description": a.get("description", ""),
                    "hidden": bool(a.get("hidden", 0)),
                    "icon": a.get("icon", ""),
                    "iconGray": a.get("icon_gray", a.get("iconGray", "")),
                })
            return {"achievements": achievements}
        except Exception:
            return {"achievements": []}

    # ── 统计配置 ─────────────────────────────────────────────

    def save_stats_config(self, game_path: str, config: dict) -> dict:
        """保存游戏统计到 steam_settings/stats.json (GBE Fork 格式)。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        stats = config.get("stats", [])
        out = []
        for s in stats:
            out.append({
                "name": str(s.get("name", "")).strip(),
                "type": str(s.get("type", "int")).lower(),
                "default": s.get("default", 0),
                "globalavgrate": bool(s.get("globalavgrate", False)),
                "displayName": str(s.get("displayName", "")).strip(),
            })
        (settings_dir / "stats.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"success": True, "message": f"已保存 {len(out)} 个统计项"}

    def load_stats_config(self, game_path: str) -> dict:
        """读取统计配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        f = settings_dir / "stats.json"
        if not f.is_file():
            return {"stats": []}
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            stats = []
            for s in (raw if isinstance(raw, list) else []):
                stats.append({
                    "name": s.get("name", ""),
                    "type": s.get("type", "int"),
                    "default": s.get("default", 0),
                    "globalavgrate": bool(s.get("globalavgrate", False)),
                    "displayName": s.get("displayName", s.get("display_name", "")),
                })
            return {"stats": stats}
        except Exception:
            return {"stats": []}

    # ── 物品配置 ─────────────────────────────────────────────

    def save_items_config(self, game_path: str, config: dict) -> dict:
        """保存物品/库存配置到 steam_settings/items.json (GBE Fork 格式)。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        items = config.get("items", [])
        out = []
        for item in items:
            out.append({
                "itemdefid": int(item.get("itemId", 0)),
                "name": str(item.get("name", "")).strip(),
                "quantity": int(item.get("quantity", 1)),
                "type": str(item.get("type", "item")).strip(),
                "attributes": str(item.get("attributes", "")).strip(),
            })
        (settings_dir / "items.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"success": True, "message": f"已保存 {len(out)} 个物品"}

    def load_items_config(self, game_path: str) -> dict:
        """读取物品配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        f = settings_dir / "items.json"
        if not f.is_file():
            return {"items": []}
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            items = []
            for item in (raw if isinstance(raw, list) else []):
                items.append({
                    "itemId": item.get("itemdefid", 0),
                    "name": item.get("name", ""),
                    "quantity": item.get("quantity", 1),
                    "type": item.get("type", "item"),
                    "attributes": item.get("attributes", ""),
                })
            return {"items": items}
        except Exception:
            return {"items": []}

    # ── 排行榜配置 ───────────────────────────────────────────

    def save_leaderboards_config(self, game_path: str, config: dict) -> dict:
        """保存排行榜配置到 steam_settings/leaderboards.json (GBE Fork 格式)。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        leaderboards = config.get("leaderboards", [])
        out = []
        for lb in leaderboards:
            out.append({
                "name": str(lb.get("name", "")).strip(),
                "sort_method": int(lb.get("sortMethod", 2)),
                "display_type": int(lb.get("displayType", 1)),
            })
        (settings_dir / "leaderboards.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"success": True, "message": f"已保存 {len(out)} 个排行榜"}

    def load_leaderboards_config(self, game_path: str) -> dict:
        """读取排行榜配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        f = settings_dir / "leaderboards.json"
        if not f.is_file():
            return {"leaderboards": []}
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            lbs = []
            for lb in (raw if isinstance(raw, list) else []):
                lbs.append({
                    "name": lb.get("name", ""),
                    "sortMethod": lb.get("sort_method", 2),
                    "displayType": lb.get("display_type", 1),
                })
            return {"leaderboards": lbs}
        except Exception:
            return {"leaderboards": []}

    # ── Overlay 配置 ─────────────────────────────────────────

    def save_overlay_config(self, game_path: str, config: dict) -> dict:
        """保存 Overlay 配置到 configs.main.ini [overlay] 节区 (GBE Fork 格式)。"""
        settings_dir = Path(game_path) / "steam_settings"
        if not settings_dir.is_dir():
            return {"success": False, "message": "请先应用基础配置"}

        main_ini = settings_dir / "configs.main.ini"
        # 读取现有内容，移除旧的 [overlay] 节区
        before = ""
        if main_ini.is_file():
            in_overlay = False
            for line in main_ini.read_text(encoding="utf-8").splitlines():
                t = line.strip()
                if t == "[overlay]":
                    in_overlay = True
                    continue
                if in_overlay and t.startswith("["):
                    in_overlay = False
                if not in_overlay:
                    before += line + "\n"

        overlay_section = "[overlay]\n"
        overlay_section += f"enable_experimental_overlay={'1' if config.get('enabled') else '0'}\n"
        if config.get("showFPS"):
            overlay_section += "show_fps=1\n"
        if config.get("showClock"):
            overlay_section += "show_clock=1\n"
        if config.get("achievementSound") and config.get("achievementSoundPath"):
            overlay_section += f"achievement_sound={config['achievementSoundPath']}\n"
        overlay_section += "\n"

        main_ini.write_text(before.rstrip("\n") + "\n" + overlay_section, encoding="utf-8")
        return {"success": True, "message": "Overlay 配置已保存"}

    def load_overlay_config(self, game_path: str) -> dict:
        """读取 Overlay 配置。"""
        settings_dir = Path(game_path) / "steam_settings"
        main_ini = settings_dir / "configs.main.ini"
        result: dict[str, Any] = {
            "enabled": False, "showFPS": False, "showClock": False,
            "achievementSound": False, "achievementSoundPath": "",
        }
        if not main_ini.is_file():
            return result
        in_overlay = False
        for line in main_ini.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t == "[overlay]":
                in_overlay = True
                continue
            if in_overlay:
                if t.startswith("["):
                    break
                if "=" in t and not t.startswith("#"):
                    key, _, val = t.partition("=")
                    key, val = key.strip(), val.strip()
                    if key == "enable_experimental_overlay":
                        result["enabled"] = val == "1"
                    elif key == "show_fps":
                        result["showFPS"] = val == "1"
                    elif key == "show_clock":
                        result["showClock"] = val == "1"
                    elif key == "achievement_sound" and val:
                        result["achievementSound"] = True
                        result["achievementSoundPath"] = val
        return result
