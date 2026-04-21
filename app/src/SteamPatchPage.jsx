import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Award,
  BarChart2,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  FolderOpen,
  Gamepad2,
  Loader2,
  Monitor,
  Network,
  Package,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  Shield,
  BarChart,
  Trash2,
  Trophy,
  User,
  X,
  Zap,
} from "lucide-react";

const API_BASE = window.nativeApp?.backendUrl || "http://127.0.0.1:18765";
const PATCH_STATE_KEY = "stm-patch-state";

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

// ── D加密预置游戏列表（来源：SteamToolPlus 游戏数据库）──────
const DENUVO_PRESETS = [
  { appId: "2358720", name: "黑神话：悟空", eng: "Black Myth: Wukong", url: "https://pan.baidu.com/s/1lQwDDi_vEItrV5aCcCaLcw?pwd=dbwj", code: "dbwj" },
  { appId: "2246340", name: "怪物猎人：荒野", eng: "Monster Hunter Wilds", url: "https://pan.baidu.com/s/1u2UzeqfbGr1eG1dt-k4M8g?pwd=tyz6", code: "tyz6" },
  { appId: "3321460", name: "红色沙漠", eng: "Crimson Desert", url: "https://pan.baidu.com/s/1fVilu8rcKiAsL-FHUHfLZA?pwd=a4vw", code: "a4vw" },
  { appId: "3489700", name: "剑星", eng: "Stellar Blade", url: "https://pan.baidu.com/s/1jIZRjAseMlQZFoh9KmTgfQ?pwd=anvn", code: "anvn" },
  { appId: "2852190", name: "怪物猎人物语 3：命运双龙", eng: "MH Stories 3: Twisted Reflection", url: "https://pan.baidu.com/s/1R1hUpnDwQopeN8FOVutKHA?pwd=548s", code: "548s" },
];

// ── 圆形进度环 ────────────────────────────────────────────
function CircleProgress({ percent, size = 48, strokeWidth = 4, color = "var(--accent)" }) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (percent / 100) * circ;
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="var(--panel-strong)" strokeWidth={strokeWidth} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
    </svg>
  );
}

