import { useState } from "react";
import { ArrowRight, Check, Layers3 } from "lucide-react";
import { Panel } from "../components";
import { date, metricValue, modelNames } from "../format";
import type { Forecast, Metric } from "../types";

const descriptions = {
  naive: "Repeat the latest observed demand",
  seasonal_naive: "Repeat the last observed week",
  moving_average: "Fixed mean of the last 7 days",
  linear_regression: "Calendar, lags, rolling statistics & price",
};
export default function Comparison({
  result,
  onForecast,
}: {
  result: Forecast | null;
  onForecast: () => void;
}) {
  const [partition, setPartition] = useState<
    "validation_metrics" | "test_metrics"
  >("validation_metrics");
  const metrics: Metric[] = ["mae", "rmse", "wape", "smape", "mase"];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">EVIDENCE BEFORE PREFERENCE</span>
          <h1>Model comparison</h1>
          <p>Four baselines. The same history. An honest comparison.</p>
        </div>
        <button className="button secondary" onClick={onForecast}>
          Back to forecast <ArrowRight size={16} />
        </button>
      </div>
      {!result ? (
        <div className="forecast-empty">
          <Layers3 size={40} />
          <h2>Every comparison starts with a forecast</h2>
          <p>
            Generate a forecast to train and evaluate all four baseline models.
          </p>
          <button className="button primary" onClick={onForecast}>
            Create a forecast <ArrowRight size={16} />
          </button>
        </div>
      ) : (
        <>
          <div className="comparison-banner">
            <span className="large-icon">
              <Check size={23} />
            </span>
            <div>
              <span className="eyebrow">
                SELECTED FOR {result.store_id} / {result.product_id}
              </span>
              <h2>{modelNames[result.model]}</h2>
              <p>{result.selection_reason}</p>
            </div>
            <span className="tag">VALIDATION-BASED SELECTION</span>
          </div>
          <Panel
            title="Measured baseline performance"
            subtitle="Lower is better for every metric. Highlighted cells mark the best measured value."
            action={
              <div className="segmented small">
                <button
                  className={
                    partition === "validation_metrics" ? "selected" : ""
                  }
                  aria-pressed={partition === "validation_metrics"}
                  onClick={() => setPartition("validation_metrics")}
                >
                  Validation
                </button>
                <button
                  className={partition === "test_metrics" ? "selected" : ""}
                  aria-pressed={partition === "test_metrics"}
                  onClick={() => setPartition("test_metrics")}
                >
                  Final test
                </button>
              </div>
            }
          >
            <div className="table-wrap">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Baseline model</th>
                    {metrics.map((key) => (
                      <th key={key}>
                        {key === "smape" ? "sMAPE" : key.toUpperCase()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.comparison.map((row) => (
                    <tr key={row.model}>
                      <td>
                        <div className="model-cell">
                          <strong>{modelNames[row.model]}</strong>
                          {row.model === result.model && (
                            <span className="selected-label">Selected</span>
                          )}
                        </div>
                        <small>{descriptions[row.model]}</small>
                      </td>
                      {metrics.map((key) => {
                        const values = result.comparison
                          .map((r) => r[partition][key])
                          .filter((v): v is number => v !== null);
                        const best =
                          row[partition][key] !== null &&
                          row[partition][key] === Math.min(...values);
                        return (
                          <td key={key}>
                            <span className={best ? "best-value" : ""}>
                              {metricValue(key, row[partition][key])}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="panel-footnote">
              — indicates an undefined metric. WAPE is undefined when actual
              total demand is zero; MASE is undefined when the historical weekly
              naive error is zero.
            </p>
          </Panel>
          <Panel
            title="Time moves in one direction. So does evaluation."
            subtitle="Chronological 70 / 15 / 15 split · no random shuffling"
          >
            <div className="split-bar">
              <span>Training · 70%</span>
              <span>Validation · 15%</span>
              <span>Test · 15%</span>
            </div>
            <div className="split-details">
              {Object.entries(result.split).map(([name, part]) => (
                <div key={name}>
                  <strong>{name}</strong>
                  <p>
                    {date(part.start)} — {date(part.end)}
                  </p>
                  <small>
                    {part.days} days ·{" "}
                    {name === "train"
                      ? "Fit baseline models"
                      : name === "validation"
                        ? "Select on WAPE, then MASE"
                        : "Final evaluation only"}
                  </small>
                </div>
              ))}
            </div>
            <p className="panel-footnote">
              Each holdout is forecast from its start, without observing sales
              inside that holdout. Models are refitted on train + validation
              before test evaluation; the selected model is refitted on all
              history for the future forecast. Holdout lengths may differ from
              the requested forecast horizon.
            </p>
          </Panel>
          <div className="metric-explain">
            <div>
              <h3>Why WAPE?</h3>
              <p>
                Absolute error relative to total demand gives a volume-weighted
                measure for selecting this series’ baseline.
              </p>
            </div>
            <div>
              <h3>Why MASE?</h3>
              <p>
                Errors are scaled by historical seven-day naive errors. A value
                below 1 beats that historical error scale.
              </p>
            </div>
            <div>
              <h3>A baseline, with context</h3>
              <p>
                The selected model fits this series’ validation period. Results
                do not establish a universally best model.
              </p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
