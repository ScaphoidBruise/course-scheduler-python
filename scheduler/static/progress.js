var alertBox = document.getElementById("alertBox");
var logoutBtn = document.getElementById("logoutBtn");

var GRADE_OPTIONS = [
    "A", "A-", "B+", "B", "B-",
    "C+", "C", "C-", "D+", "D",
    "P", "CR", "S",
];
var completedCourseCodes = {};
var inProgressCourseCodes = {};

function showAlert(message, type) {
    if (!alertBox) return;
    var div = document.createElement("div");
    div.className = "alert alert-" + type + " alert-dismissible fade show py-2 mb-2";
    div.innerHTML = message + '<button type="button" class="btn-close btn-sm" data-bs-dismiss="alert"></button>';
    alertBox.appendChild(div);
    setTimeout(function () { div.remove(); }, 6000);
}

function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function fmt(n, digits) {
    if (n === null || n === undefined || n === "" || isNaN(Number(n))) return "—";
    return Number(n).toFixed(digits == null ? 1 : digits);
}

function normalizeCourseCode(code) {
    return String(code || "").trim().replace(/\s+/g, " ").toUpperCase();
}

function bootstrapInstance() {
    return (typeof bootstrap !== "undefined") ? bootstrap : null;
}

if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
        fetch("/api/logout", { method: "POST" })
            .then(function () {
                window.location.href = "/account";
            });
    });
}

function loadMe() {
    return fetch("/api/me")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data || !data.authenticated) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            return data.user;
        });
}

function setHeroFromOverview(o) {
    var earnedEl = document.getElementById("progressCreditsEarned");
    var targetEl = document.getElementById("progressCreditsTarget");
    var percentEl = document.getElementById("progressPercentNumber");
    var bar = document.getElementById("progressHeroBar");
    var majorPill = document.getElementById("progressMajorPill");
    var minorPill = document.getElementById("progressMinorPill");
    var targetInput = document.getElementById("progressTargetInput");
    var emptyTranscript = document.getElementById("progressEmptyTranscript");
    var emptyMajor = document.getElementById("progressEmptyMajor");
    var transferNote = document.getElementById("progressTransferNote");
    var subjectSelect = document.getElementById("progressCourseSubjectSelect");
    var targetStatus = document.getElementById("progressTargetStatus");

    var earned = (o && o.credits_completed != null) ? Number(o.credits_completed) : 0;
    var target = (o && o.credits_target != null) ? Number(o.credits_target) : 120;
    var pct = (o && o.percent_complete != null) ? Number(o.percent_complete) : 0;
    var isCatalogTarget = !!(o && o.credits_target_source === "scraped_program_requirements");

    if (earnedEl) earnedEl.textContent = fmt(earned, earned % 1 === 0 ? 0 : 1);
    if (targetEl) targetEl.textContent = String(target);
    if (percentEl) percentEl.textContent = pct.toFixed(0) + "%";
    if (bar) {
        bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
        bar.setAttribute("aria-valuenow", String(pct));
    }
    if (majorPill) {
        majorPill.textContent = "Major: " + (o && o.major ? o.major : "—");
        majorPill.classList.toggle("bg-light", true);
    }
    if (minorPill) {
        minorPill.textContent = "Minor: " + (o && o.minor ? o.minor : "—");
    }
    if (targetInput && target > 0) {
        targetInput.value = String(target);
        targetInput.disabled = isCatalogTarget;
    }
    var targetButton = document.querySelector("#progressTargetForm button[type='submit']");
    if (targetButton) targetButton.disabled = isCatalogTarget;
    if (targetStatus) {
        targetStatus.textContent = isCatalogTarget
            ? "Catalog target: " + String(target) + " credits"
            : "";
    }
    if (subjectSelect && !subjectSelect.value && o && o.scope_subjects && o.scope_subjects.length) {
        subjectSelect.value = o.scope_subjects[0];
    }
    if (emptyTranscript) emptyTranscript.classList.toggle("d-none", !!(o && o.has_transcript));
    if (emptyMajor) emptyMajor.classList.toggle("d-none", !!(o && o.major));
    if (transferNote) transferNote.classList.toggle("d-none", !(o && Number(o.transfer_credits || 0) > 0));
}

