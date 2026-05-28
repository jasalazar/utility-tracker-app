import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "./api";
import StatCard from "./components/StatCard";

export default function AdminDashboard({ user, onLogout }) {
  const [summary,  setSummary]  = useState(null);
  const [services, setServices] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [users,    setUsers]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const navigate = useNavigate();

  // Load all four datasets in parallel.
  useEffect(() => {
    Promise.all([
      api.adminSummary(),
      api.adminServices(),
      api.adminTimeline(),
      api.adminUsers(),
    ])
      .then(([s, sv, tl, u]) => {
        setSummary(s);
        setServices(sv || []);
        setTimeline(tl || []);
        setUsers(u || []);
      })
      .catch((err) => console.error("Admin data load failed", err))
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = async () => {
    await api.logout();
    onLogout();
    navigate("/");
  };

  if (loading) {
    return (
      <div style={styles.page}>
        <Header user={user} onLogout={handleLogout} />
        <main style={styles.main}>
          <p style={styles.muted}>Loading analytics…</p>
        </main>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <Header user={user} onLogout={handleLogout} />

      <main style={styles.main}>
        <h2 style={styles.heading}>Admin Dashboard</h2>
        <p style={styles.subheading}>Platform-wide analytics across all users.</p>

        {/* ── Summary stats ── */}
        {summary && (
          <div style={styles.statsRow}>
            <StatCard label="Total users"    value={summary.total_users}    color="#7c3aed" />
            <StatCard label="Total payments" value={summary.total_payments} color="#1a56db" />
            <StatCard
              label="Pending"
              value={`$${summary.total_pending_amount.toLocaleString()}`}
              color="#d97706"
              sub={`${summary.pending_count} payment${summary.pending_count !== 1 ? "s" : ""}`}
            />
            <StatCard
              label="Paid"
              value={`$${summary.total_paid_amount.toLocaleString()}`}
              color="#059669"
              sub={`${summary.paid_count} payment${summary.paid_count !== 1 ? "s" : ""}`}
            />
            <StatCard
              label="Overdue"
              value={`$${summary.total_overdue_amount.toLocaleString()}`}
              color="#dc2626"
              sub={`${summary.overdue_count} payment${summary.overdue_count !== 1 ? "s" : ""}`}
            />
          </div>
        )}

        <div style={styles.twoCol}>
          {/* ── Services breakdown ── */}
          <section style={styles.card}>
            <h3 style={styles.cardTitle}>Services Breakdown</h3>
            {services.length === 0 ? (
              <p style={styles.muted}>No data yet.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    {["Service", "Payments", "Total", "Avg", "Paid", "Pending", "Overdue"].map((h) => (
                      <th key={h} style={styles.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {services.map((s) => (
                    <tr key={s.service_name} style={styles.tr}>
                      <td style={{ ...styles.td, fontWeight: 600 }}>{s.service_name}</td>
                      <td style={styles.tdNum}>{s.count}</td>
                      <td style={styles.tdNum}>${s.total_amount.toLocaleString()}</td>
                      <td style={styles.tdNum}>${s.avg_amount.toLocaleString()}</td>
                      <td style={{ ...styles.tdNum, color: "#059669" }}>{s.paid_count}</td>
                      <td style={{ ...styles.tdNum, color: "#d97706" }}>{s.pending_count}</td>
                      <td style={{ ...styles.tdNum, color: "#dc2626" }}>{s.overdue_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* ── Timeline ── */}
          <section style={styles.card}>
            <h3 style={styles.cardTitle}>Monthly Volume (last 13 months)</h3>
            <TimelineChart data={timeline} />
          </section>
        </div>

        {/* ── Users table ── */}
        <section style={{ ...styles.card, marginTop: 20 }}>
          <h3 style={styles.cardTitle}>All Users</h3>
          {users.length === 0 ? (
            <p style={styles.muted}>No users yet.</p>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  {["Name", "Email", "Role", "Payments", "Pending", "Overdue", "Joined"].map((h) => (
                    <th key={h} style={styles.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.uid} style={styles.tr}>
                    <td style={{ ...styles.td, fontWeight: 500 }}>{u.name || "—"}</td>
                    <td style={styles.td}>{u.email}</td>
                    <td style={styles.td}>
                      <RoleBadge role={u.role} />
                    </td>
                    <td style={styles.tdNum}>{u.payment_count}</td>
                    <td style={{ ...styles.tdNum, color: "#d97706" }}>
                      {u.pending_amount > 0 ? `$${u.pending_amount.toLocaleString()}` : "—"}
                    </td>
                    <td style={{ ...styles.tdNum, color: u.overdue_count > 0 ? "#dc2626" : "#9ca3af" }}>
                      {u.overdue_count > 0 ? u.overdue_count : "—"}
                    </td>
                    <td style={styles.td}>
                      {u.created_at
                        ? new Date(parseInt(u.created_at) * 1000).toLocaleDateString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Header({ user, onLogout }) {
  return (
    <header style={styles.header}>
      <span style={styles.logo}>⚡ Utility Tracker</span>
      <nav style={styles.nav}>
        <Link to="/dashboard" style={styles.navLink}>My Dashboard</Link>
        <Link to="/settings"  style={styles.navLink}>Settings</Link>
        <span style={styles.adminBadge}>Admin</span>
        <button onClick={onLogout} style={styles.logoutBtn}>Sign out</button>
      </nav>
    </header>
  );
}

function RoleBadge({ role }) {
  const isAdmin = role === "admin";
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: 20,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        background: isAdmin ? "#f5f3ff" : "#f3f4f6",
        color:      isAdmin ? "#7c3aed"  : "#6b7280",
        border:     `1px solid ${isAdmin ? "#ddd6fe" : "#e5e7eb"}`,
      }}
    >
      {role}
    </span>
  );
}

/**
 * Minimal CSS bar chart — no external library required.
 * Bars are proportional to the maximum monthly total in the dataset.
 */
function TimelineChart({ data }) {
  if (!data || data.length === 0) {
    return <p style={styles.muted}>No data yet.</p>;
  }

  const max = Math.max(...data.map((d) => d.total_amount), 1);

  return (
    <div style={chartStyles.wrap}>
      {data.map((d) => {
        const heightPct = Math.max((d.total_amount / max) * 100, d.total_amount > 0 ? 4 : 0);
        return (
          <div key={d.month} style={chartStyles.col}>
            <span style={chartStyles.value}>
              {d.total_amount > 0 ? `$${d.total_amount.toLocaleString()}` : ""}
            </span>
            <div style={chartStyles.barWrap}>
              <div
                style={{ ...chartStyles.bar, height: `${heightPct}%` }}
                title={`${d.month}: $${d.total_amount} (${d.count} payments)`}
              />
            </div>
            <span style={chartStyles.label}>
              {/* Show only last 2 chars of month for brevity */}
              {d.month.slice(5)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  page:       { minHeight: "100vh", display: "flex", flexDirection: "column", background: "#f3f4f6" },
  header:     { background: "#fff", borderBottom: "1px solid #e5e7eb", padding: "0 24px", height: 56, display: "flex", alignItems: "center", justifyContent: "space-between" },
  logo:       { fontWeight: 700, fontSize: 18, color: "#1a56db" },
  nav:        { display: "flex", alignItems: "center", gap: 16 },
  navLink:    { color: "#374151", textDecoration: "none", fontSize: 14 },
  adminBadge: { background: "#f5f3ff", color: "#7c3aed", border: "1px solid #ddd6fe", borderRadius: 6, padding: "4px 10px", fontSize: 12, fontWeight: 600 },
  logoutBtn:  { background: "none", border: "1px solid #d1d5db", borderRadius: 6, padding: "6px 14px", fontSize: 13, cursor: "pointer", color: "#374151" },
  main:       { maxWidth: 1200, margin: "0 auto", padding: "32px 24px", width: "100%" },
  heading:    { fontSize: 22, fontWeight: 600, marginBottom: 4 },
  subheading: { color: "#6b7280", fontSize: 14, marginBottom: 28 },
  statsRow:   { display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" },
  twoCol:     { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, "@media(max-width:700px)": { gridTemplateColumns: "1fr" } },
  card:       { background: "#fff", borderRadius: 12, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.06)", overflow: "auto" },
  cardTitle:  { fontSize: 15, fontWeight: 600, marginBottom: 16 },
  table:      { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th:         { textAlign: "left", padding: "6px 10px", borderBottom: "2px solid #f3f4f6", color: "#6b7280", fontWeight: 600, whiteSpace: "nowrap" },
  td:         { padding: "9px 10px", borderBottom: "1px solid #f9fafb", color: "#111827" },
  tdNum:      { padding: "9px 10px", borderBottom: "1px solid #f9fafb", textAlign: "right", fontVariantNumeric: "tabular-nums" },
  tr:         { transition: "background 0.1s" },
  muted:      { color: "#9ca3af", fontSize: 14 },
};

const chartStyles = {
  wrap:    { display: "flex", alignItems: "flex-end", gap: 6, height: 160, paddingTop: 24, overflowX: "auto" },
  col:     { display: "flex", flexDirection: "column", alignItems: "center", flex: "1 0 28px", gap: 4 },
  barWrap: { width: "100%", height: 120, display: "flex", alignItems: "flex-end" },
  bar:     { width: "100%", background: "#1a56db", borderRadius: "3px 3px 0 0", transition: "height 0.3s", minHeight: 0 },
  value:   { fontSize: 9, color: "#9ca3af", whiteSpace: "nowrap", height: 14 },
  label:   { fontSize: 10, color: "#6b7280", marginTop: 4 },
};
