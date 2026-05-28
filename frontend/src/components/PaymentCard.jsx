/**
 * A single payment record card.
 * Shows service name, amount, due date, status badge, and action controls.
 */

const STATUS_COLORS = {
  pending:  { bg: "#eff6ff", text: "#1a56db", border: "#bfdbfe" },
  paid:     { bg: "#f0fdf4", text: "#059669", border: "#bbf7d0" },
  overdue:  { bg: "#fef2f2", text: "#dc2626", border: "#fecaca" },
};

export default function PaymentCard({ payment, onStatusChange, onDelete }) {
  const { payment_id, service_name, amount, currency, due_date, status, email_subject } = payment;
  const colors = STATUS_COLORS[status] || STATUS_COLORS.pending;

  const isOverdue =
    status === "pending" && new Date(due_date) < new Date();

  const daysUntilDue = () => {
    const diff = Math.ceil((new Date(due_date) - new Date()) / (1000 * 60 * 60 * 24));
    if (diff < 0) return `${Math.abs(diff)}d overdue`;
    if (diff === 0) return "due today";
    return `in ${diff}d`;
  };

  return (
    <div style={{ ...styles.card, borderLeft: `4px solid ${colors.border}` }}>
      {/* Left: service info */}
      <div style={styles.body}>
        <div style={styles.top}>
          <span style={styles.service}>{service_name}</span>
          <span
            style={{
              ...styles.badge,
              background: colors.bg,
              color: colors.text,
              border: `1px solid ${colors.border}`,
            }}
          >
            {isOverdue ? "overdue" : status}
          </span>
        </div>

        <div style={styles.meta}>
          <span style={styles.amount}>
            {currency} {parseFloat(amount).toFixed(2)}
          </span>
          <span style={styles.dot}>·</span>
          <span style={styles.dueDate}>
            Due {due_date}
          </span>
          <span style={styles.dot}>·</span>
          <span style={{ color: isOverdue ? "#dc2626" : "#6b7280", fontSize: 13 }}>
            {daysUntilDue()}
          </span>
        </div>

        {email_subject && (
          <p style={styles.subject} title={email_subject}>
            {email_subject.length > 70 ? email_subject.slice(0, 70) + "…" : email_subject}
          </p>
        )}
      </div>

      {/* Right: actions */}
      <div style={styles.actions}>
        {status !== "paid" && (
          <button
            style={{ ...styles.actionBtn, background: "#f0fdf4", color: "#059669" }}
            onClick={() => onStatusChange(payment_id, "paid")}
          >
            Mark paid
          </button>
        )}
        {status === "paid" && (
          <button
            style={{ ...styles.actionBtn, background: "#eff6ff", color: "#1a56db" }}
            onClick={() => onStatusChange(payment_id, "pending")}
          >
            Unmark
          </button>
        )}
        <button
          style={{ ...styles.actionBtn, background: "#fef2f2", color: "#dc2626" }}
          onClick={() => {
            if (window.confirm(`Delete ${service_name} payment?`)) onDelete(payment_id);
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

const styles = {
  card: {
    background: "#fff",
    borderRadius: 10,
    padding: "16px 20px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
    gap: 16,
    flexWrap: "wrap",
  },
  body: { flex: 1, minWidth: 0 },
  top: { display: "flex", alignItems: "center", gap: 10, marginBottom: 6 },
  service: { fontWeight: 600, fontSize: 16 },
  badge: {
    fontSize: 11,
    fontWeight: 600,
    padding: "2px 8px",
    borderRadius: 20,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  meta: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  amount: { fontSize: 15, fontWeight: 600, color: "#111827" },
  dueDate: { fontSize: 13, color: "#6b7280" },
  dot: { color: "#d1d5db" },
  subject: { fontSize: 12, color: "#9ca3af", marginTop: 6, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  actions: { display: "flex", gap: 8, flexShrink: 0 },
  actionBtn: {
    border: "none",
    borderRadius: 6,
    padding: "7px 14px",
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  },
};