function requirementStatusLabel(status) {
    if (status === "complete") return "Complete";
    if (status === "partial") return "In progress";
    if (status === "choose") return "Choose option";
    if (status === "optional") return "Optional";
    return "Missing/incomplete";
}

function requirementTypeText(type, minCredits) {
    if (type === "choice_option") return "Track or option";
    if (type === "choose_from") return minCredits ? "Choose " + fmt(minCredits, minCredits % 1 === 0 ? 0 : 1) + " credits" : "Choose from list";
    if (type === "optional") return "Optional";
    return "Required";
}

function renderRequirementCourses(courses) {
    if (!courses || !courses.length) {
        return '<p class="text-muted small mb-0">No specific courses listed.</p>';
    }
    var html = '<div class="progress-audit-course-list">';
    for (var i = 0; i < courses.length; i++) {
        var course = courses[i] || {};
        var status = course.status || "remaining";
        var action = "";
        if (status === "completed") {
            action = '<span class="progress-remaining-status-badge progress-remaining-status-completed">Completed</span>';
        } else if (status === "in_progress") {
            action = '<span class="progress-remaining-status-badge progress-remaining-status-in-progress">In progress</span>';
        } else {
            action =
                '<button type="button" class="btn btn-sm btn-accent progress-reference-mark-complete" ' +
                'data-course-code="' + escapeHtml(course.course_code || "") + '">Mark complete</button>';
        }
        html +=
            '<div class="progress-audit-course-row progress-audit-course-' + escapeHtml(status) + '">' +
            '<div class="min-w-0">' +
            '<div class="progress-audit-course-code">' + escapeHtml(course.course_code || "Course") + '</div>' +
            '<div class="progress-audit-course-title">' + escapeHtml(course.course_title || "Untitled course") + '</div>' +
            '</div>' +
            action +
            '</div>';
    }
    html += "</div>";
    return html;
}

function renderRequirementBlockBody(block) {
    if (block.requirement_type === "choose_from") {
        return renderRequirementCourses(block.courses || []);
    }
    return renderRequirementCourses(block.courses || []);
}

function renderRequirementAudit(blocks, programInfo) {
    var el = document.getElementById("progressRequirementAudit");
    var sourceEl = document.getElementById("progressRequirementSource");
    var summaryEl = document.getElementById("progressAuditSummary");
    if (!el) return;
    blocks = blocks || [];
    if (sourceEl) {
        if (programInfo && programInfo.program_name) {
            sourceEl.innerHTML =
                'Matched to <span class="fw-semibold text-navy-deep">' + escapeHtml(programInfo.program_name) + '</span>' +
                (programInfo.degree_total_credits ? " · " + escapeHtml(fmt(programInfo.degree_total_credits, 0)) + " credits" : "");
        } else {
            sourceEl.textContent = "No scraped catalog match yet. Set your major on Profile.";
        }
    }
    if (!blocks.length) {
        el.innerHTML =
            '<div class="progress-audit-empty">' +
            '<div class="fw-semibold mb-1">No requirement audit available yet.</div>' +
            '<div class="text-muted small">Upload a transcript and choose a major so Progress can match catalog requirements.</div>' +
            '</div>';
        if (summaryEl) summaryEl.innerHTML = "";
        return;
    }

    if (summaryEl) {
        summaryEl.textContent = "Exact course matches only";
    }

    var html = '<div class="progress-audit-list">';
    for (var i = 0; i < blocks.length; i++) {
        var block = blocks[i] || {};
        if (Number(block.level || 0) <= 2 && block.min_credits) {
            html +=
                '<div class="progress-audit-section-title">' +
                '<span>' + escapeHtml(block.heading || "Requirement section") + '</span>' +
                '<strong>' + escapeHtml(fmt(block.min_credits, Number(block.min_credits) % 1 === 0 ? 0 : 1)) + ' credits</strong>' +
                '</div>';
        }
        if (!block.course_count && block.status !== "optional" && block.status !== "choose") continue;
        var minCredits = Number(block.min_credits || 0);
        html +=
            '<article class="progress-audit-block">' +
            '<div class="progress-audit-block-top">' +
            '<div class="min-w-0">' +
            '<div class="progress-audit-block-title">' + escapeHtml(block.heading || "Requirement") + '</div>' +
            '<div class="progress-audit-block-meta">' +
            escapeHtml(requirementTypeText(block.requirement_type, minCredits)) +
            (minCredits ? ' · ' + escapeHtml(fmt(minCredits, minCredits % 1 === 0 ? 0 : 1)) + ' credits' : '') +
            '</div>' +
            '</div>' +
            '</div>' +
            renderRequirementBlockBody(block) +
            '</article>';
    }
    html += "</div>";
    el.innerHTML = html;
}

