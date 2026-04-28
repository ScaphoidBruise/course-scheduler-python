var COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B",
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316",
    "#6366F1", "#06B6D4", "#84CC16", "#D946EF",
];
var DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
var DAY_CHARS  = ["M", "T", "W", "R", "F"];
var PX_PER_HOUR = 64;
var SHARE_DATA = window.SCHEDULE_SHARE_DATA || null;
var READ_ONLY_SCHEDULE = !!SHARE_DATA;

function storageKey(term) {
    return "schedule_" + term.replace(/\s+/g, "_");
}

var scheduleByTerm = {};
var scenariosByTerm = {};
var currentScenario = null;

function scheduleKey(term) {
    return term + "::" + (currentScenario && currentScenario.id ? currentScenario.id : "active");
}

function getScheduleIds(term) {
    return (scheduleByTerm[scheduleKey(term)] || []).slice();
}

function setScheduleIds(term, ids) {
    scheduleByTerm[scheduleKey(term)] = ids.slice();
}

function loadScheduleIds(term) {
    var url = "/api/my-schedule?term=" + encodeURIComponent(term);
    if (currentScenario && currentScenario.id) {
        url += "&scenario_id=" + encodeURIComponent(currentScenario.id);
    }
    return fetch(url)
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            return r.json();
        })
        .then(function (data) {
            setScheduleIds(term, data.ids || []);
        });
}

function saveScheduleIds(term, ids) {
    setScheduleIds(term, ids);
    var body = { term: term, ids: ids };
    if (currentScenario && currentScenario.id) {
        body.scenario_id = currentScenario.id;
    }
    return fetch("/api/my-schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    }).then(function (r) {
        if (r.status === 401) {
            window.location.href = "/account";
            throw new Error("Unauthorized");
        }
        if (!r.ok) throw new Error("Failed to save schedule");
    });
}

function currentTerm() {
    return termValueEl ? termValueEl.value : "";
}

function showAlert(message, type) {
    var box = document.getElementById("alertBox");
    var div = document.createElement("div");
    div.className = "alert alert-" + type + " alert-dismissible fade show py-2 mb-2";
    div.innerHTML = message + '<button type="button" class="btn-close btn-sm" data-bs-dismiss="alert"></button>';
    box.appendChild(div);
    setTimeout(function () { div.remove(); }, 4000);
}

function parseDays(str) {
    if (!str) return [];
    var result = [];
    for (var i = 0; i < str.length; i++) {
        var c = str[i].toUpperCase();
        if (DAY_CHARS.indexOf(c) !== -1) result.push(c);
    }
    return result;
}

function parseTime(str) {
    if (!str || !str.trim()) return null;
    var text = str.trim().toUpperCase();
    var isPM = text.indexOf("PM") !== -1;
    var isAM = text.indexOf("AM") !== -1;
    text = text.replace("PM", "").replace("AM", "").trim();
    var parts = text.split(":");
    if (parts.length !== 2) return null;
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return null;
    if (isPM && h !== 12) h += 12;
    if (isAM && h === 12) h = 0;
    return h * 60 + m;
}

function isHalfSemester(session) {
    if (!session) return false;
    var s = session.toUpperCase();
    return s.indexOf("W1") !== -1 || s.indexOf("W2") !== -1;
}

function sessionLabel(session) {
    if (!session) return "Full";
    var s = session.toUpperCase();
    if (s.indexOf("W1") !== -1) return "1st Half";
    if (s.indexOf("W2") !== -1) return "2nd Half";
    return "Full";
}

function formatDate(iso) {
    if (!iso) return "";
    var parts = iso.split("-");
    if (parts.length !== 3) return iso;
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    var m = parseInt(parts[1], 10);
    var d = parseInt(parts[2], 10);
    return months[m - 1] + " " + d;
}

/**
 * Short label for the planning dropdown: "Spring 2026 | Current semester"
 * Replaces informal "forecast" with academic "Catalog TBA" (sections not published yet).
 */
function termPlanStatusTag(t, currentLabel) {
    if (currentLabel && t.label === currentLabel) {
        return "Current semester";
    }
    if (t.is_projected) {
        return "Catalog TBA";
    }
    if (t.has_sections) {
        return "Sections available";
    }
    return "Catalog pending";
}

function termPlanOptionText(t, currentLabel) {
    var semYear = ((t.season || "") + " " + (t.year !== null && t.year !== undefined ? t.year : "")).trim().replace(/\s+/g, " ") || (t.label || "");
    var status = termPlanStatusTag(t, currentLabel);
    var bits = [semYear + " | " + status];
    if (t.date_start && t.date_end) {
        bits.push(formatDate(t.date_start) + " – " + formatDate(t.date_end));
    }
    if (t.has_sections && t.section_count) {
        bits.push(t.section_count + " sections");
    }
    if (t.from_transcript) {
        bits.push("Transcript");
    }
    if (t.has_saved_schedule) {
        bits.push("Saved plan");
    }
    return bits.join(" · ");
}

function timeConflict(a, b) {
    var daysA = parseDays(a.days);
    var daysB = parseDays(b.days);
    if (daysA.length === 0 || daysB.length === 0) return false;
    var overlap = false;
    for (var i = 0; i < daysA.length; i++) {
        if (daysB.indexOf(daysA[i]) !== -1) { overlap = true; break; }
    }
    if (!overlap) return false;
    var sA = parseTime(a.start_time), eA = parseTime(a.end_time);
    var sB = parseTime(b.start_time), eB = parseTime(b.end_time);
    if (sA === null || eA === null || sB === null || eB === null) return false;
    if (sA >= eB || sB >= eA) return false;
    // 8W1 and 8W2 don't overlap since they run in different halves
    if (isHalfSemester(a.session) && isHalfSemester(b.session)) {
        var aIs1 = a.session.toUpperCase().indexOf("W1") !== -1;
        var bIs1 = b.session.toUpperCase().indexOf("W1") !== -1;
        if (aIs1 !== bIs1) return false;
    }
    return true;
}

function buildColorMap(sections) {
    var codes = [];
    var map = {};
    for (var i = 0; i < sections.length; i++) {
        var code = sections[i].course_code;
        if (codes.indexOf(code) === -1) codes.push(code);
    }
    for (var j = 0; j < codes.length; j++) {
        map[codes[j]] = COLORS[j % COLORS.length];
    }
    return map;
}

