from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.service import SteamToolsService
from backend.trainer_service import TrainerService
from backend.patch_service import PatchService
from backend import resource_service
from backend.translate_helper import translate_term
from backend.steam_tools_service import (
    AcceleratorService,
    AccountService,
    LibraryService,
    AuthenticatorService,
    run_idle_helper,
)


class SearchRequest(BaseModel):
    term: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    translate_fallback: bool = True


class TranslateRequest(BaseModel):
    term: str = Field(min_length=1)


class SettingsRequest(BaseModel):
    download_source: Literal["auto", "domestic", "overseas"] = "auto"
    auto_import: bool = False
    unlock_dlc: bool = False
    search_enhance: bool = False
    patch_emulator_mode: int = 0
    patch_use_experimental: bool = False
    patch_default_username: str = "Player"
    patch_default_language: str = "schinese"
    lan_default_port: int = 47584
    denuvo_auto_backup: bool = True


class DownloadRequest(BaseModel):
    appid: str = Field(min_length=1)
    source: Literal["auto", "domestic", "overseas"] = "auto"
    auto_import: bool = False
    unlock_dlc: bool = False


class TrainerSearchRequest(BaseModel):
    game_name: str = Field(min_length=1)


class TrainerDownloadRequest(BaseModel):
    trainer_url: str = Field(min_length=1)
    game_name: str = Field(min_length=1)
    download_url: str = ""
    download_label: str = ""


class TrainerVersionsRequest(BaseModel):
    game_name: str = Field(min_length=1)


class TrainerDetailRequest(BaseModel):
    trainer_url: str = Field(min_length=1)


class TrainerCacheLaunchRequest(BaseModel):
    game_name: str = Field(min_length=1)


class PatchBasicRequest(BaseModel):
    game_path: str = Field(min_length=1)
    steam_app_id: str = Field(min_length=1)
    use_experimental: bool = False
    emulator_mode: int = 0


class PatchFeasibilityRequest(BaseModel):
    game_path: str = Field(min_length=1)
    emulator_mode: int = 0


class PatchDetectAppidRequest(BaseModel):
    game_path: str = Field(min_length=1)


class UnpackRequest(BaseModel):
    exe_path: str = Field(min_length=1)


class LanConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class DlcConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class UserConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class MainConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class DenuvoFeasibilityRequest(BaseModel):
    game_path: str = Field(min_length=1)


class DenuvoPatchRequest(BaseModel):
    game_path: str = Field(min_length=1)
    archive_path: str = Field(min_length=1)


class RestoreBackupRequest(BaseModel):
    game_path: str = Field(min_length=1)


class AchievementsConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class StatsConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class ItemsConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class LeaderboardsConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


class OverlayConfigRequest(BaseModel):
    game_path: str = Field(min_length=1)
    config: dict


service = SteamToolsService()
trainer_service = TrainerService()
patch_service = PatchService()
accelerator_service = AcceleratorService()
account_service = AccountService()
library_service = LibraryService()
authenticator_service = AuthenticatorService()
app = FastAPI(title="SteamTools ALLinOne Backend", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/settings")
def get_settings():
    return service.get_settings()


@app.post("/settings")
def update_settings(payload: SettingsRequest):
    return service.save_settings(payload.model_dump())


@app.post("/search")
def search(payload: SearchRequest):
    try:
        items = service.search(
            term=payload.term,
            limit=payload.limit,
            translate_fallback=payload.translate_fallback,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"搜索失败：{exc}") from exc
    return {"items": items}


@app.post("/tasks/download")
def start_download(payload: DownloadRequest):
    try:
        task_id = service.start_download_task(
            appid=payload.appid,
            source=payload.source,
            auto_import=payload.auto_import,
            unlock_dlc=payload.unlock_dlc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"task_id": task_id}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, offset: int = Query(default=0, ge=0)):
    try:
        return service.get_task_snapshot(task_id, offset=offset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/actions/open-download-folder")
def open_download_folder():
    try:
        service.open_download_folder()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"无法打开目录：{exc}") from exc
    return {"ok": True}


