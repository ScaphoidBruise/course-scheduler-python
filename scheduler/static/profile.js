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
        var g =
            c.grade !== null && c.grade !== undefined && c.grade !== ""
                ? c.grade
                : "—";
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
            fmtNum(c.attempted, 1) +
            " cr · " +
            g +
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

function renderProfile(data) {
    var p = data.profile || {};
    var tp = p.transcript_parsed || null;

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

    document.getElementById("transcriptFileMeta").textContent =
        p.has_transcript && p.transcript_original_name
            ? "Current file: " + p.transcript_original_name
            : "No file uploaded yet.";

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

}

function loadProfile() {
    return fetch("/api/profile")
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
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
            showAlert("Transcript uploaded and parsed.", "success");
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

loadProfile().catch(function () {});
