import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";
import { api, describeProblem } from "../api/client";
import { Logo } from "../components/ui";
import { rememberSignIn } from "../lib/session";

/** Sign in: email + password -> POST /auth/token, then into the app. */
export function SignInPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Exchange the credentials for an access token. */
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error: problem } = await api.POST("/auth/token", { body: { email, password } });
    setBusy(false);
    if (!data) return setError(describeProblem(problem));
    rememberSignIn(email, data.accessToken);
    navigate("/portfolios");
  }

  return (
    <div className="auth">
      <section className="auth-story">
        <div className="wordmark">
          <Logo /> Hindsight
        </div>
        <div>
          <blockquote>Every sale has a price you never see. Hindsight shows it to you.</blockquote>
          <div className="example">
            <span className="small">Example: 50 shares sold in June 2017</span>
            <div className="line">
              <span>Sold for</span>
              <span className="num">$7,612.50</span>
            </div>
            <div className="line">
              <span>The same shares today</span>
              <span className="num">$45,210.00</span>
            </div>
            <div className="line big">
              <span>What selling cost</span>
              <span className="num">$37,597.50</span>
            </div>
          </div>
        </div>
        <span className="small" style={{ color: "#9a9993" }}>
          Illustrative figures. Not investment advice.
        </span>
      </section>

      <section className="auth-form">
        <form onSubmit={submit}>
          <div>
            <h1>Welcome back</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              Sign in to your Hindsight account.
            </p>
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p className="error-text">{error}</p>}
          <button
            className="btn primary"
            style={{ justifyContent: "center" }}
            disabled={busy || !email || !password}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}
