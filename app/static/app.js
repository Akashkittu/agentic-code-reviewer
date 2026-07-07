let activeTab = "local";
let lastResult = null;
let activeSeverity = "all";

const severityOrder = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
};

const severityLabels = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
    info: "Info",
};

const tabs = document.querySelectorAll(".tab");
const tabBodies = document.querySelectorAll(".tab-body");
const runBtn = document.getElementById("runBtn");
const loading = document.getElementById("loading");
const results = document.getElementById("results");
const errorBox = document.getElementById("errorBox");
const findingSearch = document.getElementById("findingSearch");
const findingSort = document.getElementById("findingSort");
const copySummaryBtn = document.getElementById("copySummaryBtn");
const downloadJsonBtn = document.getElementById("downloadJsonBtn");

tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        activeTab = tab.dataset.tab;

        tabs.forEach((item) => item.classList.remove("active"));
        tab.classList.add("active");

        tabBodies.forEach((body) => {
            body.classList.toggle("active", body.id === activeTab);
        });
    });
});

runBtn.addEventListener("click", runReview);
copySummaryBtn.addEventListener("click", copyCleanSummary);
downloadJsonBtn.addEventListener("click", downloadResultJson);

findingSearch.addEventListener("input", refreshFindings);
findingSort.addEventListener("change", refreshFindings);

document.querySelectorAll(".filter").forEach((button) => {
    button.addEventListener("click", () => {
        setActiveSeverity(button.dataset.severity || "all");
    });
});

function showLoading() {
    loading.classList.remove("hidden");
    results.classList.add("hidden");
    errorBox.classList.add("hidden");
    runBtn.disabled = true;
    runBtn.textContent = "Running…";
}

