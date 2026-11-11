import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";
type Status = { hashrate: number; estimated_reward_per_day: number; active_miners: number; mode: string; real_mining: boolean; on_chain_payouts_enabled: boolean };
type Me = { balance_zrl: string; wallet_address?: string | null; username?: string | null };
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

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [tab, setTab] = useState<Tab>("home");

  async function load() {
    setBusy(true);
    setError("");
    try {
      const initData = (window as any).Telegram?.WebApp?.initData || "";
      const headers = { Authorization: "tma " + initData };
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

  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    load();
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">Z<span>•</span></div>
        <div className="brand-copy"><b>ZER0LIFE <i>MINING</i></b><small>POWERED BY ZER0LIFE LABS</small></div>
        <div className="network-pill"><span /> SOLANA</div>
      </header>

      <div className="page-heading">
        <div><span className="eyebrow">MINING ECOSYSTEM</span><h1>{tab === "home" ? <>Mine your<br /><em>digital future.</em></> : title}</h1></div>
        <button className="refresh-btn" onClick={load} disabled={busy} aria-label="Refresh">↻</button>
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
          <button onClick={() => setTab("wallet")}><span>▣</span><b>Connect wallet</b><small>Wallet overview</small></button>
        </section>
      </>}

      {tab === "mining" && <section className="content-card">
        <span className="eyebrow">YOUR MINING SESSION</span><h2>Mining status</h2>
        <div className="big-stat">{busy ? "—" : fmt(status?.hashrate)} <small>TH/s</small></div>
        <div className="detail-row"><span>Active miners</span><b>{busy ? "—" : fmt(status?.active_miners)}</b></div>
        <div className="detail-row"><span>Estimated daily reward</span><b>{busy ? "—" : fmt(status?.estimated_reward_per_day)} ZRL</b></div>
        <div className="detail-row"><span>Mode</span><b>{busy ? "—" : status?.mode || "—"}</b></div>
        <div className="info-note">Mining is currently represented by in-app game statistics. This screen does not start real proof-of-work mining.</div>
      </section>}

      {tab === "upgrade" && <section className="content-card">
        <span className="eyebrow">BOOST YOUR PROGRESS</span><h2>Miner upgrades</h2>
        <div className="empty-visual">↗</div><h3>Upgrade center</h3>
        <p>The upgrade interface is prepared as a menu section. Miner inventory, prices and purchase actions are not yet connected to the backend.</p>
        <span className="feature-state">NOT CONNECTED</span>
      </section>}

      {tab === "rewards" && <section className="content-card">
        <span className="eyebrow">YOUR EARNINGS</span><h2>Rewards</h2>
        <div className="reward-total">{busy ? "—" : fmt(me?.balance_zrl)} <small>ZRL</small></div>
        <p>Current internal ZRL balance from your account.</p>
        <div className="info-note">A detailed reward history requires a transaction-history API. No reward records are fabricated or changed by this screen.</div>
      </section>}

      {tab === "wallet" && <section className="content-card">
        <span className="eyebrow">SOLANA CONNECTION</span><h2>Wallet</h2>
        <div className="wallet-symbol">▣</div>
        <h3>{me?.wallet_address ? "Wallet linked" : "No wallet linked yet"}</h3>
        <p className="wallet-address">{me?.wallet_address || "Connect a Solana wallet to see its linked address here."}</p>
        <div className="info-note">Wallet linking and on-chain transfers are not triggered from this redesigned menu. Never share your seed phrase or private key.</div>
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
