var subjectSelect = document.getElementById("subjectSelect");
var levelSelect = document.getElementById("levelSelect");
var termSelect = document.getElementById("termSelect");
var searchInput = document.getElementById("searchInput");
var filterBtn = document.getElementById("filterBtn");
var courseBody = document.getElementById("courseBody");
var courseCount = document.getElementById("courseCount");
var detailModalEl = document.getElementById("courseDetailModal");
var detailModal = detailModalEl ? new bootstrap.Modal(detailModalEl) : null;
var detailWishlistBtn = document.getElementById("detailWishlistBtn");
var detailCourse = null;
var wishlistCourseIds = {};

function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function attr(value) {
    return escapeHtml(value).replace(/'/g, "&#39;");
}

function dash(value) {
    var text = value === null || value === undefined ? "" : String(value).trim();
    return text ? escapeHtml(text) : "&mdash;";
}

function timeText(section) {
    var start = (section.start_time || "").trim();
    var end = (section.end_time || "").trim();
    if (start && end) return escapeHtml(start + " - " + end);
    return dash(start || end);
}

function isWishlisted(courseId) {
    return Boolean(wishlistCourseIds[String(courseId)]);
}

function setWishlist(courseId, on) {
    if (on) {
        wishlistCourseIds[String(courseId)] = true;
    } else {
        delete wishlistCourseIds[String(courseId)];
    }
    updateWishlistButtons(courseId);
}

function updateWishlistButtons(courseId) {
    var selector = '.catalog-wishlist-btn[data-course-id="' + String(courseId) + '"]';
    var buttons = document.querySelectorAll(selector);
    var on = isWishlisted(courseId);
    for (var i = 0; i < buttons.length; i++) {
        buttons[i].classList.toggle("catalog-wishlist-on", on);
        buttons[i].setAttribute("aria-pressed", on ? "true" : "false");
        buttons[i].title = on ? "Remove from wishlist" : "Add to wishlist";
        buttons[i].innerHTML = on ? "&#9829;" : "&#9825;";
    }
    if (detailCourse && String(detailCourse.id) === String(courseId) && detailWishlistBtn) {
        detailWishlistBtn.textContent = on ? "Remove from wishlist" : "Add to wishlist";
        detailWishlistBtn.classList.toggle("btn-accent", on);
        detailWishlistBtn.classList.toggle("btn-outline-accent", !on);
    }
}

function refreshWishlistButtons() {
    var buttons = document.querySelectorAll(".catalog-wishlist-btn");
    for (var i = 0; i < buttons.length; i++) {
        updateWishlistButtons(buttons[i].getAttribute("data-course-id"));
    }
}

function fetchWishlist() {
    return fetch("/api/wishlist")
        .then(function (r) {
            if (r.status === 401) return [];
            if (!r.ok) throw new Error("Could not load wishlist.");
            return r.json();
        })
        .then(function (rows) {
            wishlistCourseIds = {};
            for (var i = 0; i < rows.length; i++) {
                wishlistCourseIds[String(rows[i].course_id)] = true;
            }
            refreshWishlistButtons();
        })
        .catch(function () {
            wishlistCourseIds = {};
        });
}

function toggleWishlist(courseId) {
    var on = isWishlisted(courseId);
    var url = on ? "/api/wishlist/" + encodeURIComponent(courseId) : "/api/wishlist";
    var opts = on
        ? { method: "DELETE" }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ course_id: Number(courseId) }),
        };
    return fetch(url, opts)
        .then(function (r) {
            if (r.status === 401) {
                window.location.href = "/account";
                throw new Error("Unauthorized");
            }
            if (!r.ok) throw new Error("Could not update wishlist.");
            return r.json();
        })
        .then(function () {
            setWishlist(courseId, !on);
        });
}

function paramsForCourses() {
    var params = new URLSearchParams();
    if (subjectSelect.value) params.set("subject", subjectSelect.value);
    if (levelSelect.value) params.set("level", levelSelect.value);
    if (termSelect.value) params.set("term", termSelect.value);
    if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
    return params.toString();
}

function loadCourses() {
    fetch("/api/courses?" + paramsForCourses())
        .then(function (r) { return r.json(); })
        .then(function (courses) {
            var html = "";
            for (var i = 0; i < courses.length; i++) {
                var c = courses[i];
                html += "<tr>";
                html += '<td class="text-center">';
                html += '<button type="button" class="btn btn-link btn-sm catalog-wishlist-btn" ';
                html += 'data-course-id="' + attr(c.id) + '" aria-label="Toggle wishlist" aria-pressed="false">&#9825;</button>';
                html += "</td>";
                html += '<td class="fw-semibold text-nowrap">' + dash(c.course_code) + "</td>";
                html += "<td>" + dash(c.course_name) + "</td>";
                html += '<td class="small">' + dash(c.prerequisites) + "</td>";
                html += "<td>" + dash(c.term_infered) + "</td>";
                html += '<td class="text-nowrap">';
                html += '<button type="button" class="btn btn-outline-accent btn-xs catalog-detail-btn me-1" data-course-id="' + attr(c.id) + '">Detail</button>';
                if (c.course_url) {
                    html += '<a href="' + attr(c.course_url) + '" target="_blank" rel="noopener" class="btn btn-outline-secondary btn-xs">View</a>';
                }
                html += "</td></tr>";
            }
            courseBody.innerHTML = html || '<tr><td colspan="6" class="text-muted text-center py-3">No courses found.</td></tr>';
            courseCount.textContent = courses.length + " course" + (courses.length !== 1 ? "s" : "") + ".";
            refreshWishlistButtons();
        });
}