function renderCompletedRows(rows) {
    var el = document.getElementById("progressCompletedContent");
    var countEl = document.getElementById("progressCompletedCount");
    if (!el) return;
    completedCourseCodes = {};
    for (var c = 0; c < (rows || []).length; c++) {
        var completedCode = normalizeCourseCode((rows[c] || {}).course_code || (rows[c] || {}).course);
        if (completedCode) completedCourseCodes[completedCode] = true;
    }
    if (countEl) countEl.textContent = rows && rows.length ? rows.length + " course" + (rows.length === 1 ? "" : "s") : "";
    if (!rows || !rows.length) {
        el.innerHTML = '<p class="text-muted mb-0">No completed courses yet.</p>';
        return;
    }
    var html =
        '<div class="table-responsive"><table class="table table-sm align-middle progress-completed-table mb-0">' +
        '<thead><tr>' +
        '<th>Term</th><th>Course</th><th>Title</th>' +
        '<th class="text-end">Attempted</th><th class="text-end">Grade</th><th class="text-end">Earned</th>' +
        '<th class="text-end"></th>' +
        '</tr></thead><tbody>';
    for (var i = 0; i < rows.length; i++) {
        var r = rows[i] || {};
        var code = r.course_code || r.course || "—";
        var title = r.course_name ? escapeHtml(r.course_name) : "—";
        var term = r.term || "—";
        var grade = r.grade || "—";
        var attempted = r.attempted == null ? "—" : fmt(r.attempted, 1);
        var earned = r.earned == null ? "—" : fmt(r.earned, 1);
        var actionCell = "";
        if (r.override_id) {
            actionCell =
                '<button type="button" class="btn btn-sm btn-outline-danger progress-completed-remove" ' +
                'data-override-id="' + escapeHtml(r.override_id) + '" ' +
                'data-course-code="' + escapeHtml(code) + '" ' +
                'aria-label="Remove ' + escapeHtml(code) + ' override">Remove</button>';
        } else {
            actionCell =
                '<span class="text-muted small" title="From transcript" data-bs-toggle="tooltip">From transcript</span>';
        }
        html +=
            '<tr><td class="text-nowrap">' + escapeHtml(term) +
            '</td><td class="fw-semibold text-nowrap">' + escapeHtml(code) +
            '</td><td class="small">' + title +
            '</td><td class="text-end">' + attempted +
            '</td><td class="text-end">' + escapeHtml(grade) +
            '</td><td class="text-end">' + earned +
            '</td><td class="text-end">' + actionCell + '</td></tr>';
    }
    html += "</tbody></table></div>";
    el.innerHTML = html;
    enableTooltips(el);
}

function renderInProgressRows(rows) {
    var el = document.getElementById("progressInProgressContent");
    var countEl = document.getElementById("progressInProgressCount");
    if (!el) return;
    inProgressCourseCodes = {};
    for (var p = 0; p < (rows || []).length; p++) {
        var progressCode = normalizeCourseCode((rows[p] || {}).course_code || (rows[p] || {}).course);
        if (progressCode) inProgressCourseCodes[progressCode] = true;
    }
    if (countEl) countEl.textContent = rows && rows.length ? rows.length + " course" + (rows.length === 1 ? "" : "s") : "";
    if (!rows || !rows.length) {
        el.innerHTML = '<p class="text-muted mb-0">No in-progress courses detected.</p>';
        return;
    }
    var html = '<ul class="list-group list-group-flush progress-in-progress-list">';
    for (var i = 0; i < rows.length; i++) {
        var r = rows[i] || {};
        var code = r.course_code || r.course || "Course";
        var title = r.course_name ? escapeHtml(r.course_name) : "";
        var term = r.term ? '<span class="text-muted small ms-2">' + escapeHtml(r.term) + "</span>" : "";
        html +=
            '<li class="list-group-item px-0 d-flex justify-content-between align-items-center gap-3">' +
            '<div class="min-w-0">' +
            '<div class="fw-semibold">' + escapeHtml(code) + term + "</div>" +
            (title ? '<div class="text-muted small">' + title + "</div>" : "") +
            "</div>" +
            '<span class="badge progress-in-progress-badge">In progress</span>' +
            "</li>";
    }
    html += "</ul>";
    el.innerHTML = html;
}

