import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Globe,
  Key,
  Library,
  Loader2,
  Plus,
  Play,
  Power,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  StopCircle,
  Trash2,
  Upload,
  User,
  Users,
  Wifi,
  WifiOff,
  X,
  Zap,
} from "lucide-react";

const API_BASE = window.nativeApp?.backendUrl || "http://127.0.0.1:18765";
const STEAM_DEFAULT_AVATAR_URL = "https://avatars.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_medium.jpg";

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

// ── 内部子页签 ────────────────────────────────────────

function SubTab({ active, icon: Icon, label, onClick }) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
        active
          ? "bg-white/10 border border-white/20 text-[var(--text)]"
          : "border border-transparent text-[var(--muted)] hover:text-[var(--text)] hover:bg-white/5"
      }`}
      onClick={onClick}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

// ═══════════════════════════════════════════════════════
//  网络加速 (Accelerator)
// ═══════════════════════════════════════════════════════

function AcceleratorPanel() {
  const [profiles, setProfiles] = useState({});
  const [status, setStatus] = useState({ active: false, entries: [] });
  const [selected, setSelected] = useState({});
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState({});
  const [msg, setMsg] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        request("/accelerator/profiles"),
        request("/accelerator/status"),
      ]);
      setProfiles(p);
      setStatus(s);
      // 初始化选中状态
      if (Object.keys(selected).length === 0) {
        const init = {};
        for (const [name, rules] of Object.entries(p)) {
          init[name] = true;
        }
        setSelected(init);
      }
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleEnable = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const rules = {};
      for (const [name, domains] of Object.entries(profiles)) {
        if (selected[name]) {
          for (const [domain, ip] of Object.entries(domains)) {
            rules[domain] = ip;
          }
        }
      }
      const res = await request("/accelerator/enable", {
        method: "POST",
        body: JSON.stringify({ rules }),
      });
      if (res.ok) {
        setMsg({ type: "success", text: `加速已启用，共 ${res.count} 条规则` });
      } else {
        setMsg({ type: "error", text: res.error });
      }
      fetchData();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await request("/accelerator/disable", { method: "POST" });
      if (res.ok) {
        setMsg({ type: "success", text: "加速已关闭" });
      } else {
        setMsg({ type: "error", text: res.error });
      }
      fetchData();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (profileName) => {
    setTesting(true);
    try {
      const results = await request(`/accelerator/test-profile/${encodeURIComponent(profileName)}`);
      const map = { ...testResults };
      for (const r of results) {
        map[`${r.host}:${r.ip}`] = r;
      }
      setTestResults(map);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 状态卡片 */}
      <div className="flex items-center gap-3 p-3 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)]">
        <div className={`flex items-center justify-center w-10 h-10 rounded-lg border border-[var(--line)] ${status.active ? "bg-green-500/15 text-green-400" : "bg-white/5 text-[var(--muted)]"}`}>
          {status.active ? <Wifi className="h-5 w-5" /> : <WifiOff className="h-5 w-5" />}
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold text-[var(--text)]">
            {status.active ? "加速已启用" : "加速未启用"}
          </p>
          <p className="text-xs text-[var(--dim)]">
            {status.active ? `${status.entries.length} 条规则生效中` : "选择加速规则后一键启用"}
          </p>
        </div>
        <button
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            status.active
              ? "bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25"
              : "bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25"
          }`}
          onClick={status.active ? handleDisable : handleEnable}
          disabled={loading}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : status.active ? "关闭加速" : "启用加速"}
        </button>
      </div>

      {msg && (
        <div className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-bold ${
          msg.type === "success"
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-red-500/30 bg-red-500/10 text-red-400"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          {msg.text}
        </div>
      )}

      {/* 加速规则分组 */}
      {Object.entries(profiles).map(([name, domains]) => (
        <div key={name} className="rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] overflow-hidden">
          <div className="flex items-center gap-3 p-3 border-b border-[var(--line)]">
            <label className="flex items-center gap-2 flex-1 cursor-pointer">
              <input
                type="checkbox"
                checked={!!selected[name]}
                onChange={() => setSelected(s => ({ ...s, [name]: !s[name] }))}
                className="w-4 h-4 rounded accent-[var(--accent)]"
              />
              <Globe className="h-4 w-4 text-[var(--accent)]" />
              <span className="text-sm font-bold text-[var(--text)]">{name}</span>
              <span className="text-xs text-[var(--dim)]">({Object.keys(domains).length} 个域名)</span>
            </label>
            <button
              className="px-2.5 py-1 rounded text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all flex items-center gap-1"
              onClick={() => handleTest(name)}
              disabled={testing}
            >
              {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
              测速
            </button>
          </div>
          <div className="p-2">
            {Object.entries(domains).map(([domain, ip]) => {
              const tr = testResults[`${domain}:${ip}`];
              return (
                <div key={domain} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-white/3 rounded">
                  <span className="flex-1 text-[var(--text)] font-mono">{domain}</span>
                  <span className="text-[var(--dim)] font-mono">{ip}</span>
                  {tr && (
                    <span className={`font-bold ${tr.ok ? (tr.latency_ms < 100 ? "text-green-400" : tr.latency_ms < 300 ? "text-yellow-400" : "text-red-400") : "text-red-400"}`}>
                      {tr.ok ? `${tr.latency_ms}ms` : "超时"}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* 提示信息 */}
      <div className="p-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] text-xs text-[var(--dim)]">
        <p className="font-bold text-[var(--muted)] mb-1">💡 说明</p>
        <p>• 网络加速通过修改系统 hosts 文件实现，需要管理员权限</p>
        <p>• 当前已支持 Steam、Epic、Ubisoft、EA、Riot、Battle.net、GOG 和 GitHub 常用域名</p>
        <p>• 部分平台节点会按当前网络环境自动解析，如遇权限问题请以管理员身份运行程序</p>
        <p>• 加速规则仅在本机生效，关闭加速后自动还原</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
//  账号切换 (Account Switching)
// ═══════════════════════════════════════════════════════

function AccountPanel() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(null);
  const [msg, setMsg] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request("/accounts/list");
      setAccounts(res.items || []);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAccounts(); }, [fetchAccounts]);

  const handleSwitch = async (account) => {
    if (account.is_current) return;
    setSwitching(account.steam_id);
    setMsg(null);
    try {
      const res = await request("/accounts/switch", {
        method: "POST",
        body: JSON.stringify({
          steam_id: account.steam_id,
          account_name: account.account_name,
        }),
      });
      if (res.ok) {
        setMsg({ type: "success", text: `已切换到 ${account.persona_name}，Steam 正在重启...` });
        setTimeout(fetchAccounts, 3000);
      } else {
        setMsg({ type: "error", text: res.error });
      }
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setSwitching(null);
    }
  };

  const filtered = accounts.filter(a =>
    !searchTerm ||
    a.persona_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.account_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-4">
      {/* 搜索 */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--dim)]" />
        <input
          type="text"
          placeholder="搜索账号..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-3 py-2 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] text-sm text-[var(--text)] placeholder-[var(--dim)] outline-none focus:border-[var(--accent)]"
        />
      </div>

      {msg && (
        <div className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-bold ${
          msg.type === "success"
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-red-500/30 bg-red-500/10 text-red-400"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          {msg.text}
        </div>
      )}

      {/* 刷新按钮 */}
      <div className="flex justify-between items-center">
        <p className="text-xs text-[var(--dim)] font-bold">
          共 {accounts.length} 个账号
        </p>
        <button
          onClick={fetchAccounts}
          disabled={loading}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      {/* 账号列表 */}
      {loading && accounts.length === 0 ? (
        <div className="empty-state">
          <Loader2 className="h-8 w-8 mb-2 animate-spin text-[var(--dim)]" />
          <p className="text-sm text-[var(--dim)]">正在扫描账号...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <Users className="h-8 w-8 mb-2" />
          <p className="text-sm text-[var(--dim)]">未找到已登录的 Steam 账号</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(account => (
            <div
              key={account.steam_id}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer hover:bg-white/5 ${
                account.is_current
                  ? "border-green-500/30 bg-green-500/5"
                  : "border-[var(--line)] bg-[var(--panel-soft)]"
              }`}
              onClick={() => handleSwitch(account)}
            >
              {/* 头像 */}
              <div className="w-11 h-11 rounded-lg border border-[var(--line)] overflow-hidden flex-shrink-0 bg-white/5">
                <img
                  src={account.avatar_url || account.default_avatar_url || STEAM_DEFAULT_AVATAR_URL}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={e => {
                    const fallback = account.default_avatar_url || STEAM_DEFAULT_AVATAR_URL;
                    if (e.currentTarget.src !== fallback) {
                      e.currentTarget.src = fallback;
                      return;
                    }
                    e.currentTarget.onerror = null;
                  }}
                />
              </div>
              {/* 信息 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-bold text-[var(--text)] truncate">{account.persona_name}</p>
                  {account.is_current && (
                    <span className="mini-pill mini-pill-green">
                      <CheckCircle className="h-3 w-3" /> 当前
                    </span>
                  )}
                </div>
                <p className="text-xs text-[var(--dim)] truncate">{account.account_name}</p>
                <p className="text-xs text-[var(--dim)] font-mono mt-0.5">{account.steam_id}</p>
              </div>
              {/* 切换按钮 */}
              {!account.is_current && (
                <button
                  className="px-3 py-1.5 rounded-lg text-xs font-bold text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-all flex items-center gap-1"
                  disabled={switching === account.steam_id}
                  onClick={e => { e.stopPropagation(); handleSwitch(account); }}
                >
                  {switching === account.steam_id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Power className="h-3 w-3" />
                  )}
                  切换
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="p-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] text-xs text-[var(--dim)]">
        <p className="font-bold text-[var(--muted)] mb-1">💡 说明</p>
        <p>• 切换账号将关闭 Steam 并使用新账号重新启动</p>
        <p>• 仅显示在本机登录过且勾选了"记住密码"的账号</p>
        <p>• Steam ID 可用于识别不同的 Steam 账号</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
//  库存游戏 (Game Library)
// ═══════════════════════════════════════════════════════

function LibraryPanel() {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [translatedTerm, setTranslatedTerm] = useState("");
  const translateTimerRef = useRef(null);
  const [selectedGame, setSelectedGame] = useState(null);
  const [idleStatus, setIdleStatus] = useState([]);
  const [msg, setMsg] = useState(null);

  const fetchGames = useCallback(async () => {
    setLoading(true);
    try {
      const [res, idle] = await Promise.all([
        request("/library/games"),
        request("/library/idle/status"),
      ]);
      setGames(res.items || []);
      setIdleStatus(idle.items || []);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchGames(); }, [fetchGames]);

  // 防抖翻译：输入停止 600ms 后触发，用于跨语言搜索
  const handleSearchChange = (value) => {
    setSearchTerm(value);
    setTranslatedTerm("");
    if (translateTimerRef.current) clearTimeout(translateTimerRef.current);
    if (!value.trim()) return;
    translateTimerRef.current = setTimeout(async () => {
      try {
        const res = await request("/translate", {
          method: "POST",
          body: JSON.stringify({ term: value.trim() }),
        });
        if (res.translated) setTranslatedTerm(res.translated);
      } catch (_) { /* 翻译失败不影响本地过滤 */ }
    }, 600);
  };

  const handleIdle = async (appid) => {
    setMsg(null);
    try {
      const res = await request(`/library/idle/${appid}`, { method: "POST" });
      if (res.ok) {
        setMsg({ type: "success", text: `已开始模拟运行 AppID: ${appid}` });
      } else {
        setMsg({ type: "error", text: res.error });
      }
      const idle = await request("/library/idle/status");
      setIdleStatus(idle.items || []);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleStopIdle = async (appid) => {
    try {
      await request(`/library/idle/${appid}/stop`, { method: "POST" });
      const idle = await request("/library/idle/status");
      setIdleStatus(idle.items || []);
      setMsg({ type: "success", text: "已停止模拟运行" });
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleStopAll = async () => {
    try {
      await request("/library/idle/stop-all", { method: "POST" });
      setIdleStatus([]);
      setMsg({ type: "success", text: "已停止所有模拟运行" });
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const isIdling = (appid) => idleStatus.some(s => s.appid === appid && s.running);

  // 模糊匹配：支持原词、中英互译词、AppID
  const matchGame = (g, term) => {
    if (!term) return true;
    const name = g.name.toLowerCase();
    const t = term.toLowerCase();
    if (g.appid.includes(t)) return true;
    if (name.includes(t)) return true;
    // 按空格/标点拆词，所有词都出现在名称中即视为匹配
    const words = t.split(/[\s\-_]+/).filter(Boolean);
    if (words.length > 1 && words.every(w => name.includes(w))) return true;
    return false;
  };

  const filtered = games.filter(g =>
    !searchTerm || matchGame(g, searchTerm) || (translatedTerm && matchGame(g, translatedTerm))
  );

  return (
    <div className="space-y-4">
      {/* 搜索和统计 */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--dim)]" />
          <input
            type="text"
            placeholder="搜索游戏名、AppID 或中英文互译..."
            value={searchTerm}
            onChange={e => handleSearchChange(e.target.value)}
            className="w-full pl-10 pr-3 py-2 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] text-sm text-[var(--text)] placeholder-[var(--dim)] outline-none focus:border-[var(--accent)]"
          />
        </div>
        <button
          onClick={fetchGames}
          disabled={loading}
          className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* 统计条 */}
      <div className="flex items-center gap-4 text-xs text-[var(--dim)]">
        <span className="font-bold">共 {games.length} 款游戏</span>
        {idleStatus.length > 0 && (
          <>
            <span className="text-green-400 font-bold">{idleStatus.filter(s => s.running).length} 款运行中</span>
            <button
              onClick={handleStopAll}
              className="text-red-400 font-bold hover:underline"
            >
              全部停止
            </button>
          </>
        )}
      </div>

      {msg && (
        <div className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-bold ${
          msg.type === "success"
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-red-500/30 bg-red-500/10 text-red-400"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          {msg.text}
        </div>
      )}

      {/* 游戏列表 */}
      {loading && games.length === 0 ? (
        <div className="empty-state">
          <Loader2 className="h-8 w-8 mb-2 animate-spin text-[var(--dim)]" />
          <p className="text-sm text-[var(--dim)]">正在扫描 Steam 游戏库...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <Library className="h-8 w-8 mb-2" />
          <p className="text-sm text-[var(--dim)]">{searchTerm ? "没有匹配的游戏" : "未检测到已安装的 Steam 游戏"}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(game => {
            const idle = isIdling(game.appid);
            const expanded = selectedGame === game.appid;
            return (
              <div key={game.appid}>
                <div
                  className={`installed-game-card ${expanded ? "installed-game-card-active" : ""} cursor-pointer`}
                  onClick={() => setSelectedGame(expanded ? null : game.appid)}
                >
                  <img
                    src={game.header_url}
                    alt=""
                    className="installed-game-art"
                    onError={e => { e.target.className = "installed-game-art installed-game-art-fallback"; }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-[var(--text)] truncate">{game.name || `AppID: ${game.appid}`}</p>
                      {idle && (
                        <span className="mini-pill mini-pill-green">
                          <Play className="h-3 w-3" /> 运行中
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs text-[var(--dim)]">AppID: {game.appid}</span>
                      <span className="text-xs text-[var(--dim)]">{game.size_display}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {idle ? (
                      <button
                        className="px-2.5 py-1.5 rounded-lg text-xs font-bold text-red-400 border border-red-500/30 hover:bg-red-500/10 transition-all flex items-center gap-1"
                        onClick={e => { e.stopPropagation(); handleStopIdle(game.appid); }}
                      >
                        <StopCircle className="h-3 w-3" /> 停止
                      </button>
                    ) : (
                      <button
                        className="px-2.5 py-1.5 rounded-lg text-xs font-bold text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-all flex items-center gap-1"
                        onClick={e => { e.stopPropagation(); handleIdle(game.appid); }}
                      >
                        <Play className="h-3 w-3" /> 挂机
                      </button>
                    )}
                    {expanded ? <ChevronUp className="h-4 w-4 text-[var(--dim)]" /> : <ChevronDown className="h-4 w-4 text-[var(--dim)]" />}
                  </div>
                </div>
                {expanded && (
                  <div className="ml-1 mt-1 p-3 rounded-lg border border-[var(--line)] bg-black/20 text-xs space-y-1.5">
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">AppID</span><span className="text-[var(--text)] font-mono">{game.appid}</span></div>
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">安装目录</span><span className="text-[var(--text)] font-mono truncate">{game.installdir}</span></div>
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">安装路径</span><span className="text-[var(--text)] font-mono truncate">{game.install_path}</span></div>
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">磁盘大小</span><span className="text-[var(--text)]">{game.size_display}</span></div>
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">Build ID</span><span className="text-[var(--text)] font-mono">{game.build_id}</span></div>
                    <div className="flex gap-2"><span className="text-[var(--dim)] w-20">所在库</span><span className="text-[var(--text)] font-mono truncate">{game.library_path}</span></div>
                    {game.last_updated > 0 && (
                      <div className="flex gap-2"><span className="text-[var(--dim)] w-20">最后更新</span><span className="text-[var(--text)]">{new Date(game.last_updated * 1000).toLocaleString()}</span></div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════
//  本地令牌 (Authenticator)
// ═══════════════════════════════════════════════════════

function AuthenticatorPanel() {
  const [codes, setCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(null);
  const [msg, setMsg] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // 表单状态
  const [formName, setFormName] = useState("");
  const [formSecret, setFormSecret] = useState("");
  const [formType, setFormType] = useState("totp");
  const [formIssuer, setFormIssuer] = useState("");
  const [importText, setImportText] = useState("");

  const fetchCodes = useCallback(async () => {
    try {
      const res = await request("/authenticator/codes");
      setCodes(res.items || []);
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCodes();
    const interval = setInterval(fetchCodes, 5000);
    return () => clearInterval(interval);
  }, [fetchCodes]);

  const handleAdd = async () => {
    if (!formName || !formSecret) return;
    setMsg(null);
    try {
      const res = await request("/authenticator/add", {
        method: "POST",
        body: JSON.stringify({
          name: formName,
          secret: formSecret,
          token_type: formType,
          issuer: formIssuer,
        }),
      });
      if (res.ok) {
        setMsg({ type: "success", text: "令牌已添加" });
        setShowAdd(false);
        setFormName(""); setFormSecret(""); setFormType("totp"); setFormIssuer("");
        fetchCodes();
      } else {
        setMsg({ type: "error", text: res.error });
      }
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleDelete = async (id) => {
    try {
      await request(`/authenticator/${id}`, { method: "DELETE" });
      fetchCodes();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleImportUri = async () => {
    if (!importText) return;
    try {
      const res = await request("/authenticator/import-uri", {
        method: "POST",
        body: JSON.stringify({ uri: importText }),
      });
      if (res.ok) {
        setMsg({ type: "success", text: "令牌导入成功" });
        setShowImport(null);
        setImportText("");
        fetchCodes();
      } else {
        setMsg({ type: "error", text: res.error });
      }
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleImportSteam = async () => {
    if (!importText) return;
    try {
      const res = await request("/authenticator/import-steam", {
        method: "POST",
        body: JSON.stringify({ json_str: importText }),
      });
      if (res.ok) {
        setMsg({ type: "success", text: "Steam 令牌导入成功" });
        setShowImport(null);
        setImportText("");
        fetchCodes();
      } else {
        setMsg({ type: "error", text: res.error });
      }
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    }
  };

  const handleScanLocal = async () => {
    setScanning(true);
    setMsg(null);
    try {
      const res = await request("/authenticator/scan-local", { method: "POST" });
      setMsg({
        type: "success",
        text: `扫描到 ${res.found || 0} 个本地令牌，新增 ${res.imported || 0} 个，跳过 ${res.skipped || 0} 个`,
      });
      fetchCodes();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setScanning(false);
    }
  };

  const handleCopy = (code, id) => {
    navigator.clipboard.writeText(code).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  return (
    <div className="space-y-4">
      {/* 操作栏 */}
      <div className="flex gap-2">
        <button
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-all"
          onClick={handleScanLocal}
          disabled={scanning}
        >
          {scanning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} 扫描本机
        </button>
        <button
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-all"
          onClick={() => { setShowAdd(!showAdd); setShowImport(null); }}
        >
          <Plus className="h-3.5 w-3.5" /> 手动添加
        </button>
        <button
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
          onClick={() => { setShowImport(showImport === "uri" ? null : "uri"); setShowAdd(false); }}
        >
          <Upload className="h-3.5 w-3.5" /> OtpAuth URI
        </button>
        <button
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
          onClick={() => { setShowImport(showImport === "steam" ? null : "steam"); setShowAdd(false); }}
        >
          <Shield className="h-3.5 w-3.5" /> Steam JSON
        </button>
        <div className="flex-1" />
        <button
          onClick={fetchCodes}
          className="flex items-center gap-1 px-2.5 py-2 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {msg && (
        <div className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-bold ${
          msg.type === "success"
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-red-500/30 bg-red-500/10 text-red-400"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          {msg.text}
        </div>
      )}

      {/* 手动添加表单 */}
      {showAdd && (
        <div className="p-3 rounded-lg border border-[var(--accent)]/30 bg-[var(--panel-soft)] space-y-3">
          <p className="text-sm font-bold text-[var(--text)]">添加新令牌</p>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-[var(--dim)] mb-1">名称 *</label>
              <input
                type="text"
                value={formName}
                onChange={e => setFormName(e.target.value)}
                placeholder="例如: My Steam"
                className="w-full px-3 py-1.5 rounded border border-[var(--line)] bg-black/20 text-sm text-[var(--text)] placeholder-[var(--dim)] outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--dim)] mb-1">类型</label>
              <select
                value={formType}
                onChange={e => setFormType(e.target.value)}
                className="w-full px-3 py-1.5 rounded border border-[var(--line)] bg-black/20 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
              >
                <option value="totp">TOTP（标准）</option>
                <option value="steam">Steam Guard</option>
                <option value="hotp">HOTP</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-[var(--dim)] mb-1">
              密钥 * {formType === "steam" ? "(Base64)" : "(Base32)"}
            </label>
            <input
              type="text"
              value={formSecret}
              onChange={e => setFormSecret(e.target.value)}
              placeholder={formType === "steam" ? "Base64 编码的 shared_secret" : "Base32 编码的密钥"}
              className="w-full px-3 py-1.5 rounded border border-[var(--line)] bg-black/20 text-sm text-[var(--text)] font-mono placeholder-[var(--dim)] outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--dim)] mb-1">颁发者（可选）</label>
            <input
              type="text"
              value={formIssuer}
              onChange={e => setFormIssuer(e.target.value)}
              placeholder="例如: Steam, Google"
              className="w-full px-3 py-1.5 rounded border border-[var(--line)] bg-black/20 text-sm text-[var(--text)] placeholder-[var(--dim)] outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div className="flex gap-2 pt-1">
            <button
              className="px-4 py-1.5 rounded-lg text-xs font-bold bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/25 transition-all"
              onClick={handleAdd}
              disabled={!formName || !formSecret}
            >
              添加
            </button>
            <button
              className="px-4 py-1.5 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
              onClick={() => setShowAdd(false)}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 导入面板 */}
      {showImport && (
        <div className="p-3 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] space-y-3">
          <p className="text-sm font-bold text-[var(--text)]">
            {showImport === "uri" ? "导入 OtpAuth URI" : "导入 Steam Desktop Authenticator JSON"}
          </p>
          <textarea
            value={importText}
            onChange={e => setImportText(e.target.value)}
            placeholder={showImport === "uri" ? "otpauth://totp/..." : '{"shared_secret": "...", "account_name": "..."}'}
            rows={3}
            className="w-full px-3 py-2 rounded border border-[var(--line)] bg-black/20 text-sm text-[var(--text)] font-mono placeholder-[var(--dim)] outline-none focus:border-[var(--accent)] resize-none"
          />
          <div className="flex gap-2">
            <button
              className="px-4 py-1.5 rounded-lg text-xs font-bold bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/25 transition-all"
              onClick={showImport === "uri" ? handleImportUri : handleImportSteam}
              disabled={!importText}
            >
              导入
            </button>
            <button
              className="px-4 py-1.5 rounded-lg text-xs font-bold text-[var(--muted)] border border-[var(--line)] hover:bg-white/5 transition-all"
              onClick={() => { setShowImport(null); setImportText(""); }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 令牌列表 */}
      {loading ? (
        <div className="empty-state">
          <Loader2 className="h-8 w-8 mb-2 animate-spin text-[var(--dim)]" />
          <p className="text-sm text-[var(--dim)]">加载中...</p>
        </div>
      ) : codes.length === 0 ? (
        <div className="empty-state">
          <Key className="h-8 w-8 mb-2" />
          <p className="text-sm text-[var(--dim)]">暂无令牌</p>
          <p className="text-xs text-[var(--dim)] mt-1">点击上方按钮添加或导入令牌</p>
        </div>
      ) : (
        <div className="space-y-2">
          {codes.map(token => {
            const progress = (token.remaining_seconds / token.period) * 100;
            return (
              <div key={token.id} className="flex items-center gap-3 p-3 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] hover:bg-white/5 transition-all">
                {/* 图标 */}
                <div className={`flex items-center justify-center w-10 h-10 rounded-lg border border-[var(--line)] flex-shrink-0 ${
                  token.type === "steam" ? "bg-blue-500/10 text-blue-400" : "bg-[var(--accent)]/10 text-[var(--accent)]"
                }`}>
                  {token.type === "steam" ? <Shield className="h-5 w-5" /> : <Key className="h-5 w-5" />}
                </div>
                {/* 信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-[var(--text)] truncate">{token.name}</p>
                    <span className="mini-pill">
                      {token.type === "steam" ? "Steam" : token.type.toUpperCase()}
                    </span>
                    {token.issuer && <span className="text-xs text-[var(--dim)]">{token.issuer}</span>}
                  </div>
                  {/* 验证码 */}
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xl font-mono font-bold text-[var(--text)] tracking-widest">{token.code}</span>
                    <button
                      className="p-1 rounded hover:bg-white/10 transition-all"
                      onClick={() => handleCopy(token.code, token.id)}
                      title="复制"
                    >
                      {copiedId === token.id ? (
                        <CheckCircle className="h-3.5 w-3.5 text-green-400" />
                      ) : (
                        <Copy className="h-3.5 w-3.5 text-[var(--dim)]" />
                      )}
                    </button>
                  </div>
                </div>
                {/* 倒计时 */}
                <div className="flex flex-col items-center gap-1 flex-shrink-0">
                  <div className="relative w-9 h-9">
                    <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                      <circle cx="18" cy="18" r="16" fill="none" stroke="var(--line)" strokeWidth="2" />
                      <circle
                        cx="18" cy="18" r="16" fill="none"
                        stroke={progress < 25 ? "#ef4444" : "var(--accent)"}
                        strokeWidth="2"
                        strokeDasharray={`${2 * Math.PI * 16}`}
                        strokeDashoffset={`${2 * Math.PI * 16 * (1 - progress / 100)}`}
                        strokeLinecap="round"
                        className="transition-all duration-1000"
                      />
                    </svg>
                    <span className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${progress < 25 ? "text-red-400" : "text-[var(--text)]"}`}>
                      {token.remaining_seconds}
                    </span>
                  </div>
                </div>
                {/* 删除 */}
                <button
                  className="p-1.5 rounded hover:bg-red-500/10 text-[var(--dim)] hover:text-red-400 transition-all"
                  onClick={() => handleDelete(token.id)}
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="p-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel-soft)] text-xs text-[var(--dim)]">
        <p className="font-bold text-[var(--muted)] mb-1">💡 说明</p>
        <p>• 支持标准 TOTP/HOTP 和 Steam Guard 令牌</p>
        <p>• 可通过 OtpAuth URI 或 Steam Desktop Authenticator JSON 导入</p>
        <p>• Steam Guard 令牌使用 Base64 编码的 shared_secret</p>
        <p>• 令牌数据保存在本地，请妥善保管</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
//  主页面组件
// ═══════════════════════════════════════════════════════

export default function SteamToolsPage() {
  const [activeTab, setActiveTab] = useState("accelerator");

  const pageKicker = {
    accelerator: "Accelerator",
    accounts: "Account",
    library: "Library",
    authenticator: "Authenticator",
  };

  const pageTitle = {
    accelerator: "网络加速",
    accounts: "账号切换",
    library: "库存游戏",
    authenticator: "本地令牌",
  };

  return (
    <div className="space-y-5">
      {/* 子页签 */}
      <div className="flex gap-1.5 flex-wrap">
        <SubTab active={activeTab === "accelerator"} icon={Zap} label="网络加速" onClick={() => setActiveTab("accelerator")} />
        <SubTab active={activeTab === "accounts"} icon={Users} label="账号切换" onClick={() => setActiveTab("accounts")} />
        <SubTab active={activeTab === "library"} icon={Library} label="库存游戏" onClick={() => setActiveTab("library")} />
        <SubTab active={activeTab === "authenticator"} icon={ShieldCheck} label="本地令牌" onClick={() => setActiveTab("authenticator")} />
      </div>

      {/* 内容区 */}
      {activeTab === "accelerator" && <AcceleratorPanel />}
      {activeTab === "accounts" && <AccountPanel />}
      {activeTab === "library" && <LibraryPanel />}
      {activeTab === "authenticator" && <AuthenticatorPanel />}
    </div>
  );
}
