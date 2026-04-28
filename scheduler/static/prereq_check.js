(function () {
    var resultsEl = document.getElementById("sectionResults");
    var summaryEl = document.getElementById("prereqChip");
    var timer = null;

    function normalizeCode(raw) {
        var s = String(raw || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
        var m = s.match(/^([A-Z]{2,5})([0-9]{4})$/);
        return m ? m[1] + " " + m[2] : String(raw || "").trim();
    }

    function codeFromCard(card) {
        var codeEl = card.querySelector(".fw-bold");
        return codeEl ? normalizeCode(codeEl.textContent) : "";
    }

    function clearChips() {
        if (!resultsEl) return;
        var chips = resultsEl.querySelectorAll(".prereq-missing-chip");
        for (var i = 0; i < chips.length; i++) {
            chips[i].remove();
        }
    }

    function updateSummary(count) {
        if (!summaryEl) return;
        summaryEl.classList.toggle("d-none", count <= 0);
        summaryEl.innerHTML = count > 0
            ? '<span class="mx-1 text-muted">&middot;</span><span class="prereq-summary-chip">' +
                count + ' planned course' + (count === 1 ? '' : 's') + ' with missing prereqs</span>'
            : "";
    }

    function injectChip(card, missing) {
        if (!missing || !missing.length) return;
        var chip = document.createElement("div");
        chip.className = "prereq-missing-chip";
        chip.textContent = "Prereqs missing: " + missing.join(", ");
        card.appendChild(chip);
    }

    function renderPrereqChecks(data) {
        var cards = Array.prototype.slice.call(resultsEl.querySelectorAll(".section-card"));
        var missingCount = 0;
        clearChips();
        for (var i = 0; i < cards.length; i++) {
            var code = codeFromCard(cards[i]);
            var result = data[code] || data[code.replace(/\s+/g, "")];
            if (!result || !result.missing || !result.missing.length) continue;
            missingCount += 1;
            injectChip(cards[i], result.missing);
        }
        updateSummary(missingCount);
    }

    function checkVisibleCards() {
        if (!resultsEl) return;
        var cards = Array.prototype.slice.call(resultsEl.querySelectorAll(".section-card"));
        var codes = [];
        var seen = {};
        for (var i = 0; i < cards.length; i++) {
            var code = codeFromCard(cards[i]);
            if (!code || seen[code]) continue;
            seen[code] = true;
            codes.push(code.replace(/\s+/g, ""));
        }
        clearChips();
        updateSummary(0);
        if (!codes.length) return;
        var term = "";
        if (typeof currentTerm === "function") {
            term = currentTerm();
        } else {
            var termEl = document.getElementById("termValue");
            term = termEl ? termEl.value : "";
        }
        var url = "/api/prereq-check?codes=" + encodeURIComponent(codes.join(","));
        if (term) {
            url += "&term=" + encodeURIComponent(term);
        }
        fetch(url)
            .then(function (r) {
                if (!r.ok) throw new Error("prereq-check");
                return r.json();
            })
            .then(renderPrereqChecks)
            .catch(function () {
                clearChips();
                updateSummary(0);
            });
    }

    function scheduleCheck() {
        if (timer) clearTimeout(timer);
        timer = setTimeout(checkVisibleCards, 180);
    }

    document.addEventListener("DOMContentLoaded", function () {
        resultsEl = document.getElementById("sectionResults");
        summaryEl = document.getElementById("prereqChip");
        if (!resultsEl) return;
        var observer = new MutationObserver(scheduleCheck);
        observer.observe(resultsEl, { childList: true });
        scheduleCheck();
    });
})();
