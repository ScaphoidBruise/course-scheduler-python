var alertBox = document.getElementById("alertBox");
var logoutBtn = document.getElementById("logoutBtn");

/** Names from SQLite reference table (/api/academic-programs); fall back to [] on error. */
var academicProgramNames = [];
var suppressProgramAutosave = false;
var programSaveTimer = null;
var PROGRAM_SAVE_MS = 900;

function showAlert(message, type) {
    var div = document.createElement("div");
    div.className = "alert alert-" + type + " alert-dismissible fade show py-2 mb-2";
    div.innerHTML = message + '<button type="button" class="btn-close btn-sm" data-bs-dismiss="alert"></button>';
    alertBox.appendChild(div);
    setTimeout(function () { div.remove(); }, 6000);
}

function fmtNum(n, digits) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toFixed(digits);
}

/** API may return transcript as object; coerce string JSON if needed. */
function parseTranscriptObject(raw) {
    if (!raw) return null;
    if (typeof raw === "string") {
        try {
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }
    if (typeof raw === "object") return raw;
    return null;
}

/** Credits / hrs: show 0.0, not an em dash, when value is zero. */
function numForDisplay(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    var n = Number(v);
    if (isNaN(n)) return "—";
    return n.toFixed(digits);
}

/** Letter grade: allow string or number from odd PDF layouts. */
function formatGrade(c) {
    if (!c) return "—";
    var g = c.grade;
    if (g === null || g === undefined) {
        g = c.Grade;
    }
    if (g === null || g === undefined) return "—";
    var s = String(g).trim();
    if (s === "") return "—";
    return escapeHtml(s);
}

function formatProfileTimestamp(raw) {
    if (!raw) return "";
    var s = String(raw).trim();
    var norm = s.indexOf("T") === -1 ? s.replace(" ", "T") : s;
    var d = new Date(norm);
    if (!isNaN(d.getTime())) {
        return d.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    }
    return s;
}

function revealProfileChrome(data) {
    var u = data.user || {};
    var welcomeEl = document.getElementById("profileWelcome");
    var blurbEl = document.getElementById("profileBlurb");
    var updatedLine = document.getElementById("profileUpdatedLine");
    if (welcomeEl) {
        welcomeEl.textContent = u.username
            ? "Welcome back, " + u.username
            : "Academic profile";
    }
    if (blurbEl) {
        blurbEl.textContent =
            "Upload your unofficial transcript (PDF) to import GPA and courses. " +
            "Use the Edit buttons on Major or Minor to update your declared program.";
    }
    var p = data.profile || {};
    if (updatedLine) {
        var ts = formatProfileTimestamp(p.updated_at);
        updatedLine.textContent = ts ? "Saved data · " + ts : "";
        updatedLine.classList.toggle("d-none", !ts);
    }
    document.getElementById("profileLoadingRow").classList.add("d-none");
    document.getElementById("profileHeroLoaded").classList.remove("d-none");
    var body = document.getElementById("profileBodyContent");
    body.classList.remove("d-none");
    body.setAttribute("aria-busy", "false");
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function formatEnrollmentGrade(c) {
    if (!c) {
        return "In progress";
    }
    var g = c.grade;
    if (g === null || g === undefined) {
        g = c.Grade;
    }
    if (g === null || g === undefined) {
        return "In progress";
    }
    var s = String(g).trim();
    if (s === "") {
        return "In progress";
    }
    return escapeHtml(s);
}

function renderCourseList(courses) {
    var ul = '<ul class="list-group list-group-flush profile-enrollment-course-list">';
    for (var i = 0; i < courses.length; i++) {
        var c = courses[i];
        var code = c.course || (c.subject + " " + c.course_number);
        var title = c.course_name && String(c.course_name).trim();
        var left =
            '<div class="me-2 min-w-0">' +
            '<div class="fw-semibold">' +
            escapeHtml(code) +
            "</div>";
        if (title) {
            left +=
                '<div class="small text-muted">' +
                escapeHtml(title) +
                "</div>";
        }
        left += "</div>";
        var hours = numForDisplay(c.attempted, 1);
        var gradeRaw = formatEnrollmentGrade(c);
        var gradeHtml =
            gradeRaw === "In progress"
                ? '<span class="profile-grade-in-progress">In progress</span>'
                : gradeRaw;
        ul +=
            '<li class="list-group-item d-flex justify-content-between align-items-start px-0 profile-enrollment-course-item">' +
            left +
            '<div class="profile-enrollment-meta text-end flex-shrink-0 ms-2">' +
            '<span class="profile-enrollment-credits-pill" title="Attempted credit hours">' +
            '<span class="profile-enrollment-credits-value">' +
            hours +
            "</span>" +
            '<span class="profile-enrollment-credits-word">credits</span>' +
            "</span>" +
            '<span class="profile-enrollment-dot" aria-hidden="true">·</span>' +
            '<span class="profile-enrollment-grade">' +
            gradeHtml +
            "</span>" +
            "</div></li>";
    }
    ul += "</ul>";
    return ul;
}

function getTranscriptCourseRows(tp) {
    if (!tp) return { rows: [], partial: false };
    if (tp.course_history && tp.course_history.length) {
        return { rows: tp.course_history, partial: Boolean(tp.course_history_is_partial) };
    }
    var lt = tp.latest_term_courses || [];
    if (lt.length) {
        return { rows: lt, partial: true };
    }
    return { rows: [], partial: false };
}

function renderPastCredits(tp) {
    var el = document.getElementById("pastCreditsContent");
    var meta = document.getElementById("pastCreditsMeta");
    var pack = getTranscriptCourseRows(tp);
    var rows = pack.rows;
    var partial = pack.partial;
    var transferEarned = tp ? Number(tp.transfer_earned_total || 0) : 0;
    var transferNote = transferEarned > 0
        ? '<div class="alert alert-warning py-2 small mb-2" role="status">Transfer hours are counted in total credits, but individual transfer equivalents are not visible in this institutional course list. Use the Progress page to mark matching UTPB courses as completed.</div>'
        : "";
    if (!rows.length) {
        meta.textContent =
            "Institutional courses (UTPB) by term from the parsed transcript. Transfer work is summarized elsewhere.";
        el.innerHTML =
            transferNote +
            '<p class="text-muted mb-0">' +
            (!tp
                ? "No transcript data yet."
                : "No course rows found. Re-upload your unofficial transcript; use the PDF from your student portal (Banner / unofficial transcript).") +
            "</p>";
        return;
    }
    var note = "";
    if (partial) {
        note =
            '<div class="alert alert-info py-2 small mb-2" role="status">' +
            "<strong>Partial list.</strong> This profile was saved before full course history was stored, or only the current term " +
            "was parsed. <strong>Re-upload the same PDF</strong> (or a fresh copy) to load <strong>all terms</strong> in this table." +
            "</div>";
    }
    meta.textContent =
        rows.length +
        " course row(s) from the institutional section (completed and in-progress).";
    if (partial) {
        meta.textContent += " Older terms may be missing until you re-import the transcript.";
    }
    var html = transferNote + note;
    html +=
        '<div class="table-responsive"><table class="table table-sm table-hover mb-0 align-middle section-table"><thead><tr>' +
        "<th>Term</th><th>Course</th><th>Title</th>" +
        '<th class="text-end">Attempted</th><th class="text-end">Grade</th><th class="text-end">Earned</th>' +
        "</tr></thead><tbody>";
    for (var i = 0; i < rows.length; i++) {
        var c = rows[i];
        var code =
            c.course ||
            (c.subject && c.course_number ? c.subject + " " + c.course_number : "—");
        var title =
            c.course_name && String(c.course_name).trim()
                ? escapeHtml(String(c.course_name).trim())
                : "—";
        html +=
            '<tr><td class="text-nowrap">' +
            escapeHtml(c.term || "—") +
            '</td><td class="fw-semibold text-nowrap">' +
            escapeHtml(code) +
            '</td><td class="small">' +
            title +
            '</td><td class="text-end">' +
            numForDisplay(c.attempted, 1) +
            '</td><td class="text-end">' +
            formatGrade(c) +
            '</td><td class="text-end">' +
            numForDisplay(c.earned, 1) +
            "</td></tr>";
    }
    html += "</tbody></table></div>";
    el.innerHTML = html;
}

var majorComboInput = document.getElementById("majorComboInput");
var minorComboInput = document.getElementById("minorComboInput");
var majorComboMenu = document.getElementById("majorComboMenu");
var minorComboMenu = document.getElementById("minorComboMenu");
var majorFieldStatus = document.getElementById("majorFieldStatus");
var minorFieldStatus = document.getElementById("minorFieldStatus");
var majorDisplay = document.getElementById("majorDisplay");
var minorDisplay = document.getElementById("minorDisplay");
var majorDisplayWrap = document.getElementById("majorDisplayWrap");
var minorDisplayWrap = document.getElementById("minorDisplayWrap");
var majorEditWrap = document.getElementById("majorEditWrap");
var minorEditWrap = document.getElementById("minorEditWrap");
var majorEditToggleBtn = document.getElementById("majorEditToggleBtn");
var minorEditToggleBtn = document.getElementById("minorEditToggleBtn");
var programFieldsEditing = false;
/** True until save finishes after user chooses "Done editing". */
var pendingCloseProgramFields = false;

function filterProgramMatches(query) {
    var q = (query || "").trim().toLowerCase();
    var list = academicProgramNames.filter(function (n) {
        if (!q) return true;
        return String(n).toLowerCase().indexOf(q) !== -1;
    });
    return list.slice(0, 52);
}

function fillComboMenu(menu, items, prefix, activeIdx, onPick) {
    menu.innerHTML = "";
    menu.removeAttribute("hidden");
    for (var i = 0; i < items.length; i++) {
        var btn = document.createElement("button");
        btn.type = "button";
        var oid = prefix + "-" + i;
        btn.id = oid;
        btn.setAttribute("role", "option");
        btn.className = "list-group-item list-group-item-action py-2 px-3 profile-combobox-item text-start border-0";
        btn.textContent = items[i];
        if (activeIdx === i) {
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
        } else {
            btn.setAttribute("aria-selected", "false");
        }
        (function (pick) {
            btn.addEventListener("mousedown", function (ev) {
                ev.preventDefault();
                onPick(pick);
            });
        })(items[i]);
        menu.appendChild(btn);
    }
}

function bindProgramCombobox(opts) {
    var input = opts.inputEl;
    var menu = opts.menuEl;
    var comboPrefix = opts.idPrefix || "combo";
    var highlighted = -1;
    var blurTimer = null;
    var lastMatches = [];

    function hide() {
        menu.innerHTML = "";
        menu.classList.add("d-none");
        menu.setAttribute("hidden", "");
        highlighted = -1;
        input.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
    }

    function showItems(items) {
        lastMatches = items;
        highlighted = Math.min(items.length > 0 ? 0 : -1, items.length - 1);
        if (!items.length) {
            hide();
            return;
        }
        fillComboMenu(menu, items, comboPrefix, highlighted, function (chosen) {
            input.value = chosen;
            hide();
            scheduleProgramSave();
            input.blur();
        });
        menu.classList.remove("d-none");
        menu.removeAttribute("hidden");
        input.setAttribute("aria-expanded", "true");
        if (items.length && highlighted >= 0) {
            input.setAttribute("aria-activedescendant", comboPrefix + "-" + highlighted);
            renderHighlight();
        }
    }

    function renderHighlight() {
        var btns = menu.querySelectorAll(".profile-combobox-item");
        var i = 0;
        for (; i < btns.length; i++) {
            btns[i].classList.toggle("active", i === highlighted);
            btns[i].setAttribute("aria-selected", i === highlighted ? "true" : "false");
        }
        if (highlighted >= 0 && highlighted < btns.length) {
            input.setAttribute("aria-activedescendant", comboPrefix + "-" + highlighted);
        }
    }

    function openOrRefreshFromInput() {
        var filtered = filterProgramMatches(input.value);
        showItems(filtered);
    }

    input.addEventListener("focus", function () {
        if (blurTimer) clearTimeout(blurTimer);
        openOrRefreshFromInput();
    });

    input.addEventListener("input", function () {
        openOrRefreshFromInput();
        scheduleProgramSave();
    });

    input.addEventListener("keydown", function (e) {
        if (menu.classList.contains("d-none") || lastMatches.length === 0) {
            if ((e.key === "ArrowDown" || e.key === "ArrowUp") && input === document.activeElement) {
                openOrRefreshFromInput();
            }
            return;
        }
        if (e.key === "ArrowDown") {
            e.preventDefault();
            highlighted = Math.min(highlighted + 1, lastMatches.length - 1);
            renderHighlight();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            highlighted = Math.max(highlighted - 1, 0);
            renderHighlight();
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (highlighted >= 0 && highlighted < lastMatches.length) {
                input.value = lastMatches[highlighted];
                hide();
                scheduleProgramSave();
            }
        } else if (e.key === "Escape") {
            e.preventDefault();
            hide();
        }
    });

    input.addEventListener("blur", function () {
        blurTimer = setTimeout(function () {
            hide();
        }, 180);
    });
}

function setProgramDisplayValue(textEl, wrapEl, raw) {
    var trimmed = "";
    if (raw !== null && raw !== undefined) {
        trimmed = String(raw).trim();
    }
    var empty = !trimmed;
    if (textEl) {
        textEl.textContent = empty ? "Not set" : trimmed;
        textEl.classList.toggle("profile-program-display-text-empty", empty);
    }
    if (wrapEl) {
        wrapEl.classList.toggle("profile-program-display-empty", empty);
    }
}

function syncStaticProgramDisplaysFromInputs() {
    if (!majorComboInput || !minorComboInput) return;
    setProgramDisplayValue(majorDisplay, majorDisplayWrap, majorComboInput.value);
    setProgramDisplayValue(minorDisplay, minorDisplayWrap, minorComboInput.value);
}

function syncStaticProgramDisplaysFromProfile(p) {
    var maj = p && p.major !== null && p.major !== undefined ? String(p.major) : "";
    var minr = p && p.minor !== null && p.minor !== undefined ? String(p.minor) : "";
    setProgramDisplayValue(majorDisplay, majorDisplayWrap, maj);
    setProgramDisplayValue(minorDisplay, minorDisplayWrap, minr);
}

function applyProgramFieldsUI() {
    var ed = programFieldsEditing;
    if (majorDisplayWrap && majorEditWrap) {
        majorDisplayWrap.classList.toggle("d-none", ed);
        majorEditWrap.classList.toggle("d-none", !ed);
    }
    if (minorDisplayWrap && minorEditWrap) {
        minorDisplayWrap.classList.toggle("d-none", ed);
        minorEditWrap.classList.toggle("d-none", !ed);
    }
    if (majorComboInput) {
        majorComboInput.tabIndex = ed ? 0 : -1;
    }
    if (minorComboInput) {
        minorComboInput.tabIndex = ed ? 0 : -1;
    }
    if (majorFieldStatus) {
        majorFieldStatus.classList.toggle("d-none", !ed);
    }
    if (minorFieldStatus) {
        minorFieldStatus.classList.toggle("d-none", !ed);
    }
    syncProgramToggleButtons(ed);
}

function syncProgramToggleButtons(ed) {
    var labelDone = !!ed;
    var buttons = [majorEditToggleBtn, minorEditToggleBtn];
    for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        if (!btn) continue;
        btn.textContent = labelDone ? "Done" : "Edit";
        btn.setAttribute("aria-expanded", labelDone ? "true" : "false");
        btn.classList.toggle("btn-accent", labelDone);
        btn.classList.toggle("btn-outline-accent", !labelDone);
    }
}

/** @param pref "minor" to focus minor when opening from minor card */
function openProgramFieldsEdit(pref) {
    if (programFieldsEditing) return;
    programFieldsEditing = true;
    applyProgramFieldsUI();
    var focusEl =
        pref === "minor"
            ? minorComboInput || majorComboInput
            : majorComboInput || minorComboInput;
    if (focusEl) {
        try {
            focusEl.focus();
        } catch (e) {
            /* noop */
        }
    }
}

function closeProgramFieldsEdit() {
    if (!programFieldsEditing) return;
    pendingCloseProgramFields = true;
    if (programSaveTimer) {
        clearTimeout(programSaveTimer);
        programSaveTimer = null;
    }
    flushProgramSave();
}

function setFieldStatuses(majorText, minorText) {
    if (majorFieldStatus) majorFieldStatus.textContent = majorText || "";
    if (minorFieldStatus) minorFieldStatus.textContent = minorText || "";
}

function flushProgramSave() {
    if (suppressProgramAutosave || !majorComboInput || !minorComboInput) {
        return;
    }
    var finalizeClose = pendingCloseProgramFields;
    if (!programFieldsEditing && !finalizeClose) {
        return;
    }
    var major = majorComboInput.value.trim();
    var minor = minorComboInput.value.trim();
    programSaveTimer = null;
    setFieldStatuses("Saving…", "Saving…");
    suppressProgramAutosave = true;
    fetch("/api/profile/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ major: major || "", minor: minor || "" }),
    })
        .then(function (r) {
            return r.json().then(function (body) {
                return { ok: r.ok, body: body };
            });
        })
        .then(function (res) {
            if (!res.ok || !res.body || res.body.ok !== true) {
                if (finalizeClose) {
                    pendingCloseProgramFields = false;
                }
                setFieldStatuses("", "");
                showAlert((res.body && res.body.error) ? res.body.error : "Could not save program.", "danger");
                return Promise.reject(new Error("save"));
            }
            if (finalizeClose) {
                programFieldsEditing = false;
                pendingCloseProgramFields = false;
            }
            return loadProfile();
        })
        .then(function () {
            setFieldStatuses("✓", "✓");
            setTimeout(function () {
                setFieldStatuses("", "");
            }, 2400);
        })
        .catch(function (err) {
            if (finalizeClose) {
                pendingCloseProgramFields = false;
            }
            if (err && err.message === "save") {
                return;
            }
            showAlert("Could not save profile info.", "danger");
            setFieldStatuses("", "");
        })
        .finally(function () {
            suppressProgramAutosave = false;
        });
}

