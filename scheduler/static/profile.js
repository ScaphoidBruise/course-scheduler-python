var alertBox = document.getElementById("alertBox");
var logoutBtn = document.getElementById("logoutBtn");
var editProgramBtn = document.getElementById("editProgramBtn");
var cancelProgramEditBtn = document.getElementById("cancelProgramEditBtn");
var programEditorCard = document.getElementById("programEditorCard");

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
            "Upload your unofficial transcript (PDF) to import GPA and courses. You can edit major or minor anytime.";
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

function renderCourseList(courses) {
    var ul = '<ul class="list-group list-group-flush">';
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
        ul +=
            '<li class="list-group-item d-flex justify-content-between align-items-start px-0">' +
            left +
            '<span class="text-muted text-nowrap flex-shrink-0">' +
            numForDisplay(c.attempted, 1) +
            " cr · " +
            formatGrade(c) +
            "</span></li>";
    }
    ul += "</ul>";
    return ul;
}

function openProgramEditor() {
    programEditorCard.classList.remove("d-none");
}

function closeProgramEditor() {
    programEditorCard.classList.add("d-none");
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
    if (!rows.length) {
        meta.textContent =
            "Institutional courses (UTPB) by term from the parsed transcript. Transfer work is summarized elsewhere.";
        el.innerHTML =
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
    var html = note;
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

function renderProfile(data) {
    var p = data.profile || {};
    var tp = parseTranscriptObject(p.transcript_parsed);

    document.getElementById("statMajor").textContent = p.major || "—";
    document.getElementById("statMinor").textContent = p.minor || "—";
    document.getElementById("majorInput").value = p.major || "";
    document.getElementById("minorInput").value = p.minor || "";
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
    var encMeta = document.getElementById("enrollmentMeta");
    if (!tp) {
        encMeta.textContent =
            "Upload a transcript to list courses that look in-progress on the latest term.";
        encEl.innerHTML =
            '<p class="text-muted mb-0">No transcript data yet.</p>';
    } else {
        var termLbl = tp.last_term_label || null;
        var enc = tp.enrolled_courses || [];
        encMeta.textContent = termLbl
            ? "Latest term on transcript: " +
              termLbl +
              ". Listed rows are courses without a final grade (or marked IP / I) on that term."
            : "No term headers found in the institutional section of this PDF; enrollment cannot be tied to a term.";
        if (!termLbl) {
            encEl.innerHTML =
                '<p class="text-muted mb-0">—</p>';
        } else if (!enc.length) {
            var latest = tp.latest_term_courses || [];
            if (latest.length) {
                encMeta.textContent =
                    "No in-progress rows detected; showing all courses parsed for " +
                    termLbl +
                    " (grades may already be final on this transcript).";
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

    document.getElementById("transcriptFileMeta").textContent =
        p.has_transcript && p.transcript_original_name
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
        }
        tEl.innerHTML = html || '<p class="text-muted mb-0">Transcript parsed; no extra summary lines.</p>';
    }

    revealProfileChrome(data);
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
            showAlert("Transcript parsed; your profile was updated.", "success");
            inp.value = "";
            return loadProfile();
        })
        .catch(function (err) {
            showAlert(err && err.message ? err.message : "Upload failed (network error).", "danger");
        });
});

document.getElementById("profileInfoForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var major = document.getElementById("majorInput").value.trim();
    var minor = document.getElementById("minorInput").value.trim();
    fetch("/api/profile/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ major: major, minor: minor })
    })
        .then(function (r) {
            return r.json().then(function (body) {
                return { ok: r.ok, body: body };
            });
        })
        .then(function (res) {
            if (!res.ok) {
                showAlert(res.body.error || "Could not save profile info.", "danger");
                return;
            }
            showAlert("Major/minor saved.", "success");
            closeProgramEditor();
            return loadProfile();
        })
        .catch(function () {
            showAlert("Could not save profile info.", "danger");
        });
});

editProgramBtn.addEventListener("click", function () {
    openProgramEditor();
});

cancelProgramEditBtn.addEventListener("click", function () {
    closeProgramEditor();
});

logoutBtn.addEventListener("click", function () {
    fetch("/api/logout", { method: "POST" })
        .then(function () {
            window.location.href = "/account";
        });
});

loadProfile().catch(function (err) {
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
