var alertBox = document.getElementById("alertBox");
var logoutBtn = document.getElementById("logoutBtn");

var GRADE_OPTIONS = [
    "A", "A-", "B+", "B", "B-",
    "C+", "C", "C-", "D+", "D",
    "P", "CR", "S",
];

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
    var remainingEl = document.getElementById("progressRemainingNumber");
    var percentEl = document.getElementById("progressPercentNumber");
    var bar = document.getElementById("progressHeroBar");
    var majorPill = document.getElementById("progressMajorPill");
    var minorPill = document.getElementById("progressMinorPill");
    var scopeNote = document.getElementById("progressScopeNote");
    var targetInput = document.getElementById("progressTargetInput");
    var emptyTranscript = document.getElementById("progressEmptyTranscript");
    var emptyMajor = document.getElementById("progressEmptyMajor");

    var earned = (o && o.credits_completed != null) ? Number(o.credits_completed) : 0;
    var target = (o && o.credits_target != null) ? Number(o.credits_target) : 120;
    var pct = (o && o.percent_complete != null) ? Number(o.percent_complete) : 0;
    var remaining = (o && o.courses_remaining_count != null) ? Number(o.courses_remaining_count) : 0;

    if (earnedEl) earnedEl.textContent = fmt(earned, earned % 1 === 0 ? 0 : 1);
    if (targetEl) targetEl.textContent = String(target);
    if (remainingEl) remainingEl.textContent = String(remaining);
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
    if (scopeNote) {
        var subjects = (o && o.scope_subjects) || [];
        scopeNote.textContent = subjects.length
            ? "Scope: " + subjects.join(", ")
            : "";
    }
    if (targetInput && target > 0) targetInput.value = String(target);
    if (emptyTranscript) emptyTranscript.classList.toggle("d-none", !!(o && o.has_transcript));
    if (emptyMajor) emptyMajor.classList.toggle("d-none", !!(o && o.major));
}

function renderCompletedRows(rows) {
    var el = document.getElementById("progressCompletedContent");
    var countEl = document.getElementById("progressCompletedCount");
    if (!el) return;
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

function renderRemainingAccordion(grouped) {
    var el = document.getElementById("progressRemainingContent");
    if (!el) return;
    grouped = grouped || {};
    var seasons = ["Spring", "Summer", "Fall", "Unscheduled"];
    var totalCount = 0;
    var sectionsHtml = "";
    for (var i = 0; i < seasons.length; i++) {
        var season = seasons[i];
        var rows = grouped[season] || [];
        totalCount += rows.length;
        var paneId = "progressRemaining-" + season.toLowerCase();
        var headingId = paneId + "-heading";
        var collapsed = i !== 0;
        sectionsHtml +=
            '<div class="accordion-item">' +
            '<h2 class="accordion-header" id="' + headingId + '">' +
            '<button class="accordion-button' + (collapsed ? " collapsed" : "") + '" type="button" ' +
            'data-bs-toggle="collapse" data-bs-target="#' + paneId + '" ' +
            'aria-expanded="' + (!collapsed) + '" aria-controls="' + paneId + '">' +
            escapeHtml(season) + ' <span class="text-muted small ms-2">(' + rows.length + ')</span>' +
            '</button></h2>' +
            '<div id="' + paneId + '" class="accordion-collapse collapse' + (collapsed ? "" : " show") + '" ' +
            'aria-labelledby="' + headingId + '">' +
            '<div class="accordion-body">';
        if (!rows.length) {
            sectionsHtml += '<p class="text-muted small mb-0">Nothing remaining for this season.</p>';
        } else {
            sectionsHtml += '<div class="d-flex flex-wrap gap-2">';
            for (var j = 0; j < rows.length; j++) {
                var r = rows[j];
                var code = r.course_code || "Course";
                var title = r.course_name ? r.course_name : "";
                var content =
                    '<div class="progress-popover-form">' +
                    '<div class="mb-2 small text-muted">' + escapeHtml(title || code) + "</div>" +
                    '<label class="form-label small mb-1">Grade</label>' +
                    gradeSelectHtml() +
                    '<button type="button" class="btn btn-accent btn-sm w-100 mt-2 progress-popover-save" ' +
                    'data-course-code="' + escapeHtml(code) + '">Mark as completed</button>' +
                    "</div>";
                sectionsHtml +=
                    '<button type="button" class="progress-remaining-pill btn btn-sm btn-outline-secondary" ' +
                    'data-bs-toggle="popover" data-bs-trigger="manual" data-bs-html="true" ' +
                    'data-bs-placement="top" data-bs-content="' + escapeHtml(content) + '" ' +
                    'data-bs-title="' + escapeHtml(code) + '" ' +
                    'data-course-code="' + escapeHtml(code) + '" ' +
                    'title="' + escapeHtml(title || "") + '">' +
                    escapeHtml(code) +
                    "</button>";
            }
            sectionsHtml += "</div>";
        }
        sectionsHtml += "</div></div></div>";
    }
    if (!totalCount) {
        el.innerHTML = '<p class="text-muted mb-0">No remaining catalog courses found for the detected program subjects.</p>';
        return;
    }
    el.innerHTML = '<div class="accordion progress-remaining-accordion">' + sectionsHtml + "</div>";
    enablePopovers(el);
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
    var pill = e.target && e.target.closest ? e.target.closest(".progress-remaining-pill") : null;
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
        fetch("/api/completed-overrides", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ course_code: code, grade: grade || "" }),
        })
            .then(function (r) {
                if (!r.ok) throw new Error("override");
                return r.json();
            })
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
            renderRemainingAccordion(data.remaining_by_typical_term || {});
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

loadMe()
    .then(loadAll)
    .catch(function (err) {
        if (err && err.message === "Unauthorized") return;
        showAlert("Could not load progress data.", "danger");
    });