// ── 资源管理面板 ──────────────────────────────────────────────
function ResourcePanel() {
  const [resources, setResources] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(null);
  const pollRef = useRef(null);

  const checkResources = useCallback(async () => {
    try {
      const data = await fetch(`${API_BASE}/patch/resources/check`).then((r) => r.json());
      setResources(data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    checkResources();
  }, [checkResources]);

  useEffect(() => {
    if (!downloading) return;
    pollRef.current = setInterval(async () => {
      try {
        const p = await fetch(`${API_BASE}/patch/resources/progress`).then((r) => r.json());
        setProgress(p);
        if (p.status === "done" || p.status === "error") {
          setDownloading(false);
          clearInterval(pollRef.current);
          checkResources();
        }
      } catch {}
    }, 1500);
    return () => clearInterval(pollRef.current);
  }, [downloading, checkResources]);

  const startDownload = async () => {
    setDownloading(true);
    setProgress({ status: "fetching", progress: 0, message: "正在检查资源获取方式…" });
    try {
      const resp = await fetch(`${API_BASE}/patch/resources/download`, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.ok === false) {
        throw new Error(data.detail || data.message || `请求失败: ${resp.status}`);
      }
    } catch (e) {
      setDownloading(false);
      const message = e instanceof Error ? e.message : String(e);
      setProgress({ status: "error", progress: 0, message });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--dim)] py-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> 检测资源中…
      </div>
    );
  }

  const isReady = resources?.ready;
  const activeProgress = progress && ["fetching", "downloading", "extracting"].includes(progress.status);
  const pct = progress?.progress ?? 0;
  const statusColor = progress?.status === "error" ? "var(--danger)"
    : progress?.status === "done" ? "var(--success)" : "var(--accent)";

  return (
    <div className={`rounded-xl border p-4 ${isReady
      ? "border-[var(--success)]/30 bg-[var(--success)]/5"
      : "border-[var(--warning)]/30 bg-[var(--warning)]/5"}`}
    >
      <div className="flex items-center gap-4">
        {/* 圆形进度环 / 状态图标 */}
        {(activeProgress) ? (
          <div className="relative shrink-0">
            <CircleProgress percent={pct} size={52} strokeWidth={4} color={statusColor} />
            <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-[var(--text)] rotate-90">
              {pct}%
            </span>
          </div>
        ) : isReady ? (
          <CheckCircle className="h-6 w-6 shrink-0 text-[var(--success)]" />
        ) : (
          <AlertCircle className="h-6 w-6 shrink-0 text-[var(--warning)]" />
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-[var(--text)]">GBE Fork 模拟器 DLL</span>
            {isReady && <span className="mini-pill">就绪</span>}
          </div>

          {/* 已有 DLL 列表 */}
          {isReady && resources.stable?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {resources.stable.map((dll) => (
                <span key={dll} className="rounded bg-[var(--panel-strong)] px-1.5 py-0.5 text-[11px] font-mono text-[var(--text)]">{dll}</span>
              ))}
              {resources.experimental?.map((dll) => (
                <span key={"exp-" + dll} className="rounded bg-[var(--panel-soft)] px-1.5 py-0.5 text-[11px] font-mono text-[var(--muted)]">{dll}<span className="opacity-50 ml-0.5">(exp)</span></span>
              ))}
            </div>
          )}

          {/* 状态消息 */}
          {progress?.message && (
            <p className={`text-xs mt-1 ${
              progress.status === "error" ? "text-[var(--danger)]"
              : progress.status === "done" ? "text-[var(--success)]"
              : "text-[var(--muted)]"}`}>
              {progress.message}
            </p>
          )}
          {!isReady && !downloading && !progress && (
            <p className="text-xs text-[var(--warning)] mt-1">缺少 steam_api.dll，点击「从 GitHub 下载」自动获取（约 13 MB）</p>
          )}
        </div>

        <div className="flex gap-1.5 shrink-0">
          <button onClick={checkResources} className="codex-btn-secondary p-1.5" title="刷新">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button onClick={startDownload} disabled={downloading} className="codex-btn-secondary text-xs">
            {downloading ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Download className="mr-1 h-3 w-3" />}
            {isReady ? "检查来源" : "从 GitHub 下载"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 子面板：局域网联机 ────────────────────────────────────
function LanConfigPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({
    customBroadcasts: [],
    listenPort: 47584,
    autoAcceptInvite: "none",
    whitelist: [],
  });
  const [newIp, setNewIp] = useState("");
  const [newWhitelist, setNewWhitelist] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/lan/load", {
      method: "POST",
      body: JSON.stringify({ game_path: gamePath }),
    })
      .then(setConfig)
      .catch(() => {});
  }, [gamePath]);

  const addBroadcast = () => {
    const ip = newIp.trim();
    if (!ip) return;
    setConfig((c) => ({ ...c, customBroadcasts: [...c.customBroadcasts, ip] }));
    setNewIp("");
  };

  const removeBroadcast = (idx) => {
    setConfig((c) => ({
      ...c,
      customBroadcasts: c.customBroadcasts.filter((_, i) => i !== idx),
    }));
  };

  const addWhitelist = () => {
    const id = newWhitelist.trim();
    if (!id) return;
    setConfig((c) => ({ ...c, whitelist: [...c.whitelist, id] }));
    setNewWhitelist("");
  };

  const removeWhitelist = (idx) => {
    setConfig((c) => ({ ...c, whitelist: c.whitelist.filter((_, i) => i !== idx) }));
  };

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const result = await request("/patch/lan/save", {
        method: "POST",
        body: JSON.stringify({ game_path: gamePath, config }),
      });
      setMsg(result.message || "已保存");
    } catch (err) {
      setMsg(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Network className="h-4 w-4" /><span>局域网联机配置</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>

      {/* 广播 IP */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-[var(--text)] mb-1">自定义广播 IP / 域名</label>
        <p className="text-xs text-[var(--dim)] mb-2">添加其他玩家的 IP 以进行局域网联机</p>
        <div className="flex gap-2 mb-2">
          <input value={newIp} onChange={(e) => setNewIp(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addBroadcast()} placeholder="192.168.1.100" className="codex-input flex-1" />
          <button onClick={addBroadcast} className="codex-btn-secondary shrink-0"><Plus className="h-4 w-4" /></button>
        </div>
        {config.customBroadcasts.map((ip, idx) => (
          <div key={idx} className="flex items-center gap-2 py-1 text-sm text-[var(--text)]">
            <span className="flex-1 font-mono">{ip}</span>
            <button onClick={() => removeBroadcast(idx)} className="icon-danger-btn"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
      </div>

      {/* 监听端口 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-[var(--text)] mb-1">监听端口</label>
        <input value={config.listenPort} onChange={(e) => setConfig((c) => ({ ...c, listenPort: e.target.value }))} placeholder="47584（默认）" className="codex-input w-48" />
      </div>

      {/* 自动接受邀请 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-[var(--text)] mb-1">自动接受邀请</label>
        <select value={config.autoAcceptInvite} onChange={(e) => setConfig((c) => ({ ...c, autoAcceptInvite: e.target.value }))} className="codex-select">
          <option value="none">不自动接受</option>
          <option value="all">接受所有邀请</option>
          <option value="whitelist">仅接受白名单</option>
        </select>
      </div>

      {/* 白名单 */}
      {config.autoAcceptInvite === "whitelist" && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-[var(--text)] mb-1">白名单（SteamID64）</label>
          <div className="flex gap-2 mb-2">
            <input value={newWhitelist} onChange={(e) => setNewWhitelist(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addWhitelist()} placeholder="76561198xxxxxxxxx" className="codex-input flex-1" />
            <button onClick={addWhitelist} className="codex-btn-secondary shrink-0"><Plus className="h-4 w-4" /></button>
          </div>
          {config.whitelist.map((id, idx) => (
            <div key={idx} className="flex items-center gap-2 py-1 text-sm text-[var(--text)]">
              <span className="flex-1 font-mono">{id}</span>
              <button onClick={() => removeWhitelist(idx)} className="icon-danger-btn"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}

      {msg && <div className="text-sm text-[var(--muted)] mb-3">{msg}</div>}
      <button onClick={save} disabled={saving} className="codex-btn-primary">
        {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存配置
      </button>
    </div>
  );
}

// ── 子面板：DLC 配置 ──────────────────────────────────────
function DlcConfigPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ unlockAll: true, dlcs: [] });
  const [newAppId, setNewAppId] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/dlc/load", {
      method: "POST",
      body: JSON.stringify({ game_path: gamePath }),
    })
      .then(setConfig)
      .catch(() => {});
  }, [gamePath]);

  const addDlc = () => {
    if (!newAppId.trim()) return;
    setConfig((c) => ({
      ...c,
      dlcs: [...c.dlcs, { appId: newAppId.trim(), name: newName.trim() }],
    }));
    setNewAppId("");
    setNewName("");
  };

  const removeDlc = (idx) => {
    setConfig((c) => ({ ...c, dlcs: c.dlcs.filter((_, i) => i !== idx) }));
  };

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const result = await request("/patch/dlc/save", {
        method: "POST",
        body: JSON.stringify({ game_path: gamePath, config }),
      });
      setMsg(result.message || "已保存");
    } catch (err) {
      setMsg(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Package className="h-4 w-4" /><span>DLC 配置</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>

      <div className="mb-4">
        <label className="flex items-center gap-2 text-sm text-[var(--text)]">
          <input type="checkbox" checked={config.unlockAll} onChange={(e) => setConfig((c) => ({ ...c, unlockAll: e.target.checked }))} />
          自动解锁所有 DLC
        </label>
      </div>

      <div className="mb-4">
        <label className="block text-sm font-medium text-[var(--text)] mb-1">手动添加 DLC</label>
        <div className="flex gap-2 mb-2">
          <input value={newAppId} onChange={(e) => setNewAppId(e.target.value)} placeholder="DLC AppID" className="codex-input w-32" />
          <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="DLC 名称（可选）" className="codex-input flex-1" />
          <button onClick={addDlc} className="codex-btn-secondary shrink-0"><Plus className="h-4 w-4" /></button>
        </div>
        {config.dlcs.map((dlc, idx) => (
          <div key={idx} className="flex items-center gap-2 py-1 text-sm text-[var(--text)]">
            <span className="font-mono w-24 shrink-0">{dlc.appId}</span>
            <span className="flex-1 truncate">{dlc.name || "—"}</span>
            <button onClick={() => removeDlc(idx)} className="icon-danger-btn"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
      </div>

      <p className="text-xs text-[var(--dim)] mb-3">
        可在 <a href="https://steamdb.info" target="_blank" rel="noopener noreferrer" className="underline">SteamDB</a> 查询 DLC AppID
      </p>

      {msg && <div className="text-sm text-[var(--muted)] mb-3">{msg}</div>}
      <button onClick={save} disabled={saving} className="codex-btn-primary">
        {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存配置
      </button>
    </div>
  );
}

// ── 子面板：用户配置 ──────────────────────────────────────
function UserConfigPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ username: "", language: "schinese", steamId: "", savesFolderName: "", localSavePath: "" });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/user/load", {
      method: "POST",
      body: JSON.stringify({ game_path: gamePath }),
    })
      .then((data) => setConfig((c) => ({ ...c, ...data })))
      .catch(() => {});
  }, [gamePath]);

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const result = await request("/patch/user/save", {
        method: "POST",
        body: JSON.stringify({ game_path: gamePath, config }),
      });
      setMsg(result.message || "已保存");
    } catch (err) {
      setMsg(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><User className="h-4 w-4" /><span>用户配置</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text)] mb-1">用户名</label>
          <input value={config.username} onChange={(e) => setConfig((c) => ({ ...c, username: e.target.value }))} placeholder="Player" className="codex-input w-full" />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text)] mb-1">语言</label>
          <select value={config.language} onChange={(e) => setConfig((c) => ({ ...c, language: e.target.value }))} className="codex-select w-full">
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
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text)] mb-1">SteamID（可选）</label>
          <input value={config.steamId} onChange={(e) => setConfig((c) => ({ ...c, steamId: e.target.value }))} placeholder="76561198xxxxxxxxx" className="codex-input w-full" />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text)] mb-1">存档文件夹（可选）</label>
          <input value={config.savesFolderName} onChange={(e) => setConfig((c) => ({ ...c, savesFolderName: e.target.value }))} placeholder="saves" className="codex-input w-full" />
        </div>
      </div>

      {msg && <div className="text-sm text-[var(--muted)] mb-3">{msg}</div>}
      <button onClick={save} disabled={saving} className="codex-btn-primary">
        {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存配置
      </button>
    </div>
  );
}