function scheduleProgramSave() {
    if (!programFieldsEditing || suppressProgramAutosave || !majorComboInput || !minorComboInput) {
        return;
    }
    if (programSaveTimer) clearTimeout(programSaveTimer);
    programSaveTimer = setTimeout(flushProgramSave, PROGRAM_SAVE_MS);
}

function loadProgramNames() {
    return fetch("/api/academic-programs")
        .then(function (r) {
            if (!r.ok) throw new Error("programs");
            return r.json();
        })
        .then(function (names) {
            academicProgramNames = Array.isArray(names) ? names : [];
        })
        .catch(function () {
            academicProgramNames = [];
        });
}

// === WISHLIST (Agent 3) ===
function renderWishlistRows(rows) {
    var el = document.getElementById("wishlistContent");
    if (!el) return;
    if (!rows || !rows.length) {
        el.innerHTML =
            '<p class="text-muted mb-0">No wishlist courses yet. Add courses from the catalog detail view.</p>';
        return;
    }
    var html = '<ul class="list-group list-group-flush wishlist-list">';
    for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        html +=
            '<li class="list-group-item px-0 wishlist-item d-flex justify-content-between align-items-start gap-2">' +
            '<div class="min-w-0">' +
            '<div class="fw-semibold">' +
            escapeHtml(row.course_code || "") +
            "</div>" +
            '<div class="text-muted">' +
            escapeHtml(row.course_name || "") +
            "</div>";
        if (row.notes) {
            html += '<div class="wishlist-notes mt-1">' + escapeHtml(row.notes) + "</div>";
        }
        html +=
            "</div>" +
            '<button type="button" class="btn btn-link btn-sm text-danger wishlist-remove-btn" ' +
            'data-course-id="' +
            escapeHtml(row.course_id) +
            '" aria-label="Remove ' +
            escapeHtml(row.course_code || "course") +
            ' from wishlist">&times;</button>' +
            "</li>";
    }
    html += "</ul>";
    el.innerHTML = html;
}

