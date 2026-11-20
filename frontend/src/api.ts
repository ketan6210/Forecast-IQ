export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const fields = Array.isArray(data?.details)
      ? data.details
          .map(
            (item: { field: string; message: string }) =>
              `${item.field}: ${item.message}`,
          )
          .join(" ")
      : "";
    throw new Error(
      `${data?.error || `Request failed (${response.status}). Check that the API is running.`} ${fields}`.trim(),
    );
  }
  if (data === null)
    throw new Error(
      "The API returned an invalid response. Check that the backend is running.",
    );
  return data as T;
}

const forecastCatalogRequests = new Map<string, Promise<unknown[]>>();

function catalogRequest<T extends { run_id: string }>(datasetId: string) {
  const existing = forecastCatalogRequests.get(datasetId);
  if (existing) return existing as Promise<T[]>;

  const request = (async () => {
    const rows = new Map<string, T>();
    const path = `/forecast/models?dataset_id=${encodeURIComponent(datasetId)}`;
    for (let offset = 0; ; offset += 100) {
      const page = await api<T[]>(
        offset ? `${path}&limit=100&offset=${offset}` : path,
      );
      const previousSize = rows.size;
      for (const row of page) rows.set(row.run_id, row);
      if (page.length < 100) return [...rows.values()];
      if (rows.size === previousSize)
        throw new Error(
          "Forecast catalog pagination did not advance. Refresh after updating the backend.",
        );
    }
  })();

  forecastCatalogRequests.set(datasetId, request as Promise<unknown[]>);
  const cleanup = () => {
    if (forecastCatalogRequests.get(datasetId) === request)
      forecastCatalogRequests.delete(datasetId);
  };
  request.then(cleanup, cleanup);
  return request;
}

export async function forecastRuns<T extends { run_id: string }>(
  datasetId: string,
  signal: AbortSignal,
): Promise<T[]> {
  if (signal.aborted) throw new DOMException("Request aborted", "AbortError");
  const request = catalogRequest<T>(datasetId);
  return new Promise<T[]>((resolve, reject) => {
    const abort = () =>
      reject(new DOMException("Request aborted", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    request.then(
      (rows) => {
        signal.removeEventListener("abort", abort);
        if (!signal.aborted) resolve(rows);
      },
      (error) => {
        signal.removeEventListener("abort", abort);
        if (!signal.aborted) reject(error);
      },
    );
  });
}
