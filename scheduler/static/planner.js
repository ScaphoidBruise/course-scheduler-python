var COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B",
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316",
    "#6366F1", "#06B6D4", "#84CC16", "#D946EF",
];
var DAY_CHARS = ["M", "T", "W", "R", "F"];

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
        if (code && codes.indexOf(code) === -1) codes.push(code);
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

function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function fmt(value) {
    var n = Number(value || 0);
    return Math.abs(n - Math.round(n)) < 0.01 ? String(Math.round(n)) : n.toFixed(1);
}

function fetchJson(url, options) {
    return fetch(url, options).then(function (r) {
        if (r.status === 401) {
            window.location.href = "/account";
            throw new Error("Authentication required");
        }
        if (!r.ok) throw new Error("Request failed");
        return r.json();
    });
}

function showAlert(message, type) {
    var box = document.getElementById("plannerAlert");
    box.innerHTML = '<div class="alert alert-' + type + ' py-2">' + escapeHtml(message) + '</div>';
}

function creditClass(credits) {
    var n = Number(credits || 0);
    if (n >= 22) return "planner-credit-overload";
    if (n >= 19) return "planner-credit-heavy";
    if (n >= 12) return "planner-credit-good";
    return "planner-credit-low";
}

function allSections(terms) {
    var out = [];
    for (var i = 0; i < terms.length; i++) {
        out = out.concat(terms[i].sections || []);
    }
    return out;
}

function renderHero(totals) {
    var completed = Number(totals.credits_completed || 0);
    var target = Number(totals.credits_target || 120);
    var percent = target > 0 ? Math.min(100, Math.round((completed / target) * 100)) : 0;
    document.getElementById("creditsCompleted").textContent = fmt(completed);
    document.getElementById("creditsTarget").textContent = fmt(target);
    document.getElementById("creditsPlanned").textContent = fmt(totals.credits_planned || 0);
    document.getElementById("expectedGraduation").textContent = totals.expected_graduation_label || "--";
    document.getElementById("targetInput").value = fmt(target);
    var bar = document.getElementById("graduationProgress");
    bar.style.width = percent + "%";
    bar.textContent = percent >= 12 ? percent + "%" : "";
}

function renderTimeline(terms) {
    var wrap = document.getElementById("termTimeline");
    if (!terms.length) {
        wrap.innerHTML = '<div class="planner-empty">No planning terms yet. Add courses on the Schedule page to start building your graduation path.</div>';
        return;
    }
    var colorMap = buildColorMap(allSections(terms));
    var html = "";
    for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        var sections = t.sections || [];
        var conflictIds = findConflictIds(sections);
        html += '<article class="planner-term-card card' + (t.is_current ? ' is-current' : '') + '">';
        html += '<div class="card-body">';
        html += '<div class="d-flex justify-content-between align-items-start gap-2 mb-2">';
        html += '<div><h3 class="h6 mb-1">' + escapeHtml(t.label) + '</h3>';
        html += '<span class="badge rounded-pill planner-season-pill">' + escapeHtml(t.season || "Term") + '</span></div>';
        html += '<span class="badge rounded-pill planner-credit-pill ' + creditClass(t.credits) + '">' + fmt(t.credits) + ' hrs</span>';
        html += '</div>';
        if (t.has_conflicts) {
            html += '<div class="badge text-bg-danger mb-2">Conflict detected</div>';
        } else if (t.is_current) {
            html += '<div class="badge text-bg-light border mb-2">Current term</div>';
        }
        html += '<div class="planner-section-list small">';
        if (!sections.length) {
            html += '<p class="text-muted mb-0">No saved sections.</p>';
        }
        for (var j = 0; j < sections.length; j++) {
            var s = sections[j];
            var color = colorMap[s.course_code] || "#888";
            var cls = conflictIds[s.id] ? " planner-section-conflict" : "";
            html += '<div class="planner-section-item' + cls + '">';
            html += '<span class="planner-section-dot" style="background:' + color + '"></span>';
            html += '<span>' + escapeHtml(s.course_code || "Course") + '</span>';
            html += '</div>';
        }
        html += '</div>';
        html += '<a class="btn btn-outline-accent btn-sm mt-3" href="/?term=' + encodeURIComponent(t.label) + '">Open in Schedule</a>';
        html += '</div></article>';
    }
    wrap.innerHTML = html;
}

