/**
 * Reusable metric card used in both the regular Dashboard and AdminDashboard.
 *
 * Props:
 *   label   — short description shown below the value
 *   value   — the headline number or string
 *   color   — accent colour for the value text (defaults to dark)
 *   sub     — optional smaller secondary line beneath the value
 */
export default function StatCard({ label, value, color = "#111827", sub }) {
  return (
    <div style={styles.card}>
      <span style={{ ...styles.value, color }}>{value}</span>
      {sub && <span style={styles.sub}>{sub}</span>}
      <span style={styles.label}>{label}</span>
    </div>
  );
}

const styles = {
  card: {
    background: "#fff",
    borderRadius: 12,
    padding: "20px 24px",
    flex: "1 1 140px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
  },
  value: {
    fontSize: 28,
    fontWeight: 700,
    lineHeight: 1.1,
  },
  sub: {
    fontSize: 12,
    color: "#9ca3af",
  },
  label: {
    fontSize: 13,
    color: "#6b7280",
    marginTop: 2,
  },
};
