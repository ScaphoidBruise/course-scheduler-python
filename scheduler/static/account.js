var statusEl = document.getElementById("accountStatus");
var guestPanel = document.getElementById("guestPanel");
var signedInPanel = document.getElementById("signedInPanel");
var signedInUsername = document.getElementById("signedInUsername");
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

var changePasswordForm = document.getElementById("changePasswordForm");
var changeUsernameForm = document.getElementById("changeUsernameForm");
var deleteAccountForm = document.getElementById("deleteAccountForm");
var deleteRevealBtn = document.getElementById("deleteRevealBtn");
var deleteCancelBtn = document.getElementById("deleteCancelBtn");
var exportDataBtn = document.getElementById("exportDataBtn");

var changePasswordStatus = document.getElementById("changePasswordStatus");
var changeUsernameStatus = document.getElementById("changeUsernameStatus");
var deleteAccountStatus = document.getElementById("deleteAccountStatus");

var accountUsername = document.getElementById("accountUsername");
var accountCreated = document.getElementById("accountCreated");
var accountHasTranscript = document.getElementById("accountHasTranscript");
var accountSchedulesCount = document.getElementById("accountSchedulesCount");

function showStatus(message, type) {
    statusEl.className = "alert mb-3 alert-" + type;
    statusEl.textContent = message;
}

function hideGuestStatus() {
    statusEl.className = "alert d-none mb-3";
    statusEl.textContent = "";
}

function showInlineStatus(el, message, type) {
    if (!el) return;
    if (!message) {
        el.className = "alert d-none small py-2";
        el.textContent = "";
        return;
    }
    el.className = "alert small py-2 alert-" + type;
    el.textContent = message;
}

function showGuestChrome() {
    guestPanel.classList.remove("d-none");
    signedInPanel.classList.add("d-none");
}

function showSignedInChrome(user) {
    guestPanel.classList.add("d-none");
    signedInPanel.classList.remove("d-none");
    if (signedInUsername) signedInUsername.textContent = user && user.username ? user.username : "";
    if (accountUsername) accountUsername.textContent = user && user.username ? user.username : "";
    hideGuestStatus();
}

function postJson(url, payload) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    }).then(function (r) {
        return r.json().then(function (body) {
            return { ok: r.ok, status: r.status, body: body };
        });
    });
}

function setPasswordVisibility(inputEl, visible) {
    inputEl.type = visible ? "text" : "password";
}

function togglePassword(inputEl) {
    setPasswordVisibility(inputEl, inputEl.type === "password");
}

function bindPasswordToggle(btnId, inputEl) {
    var btn = document.getElementById(btnId);
    if (!btn || !inputEl) return;
    btn.addEventListener("click", function () { togglePassword(inputEl); });
}

function showLoginMode() {
    authTitle.textContent = "Login";
    authSubtitle.textContent = "Sign in to access your personal schedule and profile.";
    loginForm.classList.remove("d-none");
    registerForm.classList.add("d-none");
}

function showRegisterMode() {
    authTitle.textContent = "Create Account";
    authSubtitle.textContent = "New users can create an account to save schedules securely.";
    registerForm.classList.remove("d-none");
    loginForm.classList.add("d-none");
}

if (toggleLoginPasswordBtn) {
    toggleLoginPasswordBtn.addEventListener("click", function () {
        togglePassword(loginPasswordInput);
    });
}
if (toggleRegisterPasswordBtn) {
    toggleRegisterPasswordBtn.addEventListener("click", function () {
        togglePassword(registerPasswordInput);
    });
}
if (toggleRegisterPasswordConfirmBtn) {
    toggleRegisterPasswordConfirmBtn.addEventListener("click", function () {
        togglePassword(registerPasswordConfirmInput);
    });
}

bindPasswordToggle("toggleCpCurrent", document.getElementById("cpCurrentPassword"));
bindPasswordToggle("toggleCpNew", document.getElementById("cpNewPassword"));
bindPasswordToggle("toggleCpConfirm", document.getElementById("cpConfirmPassword"));
bindPasswordToggle("toggleCuCurrent", document.getElementById("cuCurrentPassword"));
bindPasswordToggle("toggleDaCurrent", document.getElementById("daCurrentPassword"));

if (showRegisterLink) {
    showRegisterLink.addEventListener("click", function (e) {
        e.preventDefault();
        showRegisterMode();
    });
}
if (showLoginLink) {
    showLoginLink.addEventListener("click", function (e) {
        e.preventDefault();
        showLoginMode();
    });
}