function findConflictIds(sections) {
    var ids = {};
    for (var i = 0; i < sections.length; i++) {
        for (var j = i + 1; j < sections.length; j++) {
            if (timeConflict(sections[i], sections[j])) {
                ids[sections[i].id] = true;
                ids[sections[j].id] = true;
            }
        }
    }
    return ids;
}

var termPickerScroll = document.getElementById("termPickerScroll");
var termSelectCompat = document.getElementById("termSelectCompat");
var termValueEl = document.getElementById("termValue");
var jumpCurrentTerm = document.getElementById("jumpCurrentTerm");
var currentTermHint = document.getElementById("currentTermHint");
var termTimeline = null;
var planningControlsWrap = document.getElementById("planningControlsWrap");
var schedulePlanningMain = document.getElementById("schedulePlanningMain");
var pastTermRecordView = document.getElementById("pastTermRecordView");
var pastTermRecordBody = document.getElementById("pastTermRecordBody");
var pastTermRecordSub = document.getElementById("pastTermRecordSub");
var pastTermPickerNotice = document.getElementById("pastTermPickerNotice");
var jumpFromPastToPlanning = document.getElementById("jumpFromPastToPlanning");
var pastTermRecordTitle = document.getElementById("pastTermRecordTitle");
function updateJumpToCurrent() {
    if (!jumpCurrentTerm || !currentTermHint || !termTimeline) {
        updatePastJumpButton();
        return;
    }
    var cur = termTimeline.current_term;
    if (cur) {
        currentTermHint.hidden = false;
        currentTermHint.textContent = "Now · " + cur;
        currentTermHint.title = "Campus current semester";
        if (currentTerm() !== cur) {
            jumpCurrentTerm.hidden = false;
        } else {
            jumpCurrentTerm.hidden = true;
        }
    } else {
        currentTermHint.hidden = true;
        jumpCurrentTerm.hidden = true;
    }
    updatePastJumpButton();
}

function termLabelSortRank(lbl) {
    var m = /^(\w+)\s+(\d{4})$/.exec(String(lbl || "").trim());
    if (!m) return 99999 * 1000;
    var yr = parseInt(m[2], 10);
    var s = String(m[1]).toLowerCase();
    var sk = { spring: 0, summer: 1, fall: 2 }[s];
    if (sk === undefined) sk = 1;
    return yr * 100 + sk;
}

function termPastOptionText(p) {
    var semYear = ((p.season || "") + " " + (p.year !== null && p.year !== undefined ? p.year : "")).trim()
        .replace(/\s+/g, " ")
        || (p.label || "");
    return semYear + " | Completed term";
}

function termIsPastLabel(label) {
    if (!label || !termTimeline || !termTimeline.past_terms) return false;
    var past = termTimeline.past_terms;
    for (var i = 0; i < past.length; i++) {
        if (past[i].label === label) {
            return true;
        }
    }
    return false;
}

function planningJumpTargetLabel() {
    if (!termTimeline || !termTimeline.terms || termTimeline.terms.length === 0) return "";
    if (termTimeline.current_term) {
        return termTimeline.current_term;
    }
    return termTimeline.default_term || (termTimeline.terms[0] && termTimeline.terms[0].label) || "";
}

function escapeHtmlSch(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function fmtTxCredits(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    var n = Number(v);
    if (isNaN(n)) return "—";
    return n.toFixed(digits);
}

function fmtTxGrade(c) {
    if (!c || typeof c !== "object") return "—";
    var g = c.grade;
    if (g === null || g === undefined || String(g).trim() === "") {
        return "—";
    }
    return escapeHtmlSch(String(g).trim());
}

function applyPlanningVsPastMode(isPast) {
    if (planningControlsWrap) {
        planningControlsWrap.classList.toggle("d-none", isPast);
    }
    if (pastTermPickerNotice) {
        pastTermPickerNotice.classList.toggle("d-none", !isPast);
    }
    if (schedulePlanningMain) {
        schedulePlanningMain.classList.toggle("d-none", isPast);
    }
    if (pastTermRecordView) {
        pastTermRecordView.classList.toggle("d-none", !isPast);
    }
}

function updatePastJumpButton() {
    if (!jumpFromPastToPlanning) {
        return;
    }
    var dest = planningJumpTargetLabel();
    jumpFromPastToPlanning.classList.toggle("d-none", !termIsPastLabel(currentTerm()) || !dest);
}

function loadPastTermTranscript(termLabel) {
    if (!pastTermRecordBody) {
        return;
    }
    if (pastTermRecordTitle) {
        pastTermRecordTitle.textContent = termLabel
            ? termLabel + " · transcript courses"
            : "Courses on transcript";
    }
    if (pastTermRecordSub) {
        pastTermRecordSub.textContent =
            "Unofficial transcript on file — institutional rows for this semester (not a weekly meeting grid).";
    }
    pastTermRecordBody.innerHTML =
        "<div class=\"text-center py-5 text-muted\" role=\"status\">" +
        "<span class=\"spinner-border spinner-border-sm me-2\" aria-hidden=\"true\"></span>" +
        "<span class=\"small\">Loading transcript data…</span></div>";

    fetch("/api/transcript-term?term=" + encodeURIComponent(termLabel))
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            return r.json();
        })
        .then(function (payload) {
            renderPastTermPayload(payload, termLabel);
        })
        .catch(function () {
            pastTermRecordBody.innerHTML =
                '<div class="alert alert-danger mb-0 small" role="alert">Could not load transcript data right now.</div>';
        });
}

