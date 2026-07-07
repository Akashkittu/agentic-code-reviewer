let activeTab = "local";
let lastResult = null;

const tabs = document.querySelectorAll(".tab");
const tabBodies = document.querySelectorAll(".tab-body");
const runBtn = document.getElementById("runBtn");
const loading = document.getElementById("loading");
const results = document.getElementById("results");
const errorBox = document.getElementById("errorBox");

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

document.querySelectorAll(".filter").forEach((button) => {
    button.addEventListener("click", () => {
        document.querySelectorAll(".filter").forEach((item) => {
            item.classList.remove("active");
        });

        button.classList.add("active");

        if (lastResult) {
            renderFindings(lastResult.findings || [], button.dataset.severity);
        }
    });
});

function showLoading() {
    loading.classList.remove("hidden");
    results.classList.add("hidden");
    errorBox.classList.add("hidden");
    runBtn.disabled = true;
    runBtn.textContent = "Running...";
}

function hideLoading() {
    loading.classList.add("hidden");
    runBtn.disabled = false;
    runBtn.textContent = "Run Agentic Review";
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

async function runReview() {
    showLoading();

    try {
        const maxIterations = Number(document.getElementById("maxIterations").value || 8);

        let response;

        if (activeTab === "zip") {
            const fileInput = document.getElementById("zipFile");

            if (!fileInput.files.length) {
                throw new Error("Please choose a ZIP file first.");
            }

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

        lastResult = data;
        renderResults(data);
    } catch (error) {
        showError(error.message || "Something went wrong.");
    } finally {
        hideLoading();
    }
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

function renderResults(data) {
    results.classList.remove("hidden");

    document.getElementById("overallScore").textContent =
        data.overall_score === null || data.overall_score === undefined
            ? "--"
            : `${data.overall_score}/100`;

    document.getElementById("repoType").textContent = data.repo_type || "Unknown repo";
    document.getElementById("totalFindings").textContent = data.findings?.length || 0;
    document.getElementById("llmStatus").textContent = data.llm_status || "--";
    document.getElementById("fallbackMode").textContent = `Fallback: ${data.fallback_mode}`;
    document.getElementById("toolsExecuted").textContent = data.tool_results?.length || 0;

    document.getElementById("projectSummary").textContent =
        data.project_summary || "No project summary generated.";

    document.getElementById("finalRecommendation").textContent =
        data.final_recommendation || "No final recommendation generated.";

    const llmReview = data.llm_review || {};
    document.getElementById("llmReview").textContent =
        llmReview.text ||
        "No LLM review text available. This may happen if fallback mode was used.";

    renderPlannerTrace(data.planner_decisions || []);
    renderToolTrace(data.tool_results || []);

    const activeFilter =
        document.querySelector(".filter.active")?.dataset.severity || "all";

    renderFindings(data.findings || [], activeFilter);
}

function renderPlannerTrace(decisions) {
    const container = document.getElementById("plannerTrace");
    container.innerHTML = "";

    if (!decisions.length) {
        container.innerHTML = "<p>No planner decisions recorded.</p>";
        return;
    }

    decisions.forEach((item) => {
        const div = document.createElement("div");
        div.className = "timeline-item";

        div.innerHTML = `
            <div class="timeline-badge">Iter ${escapeHtml(item.iteration)}</div>
            <div>
                <div class="timeline-tool">${escapeHtml(item.next_tool || "")}</div>
                <div class="finding-meta">Source: ${escapeHtml(item.source || "unknown")}</div>
                <div class="timeline-reason">${escapeHtml(item.reason || "")}</div>
            </div>
        `;

        container.appendChild(div);
    });
}

function renderToolTrace(tools) {
    const container = document.getElementById("toolTrace");
    container.innerHTML = "";

    if (!tools.length) {
        container.innerHTML = "<p>No tools executed.</p>";
        return;
    }

    tools.forEach((tool) => {
        const div = document.createElement("div");
        div.className = "tool-item";

        const status = (tool.status || "unknown").toLowerCase();

        div.innerHTML = `
            <div>
                <div class="tool-name">${escapeHtml(tool.tool_name || "")}</div>
                <div class="tool-summary">${escapeHtml(tool.summary || "")}</div>
            </div>
            <span class="badge ${status}">${escapeHtml(status)}</span>
        `;

        container.appendChild(div);
    });
}

function renderFindings(findings, severityFilter) {
    const container = document.getElementById("findingsList");
    container.innerHTML = "";

    const filtered = severityFilter === "all"
        ? findings
        : findings.filter((finding) => finding.severity === severityFilter);

    if (!filtered.length) {
        container.innerHTML = "<p>No findings for this filter.</p>";
        return;
    }

    filtered.forEach((finding) => {
        const severity = finding.severity || "info";
        const file = finding.file || "N/A";
        const line = finding.line ? `:${finding.line}` : "";

        const div = document.createElement("div");
        div.className = `finding-card ${severity}`;

        div.innerHTML = `
            <div class="finding-top">
                <div>
                    <div class="finding-title">${escapeHtml(finding.issue || "")}</div>
                    <div class="finding-meta">
                        ${escapeHtml(finding.category || "unknown")} ·
                        ${escapeHtml(file)}${escapeHtml(line)} ·
                        Importance ${escapeHtml(String(finding.importance_percent || 0))}%
                    </div>
                </div>
                <span class="badge ${severity}">${escapeHtml(severity)}</span>
            </div>

            <p><strong>Why it matters:</strong> ${escapeHtml(finding.why_it_matters || "")}</p>

            <div class="fix">
                <strong>Suggested fix:</strong>
                ${escapeHtml(finding.suggested_fix || "")}
            </div>
        `;

        container.appendChild(div);
    });
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}