/**
 * Typed API helpers.
 * All requests include credentials (cookies) so the HttpOnly session cookie
 * is forwarded automatically.
 */

const BASE = "";   // Same origin — FastAPI serves both API and SPA.

async function request(method, path, body) {
  const opts = {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : {},
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(BASE + path, opts);

  if (res.status === 401) {
    // Session expired or not authenticated.
    // Only redirect to the login page if we are NOT already there —
    // otherwise api.me() on first load triggers an infinite reload loop.
    if (window.location.pathname !== "/") {
      window.location.href = "/";
    }
    return null;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }

  if (res.status === 204) return null;
  return res.json();
}

// ---- Auth -------------------------------------------------------------------
export const api = {
  me: () => request("GET", "/auth/me"),
  logout: () => request("POST", "/auth/logout"),

  // ---- Payments -------------------------------------------------------------
  listPayments: () => request("GET", "/api/payments"),
  getPayment: (id) => request("GET", `/api/payments/${id}`),
  updateStatus: (id, status) => request("PATCH", `/api/payments/${id}/status`, { status }),
  deletePayment: (id) => request("DELETE", `/api/payments/${id}`),

  // ---- Rules ----------------------------------------------------------------
  getRules: () => request("GET", "/api/rules"),
  saveRules: (rules) => request("PUT", "/api/rules", { rules }),

  // ---- Web Push -------------------------------------------------------------
  getVapidKey: () => request("GET", "/api/push-key"),
  subscribePush: (subscription) => request("POST", "/api/push-subscribe", subscription),
  unsubscribePush: (subscription) => request("DELETE", "/api/push-subscribe", subscription),

  // ---- Admin analytics ------------------------------------------------------
  adminSummary:  () => request("GET", "/api/admin/summary"),
  adminServices: () => request("GET", "/api/admin/services"),
  adminTimeline: () => request("GET", "/api/admin/timeline"),
  adminUsers:    () => request("GET", "/api/admin/users"),
};

// ---- WebSocket --------------------------------------------------------------

/**
 * Open a WebSocket connection for real-time server-push events.
 * Returns a cleanup function that closes the socket.
 */
/**
 * Open a WebSocket connection with automatic reconnect on unexpected close.
 * Returns a cleanup function that permanently stops reconnection and closes
 * the socket (call it when the component unmounts).
 *
 * Backoff: 1s → 2s → 4s → … capped at 30s.
 */
export function openWebSocket(uid, onMessage) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${window.location.host}/ws/${uid}`;

  let ws = null;
  let stopped = false;
  let retryDelay = 1000;
  let retryTimer = null;

  function connect() {
    if (stopped) return;
    console.log("[WS] Connecting to", url);
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("[WS] Connected ✓");
      retryDelay = 1000; // reset backoff on successful connection
    };

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = (e) => console.error("[WS] Error", e);

    ws.onclose = (e) => {
      if (stopped) return;
      console.warn(`[WS] Closed (code ${e.code}) — reconnecting in ${retryDelay / 1000}s`);
      retryTimer = setTimeout(() => {
        retryDelay = Math.min(retryDelay * 2, 30000);
        connect();
      }, retryDelay);
    };
  }

  connect();

  return () => {
    stopped = true;
    clearTimeout(retryTimer);
    if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  };
}

// ---- Web Push registration --------------------------------------------------

export async function registerBrowserPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("Push notifications are not supported in this browser.");
  }

  const { publicKey } = await api.getVapidKey();

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const existing = await registration.pushManager.getSubscription();
  if (existing) return existing;

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: _urlBase64ToUint8Array(publicKey),
  });

  await api.subscribePush(subscription.toJSON());
  return subscription;
}

function _urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