function renderPastTermPayload(payload, termLabel) {
    if (!pastTermRecordBody) {
        return;
    }
    var courses = (payload && payload.courses) ? payload.courses : [];
    var lbl = (payload && payload.normalized_term) ? String(payload.normalized_term) : String(termLabel || "");

    function emptyNoFile() {
        pastTermRecordBody.innerHTML =
            '<div class="past-term-empty rounded-3 bg-body-secondary bg-opacity-25 p-md-5 p-4 text-center">' +
            '<p class="fw-semibold text-body mb-2">No transcript uploaded yet</p>' +
            '<p class="text-muted small mb-3">' +
            escapeHtmlSch(lbl) +
            ' will appear here after you upload your unofficial transcript on Profile.</p>' +
            '<a class="btn btn-sm btn-accent" href="/profile">Go to Profile to upload transcript</a></div>';
    }

    function emptyWrongTermWarn() {
        var partial = !!(payload && payload.course_history_partial);
        var banner = "";
        if (partial) {
            banner =
                '<div class="alert alert-info small mb-3" role="status">' +
                "<strong>Note:</strong> Your saved transcript may include only recent terms. " +
                'Re-export the unofficial transcript from your portal and upload it again on <a href="/profile">Profile</a> for older semesters.</div>';
        }
        pastTermRecordBody.innerHTML =
            banner +
            '<div class="past-term-empty rounded-3 bg-body-secondary bg-opacity-25 p-md-5 p-4 text-center">' +
            '<p class="fw-semibold text-body mb-2">No courses for this term</p>' +
            '<p class="text-muted small mb-0">' +
            'We couldn’t find institutional rows matching <strong>' +
            escapeHtmlSch(lbl) +
            '</strong> in your imported transcript.' +
            (partial ? " Older terms sometimes require a fresh PDF upload." : "") +
            "</p></div>";
    }

    if (!payload || !payload.has_transcript_file) {
        emptyNoFile();
        return;
    }
    if (!payload.has_parsed_transcript) {
        pastTermRecordBody.innerHTML =
            '<div class="past-term-empty rounded-3 bg-body-secondary bg-opacity-25 p-md-5 p-4 text-center">' +
            '<p class="text-muted small mb-0">Transcript is on file but could not be read. Upload again from <a href="/profile">Profile</a>.</p></div>';
        return;
    }
    if (courses.length === 0) {
        emptyWrongTermWarn();
        return;
    }

    var note = "";
    if (payload.course_history_partial) {
        note =
            '<div class="alert alert-info py-2 small mb-3" role="status">' +
            '<strong>Partial course history:</strong> this import may omit older semesters. Re-upload your full unofficial transcript when you can.</div>';
    }
    var table =
        '<div class="table-responsive"><table class="table table-sm table-hover mb-0 align-middle section-table"><thead><tr>' +
        "<th>Course</th><th>Title</th>" +
        '<th class="text-end">Attempted</th><th class="text-end">Grade</th><th class="text-end">Earned</th>' +
        "</tr></thead><tbody>";

    var totalAtt = 0;
    var totalEarn = 0;
    for (var i = 0; i < courses.length; i++) {
        var sec = courses[i];
        var code =
            sec.course ||
            (sec.subject && sec.course_number != null ? sec.subject + " " + sec.course_number : "—");
        var ct;
        try {
            if (sec.course_name !== null && sec.course_name !== undefined && String(sec.course_name).trim()) {
                ct = escapeHtmlSch(String(sec.course_name).trim());
            } else {
                ct = "—";
            }
        } catch (_e2) {
            ct = "—";
        }
        var atm = Number(sec.attempted);
        if (!isNaN(atm)) {
            totalAtt += atm;
        }
        var erw = Number(sec.earned);
        if (!isNaN(erw)) {
            totalEarn += erw;
        }

        table += "<tr><td class=\"fw-semibold text-nowrap\">" +
            escapeHtmlSch(code) + "</td>" +
            "<td class=\"small\">" +
            ct + "</td><td class=\"text-end\">" +
            fmtTxCredits(sec.attempted, 1) + '</td><td class=\"text-end\">' +
            fmtTxGrade(sec) + '</td><td class=\"text-end\">' +
            fmtTxCredits(sec.earned, 1) + "</td></tr>";
    }
    table += "</tbody>";
    table += "<tfoot><tr><td colspan=\"2\" class=\"text-muted small fw-semibold\">Totals (this term)</td>";
    table +=
        '<td class="text-end small">' +
        fmtTxCredits(totalAtt, 1) +
        "</td><td></td><td class=\"text-end small\">" +
        fmtTxCredits(totalEarn, 1) +
        "</td></tr></tfoot></table></div>";

    pastTermRecordBody.innerHTML = note + table;
}

function populateTermSelectCompat(terms, pastTerms, currentLabel, selectedLabel) {
    if (!termSelectCompat || !terms || terms.length === 0) {
        return;
    }
    termSelectCompat.innerHTML = "";
    var byY = {};
    for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        var yk = t.year != null ? String(t.year) : "other";
        if (!byY[yk]) {
            byY[yk] = [];
        }
        byY[yk].push(t);
    }
    var years = Object.keys(byY).sort(function (a, b) {
        if (a === "other") {
            return 1;
        }
        if (b === "other") {
            return -1;
        }
        return parseInt(a, 10) - parseInt(b, 10);
    });

    function optionText(t) {
        return termPlanOptionText(t, currentLabel);
    }

    for (var yi = 0; yi < years.length; yi++) {
        var yk = years[yi];
        var og = document.createElement("optgroup");
        og.label = yk === "other" ? "Terms" : "Year " + yk;
        var group = byY[yk];
        for (var j = 0; j < group.length; j++) {
            var t = group[j];
            var opt = document.createElement("option");
            opt.value = t.label;
            opt.textContent = optionText(t);
            og.appendChild(opt);
        }
        termSelectCompat.appendChild(og);
    }
    var pastArr = pastTerms || [];
    if (pastArr.length > 0) {
        var sortedPast = pastArr.slice().sort(function (a, b) {
            return termLabelSortRank(a.label) - termLabelSortRank(b.label);
        });
        var ogPast = document.createElement("optgroup");
        ogPast.label = "Prior semesters";
        for (var pj = 0; pj < sortedPast.length; pj++) {
            var pe = sortedPast[pj];
            var op = document.createElement("option");
            op.value = pe.label;
            op.textContent = termPastOptionText(pe);
            ogPast.appendChild(op);
        }
        termSelectCompat.appendChild(ogPast);
    }
    var v = selectedLabel || (terms[0] && terms[0].label) || "";
    if (v) {
        var found = false;
        for (var jj = 0; jj < termSelectCompat.options.length; jj++) {
            if (termSelectCompat.options[jj].value === v) {
                found = true;
                break;
            }
        }
        if (found) {
            termSelectCompat.value = v;
        }
    }
}

