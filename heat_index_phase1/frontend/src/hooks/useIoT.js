import { useContext, useEffect, useState } from "react";
import { RefreshContext } from "./useData";
import { fetchData } from "../services/api";

const configuredInterval = Number(import.meta.env.VITE_IOT_REFRESH_MS || 10000);
export const IOT_REFRESH_MS = Number.isFinite(configuredInterval) ? Math.min(300000, Math.max(1000, configuredInterval)) : 10000;

export function useIoT({ history = false, limit = 100 } = {}) {
  const revision = useContext(RefreshContext);
  const [state, setState] = useState({ loading: true, refreshing: false, latest: null, history: null, error: null });
  useEffect(() => {
    let active = true, timer, controller, deadline;
    async function poll() {
      controller = new AbortController();
      setState((previous) => ({ ...previous, loading: !previous.latest, refreshing: true, error: null }));
      deadline = setTimeout(() => controller.abort(new DOMException("IoT request timed out", "TimeoutError")), 30000);
      try {
        const results = await Promise.allSettled([
          fetchData("/iot/latest", {}, controller.signal),
          history ? fetchData("/iot/history", { limit }, controller.signal) : Promise.resolve(null),
        ]);
        const rejected = results.find((result) => result.status === "rejected");
        if (rejected) throw rejected.reason;
        const [latest, records] = results.map((result) => result.value);
        if (active) setState({ loading: false, refreshing: false, latest, history: records, error: null });
      } catch (error) {
        if (active) setState({ loading: false, refreshing: false, latest: null, history: null, error: error.message });
      } finally {
        clearTimeout(deadline);
        // Schedule only after the entire batch settles: no overlapping polling cycles.
        if (active) timer = setTimeout(poll, IOT_REFRESH_MS);
      }
    }
    poll();
    return () => { active = false; clearTimeout(timer); clearTimeout(deadline); controller?.abort(); };
  }, [revision, history, limit]);
  return state;
}
