var statusEl = document.getElementById("accountStatus");
var loginForm = document.getElementById("loginForm");
var registerForm = document.getElementById("registerForm");
var logoutBtn = document.getElementById("logoutBtn");
var authTitle = document.getElementById("authTitle");
var authSubtitle = document.getElementById("authSubtitle");
var loginPasswordInput = document.getElementById("loginPassword");
var registerPasswordInput = document.getElementById("registerPassword");
var registerPasswordConfirmInput = document.getElementById("registerPasswordConfirm");
var toggleLoginPasswordBtn = document.getElementById("toggleLoginPassword");
var toggleRegisterPasswordBtn = document.getElementById("toggleRegisterPassword");
var toggleRegisterPasswordConfirmBtn = document.getElementById("toggleRegisterPasswordConfirm");
var showRegisterLink = document.getElementById("showRegisterLink");
var showLoginLink = document.getElementById("showLoginLink");

function showStatus(message, type) {
    statusEl.className = "alert mb-0 alert-" + type;
    statusEl.textContent = message;
}

function postJson(url, payload) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    }).then(function (r) {
        return r.json().then(function (body) {
            return { ok: r.ok, body: body };
        });
    });
}

function setPasswordVisibility(inputEl, visible) {
    inputEl.type = visible ? "text" : "password";
}

function togglePassword(inputEl) {
    setPasswordVisibility(inputEl, inputEl.type === "password");
}

function showLoginMode() {
    authTitle.textContent = "Login";
    authSubtitle.textContent = "Sign in to access your personal schedule profile.";
    loginForm.classList.remove("d-none");
    registerForm.classList.add("d-none");
}

function showRegisterMode() {
    authTitle.textContent = "Create Account";
    authSubtitle.textContent = "New users can create an account to save schedules securely.";
    registerForm.classList.remove("d-none");
    loginForm.classList.add("d-none");
}

toggleLoginPasswordBtn.addEventListener("click", function () {
    togglePassword(loginPasswordInput);
});

toggleRegisterPasswordBtn.addEventListener("click", function () {
    togglePassword(registerPasswordInput);
});

toggleRegisterPasswordConfirmBtn.addEventListener("click", function () {
    togglePassword(registerPasswordConfirmInput);
});

showRegisterLink.addEventListener("click", function (e) {
    e.preventDefault();
    showRegisterMode();
});

showLoginLink.addEventListener("click", function (e) {
    e.preventDefault();
    showLoginMode();
});

function refreshSessionBanner() {
    fetch("/api/me")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.authenticated && data.user) {
                logoutBtn.classList.remove("d-none");
                showStatus(
                    "Logged in as " + data.user.username + ". You can open your scheduler now.",
                    "success"
                );
            } else {
                logoutBtn.classList.add("d-none");
                showStatus("You are not logged in.", "secondary");
            }
        })
        .catch(function () {
            showStatus("Could not check session status.", "danger");
        });
}

loginForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var username = document.getElementById("loginUsername").value.trim();
    var password = document.getElementById("loginPassword").value;

    postJson("/api/login", { username: username, password: password })
        .then(function (result) {
            if (!result.ok) {
                showStatus(result.body.error || "Login failed.", "danger");
                return;
            }
            showStatus("Login successful. Redirecting to schedule...", "success");
            setTimeout(function () {
                window.location.href = "/";
            }, 600);
        })
        .catch(function () {
            showStatus("Login failed. Please try again.", "danger");
        });
});

registerForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var username = document.getElementById("registerUsername").value.trim();
    var password = document.getElementById("registerPassword").value;
    var passwordConfirm = document.getElementById("registerPasswordConfirm").value;

    if (password !== passwordConfirm) {
        showStatus("Passwords must match before registration.", "danger");
        return;
    }

    postJson("/api/register", {
        username: username,
        password: password,
        confirm_password: passwordConfirm
    })
        .then(function (result) {
            if (!result.ok) {
                showStatus(result.body.error || "Registration failed.", "danger");
                return;
            }
            showStatus("Registration successful. Redirecting to schedule...", "success");
            setTimeout(function () {
                window.location.href = "/";
            }, 600);
        })
        .catch(function () {
            showStatus("Registration failed. Please try again.", "danger");
        });
});

logoutBtn.addEventListener("click", function () {
    postJson("/api/logout", {})
        .then(function () {
            showStatus("You have been logged out.", "info");
            setTimeout(function () {
                window.location.href = "/account";
            }, 500);
        })
        .catch(function () {
            showStatus("Could not log out right now. Try again.", "danger");
        });
});

refreshSessionBanner();
showLoginMode();