function renderPastTermsPanel(pastTerms) {
    var btn = document.getElementById("pastCreditsBtn");
    var listEl = document.getElementById("pastCreditsList");
    if (!listEl || !btn) {
        return;
    }
    listEl.innerHTML = "";
    if (!pastTerms || pastTerms.length === 0) {
        btn.classList.add("d-none");
        return;
    }
    btn.classList.remove("d-none");
    for (var i = 0; i < pastTerms.length; i++) {
        var p = pastTerms[i];
        var li = document.createElement("li");
        li.className = "past-credits-item border-bottom border-opacity-50 p-0";
        if (i === pastTerms.length - 1) {
            li.classList.remove("border-bottom");
        }
        var b = document.createElement("button");
        b.type = "button";
        b.className =
            "btn btn-light w-100 text-start rounded-0 py-2 px-3 past-credits-pick text-decoration-none d-block";
        b.setAttribute("data-select-term", p.label || "");
        b.innerHTML =
            '<div class="d-flex justify-content-between align-items-baseline gap-2 flex-wrap">' +
            '<span class="fw-semibold text-body-emphasis">' +
            escapeHtmlSch(p.label || "") +
            "</span>" +
            (p.date_end
                ? '<span class="text-muted small">Ended ' +
                escapeHtmlSch(formatDate(p.date_end)) +
                "</span>"
                : "") +
            "</div>" +
            '<span class="d-block small text-muted mt-1">Opens your transcript grades for this term (weekly calendar is hidden).</span>';

        li.appendChild(b);
        listEl.appendChild(li);
    }
}

function renderTermPicker(terms) {
    if (!termPickerScroll) {
        return;
    }
    var byYear = {};
    for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        var y = t.year;
        if (y === null || y === undefined) {
            y = "—";
        }
        if (!byYear[y]) {
            byYear[y] = [];
        }
        byYear[y].push(t);
    }
    var years = Object.keys(byYear);
    years.sort(function (a, b) {
        if (a === "—") {
            return 1;
        }
        if (b === "—") {
            return -1;
        }
        return parseInt(a, 10) - parseInt(b, 10);
    });
    var html = "";
    for (var yi = 0; yi < years.length; yi++) {
        var yk = years[yi];
        html += "<div class=\"term-year-block\">";
        html += "<div class=\"term-year-pill\">" + yk + "</div>";
        html += "<div class=\"term-year-chips\">";
        var ch = byYear[yk];
        for (var j = 0; j < ch.length; j++) {
            var t = ch[j];
            var cls = "term-chip";
            if (t.is_projected) {
                cls += " term-chip-projected";
            } else if (t.has_sections && t.from_transcript) {
                cls += " term-chip-both";
            } else if (t.has_sections) {
                cls += " term-chip-live";
            } else if (t.from_transcript) {
                cls += " term-chip-tx";
            }
            if (termTimeline && t.label === termTimeline.current_term) {
                cls += " term-chip-now";
            }
            if (t.has_saved_schedule) {
                cls += " term-chip-saved";
            }
            var semY = ((t.season || "") + " " + (t.year != null ? t.year : "")).trim();
            var st = termPlanStatusTag(t, termTimeline ? termTimeline.current_term : null);
            var title;
            if (t.is_projected) {
                title = t.label + " — Catalog TBA: sections not published by the registrar yet.";
            } else if (!t.has_sections) {
                title = t.label + " — No section rows in the local database for this label yet.";
            } else {
                title = t.label;
            }
            html += "<button type=\"button\" class=\"" + cls + "\" data-term=\"" +
                t.label.replace(/&/g, "&amp;").replace(/"/g, "&quot;") +
                "\" title=\"" + title.replace(/&/g, "&amp;").replace(/"/g, "&quot;") + "\"";
            html += " aria-selected=\"false\">";
            html += "<span class=\"term-chip-line d-flex flex-column align-items-start\">";
            html += "<span class=\"term-chip-semrow\"><span class=\"term-chip-sem-year\">" + (semY || t.label || "") + "</span>";
            html += " <span class=\"term-chip-pipe text-muted\">|</span> ";
            html += "<span class=\"term-chip-status\">" + st + "</span></span>";
            if (t.date_start && t.date_end) {
                html += "<span class=\"term-chip-dates d-none d-xl-inline\">" + formatDate(t.date_start) + " – " + formatDate(t.date_end) + "</span>";
            }
            html += "</span></button>";
        }
        html += "</div></div>";
    }
    termPickerScroll.innerHTML = html;
}

function setSelectedTerm(label, andNotify) {
    if (!termValueEl) {
        return;
    }
    termValueEl.value = label;
    if (termSelectCompat) {
        var hasOpt = false;
        for (var s = 0; s < termSelectCompat.options.length; s++) {
            if (termSelectCompat.options[s].value === label) {
                hasOpt = true;
                break;
            }
        }
        if (hasOpt) {
            termSelectCompat.value = label;
        }
    }
    var chips = termPickerScroll ? termPickerScroll.querySelectorAll(".term-chip") : [];
    for (var i = 0; i < chips.length; i++) {
        var c = chips[i];
        var isSel = c.getAttribute("data-term") === label;
        c.classList.toggle("active", isSel);
        c.setAttribute("aria-selected", isSel ? "true" : "false");
    }
    if (andNotify) {
        onTermChange();
    } else {
        updateJumpToCurrent();
    }
    var active = termPickerScroll && termPickerScroll.querySelector(".term-chip.active");
    if (active && typeof active.scrollIntoView === "function") {
        active.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
    }
}
var subjectSelect  = document.getElementById("subjectSelect");
var modeSelect     = document.getElementById("modeSelect");
var levelSelect    = document.getElementById("levelSelect");
var searchInput    = document.getElementById("searchInput");
var filterBtn      = document.getElementById("filterBtn");
var sectionResults = document.getElementById("sectionResults");
var clearBtn       = document.getElementById("clearBtn");
var termDatesEl    = document.getElementById("termDates");
var termLabelEl    = document.getElementById("termLabel");
var logoutBtn      = document.getElementById("logoutBtn");
var scenarioSelect = document.getElementById("scenarioSelect");
var newScenarioBtn = document.getElementById("newScenarioBtn");
var duplicateScenarioBtn = document.getElementById("duplicateScenarioBtn");
var renameScenarioBtn = document.getElementById("renameScenarioBtn");
var deleteScenarioBtn = document.getElementById("deleteScenarioBtn");
var exportIcsBtn = document.getElementById("exportIcsBtn");
var copyShareLinkBtn = document.getElementById("copyShareLinkBtn");

function updateTermScenarioLabel() {
    if (!termLabelEl) return;
    var term = currentTerm();
    if (currentScenario && currentScenario.name) {
        termLabelEl.textContent = term + " · " + currentScenario.name;
    } else {
        termLabelEl.textContent = term;
    }
}

function populateScenarioSelect(term, scenarios) {
    scenariosByTerm[term] = scenarios || [];
    if (!scenarioSelect) return;
    scenarioSelect.innerHTML = "";
    for (var i = 0; i < scenariosByTerm[term].length; i++) {
        var sc = scenariosByTerm[term][i];
        var opt = document.createElement("option");
        opt.value = sc.id;
        opt.textContent = sc.name + (sc.is_active ? " (active)" : "");
        scenarioSelect.appendChild(opt);
    }
    if (currentScenario && currentScenario.id) {
        scenarioSelect.value = String(currentScenario.id);
    }
}

function loadScenarios(term) {
    return fetch("/api/scenarios?term=" + encodeURIComponent(term))
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            if (!r.ok) throw new Error("Could not load scenarios");
            return r.json();
        })
        .then(function (data) {
            var scenarios = data.scenarios || [];
            currentScenario = scenarios.length ? scenarios[0] : null;
            for (var i = 0; i < scenarios.length; i++) {
                if (scenarios[i].is_active) {
                    currentScenario = scenarios[i];
                    break;
                }
            }
            populateScenarioSelect(term, scenarios);
            updateTermScenarioLabel();
        });
}

