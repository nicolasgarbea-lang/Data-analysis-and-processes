import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createHashHistory, createRootRoute, createRoute, createRouter, Link, Outlet, RouterProvider } from "@tanstack/react-router";
import "@fontsource-variable/archivo/standard.css";
import "./styles.css";
import { useMeta } from "./data/api";
import { Tomorrow } from "./routes/Tomorrow";
import { Battery } from "./routes/Battery";
import { Results } from "./routes/Results";
import { MethodPage } from "./routes/Method";
import { Live } from "./routes/Live";

type DaySearch = { date?: string };
const daySearch = (s: Record<string, unknown>): DaySearch => (typeof s.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s.date) ? { date: s.date } : {});

function Shell() {
  const meta = useMeta();
  return (
    <>
      <header className="masthead">
        <Link to="/" className="wordmark">
          {meta.data?.company ?? "Limmat Energie AG"}
        </Link>
        <nav aria-label="Sections">
          <Link to="/live" activeProps={{ "aria-current": "page" }}>
            1 · Plan tomorrow
            <small>the real tool, today’s data</small>
          </Link>
          <Link to="/" activeOptions={{ exact: true, includeSearch: false }} activeProps={{ "aria-current": "page" }}>
            2 · Replay a test day
            <small>one past day, plan vs reality</small>
          </Link>
          <Link to="/battery" activeOptions={{ includeSearch: false }} activeProps={{ "aria-current": "page" }}>
            3 · Battery simulator
            <small>try another battery size</small>
          </Link>
          <Link to="/results" activeProps={{ "aria-current": "page" }}>
            4 · October results
            <small>did it work, in CHF</small>
          </Link>
          <Link to="/how" activeProps={{ "aria-current": "page" }}>
            5 · How it works
            <small>method and limits</small>
          </Link>
        </nav>
        {meta.data && (
          <span className="clock">
            Every day: forecast at {meta.data.forecast_time_local}, bids due {meta.data.gate_closure_local}
          </span>
        )}
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="colophon">
        <p>
          A university project (HSG, Business Analytics and Data Science Applications, 2026). Limmat Energie AG and its battery are fictional. The demand is the
          real grid load of the city of Zurich, the prices are the real Swiss day-ahead prices. Every result is a simulation.
        </p>
      </footer>
    </>
  );
}

const rootRoute = createRootRoute({ component: Shell });
const tomorrowRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: Tomorrow, validateSearch: daySearch });
const batteryRoute = createRoute({ getParentRoute: () => rootRoute, path: "/battery", component: Battery, validateSearch: daySearch });
const resultsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/results", component: Results });
const methodRoute = createRoute({ getParentRoute: () => rootRoute, path: "/how", component: MethodPage });
const liveRoute = createRoute({ getParentRoute: () => rootRoute, path: "/live", component: Live });

const router = createRouter({
  routeTree: rootRoute.addChildren([liveRoute, tomorrowRoute, resultsRoute, batteryRoute, methodRoute]),
  history: createHashHistory(), // works from any static file host
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