// ── 子面板：主配置 ────────────────────────────────────────
function MainConfigPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({
    newAppTicket: false,
    gcToken: false,
    encryptedAppTicket: "",
    disableNetworking: false,
    offlineMode: false,
    enableLogging: false,
    logLevel: "0",
    disableAccountLimit: false,
    forceOffline: false,
    disableCloud: false,
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/main/load", {
      method: "POST",
      body: JSON.stringify({ game_path: gamePath }),
    })
      .then((data) => {
        if (data && typeof data === "object" && !data.detail) {
          setConfig((c) => ({ ...c, ...data }));
        }
      })
      .catch(() => {});
  }, [gamePath]);

  const toggle = (key) => setConfig((c) => ({ ...c, [key]: !c[key] }));

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      const result = await request("/patch/main/save", {
        method: "POST",
        body: JSON.stringify({ game_path: gamePath, config }),
      });
      setMsg(result.message || "已保存");
    } catch (err) {
      setMsg(err.message);
    } finally {
      setSaving(false);
    }
  };

  const ticketItems = [
    { key: "newAppTicket", label: "使用新 App Ticket 格式", desc: "某些游戏需要新格式才能正常工作" },
    { key: "gcToken", label: "生成 GC Token", desc: "为使用 Steam 协调器的游戏生成 GC Token" },
  ];

  const toggleItems = [
    { key: "disableNetworking", label: "禁用网络", desc: "完全禁用模拟器的网络功能" },
    { key: "offlineMode", label: "离线模式", desc: "以离线模式运行" },
    { key: "enableLogging", label: "启用日志", desc: "开启模拟器调试日志" },
    { key: "disableAccountLimit", label: "禁用账户限制", desc: "跳过账户限制检查" },
    { key: "forceOffline", label: "强制离线", desc: "强制模拟器处于离线状态" },
    { key: "disableCloud", label: "禁用云存档", desc: "禁用 Steam 云存档同步" },
  ];

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Settings className="h-4 w-4" /><span>主配置</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>

      {/* 认证票据设置 */}
      <p className="text-xs font-semibold text-[var(--dim)] uppercase tracking-wide mb-2">认证票据</p>
      <div className="space-y-2 mb-4">
        {ticketItems.map((item) => (
          <label key={item.key} className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={!!config[item.key]} onChange={() => toggle(item.key)} className="mt-0.5" />
            <div>
              <span className="text-sm font-medium text-[var(--text)]">{item.label}</span>
              <p className="text-xs text-[var(--dim)]">{item.desc}</p>
            </div>
          </label>
        ))}
        <div>
          <label className="block text-xs font-medium text-[var(--text)] mb-1">加密 App Ticket（Base64，可选）</label>
          <input
            value={config.encryptedAppTicket || ""}
            onChange={(e) => setConfig((c) => ({ ...c, encryptedAppTicket: e.target.value }))}
            placeholder="某些游戏需要特定票据格式"
            className="codex-input w-full text-xs"
          />
        </div>
      </div>

      <p className="text-xs font-semibold text-[var(--dim)] uppercase tracking-wide mb-2">联机 / 日志 / 高级</p>
      <div className="space-y-3 mb-4">
        {toggleItems.map((item) => (
          <label key={item.key} className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={!!config[item.key]} onChange={() => toggle(item.key)} className="mt-0.5" />
            <div>
              <span className="text-sm font-medium text-[var(--text)]">{item.label}</span>
              <p className="text-xs text-[var(--dim)]">{item.desc}</p>
            </div>
          </label>
        ))}
      </div>

      {config.enableLogging && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-[var(--text)] mb-1">日志级别</label>
          <select value={config.logLevel} onChange={(e) => setConfig((c) => ({ ...c, logLevel: e.target.value }))} className="codex-select w-48">
            <option value="0">Error</option>
            <option value="1">Warning</option>
            <option value="2">Info</option>
            <option value="3">Debug</option>
          </select>
        </div>
      )}

      {msg && <div className="text-sm text-[var(--muted)] mb-3">{msg}</div>}
      <button onClick={save} disabled={saving} className="codex-btn-primary">
        {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存配置
      </button>
    </div>
  );
}