function formatCreatedAt(value) {
    if (!value) return "—";
    var s = String(value).trim();
    var norm = s.indexOf("T") === -1 ? s.replace(" ", "T") : s;
    var d = new Date(norm);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function loadAccountSummary() {
    return fetch("/api/account/summary")
        .then(function (r) {
            if (!r.ok) throw new Error("summary");
            return r.json();
        })
        .then(function (data) {
            if (accountUsername) accountUsername.textContent = data.username || "";
            if (signedInUsername) signedInUsername.textContent = data.username || "";
            if (accountCreated) accountCreated.textContent = formatCreatedAt(data.created_at);
            if (accountHasTranscript) accountHasTranscript.textContent = data.transcript_on_file ? "Yes" : "No";
            if (accountSchedulesCount) {
                accountSchedulesCount.textContent =
                    String(data.saved_schedules_count || 0) +
                    " (" + String(data.total_sections_in_schedules || 0) + " sections)";
            }
        })
        .catch(function () {
            if (accountCreated) accountCreated.textContent = "—";
        });
}

function refreshSessionBanner() {
    fetch("/api/me")
        .then(function (r) {
            return r.json();
        })
        .then(function (data) {
            if (data.authenticated && data.user) {
                showSignedInChrome(data.user);
                loadAccountSummary();
            } else {
                showGuestChrome();
                showLoginMode();
                hideGuestStatus();
            }
        })
        .catch(function () {
            showGuestChrome();
            showLoginMode();
            showStatus("Could not check session status. You can still try to sign in.", "danger");
        });
}

if (loginForm) {
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
                showStatus("Login successful. Redirecting to schedule…", "success");
                setTimeout(function () {
                    window.location.href = "/";
                }, 600);
            })
            .catch(function () {
                showStatus("Login failed. Please try again.", "danger");
            });
    });
}

if (registerForm) {
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
                showStatus("Registration successful. Redirecting to schedule…", "success");
                setTimeout(function () {
                    window.location.href = "/";
                }, 600);
            })
            .catch(function () {
                showStatus("Registration failed. Please try again.", "danger");
            });
    });
}

if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
        postJson("/api/logout", {})
            .then(function () {
                window.location.href = "/account";
            })
            .catch(function () {
                showStatus("Could not log out right now. Try again.", "danger");
            });
    });
}

if (changePasswordForm) {
    changePasswordForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var current = document.getElementById("cpCurrentPassword").value;
        var nw = document.getElementById("cpNewPassword").value;
        var confirm = document.getElementById("cpConfirmPassword").value;
        if (nw.length < 8) {
            showInlineStatus(changePasswordStatus, "New password must be at least 8 characters.", "danger");
            return;
        }
        if (nw !== confirm) {
            showInlineStatus(changePasswordStatus, "New passwords do not match.", "danger");
            return;
        }
        showInlineStatus(changePasswordStatus, "Saving…", "info");
        postJson("/api/account/change-password", {
            current_password: current,
            new_password: nw,
            confirm_password: confirm,
        })
            .then(function (result) {
                if (!result.ok) {
                    showInlineStatus(changePasswordStatus, (result.body && result.body.error) || "Could not change password.", "danger");
                    return;
                }
                showInlineStatus(changePasswordStatus, "Password updated.", "success");
                changePasswordForm.reset();
            })
            .catch(function () {
                showInlineStatus(changePasswordStatus, "Could not change password.", "danger");
            });
    });
}

if (changeUsernameForm) {
    changeUsernameForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var newUsername = document.getElementById("cuNewUsername").value.trim().toLowerCase();
        var current = document.getElementById("cuCurrentPassword").value;
        if (newUsername.length < 3) {
            showInlineStatus(changeUsernameStatus, "Username must be at least 3 characters.", "danger");
            return;
        }
        showInlineStatus(changeUsernameStatus, "Saving…", "info");
        postJson("/api/account/change-username", {
            new_username: newUsername,
            current_password: current,
        })
            .then(function (result) {
                if (!result.ok) {
                    showInlineStatus(changeUsernameStatus, (result.body && result.body.error) || "Could not change username.", "danger");
                    return;
                }
                showInlineStatus(changeUsernameStatus, "Username updated.", "success");
                if (result.body && result.body.user && result.body.user.username) {
                    if (signedInUsername) signedInUsername.textContent = result.body.user.username;
                    if (accountUsername) accountUsername.textContent = result.body.user.username;
                }
                changeUsernameForm.reset();
            })
            .catch(function () {
                showInlineStatus(changeUsernameStatus, "Could not change username.", "danger");
            });
    });
}

if (deleteRevealBtn && deleteAccountForm) {
    deleteRevealBtn.addEventListener("click", function () {
        deleteAccountForm.classList.remove("d-none");
        deleteRevealBtn.classList.add("d-none");
    });
}
if (deleteCancelBtn && deleteAccountForm) {
    deleteCancelBtn.addEventListener("click", function () {
        deleteAccountForm.classList.add("d-none");
        if (deleteRevealBtn) deleteRevealBtn.classList.remove("d-none");
        showInlineStatus(deleteAccountStatus, "", "info");
        deleteAccountForm.reset();
    });
}

if (deleteAccountForm) {
    deleteAccountForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var confirmText = document.getElementById("daConfirmText").value;
        var current = document.getElementById("daCurrentPassword").value;
        if (confirmText !== "DELETE") {
            showInlineStatus(deleteAccountStatus, 'Type "DELETE" exactly to confirm.', "danger");
            return;
        }
        showInlineStatus(deleteAccountStatus, "Deleting…", "info");
        postJson("/api/account/delete", {
            confirm: confirmText,
            current_password: current,
        })
            .then(function (result) {
                if (!result.ok) {
                    showInlineStatus(deleteAccountStatus, (result.body && result.body.error) || "Could not delete account.", "danger");
                    return;
                }
                window.location.href = "/account";
            })
            .catch(function () {
                showInlineStatus(deleteAccountStatus, "Could not delete account.", "danger");
            });
    });
}

if (exportDataBtn) {
    exportDataBtn.addEventListener("click", function () {
        window.location.href = "/api/account/export";
    });
}

refreshSessionBanner();