function gradeSelectHtml() {
    var html = '<select class="form-select form-select-sm progress-popover-grade" aria-label="Grade">';
    html += '<option value="">No grade</option>';
    for (var i = 0; i < GRADE_OPTIONS.length; i++) {
        var g = GRADE_OPTIONS[i];
        html += '<option value="' + escapeHtml(g) + '">' + escapeHtml(g) + "</option>";
    }
    html += "</select>";
    return html;
}

function inlineGradeSelectHtml() {
    return gradeSelectHtml().replace("progress-popover-grade", "progress-course-result-grade");
}

function postCompletedOverride(courseCode, grade) {
    return fetch("/api/completed-overrides", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ course_code: courseCode, grade: grade || "" }),
    }).then(function (r) {
        return r.text().then(function (text) {
            var body = {};
            try { body = text ? JSON.parse(text) : {}; } catch (err) { body = {}; }
            if (!r.ok) throw new Error(body.error || "Could not mark course completed.");
            return body;
        });
    });
}

function renderCourseSearchResults(rows) {
    var resultsEl = document.getElementById("progressCourseSearchResults");
    var statusEl = document.getElementById("progressCourseSearchStatus");
    if (!resultsEl) return;
    rows = rows || [];
    if (statusEl) statusEl.textContent = rows.length ? rows.length + " result" + (rows.length === 1 ? "" : "s") + " found." : "No matching courses found.";
    if (!rows.length) {
        resultsEl.innerHTML = "";
        return;
    }
    var html = "";
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i] || {};
        var code = row.course_code || "";
        var title = row.course_name || "";
        var normalized = normalizeCourseCode(code);
        var state = "";
        var action = '<div class="progress-course-result-action">' +
            inlineGradeSelectHtml() +
            '<button type="button" class="btn btn-sm btn-accent progress-course-result-add" data-course-code="' + escapeHtml(code) + '">Mark completed</button>' +
            '</div>';
        if (completedCourseCodes[normalized]) {
            state = '<span class="badge text-bg-success">Already completed</span>';
            action = state;
        } else if (inProgressCourseCodes[normalized]) {
            state = '<span class="badge text-bg-primary">In progress</span>';
            action = state;
        }
        html += '<div class="list-group-item d-flex justify-content-between align-items-start gap-3 progress-course-result-item">' +
            '<div class="min-w-0">' +
            '<div class="fw-semibold">' + escapeHtml(code) + '</div>' +
            '<div class="text-muted small">' + escapeHtml(title || "Untitled course") + '</div>' +
            '</div>' +
            action +
            '</div>';
    }
    resultsEl.innerHTML = html;
}

function searchProgressCourses(query) {
    var statusEl = document.getElementById("progressCourseSearchStatus");
    var subjectEl = document.getElementById("progressCourseSubjectSelect");
    var subject = subjectEl ? subjectEl.value.trim().toUpperCase() : "";
    var params = new URLSearchParams();
    if (query) params.set("search", query);
    if (subject) params.set("subject", subject);
    if (statusEl) statusEl.textContent = "Searching...";
    return fetch("/api/completion-course-search?" + params.toString())
        .then(function (r) {
            if (!r.ok) throw new Error("course-search");
            return r.json();
        })
        .then(renderCourseSearchResults)
        .catch(function () {
            if (statusEl) statusEl.textContent = "Could not search courses.";
        });
}

