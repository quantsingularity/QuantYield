import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import api, { ApiError } from "@/lib/apiClient";

const AuthContext = createContext(null);

// Token storage helpers
function saveTokens(tokens) {
  localStorage.setItem("qy_tokens", JSON.stringify(tokens));
}
function clearTokens() {
  localStorage.removeItem("qy_tokens");
  localStorage.removeItem("qy_user");
}
function loadUser() {
  try {
    const s = localStorage.getItem("qy_user");
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Restore session from localStorage on first mount
  useEffect(() => {
    const stored = loadUser();
    if (stored) setUser(stored);
    setLoading(false);
  }, []);

  const login = useCallback(async (email, password) => {
    if (!email || !password)
      return { ok: false, error: "Email and password required" };
    try {
      // POST /api/v1/auth/token/  (djangorestframework-simplejwt)
      const tokens = await api.post("/auth/token/", { email, password });
      saveTokens(tokens);

      // Fetch the authenticated user's profile
      const userData = await api.get("/auth/me/");
      const normalized = {
        id: userData.id ?? userData.pk,
        name: userData.first_name
          ? `${userData.first_name} ${userData.last_name}`.trim()
          : userData.username,
        email: userData.email,
        role: userData.profile?.role ?? "Analyst",
        initials: (userData.first_name?.[0] ?? userData.email[0]).toUpperCase(),
        plan: userData.profile?.plan ?? "Pro",
      };
      setUser(normalized);
      localStorage.setItem("qy_user", JSON.stringify(normalized));
      return { ok: true };
    } catch (err) {
      clearTokens();
      if (err instanceof ApiError) {
        const msg =
          err.data?.detail ?? err.data?.non_field_errors?.[0] ?? "Login failed";
        return { ok: false, error: msg };
      }
      return { ok: false, error: "Network error - check your connection" };
    }
  }, []);

  const register = useCallback(
    async (data) => {
      if (!data.name || !data.email || !data.password)
        return { ok: false, error: "All fields required" };
      if (data.password.length < 8)
        return { ok: false, error: "Password must be at least 8 characters" };
      try {
        // POST /api/v1/auth/register/
        await api.post("/auth/register/", {
          username: data.email,
          email: data.email,
          password: data.password,
          first_name: data.name.split(" ")[0],
          last_name: data.name.split(" ").slice(1).join(" "),
        });
        // Log in immediately after registration
        return await login(data.email, data.password);
      } catch (err) {
        if (err instanceof ApiError) {
          const firstMsg =
            err.data?.email?.[0] ??
            err.data?.username?.[0] ??
            err.data?.password?.[0] ??
            err.data?.detail ??
            "Registration failed";
          return { ok: false, error: firstMsg };
        }
        return { ok: false, error: "Network error - check your connection" };
      }
    },
    [login],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