function scenarioById(term, id) {
    var list = scenariosByTerm[term] || [];
    for (var i = 0; i < list.length; i++) {
        if (String(list[i].id) === String(id)) return list[i];
    }
    return null;
}

function activateScenario(id) {
    return fetch("/api/scenarios/" + encodeURIComponent(id) + "/activate", { method: "POST" })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not activate scenario");
            return r.json();
        })
        .then(function (data) {
            currentScenario = data.scenario;
            return loadScenarios(currentScenario.term_label);
        });
}

function reloadCurrentScenarioSchedule() {
    var term = currentTerm();
    updateTermScenarioLabel();
    return loadScheduleIds(term).then(function () {
        loadSections();
        refreshSchedule();
    });
}

function termsFromLabelStrings(labels) {
    return labels.map(function (lbl) {
        return {
            label: lbl,
            year: null,
            season: null,
            has_sections: true,
            has_calendar: false,
            date_start: null,
            date_end: null,
            from_transcript: false,
            has_saved_schedule: false,
            is_projected: false
        };
    });
}

function initScheduleWithTimeline(data) {
    if (!data.terms || data.terms.length === 0) {
        if (sectionResults) {
            sectionResults.innerHTML = "<p class=\"text-danger small\">No terms available. Run the course sync (python -m scrapers sync) from the project root.</p>";
        }
        return;
    }
    termTimeline = data;
    renderTermPicker(data.terms);
    populateTermSelectCompat(
        data.terms,
        data.past_terms || [],
        data.current_term,
        data.default_term
    );
    renderPastTermsPanel(data.past_terms || []);
    setSelectedTerm(data.default_term || (data.terms[0] && data.terms[0].label) || "", false);
    onTermChange();
}

function loadTermTimelineOrFallback() {
    return fetch("/api/term-timeline")
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            if (!r.ok) {
                return r.json().then(function (body) {
                    var msg = (body && (body.error || body.detail)) || r.status;
                    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
                }).catch(function () {
                    throw new Error("Server error " + r.status);
                });
            }
            return r.json();
        })
        .then(function (data) {
            if (data.error) {
                throw new Error(data.error);
            }
            initScheduleWithTimeline(data);
        })
        .catch(function (err) {
            if (err && err.message === "Unauthorized") {
                return;
            }
            console.error("term-timeline failed:", err);
            showAlert(
                "Using basic term list: " + (err && err.message ? err.message : "unknown error") + ". " +
                "The full term planner could not be loaded.",
                "warning"
            );
            return fetch("/api/terms")
                .then(function (r) {
                    if (!r.ok) {
                        throw new Error("GET /api/terms " + r.status);
                    }
                    return r.json();
                })
                .then(function (labels) {
                    if (!labels || labels.length === 0) {
                        if (sectionResults) {
                            sectionResults.innerHTML = "<p class=\"text-danger small\">No terms in the database. Run: <code>python -m scrapers sync</code> from the project root.</p>";
                        }
                        return;
                    }
                    var simple = {
                        terms: termsFromLabelStrings(labels),
                        current_term: null,
                        default_term: labels[0],
                        past_terms: []
                    };
                    initScheduleWithTimeline(simple);
                })
                .catch(function (e2) {
                    if (sectionResults) {
                        sectionResults.innerHTML = "<p class=\"text-danger small\">" +
                            (e2 && e2.message ? e2.message : "Could not load terms.") + "</p>";
                    }
                    showAlert("Failed to load term list.", "danger");
                });
        });
}

logoutBtn && logoutBtn.addEventListener("click", function () {
    fetch("/api/logout", { method: "POST" })
        .then(function () {
            window.location.href = "/account";
        })
        .catch(function () {
            showAlert("Could not log out right now. Try again.", "danger");
        });
});

if (READ_ONLY_SCHEDULE) {
    renderSharedSchedule();
} else {
    fetch("/api/me")
        .then(function (r) {
            if (!r.ok) {
                throw new Error("session check failed");
            }
            return r.json();
        })
        .then(function (me) {
            if (!me.authenticated) {
                window.location.href = "/account";
                return;
            }
            return loadTermTimelineOrFallback();
        })
        .catch(function (err) {
            console.error("schedule init:", err);
            showAlert("Could not load the schedule page. Refresh or sign in again.", "danger");
        });
}

if (termPickerScroll) {
    termPickerScroll.addEventListener("click", function (e) {
        var btn = e.target && e.target.closest && e.target.closest(".term-chip");
        if (!btn) {
            return;
        }
        var t = btn.getAttribute("data-term");
        if (t) {
            setSelectedTerm(t, true);
        }
    });
}

if (jumpCurrentTerm) {
    jumpCurrentTerm.addEventListener("click", function () {
        if (termTimeline && termTimeline.current_term) {
            setSelectedTerm(termTimeline.current_term, true);
        }
    });
}

if (jumpFromPastToPlanning) {
    jumpFromPastToPlanning.addEventListener("click", function () {
        var dest = planningJumpTargetLabel();
        if (dest) {
            setSelectedTerm(dest, true);
        }
    });
}

var pastCreditsListEl = document.getElementById("pastCreditsList");
if (pastCreditsListEl) {
    pastCreditsListEl.addEventListener("click", function (e) {
        var b = e.target && e.target.closest && e.target.closest(".past-credits-pick");
        if (!b) {
            return;
        }
        var tl = b.getAttribute("data-select-term");
        if (tl) {
            setSelectedTerm(tl, true);
        }
    });
}

if (termSelectCompat) {
    termSelectCompat.addEventListener("change", function () {
        var v = termSelectCompat.value;
        if (v) {
            setSelectedTerm(v, true);
        }
    });
}