function renderCreditChart(terms) {
    var wrap = document.getElementById("creditChart");
    if (!terms.length) {
        wrap.innerHTML = '<p class="text-muted small mb-0">No terms to chart.</p>';
        return;
    }
    var width = Math.max(560, terms.length * 82);
    var height = 220;
    var pad = 34;
    var maxCredits = 24;
    for (var i = 0; i < terms.length; i++) {
        maxCredits = Math.max(maxCredits, Number(terms[i].credits || 0));
    }
    var plotH = height - pad * 2;
    var band = (width - pad * 2) / terms.length;
    var html = '<svg class="planner-chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="Credits per term">';
    html += '<line class="planner-chart-axis" x1="' + pad + '" y1="' + (height - pad) + '" x2="' + (width - pad + 10) + '" y2="' + (height - pad) + '"></line>';
    for (var j = 0; j < terms.length; j++) {
        var credits = Number(terms[j].credits || 0);
        var barH = maxCredits > 0 ? (credits / maxCredits) * plotH : 0;
        var x = pad + j * band + band * 0.18;
        var y = height - pad - barH;
        var barW = band * 0.64;
        html += '<rect class="planner-chart-bar" rx="6" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + barH.toFixed(1) + '"></rect>';
        html += '<text class="planner-chart-label" text-anchor="middle" x="' + (x + barW / 2).toFixed(1) + '" y="' + (y - 6).toFixed(1) + '">' + fmt(credits) + '</text>';
        html += '<text class="planner-chart-muted" text-anchor="middle" x="' + (x + barW / 2).toFixed(1) + '" y="' + (height - 10) + '">' + escapeHtml(shortTermLabel(terms[j].label)) + '</text>';
    }
    html += '</svg>';
    wrap.innerHTML = html;
}

function shortTermLabel(label) {
    var parts = String(label || "").split(/\s+/);
    if (parts.length < 2) return label || "";
    return parts[0].slice(0, 3) + " " + parts[1].slice(2);
}

function termGpaPoints(parsed) {
    var terms = parsed && Array.isArray(parsed.terms) ? parsed.terms : [];
    var points = [];
    for (var i = 0; i < terms.length; i++) {
        var item = terms[i];
        if (!item || typeof item !== "object") continue;
        var gpa = Number(item.term_gpa || item.gpa);
        var label = item.label || item.term || item.name;
        if (!isNaN(gpa) && gpa > 0 && label) {
            points.push({ label: label, gpa: gpa });
        }
    }
    return points;
}

function renderGpa(profile) {
    var p = profile || {};
    document.getElementById("cumulativeGpa").textContent = p.cumulative_gpa === null || p.cumulative_gpa === undefined ? "--" : Number(p.cumulative_gpa).toFixed(3);
    document.getElementById("lastTermGpa").textContent = p.last_term_gpa === null || p.last_term_gpa === undefined ? "--" : Number(p.last_term_gpa).toFixed(3);
    var points = termGpaPoints(p.transcript_parsed);
    var wrap = document.getElementById("gpaSparkline");
    if (points.length < 2) {
        wrap.innerHTML = "";
        return;
    }
    var width = 320;
    var height = 72;
    var pad = 8;
    var path = "";
    for (var i = 0; i < points.length; i++) {
        var x = pad + (i / (points.length - 1)) * (width - pad * 2);
        var y = height - pad - (Math.min(4, points[i].gpa) / 4) * (height - pad * 2);
        path += (i === 0 ? "M" : "L") + x.toFixed(1) + " " + y.toFixed(1) + " ";
    }
    wrap.innerHTML = '<div class="text-muted small mb-1">GPA trend</div><svg class="planner-sparkline" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="GPA trend"><path class="planner-sparkline-path" d="' + path + '"></path></svg>';
}

function loadPlanner() {
    fetchJson("/api/planner-overview")
        .then(function (data) {
            renderHero(data.totals || {});
            renderTimeline(data.terms || []);
            renderCreditChart(data.terms || []);
        })
        .catch(function (err) {
            showAlert(err.message || "Could not load planner.", "danger");
        });

    fetchJson("/api/profile")
        .then(function (data) { renderGpa(data.profile || {}); })
        .catch(function () { renderGpa({}); });
}

document.addEventListener("DOMContentLoaded", function () {
    loadPlanner();
    document.getElementById("targetForm").addEventListener("submit", function (event) {
        event.preventDefault();
        fetchJson("/api/planner-target", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credits_target: document.getElementById("targetInput").value })
        }).then(loadPlanner).catch(function (err) {
            showAlert(err.message || "Could not update target.", "danger");
        });
    });
    var logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            fetch("/api/logout", { method: "POST" }).then(function () {
                window.location.href = "/account";
            });
        });
    }
});