function loadWishlistPanel() {
    var el = document.getElementById("wishlistContent");
    if (!el) return Promise.resolve();
    return fetch("/api/wishlist")
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            if (!r.ok) throw new Error("wishlist");
            return r.json();
        })
        .then(renderWishlistRows)
        .catch(function (err) {
            if (err && err.message === "Unauthorized") return;
            el.innerHTML = '<p class="text-danger mb-0">Could not load wishlist.</p>';
        });
}

document.addEventListener("click", function (e) {
    var btn = e.target.closest(".wishlist-remove-btn");
    if (!btn) return;
    fetch("/api/wishlist/" + encodeURIComponent(btn.getAttribute("data-course-id")), {
        method: "DELETE",
    })
        .then(function (r) {
            if (!r.ok) throw new Error("remove");
            return r.json();
        })
        .then(function (body) {
            renderWishlistRows(body.wishlist || []);
        })
        .catch(function () {
            showAlert("Could not remove that wishlist course.", "danger");
        });
});
// === END WISHLIST ===

function renderProfile(data) {
    var p = data.profile || {};
    var tp = parseTranscriptObject(p.transcript_parsed);

    if (majorComboInput) majorComboInput.value = p.major || "";
    if (minorComboInput) minorComboInput.value = p.minor || "";

    document.getElementById("statCumGpa").textContent = fmtNum(p.cumulative_gpa, 3);
    var termGpa =
        p.last_term_gpa !== null && p.last_term_gpa !== undefined
            ? p.last_term_gpa
            : tp && tp.last_term_gpa !== null && tp.last_term_gpa !== undefined
                ? tp.last_term_gpa
                : null;
    document.getElementById("statTermGpa").textContent = fmtNum(termGpa, 3);

    var ca = p.credits_attempted;
    var ce = p.credits_earned;
    if (ce !== null && ce !== undefined && ca !== null && ca !== undefined) {
        document.getElementById("statCredits").textContent =
            fmtNum(ce, 1) + " / " + fmtNum(ca, 1);
    } else {
        document.getElementById("statCredits").textContent = "—";
    }

    var transfer = tp ? tp.transfer_earned_total : null;
    var utpb = tp ? tp.utpb_credits_earned : null;
    var total = tp ? tp.total_credit_hours : null;
    var lower = tp ? tp.lower_level_credits_earned : null;
    var upper = tp ? tp.upper_level_credits_earned : null;
    document.getElementById("statTransferCredits").textContent = fmtNum(transfer, 1);
    document.getElementById("statUtpbCredits").textContent = fmtNum(utpb, 1);
    document.getElementById("statTotalCredits").textContent = fmtNum(total, 1);
    if (lower !== null && lower !== undefined && upper !== null && upper !== undefined) {
        document.getElementById("statLevelSplit").textContent =
            fmtNum(lower, 1) + " / " + fmtNum(upper, 1);
    } else {
        document.getElementById("statLevelSplit").textContent = "—";
    }

    var encEl = document.getElementById("enrollmentContent");
    if (!tp) {
        encEl.innerHTML =
            '<p class="text-muted mb-0">No transcript data yet.</p>';
    } else {
        var termLbl = tp.last_term_label || null;
        var enc = tp.enrolled_courses || [];
        if (!termLbl) {
            encEl.innerHTML =
                '<p class="text-muted mb-0">—</p>';
        } else if (!enc.length) {
            var latest = tp.latest_term_courses || [];
            if (latest.length) {
                encEl.innerHTML = renderCourseList(latest);
            } else {
                encEl.innerHTML =
                    '<p class="text-muted mb-0">No courses parsed for that term. The PDF text layout may not match expected Banner rows — try re-exporting the unofficial transcript.</p>';
            }
        } else {
            encEl.innerHTML = renderCourseList(enc);
        }
    }

    renderPastCredits(tp);
    // === WISHLIST (Agent 3) ===
    loadWishlistPanel();
    // === END WISHLIST ===

    document.getElementById("transcriptFileMeta").textContent =
        p.transcript_original_name
            ? "Last import: " + p.transcript_original_name
            : "No transcript on file. Upload a PDF to import grades and program info.";

    var warnEl = document.getElementById("warningsPanel");
    var warns = [];
    if (p.transcript_parsed && p.transcript_parsed.warnings) {
        warns = warns.concat(p.transcript_parsed.warnings);
    }
    if (warns.length) {
        warnEl.classList.remove("d-none");
        warnEl.innerHTML = "<strong>Note:</strong> " + warns.join(" ");
    } else {
        warnEl.classList.add("d-none");
        warnEl.innerHTML = "";
    }

    var tEl = document.getElementById("transcriptDetail");
    if (!tp) {
        tEl.innerHTML = '<p class="text-muted mb-0">No parsed transcript data yet.</p>';
    } else {
        var html = "";
        if (tp.majors_found && tp.majors_found.length) {
            html += "<p><strong>Majors (history):</strong> " + tp.majors_found.join(" → ") + "</p>";
        }
        if (tp.minors_found && tp.minors_found.length) {
            html += "<p><strong>Minors (history):</strong> " + tp.minors_found.join(" → ") + "</p>";
        }
        if (tp.terms && tp.terms.length) {
            html += "<p><strong>Terms seen:</strong> " + tp.terms.length + " (latest activity through "
                + tp.terms[tp.terms.length - 1] + ")</p>";
        }
        if (tp.transfer_earned_total !== null && tp.transfer_earned_total !== undefined) {
            html += "<p><strong>Transfer hours (earned / attempted):</strong> "
                + fmtNum(tp.transfer_earned_total, 1) + " / "
                + fmtNum(tp.transfer_attempted_total, 1) + "</p>";
            html += '<p class="text-muted small mb-0">Transfer hours count toward total credits, but course-level requirements need matching UTPB courses marked completed on the Progress page.</p>';
        }
        tEl.innerHTML = html || '<p class="text-muted mb-0">Transcript parsed; no extra summary lines.</p>';
    }

    syncStaticProgramDisplaysFromProfile(p);
    applyProgramFieldsUI();

    revealProfileChrome(data);
    loadDegreeOverview();
}

