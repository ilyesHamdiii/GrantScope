const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  "http://localhost:8000/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const rawBody = await response.text();

  let data = null;

  try {
    data = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    data = rawBody;
  }

  if (!response.ok) {
    const detail =
      typeof data === "object" && data?.detail
        ? data.detail
        : typeof data === "string" && data
          ? data
          : `Request failed with HTTP ${response.status}`;

    throw new Error(detail);
  }

  return data;
}

function queryString(parameters) {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(parameters)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  }

  const text = query.toString();

  return text ? `?${text}` : "";
}

export function getDatabaseStatus() {
  return request("/system/database");
}

export function getImportRuns() {
  return request("/import-runs");
}

export function getCases(importRunId) {
  return request(
    `/cases${queryString({
      import_run_id: importRunId
    })}`
  );
}

export function getCaseDetail(caseId) {
  return request(`/cases/${caseId}`);
}

export function uploadEvidenceBundle(file) {
  const formData = new FormData();
  formData.append("file", file);

  return request("/imports/bundle", {
    method: "POST",
    body: formData
  });
}

export function analyzeImportRun(importRunId) {
  return request(`/import-runs/${importRunId}/analyze`, {
    method: "POST"
  });
}

export function generateCases(importRunId) {
  return request(`/import-runs/${importRunId}/cases/generate`, {
    method: "POST"
  });
}

export function updateCaseWorkflow(caseId, payload) {
  return request(`/cases/${caseId}/workflow`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function reportUrl(caseId, format) {
  return `${API_BASE}/cases/${caseId}/report/${format}`;
}