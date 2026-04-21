import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Download,
  Eraser,
  FileText,
  FolderCog,
  FolderOpen,
  Gamepad2,
  Globe,
  HardDrive,
  Library,
  Loader2,
  Monitor,
  MonitorPlay,
  Moon,
  Play,
  RefreshCw,
  ScrollText,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  SquareArrowOutUpRight,
  StopCircle,
  Trash2,
  User,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import "./App.css";
import SteamPatchPage from "./SteamPatchPage";
import SteamToolsPage from "./SteamToolsPage";

const API_BASE = window.nativeApp?.backendUrl || "http://127.0.0.1:18765";

const statusText = {
  idle: "待机",
  running: "执行中",
  success: "已完成",
  error: "失败",
};

const statusIcons = {
  idle: Clock,
  running: Loader2,
  success: CheckCircle,
  error: AlertCircle,
};

async function request(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const payload = await resp.json().catch(() => ({}));
    throw new Error(payload.detail || `请求失败: ${resp.status}`);
  }
  return resp.json();
}

function normalizeGameKey(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function StatusBadge({ status }) {
  const Icon = statusIcons[status] || Clock;
  const colorClass =
    status === "idle"
      ? "status-idle"
      : status === "running"
        ? "status-running"
        : status === "success"
          ? "status-success"
          : "status-error";

  const dotColor =
    status === "idle"
      ? "bg-[#a0aab8]"
      : status === "running"
        ? "bg-[#8898cc]"
        : status === "success"
          ? "bg-[#6cb58a]"
          : "bg-[#d48686]";

  return (
    <span className={`status-badge ${colorClass}`}>
      <span className={`status-dot ${dotColor} ${status === "running" ? "animate-pulse" : ""}`} />
      {statusText[status] || status}
      {status === "running" && <Icon className="h-3.5 w-3.5 animate-spin" />}
    </span>
  );
}

function PageTab({ active, icon, label, onClick, hint }) {
  const TabIcon = icon;
  return (
    <button className={`page-tab ${active ? "page-tab-active" : ""}`} onClick={onClick}>
      <span className="page-tab-icon-wrap">
        <TabIcon className="h-4 w-4" />
      </span>
      <span className="page-tab-copy">
        <span className="page-tab-label">{label}</span>
        {hint && <span className="page-tab-hint">{hint}</span>}
      </span>
    </button>
  );
}

function SettingRow({ icon, title, description, children }) {
  const RowIcon = icon;
  return (
    <div className="setting-row">
      <div className="setting-row-main">
        <span className="setting-row-icon">
          <RowIcon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="setting-row-title">{title}</p>
          {description && <p className="setting-row-desc">{description}</p>}
        </div>
      </div>
      <div className="setting-row-control">{children}</div>
    </div>
  );
}

function MetricCard({ icon, label, value, tone = "blue" }) {
  const CardIcon = icon;
  return (
    <div className={`metric-card metric-${tone}`}>
      <div className="metric-icon">
        <CardIcon className="h-4 w-4" />
      </div>
      <div>
        <p className="metric-label">{label}</p>
        <p className="metric-value">{value}</p>
      </div>
    </div>
  );
}

function EmptyState({ icon, title, description }) {
  const StateIcon = icon;
  return (
    <div className="empty-state">
    <StateIcon className="mx-auto mb-3 h-10 w-10 text-[#c4ccd8]" />
    <p className="text-sm font-semibold text-[#7a8899]">{title}</p>
    <p className="mt-1 text-xs text-[#a0aab8]">{description}</p>
    </div>
  );
}

function App() {
  const [activePage, setActivePage] = useState("overview");
  const [theme, setTheme] = useState(() => localStorage.getItem("stm-theme") || "system");
  const [settings, setSettings] = useState({
    download_source: "auto",
    auto_import: false,
    unlock_dlc: false,
    search_enhance: false,
    patch_emulator_mode: 0,
    patch_use_experimental: false,
    patch_default_username: "Player",
    patch_default_language: "schinese",
    lan_default_port: 47584,
    denuvo_auto_backup: true,
  });
  const [term, setTerm] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [appid, setAppid] = useState("");
  const [taskId, setTaskId] = useState("");
  const [taskStatus, setTaskStatus] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [selectedGame, setSelectedGame] = useState(null);
  const [error, setError] = useState("");
  const [importedGames, setImportedGames] = useState([]);
  const [importsLoading, setImportsLoading] = useState(false);
  const [importNotice, setImportNotice] = useState("");
  const [installedGames, setInstalledGames] = useState([]);
  const [installedLoading, setInstalledLoading] = useState(false);
  const [installedError, setInstalledError] = useState("");
  const [gameFilter, setGameFilter] = useState("");
  const [selectedInstalledGame, setSelectedInstalledGame] = useState(null);
  const [trainerQuery, setTrainerQuery] = useState("");
  const [trainerLookups, setTrainerLookups] = useState({});
  const [trainerTasks, setTrainerTasks] = useState([]);
  const [trainerCached, setTrainerCached] = useState([]);
  const [trainerError, setTrainerError] = useState("");
  const [trainerActionBusy, setTrainerActionBusy] = useState("");
  const [trainerVersions, setTrainerVersions] = useState(null); // null=未加载 []|[...]=已加载
  const [trainerVersionsLoading, setTrainerVersionsLoading] = useState(false);
  const [trainerVersionsGame, setTrainerVersionsGame] = useState(""); // 当前版本列表对应的游戏名
  const [trainerDownloadingUrl, setTrainerDownloadingUrl] = useState(""); // 正在下载的 url
  const [trainerResolvedName, setTrainerResolvedName] = useState("");
  const [trainerMatchStatus, setTrainerMatchStatus] = useState("idle");
  const [trainerAlternatives, setTrainerAlternatives] = useState([]);
  const logContainerRef = useRef(null);
  const manifestOffsetRef = useRef(0);
  const trainerBatchRef = useRef(0);
  const trainerRequestRef = useRef(0);
  const searchAbortRef = useRef(null);
  const searchTimerRef = useRef(null);
  const searchCacheRef = useRef(new Map());

  const getTrainerLookup = (gameName) => {
    const key = normalizeGameKey(gameName);
    return key ? trainerLookups[key] : null;
  };

  const getCachedTrainer = (gameName) => {
    const key = normalizeGameKey(gameName);
    if (!key) return null;
    return trainerCached.find((item) => normalizeGameKey(item.game_name) === key) || null;
  };

  const setTrainerLookupForGame = (gameName, lookup) => {
    const key = normalizeGameKey(gameName);
    if (!key) return;
    setTrainerLookups((prev) => ({
      ...prev,
      [key]: {
        gameName,
        ...lookup,
      },
    }));
  };

  const queryInstalledGameTrainers = async (games) => {
    const items = (games || []).filter((item) => String(item.name || "").trim());
    const batchId = ++trainerBatchRef.current;
    if (items.length === 0) {
      setTrainerLookups({});
      return;
    }

    setTrainerError("");
    setTrainerLookups((prev) => {
      const next = { ...prev };
      items.forEach((item) => {
        const key = normalizeGameKey(item.name);
        if (!key) return;
        next[key] = {
          gameName: item.name,
          status: "checking",
          message: "正在查找修改器",
        };
      });
      return next;
    });

    let cursor = 0;
    const workerCount = Math.min(3, items.length);
    const runWorker = async () => {
      while (cursor < items.length) {
        const item = items[cursor];
        cursor += 1;
        const name = String(item.name || "").trim();
        try {
          const result = await request("/trainer/search", {
            method: "POST",
            body: JSON.stringify({ game_name: name }),
          });
          if (trainerBatchRef.current !== batchId) return;
          const hasTrainer = (result.items || []).length > 0;
          setTrainerLookupForGame(name, {
            status: hasTrainer ? "available" : "unavailable",
            message: hasTrainer ? "可下载" : "没有修改器",
          });
        } catch (err) {
          if (trainerBatchRef.current !== batchId) return;
          setTrainerLookupForGame(name, {
            status: "error",
            message: err.message,
          });
        }
      }
    };

    await Promise.all(Array.from({ length: workerCount }, runWorker));
  };

  async function loadImportedGames(showLoading = true) {
    if (showLoading) {
      setImportsLoading(true);
    }
    try {
      const data = await request("/imports");
      setImportedGames(data.items || []);
    } catch (err) {
      setImportedGames([]);
      setImportNotice(err.message);
    } finally {
      if (showLoading) {
        setImportsLoading(false);
      }
    }
  }

  async function loadInstalledGames(showLoading = true) {
    if (showLoading) {
      setInstalledLoading(true);
    }
    setInstalledError("");
    try {
      const data = await request("/steam/installed-games");
      const items = data.items || [];
      setInstalledGames(items);
      if (!selectedInstalledGame && items.length > 0) {
        setSelectedInstalledGame(items[0]);
        setTrainerQuery(items[0].name || "");
      }
      queryInstalledGameTrainers(items).catch((err) => {
        setTrainerError(err.message);
      });
    } catch (err) {
      setInstalledGames([]);
      setTrainerLookups({});
      setInstalledError(err.message);
    } finally {
      if (showLoading) {
        setInstalledLoading(false);
      }
    }
  }

  async function refreshTrainerState() {
    try {
      const taskData = await request("/trainer/tasks");
      setTrainerTasks(taskData.items || []);
    } catch (err) {
      setTrainerError(err.message);
    }
  }

  async function loadTrainerCache() {
    try {
      const data = await request("/trainer/cache");
      setTrainerCached(data.items || []);
    } catch (err) {
      setTrainerError(err.message);
    }
  }

  useEffect(() => {
    request("/settings")
      .then((data) => setSettings(data))
      .catch((err) => setError(err.message));
    const timer = setTimeout(() => {
      loadImportedGames(false);
      loadInstalledGames(true);
      refreshTrainerState();
      loadTrainerCache();
    }, 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    searchCacheRef.current.clear();
  }, [settings.search_enhance]);

  // Auto-scroll log container
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    if (!taskId) return;
    const timer = setInterval(async () => {
      try {
        const data = await request(`/tasks/${taskId}?offset=${manifestOffsetRef.current}`);
        setTaskStatus(data.status || "running");
        setProgress(Number(data.progress || 0));
        manifestOffsetRef.current = data.next_offset || manifestOffsetRef.current;
        if (Array.isArray(data.logs) && data.logs.length > 0) {
          setLogs((prev) => [...prev, ...data.logs]);
        }
        if (data.game_name || data.folder_name) {
          setSelectedGame({
            name: data.game_name || "未知",
            appid: data.appid,
            image: "",
          });
        }
        if (data.status === "success" || data.status === "error") {
          clearInterval(timer);
          setTaskId("");
          if (data.status === "success") {
            loadImportedGames();
          }
        }
      } catch (err) {
        clearInterval(timer);
        setTaskId("");
        setTaskStatus("error");
        setError(err.message);
      }
    }, 900);
    return () => clearInterval(timer);
  }, [taskId]);

  useEffect(() => {
    const timer = setInterval(() => {
      refreshTrainerState();
      loadTrainerCache();
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  const progressStyle = useMemo(
    () => ({ width: `${Math.max(0, Math.min(100, progress))}%` }),
    [progress],
  );

  const trainerTaskMap = useMemo(() => {
    const map = new Map();
    trainerTasks.forEach((item) => {
      const key = normalizeGameKey(item.game_name);
      if (!key || map.has(key)) return;
      map.set(key, item);
    });
    return map;
  }, [trainerTasks]);

  const filteredInstalledGames = useMemo(() => {
    const keyword = gameFilter.trim().toLowerCase();
    return installedGames.filter((item) => {
      if (!keyword) return true;
      return (
        String(item.name || "").toLowerCase().includes(keyword) ||
        String(item.appid || "").includes(keyword)
      );
    });
  }, [gameFilter, installedGames]);

  const selectedGameKey = normalizeGameKey(selectedInstalledGame?.name);
  const selectedTrainerTask = selectedGameKey ? trainerTaskMap.get(selectedGameKey) : null;
  const currentTrainerName = selectedInstalledGame?.name || trainerQuery.trim();
  const currentTrainerLookup = getTrainerLookup(currentTrainerName);
  const currentCachedTrainer = getCachedTrainer(currentTrainerName);
  const trainerLookupStatus =
    currentCachedTrainer
      ? "已下载"
      :
    trainerVersionsLoading && trainerVersionsGame === currentTrainerName
      ? "匹配中"
      : currentTrainerLookup?.status === "checking"
      ? "查询中"
      : currentTrainerLookup?.status === "available"
        ? "可下载"
        : currentTrainerLookup?.status === "unavailable"
          ? "没有修改器"
          : currentTrainerLookup?.status === "error"
            ? "查询失败"
            : "未检测";
  const saveSettings = async (next) => {
    setSettings(next);
    await request("/settings", {
      method: "POST",
      body: JSON.stringify(next),
    });
  };

  const saveTheme = (nextTheme) => {
    const normalized = ["system", "dark", "light"].includes(nextTheme) ? nextTheme : "system";
    setTheme(normalized);
    localStorage.setItem("stm-theme", normalized);
  };

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme =
      theme === "system" ? "dark light" : theme === "light" ? "light" : "dark";
    window.nativeApp?.appearance?.setTheme?.(theme).catch(() => {});
  }, [theme]);

  const isAbortError = (err) =>
    err?.name === "AbortError" || String(err?.message || "").toLowerCase().includes("abort");

  const runManifestSearch = async (rawTerm) => {
    const keyword = String(rawTerm || "").trim();
    if (!keyword) {
      searchAbortRef.current?.abort();
      setSearching(false);
      setSearchResults([]);
      return;
    }

    const cacheKey = `${settings.search_enhance ? "enhanced" : "plain"}:${keyword.toLowerCase()}`;
    const cached = searchCacheRef.current.get(cacheKey);
    if (cached) {
      setSearchResults(cached);
      setSearching(false);
      return;
    }

    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;
    setSearching(true);
    setError("");

    try {
      const data = await request("/search", {
        method: "POST",
        body: JSON.stringify({
          term: keyword,
          limit: 10,
          translate_fallback: settings.search_enhance,
        }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const items = data.items || [];
      searchCacheRef.current.set(cacheKey, items);
      if (searchCacheRef.current.size > 40) {
        const oldestKey = searchCacheRef.current.keys().next().value;
        if (oldestKey) {
          searchCacheRef.current.delete(oldestKey);
        }
      }
      setSearchResults(items);
    } catch (err) {
      if (isAbortError(err)) return;
      setSearchResults([]);
      setError(err.message);
    } finally {
      if (searchAbortRef.current === controller) {
        searchAbortRef.current = null;
      }
      if (!controller.signal.aborted) {
        setSearching(false);
      }
    }
  };

  const onSearchInputChange = (value) => {
    setTerm(value);
    setError("");
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    if (!value.trim()) {
      searchAbortRef.current?.abort();
      setSearching(false);
      setSearchResults([]);
      return;
    }
    searchTimerRef.current = setTimeout(() => {
      runManifestSearch(value);
    }, settings.search_enhance ? 420 : 280);
  };

  const onSearch = async () => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    await runManifestSearch(term);
  };

  const onSelectGame = (item) => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchAbortRef.current?.abort();
    setSelectedGame(item);
    setTerm(String(item.name || ""));
    setAppid(String(item.appid || ""));
    setSearchResults([]);
  };

  const onStartDownload = async () => {
    if (!appid.trim() || taskId) return;
    setError("");
    setLogs([]);
    manifestOffsetRef.current = 0;
    setProgress(0);
    setTaskStatus("running");
    try {
      const data = await request("/tasks/download", {
        method: "POST",
        body: JSON.stringify({
          appid: appid.trim(),
          source: settings.download_source,
          auto_import: settings.auto_import,
          unlock_dlc: settings.unlock_dlc,
        }),
      });
      setTaskId(data.task_id);
    } catch (err) {
      setTaskStatus("error");
      setError(err.message);
    }
  };

  const onAction = async (path) => {
    setError("");
    try {
      await request(path, { method: "POST" });
    } catch (err) {
      setError(err.message);
    }
  };

  const onDeleteImportedGame = async (item) => {
    const ok = window.confirm(`确定删除 ${item.name || item.appid} 的入库文件吗？`);
    if (!ok) return;
    setImportsLoading(true);
    setImportNotice("");
    try {
      const result = await request(`/imports/${item.appid}`, { method: "DELETE" });
      setImportNotice(
        `已删除 ${result.lua_deleted || 0} 个 lua，${result.manifest_deleted || 0} 个 manifest。`,
      );
      await loadImportedGames();
    } catch (err) {
      setImportNotice(err.message);
    } finally {
      setImportsLoading(false);
    }
  };

  const onClearImports = async () => {
    const ok = window.confirm("确定清理所有入库文件吗？这会移除 stplug-in 下的 lua 和关联 manifest。");
    if (!ok) return;
    setImportsLoading(true);
    setImportNotice("");
    try {
      const result = await request("/imports/clear", { method: "POST" });
      setImportNotice(
        `已清理 ${result.lua_deleted || 0} 个 lua，${result.manifest_deleted || 0} 个 manifest。`,
      );
      await loadImportedGames();
    } catch (err) {
      setImportNotice(err.message);
    } finally {
      setImportsLoading(false);
    }
  };

  const clearError = () => setError("");

  const checkTrainerAvailability = async (gameName) => {
    const name = String(gameName || "").trim();

    if (!name) {
      return;
    }

    setTrainerError("");
    setTrainerLookupForGame(name, { status: "checking", message: "正在查找修改器" });
    try {
      const result = await request("/trainer/search", {
        method: "POST",
        body: JSON.stringify({ game_name: name }),
      });
      const hasTrainer = (result.items || []).length > 0;
      setTrainerLookupForGame(name, {
        status: hasTrainer ? "available" : "unavailable",
        message: hasTrainer ? "可下载" : "没有修改器",
      });
    } catch (err) {
      setTrainerLookupForGame(name, { status: "error", message: err.message });
    }
  };

  const selectInstalledGame = (item) => {
    setSelectedInstalledGame(item);
    setTrainerQuery(item.name || "");
    if (trainerVersionsGame !== (item.name || "")) {
      setTrainerVersions(null);
      setTrainerVersionsGame("");
      setTrainerResolvedName("");
      setTrainerAlternatives([]);
      setTrainerMatchStatus("idle");
    }
  };

  const fetchTrainerVersions = async (gameName) => {
    if (!gameName) return;
    if (getCachedTrainer(gameName)) {
      setTrainerVersions(null);
      setTrainerVersionsGame(gameName);
      setTrainerResolvedName("");
      setTrainerAlternatives([]);
      setTrainerMatchStatus("idle");
      return;
    }
    const requestId = ++trainerRequestRef.current;
    setTrainerVersionsLoading(true);
    setTrainerVersions(null);
    setTrainerVersionsGame(gameName);
    setTrainerResolvedName("");
    setTrainerAlternatives([]);
    setTrainerMatchStatus("checking");
    setTrainerError("");
    try {
      const res = await request("/trainer/versions", {
        method: "POST",
        body: JSON.stringify({ game_name: gameName }),
      });
      if (requestId !== trainerRequestRef.current) return;
      const items = res.items || [];
      const resolvedGame = res.resolved_game || "";
      const matchStatus = res.match_status || (items.length > 0 ? "exact" : "none");
      setTrainerVersions(items);
      setTrainerResolvedName(resolvedGame);
      setTrainerAlternatives(res.alternatives || []);
      setTrainerMatchStatus(matchStatus);
      setTrainerLookupForGame(gameName, {
        status: items.length > 0 ? "available" : "unavailable",
        message:
          items.length > 0
            ? matchStatus === "approx" && resolvedGame
              ? `已匹配 ${resolvedGame}`
              : "可下载"
            : "没有修改器",
      });
    } catch (err) {
      if (requestId !== trainerRequestRef.current) return;
      setTrainerError(err.message);
      setTrainerVersions([]);
      setTrainerResolvedName("");
      setTrainerAlternatives([]);
      setTrainerMatchStatus("error");
      setTrainerLookupForGame(gameName, { status: "error", message: err.message });
    } finally {
      if (requestId === trainerRequestRef.current) {
        setTrainerVersionsLoading(false);
      }
    }
  };

  const onDownloadTrainerVersion = async (trainerItem, linkItem) => {
    const url = linkItem.url;
    setTrainerDownloadingUrl(url);
    setTrainerError("");
    try {
      await request("/trainer/download", {
        method: "POST",
        body: JSON.stringify({
          trainer_url: trainerItem.url,
          game_name: trainerItem.game_name || currentTrainerName,
          download_url: url,
          download_label: linkItem.label || trainerItem.title,
        }),
      });
      await refreshTrainerState();
      await loadTrainerCache();
    } catch (err) {
      setTrainerError(err.message);
    } finally {
      setTrainerDownloadingUrl("");
    }
  };

  useEffect(() => {
    const gameName = selectedInstalledGame?.name || "";
    if (!gameName) return;
    if (getCachedTrainer(gameName)) return;
    const lookup = getTrainerLookup(gameName);
    if (lookup?.status !== "available") return;
    if (trainerVersionsGame === gameName && (trainerVersions !== null || trainerVersionsLoading)) return;
    fetchTrainerVersions(gameName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedInstalledGame?.appid, trainerLookups, trainerCached]);

  const onLaunchTrainer = async () => {
    const gameName = currentTrainerName;
    if (!gameName) return;
    setTrainerActionBusy(`launch:${gameName}`);
    setTrainerError("");
    try {
      if (currentCachedTrainer) {
        await request("/trainer/launch-cache", {
          method: "POST",
          body: JSON.stringify({ game_name: gameName }),
        });
      } else {
        if (currentTrainerLookup?.status !== "available") return;
        await request("/trainer/start-latest", {
          method: "POST",
          body: JSON.stringify({ game_name: gameName }),
        });
      }
      await refreshTrainerState();
      await loadTrainerCache();
    } catch (err) {
      setTrainerError(err.message);
    } finally {
      setTrainerActionBusy("");
    }
  };

  const onDeleteCachedTrainer = async () => {
    const gameName = currentTrainerName;
    if (!gameName || !currentCachedTrainer) return;
    const ok = window.confirm(`确定删除「${gameName}」的本地修改器缓存吗？`);
    if (!ok) return;
    setTrainerActionBusy(`delete:${gameName}`);
    setTrainerError("");
    try {
      await request("/trainer/cache", {
        method: "DELETE",
        body: JSON.stringify({ game_name: gameName }),
      });
      setTrainerVersions(null);
      setTrainerVersionsGame("");
      setTrainerResolvedName("");
      setTrainerAlternatives([]);
      setTrainerMatchStatus("idle");
      await refreshTrainerState();
      await loadTrainerCache();
    } catch (err) {
      setTrainerError(err.message);
    } finally {
      setTrainerActionBusy("");
    }
  };

  const onStopTrainer = async () => {
    if (!selectedTrainerTask?.id) return;
    setTrainerActionBusy(`stop:${selectedTrainerTask.id}`);
    setTrainerError("");
    try {
      await request(`/trainer/stop/${selectedTrainerTask.id}`, { method: "POST" });
      await refreshTrainerState();
    } catch (err) {
      setTrainerError(err.message);
    } finally {
      setTrainerActionBusy("");
    }
  };

  const renderOverviewPage = () => (
    <section className="overview-page">
      {/* 上半区：搜索 + 任务 */}
      <div className="overview-top">
        {/* 左侧：游戏搜索 */}
        <div className="glass-panel flex min-h-0 flex-col rounded-2xl p-3 sm:p-4 overview-search-col">
          <div className="section-title mb-2">
            <Search className="h-4 w-4" />
            <span>游戏搜索</span>
          </div>
          <div className="flex gap-2">
            <input
              value={term}
              onChange={(e) => onSearchInputChange(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSearch()}
              placeholder="输入中文名、英文名或 AppID"
              className="codex-input flex-1"
            />
            <button onClick={onSearch} disabled={searching || !term.trim()} className="codex-btn-primary shrink-0">
              {searching ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />搜索中
                </>
              ) : (
                <>
                  <Search className="mr-1.5 h-4 w-4" />搜索
                </>
              )}
            </button>
          </div>
          <div className="manifest-search-meta">
            <span>{settings.search_enhance ? "已启用中英文翻译回退" : "可在设置中开启搜索增强"}</span>
            {searching && <span className="manifest-searching">正在搜索...</span>}
          </div>
          <div className="mt-2 min-h-0 flex-1 overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] p-2">
            {searchResults.length > 0 ? (
              <div className="space-y-1.5">
                {searchResults.map((item, idx) => (
                  <button key={`${item.appid}-${idx}`} onClick={() => onSelectGame(item)} className="search-item group">
                    <div className="flex min-w-0 items-center gap-3">
                      {item.image ? (
                        <img src={item.image} alt="" className="h-10 w-20 rounded-md object-cover ring-1 ring-[var(--line)]" />
                      ) : (
                        <div className="flex h-10 w-20 items-center justify-center rounded-md bg-[var(--panel-soft)]">
                          <Sparkles className="h-4 w-4 text-[var(--dim)]" />
                        </div>
                      )}
                      <div className="min-w-0 text-left">
                        <p className="truncate text-sm font-semibold text-[var(--text)]">{item.name || "未命名游戏"}</p>
                        <p className="text-xs text-[var(--dim)]">AppID: {item.appid}</p>
                      </div>
                    </div>
                    <SquareArrowOutUpRight className="h-4 w-4 text-[var(--dim)] transition-colors group-hover:text-[var(--accent-2)]" />
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Search}
                title={term.trim() ? (searching ? "正在搜索" : "没有找到结果") : "输入关键词开始搜索"}
                description={term.trim() ? "可使用中文、英文名或 AppID" : "搜索结果会显示在这里，点选后可直接开始下载。"}
              />
            )}
          </div>
        </div>

        {/* 右侧：任务执行 */}
        <div className="glass-panel flex min-h-0 flex-col rounded-2xl p-3 sm:p-4 overview-task-col">
          <div className="section-title mb-2">
            <Download className="h-4 w-4" />
            <span>任务执行</span>
          </div>

          {/* AppID 输入 + 下载按钮 */}
          <div className="mb-3 flex gap-2">
            <input
              value={appid}
              onChange={(e) => setAppid(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onStartDownload()}
              placeholder="输入 AppID（如 570）"
              className="codex-input flex-1"
            />
            <button disabled={!!taskId || !appid.trim()} onClick={onStartDownload} className="codex-btn-primary shrink-0 min-w-[110px] justify-center">
              {taskId ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />执行中
                </>
              ) : (
                <>
                  <Download className="mr-1.5 h-4 w-4" />开始下载
                </>
              )}
            </button>
          </div>

          {/* 当前选择 + 快捷选项 */}
          <div className="manifest-task-grid mb-3">
            <div className="manifest-task-card">
              <p className="manifest-card-kicker">当前选择</p>
              <div className="mt-1.5 flex items-center gap-2 text-sm">
                {selectedGame ? (
                  <>
                    <CheckCircle className="h-4 w-4 shrink-0 text-[var(--success)]" />
                    <span className="text-[var(--muted)] truncate">
                      <span className="font-semibold text-[var(--text)]">{selectedGame.name}</span>
                      <span className="ml-1.5 text-[var(--dim)]">({selectedGame.appid})</span>
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 shrink-0 text-[var(--dim)]" />
                    <span className="text-[var(--dim)]">未选择游戏</span>
                  </>
                )}
              </div>
            </div>

            <div className="manifest-task-card">
              <p className="manifest-card-kicker">快捷选项</p>
              <div className="manifest-toggle-row">
                <label className="manifest-inline-toggle">
                  <input
                    type="checkbox"
                    checked={settings.auto_import}
                    onChange={(e) => saveSettings({ ...settings, auto_import: e.target.checked })}
                  />
                  <span>自动入库</span>
                </label>
                <label className="manifest-inline-toggle">
                  <input
                    type="checkbox"
                    checked={settings.search_enhance}
                    onChange={(e) => saveSettings({ ...settings, search_enhance: e.target.checked })}
                  />
                  <span>搜索增强</span>
                </label>
              </div>
              {settings.auto_import && (
                <label className="manifest-inline-toggle manifest-inline-toggle-wide">
                  <input
                    id="unlock-dlc-cb"
                    type="checkbox"
                    checked={settings.unlock_dlc}
                    onChange={(e) => saveSettings({ ...settings, unlock_dlc: e.target.checked })}
                  />
                  <span>同步复制 manifest 到 depotcache 以解锁 DLC</span>
                </label>
              )}
            </div>
          </div>

          {/* 下载进度条 */}
          <div className="mb-1 flex items-center justify-between gap-2 text-xs font-medium text-[var(--muted)]">
            <div className="flex items-center gap-1.5 min-w-0 truncate">
              {selectedGame ? (
                <>
                  <HardDrive className="h-3.5 w-3.5 shrink-0 text-[var(--accent-2)]" />
                  <span className="text-[var(--dim)] truncate">下载后写入 {settings.auto_import ? "SteamTools 入库目录" : "download 目录"}</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[var(--dim)]" />
                  <span className="text-[var(--dim)]">先从左侧搜索结果选择一个游戏</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="font-bold text-[var(--text)]">{Math.round(progress)}%</span>
              {taskStatus === "running" && <span className="mini-pill mini-pill-blue">下载中</span>}
              {taskStatus === "success" && <span className="mini-pill mini-pill-green">完成</span>}
            </div>
          </div>
          <div className="mb-3">
            <div className="progress-track">
              <div className="progress-fill" style={progressStyle} />
            </div>
          </div>

          {/* 日志区域 */}
          <div ref={logContainerRef} className="min-h-0 flex-1 overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] p-2.5 font-mono text-xs leading-relaxed text-[var(--muted)]">
            {logs.length === 0 ? (
              <div className="flex h-full min-h-[48px] items-center justify-center text-[var(--dim)]">
                <FileText className="mr-2 h-3.5 w-3.5" />开始下载后显示日志
              </div>
            ) : (
              logs.map((line, idx) => (
                <div key={`${idx}-${line.slice(0, 8)}`} className="log-line animate-fade-in">{line}</div>
              ))
            )}
          </div>

          {/* 操作按钮 + 错误提示 */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button onClick={() => onAction("/actions/open-download-folder")} className="codex-btn-secondary">
              <FolderOpen className="mr-1.5 h-4 w-4" />下载目录
            </button>
            {logs.length > 0 && (
              <button onClick={() => setLogs([])} className="codex-btn-secondary">
                <Eraser className="mr-1.5 h-4 w-4" />清空日志
              </button>
            )}
            {error && (
              <div className="error-alert flex items-center gap-2 flex-1 min-w-0">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span className="truncate">{error}</span>
                <button onClick={clearError} className="shrink-0 rounded-full p-0.5 transition-colors hover:bg-[var(--panel-soft)]">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 下半区：已入库游戏 */}
      <div className="glass-panel flex min-h-0 flex-col rounded-2xl p-3 sm:p-4 overview-imports-col">
        <div className="flex items-center gap-3 mb-2">
          <div className="section-title mb-0">
            <Library className="h-4 w-4" />
            <span>已入库游戏</span>
            <span className="section-count-badge">{importedGames.length}</span>
          </div>
          <div className="ml-auto flex gap-2 shrink-0">
            <button onClick={loadImportedGames} disabled={importsLoading} className="codex-btn-secondary">
              <RefreshCw className={`mr-1.5 h-4 w-4 ${importsLoading ? "animate-spin" : ""}`} />检测
            </button>
            <button onClick={onClearImports} disabled={importsLoading || importedGames.length === 0} className="codex-btn-danger">
              <Eraser className="mr-1.5 h-4 w-4" />清理全部
            </button>
          </div>
        </div>
        {importNotice && <div className="mb-2 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-3 py-1.5 text-xs text-[var(--muted)]">{importNotice}</div>}
        <div className="min-h-0 flex-1 overflow-auto">
          {importsLoading && importedGames.length === 0 ? (
            <EmptyState icon={Loader2} title="检测中" description="正在扫描 stplug-in 与 manifest 文件。" />
          ) : importedGames.length === 0 ? (
            <EmptyState icon={Library} title="暂无已入库游戏" description="完成一次下载并开启自动入库后会显示在这里。" />
          ) : (
            <div className="import-grid">
              {importedGames.map((item) => (
                <div key={`${item.appid}-${item.lua_path}`} className="import-item">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-[var(--text)]">{item.name || "未知游戏"}</p>
                    <p className="mt-0.5 text-xs text-[var(--dim)]">manifest {item.existing_manifest_count}/{item.manifest_count}</p>
                  </div>
                  <button onClick={() => onDeleteImportedGame(item)} disabled={importsLoading} className="icon-danger-btn" title="删除入库">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );

  const renderTrainerPage = () => (
    <section className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-12">
      <div className="glass-panel flex min-h-0 flex-col rounded-2xl p-5 xl:col-span-4">
        <div className="section-title mb-4">
          <Gamepad2 className="h-4 w-4" />
          <span>选择游戏</span>
          <span className="section-count-badge ml-auto">{installedGames.length}</span>
        </div>
        <div className="mb-4 flex gap-2">
          <div className="search-input-wrap relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#c4ccd8]" />
            <input
              value={gameFilter}
              onChange={(e) => setGameFilter(e.target.value)}
              placeholder="筛选游戏或 AppID"
              className="codex-input search-input w-full"
            />
          </div>
          <button onClick={() => loadInstalledGames()} disabled={installedLoading} className="codex-btn-secondary">
            <RefreshCw className={`h-4 w-4 ${installedLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
        {installedError && <div className="error-alert mb-3">{installedError}</div>}
        <div className="min-h-0 flex-1 space-y-2.5 overflow-auto pr-1">
          {installedLoading && filteredInstalledGames.length === 0 ? (
            <EmptyState icon={Loader2} title="扫描中" description="" />
          ) : filteredInstalledGames.length === 0 ? (
            <EmptyState icon={Gamepad2} title="没有找到游戏" description="" />
          ) : (
            filteredInstalledGames.map((item) => {
              const key = normalizeGameKey(item.name);
              const task = trainerTaskMap.get(key);
              const lookup = getTrainerLookup(item.name);
              const cached = getCachedTrainer(item.name);
              const active = selectedInstalledGame?.appid === item.appid;
              return (
                <button key={item.appid} className={`installed-game-card ${active ? "installed-game-card-active" : ""}`} onClick={() => selectInstalledGame(item)}>
                  {item.image ? <img src={item.image} alt="" className="installed-game-art" /> : <div className="installed-game-art installed-game-art-fallback" />}
                  <div className="min-w-0 flex-1 text-left">
                    <p className="truncate text-sm font-semibold text-[var(--text)]">{item.name || "未知游戏"}</p>
                    <p className="mt-0.5 text-xs text-[var(--dim)]">AppID {item.appid}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {cached && <span className="mini-pill mini-pill-blue">已下载</span>}
                      {lookup?.status === "checking" && <span className="mini-pill mini-pill-slate">匹配中</span>}
                      {lookup?.status === "available" && <span className="mini-pill mini-pill-green">有修改器</span>}
                      {lookup?.status === "unavailable" && <span className="mini-pill mini-pill-amber">没有修改器</span>}
                      {lookup?.status === "error" && <span className="mini-pill mini-pill-amber">查询失败</span>}
                      {task?.status === "downloading" && <span className="mini-pill mini-pill-amber">下载中</span>}
                      {task?.is_running && <span className="mini-pill mini-pill-blue">运行中</span>}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-col gap-4 xl:col-span-8">
        <div className="glass-panel rounded-2xl p-5">
          <div className="section-title mb-4">
            <Play className="h-4 w-4" />
            <span>修改器控制</span>
          </div>

          <div className="mb-5 flex items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] p-4">
            <FolderCog className="h-5 w-5 shrink-0 text-[var(--accent-2)]" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--text)] truncate">{selectedInstalledGame?.name || trainerQuery || "未选择游戏"}</p>
              {selectedInstalledGame && <p className="text-xs text-[var(--dim)] mt-0.5">AppID {selectedInstalledGame.appid}</p>}
            </div>
            <div className="flex gap-2 shrink-0">
              {currentCachedTrainer ? (
                <>
                  <button onClick={onLaunchTrainer} disabled={trainerActionBusy.startsWith("launch")} className="codex-btn-primary">
                    {trainerActionBusy.startsWith("launch") ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Play className="mr-1.5 h-4 w-4" />}
                    启动
                  </button>
                  <button onClick={onDeleteCachedTrainer} disabled={trainerActionBusy.startsWith("delete") || selectedTrainerTask?.is_running} className="codex-btn-danger">
                    {trainerActionBusy.startsWith("delete") ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1.5 h-4 w-4" />}
                    删除
                  </button>
                </>
              ) : (
                <button onClick={() => fetchTrainerVersions(currentTrainerName)} disabled={trainerVersionsLoading || !currentTrainerName} className="codex-btn-primary">
                  {trainerVersionsLoading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
                  {trainerVersionsGame === currentTrainerName && trainerVersions !== null ? "重新获取" : "获取下载列表"}
                </button>
              )}
              <button onClick={onStopTrainer} disabled={!selectedTrainerTask?.is_running || trainerActionBusy.startsWith("stop")} className="codex-btn-danger">
                <StopCircle className="mr-1.5 h-4 w-4" />停止
              </button>
            </div>
          </div>

          {!currentCachedTrainer && trainerVersionsLoading && trainerVersionsGame === currentTrainerName && (
            <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-4 text-sm text-[var(--muted)]">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--accent-2)]" />
                <span>正在为「{currentTrainerName}」匹配最合适的修改器...</span>
              </div>
            </div>
          )}

          {currentCachedTrainer && (
            <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3 text-sm text-[var(--muted)]">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-[var(--success)]" />
                <span>本地已存在该游戏的修改器缓存，不再显示下载入口。</span>
              </div>
            </div>
          )}

          {!currentCachedTrainer && trainerVersions !== null && trainerVersionsGame === currentTrainerName && !trainerVersionsLoading && (
            <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[var(--line)] text-xs font-bold text-[var(--muted)] uppercase tracking-wide flex items-center justify-between">
                <span>推荐下载 ({trainerVersions.length})</span>
                <button onClick={() => setTrainerVersions(null)} className="text-[var(--dim)] hover:text-[var(--text)] transition-colors">×</button>
              </div>
              <div className="px-4 py-3 border-b border-[var(--line)] text-xs text-[var(--dim)] bg-black/10">
                {trainerVersions.length > 0 ? (
                  <div className="space-y-1">
                    <p>
                      {trainerMatchStatus === "approx" && trainerResolvedName
                        ? `已按最接近结果匹配到「${trainerResolvedName}」`
                        : trainerResolvedName
                          ? `已匹配到「${trainerResolvedName}」`
                          : "已完成匹配"}
                    </p>
                    {trainerAlternatives.length > 0 && (
                      <p>其他近似结果：{trainerAlternatives.map((item) => item.game_name).join(" / ")}</p>
                    )}
                  </div>
                ) : (
                  <p>没有找到可直接下载的修改器，可以稍后重试或更换游戏名称。</p>
                )}
              </div>
              {trainerVersions.length === 0 ? (
                <div className="px-4 py-3 text-sm text-[var(--dim)]">未找到可用下载链接</div>
              ) : (
                <div className="divide-y divide-[var(--line)] max-h-72 overflow-auto">
                  {trainerVersions.map((tv, ti) => (
                    <div key={ti} className="px-4 py-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-[var(--text)] truncate">{tv.display_name || currentTrainerName}</p>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[var(--dim)]">
                            <span className="mini-pill mini-pill-slate">{tv.source === "archive" ? "Archive" : "官网"}</span>
                            <span>{tv.source_label || "推荐版本"}</span>
                            {tv.detail && <span>{tv.detail}</span>}
                            <span>{tv.author || "FLiNG"}</span>
                          </div>
                        </div>
                        <span className="text-xs text-[var(--dim)]">{tv.download_links.length} 个入口</span>
                      </div>
                      {tv.download_links.length === 0 ? (
                        <p className="mt-2 text-xs text-[var(--dim)]">暂无直接下载链接，请访问页面手动下载</p>
                      ) : (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {tv.download_links.map((lk, li) => (
                            <button
                              key={li}
                              disabled={!!trainerDownloadingUrl}
                              onClick={() => onDownloadTrainerVersion(tv, lk)}
                              className="codex-btn-secondary text-xs"
                            >
                              {trainerDownloadingUrl === lk.url
                                ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                                : <Download className="mr-1 h-3.5 w-3.5" />}
                              {lk.label || `下载 ${li + 1}`}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-5">
            <MetricCard icon={Search} label="修改器" value={trainerLookupStatus} tone={currentTrainerLookup?.status === "available" ? "emerald" : "slate"} />
            <MetricCard
              icon={MonitorPlay}
              label="运行状态"
              value={selectedTrainerTask?.is_running ? "运行中" : selectedTrainerTask?.status === "downloading" ? "下载中" : "未运行"}
              tone={selectedTrainerTask?.is_running ? "emerald" : "slate"}
            />
            <MetricCard icon={FolderCog} label="当前游戏" value={selectedInstalledGame?.name || "未选择"} tone="amber" />
          </div>

          {selectedTrainerTask?.status === "downloading" && (
            <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3">
              <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                <span className="font-semibold text-[var(--text)]">下载进度</span>
                <span className="text-[var(--muted)]">{Math.round(selectedTrainerTask.progress || 0)}%</span>
              </div>
              <div className="trainer-progress-track">
                <div
                  className="trainer-progress-fill"
                  style={{ width: `${Math.max(0, Math.min(100, Number(selectedTrainerTask.progress || 0)))}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-[var(--muted)]">
                {selectedTrainerTask.message || "正在下载修改器文件..."}
              </p>
            </div>
          )}

          {selectedTrainerTask?.security && (
            <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3 text-sm text-[var(--muted)]">
              <div className="mb-2 flex items-center gap-2 font-semibold text-[var(--text)]">
                <ShieldCheck className="h-4 w-4 text-[var(--accent-2)]" />
                <span>安全提示</span>
              </div>
              <div className="space-y-1.5 text-xs sm:text-sm">
                <p>来源：{selectedTrainerTask.security.source_name || "未知来源"}{selectedTrainerTask.security.download_host ? ` / ${selectedTrainerTask.security.download_host}` : ""}</p>
                {selectedTrainerTask.security.executable_sha256 && <p>可执行文件 SHA-256：{selectedTrainerTask.security.executable_sha256}</p>}
                {selectedTrainerTask.security.package_sha256 && <p>下载包 SHA-256：{selectedTrainerTask.security.package_sha256}</p>}
                <p className={selectedTrainerTask.security.official_source ? "text-[#7ec699]" : "text-[#d9b16c]"}>
                  {selectedTrainerTask.security.summary || "已记录来源与哈希。"}
                </p>
              </div>
            </div>
          )}

          <div className={`rounded-xl border px-4 py-3 text-sm font-medium ${
            currentTrainerLookup?.status === "unavailable"
              ? "border-[var(--warning)]/30 bg-[var(--warning)]/5 text-[var(--warning)]"
              : currentTrainerLookup?.status === "error"
                ? "border-[var(--danger)]/30 bg-[var(--danger)]/5 text-[var(--danger)]"
                : trainerError
                  ? "border-[var(--danger)]/30 bg-[var(--danger)]/5 text-[var(--danger)]"
                  : "border-[var(--line)] bg-[var(--panel-soft)] text-[var(--muted)]"
          }`}>
            {currentTrainerLookup?.status === "unavailable"
              ? `没有找到「${currentTrainerName}」的修改器`
              : currentTrainerLookup?.status === "error"
                ? (currentTrainerLookup.message || "修改器查询失败")
                : trainerError
                  ? trainerError
                  : selectedInstalledGame
                    ? currentCachedTrainer
                      ? `已检测到「${selectedInstalledGame.name}」的本地修改器缓存，可直接启动或删除`
                      : trainerVersionsLoading && trainerVersionsGame === currentTrainerName
                        ? `正在为「${selectedInstalledGame.name}」匹配修改器...`
                        : trainerVersionsGame === currentTrainerName && trainerVersions !== null && trainerVersions.length > 0
                          ? `已为「${selectedInstalledGame.name}」整理好可直接下载的修改器版本`
                          : currentTrainerLookup?.status === "checking"
                            ? `软件启动后正在自动检测「${selectedInstalledGame.name}」是否有修改器`
                            : currentTrainerLookup?.status === "available"
                              ? `已自动检测到「${selectedInstalledGame.name}」有修改器，正在准备下载列表`
                              : `已选择「${selectedInstalledGame.name}」，等待自动检测结果`
                    : "请从左侧选择一个已安装的游戏"
            }
          </div>
        </div>
      </div>
    </section>
  );

  const renderNoticePage = () => (
    <section className="notice-page">
      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <ScrollText className="h-4 w-4" />
          <span>开源许可声明（Open Source Notice）</span>
        </div>
        <div className="notice-text">
          <p>本软件使用或参考了以下开源项目：</p>
          <ol className="notice-list">
            <li>
              <strong>SteamToolPlus</strong><br />
              作者: Jingluohi<br />
              仓库: <a href="https://github.com/Jingluohi/SteamToolPlus" target="_blank" rel="noopener noreferrer">https://github.com/Jingluohi/SteamToolPlus</a><br />
              许可: 未明确提供开源许可证（仅用于学习参考或已获得授权）
            </li>
            <li>
              <strong>Fluent-Install</strong><br />
              作者: zhouchentao666<br />
              仓库: <a href="https://github.com/zhouchentao666/Fluent-Install" target="_blank" rel="noopener noreferrer">https://github.com/zhouchentao666/Fluent-Install</a><br />
              许可: GNU General Public License v3.0 (GPLv3)
            </li>
            <li>
              <strong>steamtoolsmanager</strong><br />
              作者: ecxwxz<br />
              仓库: <a href="https://github.com/ecxwxz/steamtoolsmanager" target="_blank" rel="noopener noreferrer">https://github.com/ecxwxz/steamtoolsmanager</a><br />
              许可: MIT License
            </li>
            <li>
              <strong>SteamTools</strong><br />
              作者: BeyondDimension<br />
              仓库: <a href="https://github.com/BeyondDimension/SteamTools" target="_blank" rel="noopener noreferrer">https://github.com/BeyondDimension/SteamTools</a><br />
              许可: GNU General Public License v3.0 (GPLv3)
            </li>
          </ol>
          <p className="mt-4">本软件基于上述 GPLv3 项目进行修改与扩展，<br />因此整体遵循 <strong>GNU General Public License v3.0（GPLv3）</strong>发布。</p>
          <p>根据 GPLv3 要求，本软件的完整源代码可在以下地址获取：<br />
            <a href="https://github.com/MonsterN58/SteamToolsALLinOne" target="_blank" rel="noopener noreferrer">https://github.com/MonsterN58/SteamToolsALLinOne</a>
          </p>
          <p className="mt-2">MIT License 部分代码遵循其原始许可，已保留相关版权声明。</p>
          <div className="notice-disclaimer mt-4">
            <p><strong>免责声明：</strong><br />本软件按"原样（AS IS）"提供，不提供任何形式的担保。</p>
          </div>
          <div className="notice-author mt-4">
            <p>作者：MonsterN58</p>
          </div>
        </div>
      </div>
    </section>
  );

  const renderSettingsPage = () => (
    <section className="settings-page">
      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <Settings className="h-4 w-4" />
          <span>下载设置</span>
        </div>
        <div className="settings-list">
          <SettingRow
            icon={Globe}
            title="下载源"
            description="选择 Manifest 下载时优先使用的网络来源。"
          >
            <select
              value={settings.download_source}
              onChange={(e) => saveSettings({ ...settings, download_source: e.target.value })}
              className="codex-select"
            >
              <option value="auto">智能源</option>
              <option value="domestic">国内源</option>
              <option value="overseas">国外源</option>
            </select>
          </SettingRow>
          <SettingRow
            icon={Download}
            title="自动入库"
            description="Manifest 下载完成后自动写入 SteamTools 目录。"
          >
            <select
              value={settings.auto_import ? "true" : "false"}
              onChange={(e) => saveSettings({ ...settings, auto_import: e.target.value === "true" })}
              className="codex-select"
            >
              <option value="false">关闭</option>
              <option value="true">开启</option>
            </select>
          </SettingRow>
          <SettingRow
            icon={Zap}
            title="搜索增强"
            description="搜索游戏时启用翻译回退，提高中英文命中率。"
          >
            <select
              value={settings.search_enhance ? "true" : "false"}
              onChange={(e) => saveSettings({ ...settings, search_enhance: e.target.value === "true" })}
              className="codex-select"
            >
              <option value="false">关闭</option>
              <option value="true">开启</option>
            </select>
          </SettingRow>
        </div>
      </div>

      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <ShieldCheck className="h-4 w-4" />
          <span>补丁工具</span>
        </div>
        <div className="settings-list">
          <SettingRow
            icon={ShieldCheck}
            title="默认模拟器模式"
            description="应用基础配置时使用的模拟器模式。"
          >
            <select
              value={settings.patch_emulator_mode}
              onChange={(e) => saveSettings({ ...settings, patch_emulator_mode: Number(e.target.value) })}
              className="codex-select"
            >
              <option value={0}>标准模式（steam_api）</option>
              <option value={1}>高级模式（steamclient）</option>
            </select>
          </SettingRow>
          <SettingRow
            icon={Zap}
            title="默认 DLL 版本"
            description="模式 0 下选择使用稳定版还是功能版（实验性）DLL。"
          >
            <select
              value={settings.patch_use_experimental ? "true" : "false"}
              onChange={(e) => saveSettings({ ...settings, patch_use_experimental: e.target.value === "true" })}
              className="codex-select"
            >
              <option value="false">稳定版</option>
              <option value="true">功能版（实验性）</option>
            </select>
          </SettingRow>
          <SettingRow
            icon={User}
            title="默认用户名"
            description="应用基础配置后设置的默认 Steam 用户名。"
          >
            <input
              value={settings.patch_default_username}
              onChange={(e) => saveSettings({ ...settings, patch_default_username: e.target.value })}
              className="codex-input w-36"
              placeholder="Player"
            />
          </SettingRow>
          <SettingRow
            icon={Globe}
            title="默认语言"
            description="模拟器使用的默认 Steam 语言。"
          >
            <select
              value={settings.patch_default_language}
              onChange={(e) => saveSettings({ ...settings, patch_default_language: e.target.value })}
              className="codex-select"
            >
              <option value="schinese">简体中文</option>
              <option value="tchinese">繁體中文</option>
              <option value="english">English</option>
              <option value="japanese">日本語</option>
              <option value="korean">한국어</option>
              <option value="french">Français</option>
              <option value="german">Deutsch</option>
              <option value="spanish">Español</option>
              <option value="russian">Русский</option>
            </select>
          </SettingRow>
        </div>
      </div>

      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <Zap className="h-4 w-4" />
          <span>联机与D加密</span>
        </div>
        <div className="settings-list">
          <SettingRow
            icon={Globe}
            title="默认联机端口"
            description="局域网联机的默认监听端口号。"
          >
            <input
              value={settings.lan_default_port ?? 47584}
              onChange={(e) => saveSettings({ ...settings, lan_default_port: Number(e.target.value) || 47584 })}
              className="codex-input w-28"
              placeholder="47584"
              type="number"
            />
          </SettingRow>
          <SettingRow
            icon={ShieldCheck}
            title="D加密自动备份"
            description="应用 D 加密补丁时自动备份被覆盖的原始文件。"
          >
            <select
              value={(settings.denuvo_auto_backup ?? true) ? "true" : "false"}
              onChange={(e) => saveSettings({ ...settings, denuvo_auto_backup: e.target.value === "true" })}
              className="codex-select"
            >
              <option value="true">开启</option>
              <option value="false">关闭</option>
            </select>
          </SettingRow>
        </div>
      </div>

      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <HardDrive className="h-4 w-4" />
          <span>运行信息</span>
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <MetricCard icon={HardDrive} label="已入库" value={`${importedGames.length} 个`} tone="slate" />
          <MetricCard icon={Gamepad2} label="已安装游戏" value={`${installedGames.length} 个`} tone="slate" />
          <MetricCard icon={MonitorPlay} label="修改器任务" value={`${trainerTasks.length} 个`} tone="slate" />
        </div>
      </div>

      <div className="glass-panel p-4 sm:p-5">
        <div className="section-title mb-3">
          <Sun className="h-4 w-4" />
          <span>主题</span>
        </div>
        <div className="settings-list">
          <SettingRow
            icon={theme === "light" ? Sun : theme === "dark" ? Moon : Monitor}
            title="界面主题"
            description="选择跟随系统，或固定使用深色、浅色主题。"
          >
            <select
              value={theme}
              onChange={(e) => saveTheme(e.target.value)}
              className="codex-select"
            >
              <option value="system">跟随系统</option>
              <option value="dark">深色</option>
              <option value="light">浅色</option>
            </select>
          </SettingRow>
        </div>
      </div>
    </section>
  );

  return (
    <div className="app-root">
      <aside className="app-sidebar">
        <div className="app-brand">
          <span className="app-brand-mark">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="app-brand-title">SteamTools</p>
            <p className="app-brand-subtitle">ALLinOne</p>
          </div>
        </div>

        <nav className="app-nav">
          <PageTab active={activePage === "overview"} icon={Download} label="Manifest 下载" hint="下载与入库" onClick={() => setActivePage("overview")} />
          <PageTab active={activePage === "trainers"} icon={Gamepad2} label="修改器" hint="搜索与启动" onClick={() => setActivePage("trainers")} />
          <PageTab active={activePage === "patch"} icon={ShieldCheck} label="补丁工具" hint="免Steam·联机·D加密" onClick={() => setActivePage("patch")} />
          <PageTab active={activePage === "tools"} icon={Wrench} label="Steam 工具箱" hint="加速·账号·库存·令牌" onClick={() => setActivePage("tools")} />
          <PageTab active={activePage === "settings"} icon={Settings} label="设置" hint="偏好与外观" onClick={() => setActivePage("settings")} />
          <PageTab active={activePage === "notice"} icon={ScrollText} label="声明" hint="开源许可·免责" onClick={() => setActivePage("notice")} />
        </nav>

        <div className="app-sidebar-footer">
          <p className="sidebar-footer-label">当前任务</p>
          <StatusBadge status={taskStatus} />
        </div>
      </aside>

      <div className="app-main">
        <header className="app-page-header">
          <div>
            <p className="app-page-kicker">
              {activePage === "overview" ? "Manifest" : activePage === "trainers" ? "Trainer" : activePage === "patch" ? "Patch" : activePage === "tools" ? "Toolbox" : activePage === "notice" ? "Notice" : "Settings"}
            </p>
            <h1 className="app-page-title">
              {activePage === "overview" ? "Manifest 下载" : activePage === "trainers" ? "修改器" : activePage === "patch" ? "补丁工具" : activePage === "tools" ? "Steam 工具箱" : activePage === "notice" ? "开源许可声明" : "设置"}
            </h1>
          </div>
          <StatusBadge status={taskStatus} />
        </header>

        <main className={`app-content${activePage === "overview" ? " app-content-overflow-hidden" : ""}`}>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "overview" ? " hidden" : ""}`}>{renderOverviewPage()}</div>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "trainers" ? " hidden" : ""}`}>{renderTrainerPage()}</div>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "patch" ? " hidden" : ""}`}><SteamPatchPage /></div>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "tools" ? " hidden" : ""}`}><SteamToolsPage /></div>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "settings" ? " hidden" : ""}`}>{renderSettingsPage()}</div>
          <div className={`flex flex-col min-h-0 flex-1${activePage !== "notice" ? " hidden" : ""}`}>{renderNoticePage()}</div>
        </main>
      </div>
    </div>
  );
}

export default App;
