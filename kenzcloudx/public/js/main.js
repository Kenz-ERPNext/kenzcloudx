/* KenzCloudX page behaviour. Vanilla, no dependencies, safe to load on every page (each part checks
   that its markup exists).
   - nav pill: .scrolled after 40px; mobile menu (.menu-btn) with Escape / link click / outside click to close
   - reveals: .reveal gets .in when it enters the viewport; stagger with style="--d:N" (90ms steps)
   - count-up: [data-count="87"] inside a .reveal counts from 0 when revealed (Western digits, as before)
   - accordion: button.faq-q[aria-controls] inside .faq-item toggles .open + aria-expanded
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

	root.classList.remove("no-motion");
})();
