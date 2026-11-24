/* KenzCloudX demo / quote form. Vanilla, no dependencies.
   The server (kenzcloudx.api.demo.submit_demo_request) validates everything again; these checks
   only give faster, inline feedback. Localised strings come from data-* attributes on the form. */
(function () {
	"use strict";
	var form = document.getElementById("demo-form");
	if (!form || !window.fetch || !window.URLSearchParams || !window.FormData) return;

	// the browser's own validation stays on without JS; with JS we show inline, localised errors
	form.noValidate = true;
	var msg = form.dataset;
	var statusEl = document.getElementById("demo-status");
	var thanks = document.getElementById("demo-thanks");
	var button = form.querySelector('button[type="submit"]');
	var buttonLabel = button.textContent;
	var busy = false;

	function ascii(value) {
		return value.replace(/[٠-٩]/g, function (c) { return String(c.charCodeAt(0) - 0x0660); })
			.replace(/[۰-۹]/g, function (c) { return String(c.charCodeAt(0) - 0x06F0); });
	}
	function value(name) { return (form.elements[name].value || "").trim(); }

	// mirror of kenzcloudx.api.demo.normalize_phone (the server decides; this only gives early feedback)
	var COUNTRIES = ["sa", "ae", "om", "in", "gulf", "other"];
	var MOBILE = {
		sa: ["966", "5[0-9]{8}"],
		ae: ["971", "5[0-9]{8}"],
		om: ["968", "[79][0-9]{7}"],
		"in": ["91", "[6-9][0-9]{9}"]
	};
	function phoneOk(v, country) {
		v = ascii(v).replace(/[\s.\-\u2010-\u2015()\[\]{}\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "");
		if (!/^\+?[0-9]+$/.test(v)) return false;
		if (v.indexOf("00") === 0) v = "+" + v.slice(2);
		var key, rule;
		if (v.charAt(0) === "+") {
			var digits = v.slice(1);
			for (key in MOBILE) {
				rule = MOBILE[key];
				if (digits.indexOf(rule[0]) === 0) return new RegExp("^" + rule[0] + "0?" + rule[1] + "$").test(digits);
			}
			return /^[1-9][0-9]{7,14}$/.test(digits);
		}
		rule = MOBILE[country];
		return !!rule && new RegExp("^(?:" + rule[0] + ")?0?" + rule[1] + "$").test(v);
	}

	var checks = {
		full_name: function (v) { return v ? "" : msg.msgRequired; },
		company: function (v) { return v ? "" : msg.msgRequired; },
		country: function (v) { return COUNTRIES.indexOf(v) >= 0 ? "" : msg.msgRequired; },
		phone: function (v) {
			if (!v) return msg.msgRequired;
			return phoneOk(v, value("country")) ? "" : msg.msgPhone;
		},
		email: function (v) {
			if (!v) return msg.msgRequired;
			// same allowlist as the server (kenzcloudx.api.demo._EMAIL)
			var ok = v.length <= 140 && /^[\x00-\x7f]*$/.test(v) &&
				/^[a-z0-9](?:[a-z0-9._%+-]*[a-z0-9_+-])?@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(v.toLowerCase());
			return ok ? "" : msg.msgEmail;
		},
		users: function (v) {
			v = ascii(v);
			return !v || (/^\d+$/.test(v) && parseInt(v, 10) >= 1) ? "" : msg.msgUsers;
		}
	};

	function setFieldError(name, text) {
		var input = form.elements[name];
		var slot = document.getElementById("df-" + name + "-error");
		if (slot) slot.textContent = text;
		if (text) input.setAttribute("aria-invalid", "true");
		else input.removeAttribute("aria-invalid");
	}

	function validate() {
		var first = null;
		Object.keys(checks).forEach(function (name) {
			var text = checks[name](value(name));
			setFieldError(name, text);
			if (text && !first) first = form.elements[name];
		});
		return first;
	}

	// re-check a field once the visitor leaves it, but only if it was already flagged
	Object.keys(checks).forEach(function (name) {
		form.elements[name].addEventListener("blur", function () {
			if (this.getAttribute("aria-invalid") === "true") setFieldError(name, checks[name](value(name)));
		});
	});

	// the phone rules depend on the country: re-check a flagged phone number when the country changes
	form.elements.country.addEventListener("change", function () {
		if (this.getAttribute("aria-invalid") === "true") setFieldError("country", checks.country(value("country")));
		if (form.elements.phone.getAttribute("aria-invalid") === "true") setFieldError("phone", checks.phone(value("phone")));
	});

	function setStatus(text, isError) {
		statusEl.textContent = text || "";
		statusEl.classList.toggle("is-error", !!isError);
	}

	function setBusy(on) {
		busy = on;
		button.disabled = on;
		button.textContent = on ? msg.msgSending : buttonLabel;
		form.setAttribute("aria-busy", on ? "true" : "false");
	}

	function serverMessage(body) {
		try {
			var list = JSON.parse(body._server_messages);
			var first = JSON.parse(list[0]);
			return first.message || "";
		} catch (e) {
			return "";
		}
	}

	function showThanks() {
		form.hidden = true;
		thanks.hidden = false;
		thanks.focus();
		thanks.scrollIntoView({ block: "center" });
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		if (busy) return;
		setStatus("");
		var invalid = validate();
		if (invalid) {
			invalid.focus();
			return;
		}
		var headers = { "Accept": "application/json" };
		if (msg.csrf) headers["X-Frappe-CSRF-Token"] = msg.csrf;
		setBusy(true);
		fetch(form.action, {
			method: "POST",
			headers: headers,
			body: new URLSearchParams(new FormData(form)),
			credentials: "same-origin"
		}).then(function (response) {
			if (response.status === 429) return { error: msg.msgRateLimited };
			return response.json().then(function (body) {
				if (response.ok && body.message && body.message.ok) return { ok: true };
				return { error: (response.status === 417 && serverMessage(body)) || msg.msgGeneric };
			}, function () {
				return { error: msg.msgGeneric };
			});
		}).catch(function () {
			return { error: msg.msgGeneric };
		}).then(function (result) {
			setBusy(false);
			if (result.ok) showThanks();
			else setStatus(result.error, true);
		});
	});
})();
