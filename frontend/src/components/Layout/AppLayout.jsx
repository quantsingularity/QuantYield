import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  FileText,
  Briefcase,
  TrendingUp,
  BarChart3,
  Brain,
  LogOut,
  Settings,
  Bell,
  RefreshCw,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";

const NAV = [
  {
    section: "Platform",
    items: [
      {
        to: "/app/dashboard",
        icon: LayoutDashboard,
        label: "Dashboard",
        badge: null,
      },
      { to: "/app/bonds", icon: FileText, label: "Bond Universe", badge: "12" },
      {
        to: "/app/portfolios",
        icon: Briefcase,
        label: "Portfolios",
        badge: "3",
      },
    ],
  },
  {
    section: "Market Data",
    items: [
      {
        to: "/app/curves",
        icon: TrendingUp,
        label: "Yield Curves",
        badge: null,
      },
      {
        to: "/app/analytics",
        icon: BarChart3,
        label: "Analytics",
        badge: null,
      },
    ],
  },
  {
    section: "AI / ML",
    items: [
      {
        to: "/app/ml",
        icon: Brain,
        label: "ML Models",
        badge: "5",
        badgeAccent: true,
      },
    ],
  },
];

const TICKERS = [
  { label: "10Y", value: "4.312%", delta: "+0.04", dir: "up" },
  { label: "2Y", value: "4.798%", delta: "-0.02", dir: "down" },
  { label: "2s10s", value: "-48bp", delta: "INV", dir: "down" },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const PAGE_TITLES = {
    "/app/dashboard": "Dashboard",
    "/app/bonds": "Bond Universe",
    "/app/portfolios": "Portfolios",
    "/app/curves": "Yield Curves",
    "/app/analytics": "Analytics",
    "/app/ml": "ML Models",
  };
  const pageTitle = PAGE_TITLES[location.pathname] ?? "";
  const [time, setTime] = useState("");
  const [showUserMenu, setShowUserMenu] = useState(false);

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setTime(
        [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()]
          .map((n) => String(n).padStart(2, "0"))
          .join(":") + " UTC",
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
    toast("Signed out successfully", "info");
  };

  const handleRefresh = () =>
    toast("Market data refreshed from FRED", "success");

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">
            <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
              <path
                d="M6 24L12 10L18 17L23 7"
                stroke="white"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="23" cy="7" r="3" fill="#14b8a6" />
            </svg>
          </div>
          <div className="sidebar-logo-text">
            <div className="sidebar-logo-name">QuantYield</div>
            <div className="sidebar-logo-sub">Analytics Platform</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="sidebar-nav">
          {NAV.map((section) => (
            <div key={section.section} className="nav-group">
              <div className="nav-group-label">{section.section}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? "active" : ""}`
                  }
                >
                  <item.icon className="nav-link-icon" size={16} />
                  <span>{item.label}</span>
                  {item.badge && (
                    <span
                      className={`nav-link-badge ${item.badgeAccent ? "accent" : ""}`}
                    >
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-indicator online" />
            <span className="status-label">FRED live feed</span>
          </div>
          <div className="sidebar-status">
            <span className="status-indicator online" />
            <span className="status-label">API v1 · :8000</span>
          </div>

          {/* User menu */}
          <div style={{ position: "relative" }}>
            <div
              className="sidebar-user"
              onClick={() => setShowUserMenu((m) => !m)}
            >
              <div className="sidebar-avatar">{user?.initials || "QY"}</div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">{user?.name || "User"}</div>
                <div className="sidebar-user-role">
                  {user?.role || "Analyst"}
                </div>
              </div>
              <ChevronDown
                size={13}
                style={{
                  color: "var(--text-muted)",
                  marginLeft: "auto",
                  flexShrink: 0,
                }}
              />
            </div>
            {showUserMenu && (
              <div
                style={{
                  position: "absolute",
                  bottom: "100%",
                  left: 0,
                  right: 0,
                  marginBottom: 4,
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--r-lg)",
                  padding: 6,
                  boxShadow: "var(--shadow-lg)",
                  zIndex: 999,
                }}
              >
                <button
                  onClick={() => {
                    setShowUserMenu(false);
                    toast("Settings coming soon", "info");
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: "var(--r-md)",
                    fontSize: 13,
                    color: "var(--text-secondary)",
                    transition: "background 0.1s",
                  }}
                  className="sidebar-user"
                >
                  <Settings size={14} /> Settings
                </button>
                <button
                  onClick={() => {
                    setShowUserMenu(false);
                    handleLogout();
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: "var(--r-md)",
                    fontSize: 13,
                    color: "var(--red)",
                    transition: "background 0.1s",
                  }}
                  className="sidebar-user"
                >
                  <LogOut size={14} /> Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="app-main">
        {/* Topbar */}
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-title" id="page-title">
              {pageTitle}
            </div>
          </div>

          <div className="topbar-right">
            <div className="ticker-bar">
              {TICKERS.map((t, i) => (
                <div
                  key={t.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: i > 0 ? 14 : 0,
                  }}
                >
                  {i > 0 && <span className="ticker-sep">|</span>}
                  <div className="ticker-item">
                    <span className="ticker-label">{t.label}</span>
                    <span className="ticker-value">{t.value}</span>
                    <span className={`ticker-delta ${t.dir}`}>{t.delta}</span>
                  </div>
                </div>
              ))}
            </div>

            <button
              className="btn btn-ghost btn-sm"
              onClick={handleRefresh}
              style={{ gap: 6 }}
            >
              <RefreshCw size={13} />
              Refresh
            </button>

            <button
              className="btn btn-ghost btn-icon"
              onClick={() => toast("No new notifications", "info")}
            >
              <Bell size={16} />
            </button>

            <div className="topbar-clock">{time}</div>
          </div>
        </header>

        {/* Page content rendered by child routes */}
        <div className="page-body">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
