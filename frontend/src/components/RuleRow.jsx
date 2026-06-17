/**
 * A single editable notification rule row.
 *
 * Fields: days_before (0–90), hour (0–23), minute (0 | 30), channels (multi-select)
 */

const ALL_CHANNELS = [
  // { id: "email",     label: "Email" },   // disabled — re-enable with a system mailer (see backlog)
  { id: "macos",        label: "macOS" },
  { id: "browser_push", label: "Browser push" },
  { id: "ui_popup",     label: "UI popup" },
];

export default function RuleRow({ rule, onChange, onRemove }) {
  const toggleChannel = (channelId) => {
    const next = rule.channels.includes(channelId)
      ? rule.channels.filter((c) => c !== channelId)
      : [...rule.channels, channelId];
    // Always keep at least one channel.
    if (next.length > 0) onChange(rule.id, "channels", next);
  };

  const pad = (n) => String(n).padStart(2, "0");

  return (
    <div style={styles.row}>
      {/* Days before */}
      <label style={styles.fieldGroup}>
        <span style={styles.label}>Days before</span>
        <input
          type="number"
          min={0}
          max={90}
          value={rule.days_before}
          onChange={(e) => onChange(rule.id, "days_before", parseInt(e.target.value, 10) || 0)}
          style={styles.numInput}
        />
      </label>

      {/* Hour */}
      <label style={styles.fieldGroup}>
        <span style={styles.label}>Hour</span>
        <select
          value={rule.hour}
          onChange={(e) => onChange(rule.id, "hour", parseInt(e.target.value, 10))}
          style={styles.select}
        >
          {Array.from({ length: 24 }, (_, h) => (
            <option key={h} value={h}>{pad(h)}:00</option>
          ))}
        </select>
      </label>

      {/* Minute */}
      <label style={styles.fieldGroup}>
        <span style={styles.label}>Minute</span>
        <select
          value={rule.minute}
          onChange={(e) => onChange(rule.id, "minute", parseInt(e.target.value, 10))}
          style={styles.select}
        >
          {[0, 15, 30, 45].map((m) => (
            <option key={m} value={m}>{pad(m)}</option>
          ))}
        </select>
      </label>

      {/* Channels */}
      <div style={styles.fieldGroup}>
        <span style={styles.label}>Channels</span>
        <div style={styles.channelGroup}>
          {ALL_CHANNELS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => toggleChannel(id)}
              style={{
                ...styles.channelBtn,
                ...(rule.channels.includes(id) ? styles.channelBtnActive : {}),
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Remove */}
      <button
        type="button"
        onClick={() => onRemove(rule.id)}
        style={styles.removeBtn}
        title="Remove rule"
      >
        ✕
      </button>
    </div>
  );
}

const styles = {
  row: {
    display: "flex",
    alignItems: "flex-end",
    gap: 16,
    background: "#f9fafb",
    borderRadius: 8,
    padding: "14px 16px",
    flexWrap: "wrap",
  },
  fieldGroup: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  label: {
    fontSize: 11,
    fontWeight: 600,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  numInput: {
    width: 64,
    padding: "6px 8px",
    border: "1px solid #d1d5db",
    borderRadius: 6,
    fontSize: 14,
  },
  select: {
    padding: "6px 8px",
    border: "1px solid #d1d5db",
    borderRadius: 6,
    fontSize: 14,
    background: "#fff",
  },
  channelGroup: { display: "flex", gap: 6, flexWrap: "wrap" },
  channelBtn: {
    border: "1px solid #d1d5db",
    borderRadius: 6,
    padding: "5px 10px",
    fontSize: 12,
    cursor: "pointer",
    background: "#fff",
    color: "#374151",
    transition: "all 0.1s",
  },
  channelBtnActive: {
    background: "#1a56db",
    color: "#fff",
    borderColor: "#1a56db",
  },
  removeBtn: {
    background: "none",
    border: "none",
    color: "#9ca3af",
    fontSize: 16,
    cursor: "pointer",
    padding: "0 4px",
    marginBottom: 2,
    alignSelf: "flex-end",
  },
};
