import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";
type Status = { hashrate: number; equipment_hashrate?: number; farming_power_ths?: number; farming_locked_zrl?: string; active_farming_positions?: number; estimated_reward_per_day: number; active_miners: number; mode: string; real_mining: boolean; on_chain_payouts_enabled: boolean };
type Me = { balance_zrl: string; wallet_address?: string | null; username?: string | null; is_admin?: boolean; farming_max_zrl?: string };
type Equipment = { id: number; code: string; name: string; price_zrl: string; hashrate: string; reward_per_day: string };
type Reward = { amount_zrl: string; kind: string; created_at: string };
type Period = "day" | "week" | "month";
type Tab = "home" | "mining" | "farming" | "community" | "upgrade" | "rewards" | "wallet" | "profile" | "admin";

const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "mining", label: "Mining", icon: "⛏" },
  { id: "farming", label: "Farming", icon: "🌱" },
  { id: "community", label: "Community", icon: "♧" },
  { id: "upgrade", label: "Upgrade", icon: "↗" },
  { id: "rewards", label: "Rewards", icon: "◇" },
  { id: "wallet", label: "Wallet", icon: "▣" },
  { id: "profile", label: "Profile", icon: "◎" },
  { id: "admin", label: "Admin", icon: "⚙" },
];

function fmt(value: string | number | undefined) {
  if (value === undefined || value === null || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return numeric.toLocaleString("en-US", { maximumFractionDigits: 3 });
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
  const [walletBusy, setWalletBusy] = useState(false);
  const [walletMessage, setWalletMessage] = useState("");
  const [depositSignature, setDepositSignature] = useState("");
  const [depositBusy, setDepositBusy] = useState(false);
  const [depositMessage, setDepositMessage] = useState("");
  const [depositIntent, setDepositIntent] = useState<{treasury_address:string;token_mint:string;memo_required:boolean;sender_wallet:string} | null>(null);
  const [farmPositions, setFarmPositions] = useState<any[]>([]);
  const [farmAmount, setFarmAmount] = useState("");
  const [farmDuration, setFarmDuration] = useState(12);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [farmMessage, setFarmMessage] = useState("");
  const [farmBusy, setFarmBusy] = useState(false);
  const [referralData, setReferralData] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [adminAvailable, setAdminAvailable] = useState(false);
  const [adminData, setAdminData] = useState<any>(null);
  const [avatarUrl, setAvatarUrl] = useState<string>("");
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarMessage, setAvatarMessage] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawId, setWithdrawId] = useState<number | null>(null);
  const [withdrawCode, setWithdrawCode] = useState("");
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [withdrawMessage, setWithdrawMessage] = useState("");
  const [withdrawals, setWithdrawals] = useState<any[]>([]);


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

  async function createDepositIntent() {
    setDepositBusy(true); setError(""); setDepositMessage("");
    try {
      const response = await fetch(API + "/api/deposits/details", { headers: authHeaders() });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Не удалось создать код пополнения.");
      setDepositIntent(data);
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка создания пополнения"); }
    finally { setDepositBusy(false); }
  }
  async function verifyDeposit() {
    const signature = depositSignature.trim();
    if (!signature) { setError("Вставь Transaction Signature из Solana."); return; }
    setDepositBusy(true);
    setDepositMessage("");
    setError("");
    try {
      const response = await fetch(API + "/api/deposits/verify", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ signature }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Не удалось проверить пополнение.");
      setDepositMessage(data.already_credited
        ? "Эта транзакция уже была зачислена."
        : "Пополнение подтверждено: +" + data.amount_zrl + " ZRL");
      setDepositSignature("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка проверки пополнения");
    } finally {
      setDepositBusy(false);
    }
  }


  async function loadWithdrawals() {
    try {
      const response = await fetch(API + "/api/wallet/withdrawals", { headers: authHeaders() });
      const data = await response.json();
      if (response.ok) setWithdrawals(Array.isArray(data) ? data : []);
    } catch { /* Keep current withdrawal history visible if refresh fails. */ }
  }

  async function requestWithdrawal() {
    setWithdrawBusy(true); setError(""); setWithdrawMessage("");
    try {
      const response = await fetch(API + "/api/wallet/withdrawals/request", {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ amount_zrl: withdrawAmount, destination_wallet: me?.wallet_address || "" })
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Could not request withdrawal.");
      setWithdrawId(data.withdrawal_id);
      setWithdrawCode("");
      setWithdrawMessage("A 6-digit confirmation code was sent to your Telegram chat. Enter it below.");
      setWithdrawAmount("");
      await loadWithdrawals();
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Withdrawal request failed."); }
    finally { setWithdrawBusy(false); }
  }

  async function verifyWithdrawal() {
    if (!withdrawId) return;
    setWithdrawBusy(true); setError(""); setWithdrawMessage("");
    try {
      const response = await fetch(API + "/api/wallet/withdrawals/verify", {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ withdrawal_id: withdrawId, code: withdrawCode })
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Could not verify withdrawal.");
      setWithdrawMessage(data.message || "Code verified. Withdrawal is pending payout review.");
      setWithdrawId(null); setWithdrawCode("");
      await Promise.all([loadWithdrawals(), load()]);
    } catch (e) { setError(e instanceof Error ? e.message : "Code verification failed."); }
    finally { setWithdrawBusy(false); }
  }

  async function cancelWithdrawal(id: number) {
    setWithdrawBusy(true); setError(""); setWithdrawMessage("");
    try {
      const response = await fetch(API + "/api/wallet/withdrawals/cancel", {
        method: "POST", headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ withdrawal_id: id })
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Could not cancel withdrawal.");
      setWithdrawMessage("Request cancelled. " + fmt(data.refunded_zrl) + " ZRL returned to your balance.");
      setWithdrawId(null); setWithdrawCode("");
      await Promise.all([loadWithdrawals(), load()]);
    } catch (e) { setError(e instanceof Error ? e.message : "Cancellation failed."); }
    finally { setWithdrawBusy(false); }
  }

  async function loadFarming() {
    setSectionBusy(true); setError("");
    try {
      const response = await fetch(API + "/api/farming/positions", { headers: authHeaders() });
      const data = await response.json(); if (!response.ok) throw Error(data.detail || "Не удалось загрузить Farming.");
      setFarmPositions(Array.isArray(data) ? data : []);
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка Farming"); }
    finally { setSectionBusy(false); }
  }
  async function createFarm() {
    setFarmBusy(true); setFarmMessage(""); setError("");
    try {
      const response = await fetch(API + "/api/farming/positions", { method:"POST", headers:{...authHeaders(),"Content-Type":"application/json"}, body:JSON.stringify({amount_zrl:farmAmount,duration_months:farmDuration}) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail || "Не удалось открыть Farming.");
      setFarmMessage("Farming открыт на " + farmDuration + " мес. Сумма заблокирована до даты окончания пакета.");
      setFarmAmount(""); await Promise.all([loadFarming(), load()]);
    } catch(e) { setError(e instanceof Error ? e.message : "Ошибка открытия Farming"); }
    finally { setFarmBusy(false); }
  }
  async function releaseFarm() {
    setFarmBusy(true); setFarmMessage(""); setError("");
    try {
      const response = await fetch(API + "/api/farming/release", {method:"POST",headers:authHeaders()});
      const data = await response.json(); if (!response.ok) throw Error(data.detail || "Principal release unavailable.");
      setFarmMessage("Returned " + fmt(data.released_principal_zrl) + " ZRL principal and credited " + fmt(data.maturity_reward_zrl || "0") + " ZRL final reward to your internal balance. No Solana transfer was made.");
      await Promise.all([loadFarming(), load()]);
    } catch(e) { setError(e instanceof Error ? e.message : "Farming release error"); }
    finally { setFarmBusy(false); }
  }
  async function claimFarm() {
    setFarmBusy(true); setFarmMessage(""); setError("");
    try {
      const response = await fetch(API + "/api/farming/claim", { method:"POST", headers:authHeaders() });
      const data = await response.json(); if (!response.ok) throw Error(data.detail || "Claim недоступен.");
      setFarmMessage("Начислено " + fmt(data.claimed_zrl) + " ZRL на внутренний баланс. Это не Solana-перевод.");
      await Promise.all([loadFarming(), load()]);
    } catch(e) { setError(e instanceof Error ? e.message : "Ошибка Claim"); }
    finally { setFarmBusy(false); }
  }
  async function loadAdmin() {
    try {
      const response = await fetch(API + "/api/admin/partner-dashboard", {headers:authHeaders()});
      if (response.status === 403 || response.status === 401) { setAdminAvailable(false); return; }
      if (!response.ok) throw Error("Admin dashboard unavailable");
      setAdminData(await response.json());
      setAdminAvailable(true);
    } catch { setAdminAvailable(false); }
  }

  async function loadCommunity() {
    setSectionBusy(true); setError("");
    try {
      const [r,l,h] = await Promise.all([
        fetch(API + "/api/referrals/me", {headers:authHeaders()}),
        fetch(API + "/api/leaderboard", {headers:authHeaders()}),
        fetch(API + "/api/referrals/commissions", {headers:authHeaders()})
      ]);
      const rd=await r.json(), ld=await l.json(), hd=await h.json();
      if(!r.ok || !l.ok || !h.ok) throw Error(rd.detail || ld.detail || hd.detail || "Не удалось загрузить Community.");
      setReferralData({...rd, commission_history:hd.items || []}); setLeaderboard(ld.leaderboard || []);
    } catch(e) { setError(e instanceof Error ? e.message : "Ошибка Community"); }
    finally { setSectionBusy(false); }
  }
  async function bindStartReferral() {
    const code = (window.Telegram?.WebApp as any)?.initDataUnsafe?.start_param || new URLSearchParams(window.location.search).get("ref") || "";
    if (!code) return;
    const response = await fetch(API + "/api/referrals/bind", {
      method:"POST",
      headers:{...authHeaders(),"Content-Type":"application/json"},
      body:JSON.stringify({referral_code:code})
    });
    if (response.ok) return;
    const data = await response.json().catch(() => ({}));
    // A previously bound account is expected on later app opens; never overwrite it.
    if (response.status === 409 && String(data.detail || "").includes("already set")) return;
    if (response.status === 400) throw Error(data.detail || "Invalid referral code");
    throw Error(data.detail || "Could not save referral attribution");
  }

  async function loadAvatar() {
    try {
      const response = await fetch(API + "/api/profile/avatar", { headers: authHeaders() });
      if (!response.ok) return;
      const data = await response.json();
      setAvatarUrl(data.avatar ? "" : (data.data ? "data:" + data.content_type + ";base64," + data.data : ""));
    } catch { /* Keep the default profile placeholder if avatar loading fails. */ }
  }

  async function uploadAvatar(file?: File) {
    if (!file) return;
    setAvatarBusy(true); setAvatarMessage(""); setError("");
    try {
      const form = new FormData(); form.append("file", file);
      const response = await fetch(API + "/api/profile/avatar", { method: "POST", headers: authHeaders(), body: form });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Could not upload avatar.");
      await loadAvatar();
      setAvatarMessage("Profile photo updated.");
    } catch (e) { setError(e instanceof Error ? e.message : "Avatar upload failed."); }
    finally { setAvatarBusy(false); }
  }

  async function removeAvatar() {
    setAvatarBusy(true); setAvatarMessage(""); setError("");
    try {
      const response = await fetch(API + "/api/profile/avatar", { method: "DELETE", headers: authHeaders() });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Could not remove avatar.");
      setAvatarUrl(""); setAvatarMessage("Profile photo removed.");
    } catch (e) { setError(e instanceof Error ? e.message : "Avatar removal failed."); }
    finally { setAvatarBusy(false); }
  }

  async function connectPhantom() {
    setWalletBusy(true);
    setWalletMessage("");
    setError("");
    try {
      const provider = window.phantom?.solana;
      if (!provider) throw Error("Phantom не найден. Открой приложение в браузере с установленным Phantom.");
      const connected = await provider.connect();
      const address = connected.publicKey.toString();
      const challengeResponse = await fetch(API + "/api/wallet/challenge", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ wallet_address: address }),
      });
      const challenge = await challengeResponse.json();
      if (!challengeResponse.ok) throw Error(challenge.detail || "Не удалось создать проверку кошелька.");
      const signed = await provider.signMessage(new TextEncoder().encode(challenge.message), "utf8");
      const signature = btoa(Array.from(signed.signature).map((byte) => String.fromCharCode(byte)).join(""));
      const verifyResponse = await fetch(API + "/api/wallet/verify", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ wallet_address: address, nonce: challenge.nonce, signature }),
      });
      const verified = await verifyResponse.json();
      if (!verifyResponse.ok) throw Error(verified.detail || "Не удалось подтвердить подпись кошелька.");
      setMe((current) => current ? { ...current, wallet_address: verified.wallet_address } : current);
      setWalletMessage("Phantom успешно привязан. Подпись подтверждает владение адресом, переводов не выполнялось.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка подключения Phantom");
    } finally {
      setWalletBusy(false);
    }
  }

  useEffect(() => {
    const viewport = window.visualViewport;
    const updateKeyboard = () => setKeyboardOpen(!!viewport && window.innerHeight - viewport.height > 140);
    viewport?.addEventListener("resize", updateKeyboard);
    viewport?.addEventListener("scroll", updateKeyboard);
    updateKeyboard();
    return () => { viewport?.removeEventListener("resize", updateKeyboard); viewport?.removeEventListener("scroll", updateKeyboard); };
  }, []);

  useEffect(() => {
    window.Telegram?.WebApp?.ready();
    window.Telegram?.WebApp?.expand();
    (async () => {
      try {
        // Bind the inviter before loading Community data. Previously this
        // function existed but was never called, so registrations could remain
        // unassigned even when the deep-link carried a referral code.
        await bindStartReferral();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Referral attribution failed");
      }
      await load();
    })();
  }, []);

  useEffect(() => {
    if (tab === "upgrade") loadEquipment();
    if (tab === "rewards") loadRewards(period);
    if (tab === "farming") loadFarming();
    if (tab === "community") loadCommunity();
    if (tab === "admin") loadAdmin();
    if (tab === "profile") loadAvatar();
    if (tab === "wallet") loadWithdrawals();
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
            <Metric label="TOTAL VIRTUAL HASHRATE" value={busy ? "—" : fmt(status?.hashrate)} suffix="TH/s" icon="⌁" />
            <Metric label="FARMING POWER" value={busy ? "—" : fmt(status?.farming_power_ths)} suffix="TH/s" icon="🌱" />
            <Metric label="EST. DAILY REWARD" value={busy ? "—" : fmt(status?.estimated_reward_per_day)} suffix="ZRL" icon="✧" />
            <Metric label="ACTIVE MINERS" value={busy ? "—" : fmt(status?.active_miners)} suffix="" icon="⛏" />
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
        <div className="big-stat">{busy ? "—" : fmt(status?.hashrate)} <small>TH/s total virtual</small></div>
        <div className="detail-row"><span>Equipment hashrate</span><b>{busy ? "—" : fmt(status?.equipment_hashrate)} TH/s</b></div>
        <div className="detail-row"><span>Farming Power</span><b>{busy ? "—" : fmt(status?.farming_power_ths)} TH/s</b></div>
        <div className="detail-row"><span>ZRL locked in Farming</span><b>{busy ? "—" : fmt(status?.farming_locked_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Active Farming positions</span><b>{busy ? "—" : fmt(status?.active_farming_positions)}</b></div>
        <div className="detail-row"><span>Active miners</span><b>{busy ? "—" : fmt(status?.active_miners)}</b></div>
        <div className="detail-row"><span>Estimated daily reward</span><b>{busy ? "—" : fmt(status?.estimated_reward_per_day)} ZRL</b></div>
        <div className="detail-row"><span>Mode</span><b>{busy ? "—" : status?.mode || "—"}</b></div>
        <div className="detail-row"><span>Real proof-of-work</span><b>{status?.real_mining ? "Enabled" : "Not active"}</b></div>
        <div className="info-note">This is virtual mining game accounting. It does not run real proof-of-work or mine cryptocurrency.</div>
      </section>}


      {tab === "farming" && <section className="content-card farming-card">
        <span className="eyebrow">ZRL FIXED-TERM FARMING</span><h2>Choose your Farming package</h2>
        <div className="info-note">Choose a lock period. Rewards follow a decreasing monthly schedule; the 12-month package totals 155% over the full term. Shorter packages receive the sum of their scheduled months. Daily Claim opens after 20:00 Warsaw time. All balances are internal; Solana payouts are disabled.</div>
        <div className="farm-packages" role="group" aria-label="Farming duration">
          {[1,3,6,9,12].map(months => <button type="button" key={months} className={farmDuration===months ? "farm-package selected" : "farm-package"} onClick={()=>setFarmDuration(months)}><b>{months}</b><small>month{months>1?"s":""}</small><strong>{(155*[12,11,10,9,8,7,6,5,4,3,2,1].slice(0,months).reduce((x,y)=>x+y,0)/78).toFixed(2)}%</strong><em>scheduled</em></button>)}
        </div>
        <label htmlFor="farm-amount">Amount to lock (ZRL)</label>
        <div className="info-note">Maximum per Farming position: {fmt(me?.farming_max_zrl || "1000000")} ZRL {me?.is_admin ? "(Admin limit)" : "(User limit)"}.</div>
        <input id="farm-amount" className="deposit-input" inputMode="decimal" type="number" min="0" max={me?.farming_max_zrl || "1000000"} step="any" value={farmAmount} onChange={e=>setFarmAmount(e.target.value)} placeholder="Enter ZRL amount" />
        <div className="farm-calculator"><div><span>Selected package</span><b>{farmDuration} months</b></div><div><span>Principal</span><b>{farmAmount && Number(farmAmount)>0 ? fmt(farmAmount)+" ZRL" : "—"}</b></div><div><span>Estimated total reward</span><b className="farm-estimate">{farmAmount && Number(farmAmount)>0 ? fmt(Number(farmAmount)*155*[12,11,10,9,8,7,6,5,4,3,2,1].slice(0,farmDuration).reduce((x,y)=>x+y,0)/7800)+" ZRL" : "—"}</b></div><div><span>Principal + scheduled reward</span><b>{farmAmount && Number(farmAmount)>0 ? fmt(Number(farmAmount)*(1+155*[12,11,10,9,8,7,6,5,4,3,2,1].slice(0,farmDuration).reduce((x,y)=>x+y,0)/7800))+" ZRL" : "—"}</b></div></div>
        <div className="farm-schedule"><b>Monthly reward schedule</b>{[12,11,10,9,8,7,6,5,4,3,2,1].slice(0,farmDuration).map((weight,index)=><div className="farm-month" key={index}><span>Month {index+1}</span><span>{(155*weight/78).toFixed(2)}% of principal</span><b>{farmAmount && Number(farmAmount)>0 ? fmt(Number(farmAmount)*155*weight/7800)+" ZRL" : "—"}</b></div>)}</div>
        <button className="wallet-connect-btn" onClick={createFarm} disabled={farmBusy || !farmAmount || Number(farmAmount)<=0 || Number(farmAmount)>Number(me?.balance_zrl||0) || Number(farmAmount)>Number(me?.farming_max_zrl||1000000)}>{farmBusy ? "Processing…" : "Start " + farmDuration + "-month Farming"}</button>
        <button className="wallet-connect-btn secondary-action" onClick={claimFarm} disabled={farmBusy}>{farmBusy ? "Processing…" : "Claim daily rewards · after 20:00"}</button>
        <button className="wallet-connect-btn secondary-action" onClick={releaseFarm} disabled={farmBusy}>{farmBusy ? "Processing…" : "Release matured principal"}</button>
        {farmMessage && <div className="wallet-success" role="status">{farmMessage}</div>}
        <h3>Your Farming positions</h3>{sectionBusy && <div className="loading-line">Loading positions…</div>}{!sectionBusy && farmPositions.length===0 && <div className="empty-state">No active Farming positions.</div>}{farmPositions.map(p=><article className="reward-item" key={p.id}><div><b>{fmt(p.principal_zrl)} ZRL locked</b><small>Ends: {dateLabel(p.ends_at)}</small><small>Claimed: {fmt(p.claimed_reward_zrl)} ZRL</small></div><strong>{fmt(p.pending_reward_zrl)} ZRL pending</strong></article>)}
      </section>}
      {tab === "community" && <section className="content-card">
        <span className="eyebrow">ZER0LIFE PARTNER PROGRAM</span><h2>Community & ranks</h2>
        {sectionBusy && <div className="loading-line">Loading community…</div>}
        {referralData && <>
          <div className="detail-row"><span>Your referral code</span><b>{referralData.referral_code}</b></div>
          <div className="detail-row"><span>Partner earnings pending</span><b>{fmt(referralData.partner_earnings_pending_zrl ?? referralData.partner_earnings_zrl)} ZRL</b></div>
          {referralData.commission_by_level?.map((x:any)=><div className="detail-row" key={"commission-"+x.level}><span>Level {x.level} · {x.rate} commission</span><b>{fmt(x.pending_zrl)} ZRL pending</b></div>)}
          <div className="deposit-details"><b>Your invitation link</b><code>{referralData.referral_link}</code><button className="wallet-connect-btn" onClick={()=>navigator.clipboard?.writeText(referralData.referral_link)}>Copy invitation link</button></div>
          {referralData.levels?.map((x:any)=><div className="detail-row" key={x.level}><span>Level {x.level} · {x.rate}</span><b>{x.count} members</b></div>)}
        </>}
        <h3>Leader ranks</h3>
        <div className="info-note">Bronze → Silver → Gold → Platinum → Diamond. Rank thresholds are provisional and require final approval before rewards or privileges are attached.</div>
        {leaderboard.map((x:any,i:number)=><article className="reward-item" key={`${x.username}-${i}`}><div><b>#{i+1} · {x.username}</b><small>{x.direct_referrals} direct referrals</small></div><strong>{x.rank}</strong></article>)}
        <div className="info-note">Invited by: {referralData?.invited_by ? (referralData.invited_by.username ? "@"+referralData.invited_by.username : "Telegram user "+referralData.invited_by.telegram_id) : "No referrer linked to this account"}.</div>
        <div className="info-note">Partner percentages: Level 1 — 5%, Level 2 — 2%, Level 3 — 1%. Commissions are pending by level and are not spendable or withdrawable. On-chain partner payouts are disabled.</div>
        <h3>Partner commission history</h3>
        {!referralData?.commission_history?.length && <div className="empty-state">No partner commissions recorded yet.</div>}
        {referralData?.commission_history?.map((x:any)=><article className="reward-item" key={x.id}><div><b>Level {x.level} commission</b><small>{dateLabel(x.created_at)}</small><small>Pending · internal ledger only</small></div><strong>{fmt(x.amount_zrl)} ZRL</strong></article>)}
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
        <span className="eyebrow">ZER0LIFE TREASURY</span><h2>Shared wallet</h2>
        <div className="wallet-symbol">▣</div>
        <h3>Central Treasury Wallet</h3>
        <p className="wallet-address">One shared Solana Treasury address for every Telegram user. No Phantom connection and no memo are required.</p>
        <div className="deposit-panel">
          <span className="eyebrow">ADD ZRL TO YOUR ACCOUNT</span>
          <h3>Generate deposit details</h3>
          <p>Show the shared Treasury address, send only ZRL on Solana, then submit the transaction signature for Helius verification.</p>
          <button className="wallet-connect-btn" onClick={createDepositIntent} disabled={depositBusy}>{depositBusy ? "Loading…" : "Show deposit address"}</button>
          {depositIntent && <div className="deposit-details"><b>Shared Treasury address</b><code>{depositIntent.treasury_address}</code><button className="wallet-connect-btn" onClick={() => navigator.clipboard?.writeText(depositIntent.treasury_address)}>Copy Treasury address</button><small>ZRL only · Solana · No memo</small></div>}
          <div className="info-note">Helius RPC verifies the finalized ZRL transfer, token mint, Treasury destination and amount. The first Telegram account to submit a transaction signature claims that deposit. Never share your transaction signature publicly.</div>
          <input className="deposit-input" value={depositSignature} onChange={(event) => setDepositSignature(event.target.value)} placeholder="Solana transaction signature" autoComplete="off" />
          <button className="wallet-connect-btn" onClick={verifyDeposit} disabled={depositBusy || !depositIntent}>{depositBusy ? "Checking on Solana…" : "Verify deposit"}</button>
          {depositMessage && <div className="wallet-success" role="status">{depositMessage}</div>}
          <a className="deposit-address" href="https://solscan.io/account/4GEVDNM4VEtdRpwLcybsX2R4yhYL2vcYoNhoFsxY49Ex" target="_blank" rel="noreferrer">View Treasury on Solscan ↗</a>
        </div>

        <div className="deposit-panel">
          <span className="eyebrow">WITHDRAW ZRL</span>
          <h3>Withdraw to your verified Solana wallet</h3>
          <div className="detail-row"><span>Available internal balance</span><b>{fmt(me?.balance_zrl)} ZRL</b></div>
          <div className="detail-row"><span>Verified destination</span><b>{me?.wallet_address ? me.wallet_address.slice(0,6)+"…"+me.wallet_address.slice(-6) : "Wallet not linked"}</b></div>
          {!me?.wallet_address && <div className="info-note">Connect and verify your Phantom wallet in Wallet before requesting a withdrawal.</div>}
          <input className="deposit-input" inputMode="decimal" value={withdrawAmount} onChange={e=>setWithdrawAmount(e.target.value)} placeholder="Amount of ZRL" disabled={withdrawBusy || !me?.wallet_address} />
          <button className="wallet-connect-btn" onClick={requestWithdrawal} disabled={withdrawBusy || !me?.wallet_address || !withdrawAmount.trim()}>{withdrawBusy ? "Processing…" : "Request withdrawal & send Telegram code"}</button>
          {withdrawId !== null && <div className="deposit-details">
            <b>Telegram confirmation</b>
            <p>Enter the 6-digit code sent by @Zer0lifeMining_bot. Code expires in 5 minutes.</p>
            <input className="deposit-input" inputMode="numeric" maxLength={6} value={withdrawCode} onChange={e=>setWithdrawCode(e.target.value.replace(/\\D/g,"").slice(0,6))} placeholder="6-digit Telegram code" />
            <button className="wallet-connect-btn" onClick={verifyWithdrawal} disabled={withdrawBusy || withdrawCode.length!==6}>Confirm withdrawal</button>
            <button className="wallet-connect-btn secondary-action" onClick={()=>cancelWithdrawal(withdrawId)} disabled={withdrawBusy}>Cancel and return ZRL</button>
          </div>}
          {withdrawMessage && <div className="wallet-success" role="status">{withdrawMessage}</div>}
          <div className="info-note">Security: requests are limited to your verified linked wallet. ZRL is reserved while confirmation is pending and returned if cancelled or expired. After code verification, payout remains pending review; on-chain transfers are currently disabled, so no tokens are sent automatically.</div>
          <h3>Withdrawal history</h3>
          {withdrawals.length===0 ? <p>No withdrawal requests yet.</p> : withdrawals.map((item:any)=><article className="reward-item" key={item.id}>
            <div><b>{fmt(item.amount_zrl)} ZRL · {item.status.replaceAll("_"," ")}</b><small>{dateLabel(item.created_at)}</small><small>{item.destination_wallet.slice(0,7)}…{item.destination_wallet.slice(-6)}</small></div>
            <div>{["awaiting_code","verified_pending"].includes(item.status) && <button className="wallet-connect-btn secondary-action" onClick={()=>cancelWithdrawal(item.id)} disabled={withdrawBusy}>Cancel</button>}</div>
          </article>)}
        </div>
        <div className="info-note">Only finalized transfers of the configured ZRL token to the shared Treasury are accepted. No Phantom connection or memo is required. Never send SOL or other tokens to this deposit flow.</div>
        <div className="detail-row"><span>On-chain payouts</span><b>Disabled until separately audited</b></div>
      </section>}

      {tab === "admin" && adminAvailable && <section className="content-card">
        <span className="eyebrow">RESTRICTED ACCESS</span><h2>Partner programme admin</h2>
        <div className="info-note">Read-only overview. Pending commission amounts are internal ledger records. Payouts are disabled.</div>
        <h3>Token allocation · 100,000,000 ZRL cap</h3>
        <div className="detail-row"><span>Total supply cap</span><b>{fmt(adminData?.supply_cap_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Mining / Farming / Partner rewards pool</span><b>{fmt(adminData?.rewards_allocation_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Rewards issued</span><b>{fmt(adminData?.issued_rewards_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Rewards pool remaining</span><b>{fmt(adminData?.rewards_remaining_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Future reserve</span><b>{fmt(adminData?.future_reserve_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Bonus allocation</span><b>{fmt(adminData?.bonus_allocation_zrl)} ZRL</b></div>
        <div className="info-note">{adminData?.allocation_config_valid ? "Allocation totals match the 100m ZRL cap." : "WARNING: configured allocation buckets do not add up to the total cap."} Partner commissions are included inside the rewards pool, not added on top. Pending commissions are a sub-ledger.</div>
        <div className="detail-row"><span>Total pending partner commissions (included above)</span><b>{fmt(adminData?.total_pending_zrl)} ZRL</b></div>
        <div className="detail-row"><span>Commission entries</span><b>{fmt(adminData?.commission_entries)}</b></div>
        <div className="detail-row"><span>Unique partners</span><b>{fmt(adminData?.unique_partners)}</b></div>
        <h3>By referral level</h3>
        {adminData?.by_level?.map((x:any)=><article className="reward-item" key={x.level}><div><b>Level {x.level} · {x.rate}</b><small>{x.entries} entries</small></div><strong>{fmt(x.pending_zrl)} ZRL</strong></article>)}
        <h3>Latest commission entries</h3>
        {adminData?.recent?.map((x:any,i:number)=><article className="reward-item" key={x.level+"-"+x.source_telegram_id+"-"+x.created_at+"-"+i}><div><b>Level {x.level} · user {x.beneficiary_telegram_id}</b><small>Source {x.source_telegram_id} · {dateLabel(x.created_at)}</small><small>Pending</small></div><strong>{fmt(x.amount_zrl)} ZRL</strong></article>)}
        <button className="wallet-connect-btn secondary-action" onClick={loadAdmin}>Refresh admin data</button>
      </section>}
      {tab === "profile" && <section className="content-card">
        <span className="eyebrow">YOUR ACCOUNT</span><h2>Profile</h2>
        <div className="profile-avatar">{avatarUrl ? <img src={avatarUrl} alt="Profile avatar" style={{width:"100%",height:"100%",objectFit:"cover",borderRadius:"50%"}} /> : (me?.username || "Z").slice(0, 1).toUpperCase()}</div>
        <label className="wallet-connect-btn avatar-upload-label">
          {avatarBusy ? "Uploading…" : avatarUrl ? "Change profile photo" : "Upload profile photo"}
          <input type="file" accept="image/jpeg,image/png,image/webp" style={{display:"none"}} disabled={avatarBusy} onChange={e => { uploadAvatar(e.target.files?.[0]); e.currentTarget.value = ""; }} />
        </label>
        {avatarUrl && <button className="wallet-connect-btn secondary-action" onClick={removeAvatar} disabled={avatarBusy}>Remove photo</button>}
        <small className="avatar-hint">JPG, PNG or WEBP · up to 2 MB</small>
        {avatarMessage && <div className="wallet-success" role="status">{avatarMessage}</div>}
        <h3>{me?.username ? "@" + me.username : "Zer0Life member"}</h3>
        <div className="detail-row"><span>Telegram account</span><b>{me?.username ? "Connected" : "Verified in Mini App"}</b></div>
        <div className="detail-row"><span>Internal balance</span><b>{busy ? "—" : fmt(me?.balance_zrl) + " ZRL"}</b></div>
        <div className="detail-row"><span>Wallet</span><b>{me?.wallet_address ? "Linked" : "Not linked"}</b></div>
      </section>}

      <footer>ZER0LIFE LABS <span>·</span> SOLANA <span>·</span> ZRL ECOSYSTEM</footer>

      <nav className={keyboardOpen ? "bottom-nav keyboard-hidden" : "bottom-nav"} aria-label="Main navigation">
        {tabs.filter(item => item.id !== "admin" || adminAvailable).map((item) => <button key={item.id} className={tab === item.id ? "nav-item active" : "nav-item"} onClick={() => setTab(item.id)}>
          <span className="nav-icon">{item.icon}</span><small>{item.label}</small>
        </button>)}
      </nav>
    </main>
  );
}

function Metric({ label, value, suffix, icon }: { label: string; value: string; suffix: string; icon: string }) {
  return <div className="metric-card"><div className="metric-head"><span>{label}</span><i>{icon}</i></div><strong>{value}<small>{suffix}</small></strong></div>;
}