function enableTooltips(scope) {
    var bs = bootstrapInstance();
    if (!bs || !bs.Tooltip) return;
    var nodes = scope.querySelectorAll('[data-bs-toggle="tooltip"]');
    for (var i = 0; i < nodes.length; i++) {
        try { bs.Tooltip.getOrCreateInstance(nodes[i]); } catch (e) { /* noop */ }
    }
}

var openPopoverEl = null;

function enablePopovers(scope) {
    var bs = bootstrapInstance();
    if (!bs || !bs.Popover) return;
    var nodes = scope.querySelectorAll('[data-bs-toggle="popover"]');
    for (var i = 0; i < nodes.length; i++) {
        try { bs.Popover.getOrCreateInstance(nodes[i]); } catch (e) { /* noop */ }
    }
}

document.addEventListener("click", function (e) {
    var pill = e.target && e.target.closest ? e.target.closest(".progress-remaining-pill[data-bs-toggle='popover']") : null;
    var bs = bootstrapInstance();
    if (pill) {
        if (!bs || !bs.Popover) return;
        var instance = bs.Popover.getOrCreateInstance(pill);
        if (openPopoverEl && openPopoverEl !== pill) {
            try { bs.Popover.getOrCreateInstance(openPopoverEl).hide(); } catch (err) { /* noop */ }
        }
        if (openPopoverEl === pill) {
            instance.hide();
            openPopoverEl = null;
        } else {
            instance.show();
            openPopoverEl = pill;
        }
        return;
    }
    var save = e.target && e.target.closest ? e.target.closest(".progress-popover-save") : null;
    if (save) {
        e.preventDefault();
        var code = save.getAttribute("data-course-code") || "";
        var popoverBody = save.closest(".popover-body") || save.parentElement;
        var grade = "";
        if (popoverBody) {
            var sel = popoverBody.querySelector(".progress-popover-grade");
            if (sel) grade = sel.value;
        }
        save.disabled = true;
        postCompletedOverride(code, grade)
            .then(function () {
                showAlert("Marked " + escapeHtml(code) + " as completed.", "success");
                if (openPopoverEl) {
                    try { bs.Popover.getOrCreateInstance(openPopoverEl).hide(); } catch (err) { /* noop */ }
                    openPopoverEl = null;
                }
                return loadAll();
            })
            .catch(function () {
                save.disabled = false;
                showAlert("Could not mark " + escapeHtml(code) + " as completed.", "danger");
            });
        return;
    }
    var addCourseBtn = e.target && e.target.closest ? e.target.closest(".progress-course-result-add") : null;
    if (addCourseBtn) {
        e.preventDefault();
        var addCode = addCourseBtn.getAttribute("data-course-code") || "";
        var resultItem = addCourseBtn.closest(".progress-course-result-item");
        var gradeInput = resultItem ? resultItem.querySelector(".progress-course-result-grade") : null;
        var addGrade = gradeInput ? gradeInput.value : "";
        addCourseBtn.disabled = true;
        postCompletedOverride(addCode, addGrade)
            .then(function () {
                showAlert("Marked " + escapeHtml(addCode) + " as completed.", "success");
                renderCourseSearchResults([]);
                var searchInput = document.getElementById("progressCourseSearchInput");
                if (searchInput) searchInput.value = "";
                return loadAll();
            })
            .catch(function (err) {
                addCourseBtn.disabled = false;
                showAlert(escapeHtml(err.message || ("Could not mark " + addCode + " as completed.")), "danger");
            });
        return;
    }
    var referenceCompleteBtn = e.target && e.target.closest ? e.target.closest(".progress-reference-mark-complete") : null;
    if (referenceCompleteBtn) {
        e.preventDefault();
        var referenceCode = referenceCompleteBtn.getAttribute("data-course-code") || "";
        if (!referenceCode) return;
        referenceCompleteBtn.disabled = true;
        postCompletedOverride(referenceCode, "")
            .then(function () {
                showAlert("Marked " + escapeHtml(referenceCode) + " as completed.", "success");
                return loadAll();
            })
            .catch(function (err) {
                referenceCompleteBtn.disabled = false;
                showAlert(escapeHtml(err.message || ("Could not mark " + referenceCode + " as completed.")), "danger");
            });
        return;
    }
    var removeBtn = e.target && e.target.closest ? e.target.closest(".progress-completed-remove") : null;
    if (removeBtn) {
        e.preventDefault();
        var overrideId = removeBtn.getAttribute("data-override-id");
        var courseCode = removeBtn.getAttribute("data-course-code") || "";
        if (!overrideId) return;
        if (!window.confirm("Remove the manual completion of " + courseCode + "?")) return;
        removeBtn.disabled = true;
        fetch("/api/completed-overrides/" + encodeURIComponent(overrideId), { method: "DELETE" })
            .then(function (r) {
                if (!r.ok) throw new Error("remove");
                return r.json();
            })
            .then(function () {
                showAlert("Removed override for " + escapeHtml(courseCode) + ".", "success");
                return loadAll();
            })
            .catch(function () {
                removeBtn.disabled = false;
                showAlert("Could not remove the override.", "danger");
            });
    }
});

