import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  Info,
  ShieldCheck,
} from "lucide-react";
import { PageHeader, Panel, Stat, StatusBadge } from "../components";
import { date, number } from "../format";
import type { Dataset } from "../types";

export default function Quality({
  dataset: d,
  onContinue,
}: {
  dataset: Dataset;
  onContinue: () => void;
}) {
  const warned = d.validation_status === "PASS_WITH_WARNINGS";
  return (
    <>
      <PageHeader
        eyebrow="Start with a strong foundation"
        title="Data quality report"
        description="Review validation results, coverage, and data readiness before modeling."
        action={
          <button className="button primary" onClick={onContinue}>
            Explore dashboard <ArrowRight size={17} />
          </button>
        }
      />
      <div className={`quality-banner ${warned ? "warn" : ""}`}>
        <span className="quality-icon">
          <ShieldCheck size={26} />
        </span>
        <div>
          <h3>
            {warned ? "Ready with warnings" : "Your data is ready to explore"}
          </h3>
          <p>
            {warned
              ? "Review the notes below before generating forecasts."
              : "Required fields, dates, and numeric values passed validation."}
          </p>
        </div>
        <StatusBadge tone={warned ? "warning" : "success"}>
          {d.validation_status.replaceAll("_", " ")}
        </StatusBadge>
      </div>
      <div className="stats-grid">
        <Stat
          label="Rows uploaded"
          value={number(d.row_count)}
          note={`${number(d.processed_row_count)} after exact deduplication`}
        />
        <Stat
          label="Stores"
          value={number(d.store_count)}
          note="Unique retail locations"
        />
        <Stat
          label="Products"
          value={number(d.product_count)}
          note="Unique product identifiers"
        />
        <Stat
          label="Categories"
          value={number(d.category_count)}
          note={
            d.category_count === null
              ? "Optional column not supplied"
              : "Across your product catalog"
          }
        />
      </div>
      <div className="two-columns quality-columns">
        <Panel title="Dataset at a glance" subtitle={d.filename}>
          <div className="detail-list">
            <div>
              <span>Historical period</span>
              <strong>
                {date(d.date_min)} → {date(d.date_max)}
              </strong>
            </div>
            <div>
              <span>Data source</span>
              <strong>
                {d.is_demo ? "Synthetic retail demo" : "Uploaded CSV"}
              </strong>
            </div>
            <div>
              <span>Missing cells</span>
              <strong>{(d.missing_rate * 100).toFixed(2)}%</strong>
            </div>
            <div>
              <span>Exact duplicate rows removed</span>
              <strong>{number(d.duplicate_count)}</strong>
            </div>
            <div>
              <span>Conflicting period observations</span>
              <strong>{number(d.duplicate_observation_count)}</strong>
            </div>
            <div>
              <span>Absent period observations</span>
              <strong>{number(d.missing_date_count)}</strong>
            </div>
            <div>
              <span>Load &amp; validation time</span>
              <strong>
                {number(d.timings.dataset_load_seconds * 1000, 1)} ms
              </strong>
            </div>
          </div>
        </Panel>
        <Panel
          title="Validation checks"
          subtitle="Checked before any model sees your data"
        >
          <div className="check-list">
            {[
              [
                "Required fields after mapping",
                d.validation_status === "FAIL" ? "Review errors" : "Validated",
              ],
              ["Invalid dates", number(d.invalid_date_count)],
              ["Negative sales", number(d.negative_sales_count)],
              ["Nonpositive prices", number(d.invalid_price_count)],
              ["Observation frequency", d.frequency],
              [
                "Chronological order",
                d.chronologically_ordered
                  ? "Already ordered"
                  : "Sorted on import",
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <CheckCircle2 size={17} />
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <p className="methodology">
            Date and demand are required. Single-series identifiers can be
            generated during mapping. Price is optional.
          </p>
        </Panel>
      </div>
      <Panel
        title="Missing values by column"
        subtitle="Missing values are reported explicitly. Sales are never silently filled."
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Column</th>
                <th>Missing values</th>
                <th>Missing rate</th>
                <th>Completeness</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(d.missing_value_summary).map(
                ([column, count]) => (
                  <tr key={column}>
                    <td>
                      <code>{column}</code>
                    </td>
                    <td>{number(count)}</td>
                    <td>{((count / d.row_count) * 100).toFixed(2)}%</td>
                    <td>
                      <div className="completeness">
                        <span
                          style={{
                            width: `${100 - (count / d.row_count) * 100}%`,
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      {d.warnings.length > 0 && (
        <div className="alert warning">
          <Info size={20} />
          <div>
            <strong>Validation notes</strong>
            <ul>
              {d.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="inline-note">
        <FileCheck2 size={17} />
        Validation checks data integrity. The baseline workflow needs 90 daily
        observations. Advanced forecasting shows the history required for your
        chosen horizon and evaluation folds.
      </div>
    </>
  );
}
