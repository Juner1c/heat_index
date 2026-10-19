import { createContext, useContext, useEffect, useState } from "react";
import { fetchData } from "../services/api";
export const RefreshContext = createContext(0);

export function useData(path, params = {}) {
  const revision = useContext(RefreshContext);
  const serialized = JSON.stringify(params);
  const requestKey = `${path}:${serialized}:${revision}`;
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, data: null, error: null, requestKey });
    fetchData(path, JSON.parse(serialized), controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ loading: false, data, error: null, requestKey }); })
      .catch((error) => { if (error.name !== "AbortError") setState({ loading: false, data: null, error: error.message, requestKey }); });
    return () => controller.abort();
  }, [path, serialized, revision]);
  return state.requestKey === requestKey ? state : { loading: true, data: null, error: null };
}
