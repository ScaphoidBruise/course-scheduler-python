var COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B",
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316",
    "#6366F1", "#06B6D4", "#84CC16", "#D946EF",
];
var DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
var DAY_CHARS  = ["M", "T", "W", "R", "F"];
var PX_PER_HOUR = 64;

function storageKey(term) {
    return "schedule_" + term.replace(/\s+/g, "_");
}

function getScheduleIds(term) {
    var raw = localStorage.getItem(storageKey(term));
    if (!raw) return [];
    try { return JSON.parse(raw); } catch (e) { return []; }
}

function saveScheduleIds(term, ids) {
    localStorage.setItem(storageKey(term), JSON.stringify(ids));
}

function currentTerm() {
    return document.getElementById("termSelect").value;
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

var termSelect     = document.getElementById("termSelect");
var subjectSelect  = document.getElementById("subjectSelect");
var modeSelect     = document.getElementById("modeSelect");
var levelSelect    = document.getElementById("levelSelect");
var searchInput    = document.getElementById("searchInput");
var filterBtn      = document.getElementById("filterBtn");
var sectionResults = document.getElementById("sectionResults");
var clearBtn       = document.getElementById("clearBtn");
var termDatesEl    = document.getElementById("termDates");
var termLabelEl    = document.getElementById("termLabel");

fetch("/api/terms")
    .then(function (r) { return r.json(); })
    .then(function (terms) {
        for (var i = 0; i < terms.length; i++) {
            var opt = document.createElement("option");
            opt.value = terms[i];
            opt.textContent = terms[i];
            termSelect.appendChild(opt);
        }
        if (terms.length > 0) {
            onTermChange();
        }
    });

termSelect.addEventListener("change", onTermChange);

function onTermChange() {
    var term = currentTerm();
    termLabelEl.textContent = term;
    loadDropdowns(term);
    loadSections();
    refreshSchedule();
    loadTermDates(term);
}

function loadTermDates(term) {
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

filterBtn.addEventListener("click", loadSections);

searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") loadSections();
});

function loadSections() {
    var params = "term=" + encodeURIComponent(currentTerm());
    if (subjectSelect.value) params += "&subject=" + encodeURIComponent(subjectSelect.value);
    if (modeSelect.value) params += "&mode=" + encodeURIComponent(modeSelect.value);
    if (levelSelect.value) params += "&level=" + encodeURIComponent(levelSelect.value);
    if (searchInput.value.trim()) params += "&search=" + encodeURIComponent(searchInput.value.trim());

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
        html = '<p class="text-muted small mb-1">' + sections.length + ' result' + (sections.length !== 1 ? 's' : '') + '</p>';
        for (var i = 0; i < sections.length; i++) {
            var sec = sections[i];
            var added = ids.indexOf(sec.id) !== -1;
            var half = isHalfSemester(sec.session);
            html += '<div class="section-card ' + (added ? 'section-card-added' : '') + '">';
            html += '<div class="d-flex justify-content-between align-items-start">';
            html += '<div><span class="fw-bold">' + sec.course_code + '</span> ';
            html += '<span class="text-muted small">&sect;' + (sec.section_code || '') + '</span>';
            if (half) {
                html += ' <span class="session-badge session-badge-half">' + sessionLabel(sec.session) + '</span>';
            }
            html += '</div>';
            if (added) {
                html += '<span class="badge badge-added">Added</span>';
            } else {
                html += '<button class="btn btn-outline-accent btn-xs" onclick="addSection(' + sec.id + ')">+ Add</button>';
            }
            html += '</div>';
            html += '<div class="small text-muted">' + (sec.course_name || '') + '</div>';
            html += '<div class="small text-muted">';
            if (sec.days) {
                html += sec.days + ' &middot; ' + sec.start_time + '–' + sec.end_time + ' &middot; ' + (sec.location || '');
            } else {
                html += 'Online / Async';
            }
            html += ' &middot; ' + (sec.credits || '') + ' hrs</div>';
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
    saveScheduleIds(term, ids);
    loadSections();
    refreshSchedule();
    showAlert("Section added.", "success");
}

function removeSection(id) {
    var term = currentTerm();
    var ids = getScheduleIds(term);
    var idx = ids.indexOf(id);
    if (idx !== -1) ids.splice(idx, 1);
    saveScheduleIds(term, ids);
    loadSections();
    refreshSchedule();
    showAlert("Section removed.", "info");
}

clearBtn.addEventListener("click", function () {
    var term = currentTerm();
    saveScheduleIds(term, []);
    loadSections();
    refreshSchedule();
    showAlert("Schedule cleared.", "info");
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
    fetch("/api/sections/batch?ids=" + ids.join(","))
        .then(function (r) { return r.json(); })
        .then(function (sections) {
            renderGrid(sections);
            renderAddedTable(sections);
            updateSummary(sections, findConflictIds(sections));
        });
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

    clearBtn.classList.toggle("d-none", sections.length === 0);
}

function renderGrid(sections) {
    var grid = document.getElementById("weeklyGrid");
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
    html += '<div class="time-header"></div>';
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
        var half = isHalfSemester(sec.session);
        html += '<tr class="' + (isConflict ? 'table-danger-subtle' : '') + '">';
        html += '<td><span class="color-dot" style="background:' + color + '"></span></td>';
        html += '<td class="fw-semibold text-nowrap">' + sec.course_code + '</td>';
        html += '<td>' + (sec.course_name || '') + '</td>';
        html += '<td>' + (sec.section_code || '') + '</td>';
        html += '<td>';
        if (half) {
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
        html += '<td><button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="removeSection(' + sec.id + ')" title="Remove">&times;</button></td>';
        html += '</tr>';
    }
    body.innerHTML = html;
}
