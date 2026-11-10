import { useEffect, useState } from "react";

declare global { interface Window { Telegram?: { WebApp?: { initData?: string; ready:()=>void; expand:()=>void } } } }
const API = import.meta.env.VITE_API_URL || "";
type Status = { hashrate?: number; estimated_reward_per_day?: number; internal_balance_zrl?: number; active_miners?: number };
export default function App() {
  const [status,setStatus]=useState<Status|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(true);
  async function load(){
    setBusy(true); setError("");
    try {
      const initData=window.Telegram?.WebApp?.initData || "";
      const r=await fetch(API+"/api/mining/status",{headers:{"X-Telegram-Init-Data":initData}});
      if(!r.ok) throw new Error(r.status===401?"Открой приложение через Telegram-бота.":"API пока не отвечает.");
      setStatus(await r.json());
    } catch(e) { setError(e instanceof Error?e.message:"Не удалось загрузить данные."); }
    finally { setBusy(false); }
  }
  useEffect(()=>{window.Telegram?.WebApp?.ready();window.Telegram?.WebApp?.expand();load();},[]);
  return <main className="app">
    <header><div className="logo">Z</div><div><b>ZER0LIFE MINING</b><small>WEB3 · SOLANA · ZRL</small></div><span className="live">● MINI APP</span></header>
    <section className="hero"><small>ZER0LIFE LABS ECOSYSTEM</small><h1>Mine your<br/><em>digital future.</em></h1><p>Virtual mining dashboard powered by the Zer0Life ecosystem.</p></section>
    {error && <div className="notice">{error}</div>}
    <section className="panel"><div className="panel-head"><b>MINING OVERVIEW</b><button onClick={load} disabled={busy}>↻ Refresh</button></div>
      {busy?<p>Loading mining data…</p>:status?<div className="stats">
        <div><small>HASHRATE</small><strong>{status.hashrate ?? "—"} TH/s</strong></div>
        <div><small>EST. DAILY REWARD</small><strong>{status.estimated_reward_per_day ?? "—"} ZRL</strong></div>
        <div><small>INTERNAL BALANCE</small><strong>{status.internal_balance_zrl ?? "—"} ZRL</strong></div>
        <div><small>ACTIVE MINERS</small><strong>{status.active_miners ?? "—"}</strong></div>
      </div>:<p>Mining data is not available yet.</p>}
    </section>
    <section className="panel"><b>IMPORTANT</b><p>This is a virtual mining simulation. Rewards shown here are internal game accounting only. No real mining, token locking, or on-chain payouts are performed.</p><p>Wallet connection and on-chain ZRL balance are read-only. Never share your seed phrase or private key.</p></section>
    <footer>ZER0LIFE LABS · SOLANA · VIRTUAL MINING</footer>
  </main>;
}
