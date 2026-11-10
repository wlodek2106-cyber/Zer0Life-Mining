import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";
declare global { interface Window { Telegram?: { WebApp?: { ready: () => void; expand: () => void; initData: string } } } }
window.Telegram?.WebApp?.ready();
window.Telegram?.WebApp?.expand();
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
