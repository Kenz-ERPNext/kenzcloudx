/* KenzCloudX demo / quote form. Vanilla, no dependencies.
   The server (kenzcloudx.api.demo.submit_demo_request) validates everything again; these checks
   only give faster, inline feedback. Localised strings come from data-* attributes on the form. */
(function () {
	"use strict";
	var form = document.getElementById("demo-form");
	if (!form || !window.fetch || !window.URLSearchParams || !window.FormData) return;

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

	var checks = {
		full_name: function (v) { return v ? "" : msg.msgRequired; },
		company: function (v) { return v ? "" : msg.msgRequired; },
		phone: function (v) {
			if (!v) return msg.msgRequired;
			v = ascii(v).replace(/[\s\-‐-―()\[\]{}‎‏‪-‮⁦-⁩]/g, "");
			return /^(?:\+966|00966|966|0)?5\d{8}$/.test(v) ? "" : msg.msgPhone;
		},
		email: function (v) {
			if (!v) return msg.msgRequired;
			return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? "" : msg.msgEmail;
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