function loadOverview() {
    return fetch("/api/degree-progress/overview")
        .then(function (r) {
            if (!r.ok) throw new Error("overview");
            return r.json();
        })
        .then(setHeroFromOverview);
}

function loadDetail() {
    return fetch("/api/degree-progress")
        .then(function (r) {
            if (!r.ok) throw new Error("degree-progress");
            return r.json();
        })
        .then(function (data) {
            renderCompletedRows(data.completed || []);
            renderInProgressRows(data.in_progress || []);
            renderRequirementAudit(data.requirement_audit || [], data.program_requirements || null);
        });
}

function loadAll() {
    return Promise.all([loadOverview(), loadDetail()]).catch(function () {
        showAlert("Could not load degree progress.", "danger");
    });
}

var targetForm = document.getElementById("progressTargetForm");
if (targetForm) {
    targetForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var input = document.getElementById("progressTargetInput");
        var status = document.getElementById("progressTargetStatus");
        if (!input) return;
        var value = parseInt(input.value, 10);
        if (!value || value <= 0 || value > 300) {
            if (status) status.textContent = "Enter a target between 1 and 300.";
            return;
        }
        if (status) status.textContent = "Saving…";
        fetch("/api/planner-target", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credits_target: value }),
        })
            .then(function (r) {
                if (!r.ok) throw new Error("target");
                return r.json();
            })
            .then(function () {
                if (status) status.textContent = "Saved.";
                setTimeout(function () { if (status) status.textContent = ""; }, 2400);
                return loadOverview();
            })
            .catch(function () {
                if (status) status.textContent = "Could not save target.";
            });
    });
}

var courseSearchForm = document.getElementById("progressCourseSearchForm");
if (courseSearchForm) {
    courseSearchForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var input = document.getElementById("progressCourseSearchInput");
        var subjectInput = document.getElementById("progressCourseSubjectSelect");
        var statusEl = document.getElementById("progressCourseSearchStatus");
        var query = input ? input.value.trim() : "";
        var subject = subjectInput ? subjectInput.value.trim() : "";
        if (query.length < 2 && subject.length < 2) {
            if (statusEl) statusEl.textContent = "Enter at least 2 search characters or a degree abbreviation.";
            return;
        }
        searchProgressCourses(query);
    });
}

function loadProgressCourseSubjects() {
    var subjectSelect = document.getElementById("progressCourseSubjectSelect");
    if (!subjectSelect) return Promise.resolve();
    return fetch("/api/course-subjects")
        .then(function (r) {
            if (!r.ok) throw new Error("subjects");
            return r.json();
        })
        .then(function (subjects) {
            for (var i = 0; i < subjects.length; i++) {
                var opt = document.createElement("option");
                opt.value = subjects[i];
                opt.textContent = subjects[i];
                subjectSelect.appendChild(opt);
            }
        })
        .catch(function () {
            return null;
        });
}

loadMe()
    .then(function () {
        return loadProgressCourseSubjects().then(loadAll);
    })
    .catch(function (err) {
        if (err && err.message === "Unauthorized") return;
        showAlert("Could not load progress data.", "danger");
    });
