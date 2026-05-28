import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, openWebSocket } from "./api";
import PaymentCard from "./components/PaymentCard";
import NotificationToast from "./components/NotificationToast";

export default function Dashboard({ user, onLogout }) {
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const navigate = useNavigate();

  // ---- Load payments -------------------------------------------------------
  const loadPayments = useCallback(async () => {
    try {
      const data = await api.listPayments();
      setPayments(data || []);
    } catch (err) {
      console.error("Failed to load payments", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPayments(); }, [loadPayments]);

  // ---- WebSocket (real-time updates) ---------------------------------------
  useEffect(() => {
    if (!user?.uid) return;
    const cleanup = openWebSocket(user.uid, (msg) => {
      if (msg.type === "payment_added") {
        // A new payment was just extracted from an incoming email — refresh the list.
        loadPayments();
        setToast(msg);
      } else if (msg.type === "payment_reminder") {
        setToast(msg);
        // Also refresh the list to pick up status changes.
        loadPayments();
      }
    });
    return cleanup;
  }, [user?.uid, loadPayments]);

  // ---- Actions -------------------------------------------------------------
  const handleStatusChange = async (paymentId, status) => {
    await api.updateStatus(paymentId, status);
    setPayments((prev) =>
      prev.map((p) => (p.payment_id === paymentId ? { ...p, status } : p))
    );
  };

  const handleDelete = async (paymentId) => {
    await api.deletePayment(paymentId);
    setPayments((prev) => prev.filter((p) => p.payment_id !== paymentId));
  };

  const handleLogout = async () => {
    await api.logout();
    onLogout();
    navigate("/");
  };

  // ---- Stats ---------------------------------------------------------------
  const now = new Date();
  const upcoming = payments.filter(
    (p) => p.status === "pending" && new Date(p.due_date) > now
  );
  const overdue = payments.filter(
    (p) => p.status === "pending" && new Date(p.due_date) <= now
  );
  const totalDue = payments
    .filter((p) => p.status === "pending")
    .reduce((sum, p) => sum + parseFloat(p.amount || 0), 0)
    .toFixed(2);

  return (
    <div style={styles.page}>
      {/* Header */}
      <header style={styles.header}>
        <span style={styles.logo}>⚡ Utility Tracker</span>
        <nav style={styles.nav}>
          <Link to="/settings" style={styles.navLink}>Settings</Link>
          {user?.role === "admin" && (
            <Link to="/admin" style={{ ...styles.navLink, color: "#7c3aed", fontWeight: 600 }}>
              Admin
            </Link>
          )}
          <button onClick={handleLogout} style={styles.logoutBtn}>
            Sign out
          </button>
        </nav>
      </header>

      <main style={styles.main}>
        <h2 style={styles.greeting}>Hello, {user?.name?.split(" ")[0]} 👋</h2>

        {/* Summary strip */}
        <div style={styles.statsRow}>
          <Stat label="Upcoming payments" value={upcoming.length} color="#1a56db" />
          <Stat label="Overdue" value={overdue.length} color="#dc2626" />
          <Stat label="Total due" value={`$${totalDue}`} color="#059669" />
        </div>

        {/* Payment list */}
        {loading ? (
          <p style={styles.empty}>Loading payments…</p>
        ) : payments.length === 0 ? (
          <p style={styles.empty}>
            No payments tracked yet. They will appear here automatically when
            utility emails arrive in your inbox.
          </p>
        ) : (
          <div style={styles.grid}>
            {payments.map((p) => (
              <PaymentCard
                key={p.payment_id}
                payment={p}
                onStatusChange={handleStatusChange}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>

      {/* Real-time notification toast */}
      {toast && (
        <NotificationToast
          message={toast}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.stat}>
      <span style={{ ...styles.statValue, color }}>{value}</span>
      <span style={styles.statLabel}>{label}</span>
    </div>
  );
}

const styles = {
  page: { minHeight: "100vh", display: "flex", flexDirection: "column" },
  header: {
    background: "#fff",
    borderBottom: "1px solid #e5e7eb",
    padding: "0 24px",
    height: 56,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  logo: { fontWeight: 700, fontSize: 18, color: "#1a56db" },
  nav: { display: "flex", alignItems: "center", gap: 16 },
  navLink: { color: "#374151", textDecoration: "none", fontSize: 14 },
  logoutBtn: {
    background: "none",
    border: "1px solid #d1d5db",
    borderRadius: 6,
    padding: "6px 14px",
    fontSize: 13,
    cursor: "pointer",
    color: "#374151",
  },
  main: { maxWidth: 960, margin: "0 auto", padding: "32px 24px", width: "100%" },
  greeting: { fontSize: 22, fontWeight: 600, marginBottom: 24 },
  statsRow: {
    display: "flex",
    gap: 16,
    marginBottom: 32,
    flexWrap: "wrap",
  },
  stat: {
    background: "#fff",
    borderRadius: 12,
    padding: "20px 28px",
    flex: "1 1 140px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
  },
  statValue: { fontSize: 28, fontWeight: 700 },
  statLabel: { fontSize: 13, color: "#6b7280" },
  grid: { display: "flex", flexDirection: "column", gap: 12 },
  empty: { color: "#9ca3af", textAlign: "center", marginTop: 60, fontSize: 15 },
};
