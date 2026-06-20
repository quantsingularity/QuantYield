import { useState, useMemo } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Search, Plus, ArrowUpDown, X } from "lucide-react";
import {
  bonds,
  fmt,
  ratingBadge,
  bondTypeBadge,
  chartColors,
} from "../../data/mockData";
import { useToast } from "../../context/ToastContext";

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: "#111927",
        border: "1px solid rgba(99,120,180,0.3)",
        borderRadius: 8,
        padding: "9px 12px",
        fontSize: 11,
      }}
    >
      <div
        style={{
          color: "#8898b8",
          marginBottom: 4,
          fontFamily: "var(--font-mono)",
        }}
      >
        {label}
      </div>
      {payload.map((p) => (
        <div
          key={p.name}
          style={{
            color: p.color || "#f0f4ff",
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
          }}
        >
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

const FREQ = { annual: 1, semiannual: 2, quarterly: 4, monthly: 12, zero: 0 };

function computeCashFlows(bond) {
  const m = FREQ[bond.coupon_frequency] || 2;
  if (m === 0) return [];
  const periods = Math.round(bond.years_to_maturity * m);
  const coupon = (bond.coupon_rate / m) * bond.face_value;
  const r = bond.ytm / m;
  const flows = [];
  for (let i = 1; i <= Math.min(periods, 14); i++) {
    const cf = i < periods ? coupon : coupon + bond.face_value;
    const pv = cf / Math.pow(1 + r, i);
    flows.push({ period: `P${i}`, CF: +cf.toFixed(2), PV: +pv.toFixed(2) });
  }
  return flows;
}

function BondDetail({ bond, onClose }) {
  const [tab, setTab] = useState("cf");
  const cashFlows = useMemo(() => computeCashFlows(bond), [bond]);
  const TABS = ["cf", "krd", "spreads", "return"];
  const LABELS = {
    cf: "Cash Flows",
    krd: "Key Rate Duration",
    spreads: "Spread Analytics",
    return: "Total Return",
  };

  const krdTenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30];
  const krdData = krdTenors.map((kt) => {
    const w = Math.exp(-Math.pow(kt - bond.duration * 0.8, 2) / 8);
    return {
      tenor: kt < 1 ? `${kt * 12}m` : `${kt}Y`,
      KRD: +(
        bond.modified_duration *
        0.09 *
        w *
        (0.85 + Math.random() * 0.3)
      ).toFixed(3),
    };
  });

  const [trForm, setTrForm] = useState({
    px: bond.clean_price.toFixed(3),
    horizon: 3,
    reinv: 4.0,
  });
  const [trResult, setTrResult] = useState(null);

  const calcTR = () => {
    const m = FREQ[bond.coupon_frequency] || 2;
    const coupon = (bond.coupon_rate / m) * bond.face_value;
    const horizon = parseFloat(trForm.horizon) || 3;
    const reinv = parseFloat(trForm.reinv) / 100 || 0.04;
    const periods = Math.round(horizon * m);
    let couponFV = 0;
    for (let i = 1; i <= periods; i++)
      couponFV += coupon * Math.pow(1 + reinv / m, (horizon - i / m) * m);
    const horizonPx = bond.dirty_price * 0.98;
    const totalRet = (horizonPx + couponFV) / parseFloat(trForm.px);
    const annRet = Math.pow(totalRet, 1 / horizon) - 1;
    setTrResult({
      couponFV: couponFV.toFixed(2),
      horizonPx: horizonPx.toFixed(3),
      annRet,
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexShrink: 0,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-head)",
              fontSize: 14,
              fontWeight: 700,
              color: "var(--text-primary)",
              marginBottom: 3,
            }}
          >
            {bond.name}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {bond.isin || "No ISIN"} · {bond.currency} · {bond.sector}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className={`badge ${ratingBadge(bond.credit_rating)}`}>
            {bond.credit_rating || "NR"}
          </span>
          <span className={`badge ${bondTypeBadge(bond.bond_type)}`}>
            {bond.bond_type.replace("_", " ")}
          </span>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Metrics */}
      <div style={{ flexShrink: 0, overflowX: "auto" }}>
        <div
          className="metric-strip"
          style={{
            borderRadius: 0,
            borderLeft: "none",
            borderRight: "none",
            borderTop: "none",
          }}
        >
          {[
            ["Dirty Px", fmt.px(bond.dirty_price)],
            ["Clean Px", fmt.px(bond.clean_price)],
            ["YTM", fmt.pct(bond.ytm), "var(--teal-400)"],
            ["Accrued", fmt.px(bond.accrued_interest)],
          ].map(([l, v, c]) => (
            <div key={l} className="metric-cell">
              <div className="metric-cell-label">{l}</div>
              <div
                className="metric-cell-value"
                style={{ color: c, fontSize: 15 }}
              >
                {v}
              </div>
            </div>
          ))}
        </div>
        <div
          className="metric-strip"
          style={{
            borderRadius: 0,
            borderLeft: "none",
            borderRight: "none",
            marginBottom: 0,
          }}
        >
          {[
            ["Macaulay", bond.duration.toFixed(2) + "Y"],
            ["Mod. Dur.", bond.modified_duration.toFixed(2)],
            ["Convexity", bond.convexity.toFixed(1)],
            ["DV01", bond.dv01.toFixed(1), "var(--amber)"],
            ["Maturity", bond.maturity_date.slice(0, 7)],
          ].map(([l, v, c]) => (
            <div key={l} className="metric-cell">
              <div className="metric-cell-label">{l}</div>
              <div
                className="metric-cell-value"
                style={{ color: c, fontSize: 15 }}
              >
                {v}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div
        className="tab-list"
        style={{ marginBottom: 0, paddingLeft: 16, flexShrink: 0 }}
      >
        {TABS.map((t) => (
          <button
            key={t}
            className={`tab-trigger ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {LABELS[t]}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "14px 16px" }}>
        {tab === "cf" && (
          <>
            <ResponsiveContainer width="100%" height={130}>
              <BarChart
                data={cashFlows}
                margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(99,120,180,0.12)"
                />
                <XAxis
                  dataKey="period"
                  tick={{
                    fill: "#4e6080",
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                  }}
                />
                <YAxis
                  tick={{
                    fill: "#4e6080",
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                  }}
                />
                <Tooltip content={<ChartTip />} />
                <Bar dataKey="CF" radius={[2, 2, 0, 0]}>
                  {cashFlows.map((_, i) => (
                    <Cell
                      key={i}
                      fill={
                        i < cashFlows.length - 1
                          ? chartColors.indigo
                          : chartColors.teal
                      }
                      fillOpacity={0.75}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ overflowX: "auto", marginTop: 10 }}>
              <table className="data-table" style={{ fontSize: 11.5 }}>
                <thead>
                  <tr>
                    <th>Period</th>
                    <th className="text-right">Cash Flow</th>
                    <th className="text-right">PV</th>
                  </tr>
                </thead>
                <tbody>
                  {cashFlows.map((r) => (
                    <tr key={r.period}>
                      <td className="mono">{r.period}</td>
                      <td className="text-right mono">${r.CF.toFixed(2)}</td>
                      <td
                        className="text-right mono"
                        style={{ color: "var(--teal-400)" }}
                      >
                        ${r.PV.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {tab === "krd" && (
          <>
            <div
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                marginBottom: 10,
              }}
            >
              Triangular bump — 1bp shift at each key tenor, all others fixed.
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={krdData}
                margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(99,120,180,0.12)"
                />
                <XAxis
                  dataKey="tenor"
                  tick={{
                    fill: "#4e6080",
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                  }}
                />
                <YAxis
                  tick={{
                    fill: "#4e6080",
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                  }}
                />
                <Tooltip content={<ChartTip />} />
                <Bar
                  dataKey="KRD"
                  fill={chartColors.indigo}
                  fillOpacity={0.75}
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}

        {tab === "spreads" && (
          <div className="stat-list">
            {[
              [
                "Z-Spread",
                (bond.ytm * 10000 - 431).toFixed(0) + " bp",
                "accent",
              ],
              [
                "OAS (Monte Carlo)",
                bond.bond_type === "callable"
                  ? Math.round(bond.ytm * 10000 - 420) + " bp"
                  : "= Z-Spread",
                "accent",
              ],
              ["Day Count", bond.day_count, ""],
              ["Issue Date", bond.issue_date, "muted"],
              ["Maturity Date", bond.maturity_date, "muted"],
              ["Face Value", "$" + bond.face_value.toLocaleString(), ""],
              ["Coupon Frequency", bond.coupon_frequency, ""],
            ].map(([k, v, c]) => (
              <div key={k} className="stat-row">
                <span className="stat-key">{k}</span>
                <span className={`stat-val ${c}`}>{v}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "return" && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: 10,
                marginBottom: 14,
              }}
            >
              {[
                ["Purchase Px", "px", "number", 0.001],
                ["Horizon (yrs)", "horizon", "number", 0.5],
                ["Reinv. Rate %", "reinv", "number", 0.1],
              ].map(([l, k, t, step]) => (
                <div key={k} className="form-group">
                  <label className="form-label">{l}</label>
                  <input
                    type={t}
                    className="form-control"
                    value={trForm[k]}
                    step={step}
                    onChange={(e) =>
                      setTrForm((f) => ({ ...f, [k]: e.target.value }))
                    }
                  />
                </div>
              ))}
            </div>
            <button className="btn btn-teal btn-sm" onClick={calcTR}>
              Calculate
            </button>
            {trResult && (
              <div
                style={{
                  marginTop: 14,
                  background: "var(--bg-overlay)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-lg)",
                  padding: 14,
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1fr",
                    gap: 10,
                  }}
                >
                  {[
                    [
                      "Reinv. Income",
                      "$" + trResult.couponFV,
                      "var(--teal-400)",
                    ],
                    [
                      "Horizon Price",
                      trResult.horizonPx,
                      "var(--text-primary)",
                    ],
                    [
                      "Ann. Return",
                      fmt.pct(trResult.annRet),
                      trResult.annRet >= 0 ? "var(--green)" : "var(--red)",
                    ],
                  ].map(([l, v, c]) => (
                    <div key={l} style={{ textAlign: "center" }}>
                      <div
                        style={{
                          fontSize: 9.5,
                          fontWeight: 600,
                          textTransform: "uppercase",
                          letterSpacing: "0.07em",
                          color: "var(--text-muted)",
                          marginBottom: 4,
                        }}
                      >
                        {l}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 18,
                          fontWeight: 700,
                          color: c,
                        }}
                      >
                        {v}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function Bonds() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [ratingFilter, setRatingFilter] = useState("");
  const [sortKey, setSortKey] = useState("issuer");
  const [sortDir, setSortDir] = useState(1);
  const [selected, setSelected] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const types = [...new Set(bonds.map((b) => b.bond_type))];
  const ratings = [
    ...new Set(bonds.map((b) => b.credit_rating).filter(Boolean)),
  ];

  const filtered = useMemo(() => {
    let b = bonds.filter((b) => {
      const s = search.toLowerCase();
      if (
        s &&
        !b.name.toLowerCase().includes(s) &&
        !b.issuer.toLowerCase().includes(s) &&
        !(b.isin || "").toLowerCase().includes(s)
      )
        return false;
      if (typeFilter && b.bond_type !== typeFilter) return false;
      if (ratingFilter && b.credit_rating !== ratingFilter) return false;
      return true;
    });
    b.sort((a, z) => {
      const av = a[sortKey] ?? "",
        zv = z[sortKey] ?? "";
      return (
        sortDir * (typeof av === "string" ? av.localeCompare(zv) : av - zv)
      );
    });
    return b;
  }, [search, typeFilter, ratingFilter, sortKey, sortDir]);

  const sort = (key) => {
    if (sortKey === key) setSortDir((d) => -d);
    else {
      setSortKey(key);
      setSortDir(1);
    }
  };

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {filtered.length} of {bonds.length} bonds · API: GET /api/v1/bonds/
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() =>
              toast("POST /api/v1/bonds/compare/ · Select 2–10 bonds", "info")
            }
          >
            Compare
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowAdd(true)}
          >
            <Plus size={13} /> Add Bond
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="search-field">
          <Search className="search-icon" size={14} />
          <input
            placeholder="Search bonds, ISIN, issuer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="form-control"
          style={{ width: 150 }}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          className="form-control"
          style={{ width: 130 }}
          value={ratingFilter}
          onChange={(e) => setRatingFilter(e.target.value)}
        >
          <option value="">All Ratings</option>
          {ratings.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        {(search || typeFilter || ratingFilter) && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setSearch("");
              setTypeFilter("");
              setRatingFilter("");
            }}
          >
            <X size={13} /> Clear
          </button>
        )}
      </div>

      {/* Layout: table + detail */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: selected ? "1fr 420px" : "1fr",
          gap: 16,
        }}
      >
        {/* Table */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  {[
                    ["name", "Bond"],
                    ["credit_rating", "Rating"],
                    ["bond_type", "Type"],
                    ["coupon_rate", "Coupon"],
                    ["ytm", "YTM"],
                    ["clean_price", "Clean Px"],
                    ["duration", "Dur"],
                    ["dv01", "DV01"],
                    ["maturity_date", "Maturity"],
                  ].map(([k, l]) => (
                    <th
                      key={k}
                      className="sortable"
                      onClick={() => sort(k)}
                      style={{ paddingRight: k === "name" ? 14 : undefined }}
                    >
                      {l}{" "}
                      {sortKey === k && (
                        <ArrowUpDown
                          size={10}
                          style={{ display: "inline", marginLeft: 3 }}
                        />
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((b) => (
                  <tr
                    key={b.id}
                    className={selected?.id === b.id ? "selected" : ""}
                    onClick={() =>
                      setSelected((s) => (s?.id === b.id ? null : b))
                    }
                  >
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 12.5 }}>
                        {b.issuer}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                        {+(b.coupon_rate * 100).toFixed(4)}% ·{" "}
                        {b.maturity_date.slice(0, 7)}
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${ratingBadge(b.credit_rating)}`}>
                        {b.credit_rating || "—"}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`badge ${bondTypeBadge(b.bond_type)}`}
                        style={{ fontSize: 9.5 }}
                      >
                        {b.bond_type.replace("_", " ")}
                      </span>
                    </td>
                    <td className="mono text-right">
                      {fmt.pct(b.coupon_rate)}
                    </td>
                    <td
                      className="mono text-right"
                      style={{ color: "var(--teal-400)" }}
                    >
                      {fmt.pct(b.ytm)}
                    </td>
                    <td className="mono text-right">{fmt.px(b.clean_price)}</td>
                    <td className="mono text-right">{b.duration.toFixed(2)}</td>
                    <td className="mono text-right">{b.dv01.toFixed(0)}</td>
                    <td
                      className="mono text-right"
                      style={{ color: "var(--text-muted)", fontSize: 11 }}
                    >
                      {b.maturity_date.slice(0, 7)}
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={9}>
                      <div className="empty-state">
                        <div className="empty-state-icon">
                          <Search size={36} />
                        </div>
                        <div className="empty-state-title">No bonds found</div>
                        <div className="empty-state-desc">
                          Try adjusting filters
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail panel */}
        {selected && (
          <div
            className="card"
            style={{
              padding: 0,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <BondDetail bond={selected} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>

      {/* Add Bond Modal */}
      {showAdd && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && setShowAdd(false)}
        >
          <div className="modal">
            <div className="modal-header">
              <span className="modal-title">Add New Bond</span>
              <button className="modal-close" onClick={() => setShowAdd(false)}>
                <X size={14} />
              </button>
            </div>
            <div className="modal-body">
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 12,
                  marginBottom: 12,
                }}
              >
                {[
                  ["Bond Name", "text", "e.g. Apple 5% 2034"],
                  ["Issuer", "text", "Apple Inc"],
                  ["ISIN", "text", "US037833XXXX"],
                  ["Face Value", "number", "1000"],
                ].map(([l, t, p]) => (
                  <div key={l} className="form-group">
                    <label className="form-label">{l}</label>
                    <input type={t} className="form-control" placeholder={p} />
                  </div>
                ))}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 12,
                  marginBottom: 12,
                }}
              >
                {[
                  ["Coupon Rate", "0.045", "0.001"],
                  ["Issue Date", "", ""],
                  ["Maturity Date", "", ""],
                ].map(([l, p, s], i) => (
                  <div key={l} className="form-group">
                    <label className="form-label">{l}</label>
                    <input
                      type={i === 0 ? "number" : "date"}
                      className="form-control"
                      placeholder={p}
                      step={s || undefined}
                    />
                  </div>
                ))}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                {[
                  ["Coupon Freq.", "semiannual,annual,quarterly,monthly,zero"],
                  [
                    "Bond Type",
                    "fixed,callable,floating,zero_coupon,inflation_linked",
                  ],
                  ["Day Count", "actual/actual,30/360,actual/360,actual/365"],
                ].map(([l, opts]) => (
                  <div key={l} className="form-group">
                    <label className="form-label">{l}</label>
                    <select className="form-control">
                      {opts.split(",").map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 12,
                  marginBottom: 20,
                }}
              >
                {[
                  ["Credit Rating", "AA+"],
                  ["Sector", "Technology"],
                  ["Currency", "USD"],
                ].map(([l, p]) => (
                  <div key={l} className="form-group">
                    <label className="form-label">{l}</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder={p}
                    />
                  </div>
                ))}
              </div>
              <div
                style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}
              >
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowAdd(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    toast("Bond created · POST /api/v1/bonds/", "success");
                    setShowAdd(false);
                  }}
                >
                  Create Bond
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