function hideLoading() {
    loading.classList.add("hidden");
    runBtn.disabled = false;
    runBtn.textContent = "Run Review";
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

async function runReview() {
    showLoading();

    try {
        const maxIterations = Number(document.getElementById("maxIterations").value || 8);
        validateInput(maxIterations);

        let response;

        if (activeTab === "zip") {
            const fileInput = document.getElementById("zipFile");
            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("max_iterations", String(maxIterations));

            response = await fetch("/api/review-upload", {
                method: "POST",
                body: formData,
            });
        } else {
            const payload = {
                max_iterations: maxIterations,
            };

            if (activeTab === "local") {
                payload.repo_path = document.getElementById("repoPath").value.trim();
            }

            if (activeTab === "github") {
                payload.repo_url = document.getElementById("repoUrl").value.trim();
            }

            response = await fetch("/api/review", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(formatApiError(data));
        }

        lastResult = normalizeResult(data);
        activeSeverity = "all";
        findingSearch.value = "";
        findingSort.value = "priority";
        renderResults(lastResult);
    } catch (error) {
        showError(error.message || "Something went wrong.");
    } finally {
        hideLoading();
    }
}

function validateInput(maxIterations) {
    if (!Number.isInteger(maxIterations) || maxIterations < 1 || maxIterations > 8) {
        throw new Error("Iterations must be 1–8.");
    }

    if (activeTab === "local") {
        const repoPath = document.getElementById("repoPath").value.trim();
        if (!repoPath) {
            throw new Error("Enter local path.");
        }
    }

    if (activeTab === "github") {
        const repoUrl = document.getElementById("repoUrl").value.trim();
        if (!repoUrl) {
            throw new Error("Enter GitHub URL.");
        }
    }

    if (activeTab === "zip") {
        const fileInput = document.getElementById("zipFile");
        if (!fileInput.files.length) {
            throw new Error("Choose a ZIP file.");
        }
    }
}


async function copyCleanSummary() {
    if (!lastResult) {
        return;
    }

    const topFindings = sortFindings(lastResult.findings || [], "priority")
        .slice(0, 5)
        .map((finding, index) => `${index + 1}. [${String(finding.severity || "info").toUpperCase()}] ${finding.issue} — ${finding.suggested_fix}`)
        .join("\n");

    const text = [
        `Type: ${lastResult.repo_type || "Unknown"}`,
        `Score: ${lastResult.overall_score ?? "--"}/100`,
        `Findings: ${(lastResult.findings || []).length}`,
        "",
        "Summary:",
        lastResult.project_summary || "No summary.",
        "",
        "Top fixes:",
        topFindings || "No priority issues.",
        "",
        "Final recommendation:",
        lastResult.final_recommendation || "No recommendation.",
    ].join("\n");

    await navigator.clipboard.writeText(text);
    copySummaryBtn.textContent = "Copied!";
    setTimeout(() => {
        copySummaryBtn.textContent = "Copy summary";
    }, 1400);
}

function downloadResultJson() {
    if (!lastResult) {
        return;
    }

    const blob = new Blob([JSON.stringify(lastResult, null, 2)], {
        type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "code-review-result.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function formatApiError(data) {
    if (data.detail) {
        if (Array.isArray(data.detail)) {
            return data.detail.map((item) => item.msg || JSON.stringify(item)).join(", ");
        }

        return String(data.detail);
    }

    return "Request failed.";
}

function normalizeResult(data) {
    const findings = Array.isArray(data.findings) ? data.findings : [];
    const normalizedFindings = findings.map((finding) => ({
        ...finding,
        severity: String(finding.severity || "info").toLowerCase(),
        importance_percent: Number(finding.importance_percent || 0),
    }));

    return {
        ...data,
        findings: normalizedFindings,
    };
}

function renderResults(data) {
    results.classList.remove("hidden");

    const score = Number(data.overall_score ?? 0);
    const scoreText = data.overall_score === null || data.overall_score === undefined
        ? "--"
        : `${score}/100`;
    const counts = getSeverityCounts(data.findings || []);
    const risk = getRiskLabel(counts, score);

    document.getElementById("resultTitle").textContent = `${risk.label} review result`;
    document.getElementById("overallScore").textContent = scoreText;
    const scoreRing = document.getElementById("scoreRing");
    scoreRing.style.setProperty("--score", `${Math.min(Math.max(score, 0), 100)}%`);
    scoreRing.className = `score-ring ${risk.className}`;

    document.getElementById("repoType").textContent = data.repo_type || "Unknown";
    document.getElementById("repoFileCount").textContent = `Files: ${data.repo_files_count ?? "--"}`;
    document.getElementById("totalFindings").textContent = data.findings?.length || 0;
    document.getElementById("riskLabel").textContent = `Risk: ${risk.label}`;
    document.getElementById("llmStatus").textContent =
        data.planner_llm_provider || "not_used";

    const finalReportMode =
        data.final_report_llm_status === "success"
            ? "LLM generated"
            : "Rule-based";

    document.getElementById("fallbackMode").textContent =
        `Final report: ${finalReportMode} · Fallback: ${data.fallback_mode ? "Yes" : "No"}`;
    document.getElementById("toolsExecuted").textContent = data.tool_results?.length || 0;

    document.getElementById("projectSummary").textContent =
        data.project_summary || "No summary.";

    document.getElementById("finalRecommendation").textContent =
        data.final_recommendation || "No recommendation.";

    const llmReview = data.llm_review || {};
    document.getElementById("llmReview").textContent =
        llmReview.text || "No LLM text.";

    renderPriorityList(data.findings || []);
    renderSeverityBreakdown(counts);
    renderPlannerTrace(data.planner_decisions || []);
    renderToolTrace(data.tool_results || []);
    updateFilterButtons();
    refreshFindings();
}

function getSeverityCounts(findings) {
    return {
        critical: findings.filter((finding) => finding.severity === "critical").length,
        high: findings.filter((finding) => finding.severity === "high").length,
        medium: findings.filter((finding) => finding.severity === "medium").length,
        low: findings.filter((finding) => finding.severity === "low").length,
        info: findings.filter((finding) => finding.severity === "info").length,
    };
}

function getRiskLabel(counts, score) {
    if (counts.critical > 0 || score < 40) {
        return { label: "Critical", className: "critical" };
    }

    if (counts.high > 0 || score < 60) {
        return { label: "High priority", className: "high" };
    }

    if (counts.medium > 0 || score < 75) {
        return { label: "Needs improvement", className: "medium" };
    }

    return { label: "Healthy", className: "passed" };
}

function renderPriorityList(findings) {
    const container = document.getElementById("priorityList");
    container.innerHTML = "";

    const topFindings = sortFindings(findings, "priority").slice(0, 5);

    if (!topFindings.length) {
        container.innerHTML = `
            <div class="empty-state">
                <strong>No priority issues.</strong>
                <span>Looks clean from current checks.</span>
            </div>
        `;
        return;
    }

    topFindings.forEach((finding, index) => {
        const item = document.createElement("article");
        item.className = `priority-item ${finding.severity}`;
        item.dataset.tooltip = "Sorted by severity and importance.";
        item.innerHTML = `
            <div class="priority-rank">${index + 1}</div>
            <div>
                <div class="priority-title-row">
                    <h3>${escapeHtml(finding.issue || "Untitled issue")}</h3>
                    <span class="badge ${escapeHtml(finding.severity)}">${escapeHtml(finding.severity)}</span>
                </div>
                <p>${escapeHtml(finding.suggested_fix || "No fix provided.")}</p>
                <span class="finding-meta">${formatLocation(finding)} · ${escapeHtml(finding.category || "unknown")}</span>
            </div>
        `;
        container.appendChild(item);
    });
}

function renderSeverityBreakdown(counts) {
    const container = document.getElementById("severityBreakdown");
    container.innerHTML = "";

    const hints = {
        critical: "Fix now",
        high: "High priority",
        medium: "Important",
        low: "Cleanup",
        info: "Info only",
    };

    Object.keys(counts).forEach((severity) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `severity-card ${severity}`;
        button.dataset.severity = severity;
        button.dataset.tooltip = `Show only ${severityLabels[severity].toLowerCase()} findings`;
        button.innerHTML = `
            <span>${severityLabels[severity]}</span>
            <strong>${counts[severity]}</strong>
            <small>${hints[severity]}</small>
        `;
        button.addEventListener("click", () => setActiveSeverity(severity));
        container.appendChild(button);
    });
}

function setActiveSeverity(severity) {
    activeSeverity = severity;
    updateFilterButtons();
    refreshFindings();
}

function updateFilterButtons() {
    document.querySelectorAll(".filter").forEach((button) => {
        button.classList.toggle("active", button.dataset.severity === activeSeverity);
    });

    document.querySelectorAll(".severity-card").forEach((button) => {
        button.classList.toggle("active", button.dataset.severity === activeSeverity);
    });
}

function refreshFindings() {
    if (!lastResult) {
        return;
    }

    renderFindings(
        lastResult.findings || [],
        activeSeverity,
        findingSearch.value.trim().toLowerCase(),
        findingSort.value,
    );
}

function renderPlannerTrace(decisions) {
    const container = document.getElementById("plannerTrace");
    container.innerHTML = "";

    if (!decisions.length) {
        container.innerHTML = "<p class='muted'>No planner steps.</p>";
        return;
    }

    decisions.forEach((item) => {
        const div = document.createElement("div");
        div.className = "timeline-item";

        div.innerHTML = `
            <div class="timeline-badge">Iter ${escapeHtml(item.iteration ?? "-")}</div>
            <div>
                <div class="timeline-tool">${escapeHtml(item.next_tool || "No tool")}</div>
                <div class="finding-meta">Source: ${escapeHtml(item.source || "unknown")}</div>
                <div class="timeline-reason">${escapeHtml(item.reason || "No reason.")}</div>
            </div>
        `;

        container.appendChild(div);
    });
}

function renderToolTrace(tools) {
    const container = document.getElementById("toolTrace");
    container.innerHTML = "";

    if (!tools.length) {
        container.innerHTML = "<p class='muted'>No tools run.</p>";
        return;
    }

    tools.forEach((tool) => {
        const div = document.createElement("div");
        div.className = "tool-item";

        const status = String(tool.status || "unknown").toLowerCase();

        div.innerHTML = `
            <div>
                <div class="tool-name">${escapeHtml(tool.tool_name || "Unknown tool")}</div>
                <div class="tool-summary">${escapeHtml(tool.summary || "No summary.")}</div>
            </div>
            <span class="badge ${escapeHtml(status)}">${escapeHtml(status)}</span>
        `;

        container.appendChild(div);
    });
}

function renderFindings(findings, severityFilter, searchTerm, sortMode) {
    const container = document.getElementById("findingsList");
    container.innerHTML = "";

    let filtered = severityFilter === "all"
        ? findings
        : findings.filter((finding) => finding.severity === severityFilter);

    if (searchTerm) {
        filtered = filtered.filter((finding) => {
            const searchable = [
                finding.issue,
                finding.file,
                finding.category,
                finding.why_it_matters,
                finding.suggested_fix,
                finding.source_tool,
            ].join(" ").toLowerCase();
            return searchable.includes(searchTerm);
        });
    }

    filtered = sortFindings(filtered, sortMode);

    if (!filtered.length) {
        container.innerHTML = `
            <div class="empty-state">
                <strong>No matches.</strong>
                <span>Change filter or search.</span>
            </div>
        `;
        return;
    }

    filtered.forEach((finding) => {
        const severity = finding.severity || "info";
        const details = document.createElement("details");
        details.className = `finding-card ${severity}`;
        details.dataset.tooltip = "Click to expand.";
        details.open = severity === "critical" || severity === "high";

        details.innerHTML = `
            <summary>
                <div>
                    <div class="finding-title">${escapeHtml(finding.issue || "Untitled issue")}</div>
                    <div class="finding-meta">
                        ${escapeHtml(finding.category || "unknown")} ·
                        ${escapeHtml(formatLocation(finding))} ·
                        Importance ${escapeHtml(String(finding.importance_percent || 0))}%
                    </div>
                </div>
                <span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>
            </summary>

            <div class="finding-body">
                <p><strong>Why:</strong> ${escapeHtml(finding.why_it_matters || "No explanation.")}</p>
                <div class="fix">
                    <strong>Fix:</strong>
                    <span>${escapeHtml(finding.suggested_fix || "No fix provided.")}</span>
                </div>
                <div class="source-line">Tool: ${escapeHtml(finding.source_tool || "unknown")}</div>
            </div>
        `;

        container.appendChild(details);
    });
}

function sortFindings(findings, sortMode) {
    const cloned = [...findings];

    if (sortMode === "severity") {
        return cloned.sort((a, b) => severityRank(b) - severityRank(a));
    }

    if (sortMode === "file") {
        return cloned.sort((a, b) => String(a.file || "").localeCompare(String(b.file || "")));
    }

    if (sortMode === "category") {
        return cloned.sort((a, b) => String(a.category || "").localeCompare(String(b.category || "")));
    }

    return cloned.sort((a, b) => {
        const severityDiff = severityRank(b) - severityRank(a);
        if (severityDiff !== 0) {
            return severityDiff;
        }
        return Number(b.importance_percent || 0) - Number(a.importance_percent || 0);
    });
}

function severityRank(finding) {
    return severityOrder[finding.severity] || 0;
}

function formatLocation(finding) {
    const file = finding.file || "Repo";
    const line = finding.line ? `:${finding.line}` : "";
    return `${file}${line}`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
