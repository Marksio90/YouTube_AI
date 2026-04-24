"use client";

import { useState } from "react";
import { useChannels } from "@/lib/hooks/useChannels";
import {
  useComplianceChecks,
  useComplianceCheck,
  useRunComplianceCheck,
  useOverrideCheck,
  useDismissFlag,
} from "@/lib/hooks/useCompliance";
import type {
  CheckStatus,
  ComplianceSummary,
  RiskCategory,
  RiskSeverity,
} from "@/lib/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const SEVERITY_ORDER: Record<RiskSeverity, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
};

const SEVERITY_COLOR: Record<RiskSeverity, string> = {
  critical: "#ef4444",
  high:     "#f97316",
  medium:   "#eab308",
  low:      "#6366f1",
  info:     "#64748b",
};

const STATUS_COLOR: Record<CheckStatus, string> = {
  pending: "#94a3b8",
  running: "#3b82f6",
  passed:  "#22c55e",
  flagged: "#eab308",
  blocked: "#ef4444",
  error:   "#ec4899",
};

const CATEGORY_LABEL: Record<RiskCategory, string> = {
  ad_safety:      "Ad Safety",
  copyright_risk: "Copyright",
  factual_risk:   "Factual",
  reused_content: "Reused Content",
  ai_disclosure:  "AI Disclosure",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score, status }: { score: number; status: CheckStatus }) {
  const color = STATUS_COLOR[status] ?? "#94a3b8";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 12,
        background: color + "22",
        color,
        fontWeight: 700,
        fontSize: 13,
        border: `1px solid ${color}44`,
      }}
    >
      {score.toFixed(1)} · {status.toUpperCase()}
    </span>
  );
}

function RiskBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min((score / max) * 100, 100);
  const color =
    pct >= 80 ? "#ef4444" : pct >= 21 ? "#eab308" : "#22c55e";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: "var(--color-border)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, color: "var(--color-text-muted)", minWidth: 36, textAlign: "right" }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

// ── CheckDetail panel ─────────────────────────────────────────────────────────

