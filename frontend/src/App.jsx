import { useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeImportRun,
  generateCases,
  getCaseDetail,
  getCases,
  getDatabaseStatus,
  getImportRuns,
  reportUrl,
  updateCaseWorkflow,
  uploadEvidenceBundle
} from "./api";

const severityOrder = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  informational: 0
};

function formatDate(value) {
  if (!value) {
    return "Not recorded";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(parsed) + " UTC";
}

function capitalize(value) {
  if (!value) {
    return "Not recorded";
  }

  return value
    .split("_")
    .map((item) => item.charAt(0).toUpperCase() + item.slice(1))
    .join(" ");
}

function runTimestamp(run) {
  const parsed = new Date(run.created_at ?? 0);
  const timestamp = parsed.getTime();

  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortRunsNewestFirst(runs) {
  return [...runs].sort(
    (left, right) => runTimestamp(right) - runTimestamp(left)
  );
}

function getTenantKey(run) {
  return (
    run.tenant_display_name?.trim() ||
    run.tenant_id?.trim() ||
    run.id
  );
}

function selectLatestRunsByTenant(runs) {
  const latestRuns = new Map();

  for (const run of sortRunsNewestFirst(runs)) {
    const tenantKey = getTenantKey(run);

    if (!latestRuns.has(tenantKey)) {
      latestRuns.set(tenantKey, run);
    }
  }

  return Array.from(latestRuns.values());
}
function SeverityBadge({ severity }) {
  return (
    <span className={`severity-badge severity-${severity ?? "informational"}`}>
      {severity ?? "informational"}
    </span>
  );
}

function ConfidenceBadge({ confidence }) {
  return (
    <span className="confidence-badge">
      {confidence ?? "unknown"} confidence
    </span>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">⌁</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export default function App() {
  const [databaseOnline, setDatabaseOnline] = useState(false);
  const [importRuns, setImportRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedCase, setSelectedCase] = useState(null);

  const [searchText, setSearchText] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [caseLoading, setCaseLoading] = useState(false);
  const [workflowSaving, setWorkflowSaving] = useState(false);

  const [analystName, setAnalystName] = useState(
    "Cloud Identity Analyst"
  );
  const [workflowStatus, setWorkflowStatus] = useState("open");
  const [workflowDisposition, setWorkflowDisposition] = useState(
    "needs_review"
  );
  const [assignedTo, setAssignedTo] = useState("");
  const [workflowNote, setWorkflowNote] = useState("");

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const fileInputRef = useRef(null);

  async function loadCaseDetail(caseId) {
    if (!caseId) {
      setSelectedCase(null);
      return;
    }

    setCaseLoading(true);

    try {
      const detail = await getCaseDetail(caseId);
      setSelectedCase(detail);
      setWorkflowStatus(detail.status ?? "open");
      setWorkflowDisposition(detail.disposition ?? "needs_review");
      setAssignedTo(detail.assigned_to ?? "");
      setWorkflowNote("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCaseLoading(false);
    }
  }

  async function loadCasesForRun(importRunId, preferredCaseId = "") {
    if (!importRunId) {
      setCases([]);
      setSelectedCase(null);
      setSelectedCaseId("");
      return;
    }

    setQueueLoading(true);

    try {
      const loadedCases = await getCases(importRunId);

      const orderedCases = [...loadedCases].sort((left, right) => {
        const severityDifference =
          (severityOrder[right.severity] ?? 0) -
          (severityOrder[left.severity] ?? 0);

        if (severityDifference !== 0) {
          return severityDifference;
        }

        return left.title.localeCompare(right.title);
      });

      setCases(orderedCases);

      const nextCaseId =
        preferredCaseId ||
        orderedCases.find((item) => item.severity === "critical")?.id ||
        orderedCases[0]?.id ||
        "";

      setSelectedCaseId(nextCaseId);

      if (nextCaseId) {
        await loadCaseDetail(nextCaseId);
      } else {
        setSelectedCase(null);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setQueueLoading(false);
    }
  }

  async function bootstrapWorkspace() {
    try {
      await getDatabaseStatus();
      setDatabaseOnline(true);

      const runs = await getImportRuns();
      const orderedRuns = sortRunsNewestFirst(runs);
      const latestRuns = selectLatestRunsByTenant(orderedRuns);

      setImportRuns(orderedRuns);

      const preferredRun =
        latestRuns.find((run) => run.status === "completed") ??
        orderedRuns.find((run) => run.status === "completed") ??
        latestRuns[0] ??
        orderedRuns[0];

      if (preferredRun) {
        setSelectedRunId(preferredRun.id);
        await loadCasesForRun(preferredRun.id);
      }
    } catch (requestError) {
      setDatabaseOnline(false);
      setError(
        `Unable to reach GrantScope API. ${requestError.message}`
      );
    }
  }
  useEffect(() => {
    bootstrapWorkspace();
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      return;
    }

    loadCaseDetail(selectedCaseId);
  }, [selectedCaseId]);

  const filteredCases = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();

    return cases.filter((caseItem) => {
      const severityMatches =
        severityFilter === "all" ||
        caseItem.severity === severityFilter;

      const statusMatches =
        statusFilter === "all" ||
        caseItem.status === statusFilter;

      const searchableText = [
        caseItem.title,
        caseItem.summary,
        caseItem.severity,
        caseItem.confidence,
        caseItem.status,
        caseItem.disposition,
        caseItem.assigned_to
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      const textMatches =
        !normalizedSearch ||
        searchableText.includes(normalizedSearch);

      return severityMatches && statusMatches && textMatches;
    });
  }, [cases, searchText, severityFilter, statusFilter]);

  const sortedImportRuns = useMemo(() => {
    return sortRunsNewestFirst(importRuns);
  }, [importRuns]);

  const latestRunsByTenant = useMemo(() => {
    return selectLatestRunsByTenant(sortedImportRuns);
  }, [sortedImportRuns]);

  const historicalImportRuns = useMemo(() => {
    const latestRunIds = new Set(
      latestRunsByTenant.map((run) => run.id)
    );

    return sortedImportRuns.filter(
      (run) => !latestRunIds.has(run.id)
    );
  }, [latestRunsByTenant, sortedImportRuns]);

  const selectedRun = useMemo(() => {
    return (
      sortedImportRuns.find(
        (run) => run.id === selectedRunId
      ) ?? null
    );
  }, [selectedRunId, sortedImportRuns]);

  const selectedRunIsLatest = useMemo(() => {
    if (!selectedRunId) {
      return false;
    }

    return latestRunsByTenant.some(
      (run) => run.id === selectedRunId
    );
  }, [latestRunsByTenant, selectedRunId]);

  const queueEmptyState = useMemo(() => {
    if (!selectedRunId) {
      return {
        title: "Select an evidence run",
        description:
          "Choose a tenant evidence run or import a GrantScope ZIP bundle to begin investigation."
      };
    }

    const filtersAreActive =
      searchText.trim() ||
      severityFilter !== "all" ||
      statusFilter !== "all";

    if (filtersAreActive) {
      return {
        title: "No cases match the active filters",
        description:
          "Clear the search, severity, or workflow filters to review all cases in this evidence run."
      };
    }

    return {
      title: "No investigation cases met the current threshold",
      description:
        "This evidence run was processed successfully. No application or service-principal evidence currently requires analyst investigation."
    };
  }, [
    searchText,
    selectedRunId,
    severityFilter,
    statusFilter
  ]);
  const summary = useMemo(() => {
    return {
      total: cases.length,
      critical: cases.filter(
        (caseItem) => caseItem.severity === "critical"
      ).length,
      high: cases.filter(
        (caseItem) => caseItem.severity === "high"
      ).length,
      underReview: cases.filter(
        (caseItem) => caseItem.status === "under_review"
      ).length
    };
  }, [cases]);

  async function handleImport(event) {
    event.preventDefault();

    if (!file) {
      setError("Select a GrantScope evidence ZIP bundle first.");
      return;
    }

    setUploading(true);
    setError("");
    setNotice("");

    try {
      const imported = await uploadEvidenceBundle(file);
      const importRunId = imported.import_run.id;

      setNotice("Evidence imported. Running correlation analysis...");
      await analyzeImportRun(importRunId);

      setNotice("Generating analyst case packets...");
      await generateCases(importRunId);

      const runs = await getImportRuns();
      setImportRuns(runs);
      setSelectedRunId(importRunId);

      await loadCasesForRun(importRunId);

      setNotice(
        "Import, analysis, and case generation completed successfully."
      );

      setFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleWorkflowSave(event) {
    event.preventDefault();

    if (!selectedCase) {
      return;
    }

    const payload = {
      analyst_name: analystName.trim() || "Cloud Identity Analyst"
    };

    if (workflowStatus !== selectedCase.status) {
      payload.status = workflowStatus;
    }

    if (workflowDisposition !== selectedCase.disposition) {
      payload.disposition = workflowDisposition;
    }

    if (assignedTo.trim()) {
      payload.assigned_to = assignedTo.trim();
    }

    if (workflowNote.trim()) {
      payload.note = workflowNote.trim();
    }

    if (Object.keys(payload).length === 1) {
      setError(
        "Change a status or disposition, add an assignment, or enter an analyst note before saving."
      );
      return;
    }

    setWorkflowSaving(true);
    setError("");
    setNotice("");

    try {
      const response = await updateCaseWorkflow(
        selectedCase.id,
        payload
      );

      setNotice(
        `Case workflow updated: ${capitalize(response.status)} / ${capitalize(response.disposition)}.`
      );

      await loadCaseDetail(selectedCase.id);
      await loadCasesForRun(selectedRunId, selectedCase.id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorkflowSaving(false);
    }
  }

  function handleRunChange(event) {
    const runId = event.target.value;

    setSelectedRunId(runId);
    setError("");
    setNotice("");

    loadCasesForRun(runId);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">G</div>
          <div>
            <div className="brand-name">GrantScope</div>
            <div className="brand-subtitle">Identity Investigation</div>
          </div>
        </div>

        <div className="environment-card">
          <span
            className={`connection-dot ${
              databaseOnline ? "online" : "offline"
            }`}
          />
          <div>
            <strong>
              {databaseOnline
                ? "Local investigation lab"
                : "API unavailable"}
            </strong>
            <span>
              {databaseOnline
                ? "FastAPI + PostgreSQL connected"
                : "Check Docker containers"}
            </span>
          </div>
        </div>

        <nav className="navigation">
          <a href="#workspace" className="nav-item active">
            <span>▣</span>
            Investigation Workspace
          </a>
          <a href="#case-queue" className="nav-item">
            <span>◫</span>
            Case Queue
          </a>
          <a href="#case-detail" className="nav-item">
            <span>⌁</span>
            Evidence Detail
          </a>
        </nav>

        <div className="sidebar-note">
          <strong>Prototype scope</strong>
          <p>
            Export-first Entra OAuth and service-principal investigation.
            No tenant credentials are stored in this interface.
          </p>
        </div>
      </aside>

      <main className="main-content" id="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Cloud identity security workbench</p>
            <h1>Investigate application privilege and persistence risk</h1>
          </div>

          <div className="topbar-actions">
            {selectedRunId && (
              <span className="case-count">
                {selectedRunIsLatest
                  ? "Latest evidence run"
                  : "Historical evidence run"}
              </span>
            )}

            <select
              value={selectedRunId}
              onChange={handleRunChange}
              aria-label="Select import run"
            >
              <option value="">Select an investigation run</option>

              {latestRunsByTenant.length > 0 && (
                <optgroup label="Latest evidence by tenant">
                  {latestRunsByTenant.map((run) => (
                    <option key={run.id} value={run.id}>
                      {(run.tenant_display_name ?? run.tenant_id)}
                      {" · Latest · "}
                      {formatDate(run.created_at)}
                    </option>
                  ))}
                </optgroup>
              )}

              {historicalImportRuns.length > 0 && (
                <optgroup label="Previous imports (history)">
                  {historicalImportRuns.map((run) => (
                    <option key={run.id} value={run.id}>
                      {(run.tenant_display_name ?? run.tenant_id)}
                      {" · "}
                      {formatDate(run.created_at)}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>

            <button
              className="secondary-button"
              onClick={bootstrapWorkspace}
              type="button"
            >
              Refresh workspace
            </button>
          </div>
        </header>
        {error && (
          <div className="banner banner-error">
            <strong>Action failed.</strong>
            <span>{error}</span>
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}

        {notice && (
          <div className="banner banner-success">
            <strong>Workspace update.</strong>
            <span>{notice}</span>
            <button onClick={() => setNotice("")}>Dismiss</button>
          </div>
        )}

        <section className="stats-grid">
          <article className="stat-card">
            <span>Open cases</span>
            <strong>{summary.total}</strong>
            <small>Current import run</small>
          </article>

          <article className="stat-card critical-stat">
            <span>Critical</span>
            <strong>{summary.critical}</strong>
            <small>Immediate human review</small>
          </article>

          <article className="stat-card high-stat">
            <span>High severity</span>
            <strong>{summary.high}</strong>
            <small>Privilege or persistence risk</small>
          </article>

          <article className="stat-card review-stat">
            <span>Under review</span>
            <strong>{summary.underReview}</strong>
            <small>Analyst workflow state</small>
          </article>
        </section>

        <section className="workspace-grid">
          <article className="panel import-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Evidence intake</p>
                <h2>Import investigation bundle</h2>
              </div>
              <span className="panel-tag">ZIP</span>
            </div>

            <p className="muted">
              Upload a GrantScope evidence bundle containing Entra application,
              consent, credential, audit, and sign-in telemetry.
            </p>

            <form onSubmit={handleImport} className="import-form">
              <label className="file-picker">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(event) =>
                    setFile(event.target.files?.[0] ?? null)
                  }
                />
                <span className="file-picker-icon">↑</span>
                <span>
                  {file
                    ? file.name
                    : "Choose evidence ZIP bundle"}
                </span>
              </label>

              <button
                className="primary-button"
                type="submit"
                disabled={uploading}
              >
                {uploading
                  ? "Importing and correlating..."
                  : "Import and investigate"}
              </button>
            </form>

            <div className="import-steps">
              <span>1. Normalize evidence</span>
              <span>2. Run detection logic</span>
              <span>3. Generate analyst cases</span>
            </div>
          </article>

          <article className="panel coverage-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Current workspace</p>
                <h2>Evidence coverage</h2>
              </div>
            </div>

            <div className="coverage-list">
              <div>
                <span>Investigation cases</span>
                <strong>{cases.length}</strong>
              </div>
              <div>
                <span>Evidence run</span>
                <strong>
                  {selectedRun
                    ? `${selectedRun.id.slice(0, 8)}…`
                    : "None"}
                </strong>
              </div>
              <div>
                <span>Run context</span>
                <strong>
                  {selectedRun
                    ? selectedRunIsLatest
                      ? "Latest tenant evidence"
                      : "Previous import"
                    : "No run selected"}
                </strong>
              </div>
              <div>
                <span>Imported bundle</span>
                <strong title={selectedRun?.source_name}>
                  {selectedRun?.source_name ?? "Not recorded"}
                </strong>
              </div>
            </div>
          </article>
        </section>
        <section className="investigation-layout">
          <article className="panel queue-panel" id="case-queue">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Triage queue</p>
                <h2>Investigation cases</h2>
              </div>

              <span className="case-count">
                {filteredCases.length} shown
              </span>
            </div>

            <div className="queue-filters">
              <input
                type="search"
                placeholder="Search cases, owners, severity..."
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
              />

              <select
                value={severityFilter}
                onChange={(event) =>
                  setSeverityFilter(event.target.value)
                }
              >
                <option value="all">All severity</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>

              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">All status</option>
                <option value="open">Open</option>
                <option value="under_review">Under review</option>
                <option value="contained">Contained</option>
                <option value="closed">Closed</option>
                <option value="insufficient_evidence">
                  Insufficient evidence
                </option>
              </select>
            </div>

            {queueLoading ? (
              <div className="loading-state">Loading cases...</div>
            ) : filteredCases.length ? (
              <div className="case-list">
                {filteredCases.map((caseItem) => (
                  <button
                    className={`case-row ${
                      selectedCaseId === caseItem.id ? "selected" : ""
                    }`}
                    key={caseItem.id}
                    onClick={() => setSelectedCaseId(caseItem.id)}
                    type="button"
                  >
                    <div className="case-row-top">
                      <SeverityBadge severity={caseItem.severity} />
                      <ConfidenceBadge confidence={caseItem.confidence} />
                      <span className="case-status">
                        {capitalize(caseItem.status)}
                      </span>
                    </div>

                    <strong>{caseItem.title}</strong>

                    <p>{caseItem.summary}</p>

                    <div className="case-row-footer">
                      <span>{caseItem.finding_count} findings</span>
                      <span>{caseItem.evidence_count} evidence items</span>
                      <span>
                        {caseItem.assigned_to
                          ? caseItem.assigned_to
                          : "Unassigned"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                title={queueEmptyState.title}
                description={queueEmptyState.description}
              />
            )}
          </article>

          <article className="panel detail-panel" id="case-detail">
            {caseLoading ? (
              <div className="loading-state">Loading case evidence...</div>
            ) : selectedCase ? (
              <>
                <div className="case-detail-header">
                  <div>
                    <div className="case-badges">
                      <SeverityBadge severity={selectedCase.severity} />
                      <ConfidenceBadge
                        confidence={selectedCase.confidence}
                      />
                      <span className="case-status large-status">
                        {capitalize(selectedCase.status)}
                      </span>
                    </div>

                    <p className="eyebrow">Analyst case packet</p>
                    <h2>{selectedCase.title}</h2>
                    <p className="case-summary">
                      {selectedCase.summary}
                    </p>
                  </div>

                  <div className="report-actions">
                    <a
                      className="primary-button"
                      href={reportUrl(selectedCase.id, "pdf")}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Export PDF
                    </a>

                    <a
                      className="secondary-button"
                      href={reportUrl(selectedCase.id, "html")}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open HTML report
                    </a>

                    <a
                      className="secondary-button"
                      href={reportUrl(selectedCase.id, "markdown")}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Export Markdown
                    </a>
                  </div>
                </div>

                <section className="detail-section">
                  <div className="section-title">
                    <h3>Executive assessment</h3>
                    <span>
                      {selectedCase.finding_count} linked findings ·{" "}
                      {selectedCase.evidence_count} evidence records
                    </span>
                  </div>

                  <p className="assessment-text">
                    {selectedCase.summary}
                  </p>
                </section>

                <section className="detail-section">
                  <div className="section-title">
                    <h3>Evidence timeline</h3>
                    <span>
                      Correlated audit, credential, permission, and sign-in context
                    </span>
                  </div>

                  {selectedCase.timeline?.length ? (
                    <div className="timeline">
                      {selectedCase.timeline.map((event, index) => (
                        <div className="timeline-event" key={`${event.source_external_id}-${index}`}>
                          <div className="timeline-marker" />
                          <div className="timeline-content">
                            <span>{formatDate(event.observed_at)}</span>
                            <strong>{event.label}</strong>
                            <p>{event.detail ?? "No detail recorded."}</p>
                            {event.correlation_id && (
                              <code>
                                Correlation: {event.correlation_id}
                              </code>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="No timestamped evidence"
                      description="The imported evidence does not contain timestamped events for this case."
                    />
                  )}
                </section>

                <section className="detail-section">
                  <div className="section-title">
                    <h3>Detection findings</h3>
                    <span>Explainable rule outcomes</span>
                  </div>

                  <div className="findings-grid">
                    {selectedCase.findings?.map((finding) => (
                      <article className="finding-card" key={finding.id}>
                        <div className="finding-card-top">
                          <SeverityBadge severity={finding.severity} />
                          <code>{finding.rule_id}</code>
                        </div>

                        <h4>{finding.title}</h4>
                        <p>{finding.rationale}</p>

                        <div className="finding-evidence-summary">
                          {finding.evidence?.slice(0, 3).map((evidence) => (
                            <span key={evidence.id}>
                              {evidence.label}
                            </span>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>

                <section className="detail-section detail-two-column">
                  <div>
                    <div className="section-title">
                      <h3>What would make this benign?</h3>
                    </div>

                    <ul className="checklist">
                      {selectedCase.what_would_make_this_benign?.map(
                        (item, index) => (
                          <li key={index}>{item}</li>
                        )
                      )}
                    </ul>
                  </div>

                  <div>
                    <div className="section-title">
                      <h3>Recommended human review</h3>
                    </div>

                    <ul className="checklist warning-list">
                      {selectedCase.recommended_human_review_actions?.map(
                        (item, index) => (
                          <li key={index}>{item}</li>
                        )
                      )}
                    </ul>
                  </div>
                </section>

                <section className="detail-section">
                  <div className="section-title">
                    <h3>Evidence index</h3>
                    <span>Traceable source records</span>
                  </div>

                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Evidence</th>
                          <th>Source</th>
                          <th>Observed</th>
                          <th>Correlation ID</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedCase.evidence?.map((evidence) => (
                          <tr key={evidence.id}>
                            <td>
                              <strong>{evidence.label}</strong>
                              <span>{evidence.detail}</span>
                            </td>
                            <td>
                              <code>{evidence.source_table}</code>
                              <small>{evidence.source_external_id}</small>
                            </td>
                            <td>{formatDate(evidence.observed_at)}</td>
                            <td>
                              {evidence.correlation_id ? (
                                <code>{evidence.correlation_id}</code>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="detail-section workflow-section">
                  <div className="section-title">
                    <div>
                      <p className="eyebrow">Analyst workflow</p>
                      <h3>Update case state</h3>
                    </div>

                    <span>
                      Assigned to:{" "}
                      <strong>
                        {selectedCase.assigned_to ?? "Unassigned"}
                      </strong>
                    </span>
                  </div>

                  <form
                    className="workflow-form"
                    onSubmit={handleWorkflowSave}
                  >
                    <label>
                      Analyst name
                      <input
                        value={analystName}
                        onChange={(event) =>
                          setAnalystName(event.target.value)
                        }
                      />
                    </label>

                    <label>
                      Status
                      <select
                        value={workflowStatus}
                        onChange={(event) =>
                          setWorkflowStatus(event.target.value)
                        }
                      >
                        <option value="open">Open</option>
                        <option value="under_review">Under review</option>
                        <option value="contained">Contained</option>
                        <option value="closed">Closed</option>
                        <option value="insufficient_evidence">
                          Insufficient evidence
                        </option>
                      </select>
                    </label>

                    <label>
                      Disposition
                      <select
                        value={workflowDisposition}
                        onChange={(event) =>
                          setWorkflowDisposition(event.target.value)
                        }
                      >
                        <option value="needs_review">Needs review</option>
                        <option value="likely_benign">Likely benign</option>
                        <option value="suspicious">Suspicious</option>
                        <option value="confirmed_malicious">
                          Confirmed malicious
                        </option>
                        <option value="contained">Contained</option>
                        <option value="insufficient_data">
                          Insufficient data
                        </option>
                      </select>
                    </label>

                    <label>
                      Assign to
                      <input
                        placeholder="Cloud Identity Review Queue"
                        value={assignedTo}
                        onChange={(event) =>
                          setAssignedTo(event.target.value)
                        }
                      />
                    </label>

                    <label className="workflow-note">
                      Analyst note
                      <textarea
                        placeholder="Record the investigation decision, evidence reviewed, or containment recommendation."
                        value={workflowNote}
                        onChange={(event) =>
                          setWorkflowNote(event.target.value)
                        }
                      />
                    </label>

                    <button
                      className="primary-button"
                      type="submit"
                      disabled={workflowSaving}
                    >
                      {workflowSaving
                        ? "Saving workflow..."
                        : "Save workflow update"}
                    </button>
                  </form>

                  {selectedCase.activities?.length ? (
                    <div className="activity-log">
                      <h4>Review history</h4>

                      {selectedCase.activities.map((activity) => (
                        <article className="activity-item" key={activity.id}>
                          <div>
                            <strong>{capitalize(activity.activity_type)}</strong>
                            <span>{formatDate(activity.created_at)}</span>
                          </div>

                          <p>
                            {activity.actor_name}
                            {activity.assigned_to
                              ? ` assigned to ${activity.assigned_to}`
                              : ""}
                          </p>

                          {activity.note && <blockquote>{activity.note}</blockquote>}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">
                      No analyst workflow activity has been recorded yet.
                    </p>
                  )}
                </section>
              </>
            ) : (
              <EmptyState
                title="Select an investigation case"
                description="Import an evidence bundle or choose a case from the triage queue to inspect its findings and evidence."
              />
            )}
          </article>
        </section>
      </main>
    </div>
  );
}