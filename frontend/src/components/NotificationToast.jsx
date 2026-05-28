import { useEffect } from "react";

/**
 * Slide-in toast that appears when the server pushes a payment_reminder
 * event over the WebSocket. Auto-dismisses after 6 seconds.
 */
export default function NotificationToast({ message, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 6000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div style={styles.toast}>
      <div style={styles.iconWrap}>🔔</div>
      <div style={styles.content}>
        <p style={styles.title}>
          {message.type === "payment_added" ? "New payment detected" : "Payment Reminder"}
        </p>
        <p style={styles.body}>
          <strong>{message.service_name}</strong> — ${parseFloat(message.amount).toFixed(2)} due on {message.due_date}
        </p>
      </div>
      <button onClick={onClose} style={styles.close}>✕</button>
    </div>
  );
}

const styles = {
  toast: {
    position: "fixed",
    bottom: 24,
    right: 24,
    background: "#1e293b",
    color: "#f1f5f9",
    borderRadius: 12,
    padding: "14px 16px",
    display: "flex",
    alignItems: "flex-start",
    gap: 12,
    maxWidth: 340,
    boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
    animation: "slideIn 0.25s ease",
    zIndex: 9999,
  },
  iconWrap: { fontSize: 20, flexShrink: 0, paddingTop: 2 },
  content: { flex: 1, minWidth: 0 },
  title: { fontWeight: 600, fontSize: 14, marginBottom: 4 },
  body: { fontSize: 13, color: "#cbd5e1", lineHeight: 1.4 },
  close: {
    background: "none",
    border: "none",
    color: "#94a3b8",
    cursor: "pointer",
    fontSize: 14,
    padding: 0,
    flexShrink: 0,
  },
};
