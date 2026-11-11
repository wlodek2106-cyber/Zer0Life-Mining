/// <reference types="vite/client" />
interface ImportMetaEnv { readonly VITE_API_URL?: string; }
interface ImportMeta { readonly env: ImportMetaEnv; }
interface Window {
  Telegram?: {
    WebApp?: {
      initData?: string;
      ready: () => void;
      expand: () => void;
    };
  };
}

interface Window {
  phantom?: {
    solana?: {
      connect: () => Promise<{ publicKey: { toString: () => string } }>;
      signMessage: (message: Uint8Array, display?: "utf8" | "hex") => Promise<{ signature: Uint8Array; publicKey: { toString: () => string } }>;
    };
  };
}
