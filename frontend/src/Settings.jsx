import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, registerBrowserPush } from "./api";
import RuleRow from "./components/RuleRow";

const EMPTY_RULE = () => ({
  id: crypto.randomUUID(),
  days_before: 7,
  hour: 9,
  minute: 0,
  channels: ["browser_push"],
});

export default function Settings({ user, onLogout }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pushStatus, setPushStatus] = useState("idle"); // idle | subscribing | done | error
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.getRules().then(({ rules }) => {
      setRules(rules.length ? rules : [EMPTY_RULE()]);
      setLoading(false);
    });
  }, []);

  const addRule = () => setRules((prev) => [...prev, EMPTY_RULE()]);

  const updateRule = (id, field, value) => {
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))
    );
  };

  const removeRule = (id) => {
    setRules((prev) => prev.filter((r) => r.id !== id));
  };

  const saveRules = async () => {
    setSaving(true);
    try {
      await api.saveRules(rules);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      alert("Failed to save rules: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleEnablePush = async () => {
    setPushStatus("subscribing");
    try {
      await registerBrowserPush();
      setPushStatus("done");
    } catch (err) {
      console.error(err);
      setPushStatus("error");
    }
  };

  const handleLogout = async () => {
    await api.logout();
    onLogout();
    navigate("/");
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <span style={styles.logo}>⚡ Utility Tracker</span>
        <nav style={styles.nav}>
          <Link to="/dashboard" style={styles.navLink}>Dashboard</Link>
          {user?.role === "admin" && (
            <Link to="/admin" style={{ ...styles.navLink, color: "#7c3aed", fontWeight: 600 }}>
              Admin
            </Link>
          )}
          <button onClick={handleLogout} style={styles.logoutBtn}>Sign out</button>
        </nav>
      </header>

      <main style={styles.main}>
        <h2 style={styles.heading}>Notification Settings</h2>
        <p style={styles.subheading}>
          Define when and how you want to be reminded about upcoming payments.
          Rules are applied to every new payment detected in your inbox.
        </p>

        {/* Browser push */}
        <section style={styles.section}>
          <h3 style={styles.sectionTitle}>Browser &amp; macOS Push</h3>
          <p style={styles.sectionDesc}>
            Enable push notifications so reminders arrive even when this tab is closed.
            The macOS notifier daemon uses the same subscription.
          </p>
          <button
            onClick={handleEnablePush}
            disabled={pushStatus === "subscribing" || pushStatus === "done"}
            style={styles.pushBtn}
          >
            {pushStatus === "idle" && "Enable Push Notifications"}
            {pushStatus === "subscribing" && "Subscribing…"}
            {pushStatus === "done" && "✓ Push notifications enabled"}
            {pushStatus === "error" && "Failed — try again"}
          </button>
        </section>

        {/* Rules */}
        <section style={styles.section}>
          <div style={styles.rulesHeader}>
            <h3 style={styles.sectionTitle}>Reminder Rules</h3>
            <button onClick={addRule} style={styles.addBtn}>+ Add rule</button>
          </div>

          {loading ? (
            <p style={{ color: "#9ca3af" }}>Loading…</p>
          ) : (
            <div style={styles.ruleList}>
              {rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  onChange={updateRule}
                  onRemove={removeRule}
                />
              ))}
            </div>
          )}

          <div style={styles.saveRow}>
            <button onClick={saveRules} disabled={saving} style={styles.saveBtn}>
              {saving ? "Saving…" : "Save rules"}
            </button>
            {saved && <span style={styles.savedBadge}>✓ Saved</span>}
          </div>
        </section>
      </main>
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
  main: { maxWidth: 720, margin: "0 auto", padding: "32px 24px", width: "100%" },
  heading: { fontSize: 22, fontWeight: 600, marginBottom: 8 },
  subheading: { color: "#6b7280", fontSize: 14, marginBottom: 32, lineHeight: 1.6 },
  section: {
    background: "#fff",
    borderRadius: 12,
    padding: 24,
    marginBottom: 20,
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
  },
  sectionTitle: { fontSize: 16, fontWeight: 600, marginBottom: 8 },
  sectionDesc: { fontSize: 13, color: "#6b7280", marginBottom: 16, lineHeight: 1.6 },
  pushBtn: {
    background: "#1a56db",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "10px 20px",
    fontSize: 14,
    cursor: "pointer",
    opacity: 1,
  },
  rulesHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
  },
  addBtn: {
    background: "#f3f4f6",
    border: "none",
    borderRadius: 6,
    padding: "7px 14px",
    fontSize: 13,
    cursor: "pointer",
    color: "#374151",
  },
  ruleList: { display: "flex", flexDirection: "column", gap: 10 },
  saveRow: { display: "flex", alignItems: "center", gap: 12, marginTop: 20 },
  saveBtn: {
    background: "#059669",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "10px 24px",
    fontSize: 14,
    cursor: "pointer",
  },
  savedBadge: { color: "#059669", fontSize: 14, fontWeight: 500 },
};