// ── 子面板：成就配置 ──────────────────────────────────────
function AchievementsPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ achievements: [] });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/achievements/load", { method: "POST", body: JSON.stringify({ game_path: gamePath }) })
      .then((d) => setConfig(d)).catch(() => {});
  }, [gamePath]);

  const add = () => setConfig((c) => ({ ...c, achievements: [...c.achievements, { name: "", displayName: "", description: "", hidden: false, icon: "", iconGray: "" }] }));
  const remove = (i) => setConfig((c) => ({ ...c, achievements: c.achievements.filter((_, idx) => idx !== i) }));
  const update = (i, field, val) => setConfig((c) => {
    const a = [...c.achievements]; a[i] = { ...a[i], [field]: val }; return { ...c, achievements: a };
  });

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await request("/patch/achievements/save", { method: "POST", body: JSON.stringify({ game_path: gamePath, config }) });
      setMsg(r.message || "已保存");
    } catch (e) { setMsg(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Trophy className="h-4 w-4" /><span>成就配置</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>
      <p className="text-xs text-[var(--dim)] mb-3">定义游戏成就列表，写入 <code>steam_settings/achievements.json</code></p>
      <div className="space-y-2 mb-3 max-h-72 overflow-y-auto pr-1">
        {config.achievements.map((a, i) => (
          <div key={i} className="rounded-lg border border-[var(--line)] p-3 space-y-2">
            <div className="flex gap-2">
              <input value={a.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="成就 ID (英文)" className="codex-input flex-1 text-xs" />
              <input value={a.displayName} onChange={(e) => update(i, "displayName", e.target.value)} placeholder="显示名称" className="codex-input flex-1 text-xs" />
              <button onClick={() => remove(i)} className="icon-danger-btn shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
            <div className="flex gap-2 items-center">
              <input value={a.description} onChange={(e) => update(i, "description", e.target.value)} placeholder="描述" className="codex-input flex-1 text-xs" />
              <label className="flex items-center gap-1.5 text-xs text-[var(--text)] shrink-0 cursor-pointer">
                <input type="checkbox" checked={a.hidden} onChange={(e) => update(i, "hidden", e.target.checked)} />隐藏
              </label>
            </div>
          </div>
        ))}
        {config.achievements.length === 0 && <p className="text-xs text-[var(--muted)] py-2">暂无成就，点击下方添加</p>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button onClick={add} className="codex-btn-secondary text-xs"><Plus className="h-3.5 w-3.5 mr-1" />添加成就</button>
        <button onClick={save} disabled={saving} className="codex-btn-primary">
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存
        </button>
        {msg && <span className="text-xs text-[var(--muted)]">{msg}</span>}
      </div>
    </div>
  );
}

// ── 子面板：游戏统计 ──────────────────────────────────────
function StatsPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ stats: [] });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/stats/load", { method: "POST", body: JSON.stringify({ game_path: gamePath }) })
      .then((d) => setConfig(d)).catch(() => {});
  }, [gamePath]);

  const add = () => setConfig((c) => ({ ...c, stats: [...c.stats, { name: "", type: "int", default: 0, globalavgrate: false, displayName: "" }] }));
  const remove = (i) => setConfig((c) => ({ ...c, stats: c.stats.filter((_, idx) => idx !== i) }));
  const update = (i, field, val) => setConfig((c) => {
    const s = [...c.stats]; s[i] = { ...s[i], [field]: val }; return { ...c, stats: s };
  });

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await request("/patch/stats/save", { method: "POST", body: JSON.stringify({ game_path: gamePath, config }) });
      setMsg(r.message || "已保存");
    } catch (e) { setMsg(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><BarChart2 className="h-4 w-4" /><span>游戏统计</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>
      <p className="text-xs text-[var(--dim)] mb-3">定义游戏统计项，写入 <code>steam_settings/stats.json</code></p>
      <div className="space-y-2 mb-3 max-h-60 overflow-y-auto pr-1">
        {config.stats.map((s, i) => (
          <div key={i} className="flex gap-2 items-center rounded-lg border border-[var(--line)] px-3 py-2">
            <input value={s.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="统计 ID" className="codex-input flex-1 text-xs" />
            <select value={s.type} onChange={(e) => update(i, "type", e.target.value)} className="codex-select text-xs w-24 shrink-0">
              <option value="int">整数</option>
              <option value="float">浮点</option>
              <option value="avgrate">平均值</option>
            </select>
            <input type="number" value={s.default} onChange={(e) => update(i, "default", Number(e.target.value))} placeholder="默认值" className="codex-input w-20 text-xs shrink-0" />
            <button onClick={() => remove(i)} className="icon-danger-btn shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
        {config.stats.length === 0 && <p className="text-xs text-[var(--muted)] py-2">暂无统计项</p>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button onClick={add} className="codex-btn-secondary text-xs"><Plus className="h-3.5 w-3.5 mr-1" />添加统计</button>
        <button onClick={save} disabled={saving} className="codex-btn-primary">
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存
        </button>
        {msg && <span className="text-xs text-[var(--muted)]">{msg}</span>}
      </div>
    </div>
  );
}

// ── 子面板：物品库存 ──────────────────────────────────────
function ItemsPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ items: [] });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/items/load", { method: "POST", body: JSON.stringify({ game_path: gamePath }) })
      .then((d) => setConfig(d)).catch(() => {});
  }, [gamePath]);

  const add = () => setConfig((c) => ({ ...c, items: [...c.items, { itemId: 1, name: "", quantity: 1, type: "item", attributes: "" }] }));
  const remove = (i) => setConfig((c) => ({ ...c, items: c.items.filter((_, idx) => idx !== i) }));
  const update = (i, field, val) => setConfig((c) => {
    const items = [...c.items]; items[i] = { ...items[i], [field]: val }; return { ...c, items };
  });

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await request("/patch/items/save", { method: "POST", body: JSON.stringify({ game_path: gamePath, config }) });
      setMsg(r.message || "已保存");
    } catch (e) { setMsg(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Package className="h-4 w-4" /><span>物品与库存</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>
      <p className="text-xs text-[var(--dim)] mb-3">定义游戏物品/库存，写入 <code>steam_settings/items.json</code></p>
      <div className="space-y-2 mb-3 max-h-60 overflow-y-auto pr-1">
        {config.items.map((item, i) => (
          <div key={i} className="flex gap-2 items-center rounded-lg border border-[var(--line)] px-3 py-2">
            <input type="number" value={item.itemId} onChange={(e) => update(i, "itemId", Number(e.target.value))} placeholder="Item ID" className="codex-input w-20 text-xs shrink-0" />
            <input value={item.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="物品名称" className="codex-input flex-1 text-xs" />
            <input type="number" value={item.quantity} onChange={(e) => update(i, "quantity", Number(e.target.value))} placeholder="数量" className="codex-input w-16 text-xs shrink-0" />
            <button onClick={() => remove(i)} className="icon-danger-btn shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
        {config.items.length === 0 && <p className="text-xs text-[var(--muted)] py-2">暂无物品定义</p>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button onClick={add} className="codex-btn-secondary text-xs"><Plus className="h-3.5 w-3.5 mr-1" />添加物品</button>
        <button onClick={save} disabled={saving} className="codex-btn-primary">
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存
        </button>
        {msg && <span className="text-xs text-[var(--muted)]">{msg}</span>}
      </div>
    </div>
  );
}

// ── 子面板：排行榜 ────────────────────────────────────────
function LeaderboardsPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ leaderboards: [] });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/leaderboards/load", { method: "POST", body: JSON.stringify({ game_path: gamePath }) })
      .then((d) => setConfig(d)).catch(() => {});
  }, [gamePath]);

  const add = () => setConfig((c) => ({ ...c, leaderboards: [...c.leaderboards, { name: "", sortMethod: 2, displayType: 1 }] }));
  const remove = (i) => setConfig((c) => ({ ...c, leaderboards: c.leaderboards.filter((_, idx) => idx !== i) }));
  const update = (i, field, val) => setConfig((c) => {
    const lbs = [...c.leaderboards]; lbs[i] = { ...lbs[i], [field]: val }; return { ...c, leaderboards: lbs };
  });

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await request("/patch/leaderboards/save", { method: "POST", body: JSON.stringify({ game_path: gamePath, config }) });
      setMsg(r.message || "已保存");
    } catch (e) { setMsg(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><BarChart className="h-4 w-4" /><span>排行榜</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>
      <p className="text-xs text-[var(--dim)] mb-3">定义排行榜，写入 <code>steam_settings/leaderboards.json</code></p>
      <div className="space-y-2 mb-3 max-h-60 overflow-y-auto pr-1">
        {config.leaderboards.map((lb, i) => (
          <div key={i} className="flex gap-2 items-center rounded-lg border border-[var(--line)] px-3 py-2">
            <input value={lb.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="排行榜名称" className="codex-input flex-1 text-xs" />
            <select value={lb.sortMethod} onChange={(e) => update(i, "sortMethod", Number(e.target.value))} className="codex-select text-xs w-28 shrink-0">
              <option value={2}>降序</option>
              <option value={1}>升序</option>
              <option value={0}>无</option>
            </select>
            <select value={lb.displayType} onChange={(e) => update(i, "displayType", Number(e.target.value))} className="codex-select text-xs w-24 shrink-0">
              <option value={1}>数字</option>
              <option value={2}>时间(秒)</option>
              <option value={3}>时间(毫秒)</option>
              <option value={0}>无</option>
            </select>
            <button onClick={() => remove(i)} className="icon-danger-btn shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        ))}
        {config.leaderboards.length === 0 && <p className="text-xs text-[var(--muted)] py-2">暂无排行榜（默认模拟器自动处理）</p>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <button onClick={add} className="codex-btn-secondary text-xs"><Plus className="h-3.5 w-3.5 mr-1" />添加排行榜</button>
        <button onClick={save} disabled={saving} className="codex-btn-primary">
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存
        </button>
        {msg && <span className="text-xs text-[var(--muted)]">{msg}</span>}
      </div>
    </div>
  );
}

// ── 子面板：Overlay ───────────────────────────────────────
function OverlayPanel({ gamePath, onClose }) {
  const [config, setConfig] = useState({ enabled: false, showFPS: false, showClock: false, achievementSound: false, achievementSoundPath: "" });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    request("/patch/overlay/load", { method: "POST", body: JSON.stringify({ game_path: gamePath }) })
      .then((d) => setConfig((c) => ({ ...c, ...d }))).catch(() => {});
  }, [gamePath]);

  const toggle = (key) => setConfig((c) => ({ ...c, [key]: !c[key] }));

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      const r = await request("/patch/overlay/save", { method: "POST", body: JSON.stringify({ game_path: gamePath, config }) });
      setMsg(r.message || "已保存");
    } catch (e) { setMsg(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 sm:p-5 mt-3">
      <div className="flex items-center justify-between mb-4">
        <div className="section-title"><Monitor className="h-4 w-4" /><span>游戏内 Overlay</span></div>
        <button onClick={onClose} className="codex-btn-secondary p-1"><X className="h-4 w-4" /></button>
      </div>
      <div className="rounded-lg border border-[var(--warning)]/40 bg-[var(--warning)]/5 px-3 py-2 text-xs text-[var(--warning)] mb-4 flex items-center gap-2">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        Overlay 为实验性功能，需要实验版 DLL，按 Shift+Tab 打开
      </div>
      <div className="space-y-3 mb-4">
        {[
          { key: "enabled", label: "启用游戏内 Overlay", desc: "开启实验性 Steam Overlay 模拟" },
          { key: "showFPS", label: "显示 FPS 计数器", desc: "在 Overlay 中显示帧率" },
          { key: "showClock", label: "显示时钟", desc: "在 Overlay 中显示时间" },
        ].map((item) => (
          <label key={item.key} className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={config[item.key]} onChange={() => toggle(item.key)} className="mt-0.5" />
            <div>
              <span className="text-sm font-medium text-[var(--text)]">{item.label}</span>
              <p className="text-xs text-[var(--dim)]">{item.desc}</p>
            </div>
          </label>
        ))}
      </div>
      {msg && <div className="text-sm text-[var(--muted)] mb-3">{msg}</div>}
      <button onClick={save} disabled={saving} className="codex-btn-primary">
        {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}保存配置
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
// 主页面组件
// ══════════════════════════════════════════════════════════

export default function SteamPatchPage() {
  const initialPatchState = (() => {
    try {
      return JSON.parse(localStorage.getItem(PATCH_STATE_KEY) || "{}");
    } catch {
      return {};
    }
  })();

  // ── 基础配置状态 ─────────────────────────────────────────
  const [emulatorMode, setEmulatorMode] = useState(() => Number(initialPatchState.emulatorMode ?? 0));
  const [useExperimental, setUseExperimental] = useState(() => Boolean(initialPatchState.useExperimental));
  const [gamePath, setGamePath] = useState(() => initialPatchState.gamePath || "");
  const [gameExePath, setGameExePath] = useState("");
  const [steamAppId, setSteamAppId] = useState(() => initialPatchState.steamAppId || "");
  const [basicApplied, setBasicApplied] = useState(() => Boolean(initialPatchState.basicApplied));
  const [applyMsg, setApplyMsg] = useState("");
  const [applyError, setApplyError] = useState("");
  const [checking, setChecking] = useState(false);
  const [feasibility, setFeasibility] = useState(null);
  const [unpacking, setUnpacking] = useState(false);
  const [unpackMsg, setUnpackMsg] = useState("");

  // ── 高级配置面板 ─────────────────────────────────────────
  const [openPanel, setOpenPanel] = useState(null);

  // ── D加密虚拟机状态 ─────────────────────────────────────
  const [denuvoGamePath, setDenuvoGamePath] = useState("");
  const [denuvoArchivePath, setDenuvoArchivePath] = useState("");
  const [denuvoChecking, setDenuvoChecking] = useState(false);
  const [denuvoFeasibility, setDenuvoFeasibility] = useState(null);
  const [denuvoApplying, setDenuvoApplying] = useState(false);
  const [denuvoMsg, setDenuvoMsg] = useState("");
  const [denuvoRestoring, setDenuvoRestoring] = useState(false);

  // ── 选项卡 ──────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState("patch");

  // ── 方法 ────────────────────────────────────────────────

  useEffect(() => {
    localStorage.setItem(PATCH_STATE_KEY, JSON.stringify({
      gamePath,
      steamAppId,
      emulatorMode,
      useExperimental,
      basicApplied,
    }));
  }, [gamePath, steamAppId, emulatorMode, useExperimental, basicApplied]);

  const selectFolder = async (title) => {
    if (window.nativeApp?.dialog?.selectFolder) {
      return await window.nativeApp.dialog.selectFolder(title);
    }
    return prompt(title || "请输入文件夹路径：");
  };

  const selectFile = async (title, filters) => {
    if (window.nativeApp?.dialog?.selectFile) {
      return await window.nativeApp.dialog.selectFile(title, filters);
    }
    return prompt(title || "请输入文件路径：");
  };

  const checkFeasibility = async () => {
    if (!gamePath) return;
    setChecking(true);
    setFeasibility(null);
    try {
      const result = await request("/patch/check-feasibility", {
        method: "POST",
        body: JSON.stringify({ game_path: gamePath, emulator_mode: emulatorMode }),
      });
      setFeasibility(result);
    } catch (err) {
      setFeasibility({ feasible: false, details: [err.message], found_dlls: [] });
    } finally {
      setChecking(false);
    }
  };

  const refreshBasicStatus = useCallback(async (path = gamePath, mode = emulatorMode) => {
    if (!path) return null;
    try {
      const result = await request("/patch/basic-status", {
        method: "POST",
        body: JSON.stringify({ game_path: path, emulator_mode: mode }),
      });
      if (result.applied) {
        setBasicApplied(true);
        setFeasibility({
          feasible: true,
          details: result.details || ["已检测到现有基础配置"],
          found_dlls: result.found_dlls || [],
        });
        if (result.appid) {
          setSteamAppId((current) => current.trim() ? current : result.appid);
        }
      } else {
        setBasicApplied(false);
      }
      return result;
    } catch {
      return null;
    }
  }, [gamePath, emulatorMode]);

  useEffect(() => {
    if (!gamePath) return;
    const timer = setTimeout(() => {
      refreshBasicStatus(gamePath, emulatorMode);
    }, 300);
    return () => clearTimeout(timer);
  }, [gamePath, emulatorMode, refreshBasicStatus]);

  // 自动检测 AppID 的公共方法
  const autoDetectAppId = async (path) => {
    if (!path || steamAppId.trim()) return;
    try {
      const result = await request("/patch/detect-appid", {
        method: "POST",
        body: JSON.stringify({ game_path: path }),
      });
      if (result.appid) {
        setSteamAppId(result.appid);
      }
    } catch {
      // 自动检测失败，忽略
    }
  };

  const onSelectGameFolder = async () => {
    const folder = await selectFolder("选择游戏文件夹");
    if (folder) {
      setGamePath(folder);
      setBasicApplied(false);
      setFeasibility(null);
      refreshBasicStatus(folder, emulatorMode);
      autoDetectAppId(folder);
    }
  };

  const onSelectGameExe = async () => {
    const file = await selectFile("选择游戏主程序", [
      { name: "可执行文件", extensions: ["exe"] },
    ]);
    if (file) setGameExePath(file);
  };

  const onUnpack = async () => {
    if (!gameExePath) return;
    setUnpacking(true);
    setUnpackMsg("");
    try {
      const result = await request("/patch/unpack", {
        method: "POST",
        body: JSON.stringify({ exe_path: gameExePath }),
      });
      setUnpackMsg(result.message);
    } catch (err) {
      setUnpackMsg(err.message);
    } finally {
      setUnpacking(false);
    }
  };

  const onApplyBasic = async () => {
    if (!gamePath || !steamAppId.trim()) return;
    setApplyMsg("");
    setApplyError("");
    try {
      const result = await request("/patch/apply-basic", {
        method: "POST",
        body: JSON.stringify({
          game_path: gamePath,
          steam_app_id: steamAppId.trim(),
          use_experimental: useExperimental,
          emulator_mode: emulatorMode,
        }),
      });
      if (result.success) {
        setBasicApplied(true);
        setApplyMsg(result.message);
        refreshBasicStatus(gamePath, emulatorMode);
      } else {
        setApplyError(result.message);
      }
    } catch (err) {
      setApplyError(err.message);
    }
  };

  // ── D 加密虚拟机方法 ────────────────────────────────────

  const onSelectDenuvoFolder = async () => {
    const folder = await selectFolder("选择游戏文件夹");
    if (folder) {
      setDenuvoGamePath(folder);
      setDenuvoFeasibility(null);
    }
  };

  const onSelectDenuvoArchive = async () => {
    const file = await selectFile("选择补丁文件", [
      { name: "归档文件", extensions: ["7z", "zip", "rar"] },
      { name: "所有文件", extensions: ["*"] },
    ]);
    if (file) setDenuvoArchivePath(file);
  };

  const checkDenuvoFeasibility = async () => {
    if (!denuvoGamePath) return;
    setDenuvoChecking(true);
    setDenuvoFeasibility(null);
    try {
      const result = await request("/patch/denuvo/check", {
        method: "POST",
        body: JSON.stringify({ game_path: denuvoGamePath }),
      });
      setDenuvoFeasibility(result);
    } catch (err) {
      setDenuvoFeasibility({ feasible: false, details: [err.message] });
    } finally {
      setDenuvoChecking(false);
    }
  };

  const onApplyDenuvo = async () => {
    if (!denuvoGamePath || !denuvoArchivePath) return;
    setDenuvoApplying(true);
    setDenuvoMsg("");
    try {
      const result = await request("/patch/denuvo/apply", {
        method: "POST",
        body: JSON.stringify({ game_path: denuvoGamePath, archive_path: denuvoArchivePath }),
      });
      setDenuvoMsg(result.message);
    } catch (err) {
      setDenuvoMsg(err.message);
    } finally {
      setDenuvoApplying(false);
    }
  };

  const onRestoreBackup = async () => {
    if (!denuvoGamePath) return;
    if (!window.confirm("确定要从备份恢复游戏文件吗？")) return;
    setDenuvoRestoring(true);
    setDenuvoMsg("");
    try {
      const result = await request("/patch/restore-backup", {
        method: "POST",
        body: JSON.stringify({ game_path: denuvoGamePath }),
      });
      setDenuvoMsg(result.message);
    } catch (err) {
      setDenuvoMsg(err.message);
    } finally {
      setDenuvoRestoring(false);
    }
  };

  // ── 高级配置卡片 ────────────────────────────────────────

  const featureCards = [
    { key: "lan", icon: Network, title: "局域网联机", desc: "自定义广播 IP，局域网多人游戏" },
    { key: "dlc", icon: Package, title: "DLC 管理", desc: "配置已安装 DLC 和自动解锁" },
    { key: "user", icon: User, title: "用户配置", desc: "用户名、语言、在线状态" },
    { key: "main", icon: Settings, title: "主配置", desc: "网络、日志、高级选项" },
    { key: "achievements", icon: Trophy, title: "成就系统", desc: "定义游戏成就列表" },
    { key: "stats", icon: BarChart2, title: "游戏统计", desc: "统计项定义与默认值" },
    { key: "items", icon: Package, title: "物品库存", desc: "Steam 物品/库存定义" },
    { key: "leaderboards", icon: BarChart, title: "排行榜", desc: "排行榜名称与排序方式" },
    { key: "overlay", icon: Monitor, title: "Overlay", desc: "游戏内实验性覆盖层" },
  ];

  // ── 渲染 ────────────────────────────────────────────────

  return (
    <>
      {/* 选项卡 */}
      <div className="flex gap-2 mb-4">
        {[
          { key: "patch", label: "免 Steam 补丁", icon: Shield },
          { key: "lan", label: "联机配置", icon: Network },
          { key: "denuvo", label: "D 加密虚拟机", icon: Zap },
        ].map((tab) => {
          const TabIcon = tab.icon;
          return (
            <button
              key={tab.key}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                activeTab === tab.key
                  ? "bg-[var(--panel-strong)] text-[var(--text)] shadow-sm"
                  : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--panel-soft)]"
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              <TabIcon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ─── 免 Steam 补丁注入 ──────────────────────────── */}
      {activeTab === "patch" && (
        <div className="space-y-4">
          {/* 资源状态 */}
          <div className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="section-title mb-3">
              <Download className="h-4 w-4" />
              <span>模拟器资源</span>
            </div>
            <ResourcePanel />
          </div>

          <div className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="section-title mb-4">
              <Shield className="h-4 w-4" />
              <span>基础配置</span>
            </div>

            {/* 模拟器模式 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-2">模拟器模式</label>
              <div className="flex gap-3">
                {[
                  { value: 0, label: "标准模式", desc: "替换 steam_api.dll，适用于 90% 游戏" },
                  { value: 1, label: "高级模式", desc: "替换 steamclient.dll，兼容特殊游戏" },
                ].map((mode) => (
                  <button
                    key={mode.value}
                    className={`flex-1 rounded-xl border p-3 text-left transition-all ${
                      emulatorMode === mode.value
                        ? "border-[var(--accent)] bg-[var(--panel-strong)]"
                        : "border-[var(--line)] hover:border-[var(--line-strong)]"
                    }`}
                    onClick={() => setEmulatorMode(mode.value)}
                  >
                    <span className="text-sm font-semibold text-[var(--text)]">{mode.label}</span>
                    <p className="mt-1 text-xs text-[var(--dim)]">{mode.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* DLL 版本 */}
            {emulatorMode === 0 && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-[var(--text)] mb-2">DLL 版本</label>
                <div className="flex gap-3">
                  {[
                    { value: false, label: "稳定版", desc: "高兼容性，无 Overlay" },
                    { value: true, label: "功能版", desc: "支持 Overlay、联机增强（实验性）" },
                  ].map((ver) => (
                    <button
                      key={String(ver.value)}
                      className={`flex-1 rounded-xl border p-3 text-left transition-all ${
                        useExperimental === ver.value
                          ? "border-[var(--accent)] bg-[var(--panel-strong)]"
                          : "border-[var(--line)] hover:border-[var(--line-strong)]"
                      }`}
                      onClick={() => setUseExperimental(ver.value)}
                    >
                      <span className="text-sm font-semibold text-[var(--text)]">{ver.label}</span>
                      <p className="mt-1 text-xs text-[var(--dim)]">{ver.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 游戏文件夹 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-1">
                游戏文件夹 <span className="text-[var(--danger)]">*</span>
              </label>
              <div className="flex gap-2">
                <input value={gamePath} onChange={(e) => setGamePath(e.target.value)} onBlur={(e) => autoDetectAppId(e.target.value)} placeholder={emulatorMode === 0 ? "包含 steam_api.dll 的文件夹" : "包含 steamclient.dll 的文件夹"} className="codex-input flex-1" />
                <button onClick={onSelectGameFolder} className="codex-btn-secondary shrink-0">
                  <FolderOpen className="mr-1.5 h-4 w-4" />浏览
                </button>
                <button onClick={checkFeasibility} disabled={!gamePath || checking} className="codex-btn-secondary shrink-0">
                  {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                </button>
              </div>
              {feasibility && (
                <div className={`mt-2 rounded-lg border px-3 py-2 text-xs ${feasibility.feasible ? "border-[var(--success)]/30 bg-[var(--success)]/5 text-[var(--success)]" : "border-[var(--danger)]/30 bg-[var(--danger)]/5 text-[var(--danger)]"}`}>
                  {feasibility.details.map((d, i) => <div key={i}>{d}</div>)}
                </div>
              )}
            </div>

            {/* 游戏主程序 + 脱壳 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-1">游戏主程序（可选，用于脱壳）</label>
              <div className="flex gap-2">
                <input value={gameExePath} onChange={(e) => setGameExePath(e.target.value)} placeholder=".exe 文件路径" className="codex-input flex-1" />
                <button onClick={onSelectGameExe} className="codex-btn-secondary shrink-0">
                  <FolderOpen className="mr-1.5 h-4 w-4" />浏览
                </button>
                <button onClick={onUnpack} disabled={!gameExePath || unpacking} className="codex-btn-secondary shrink-0">
                  {unpacking ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Zap className="mr-1.5 h-4 w-4" />}脱壳
                </button>
              </div>
              {unpackMsg && <div className="mt-2 text-xs text-[var(--muted)]">{unpackMsg}</div>}
            </div>

            {/* AppID */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-1">
                Steam AppID <span className="text-[var(--danger)]">*</span>
              </label>
              <div className="flex gap-2 items-center">
                <input value={steamAppId} onChange={(e) => setSteamAppId(e.target.value)} placeholder="如 1245620" className="codex-input w-48" />
                {gamePath && !steamAppId.trim() && (
                  <button onClick={() => autoDetectAppId(gamePath)} className="codex-btn-secondary text-xs shrink-0" title="从游戏目录自动检测 AppID">
                    <Search className="mr-1 h-3 w-3" />自动检测
                  </button>
                )}
              </div>
              <p className="mt-1 text-xs text-[var(--dim)]">选择文件夹后自动检测，或从 Steam 商店页 URL 手动获取</p>
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-2">
              <button onClick={onApplyBasic} disabled={!gamePath || !steamAppId.trim()} className="codex-btn-primary">
                <Save className="mr-1.5 h-4 w-4" />应用基础配置
              </button>
              <button onClick={() => {
                localStorage.removeItem(PATCH_STATE_KEY);
                setGamePath("");
                setGameExePath("");
                setSteamAppId("");
                setBasicApplied(false);
                setFeasibility(null);
                setApplyMsg("");
                setApplyError("");
                setOpenPanel(null);
              }} className="codex-btn-secondary">
                重置
              </button>
            </div>

            {applyMsg && (
              <div className="mt-3 rounded-lg border border-[var(--success)]/30 bg-[var(--success)]/5 px-3 py-2 text-sm text-[var(--success)]">
                <CheckCircle className="inline h-4 w-4 mr-1.5" />{applyMsg}
              </div>
            )}
            {applyError && (
              <div className="error-alert mt-3">
                <AlertCircle className="inline h-4 w-4 mr-1.5" />{applyError}
              </div>
            )}
          </div>

          {/* 高级功能（基础配置应用后显示） */}
          {basicApplied && (
            <div className="glass-panel rounded-2xl p-4 sm:p-5">
              <div className="section-title mb-3">
                <Zap className="h-4 w-4" />
                <span>高级功能配置</span>
              </div>
              <p className="text-xs text-[var(--dim)] mb-4">基础配置已应用，点击下方卡片配置更多功能</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {featureCards.map((card) => {
                  const CardIcon = card.icon;
                  return (
                    <button
                      key={card.key}
                      className={`rounded-xl border p-4 text-left transition-all hover:shadow-sm ${
                        openPanel === card.key
                          ? "border-[var(--accent)] bg-[var(--panel-strong)]"
                          : "border-[var(--line)] hover:border-[var(--line-strong)]"
                      }`}
                      onClick={() => setOpenPanel(openPanel === card.key ? null : card.key)}
                    >
                      <CardIcon className="h-5 w-5 text-[var(--accent-2)] mb-2" />
                      <span className="block text-sm font-semibold text-[var(--text)]">{card.title}</span>
                      <span className="block mt-1 text-xs text-[var(--dim)]">{card.desc}</span>
                    </button>
                  );
                })}
              </div>

              {openPanel === "lan" && <LanConfigPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "dlc" && <DlcConfigPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "user" && <UserConfigPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "main" && <MainConfigPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "achievements" && <AchievementsPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "stats" && <StatsPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "items" && <ItemsPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "leaderboards" && <LeaderboardsPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
              {openPanel === "overlay" && <OverlayPanel gamePath={gamePath} onClose={() => setOpenPanel(null)} />}
            </div>
          )}
        </div>
      )}

      {/* ─── 联机配置（独立入口） ──────────────────────── */}
      {activeTab === "lan" && (
        <div className="space-y-4">
          <div className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="section-title mb-4">
              <Network className="h-4 w-4" />
              <span>联机功能</span>
            </div>

            {/* 快速配置：如果还没有选择游戏目录，允许直接输入 */}
            {!gamePath && (
              <div className="mb-4">
                <div className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/5 px-4 py-3 mb-4">
                  <p className="text-sm font-medium text-[var(--warning)] mb-1">快速联机配置</p>
                  <p className="text-xs text-[var(--dim)]">
                    选择已应用过免 Steam 补丁的游戏目录（包含 steam_settings 文件夹），即可直接配置联机参数。
                    如果还未应用补丁，请先前往「免 Steam 补丁」选项卡完成基础配置。
                  </p>
                </div>
                <label className="block text-sm font-medium text-[var(--text)] mb-1">
                  游戏文件夹 <span className="text-[var(--danger)]">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    value={gamePath}
                    onChange={(e) => setGamePath(e.target.value)}
                    placeholder="包含 steam_settings 的游戏文件夹"
                    className="codex-input flex-1"
                  />
                  <button onClick={onSelectGameFolder} className="codex-btn-secondary shrink-0">
                    <FolderOpen className="mr-1.5 h-4 w-4" />浏览
                  </button>
                </div>
              </div>
            )}

            {/* 联机原理说明 */}
            <div className="rounded-xl border border-[var(--line)] p-4 mb-4">
              <h4 className="text-sm font-semibold text-[var(--text)] mb-2">联机原理说明</h4>
              <ul className="text-xs text-[var(--dim)] space-y-1.5 list-disc list-inside">
                <li>模拟器通过自定义广播 IP 发送局域网组播包，发现同一模拟器环境下的其他玩家</li>
                <li>支持添加多个广播 IP 或域名，适配不同的网络环境（如 VPN、ZeroTier、Radmin 等）</li>
                <li>联机双方需要使用相同版本的 GBE Fork 模拟器和相同的 AppID</li>
                <li>可配置自动接受邀请和白名单，方便快速联机</li>
                <li>监听端口默认为 47584，可自定义以配合端口转发或防火墙规则</li>
                <li>如果使用 ZeroTier/Radmin VPN 等虚拟局域网工具，需要添加对方的虚拟 IP</li>
              </ul>
            </div>

            {/* 快速联机步骤 */}
            <div className="rounded-xl border border-[var(--line)] p-4 mb-4">
              <h4 className="text-sm font-semibold text-[var(--text)] mb-2">联机步骤</h4>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                {[
                  { step: "1", title: "安装虚拟局域网", desc: "安装 ZeroTier / Radmin VPN 并加入同一网络" },
                  { step: "2", title: "应用免Steam补丁", desc: "在「免 Steam 补丁」选项卡中完成基础配置" },
                  { step: "3", title: "添加广播 IP", desc: "在下方添加对方玩家的虚拟局域网 IP 地址" },
                  { step: "4", title: "启动游戏", desc: "双方启动游戏即可在局域网中互相发现" },
                ].map((item) => (
                  <div key={item.step} className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] p-3 text-center">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[var(--panel-strong)] text-sm font-bold text-[var(--text)] mb-2">{item.step}</span>
                    <p className="text-xs font-semibold text-[var(--text)] mb-1">{item.title}</p>
                    <p className="text-[10px] text-[var(--dim)]">{item.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            {gamePath ? (
              <LanConfigPanel gamePath={gamePath} onClose={() => {}} />
            ) : (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3 text-sm text-[var(--muted)]">
                请先选择游戏文件夹以配置联机参数
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── D 加密虚拟机 ──────────────────────────────── */}
      {activeTab === "denuvo" && (
        <div className="space-y-4">
          {/* 预置游戏 - D加密补丁下载链接 */}
          <div className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="section-title mb-3">
              <Zap className="h-4 w-4" />
              <span>D 加密补丁预置游戏</span>
            </div>
            <p className="text-xs text-[var(--dim)] mb-3">
              以下游戏有已知的 Denuvo VM 破解补丁，点击「下载」在百度网盘获取补丁文件（.7z/.zip），然后在下方「应用补丁」区域选择文件使用。
            </p>
            <div className="space-y-2">
              {DENUVO_PRESETS.map((game) => (
                <div
                  key={game.appId}
                  className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <span className="block text-sm font-medium text-[var(--text)] truncate">{game.name}</span>
                    <span className="block text-xs text-[var(--dim)] truncate">
                      {game.eng} · AppID: {game.appId}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => setDenuvoGamePath("")}
                      className="codex-btn-secondary text-xs px-2 py-1"
                      title={`使用 AppID ${game.appId}`}
                      onMouseDown={() => {
                        // 预填 AppID 到 patch 标签的 steamAppId
                      }}
                    >
                      AppID: {game.appId}
                    </button>
                    <a
                      href={game.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="codex-btn-primary text-xs px-3 py-1.5 inline-flex items-center gap-1"
                    >
                      <Download className="h-3 w-3" />
                      下载补丁
                      <span className="opacity-60 text-[10px] ml-0.5">提取码: {game.code}</span>
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="section-title mb-4">
              <Zap className="h-4 w-4" />
              <span>应用 D 加密虚拟机补丁</span>
            </div>
            <p className="text-sm text-[var(--muted)] mb-4">
              从上方下载补丁文件后，选择游戏目录和补丁文件，点击「应用补丁」一键覆盖。支持 .7z、.zip、.rar 格式。
            </p>

            {/* 游戏文件夹 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-1">
                游戏文件夹 <span className="text-[var(--danger)]">*</span>
              </label>
              <div className="flex gap-2">
                <input value={denuvoGamePath} onChange={(e) => setDenuvoGamePath(e.target.value)} placeholder="游戏安装目录" className="codex-input flex-1" />
                <button onClick={onSelectDenuvoFolder} className="codex-btn-secondary shrink-0">
                  <FolderOpen className="mr-1.5 h-4 w-4" />浏览
                </button>
                <button onClick={checkDenuvoFeasibility} disabled={!denuvoGamePath || denuvoChecking} className="codex-btn-secondary shrink-0">
                  {denuvoChecking ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                </button>
              </div>
              {denuvoFeasibility && (
                <div className={`mt-2 rounded-lg border px-3 py-2 text-xs ${denuvoFeasibility.feasible ? "border-[var(--success)]/30 bg-[var(--success)]/5 text-[var(--success)]" : "border-[var(--danger)]/30 bg-[var(--danger)]/5 text-[var(--danger)]"}`}>
                  {denuvoFeasibility.details.map((d, i) => <div key={i}>{d}</div>)}
                </div>
              )}
            </div>

            {/* 补丁文件 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-[var(--text)] mb-1">
                补丁文件（.7z / .zip / .rar） <span className="text-[var(--danger)]">*</span>
              </label>
              <div className="flex gap-2">
                <input value={denuvoArchivePath} onChange={(e) => setDenuvoArchivePath(e.target.value)} placeholder="选择 .7z 补丁文件" className="codex-input flex-1" />
                <button onClick={onSelectDenuvoArchive} className="codex-btn-secondary shrink-0">
                  <FolderOpen className="mr-1.5 h-4 w-4" />浏览
                </button>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-2">
              <button onClick={onApplyDenuvo} disabled={!denuvoGamePath || !denuvoArchivePath || denuvoApplying} className="codex-btn-primary">
                {denuvoApplying ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Zap className="mr-1.5 h-4 w-4" />}应用补丁
              </button>
              <button onClick={onRestoreBackup} disabled={!denuvoGamePath || denuvoRestoring} className="codex-btn-danger">
                {denuvoRestoring ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <AlertCircle className="mr-1.5 h-4 w-4" />}恢复备份
              </button>
            </div>

            {denuvoMsg && (
              <div className="mt-3 text-sm text-[var(--muted)]">{denuvoMsg}</div>
            )}

            {/* 说明 */}
            <div className="mt-4 rounded-xl border border-[var(--line)] p-4">
              <h4 className="text-sm font-semibold text-[var(--text)] mb-2">使用说明</h4>
              <ul className="text-xs text-[var(--dim)] space-y-1.5 list-disc list-inside">
                <li>支持 .7z、.zip、.rar 格式的补丁文件</li>
                <li>自动检测并去除归档内多余的根目录前缀</li>
                <li>应用前会自动备份将被覆盖的原始文件到 .stm_backup 目录</li>
                <li>自动检测 exe 文件中的 Denuvo 特征段（.arch / .denuvo）</li>
                <li>如果游戏出现问题，可点击「恢复备份」还原原始文件</li>
                <li>D 加密（Denuvo）是一种 DRM 保护，此功能应用虚拟机破解补丁</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
