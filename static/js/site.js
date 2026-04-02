/* All front-end logic for this app: planner (saved in the browser) + course list + helper. */
(function () {
  var PLAN_KEY = "utpb_planner_v1";

  function loadPlan() {
    try {
      var raw = localStorage.getItem(PLAN_KEY);
      var a = raw ? JSON.parse(raw) : [];
      return Array.isArray(a) ? a : [];
    } catch (e) {
      return [];
    }
  }

  function savePlan(items) {
    localStorage.setItem(PLAN_KEY, JSON.stringify(items));
    var badge = document.getElementById("nav-plan-count");
    if (badge) badge.textContent = String(items.length);
  }

  function addToPlan(item) {
    var items = loadPlan();
    var id = String(item.section_id);
    for (var i = 0; i < items.length; i++) {
      if (String(items[i].section_id) === id) return false;
    }
    items.push(item);
    savePlan(items);
    return true;
  }

  function removeFromPlan(sectionId) {
    var id = String(sectionId);
    savePlan(
      loadPlan().filter(function (x) {
        return String(x.section_id) !== id;
      })
    );
  }

  function clearPlan() {
    savePlan([]);
  }

  function normCode(s) {
    return String(s || "")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase();
  }

  function fmtTime(hms) {
    if (!hms) return "";
    var p = String(hms).split(":");
    if (p.length < 2) return hms;
    var h = parseInt(p[0], 10);
    var m = parseInt(p[1], 10);
    var am = h < 12;
    var h12 = h % 12 || 12;
    return h12 + ":" + String(m).padStart(2, "0") + " " + (am ? "AM" : "PM");
  }

  function sectionLine(s) {
    var parts = [];
    if (s.section_code) parts.push("Sec. " + s.section_code);
    if (s.semester) parts.push(s.semester);
    if (s.instructor) parts.push(s.instructor);
    if (s.days) parts.push(s.days);
    var st = fmtTime(s.start_time);
    var en = fmtTime(s.end_time);
    if (st && en) parts.push(st + "–" + en);
    else if (st || en) parts.push(st || en);
    if (s.room_number) parts.push(s.room_number);
    if (s.delivery_mode) parts.push(s.delivery_mode);
    if (s.enrolled != null && s.seat_limit != null) {
      parts.push(s.enrolled + "/" + s.seat_limit + " enrolled");
    } else if (s.seat_limit != null) parts.push("limit " + s.seat_limit);
    return parts.join(" · ");
  }

  /* Build one saved row: course = full course from catalog (or null); sec = section object */
  function planRow(course, sec) {
    return {
      section_id: sec.section_id,
      course_code: course ? course.course_code : sec.course_code,
      title: course ? course.title : sec.course_code,
      credits: course ? course.credits : 0,
      section_code: sec.section_code,
      semester: sec.semester,
      instructor: sec.instructor,
      days: sec.days,
      start_time: sec.start_time,
      end_time: sec.end_time,
      room_number: sec.room_number,
      delivery_mode: sec.delivery_mode,
      enrolled: sec.enrolled,
      seat_limit: sec.seat_limit,
    };
  }

  function findSection(allCourses, code, sid) {
    for (var i = 0; i < allCourses.length; i++) {
      if (allCourses[i].course_code !== code) continue;
      var secs = allCourses[i].sections || [];
      for (var j = 0; j < secs.length; j++) {
        if (String(secs[j].section_id) === String(sid)) {
          return { course: allCourses[i], sec: secs[j] };
        }
      }
    }
    return null;
  }

  function findCourse(allCourses, code) {
    for (var i = 0; i < allCourses.length; i++) {
      if (allCourses[i].course_code === code) return allCourses[i];
    }
    return null;
  }

  /* -------- Planner page -------- */
  var plannerList = document.getElementById("planner-list");
  if (plannerList) {
    var emptyEl = document.getElementById("planner-empty");
    var wrapEl = document.getElementById("planner-wrap");
    var totalEl = document.getElementById("planner-total");

    function renderPlanner() {
      var items = loadPlan();
      plannerList.innerHTML = "";
      if (!items.length) {
        emptyEl.classList.remove("hidden");
        wrapEl.classList.add("hidden");
        return;
      }
      emptyEl.classList.add("hidden");
      wrapEl.classList.remove("hidden");
      var credits = 0;
      for (var i = 0; i < items.length; i++) {
        var it = items[i];
        credits += Number(it.credits) || 0;
        var li = document.createElement("li");
        li.className = "planner-item";
        var head = document.createElement("div");
        head.className = "planner-item-head";
        var strong = document.createElement("strong");
        strong.className = "planner-code";
        strong.textContent = it.course_code;
        head.appendChild(strong);
        head.appendChild(document.createTextNode(" " + (it.title || "")));
        var meta = document.createElement("p");
        meta.className = "planner-meta";
        meta.textContent = sectionLine(it);
        var rm = document.createElement("button");
        rm.type = "button";
        rm.className = "btn-remove-plan";
        rm.textContent = "Remove";
        rm.setAttribute("data-sid", String(it.section_id));
        li.appendChild(head);
        li.appendChild(meta);
        li.appendChild(rm);
        plannerList.appendChild(li);
      }
      totalEl.textContent =
        items.length +
        " section(s) · about " +
        credits +
        " credit(s)";
    }

    plannerList.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".btn-remove-plan");
      if (!btn) return;
      removeFromPlan(btn.getAttribute("data-sid"));
      renderPlanner();
    });

    var clearBtn = document.getElementById("planner-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (confirm("Remove everything from your plan?")) {
          clearPlan();
          renderPlanner();
        }
      });
    }

    renderPlanner();
  }

  /* -------- Courses page -------- */
  var listEl = document.getElementById("course-list");
  if (!listEl) {
    var b = document.getElementById("nav-plan-count");
    if (b) b.textContent = String(loadPlan().length);
    return;
  }

  var statusEl = document.getElementById("status");
  var filterEl = document.getElementById("filter");
  var countEl = document.getElementById("count");
  var showAllBtn = document.getElementById("show-all-courses");
  var listNoteEl = document.getElementById("course-list-note");
  var msgEl = document.getElementById("assist-message");
  var btnEl = document.getElementById("assist-submit");
  var assistStatusEl = document.getElementById("assist-status");
  var outEl = document.getElementById("assist-output");

  var allCourses = [];
  var filterBound = false;

  function courseCard(course, recommendedOnly) {
    var li = document.createElement("li");
    li.className = "course-card";
    li.dataset.code = course.course_code.toLowerCase();
    li.dataset.title = course.title.toLowerCase();
    var s1 = recommendedOnly ? "Recommended section" : "Section";
    var sN = recommendedOnly ? "Recommended sections" : "Sections";

    var h2 = document.createElement("h2");
    var span = document.createElement("span");
    span.className = "code";
    span.textContent = course.course_code;
    h2.appendChild(span);
    h2.appendChild(document.createTextNode(course.title));

    var meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      course.credits === 1 ? "1 credit" : course.credits + " credits";

    var desc = document.createElement("p");
    desc.className = "desc";
    desc.textContent = course.description || "No description yet.";

    li.appendChild(h2);
    li.appendChild(meta);
    li.appendChild(desc);

    if (course.sections && course.sections.length) {
      var wrap = document.createElement("div");
      wrap.className = "sections";
      var st = document.createElement("div");
      st.className = "sections-title";
      st.textContent =
        course.sections.length === 1
          ? s1
          : sN + " (" + course.sections.length + ")";
      wrap.appendChild(st);
      var ul = document.createElement("ul");
      ul.className = "section-lines";
      for (var i = 0; i < course.sections.length; i++) {
        var sec = course.sections[i];
        var row = document.createElement("li");
        row.className = "section-line-row";
        var tx = document.createElement("span");
        tx.className = "section-line-text";
        tx.textContent = sectionLine(sec);
        var addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn-add-plan";
        addBtn.textContent = "Add";
        addBtn.setAttribute("data-sid", String(sec.section_id));
        addBtn.setAttribute("data-code", course.course_code);
        row.appendChild(tx);
        row.appendChild(addBtn);
        ul.appendChild(row);
      }
      wrap.appendChild(ul);
      li.appendChild(wrap);
    }

    if (course.prerequisites && course.prerequisites.length) {
      var pr = document.createElement("div");
      pr.className = "prereq";
      var strong = document.createElement("strong");
      strong.textContent = "Prerequisites: ";
      pr.appendChild(strong);
      pr.appendChild(
        document.createTextNode(course.prerequisites.join(", "))
      );
      li.appendChild(pr);
    }

    return li;
  }

  function runFilter() {
    var q = (filterEl.value || "").trim().toLowerCase();
    var n = 0;
    var cards = listEl.querySelectorAll(".course-card");
    for (var i = 0; i < cards.length; i++) {
      var el = cards[i];
      var ok =
        !q ||
        el.dataset.code.indexOf(q) !== -1 ||
        el.dataset.title.indexOf(q) !== -1;
      el.classList.toggle("hidden", !ok);
      if (ok) n += 1;
    }
    var rec = showAllBtn && !showAllBtn.classList.contains("hidden");
    countEl.textContent = n + (rec ? " shown (recommended)" : " shown");
  }

  function buildRecommendedList(courses, recSecs, extraCodes) {
    var ids = {};
    var hasRec = {};
    for (var i = 0; i < (recSecs || []).length; i++) {
      var s = recSecs[i];
      if (s.section_id != null) ids[String(s.section_id)] = true;
      var k = normCode(s.course_code);
      if (k) hasRec[k] = true;
    }
    var extra = {};
    for (var e = 0; e < (extraCodes || []).length; e++) {
      var k2 = normCode(extraCodes[e]);
      if (k2) extra[k2] = true;
    }
    var out = [];
    for (var c = 0; c < courses.length; c++) {
      var course = courses[c];
      var key = normCode(course.course_code);
      var fromS = hasRec[key];
      var fromE = extra[key];
      if (!fromS && !fromE) continue;
      var secs = [];
      if (fromS) {
        var all = course.sections || [];
        for (var t = 0; t < all.length; t++) {
          if (ids[String(all[t].section_id)]) secs.push(all[t]);
        }
        if (!secs.length) secs = all.slice();
      } else {
        secs = (course.sections || []).slice();
      }
      out.push({
        course_code: course.course_code,
        title: course.title,
        credits: course.credits,
        description: course.description,
        prerequisites: course.prerequisites,
        sections: secs,
      });
    }
    out.sort(function (a, b) {
      return a.course_code.localeCompare(b.course_code);
    });
    return out;
  }

  function showCourses(courses, mode) {
    listEl.innerHTML = "";
    var rec = mode === "recommended";
    for (var i = 0; i < courses.length; i++) {
      listEl.appendChild(courseCard(courses[i], rec));
    }
    if (mode === "recommended") {
      showAllBtn.classList.remove("hidden");
      listNoteEl.textContent =
        "Showing suggested courses and sections for your question.";
      listNoteEl.classList.remove("hidden");
      listEl.classList.add("course-list--recommended");
    } else {
      showAllBtn.classList.add("hidden");
      listNoteEl.textContent = "";
      listNoteEl.classList.add("hidden");
      listEl.classList.remove("course-list--recommended");
      countEl.textContent = courses.length + " courses";
    }
    if (!filterBound) {
      filterEl.addEventListener("input", runFilter);
      filterBound = true;
    }
    runFilter();
  }

  function applyAssistantFilter(data) {
    var secs = data.sections || [];
    var ex = data.suggested_course_codes || [];
    if (!secs.length && !ex.length) return;
    var filtered = buildRecommendedList(allCourses, secs, ex);
    if (!filtered.length) {
      assistStatusEl.textContent =
        "Could not match suggestions. Showing all courses.";
      assistStatusEl.classList.add("error");
      filterEl.value = "";
      showCourses(allCourses, "all");
      return;
    }
    filterEl.value = "";
    showCourses(filtered, "recommended");
  }

  function showAssistantReply(data, hasRec) {
    outEl.classList.remove("hidden");
    outEl.innerHTML = "";
    var p = document.createElement("p");
    p.className = "assist-reply";
    p.textContent = data.reply || "";
    outEl.appendChild(p);

    if (data.warnings && data.warnings.length) {
      var note = document.createElement("div");
      note.innerHTML = "<strong>Notes</strong>";
      outEl.appendChild(note);
      var ul = document.createElement("ul");
      ul.className = "assist-list";
      for (var w = 0; w < data.warnings.length; w++) {
        var li = document.createElement("li");
        li.textContent = data.warnings[w];
        ul.appendChild(li);
      }
      outEl.appendChild(ul);
    }

    if (data.sections && data.sections.length) {
      var addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "btn-add-suggestions";
      addBtn.textContent = "Add suggested sections to My plan";
      addBtn.addEventListener("click", function () {
        var added = 0;
        for (var i = 0; i < data.sections.length; i++) {
          var row = data.sections[i];
          var course = findCourse(allCourses, row.course_code);
          if (addToPlan(planRow(course, row))) added += 1;
        }
        addBtn.textContent =
          added ? "Added " + added + " — open My plan" : "Already in plan";
        addBtn.disabled = true;
      });
      outEl.appendChild(addBtn);
    }

    if (hasRec) {
      var f = document.createElement("p");
      f.className = "assist-followup";
      f.textContent =
        "Matches are listed below. Use Show all courses for the full catalog.";
      outEl.appendChild(f);
    }

    var problems = (data.errors || []).concat(data.conflicts || []);
    for (var e = 0; e < problems.length; e++) {
      if (e === 0) {
        var h = document.createElement("div");
        h.style.marginTop = "0.65rem";
        h.innerHTML = "<strong>Heads up</strong>";
        outEl.appendChild(h);
      }
      var sp = document.createElement("span");
      sp.className = "assist-tag bad";
      sp.textContent = problems[e];
      outEl.appendChild(sp);
    }
  }

  listEl.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".btn-add-plan");
    if (!btn) return;
    var found = findSection(
      allCourses,
      btn.getAttribute("data-code"),
      btn.getAttribute("data-sid")
    );
    if (!found) return;
    if (addToPlan(planRow(found.course, found.sec))) {
      btn.textContent = "Added";
      btn.disabled = true;
    }
  });

  statusEl.textContent = "Loading…";
  fetch("/api/courses")
    .then(function (r) {
      return r.json().then(function (data) {
        return { ok: r.ok, data: data };
      });
    })
    .then(function (x) {
      if (!x.ok) throw new Error((x.data && x.data.error) || "Load failed");
      if (!Array.isArray(x.data)) throw new Error("Bad data");
      allCourses = x.data;
      showCourses(allCourses, "all");
      statusEl.textContent = "";
    })
    .catch(function (err) {
      statusEl.textContent = "Could not load courses.";
      statusEl.classList.add("error");
      console.error(err);
    });

  showAllBtn.addEventListener("click", function () {
    assistStatusEl.textContent = "";
    assistStatusEl.classList.remove("error");
    showCourses(allCourses, "all");
  });

  btnEl.addEventListener("click", function () {
    var message = (msgEl.value || "").trim();
    if (!message) {
      assistStatusEl.textContent =
        "Describe semester, credits or courses, and time preferences.";
      assistStatusEl.classList.add("error");
      return;
    }
    assistStatusEl.classList.remove("error");
    assistStatusEl.textContent = "Thinking…";
    btnEl.disabled = true;
    outEl.classList.add("hidden");
    outEl.innerHTML = "";

    fetch("/api/schedule-assist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (x) {
        if (!x.ok) {
          assistStatusEl.textContent = x.data.error || "Error.";
          assistStatusEl.classList.add("error");
          return;
        }
        assistStatusEl.textContent = "";
        var secs = x.data.sections || [];
        var ex = x.data.suggested_course_codes || [];
        var hasRec = secs.length > 0 || ex.length > 0;
        if (hasRec) applyAssistantFilter(x.data);
        showAssistantReply(x.data, hasRec);
      })
      .catch(function (err) {
        assistStatusEl.textContent = "Could not reach the server.";
        assistStatusEl.classList.add("error");
        console.error(err);
      })
      .then(function () {
        btnEl.disabled = false;
      });
  });

  var badge = document.getElementById("nav-plan-count");
  if (badge) badge.textContent = String(loadPlan().length);
})();