if (scenarioSelect) {
    scenarioSelect.addEventListener("change", function () {
        var term = currentTerm();
        var picked = scenarioById(term, scenarioSelect.value);
        if (!picked) return;
        currentScenario = picked;
        updateTermScenarioLabel();
        activateScenario(picked.id)
            .then(reloadCurrentScenarioSchedule)
            .catch(function () {
                showAlert("Could not switch scenarios.", "danger");
            });
    });
}

newScenarioBtn && newScenarioBtn.addEventListener("click", function () {
    var term = currentTerm();
    var name = window.prompt("Name this scenario:", "New scenario");
    if (name === null) return;
    fetch("/api/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ term: term, name: name })
    })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not create scenario");
            return r.json();
        })
        .then(function (data) {
            currentScenario = data.scenario;
            return loadScenarios(term);
        })
        .then(reloadCurrentScenarioSchedule)
        .then(function () {
            showAlert("Scenario created.", "success");
        })
        .catch(function () {
            showAlert("Could not create scenario.", "danger");
        });
});

duplicateScenarioBtn && duplicateScenarioBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    var name = window.prompt("Name the duplicate scenario:", currentScenario.name + " copy");
    if (name === null) return;
    fetch("/api/scenarios/" + encodeURIComponent(currentScenario.id) + "/duplicate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name })
    })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not duplicate scenario");
            return r.json();
        })
        .then(function (data) {
            currentScenario = data.scenario;
            return loadScenarios(currentTerm());
        })
        .then(reloadCurrentScenarioSchedule)
        .then(function () {
            showAlert("Scenario duplicated.", "success");
        })
        .catch(function () {
            showAlert("Could not duplicate scenario.", "danger");
        });
});

renameScenarioBtn && renameScenarioBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    var name = window.prompt("Rename scenario:", currentScenario.name);
    if (name === null) return;
    fetch("/api/scenarios/" + encodeURIComponent(currentScenario.id) + "/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name })
    })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not rename scenario");
            return r.json();
        })
        .then(function (data) {
            currentScenario = data.scenario;
            return loadScenarios(currentTerm());
        })
        .then(function () {
            updateTermScenarioLabel();
            showAlert("Scenario renamed.", "success");
        })
        .catch(function () {
            showAlert("Could not rename scenario.", "danger");
        });
});

deleteScenarioBtn && deleteScenarioBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    if (!window.confirm("Delete scenario \"" + currentScenario.name + "\"?")) return;
    fetch("/api/scenarios/" + encodeURIComponent(currentScenario.id), { method: "DELETE" })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not delete scenario");
            return r.json();
        })
        .then(function (data) {
            currentScenario = data.active_scenario;
            return loadScenarios(currentTerm());
        })
        .then(reloadCurrentScenarioSchedule)
        .then(function () {
            showAlert("Scenario deleted.", "info");
        })
        .catch(function () {
            showAlert("Could not delete scenario.", "danger");
        });
});

exportIcsBtn && exportIcsBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    window.location.href = "/api/scenarios/" + encodeURIComponent(currentScenario.id) + "/ics";
});

copyShareLinkBtn && copyShareLinkBtn.addEventListener("click", function () {
    if (!currentScenario) return;
    fetch("/api/scenarios/" + encodeURIComponent(currentScenario.id) + "/share", { method: "POST" })
        .then(function (r) {
            if (!r.ok) throw new Error("Could not create share link");
            return r.json();
        })
        .then(function (data) {
            var absolute = new URL(data.url, window.location.origin).href;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                return navigator.clipboard.writeText(absolute).then(function () {
                    showAlert("Share link copied.", "success");
                });
            }
            window.prompt("Copy this share link:", absolute);
        })
        .catch(function () {
            showAlert("Could not create share link.", "danger");
        });
});

function onTermChange() {
    var term = currentTerm();
    currentScenario = null;
    updateTermScenarioLabel();
    loadTermDates(term);
    var isPast = termIsPastLabel(term);
    applyPlanningVsPastMode(isPast);
    if (scenarioSelect) {
        scenarioSelect.disabled = isPast;
    }
    if (isPast) {
        loadPastTermTranscript(term);
        updateJumpToCurrent();
        return;
    }
    loadDropdowns(term);
    loadScenarios(term)
        .then(function () {
            return reloadCurrentScenarioSchedule();
        })
        .catch(function () {
            showAlert("Could not load schedule scenarios.", "danger");
        });
    updateJumpToCurrent();
}

function loadTermDates(term) {
    if (!termDatesEl) {
        return;
    }
    fetch("/api/session-dates?term=" + encodeURIComponent(term))
        .then(function (r) { return r.json(); })
        .then(function (dates) {
            if (dates.length === 0) {
                termDatesEl.classList.add("d-none");
                return;
            }
            var html = "";
            for (var i = 0; i < dates.length; i++) {
                var d = dates[i];
                var label = sessionLabel(d.session);
                if (html) html += " &nbsp;|&nbsp; ";
                html += "<strong>" + label + ":</strong> " + formatDate(d.session_start_date) + " – " + formatDate(d.session_end_date);
            }
            termDatesEl.innerHTML = html;
            termDatesEl.classList.remove("d-none");
        })
        .catch(function () {
            termDatesEl.classList.add("d-none");
        });
}

function loadDropdowns(term) {
    if (subjectSelect) {
        fetch("/api/subjects?term=" + encodeURIComponent(term))
            .then(function (r) { return r.json(); })
            .then(function (subjects) {
                subjectSelect.innerHTML = '<option value="">All</option>';
                for (var i = 0; i < subjects.length; i++) {
                    var opt = document.createElement("option");
                    opt.value = subjects[i];
                    opt.textContent = subjects[i];
                    subjectSelect.appendChild(opt);
                }
            });
    }
    if (modeSelect) {
        fetch("/api/modes?term=" + encodeURIComponent(term))
            .then(function (r) { return r.json(); })
            .then(function (modes) {
                modeSelect.innerHTML = '<option value="">All</option>';
                for (var i = 0; i < modes.length; i++) {
                    var opt = document.createElement("option");
                    opt.value = modes[i];
                    opt.textContent = modes[i];
                    modeSelect.appendChild(opt);
                }
            });
    }
}

filterBtn && filterBtn.addEventListener("click", loadSections);

searchInput && searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") loadSections();
});