function loadProfile() {
    return fetch("/api/profile")
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            if (!r.ok) {
                throw new Error("Server returned HTTP " + r.status + ".");
            }
            return r.json();
        })
        .then(renderProfile);
}

function loadDegreeOverview() {
    var earnedEl = document.getElementById("overviewCreditsEarned");
    var targetEl = document.getElementById("overviewCreditsTarget");
    var bar = document.getElementById("overviewProgressBar");
    var scopeLine = document.getElementById("overviewScopeLine");
    var emptyState = document.getElementById("overviewEmptyState");
    if (!earnedEl || !targetEl || !bar) return;

    fetch("/api/degree-progress/overview")
        .then(function (r) {
            if (!r.ok) throw new Error("overview");
            return r.json();
        })
        .then(function (data) {
            var earned = data.credits_completed != null ? Number(data.credits_completed) : 0;
            var target = data.credits_target != null ? Number(data.credits_target) : 120;
            var pct = data.percent_complete != null ? Number(data.percent_complete) : 0;
            earnedEl.textContent = earned % 1 === 0 ? String(earned) : earned.toFixed(1);
            targetEl.textContent = String(target);
            bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
            bar.setAttribute("aria-valuenow", String(pct));
            if (scopeLine) {
                var pieces = [];
                if (data.major) pieces.push("Based on: " + data.major);
                if (data.transfer_note) pieces.push(data.transfer_note);
                scopeLine.textContent = pieces.join(" · ");
            }
            if (emptyState) {
                emptyState.classList.toggle("d-none", Boolean(data.has_transcript));
            }
        })
        .catch(function () {
            if (scopeLine) scopeLine.textContent = "Could not load progress overview.";
        });
}