@app.get("/imports")
def list_imports():
    try:
        return service.list_imported_games()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检测已入库游戏失败：{exc}") from exc


@app.get("/steam/installed-games")
def list_installed_games():
    try:
        return service.list_installed_games()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"扫描已安装 Steam 游戏失败：{exc}") from exc


@app.delete("/imports/{appid}")
def delete_import(appid: str):
    try:
        return service.delete_imported_game(appid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除入库游戏失败：{exc}") from exc


@app.post("/imports/clear")
def clear_imports():
    try:
        return service.clear_all_imports()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"清理入库残留失败：{exc}") from exc


@app.post("/trainer/search")
def trainer_search(payload: TrainerSearchRequest):
    try:
        results = trainer_service.search_trainer(payload.game_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"修改器搜索失败：{exc}") from exc
    return {"items": results}


@app.post("/trainer/detail")
def trainer_detail(payload: TrainerDetailRequest):
    try:
        detail = trainer_service.get_trainer_detail(payload.trainer_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"获取修改器详情失败：{exc}") from exc
    return detail


@app.post("/trainer/versions")
def trainer_versions(payload: TrainerVersionsRequest):
    """获取已解析好的修改器下载目录。"""
    try:
        catalog = trainer_service.get_trainer_versions(payload.game_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"获取修改器版本列表失败：{exc}") from exc
    return catalog


@app.post("/trainer/download")
def trainer_download(payload: TrainerDownloadRequest):
    try:
        tid = trainer_service.start_download(
            trainer_url=payload.trainer_url,
            game_name=payload.game_name,
            download_url=payload.download_url,
            download_label=payload.download_label,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"启动下载失败：{exc}") from exc
    return {"task_id": tid}


@app.post("/trainer/start-latest")
def trainer_start_latest(payload: TrainerCacheLaunchRequest):
    try:
        return trainer_service.start_latest_trainer(payload.game_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"启动最新修改器失败：{exc}") from exc


