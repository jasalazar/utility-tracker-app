/**
 * Login page — single "Sign in with Google" button.
 * Redirects to FastAPI's /auth/login which starts the OAuth flow.
 */
export default function Login() {
  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>⚡ Utility Tracker</h1>
        <p style={styles.subtitle}>
          Monitor your household utility payments automatically.
        </p>
        <a href="/auth/login" style={styles.button}>
          <GoogleIcon />
          Sign in with Google
        </a>
        <p style={styles.note}>
          We request read access to your Gmail inbox to detect utility payment
          emails. Your credentials are stored securely and never shared.
        </p>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" style={{ marginRight: 10 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71C3.784 10.17 3.682 9.593 3.682 9s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/>
    </svg>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)",
  },
  card: {
    background: "#fff",
    borderRadius: 16,
    padding: "48px 40px",
    maxWidth: 420,
    width: "90%",
    boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
    textAlign: "center",
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    color: "#1a56db",
    marginBottom: 8,
  },
  subtitle: {
    color: "#6b7280",
    fontSize: 15,
    marginBottom: 32,
    lineHeight: 1.5,
  },
  button: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#fff",
    border: "1px solid #d1d5db",
    borderRadius: 8,
    padding: "12px 24px",
    fontSize: 15,
    fontWeight: 500,
    color: "#111827",
    textDecoration: "none",
    cursor: "pointer",
    transition: "box-shadow 0.15s",
    width: "100%",
    marginBottom: 24,
  },
  note: {
    fontSize: 12,
    color: "#9ca3af",
    lineHeight: 1.6,
  },
};
