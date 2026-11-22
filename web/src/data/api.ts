import { useQuery } from "@tanstack/react-query";
import type { Backtest, BatterySettings, DayPlan, Drivers, LiveLogEntry, LivePlan, LivePlanRequest, LiveStatus, Meta, Method, ModelInfo, MonthResult } from "./types";

const DATA = `${import.meta.env.BASE_URL}data`;

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url} (${res.status})`);
  return (await res.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") message = j.detail;
      else if (Array.isArray(j.detail)) message = j.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* keep the generic message */
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

const forever = { staleTime: Infinity, gcTime: Infinity } as const;

export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => getJson<Meta>(`${DATA}/meta.json`), ...forever });
export const useDay = (date: string | undefined) =>
  useQuery({ queryKey: ["day", date], queryFn: () => getJson<DayPlan>(`${DATA}/days/${date}.json`), enabled: !!date, ...forever, placeholderData: (prev) => prev });
export const useBacktest = () => useQuery({ queryKey: ["backtest"], queryFn: () => getJson<Backtest>(`${DATA}/backtest.json`), ...forever });
export const useModels = () =>
  useQuery({ queryKey: ["models"], queryFn: () => getJson<{ demand: ModelInfo; price: ModelInfo }>(`${DATA}/models.json`), ...forever });
export const useDrivers = () => useQuery({ queryKey: ["drivers"], queryFn: () => getJson<Drivers>(`${DATA}/drivers.json`), ...forever });
export const useMethod = () => useQuery({ queryKey: ["method"], queryFn: () => getJson<Method>(`${DATA}/method.json`), ...forever });

/** Is the Python planning service running? Checked once, then every 15 s while it is down. */
export const useApiHealth = () =>
  useQuery({
    queryKey: ["api-health"],
    queryFn: async () => {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("down");
      return true;
    },
    retry: false,
    refetchInterval: (q) => (q.state.data ? false : 15000),
    staleTime: 60000,
  });

export const useCustomPlan = (date: string | undefined, battery: BatterySettings, enabled: boolean) =>
  useQuery({
    queryKey: ["plan", date, battery],
    queryFn: () => postJson<DayPlan>("/api/plan", { date, battery }),
    enabled: enabled && !!date,
    staleTime: Infinity,
    retry: false,
    placeholderData: (prev) => prev,
  });

export const runMonth = (battery: BatterySettings) => postJson<MonthResult>("/api/month", { battery });

// ---- Plan live: tomorrow from today's data (needs the planning service) ----
export const getLiveStatus = () => getJson<LiveStatus>("/api/live/status");
/** Downloads today's data. Slow: one to three minutes. */
export const refreshLive = (force = false) => postJson<LiveStatus>("/api/live/refresh", { force });
export const planLive = (req: LivePlanRequest) => postJson<LivePlan>("/api/live/plan", req);
export const getLiveLog = () => getJson<LiveLogEntry[]>("/api/live/log");

export const useLiveStatus = (enabled: boolean) => useQuery({ queryKey: ["live-status"], queryFn: getLiveStatus, enabled, retry: false, staleTime: 60000 });
export const useLivePlan = (req: LivePlanRequest | null, enabled: boolean) =>
  useQuery({ queryKey: ["live-plan", req], queryFn: () => planLive(req!), enabled: enabled && !!req, retry: false, staleTime: Infinity, placeholderData: (prev) => prev });
export const useLiveLog = (enabled: boolean) => useQuery({ queryKey: ["live-log"], queryFn: getLiveLog, enabled, retry: false, staleTime: 60000 });
