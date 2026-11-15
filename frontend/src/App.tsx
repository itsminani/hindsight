import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router";
import { getToken, onUnauthorized } from "./api/client";
import { Toaster } from "sonner";
import { Logo } from "./components/ui";
import { currentEmail, signOut } from "./lib/session";
import { PortfolioPage } from "./pages/PortfolioPage";
import { PortfoliosPage } from "./pages/PortfoliosPage";
import { SignInPage } from "./pages/SignInPage";

// One cache for all API data (TanStack Query): pages share results and refetch when needed.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 5_000 } } });

/** Routes: /signin is public; everything else needs a token and sits inside the app shell. */
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="bottom-center" />
      <BrowserRouter>
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route element={<RequireSignIn />}>
            <Route element={<Shell />}>
              <Route index element={<Navigate to="/portfolios" replace />} />
              <Route path="/portfolios" element={<PortfoliosPage />} />
              <Route path="/portfolios/:portfolioId" element={<PortfolioPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

/** Lets signed-in users through; sends everyone else (and expired tokens) to /signin. */
function RequireSignIn() {
  const [signedIn, setSignedIn] = useState(() => getToken() !== null);
  useEffect(() => onUnauthorized(() => setSignedIn(false)), []);
  return signedIn ? <Outlet /> : <Navigate to="/signin" replace />;
}

/** The app frame: navigation on the left, the current page on the right. */
function Shell() {
  const navigate = useNavigate();
  const email = currentEmail();

  /** Sign out and go back to the sign-in page. */
  function leave() {
    signOut();
    queryClient.clear();
    navigate("/signin");
  }

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="wordmark">
          <Logo /> Hindsight
        </div>
        <NavLink to="/portfolios" className="nav-link">
          Portfolios
        </NavLink>
        <NavLink to="/reports" className="nav-link">
          Reports
        </NavLink>
        <NavLink to="/plan" className="nav-link">
          Plan &amp; credits
        </NavLink>
        <div className="sidebar-foot">
          <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
            <span className="avatar">{email.slice(0, 1).toUpperCase()}</span>
            <span className="small" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
              {email}
            </span>
          </div>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <button className="btn ghost small" onClick={leave}>
              Sign out
            </button>
            <NavLink to="/lab" className="small muted" style={{ textDecoration: "none" }}>
              Developer lab
            </NavLink>
          </div>
        </div>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