function CheckDetail({ checkId, onClose }: { checkId: string; onClose: () => void }) {
  const { data: check, isLoading } = useComplianceCheck(checkId);
  const overrideMut  = useOverrideCheck();
  const dismissMut   = useDismissFlag();
  const [overrideBy, setOverrideBy]     = useState("");
  const [overrideReason, setOverrideReason] = useState("");

  if (isLoading || !check) {
    return (
      <div className="card" style={{ padding: 24 }}>
        <button onClick={onClose} style={{ marginBottom: 16, cursor: "pointer" }}>← Back</button>
        <p style={{ color: "var(--color-text-muted)" }}>
          {isLoading ? "Loading…" : "Check not found"}
        </p>
      </div>
    );
  }

  const activeFlags = check.flags.filter((f) => !f.is_dismissed);

  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
        <button onClick={onClose} style={{ cursor: "pointer", background: "none", border: "none", fontSize: 14, color: "var(--color-text-muted)" }}>
          ← Back
        </button>
        <ScoreBadge score={check.risk_score} status={check.status} />
        {check.monetization_eligible && (
          <span style={{ fontSize: 12, color: "#22c55e", fontWeight: 600 }}>✓ Monetizable</span>
        )}
        {check.ai_disclosure_required && (
          <span style={{ fontSize: 12, color: "#f97316", fontWeight: 600 }}>⚠ AI Disclosure Required</span>
        )}
      </div>

      {/* Category breakdown */}
      {check.categories && (
        <div style={{ marginBottom: 24 }}>
          <div className="t-section" style={{ marginBottom: 10 }}>Category Scores</div>
          <div style={{ display: "grid", gap: 10 }}>
            {check.categories.map((cat) => (
              <div key={cat.category}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{CATEGORY_LABEL[cat.category]}</span>
                  <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                    {cat.flag_count} flag{cat.flag_count !== 1 ? "s" : ""}
                    {cat.worst_severity && (
                      <span style={{ marginLeft: 6, color: SEVERITY_COLOR[cat.worst_severity], fontWeight: 600 }}>
                        · {cat.worst_severity}
                      </span>
                    )}
                  </span>
                </div>
                <RiskBar score={cat.score} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active flags */}
      <div style={{ marginBottom: 24 }}>
        <div className="t-section" style={{ marginBottom: 10 }}>
          Risk Flags ({activeFlags.length})
        </div>
        {activeFlags.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: 13 }}>No active flags.</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {activeFlags.map((flag) => (
              <div
                key={flag.id}
                style={{
                  padding: 14,
                  border: `1px solid ${SEVERITY_COLOR[flag.severity]}44`,
                  borderLeft: `3px solid ${SEVERITY_COLOR[flag.severity]}`,
                  borderRadius: 8,
                  background: SEVERITY_COLOR[flag.severity] + "08",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{flag.title}</div>
                    <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 6 }}>
                      {CATEGORY_LABEL[flag.category]} · {flag.source.toUpperCase()} · <code style={{ fontSize: 11 }}>{flag.rule_id}</code>
                    </div>
                    <div style={{ fontSize: 13, marginBottom: 6 }}>{flag.detail}</div>
                    {flag.evidence && (
                      <blockquote style={{ margin: "6px 0", padding: "4px 10px", borderLeft: "2px solid var(--color-border)", fontSize: 12, color: "var(--color-text-muted)", fontStyle: "italic" }}>
                        "{flag.evidence}"
                      </blockquote>
                    )}
                    {flag.suggestion && (
                      <div style={{ fontSize: 12, color: "#22c55e", marginTop: 4 }}>
                        💡 {flag.suggestion}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() =>
                      dismissMut.mutate({ flagId: flag.id, dismissed_by: "reviewer" })
                    }
                    disabled={dismissMut.isPending}
                    style={{ flexShrink: 0, fontSize: 12, padding: "3px 10px", borderRadius: 6, cursor: "pointer" }}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Override blocked */}
      {check.status === "blocked" && !check.is_overridden && (
        <div style={{ padding: 16, border: "1px solid #ef444444", borderRadius: 8, background: "#ef444408" }}>
          <div className="t-section" style={{ marginBottom: 10, color: "#ef4444" }}>Override Blocked Check</div>
          <input
            placeholder="Your name"
            value={overrideBy}
            onChange={(e) => setOverrideBy(e.target.value)}
            style={{ display: "block", width: "100%", marginBottom: 8, padding: "8px 12px", borderRadius: 6, border: "1px solid var(--color-border)", background: "var(--color-bg-card)", color: "inherit" }}
          />
          <textarea
            placeholder="Justification (min. 10 chars)"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            rows={3}
            style={{ display: "block", width: "100%", marginBottom: 8, padding: "8px 12px", borderRadius: 6, border: "1px solid var(--color-border)", background: "var(--color-bg-card)", color: "inherit", resize: "vertical" }}
          />
          <button
            onClick={() =>
              overrideMut.mutate({ checkId: check.id, override_by: overrideBy, override_reason: overrideReason })
            }
            disabled={overrideMut.isPending || overrideBy.length < 1 || overrideReason.length < 10}
            style={{ padding: "8px 18px", borderRadius: 6, background: "#ef4444", color: "#fff", fontWeight: 600, cursor: "pointer", border: "none" }}
          >
            {overrideMut.isPending ? "Overriding…" : "Override"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Check list row ────────────────────────────────────────────────────────────

function CheckRow({
  check,
  onSelect,
}: {
  check: ComplianceSummary;
  onSelect: () => void;
}) {
  const color = STATUS_COLOR[check.status];
  return (
    <tr
      onClick={onSelect}
      style={{ cursor: "pointer" }}
    >
      <td style={{ padding: "10px 12px", fontSize: 13 }}>
        <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--color-text-muted)" }}>
          {check.id.slice(0, 8)}
        </span>
      </td>
      <td style={{ padding: "10px 12px", fontSize: 13 }}>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: 10,
            background: color + "22",
            color,
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {check.status.toUpperCase()}
        </span>
      </td>
      <td style={{ padding: "10px 12px" }}>
        <RiskBar score={check.risk_score} />
      </td>
      <td style={{ padding: "10px 12px", fontSize: 13, textAlign: "center" }}>
        {check.flag_count}
        {check.critical_count > 0 && (
          <span style={{ marginLeft: 4, color: "#ef4444", fontWeight: 700 }}>
            ({check.critical_count} crit)
          </span>
        )}
      </td>
      <td style={{ padding: "10px 12px", fontSize: 12, textAlign: "center" }}>
        {check.monetization_eligible ? (
          <span style={{ color: "#22c55e" }}>✓</span>
        ) : (
          <span style={{ color: "#ef4444" }}>✗</span>
        )}
      </td>
      <td style={{ padding: "10px 12px", fontSize: 12, color: "var(--color-text-muted)" }}>
        {new Date(check.created_at).toLocaleDateString()}
      </td>
    </tr>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function ComplianceView() {
  const { data: channelPages } = useChannels(1);
  const channels = channelPages?.items ?? [];
  const [channelId, setChannelId] = useState("");
  const activeChannelId = channelId || channels[0]?.id || "";

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedCheckId, setSelectedCheckId] = useState<string | null>(null);

  const { data: checks = [], isLoading } = useComplianceChecks(
    activeChannelId,
    statusFilter ? { status: statusFilter } : undefined
  );

  const runMut = useRunComplianceCheck(activeChannelId);

  if (selectedCheckId) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
        <CheckDetail checkId={selectedCheckId} onClose={() => setSelectedCheckId(null)} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Compliance</h1>
          <p style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            Risk scoring · Copyright · Ad safety · Factual accuracy
          </p>
        </div>
        <button
          onClick={() => runMut.mutate({ mode: "both" })}
          disabled={runMut.isPending || !activeChannelId}
          style={{
            padding: "9px 18px",
            borderRadius: 8,
            background: "var(--color-primary)",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
            border: "none",
            fontSize: 14,
          }}
        >
          {runMut.isPending ? "Running…" : "Run Check"}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {channels.length > 1 && (
          <select
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            style={{ padding: "7px 12px", borderRadius: 6, border: "1px solid var(--color-border)", background: "var(--color-bg-card)", color: "inherit", fontSize: 13 }}
          >
            {channels.map((ch) => (
              <option key={ch.id} value={ch.id}>{ch.name}</option>
            ))}
          </select>
        )}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ padding: "7px 12px", borderRadius: 6, border: "1px solid var(--color-border)", background: "var(--color-bg-card)", color: "inherit", fontSize: 13 }}
        >
          <option value="">All Statuses</option>
          <option value="passed">Passed</option>
          <option value="flagged">Flagged</option>
          <option value="blocked">Blocked</option>
          <option value="running">Running</option>
        </select>
      </div>

      {/* Score legend */}
      <div className="card" style={{ padding: "12px 16px", marginBottom: 20, display: "flex", gap: 24, flexWrap: "wrap" }}>
        {[
          { label: "Passed", range: "< 21", color: "#22c55e" },
          { label: "Flagged", range: "21–79", color: "#eab308" },
          { label: "Blocked", range: "≥ 80", color: "#ef4444" },
        ].map((t) => (
          <div key={t.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: t.color }} />
            <span style={{ color: "var(--color-text-muted)" }}>{t.label}</span>
            <span style={{ fontWeight: 600 }}>{t.range}</span>
          </div>
        ))}
      </div>

      {/* Check table */}
      <div className="card" style={{ overflow: "hidden" }}>
        {isLoading ? (
          <p style={{ padding: 24, color: "var(--color-text-muted)" }}>Loading checks…</p>
        ) : checks.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center" }}>
            <p style={{ color: "var(--color-text-muted)", marginBottom: 12 }}>No compliance checks yet.</p>
            <button
              onClick={() => runMut.mutate({ mode: "both" })}
              disabled={runMut.isPending}
              style={{ padding: "8px 16px", borderRadius: 6, background: "var(--color-primary)", color: "#fff", fontWeight: 600, cursor: "pointer", border: "none" }}
            >
              Run First Check
            </button>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                {["ID", "Status", "Risk Score", "Flags", "Monetizable", "Date"].map((h) => (
                  <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <CheckRow
                  key={check.id}
                  check={check}
                  onSelect={() => setSelectedCheckId(check.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