function loadSections() {
    var params = "term=" + encodeURIComponent(currentTerm());
    if (subjectSelect && subjectSelect.value) params += "&subject=" + encodeURIComponent(subjectSelect.value);
    if (modeSelect && modeSelect.value) params += "&mode=" + encodeURIComponent(modeSelect.value);
    if (levelSelect && levelSelect.value) params += "&level=" + encodeURIComponent(levelSelect.value);
    if (searchInput && searchInput.value.trim()) params += "&search=" + encodeURIComponent(searchInput.value.trim());

    fetch("/api/sections?" + params)
        .then(function (r) { return r.json(); })
        .then(function (sections) {
            renderSectionList(sections);
        });
}

function renderSectionList(sections) {
    var term = currentTerm();
    var ids = getScheduleIds(term);
    var html = "";

    if (sections.length === 0) {
        html = '<p class="text-muted small">No sections match your filters.</p>';
    } else {
        var allInferred = sections[0] && sections[0].is_inferred_placeholder;
        if (allInferred) {
            html = '<p class="small text-info mb-2">This term has no scraped schedule data yet. ' +
                'Showing catalog courses whose <strong>typical term</strong> (from degree maps) matches this season — not a guarantee of offerings.</p>';
        }
        html += '<p class="text-muted small mb-1">' + sections.length + ' result' + (sections.length !== 1 ? 's' : '') + '</p>';
        for (var i = 0; i < sections.length; i++) {
            var sec = sections[i];
            var added = sec.id != null && ids.indexOf(sec.id) !== -1;
            var half = sec.session && isHalfSemester(sec.session);
            var inferred = !!sec.is_inferred_placeholder;
            html += '<div class="section-card ' + (added ? 'section-card-added' : '') + '">';
            html += '<div class="d-flex justify-content-between align-items-start">';
            html += '<div><span class="fw-bold">' + sec.course_code + '</span> ';
            if (!inferred) {
                html += '<span class="text-muted small">&sect;' + (sec.section_code || '') + '</span>';
            }
            if (inferred && sec.term_infered) {
                html += ' <span class="badge bg-secondary-subtle text-secondary border">Maps: ' + escapeHtmlSch(sec.term_infered) + '</span>';
            }
            if (!inferred && half) {
                html += ' <span class="session-badge session-badge-half">' + sessionLabel(sec.session) + '</span>';
            }
            html += '</div>';
            if (added) {
                html += '<span class="badge badge-added">Added</span>';
            } else {
                html += '<button class="btn btn-outline-accent btn-xs" onclick="addSection(' + sec.id + ')">+ Add</button>';
            }
            if (inferred && !added) {
                html += ' <span class="badge bg-light text-muted border ms-1">Planning</span>';
            }
            html += '</div>';
            html += '<div class="small text-muted">' + (sec.course_name || '') + '</div>';
            html += '<div class="small text-muted">';
            if (sec.days) {
                html += sec.days + ' &middot; ' + sec.start_time + '–' + sec.end_time + ' &middot; ' + (sec.location || '');
            } else if (inferred) {
                html += 'No section / meeting data until this term is published in Banner.';
            } else {
                html += 'Online / Async';
            }
            html += ' &middot; ' + (sec.credits || '') + (sec.credits ? ' hrs' : '') + '</div>';
            if (sec.session_start_date) {
                html += '<div class="small text-muted">' + formatDate(sec.session_start_date) + ' – ' + formatDate(sec.session_end_date) + '</div>';
            }
            html += '</div>';
        }
    }
    sectionResults.innerHTML = html;
}

function addSection(id) {
    var term = currentTerm();
    var ids = getScheduleIds(term);
    if (ids.indexOf(id) !== -1) return;
    ids.push(id);
    saveScheduleIds(term, ids)
        .then(function () {
            loadSections();
            refreshSchedule();
            showAlert(id < 0 ? "Planned course added." : "Section added.", "success");
        })
        .catch(function () {
            showAlert("Could not save section. Try again.", "danger");
        });
}

function removeSection(id) {
    var term = currentTerm();
    var ids = getScheduleIds(term);
    var idx = ids.indexOf(id);
    if (idx !== -1) ids.splice(idx, 1);
    saveScheduleIds(term, ids)
        .then(function () {
            loadSections();
            refreshSchedule();
            showAlert("Section removed.", "info");
        })
        .catch(function () {
            showAlert("Could not update schedule. Try again.", "danger");
        });
}

clearBtn && clearBtn.addEventListener("click", function () {
    var term = currentTerm();
    saveScheduleIds(term, [])
        .then(function () {
            loadSections();
            refreshSchedule();
            showAlert("Schedule cleared.", "info");
        })
        .catch(function () {
            showAlert("Could not clear schedule. Try again.", "danger");
        });
});

function refreshSchedule() {
    var term = currentTerm();
    var ids = getScheduleIds(term);
    if (ids.length === 0) {
        renderGrid([]);
        renderAddedTable([]);
        updateSummary([], {});
        return;
    }
    fetch("/api/sections/batch?ids=" + ids.join(",") + "&term=" + encodeURIComponent(term))
        .then(function (r) { return r.json(); })
        .then(function (sections) {
            renderGrid(sections);
            renderAddedTable(sections);
            updateSummary(sections, findConflictIds(sections));
        });
}

function renderSharedSchedule() {
    var scenario = SHARE_DATA && SHARE_DATA.scenario ? SHARE_DATA.scenario : null;
    var sections = SHARE_DATA && SHARE_DATA.sections ? SHARE_DATA.sections : [];
    if (termLabelEl && scenario) {
        termLabelEl.textContent = scenario.term_label + " · " + scenario.name;
    }
    renderGrid(sections);
    renderAddedTable(sections);
    updateSummary(sections, findConflictIds(sections));
}

function updateSummary(sections, conflictIds) {
    document.getElementById("sectionCount").textContent = sections.length;
    var total = 0;
    for (var i = 0; i < sections.length; i++) {
        var c = parseFloat(sections[i].credits);
        if (!isNaN(c)) total += c;
    }
    document.getElementById("creditCount").textContent = total.toFixed(1);

    var conflictCount = Object.keys(conflictIds).length;
    var badge = document.getElementById("conflictBadge");
    if (conflictCount > 0) {
        badge.classList.remove("d-none");
        document.getElementById("conflictText").textContent = conflictCount + " conflict" + (conflictCount !== 1 ? "s" : "");
    } else {
        badge.classList.add("d-none");
    }

    if (clearBtn) {
        clearBtn.classList.toggle("d-none", sections.length === 0);
    }
}