@app.get("/trainer/task/{tid}")
def trainer_task_status(tid: str):
    try:
        return trainer_service.get_task(tid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/trainer/tasks")
def trainer_task_list():
    return {"items": trainer_service.list_tasks()}


@app.get("/trainer/cache")
def trainer_cache_list():
    return {"items": trainer_service.list_cached_trainers()}


@app.post("/trainer/launch/{tid}")
def trainer_launch(tid: str):
    try:
        return trainer_service.launch_trainer(tid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"启动修改器失败：{exc}") from exc


@app.post("/trainer/launch-cache")
def trainer_launch_cache(payload: TrainerCacheLaunchRequest):
    try:
        return trainer_service.launch_from_cache(payload.game_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"启动缓存修改器失败：{exc}") from exc


@app.delete("/trainer/cache")
def trainer_cache_delete(payload: TrainerCacheLaunchRequest):
    try:
        return trainer_service.delete_cached_trainer(payload.game_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"删除缓存修改器失败：{exc}") from exc


@app.post("/trainer/stop/{tid}")
def trainer_stop(tid: str):
    try:
        return trainer_service.stop_trainer(tid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/trainer/stop-all")
def trainer_stop_all():
    trainer_service.stop_all_trainers()
    return {"message": "已关闭所有修改器"}


# ── 补丁注入 API ────────────────────────────────────────


@app.post("/patch/check-feasibility")
def patch_check_feasibility(payload: PatchFeasibilityRequest):
    try:
        return patch_service.check_feasibility(payload.game_path, payload.emulator_mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/basic-status")
def patch_basic_status(payload: PatchFeasibilityRequest):
    """读取已写入磁盘的基础补丁状态。"""
    try:
        return patch_service.get_basic_status(payload.game_path, payload.emulator_mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/detect-appid")
def patch_detect_appid(payload: PatchDetectAppidRequest):
    """从游戏目录中自动检测 Steam AppID。"""
    try:
        return patch_service.detect_appid(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/apply-basic")
def patch_apply_basic(payload: PatchBasicRequest):
    try:
        return patch_service.apply_basic_config(
            game_path=payload.game_path,
            steam_app_id=payload.steam_app_id,
            use_experimental=payload.use_experimental,
            emulator_mode=payload.emulator_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/unpack")
def patch_unpack(payload: UnpackRequest):
    try:
        return patch_service.unpack_game_exe(payload.exe_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/lan/save")
def patch_lan_save(payload: LanConfigRequest):
    try:
        return patch_service.save_lan_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/lan/load")
def patch_lan_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_lan_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/dlc/save")
def patch_dlc_save(payload: DlcConfigRequest):
    try:
        return patch_service.save_dlc_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/dlc/load")
def patch_dlc_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_dlc_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/user/save")
def patch_user_save(payload: UserConfigRequest):
    try:
        return patch_service.save_user_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/user/load")
def patch_user_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_user_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/main/save")
def patch_main_save(payload: MainConfigRequest):
    try:
        return patch_service.save_main_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/main/load")
def patch_main_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_main_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/denuvo/check")
def patch_denuvo_check(payload: DenuvoFeasibilityRequest):
    try:
        return patch_service.check_denuvo_feasibility(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/denuvo/apply")
def patch_denuvo_apply(payload: DenuvoPatchRequest):
    try:
        return patch_service.apply_denuvo_patch(payload.game_path, payload.archive_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/restore-backup")
def patch_restore_backup(payload: RestoreBackupRequest):
    try:
        return patch_service.restore_backup(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 成就 / 统计 / 物品 / 排行榜 / Overlay API ────────────


@app.post("/patch/achievements/save")
def patch_achievements_save(payload: AchievementsConfigRequest):
    try:
        return patch_service.save_achievements_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/achievements/load")
def patch_achievements_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_achievements_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/stats/save")
def patch_stats_save(payload: StatsConfigRequest):
    try:
        return patch_service.save_stats_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/stats/load")
def patch_stats_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_stats_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/items/save")
def patch_items_save(payload: ItemsConfigRequest):
    try:
        return patch_service.save_items_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/items/load")
def patch_items_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_items_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/leaderboards/save")
def patch_leaderboards_save(payload: LeaderboardsConfigRequest):
    try:
        return patch_service.save_leaderboards_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/leaderboards/load")
def patch_leaderboards_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_leaderboards_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/overlay/save")
def patch_overlay_save(payload: OverlayConfigRequest):
    try:
        return patch_service.save_overlay_config(payload.game_path, payload.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/overlay/load")
def patch_overlay_load(payload: PatchFeasibilityRequest):
    try:
        return patch_service.load_overlay_config(payload.game_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 资源管理 API ────────────────────────────────────


@app.get("/patch/resources/check")
def patch_resources_check():
    """检测 GBE Fork DLL 资源是否就绪。"""
    try:
        return resource_service.check_resources()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/patch/resources/download")
def patch_resources_download():
    """#启动后台下载 GBE Fork DLL。"""
    try:
        return resource_service.start_download_gbe_fork()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/patch/resources/progress")
def patch_resources_progress():
    """返回当前下载进度。"""
    try:
        return resource_service.get_download_progress()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Steam 工具箱 API ────────────────────────────────


# ── 网络加速 ──


class AcceleratorEnableRequest(BaseModel):
    rules: dict[str, str]


@app.get("/accelerator/profiles")
def accelerator_profiles():
    return accelerator_service.get_profiles()


@app.get("/accelerator/status")
def accelerator_status():
    return accelerator_service.get_status()


@app.post("/accelerator/enable")
def accelerator_enable(payload: AcceleratorEnableRequest):
    try:
        return accelerator_service.enable(payload.rules)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/accelerator/disable")
def accelerator_disable():
    try:
        return accelerator_service.disable()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class LatencyTestRequest(BaseModel):
    host: str
    ip: str


@app.post("/accelerator/test-latency")
def accelerator_test_latency(payload: LatencyTestRequest):
    return accelerator_service.test_latency(payload.host, payload.ip)


@app.get("/accelerator/test-profile/{profile_name}")
def accelerator_test_profile(profile_name: str):
    return accelerator_service.test_profile_latency(profile_name)


# ── 账号切换 ──


class SwitchAccountRequest(BaseModel):
    steam_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1)


@app.get("/accounts/list")
def accounts_list():
    try:
        return {"items": account_service.list_accounts()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/accounts/current")
def accounts_current():
    return account_service.get_current_account()


@app.post("/accounts/switch")
def accounts_switch(payload: SwitchAccountRequest):
    try:
        return account_service.switch_account(payload.steam_id, payload.account_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 库存游戏 ──


@app.get("/library/games")
def library_games():
    try:
        return {"items": library_service.list_games()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/library/game/{appid}")
def library_game_detail(appid: str):
    try:
        return library_service.get_game_detail(appid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/library/idle/{appid}")
def library_idle_start(appid: str):
    try:
        return library_service.idle_game(appid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/library/idle/{appid}/stop")
def library_idle_stop(appid: str):
    return library_service.stop_idle(appid)


@app.post("/library/idle/stop-all")
def library_idle_stop_all():
    return library_service.stop_all_idle()


@app.get("/library/idle/status")
def library_idle_status():
    return {"items": library_service.get_idle_status()}


@app.post("/translate")
def translate(payload: TranslateRequest):
    """将搜索词双向翻译（中文→英文 或 英文→中文）。"""
    try:
        result = translate_term(payload.term)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 本地令牌 ──


class AddTokenRequest(BaseModel):
    name: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    token_type: str = "totp"
    issuer: str = ""
    digits: int = 6
    period: int = 30
    algorithm: str = "SHA1"


class ImportUriRequest(BaseModel):
    uri: str = Field(min_length=1)


class ImportSteamJsonRequest(BaseModel):
    json_str: str = Field(min_length=1)


@app.get("/authenticator/tokens")
def authenticator_list():
    return {"items": authenticator_service.list_tokens()}


@app.get("/authenticator/codes")
def authenticator_codes():
    return {"items": authenticator_service.get_all_codes()}


@app.get("/authenticator/code/{token_id}")
def authenticator_code(token_id: str):
    return authenticator_service.get_code(token_id)


@app.post("/authenticator/add")
def authenticator_add(payload: AddTokenRequest):
    try:
        return authenticator_service.add_token(
            name=payload.name,
            secret=payload.secret,
            token_type=payload.token_type,
            issuer=payload.issuer,
            digits=payload.digits,
            period=payload.period,
            algorithm=payload.algorithm,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/authenticator/{token_id}")
def authenticator_remove(token_id: str):
    return authenticator_service.remove_token(token_id)


@app.post("/authenticator/import-uri")
def authenticator_import_uri(payload: ImportUriRequest):
    try:
        return authenticator_service.import_uri(payload.uri)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/authenticator/import-steam")
def authenticator_import_steam(payload: ImportSteamJsonRequest):
    try:
        return authenticator_service.import_steam_json(payload.json_str)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/authenticator/scan-local")
def authenticator_scan_local():
    try:
        return authenticator_service.scan_local_tokens()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--idle-helper", action="store_true")
    parser.add_argument("--appid", default="")
    parser.add_argument("--idle-dir", default="")
    parser.add_argument("--api-dll", default="")
    parser.add_argument("--steam-root", default="")
    args, _ = parser.parse_known_args()

    if args.idle_helper:
        raise SystemExit(run_idle_helper(args.appid, args.idle_dir, args.api_dll, args.steam_root))

    uvicorn.run(app, host="127.0.0.1", port=18765, reload=False)