document.getElementById("transcriptForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var inp = document.getElementById("transcriptFile");
    if (!inp.files || !inp.files[0]) {
        showAlert("Choose a PDF file first.", "warning");
        return;
    }
    var fd = new FormData();
    fd.append("file", inp.files[0]);
    fetch("/api/profile/transcript", { method: "POST", body: fd })
        .then(function (r) {
            return r.text().then(function (txt) {
                var body = {};
                try {
                    body = txt ? JSON.parse(txt) : {};
                } catch (ignore) {
                    body = { error: "Server returned a non-JSON response (HTTP " + r.status + ")." };
                }
                return { ok: r.ok, status: r.status, body: body };
            });
        })
        .then(function (res) {
            if (!res.ok) {
                showAlert(
                    res.body.error || ("Upload failed (HTTP " + res.status + ")."),
                    "danger"
                );
                return;
            }
            var seeded = res.body.seeded_schedule || {};
            var msg = "Transcript parsed; your profile was updated.";
            if (seeded.added_count > 0) {
                msg += " " + seeded.added_count + " current course" + (seeded.added_count === 1 ? "" : "s") +
                    " added to Schedule. Choose exact sections there if any do not appear on the calendar.";
            }
            showAlert(msg, "success");
            inp.value = "";
            programFieldsEditing = false;
            pendingCloseProgramFields = false;
            return loadProfile();
        })
        .catch(function (err) {
            showAlert(err && err.message ? err.message : "Upload failed (network error).", "danger");
        });
});