function renderGrid(sections) {
    var grid = document.getElementById("weeklyGrid");
    if (!grid) return;
    var colorMap = buildColorMap(sections);
    var conflictIds = findConflictIds(sections);

    var earliest = 480;
    var latest = 1260;
    for (var i = 0; i < sections.length; i++) {
        var s = parseTime(sections[i].start_time);
        var e = parseTime(sections[i].end_time);
        if (s !== null && e !== null) {
            if (s < earliest) earliest = s;
            if (e > latest) latest = e;
        }
    }
    earliest = Math.floor(earliest / 60) * 60;
    latest = Math.ceil(latest / 60) * 60;
    var totalMin = Math.max(latest - earliest, 60);
    var totalHours = totalMin / 60;
    var gridHeight = Math.max(totalHours * PX_PER_HOUR, 300);

    var hours = [];
    for (var t = earliest; t <= latest; t += 60) {
        var h = Math.floor(t / 60);
        var ampm = h < 12 ? "AM" : "PM";
        var dh = h <= 12 ? h : h - 12;
        if (dh === 0) dh = 12;
        hours.push({ label: dh + ":00 " + ampm, top: ((t - earliest) / totalMin) * 100 });
    }

    var blocks = [];
    for (var i = 0; i < sections.length; i++) {
        var sec = sections[i];
        var days = parseDays(sec.days);
        var sMin = parseTime(sec.start_time);
        var eMin = parseTime(sec.end_time);
        if (days.length === 0 || sMin === null || eMin === null) continue;
        var topPct = ((sMin - earliest) / totalMin) * 100;
        var heightPct = ((eMin - sMin) / totalMin) * 100;
        var color = colorMap[sec.course_code] || "#888";
        var isConflict = conflictIds[sec.id] || false;
        var half = isHalfSemester(sec.session);
        for (var d = 0; d < days.length; d++) {
            var col = DAY_CHARS.indexOf(days[d]);
            if (col !== -1) {
                blocks.push({ sec: sec, col: col, top: topPct, height: heightPct, color: color, conflict: isConflict, half: half });
            }
        }
    }

    var html = "";

    html += '<div class="grid-time-col">';
    html += '<div class="time-header"><span class="time-header-text">Time</span></div>';
    html += '<div class="time-body" style="height:' + gridHeight + 'px">';
    for (var i = 0; i < hours.length; i++) {
        html += '<div class="hour-label" style="top:' + hours[i].top.toFixed(2) + '%">' + hours[i].label + '</div>';
    }
    html += '</div></div>';

    for (var col = 0; col < 5; col++) {
        html += '<div class="grid-day-col">';
        html += '<div class="day-header">' + DAY_LABELS[col] + '</div>';
        html += '<div class="day-body" style="height:' + gridHeight + 'px">';

        for (var i = 0; i < hours.length; i++) {
            html += '<div class="hour-line" style="top:' + hours[i].top.toFixed(2) + '%"></div>';
        }

        for (var b = 0; b < blocks.length; b++) {
            if (blocks[b].col !== col) continue;
            var bl = blocks[b];
            var cls = "schedule-block";
            if (bl.conflict) cls += " conflict-block";
            if (bl.half) cls += " half-sem-block";
            html += '<div class="' + cls + '"';
            html += ' style="top:' + bl.top.toFixed(2) + '%;height:' + bl.height.toFixed(2) + '%;border-left-color:' + bl.color + ';"';
            html += ' title="' + bl.sec.course_code + ' ' + (bl.sec.start_time || '') + '–' + (bl.sec.end_time || '') + '">';
            html += '<div class="block-code">' + bl.sec.course_code + '</div>';
            html += '<div class="block-detail">' + (bl.sec.start_time || '') + '–' + (bl.sec.end_time || '') + '</div>';
            html += '<div class="block-detail">' + (bl.sec.location || '') + '</div>';
            if (bl.half) {
                html += '<div class="block-session">' + sessionLabel(bl.sec.session) + '</div>';
            }
            html += '</div>';
        }

        html += '</div></div>';
    }

    grid.innerHTML = html;
}

function renderAddedTable(sections) {
    var wrap = document.getElementById("addedTableWrap");
    var body = document.getElementById("addedBody");
    if (!wrap || !body) return;
    if (sections.length === 0) {
        wrap.classList.add("d-none");
        body.innerHTML = "";
        return;
    }
    wrap.classList.remove("d-none");

    var colorMap = buildColorMap(sections);
    var conflictIds = findConflictIds(sections);
    var html = "";

    for (var i = 0; i < sections.length; i++) {
        var sec = sections[i];
        var isConflict = conflictIds[sec.id] || false;
        var color = colorMap[sec.course_code] || "#888";
        var half = sec.session && isHalfSemester(sec.session);
        var inferred = !!sec.is_inferred_placeholder;
        html += '<tr class="' + (isConflict ? 'table-danger-subtle' : '') + '">';
        html += '<td><span class="color-dot" style="background:' + color + '"></span></td>';
        html += '<td class="fw-semibold text-nowrap">' + sec.course_code + '</td>';
        html += '<td>' + (sec.course_name || '') + '</td>';
        html += '<td>' + (inferred ? '—' : (sec.section_code || '')) + '</td>';
        html += '<td>';
        if (inferred) {
            html += '<span class="badge bg-light text-muted border">Planning</span>';
        } else if (half) {
            html += '<span class="session-badge session-badge-half">' + sessionLabel(sec.session) + '</span>';
        } else {
            html += '<span class="session-badge session-badge-full">Full</span>';
        }
        html += '</td>';
        html += '<td class="small text-nowrap">';
        if (sec.session_start_date) {
            html += formatDate(sec.session_start_date) + ' – ' + formatDate(sec.session_end_date);
        } else {
            html += '—';
        }
        html += '</td>';
        html += '<td class="text-nowrap">' + (sec.days || '—') + '</td>';
        html += '<td class="text-nowrap">';
        if (sec.start_time) {
            html += sec.start_time + '–' + sec.end_time;
        } else {
            html += '—';
        }
        html += '</td>';
        html += '<td>' + (sec.location || '—') + '</td>';
        html += '<td class="small">' + (sec.mode || '') + '</td>';
        html += '<td>' + (sec.credits || '') + '</td>';
        if (READ_ONLY_SCHEDULE) {
            html += '<td class="schedule-edit-col"></td>';
        } else {
            html += '<td class="schedule-edit-col"><button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="removeSection(' + sec.id + ')" title="Remove">&times;</button></td>';
        }
        html += '</tr>';
    }
    body.innerHTML = html;
}