function renderDetail(course) {
    detailCourse = course;
    document.getElementById("courseDetailTitle").textContent = course.course_name || "Course detail";
    document.getElementById("courseDetailCode").textContent = course.course_code || "";
    document.getElementById("courseDetailPrereqs").innerHTML = dash(course.prerequisites);
    document.getElementById("courseDetailUrl").innerHTML = course.course_url
        ? '<a href="' + attr(course.course_url) + '" target="_blank" rel="noopener">' + escapeHtml(course.course_url) + "</a>"
        : "&mdash;";
    document.getElementById("courseDetailAlert").classList.add("d-none");

    var rows = course.sections || [];
    var html = "";
    for (var i = 0; i < rows.length; i++) {
        var s = rows[i];
        html += "<tr>";
        html += "<td>" + dash(s.term_label) + "</td>";
        html += "<td>" + dash(s.section_code) + "</td>";
        html += "<td>" + dash(s.days) + "</td>";
        html += "<td>" + timeText(s) + "</td>";
        html += "<td>" + dash(s.mode) + "</td>";
        html += "<td>" + dash(s.location) + "</td>";
        html += "<td>" + dash(s.dates) + "</td>";
        html += '<td class="text-end text-nowrap">';
        html += '<button type="button" class="btn btn-accent btn-xs catalog-plan-btn" ';
        html += 'data-term="' + attr(s.term_label || "") + '" data-section-id="' + attr(s.id) + '">Plan in schedule</button>';
        html += "</td></tr>";
    }
    document.getElementById("courseDetailSections").innerHTML =
        html || '<tr><td colspan="8" class="text-muted text-center py-3">No sections found for this course.</td></tr>';

    updateWishlistButtons(course.id);
    if (detailModal) detailModal.show();
}

function showDetailError(message) {
    var alertEl = document.getElementById("courseDetailAlert");
    alertEl.textContent = message;
    alertEl.classList.remove("d-none");
}

function loadCourseDetail(courseId) {
    fetch("/api/courses/" + encodeURIComponent(courseId))
        .then(function (r) {
            if (!r.ok) throw new Error("Could not load course detail.");
            return r.json();
        })
        .then(renderDetail)
        .catch(function (err) {
            if (detailModal) detailModal.show();
            showDetailError(err && err.message ? err.message : "Could not load course detail.");
        });
}

fetch("/api/course-subjects")
    .then(function (r) { return r.json(); })
    .then(function (subjects) {
        for (var i = 0; i < subjects.length; i++) {
            var opt = document.createElement("option");
            opt.value = subjects[i];
            opt.textContent = subjects[i];
            subjectSelect.appendChild(opt);
        }
        return fetchWishlist();
    })
    .then(loadCourses);

filterBtn.addEventListener("click", loadCourses);
subjectSelect.addEventListener("change", loadCourses);
levelSelect.addEventListener("change", loadCourses);
termSelect.addEventListener("change", loadCourses);
searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") loadCourses();
});

courseBody.addEventListener("click", function (e) {
    var wishlistBtn = e.target.closest(".catalog-wishlist-btn");
    if (wishlistBtn) {
        toggleWishlist(wishlistBtn.getAttribute("data-course-id")).catch(function (err) {
            if (err && err.message === "Unauthorized") return;
            courseCount.textContent = "Could not update wishlist. Try again.";
        });
        return;
    }
    var detailBtn = e.target.closest(".catalog-detail-btn");
    if (detailBtn) {
        loadCourseDetail(detailBtn.getAttribute("data-course-id"));
    }
});

document.getElementById("courseDetailSections").addEventListener("click", function (e) {
    var btn = e.target.closest(".catalog-plan-btn");
    if (!btn) return;
    var term = btn.getAttribute("data-term") || "";
    var id = Number(btn.getAttribute("data-section-id"));
    localStorage.setItem("preselect_section", JSON.stringify({ term: term, id: id }));
    window.location.href = "/?term=" + encodeURIComponent(term);
});

if (detailWishlistBtn) {
    detailWishlistBtn.addEventListener("click", function () {
        if (!detailCourse) return;
        toggleWishlist(detailCourse.id).catch(function (err) {
            if (err && err.message === "Unauthorized") return;
            showDetailError("Could not update wishlist.");
        });
    });
}
