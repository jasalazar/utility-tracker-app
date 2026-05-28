import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./Login";
import Dashboard from "./Dashboard";
import Settings from "./Settings";
import AdminDashboard from "./AdminDashboard";
import { api } from "./api";

/**
 * Root component.
 * Resolves auth state once on mount, then guards routes accordingly.
 */
export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then((data) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={styles.center}>
        <p style={{ color: "#6b7280" }}>Loading…</p>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={user ? <Navigate to="/dashboard" replace /> : <Login />}
        />
        <Route
          path="/dashboard"
          element={user ? <Dashboard user={user} onLogout={() => setUser(null)} /> : <Navigate to="/" replace />}
        />
        <Route
          path="/settings"
          element={user ? <Settings user={user} onLogout={() => setUser(null)} /> : <Navigate to="/" replace />}
        />
        <Route
          path="/admin"
          element={
            user
              ? user.role === "admin"
                ? <AdminDashboard user={user} onLogout={() => setUser(null)} />
                : <Navigate to="/dashboard" replace />
              : <Navigate to="/" replace />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

const styles = {
  center: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100vh",
  },
};
