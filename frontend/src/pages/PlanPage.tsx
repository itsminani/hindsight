import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { api } from "../api/client";
import { keys, unwrap, usePlan } from "../api/queries";
import { CreditsDonut } from "../components/charts";
import { PageHead } from "../components/ui";
import { plural } from "../lib/format";

/** The user's plan: credit balance, who shares it, and (for owners of shared plans) adding members. */
export function PlanPage() {
  const plan = usePlan();
  if (plan.isLoading) return <p className="muted">Loading…</p>;
  if (plan.isError || !plan.data) return <p className="error-text">{plan.error?.message}</p>;
  const p = plan.data;
  const canManage = p.kind === "shared" && p.role === "owner";

  return (
    <>
      <PageHead
        title="Plan & credits"
        subtitle={
          p.kind === "shared"
            ? `A shared plan · ${plural(p.memberCount, "member")} draw from the same credits`
            : "Your personal plan"
        }
      />
      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)" }}>
        <section className="panel panel-pad">
          <span className="small muted">Credits available</span>
          <div className="hero-figure">{p.creditsAvailable}</div>
          <p className="small muted" style={{ marginTop: 6 }}>
            One credit runs a report on one stock. Credits held by reports in progress come back if a report
            fails.
          </p>
          <CreditsDonut available={p.creditsAvailable} held={p.creditsHeld} />
        </section>

        <section className="panel panel-pad stack" style={{ alignContent: "start" }}>
          <div>
            <h2>Members</h2>
            <p className="small muted" style={{ marginTop: 4 }}>
              You are the {p.role} of this plan.{" "}
              {p.memberCount === 1 ? "Only you use it." : `${p.memberCount} people use it.`}
            </p>
          </div>
          {canManage ? (
            <AddMemberForm />
          ) : (
            <p className="notice">
              {p.kind === "personal"
                ? "Personal plans are just for you. Ask someone with a shared plan to add you."
                : "Only the plan owner can add or remove members."}
            </p>
          )}
        </section>
      </div>
    </>
  );
}

/** Owner only: add someone to the shared plan by their email. */
function AddMemberForm() {
  const [email, setEmail] = useState("");
  const queryClient = useQueryClient();
  const add = useMutation({
    mutationFn: async () => unwrap(await api.POST("/plans/me/members", { body: { email } })),
    onSuccess: (member) => {
      toast.success(`${member.email} now shares your credits`);
      setEmail("");
      void queryClient.invalidateQueries({ queryKey: keys.plan });
    },
    onError: (error) => toast.error(error.message),
  });

  /** Submit the email. */
  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <form className="field" onSubmit={submit}>
      <label htmlFor="member-email">Add a member</label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input
          id="member-email"
          className="input"
          type="email"
          placeholder="name@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button className="btn primary" disabled={!email || add.isPending}>
          Add
        </button>
      </div>
      <span className="hint">They'll draw from this plan's credits right away.</span>
    </form>
  );
}
