import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";
type Status = { hashrate: number; estimated_reward_per_day: number; active_miners: number; mode: string; real_mining: boolean; on_chain_payouts_enabled: boolean };
type Me = { balance_zrl: string; wallet_address?: string | null; username?: string | null };
type Equipment = { id: number; code: string; name: string; price_zrl: string; hashrate: string; reward_per_day: string };
type Reward = { amount_zrl: string; kind: string; created_at: string };
type Period = "day" | "week" | "month";
type Tab = "home" | "mining" | "upgrade" | "rewards" | "wallet" | "profile";

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "mining", label: "Mining", icon: "⛏" },
  { id: "upgrade", label: "Upgrade", icon: "↗" },
  { id: "rewards", label: "Rewards", icon: "◇" },
  { id: "wallet", label: "Wallet", icon: "▣" },
  { id: "profile", label: "Profile", icon: "◎" },
];

function fmt(value: string | number | undefined) {
  if (value === undefined || value === null || value === "") return "—";
  return typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 4 }) : value;
}
function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
function kindLabel(kind: string) {
  const labels: Record<string, string> = { accrual: "Mining accrual", claim_internal: "Internal claim", admin_adjustment: "Account adjustment" };
  return labels[kind] || kind.replaceAll("_", " ");
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [period, setPeriod] = useState<Period>("week");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [sectionBusy, setSectionBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("home");

  function authHeaders() {
    const initData = window.Telegram?.WebApp?.initData || "";
    return { Authorization: "tma " + initData };
  }

  async function load() {
    setBusy(true);
    setError("");
    try {
      const headers = authHeaders();
      const [a, b] = await Promise.all([
        fetch(API + "/api/mining/status", { headers }),
        fetch(API + "/api/me", { headers }),
      ]);
      if (a.status === 401 || b.status === 401) throw Error("Открой Mini App через Telegram-бота.");
      if (!a.ok || !b.ok) throw Error("Backend API пока не готов.");
      setStatus(await a.json());
      setMe(await b.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки данных");
    } finally {
      setBusy(false);
    }
  }

  async function loadEquipment() {
    setSectionBusy(true);
    setError("");
    try {
      const response = await fetch(API + "/api/equipment", { headers: authHeaders() });
      if (response.status === 401) throw Error("Telegram-сессия истекла. Перезапусти Mini App.");
      if (!response.ok) throw Error("Не удалось загрузить каталог оборудования.");
      setEquipment(await response.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки оборудования");
    } finally {
      setSectionBusy(false);
    }
  }

  async function loadRewards(selectedPeriod: Period) {
    setSectionBusy(true);
    setError("");
    try {
      const response = await fetch(API + "/api/mining/stats?period=" + selectedPeriod, { headers: authHeaders() });
      if (response.status === 401) throw Error("Telegram-сессия истекла. Перезапусти Mini App.");
      if (!response.ok) throw Error("Не удалось загрузить историю наград.");
      const data = await response.json();
      setRewards(Array.isArray(data.rewards) ? data.rewards : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки истории");
    } finally {
      setSectionBusy(false);
    }
  }

  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    load();
  }, []);

  useEffect(() => {
    if (tab === "upgrade") loadEquipment();
    if (tab === "rewards") loadRewards(period);
  }, [tab, period]);

  const title = tabs.find((item) => item.id === tab)?.label || "Home";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">Z<span>•</span></div>
        <div className="brand-copy"><b>ZER0LIFE <i>MINING</i></b><small>POWERED BY ZER0LIFE LABS</small></div>
        <div className="network-pill"><span /> SOLANA</div>
      </header>

      <div className="page-heading">
        <div><span className="eyebrow">MINING ECOSYSTEM</span><h1>{tab === "home" ? <>Mine your<br /><em>digital future.</em></> : title}</h1></div>
        <button className="refresh-btn" onClick={() => { load(); if (tab === "upgrade") loadEquipment(); if (tab === "rewards") loadRewards(period); }} disabled={busy || sectionBusy} aria-label="Refresh">↻</button>
      </div>

      {error && <div className="notice" role="alert">{error}</div>}

      {tab === "home" && <>
        <section className="balance-card">
          <div className="balance-top"><span>YOUR ZRL BALANCE</span><span className="status-dot">● ACCOUNT</span></div>
          <div className="balance-value">{busy ? "••••••" : fmt(me?.balance_zrl)} <small>ZRL</small></div>
          <div className="balance-bottom"><span>Internal game balance</span><button onClick={() => setTab("wallet")}>View wallet ↗</button></div>
          <div className="card-glow" />
        </section>
        <section className="section-block">
          <div className="section-title"><div><span className="eyebrow">LIVE PERFORMANCE</span><h2>Mining overview</h2></div><span className="live-tag">● LIVE DATA</span></div>
          <div className="metric-grid">
            <Metric label="HASHRATE" value={busy ? "—" : fmt(status?.hashrate)} suffix="TH/s" icon="⌁" />
            <Metric label="EST. DAILY REWARD" value={busy ? "—" : fmt(status?.estimated_reward_per_day)} suffix="ZRL" icon="✧" />
            <Metric label="ACTIVE MINERS" value={busy ? "—" : fmt(status?.active_miners)} suffix="" icon="⛏" />
            <Metric label="MINING MODE" value={busy ? "—" : status?.mode || "—"} suffix="" icon="◈" />
          </div>
        </section>
        <section className="quick-actions">
          <button onClick={() => setTab("mining")}><span>⛏</span><b>Mining status</b><small>View performance</small></button>
          <button onClick={() => setTab("rewards")}><span>◇</span><b>My rewards</b><small>Balance & earnings</small></button>
          <button onClick={() => setTab("wallet")}><span>▣</span><b>Wallet</b><small>Wallet overview</small></button>
        </section>
      </>}

      {tab === "mining" && <section className="content-card">
        <span className="eyebrow">YOUR MINING SESSION</span><h2>Mining status</h2>
        <div className="big-stat">{busy ? "—" : fmt(status?.hashrate)} <small>TH/s</small></div>
        <div className="detail-row"><span>Active miners</span><b>{busy ? "—" : fmt(status?.active_miners)}</b></div>
        <div className="detail-row"><span>Estimated daily reward</span><b>{busy ? "—" : fmt(status?.estimated_reward_per_day)} ZRL</b></div>
        <div className="detail-row"><span>Mode</span><b>{busy ? "—" : status?.mode || "—"}</b></div>
        <div className="detail-row"><span>Real proof-of-work</span><b>{status?.real_mining ? "Enabled" : "Not active"}</b></div>
        <div className="info-note">This is virtual mining game accounting. It does not run real proof-of-work or mine cryptocurrency.</div>
      </section>}

      {tab === "upgrade" && <section className="content-card">
        <span className="eyebrow">BOOST YOUR PROGRESS</span><h2>Equipment catalog</h2>
        <p>Catalog loaded from the Mining API. Purchases are intentionally unavailable until real pricing and payment verification are implemented.</p>
        {sectionBusy && <div className="loading-line">Loading equipment…</div>}
        {!sectionBusy && equipment.length === 0 && <div className="empty-state">No equipment is currently available in the catalog.</div>}
        <div className="equipment-list">
          {equipment.map((item) => <article className="equipment-item" key={item.id}>
            <div className="equipment-icon">⛏</div>
            <div className="equipment-copy"><b>{item.name}</b><small>{item.code}</small><span>{fmt(item.hashrate)} TH/s · {fmt(item.reward_per_day)} ZRL/day</span></div>
            <div className="equipment-price"><b>{fmt(item.price_zrl)}</b><small>ZRL</small></div>
          </article>)}
        </div>
        <span className="feature-state">CATALOG CONNECTED · PURCHASES DISABLED</span>
      </section>}

      {tab === "rewards" && <section className="content-card">
        <span className="eyebrow">YOUR EARNINGS</span><h2>Rewards history</h2>
        <div className="reward-total">{busy ? "—" : fmt(me?.balance_zrl)} <small>ZRL</small></div>
        <p>Current internal balance. History is read directly from your account ledger.</p>
        <div className="period-switch" role="group" aria-label="History period">
          {(["day", "week", "month"] as Period[]).map((value) => <button key={value} className={period === value ? "selected" : ""} onClick={() => setPeriod(value)}>{value === "day" ? "24H" : value === "week" ? "7D" : "30D"}</button>)}
        </div>
        {sectionBusy && <div className="loading-line">Loading reward history…</div>}
        {!sectionBusy && rewards.length === 0 && <div className="empty-state">No reward entries in this period yet.</div>}
        <div className="reward-list">
          {rewards.map((item, index) => <article className="reward-item" key={item.created_at + "-" + index}>
            <div><b>{kindLabel(item.kind)}</b><small>{dateLabel(item.created_at)}</small></div>
            <strong>{fmt(item.amount_zrl)} ZRL</strong>
          </article>)}
        </div>
        <div className="info-note">Ledger entries are shown as recorded by the API. Claim and blockchain transfer actions are not enabled here.</div>
      </section>}

      {tab === "wallet" && <section className="content-card">
        <span className="eyebrow">SOLANA CONNECTION</span><h2>Wallet</h2>
        <div className="wallet-symbol">▣</div>
        <h3>{me?.wallet_address ? "Wallet linked" : "No wallet linked yet"}</h3>
        <p className="wallet-address">{me?.wallet_address || "Connect a Solana wallet to see its linked address here."}</p>
        <div className="info-note">Wallet linking and on-chain transfers are not triggered from this menu. Never share your seed phrase or private key.</div>
        <div className="detail-row"><span>On-chain payouts</span><b>{status?.on_chain_payouts_enabled ? "Enabled in API" : "Disabled"}</b></div>
      </section>}

      {tab === "profile" && <section className="content-card">
        <span className="eyebrow">YOUR ACCOUNT</span><h2>Profile</h2>
        <div className="profile-avatar">{(me?.username || "Z").slice(0, 1).toUpperCase()}</div>
        <h3>{me?.username ? "@" + me.username : "Zer0Life member"}</h3>
        <div className="detail-row"><span>Telegram account</span><b>{me?.username ? "Connected" : "Verified in Mini App"}</b></div>
        <div className="detail-row"><span>Internal balance</span><b>{busy ? "—" : fmt(me?.balance_zrl) + " ZRL"}</b></div>
        <div className="detail-row"><span>Wallet</span><b>{me?.wallet_address ? "Linked" : "Not linked"}</b></div>
      </section>}

      <footer>ZER0LIFE LABS <span>·</span> SOLANA <span>·</span> ZRL ECOSYSTEM</footer>

      <nav className="bottom-nav" aria-label="Main navigation">
        {tabs.map((item) => <button key={item.id} className={tab === item.id ? "nav-item active" : "nav-item"} onClick={() => setTab(item.id)}>
          <span className="nav-icon">{item.icon}</span><small>{item.label}</small>
        </button>)}
      </nav>
    </main>
  );
}

function Metric({ label, value, suffix, icon }: { label: string; value: string; suffix: string; icon: string }) {
  return <div className="metric-card"><div className="metric-head"><span>{label}</span><i>{icon}</i></div><strong>{value}<small>{suffix}</small></strong></div>;
}
