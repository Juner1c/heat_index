export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
export function apiUrl(path, params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== "" && value != null));
  return `${API_BASE}${path}${query.size ? `?${query}` : ""}`;
}
export async function fetchData(path, params, signal) {
  const response = await fetch(apiUrl(path, params), { signal });
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "The data request could not be completed. Check the filters or retry.");
  }
  return result;
}
export async function download(path, params = {}) {
  const response = await fetch(apiUrl(path, params));
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.detail?.message || "The report could not be downloaded.");
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] || "thermocast_export.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
