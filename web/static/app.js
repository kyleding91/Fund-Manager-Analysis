/* Client-side search / filter / sort for the static tables.
   Progressive enhancement: the table is fully rendered server-side; this only
   reorders and hides rows, so the page works with JS disabled too. */
/* Fund detail page: switch the visible quarter panel. */
(function () {
  "use strict";
  var chips = document.getElementById("quarter-chips");
  if (!chips) return;
  var panels = Array.prototype.slice.call(document.querySelectorAll(".qpanel"));
  chips.addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip) return;
    var slug = chip.getAttribute("data-q");
    Array.prototype.forEach.call(chips.children, function (c) { c.classList.remove("on"); });
    chip.classList.add("on");
    panels.forEach(function (p) { p.hidden = p.getAttribute("data-q") !== slug; });
  });
})();

(function () {
  "use strict";
  var table = document.getElementById("funds-table");
  if (!table) return;
  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  var search = document.getElementById("fund-search");
  var chips = document.getElementById("type-chips");
  var countEl = document.getElementById("row-count");
  var activeCat = chips ? "Investment Manager" : "__all__";

  function applyFilter() {
    var q = (search && search.value || "").trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {
      var name = r.getAttribute("data-name") || "";
      var cat = r.getAttribute("data-cat") || "__all__";
      var okText = !q || name.indexOf(q) !== -1;
      var okCat = activeCat === "__all__" || cat === activeCat;
      var show = okText && okCat;
      r.style.display = show ? "" : "none";
      if (show) shown++;
    });
    if (countEl) countEl.textContent = shown;
  }

  function sortBy(key, type, dir) {
    var mult = dir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      var av = a.getAttribute("data-" + key);
      var bv = b.getAttribute("data-" + key);
      if (type === "num") { av = parseFloat(av) || 0; bv = parseFloat(bv) || 0; return (av - bv) * mult; }
      av = (av || "").toString(); bv = (bv || "").toString();
      return av.localeCompare(bv) * mult;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
  }

  if (search) search.addEventListener("input", applyFilter);

  if (chips) {
    chips.addEventListener("click", function (e) {
      var chip = e.target.closest(".chip");
      if (!chip) return;
      Array.prototype.forEach.call(chips.children, function (c) { c.classList.remove("on"); });
      chip.classList.add("on");
      activeCat = chip.getAttribute("data-cat");
      applyFilter();
    });
  }

  Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th) {
    var type = th.getAttribute("data-sort");
    if (!type) return;
    var key = th.getAttribute("data-key");
    th.addEventListener("click", function () {
      var asc = !th.classList.contains("sorted-asc");
      Array.prototype.forEach.call(table.tHead.rows[0].cells, function (c) {
        c.classList.remove("sorted-asc", "sorted-desc");
      });
      th.classList.add(asc ? "sorted-asc" : "sorted-desc");
      var arrow = th.querySelector(".arrow");
      if (arrow) arrow.textContent = asc ? "▴" : "▾";
      sortBy(key, type, asc ? "asc" : "desc");
    });
  });

  applyFilter();
})();