logoutBtn.addEventListener("click", function () {
    fetch("/api/logout", { method: "POST" })
        .then(function () {
            window.location.href = "/account";
        });
});

function wireProgramFieldToggle(btn, pref) {
    if (!btn) return;
    btn.addEventListener("click", function () {
        if (programFieldsEditing) {
            closeProgramFieldsEdit();
        } else {
            openProgramFieldsEdit(pref);
        }
    });
}

wireProgramFieldToggle(majorEditToggleBtn, "major");
wireProgramFieldToggle(minorEditToggleBtn, "minor");

loadProgramNames()
    .then(function () {
        if (majorComboInput && minorComboInput && majorComboMenu && minorComboMenu) {
            bindProgramCombobox({
                inputEl: majorComboInput,
                menuEl: majorComboMenu,
                idPrefix: "major-opt",
            });
            bindProgramCombobox({
                inputEl: minorComboInput,
                menuEl: minorComboMenu,
                idPrefix: "minor-opt",
            });
        }
        return loadProfile();
    })
    .catch(function (err) {
        if (err && err.message === "Unauthorized") return;
        document.getElementById("profileLoadingRow").classList.add("d-none");
        document.getElementById("profileHeroLoaded").classList.remove("d-none");
        document.getElementById("profileWelcome").textContent = "Could not load profile";
        document.getElementById("profileBlurb").textContent =
            err && err.message
                ? err.message
                : "Something went wrong. Check your connection and refresh this page.";
        document.getElementById("profileUpdatedLine").textContent = "";
        document.getElementById("profileUpdatedLine").classList.add("d-none");
        showAlert(
            err && err.message ? escapeHtml(err.message) : "Could not load profile data.",
            "danger"
        );
    });
