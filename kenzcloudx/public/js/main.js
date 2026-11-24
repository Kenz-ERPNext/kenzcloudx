/* KenzCloudX page behaviour. Vanilla, no dependencies, safe to load on every page (each part checks
   that its markup exists).
   - nav pill: .scrolled after 40px; mobile menu (.menu-btn) with Escape / link click / outside click to close
   - reveals: .reveal gets .in when it enters the viewport; stagger with style="--d:N" (90ms steps)
   - count-up: [data-count="87"] inside a .reveal counts from 0 when revealed (Western digits, as before)
   - accordion: button.faq-q[aria-controls] inside .faq-item toggles .open + aria-expanded
   - country tabs ([data-tabs], templates/kenz/pages/_country_tabs.html): the server sends plain in-page links and
     visible panels with no tab semantics (works without JS); here they get the ARIA roles and become a tablist with roving tabindex, arrow keys that follow
     the reading direction (in RTL ArrowLeft moves to the next tab), Home/End, an animated panel switch,
     a sliding indicator and deep links (#saudi-arabia, #india, #uae, #oman; also on hashchange)
   - timeline (.tl-card): the progress line and the step dots follow the scroll position
   prefers-reduced-motion: everything is shown at once, numbers are not animated. */
(function () {
	"use strict";
	window.__kcxMain = true;
	var root = document.documentElement;
	var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	/* ---- nav ---- */
	var nav = document.getElementById("nav");
	if (nav) {
		var onScroll = function () { nav.classList.toggle("scrolled", window.scrollY > 40); };
		window.addEventListener("scroll", onScroll, { passive: true });
		onScroll();

		var menuBtn = nav.querySelector(".menu-btn");
		var panel = document.getElementById("mobile-panel");
		if (menuBtn && panel) {
			var setMenu = function (open) {
				nav.classList.toggle("open", open);
				menuBtn.setAttribute("aria-expanded", String(open));
				menuBtn.setAttribute("aria-label", open ? menuBtn.dataset.labelClose : menuBtn.dataset.labelOpen);
			};
			menuBtn.addEventListener("click", function () { setMenu(!nav.classList.contains("open")); });
			panel.addEventListener("click", function (e) { if (e.target.closest("a")) setMenu(false); });
			document.addEventListener("keydown", function (e) {
				if (e.key === "Escape" && nav.classList.contains("open")) { setMenu(false); menuBtn.focus(); }
			});
			document.addEventListener("click", function (e) {
				if (nav.classList.contains("open") && !nav.contains(e.target)) setMenu(false);
			});
			// leaving the mobile layout with the menu open must not leave it stuck open
			window.addEventListener("resize", function () {
				if (nav.classList.contains("open") && window.innerWidth >= 1100) setMenu(false);
			});
		}
	}

	/* ---- count-up ---- */
	function countUp(el) {
		var end = parseFloat(el.getAttribute("data-count"));
		if (isNaN(end)) return;
		if (reduced) { el.textContent = String(end); return; }
		var t0 = null, dur = 1600;
		el.textContent = "0";
		function step(t) {
			if (!t0) t0 = t;
			var p = Math.min(1, (t - t0) / dur);
			el.textContent = String(Math.round(end * (1 - Math.pow(1 - p, 4))));
			if (p < 1) requestAnimationFrame(step);
		}
		requestAnimationFrame(step);
	}

	/* ---- reveals ---- */
	var reveals = document.querySelectorAll(".reveal");
	function show(el) {
		el.classList.add("in");
		el.querySelectorAll("[data-count]").forEach(countUp);
	}
	if (reduced || !("IntersectionObserver" in window)) {
		reveals.forEach(function (el) { el.classList.add("in"); });
	} else {
		var io = new IntersectionObserver(function (entries) {
			entries.forEach(function (en) {
				if (!en.isIntersecting) return;
				show(en.target);
				io.unobserve(en.target);
			});
		}, { rootMargin: "0px 0px -10% 0px", threshold: 0.12 });
		reveals.forEach(function (el) { io.observe(el); });
	}

	/* ---- accordion (opt-in markup: .faq-item > button.faq-q[aria-controls]) ---- */
	document.querySelectorAll(".faq-q[aria-controls]").forEach(function (q) {
		q.addEventListener("click", function () {
			var item = q.closest(".faq-item");
			if (!item) return;
			var open = !item.classList.contains("open");
			item.classList.toggle("open", open);
			q.setAttribute("aria-expanded", String(open));
		});
	});

	/* ---- country tabs ---- */
	var rtl = (root.getAttribute("dir") || "").toLowerCase() === "rtl";
	document.querySelectorAll("[data-tabs]").forEach(function (wrap) {
		var list = wrap.querySelector(".tabs");
		if (!list) return;
		var tabs = Array.prototype.slice.call(list.querySelectorAll("a.tab"));
		if (!tabs.length) return;
		// the HTML is plain in-page navigation; the tab semantics are added here, once the script runs
		list.setAttribute("role", "tablist");
		tabs.forEach(function (t) {
			var id = (t.getAttribute("href") || "").slice(1);
			var panel = document.getElementById(id);
			t.setAttribute("role", "tab");
			t.setAttribute("aria-controls", id);
			t.setAttribute("aria-selected", "false");
			if (panel) {
				panel.setAttribute("role", "tabpanel");
				panel.setAttribute("aria-labelledby", t.id);
				panel.tabIndex = 0;
			}
		});
		var ind = list.querySelector(".tab-ind");
		var current = null;
		function panelOf(tab) { return document.getElementById(tab.getAttribute("aria-controls")); }
		function moveInd() {
			if (!ind || !current) return;
			ind.style.left = current.offsetLeft + "px";
			ind.style.top = current.offsetTop + "px";
			ind.style.width = current.offsetWidth + "px";
			ind.style.height = current.offsetHeight + "px";
		}
		function select(tab, opts) {
			opts = opts || {};
			current = tab;
			tabs.forEach(function (t) {
				var on = t === tab;
				var panel = panelOf(t);
				t.setAttribute("aria-selected", String(on));
				t.tabIndex = on ? 0 : -1;
				if (!panel) return;
				if (on) {
					var wasHidden = panel.hidden;
					panel.hidden = false;
					if (wasHidden && opts.animate !== false && !reduced) {
						panel.classList.remove("enter");
						void panel.offsetWidth;
						panel.classList.add("enter");
					}
				} else {
					panel.hidden = true;
				}
			});
			moveInd();
			if (opts.focus) tab.focus();
			if (opts.hash && window.history && history.replaceState) {
				history.replaceState(null, "", "#" + tab.getAttribute("aria-controls"));
			}
		}
		function fromHash() {
			var id = "";
			try { id = decodeURIComponent((location.hash || "").slice(1)); } catch (e) { return null; }
			for (var k = 0; k < tabs.length; k++) {
				if (tabs[k].getAttribute("aria-controls") === id) return tabs[k];
			}
			return null;
		}
		tabs.forEach(function (t, i) {
			t.addEventListener("click", function (e) {
				e.preventDefault();
				select(t, { hash: true });
			});
			t.addEventListener("keydown", function (e) {
				var nextKey = rtl ? "ArrowLeft" : "ArrowRight";
				var prevKey = rtl ? "ArrowRight" : "ArrowLeft";
				var n = null;
				if (e.key === nextKey) n = tabs[(i + 1) % tabs.length];
				else if (e.key === prevKey) n = tabs[(i - 1 + tabs.length) % tabs.length];
				else if (e.key === "Home") n = tabs[0];
				else if (e.key === "End") n = tabs[tabs.length - 1];
				else if (e.key === " " || e.key === "Spacebar") n = t; // links do not react to Space on their own
				if (n) {
					e.preventDefault();
					select(n, { focus: true, hash: true });
				}
			});
		});
		var linked = fromHash();
		var initial = linked || tabs[0];
		select(initial, { animate: false });
		wrap.classList.add("tabs-ready");
		if (linked) {
			// the browser jumped to the (then still visible) panel; show the tabs instead
			requestAnimationFrame(function () { wrap.scrollIntoView({ block: "start" }); });
		}
		window.addEventListener("hashchange", function () {
			var t = fromHash();
			if (!t) return;
			select(t);
			wrap.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
		});
		window.addEventListener("resize", moveInd);
		if (document.fonts && document.fonts.ready) document.fonts.ready.then(moveInd);
	});

	/* ---- timeline progress ---- */
	var tl = document.querySelector(".tl-card");
	if (tl) {
		var tlLine = tl.querySelector(".tl-line i");
		var tlSteps = tl.querySelectorAll(".tl-step");
		var tlUpdate = function () {
			var r = tl.getBoundingClientRect();
			var vh = window.innerHeight || 1;
			var p = reduced ? 1 : Math.max(0, Math.min(1, (vh * 0.8 - r.top) / (vh * 0.45)));
			if (tlLine) tlLine.style.setProperty("--p", p.toFixed(3));
			var last = Math.max(1, tlSteps.length - 1);
			tlSteps.forEach(function (s, i) { s.classList.toggle("on", p > 0.02 && p >= i / last - 0.001); });
		};
		window.addEventListener("scroll", tlUpdate, { passive: true });
		window.addEventListener("resize", tlUpdate);
		tlUpdate();
	}

	root.classList.remove("no-motion");
})();
