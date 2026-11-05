import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  CircleHelp,
  Database,
  FileCheck2,
  Layers3,
  LayoutDashboard,
  LineChart,
  Menu,
  Plus,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { api } from "./api";
import { Loading } from "./components";
import { number } from "./format";
import Dashboard from "./pages/Dashboard";
import Quality from "./pages/Quality";
import ForecastPage from "./pages/ForecastPage";
import Comparison from "./pages/Comparison";
import Advanced from "./pages/Advanced";
import Inventory from "./pages/Inventory";
import type { Dataset, Forecast, Options, Page } from "./types";

const navigation = [
  { id: "dashboard" as Page, label: "Overview", icon: LayoutDashboard },
  { id: "quality" as Page, label: "Data quality", icon: ShieldCheck },
  { id: "forecast" as Page, label: "Demand forecast", icon: LineChart },
  { id: "comparison" as Page, label: "Model comparison", icon: Layers3 },
  { id: "advanced" as Page, label: "Advanced forecasting", icon: Activity },
  { id: "inventory" as Page, label: "Inventory optimization", icon: Layers3 },
];

export default function App() {
  const [page, setPage] = useState<Page>("welcome");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [mapping, setMapping] = useState({
    date_column: "date",
    target_column: "units_sold",
    store_column: "store_id",
    product_column: "product_id",
    price_column: "price",
    external_features: "",
    frequency: "auto",
  });

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams(window.location.search);
    const saved =
      query.get("dataset") ?? localStorage.getItem("forecastiq.dataset");
    if (!saved) {
      setRestoring(false);
      return;
    }
    Promise.all([
      api<Dataset>(`/datasets/${saved}`, { signal: controller.signal }),
      api<Options>(`/datasets/${saved}/options`, { signal: controller.signal }),
    ])
      .then(([data, opts]) => {
        setDataset(data);
        setOptions(opts);
        setPage(query.get("view") === "inventory" ? "inventory" : "dashboard");
        localStorage.setItem("forecastiq.dataset", data.dataset_id);
      })
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          localStorage.removeItem("forecastiq.dataset");
          setError(err.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setRestoring(false);
      });
    return () => controller.abort();
  }, []);

  async function loadData(file?: File) {
    setBusy(true);
    setError("");
    try {
      let body: FormData | undefined;
      if (file) {
        body = new FormData();
        body.append("file", file);
        Object.entries(mapping).forEach(([key, value]) =>
          body!.append(key, value),
        );
      }
      const data = await api<Dataset>(
        file ? "/datasets/upload" : "/datasets/demo",
        { method: "POST", body },
      );
      const opts = await api<Options>(`/datasets/${data.dataset_id}/options`);
      setDataset(data);
      setOptions(opts);
      window.history.replaceState(null, "", window.location.pathname);
      setForecast(null);
      setPage("quality");
      localStorage.setItem("forecastiq.dataset", data.dataset_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not load the dataset.";
      setError(file ? `${file.name}: ${message}` : message);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  const navigate = (next: Page) => {
    setPage(next);
    setMobileNav(false);
    setError("");
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <button
          className="brand"
          onClick={() => navigate(dataset ? "dashboard" : "welcome")}
          aria-label="ForecastIQ home"
        >
          <span className="brand-icon">
            <BarChart3 size={23} />
          </span>
          <span>
            Forecast<span className="brand-iq">IQ</span>
          </span>
        </button>
        <div className="workspace-label">
          YOUR WORKSPACE <span>01</span>
        </div>
        <nav aria-label="Main navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              disabled={!dataset || busy}
              className={`nav-item ${page === id ? "active" : ""}`}
              onClick={() => navigate(id)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {page === id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-data">
          <div className="sidebar-caption">
            <Database size={15} /> CONNECTED DATA
          </div>
          {dataset ? (
            <>
              <strong>
                {dataset.is_demo ? "Retail demo dataset" : dataset.filename}
              </strong>
              <small>
                <span className="status-dot" />{" "}
                {number(dataset.processed_row_count)} observations
              </small>
              <button onClick={() => navigate("welcome")} disabled={busy}>
                <Plus size={14} /> Change dataset
              </button>
            </>
          ) : (
            <>
              <strong>Your insights start here.</strong>
              <small>Connect your first sales dataset.</small>
            </>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="phase-badge">
            <Activity size={15} /> Phase 3 <span>INVENTORY</span>
          </div>
          <p>A clearer view of what’s next.</p>
          <div className="profile">
            <span className="avatar">FQ</span>
            <div>
              <strong>ForecastIQ workspace</strong>
              <small>Local development</small>
            </div>
          </div>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="nav-overlay"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              onClick={() => setMobileNav(!mobileNav)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {page === "welcome"
                ? "Get started"
                : navigation.find((item) => item.id === page)?.label}
            </strong>
          </div>
          <div className="topbar-right">
            {dataset && (
              <span className="dataset-pill">
                <span className="status-dot" />
                {dataset.is_demo ? "Synthetic demo data" : "Uploaded dataset"}
              </span>
            )}
            <a
              className="icon-button"
              href="/api/redoc"
              target="_blank"
              rel="noreferrer"
              aria-label="Open API documentation"
            >
              <CircleHelp size={19} />
            </a>
            <span className="top-avatar">FQ</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="alert error" role="alert">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={18} />
              </button>
            </div>
          )}
          {restoring ? (
            <Loading text="Opening your workspace…" />
          ) : page === "welcome" ? (
            <>
              <div className="welcome-intro">
                <span className="eyebrow">
                  <span className="status-dot" /> A LITTLE HISTORY. A CLEARER
                  FUTURE.
                </span>
                <h1>
                  Know your demand.
                  <br />
                  <span>Plan with perspective.</span>
                </h1>
                <p className="product-title">
                  ForecastIQ — Demand Forecasting &amp; Inventory Optimization
                  Platform
                </p>
                <p>
                  Turn everyday sales into a view of what comes next.
                  <br />
                  Explore your data, compare baselines, and build your first
                  forecast.
                </p>
              </div>
              <div className="welcome-cards">
                <button
                  className="start-card demo"
                  disabled={busy}
                  onClick={() => void loadData()}
                >
                  <div className="card-top">
                    <span className="large-icon">
                      <Database size={25} />
                    </span>
                    <span className="tag">READY TO EXPLORE</span>
                  </div>
                  <h2>Use Demo Dataset</h2>
                  <p>
                    A year in retail. Two stores, six products, and the patterns
                    behind their daily sales.
                  </p>
                  <div className="card-bottom">
                    <span>
                      {busy ? "Loading dataset…" : "Explore synthetic data"}
                    </span>
                    <ArrowRight size={20} />
                  </div>
                </button>
                <button
                  className="start-card"
                  disabled={busy}
                  onClick={() => fileInput.current?.click()}
                >
                  <div className="card-top">
                    <span className="large-icon">
                      <Upload size={25} />
                    </span>
                    <span className="tag neutral">
                      YOUR DATA, YOUR INSIGHTS
                    </span>
                  </div>
                  <h2>Upload CSV</h2>
                  <p>
                    Bring your historical retail sales. We’ll check the data
                    before you start forecasting. For Kaggle Store Item data,
                    choose train.csv.
                  </p>
                  <div className="card-bottom">
                    <span>Select a CSV file</span>
                    <ArrowRight size={20} />
                  </div>
                </button>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                className="visually-hidden"
                aria-label="Upload sales CSV"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void loadData(file);
                }}
              />
              {busy && (
                <Loading text="Reading observations and validating your dataset…" />
              )}
              <div className="schema-note">
                <FileCheck2 size={20} />
                <div>
                  <strong>A simple format to get started</strong>
                  <p>
                    Required: date and demand. Map your column names below;
                    store, product, price and additional numeric predictors are
                    optional.
                  </p>
                  <p>
                    Kaggle Store Item sales files with date, store, item and
                    sales columns are recognized automatically. Upload train.csv
                    using the default settings.
                  </p>
                  <small>
                    UTF-8 CSV · up to 25 MB · daily, weekly or monthly
                    observations. Advanced forecasting reports the history
                    needed for your chosen horizon.
                  </small>
                </div>
              </div>
              <details className="methodology csv-mapping">
                <summary>Column names and frequency for your CSV</summary>
                <p>
                  Keep the defaults for the example schema, or enter the names
                  used in your file before selecting Upload CSV. A sku_id column
                  is also recognized automatically, as are Kaggle Store Item
                  columns: date, store, item and sales.
                </p>
                <div className="advanced-controls">
                  {[
                    ["date_column", "Time column"],
                    ["target_column", "Demand / target column"],
                    ["store_column", "Store column"],
                    ["product_column", "Product / SKU column"],
                    ["price_column", "Price column (optional)"],
                    [
                      "external_features",
                      "Additional numeric predictors (comma-separated)",
                    ],
                  ].map(([key, label]) => (
                    <label key={key}>
                      <span>{label}</span>
                      <input
                        aria-label={label}
                        value={mapping[key as keyof typeof mapping]}
                        onChange={(e) =>
                          setMapping({ ...mapping, [key]: e.target.value })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    <span>Observation frequency</span>
                    <select
                      aria-label="Upload frequency"
                      value={mapping.frequency}
                      onChange={(e) =>
                        setMapping({ ...mapping, frequency: e.target.value })
                      }
                    >
                      <option value="auto">Detect from dates</option>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                    </select>
                  </label>
                </div>
                <p>
                  For a single series without store or product columns, enter{" "}
                  <code>__single__</code> in the corresponding field. Price is
                  optional. Monthly dates must use month starts or month ends.
                  Selected additional predictors must be numeric and available
                  at the forecast origin. Future values stay at the last
                  observed value; realized holdout values are never used to
                  forecast that holdout.
                </p>
              </details>
              <div className="welcome-proof">
                {[
                  "Chronological evaluation",
                  "Four transparent baselines",
                  "Measured model performance",
                ].map((text) => (
                  <span key={text}>
                    <Check size={15} />
                    {text}
                  </span>
                ))}
              </div>
            </>
          ) : dataset && options ? (
            <>
              {page === "quality" && (
                <Quality
                  dataset={dataset}
                  onContinue={() => navigate("dashboard")}
                />
              )}
              {page === "dashboard" && (
                <Dashboard
                  dataset={dataset}
                  options={options}
                  onForecast={() => navigate("forecast")}
                />
              )}
              {page === "forecast" && (
                <ForecastPage
                  key={dataset.dataset_id}
                  dataset={dataset}
                  options={options}
                  result={forecast}
                  setResult={setForecast}
                  onCompare={() => navigate("comparison")}
                />
              )}
              {page === "comparison" && (
                <Comparison
                  result={forecast}
                  onForecast={() => navigate("forecast")}
                />
              )}
              {page === "advanced" && (
                <Advanced
                  key={dataset.dataset_id}
                  dataset={dataset}
                  options={options}
                />
              )}
              {page === "inventory" && (
                <Inventory
                  key={dataset.dataset_id}
                  dataset={dataset}
                  onForecast={() => navigate("advanced")}
                />
              )}
            </>
          ) : null}
          <footer>
            <span>
              ForecastIQ <span className="footer-dot">/</span> Demand
              intelligence, grounded in data.
            </span>
            <span>PHASE 3 · INVENTORY OPTIMIZATION</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
