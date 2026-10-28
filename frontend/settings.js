/* Settings page — the signed-in user's own account and preferences.
 *
 *   Profile     who you are signed in as (from /auth/me; company name from the
 *               companies API). Read-only: the app has no profile-editing API.
 *   Appearance  the sidebar preferences — keep it collapsed, fold/unfold
 *               groups. The theme is picked from the palette button at the
 *               top right of every page (renderThemeMenu() in app.js).
 *   Password    POST /api/v1/auth/change-password. The server signs out every
 *               session afterwards, so this page then returns you to sign-in.
 *   Sessions    POST /api/v1/auth/logout-all (same call as the Overview
 *               button), and a link to the Sessions page.
 *
 * Open to every role: it only ever touches the user's own account, and every
 * action goes through an existing, already-protected endpoint.
 *
 * Loaded BEFORE app.js; it uses app.js's globals (api, state, ...) only
 * inside functions that run once the page is opened.
 */
(function () {
  "use strict";

  const esc = (value) => escapeHtml(value == null ? "" : String(value));
  const root = () => document.getElementById("settings-root");
  const st = { userId: null, companyName: null, rendered: false, wired: false };

  /* ------------------------------------------------------------------ */
  /* Rendering                                                           */
  /* ------------------------------------------------------------------ */
  function sidebarCollapsed() {
    const sidebar = document.querySelector(".sidebar");
    return !!(sidebar && sidebar.classList.contains("collapsed"));
  }

  function profileRows(user) {
    const rows = [
      ["Name", user.full_name || "—"],
      ["Email", user.email],
      ["Role", humanize(user.role)],
      ["Company", st.companyName || (user.company_id ? `#${user.company_id}` : "—")],
      ["Account", user.is_active ? "Active" : "Inactive"],
      ["Sign-ins", String(user.login_count ?? 0)],
    ];
    return rows.map(([label, value]) => `<div class="st-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("");
  }

  function render() {
    const user = state.user;
    root().innerHTML = `
      <div class="st-grid">
        <section class="card st-card" aria-labelledby="st-h-profile">
          <h3 id="st-h-profile">Profile</h3>
          <p class="st-note">The account you are signed in as. Your role is set by an administrator.</p>
          <dl class="st-facts" id="st-profile">${profileRows(user)}</dl>
        </section>

        <section class="card st-card" aria-labelledby="st-h-appearance">
          <h3 id="st-h-appearance">Appearance</h3>
          <p class="st-note">Sidebar preferences, remembered in this browser. To change the theme, use the palette button at the top right of any page.</p>
          <label class="checkbox st-check-row">
            <input type="checkbox" id="st-collapsed" ${sidebarCollapsed() ? "checked" : ""} />
            Keep the sidebar collapsed (icons only)
          </label>
          <div class="st-actions">
            <button type="button" class="outline" data-st-action="unfold-groups">Open all sidebar groups</button>
          </div>
        </section>

        <section class="card st-card" aria-labelledby="st-h-password">
          <h3 id="st-h-password">Password</h3>
          <p class="st-note">Changing your password signs you out everywhere, including here, so you will sign in again with the new one.</p>
          <form id="st-password-form" class="st-form" novalidate>
            <label>Current password
              <input id="st-current" type="password" autocomplete="current-password" required />
            </label>
            <label>New password
              <input id="st-new" type="password" autocomplete="new-password" required />
            </label>
            <label>Confirm new password
              <input id="st-confirm" type="password" autocomplete="new-password" required />
            </label>
            <p id="st-password-error" class="st-error hidden" role="alert"></p>
            <div class="actions">
              <button type="submit" class="primary" id="st-password-submit">Change password</button>
            </div>
          </form>
        </section>

        <section class="card st-card" aria-labelledby="st-h-sessions">
          <h3 id="st-h-sessions">Sessions</h3>
          <p class="st-note">Every sign-in is a session. Sign out of all of them — on every browser and device — if you think someone else may have access.</p>
          <div class="st-actions">
            <button type="button" class="danger" id="st-logout-all" data-st-action="logout-all">Log out of all sessions</button>
            <a class="st-link" href="#sessions">View my sessions</a>
          </div>
        </section>
      </div>`;
    st.rendered = true;
  }

  /* ------------------------------------------------------------------ */
  /* Actions                                                             */
  /* ------------------------------------------------------------------ */
  function showPasswordError(message) {
    const el = document.getElementById("st-password-error");
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("hidden", !message);
  }

  async function changePassword() {
    const current = document.getElementById("st-current").value;
    const next = document.getElementById("st-new").value;
    const confirm = document.getElementById("st-confirm").value;
    showPasswordError("");
    if (!current || !next || !confirm) return showPasswordError("Fill in all three fields.");
    if (next !== confirm) return showPasswordError("The new password and its confirmation don't match.");
    if (next === current) return showPasswordError("Choose a new password that is different from the current one.");
    const policyError = passwordPolicyError(next);
    if (policyError) return showPasswordError(policyError.replace("The password", "The new password"));
    if (!(await confirmModal("Change your password? You will be signed out everywhere."))) return;
    const button = document.getElementById("st-password-submit");
    await withLoading(button, "Changing…", async () => {
      const result = await api("/api/v1/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
        auth: true,
      });
      if (result.status === 200) {
        toast("Password changed. Please sign in again.", "ok");
        clearSession();
      } else {
        // api() already showed the server's message (e.g. wrong current password)
        showPasswordError(result.data && result.data.message ? result.data.message : "The password could not be changed.");
      }
    });
  }

  async function logoutAll() {
    if (!(await confirmModal("Log out of all sessions?"))) return;
    await withLoading(document.getElementById("st-logout-all"), "Revoking…", async () => {
      const result = await api("/api/v1/auth/logout-all", { method: "POST", auth: true });
      if (result.status === 200) {
        toast("All sessions revoked.", "ok");
        clearSession();
      }
    });
  }

  function setCollapsed(collapsed) {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch (error) {
      /* applies for this visit only */
    }
    applySidebarCollapsed(collapsed);
  }

  function unfoldGroups() {
    document.querySelectorAll(".nav-group.is-collapsed").forEach((group) => setNavGroupCollapsed(group, false));
    toast("All sidebar groups are open.", "ok");
  }

  function wire() {
    if (st.wired) return;
    st.wired = true;
    const el = root();
    el.addEventListener("click", (event) => {
      const button = event.target.closest("[data-st-action]");
      if (!button) return;
      const action = button.getAttribute("data-st-action");
      if (action === "unfold-groups") unfoldGroups();
      else if (action === "logout-all") logoutAll();
    });
    el.addEventListener("change", (event) => {
      if (event.target.id === "st-collapsed") setCollapsed(event.target.checked);
    });
    el.addEventListener("submit", (event) => {
      if (event.target.id !== "st-password-form") return;
      event.preventDefault();
      changePassword();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Entry                                                               */
  /* ------------------------------------------------------------------ */
  function whenSignedIn() {
    return new Promise((resolve) => {
      let tries = 0;
      const tick = () => {
        if (state.user) return resolve(true);
        if (!state.accessToken || ++tries > 200) return resolve(false);
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  async function show() {
    if (typeof state === "undefined") return;
    if (!state.user && !(await whenSignedIn())) return;
    wire();
    if (st.userId !== state.user.id) {
      st.userId = state.user.id;
      st.companyName = null;
      st.rendered = false;
    }
    // Re-render on every visit (cheap, and the profile/sidebar state may
    // have changed elsewhere) but don't wipe a half-typed password form.
    const form = document.getElementById("st-password-form");
    const typing = form && ["st-current", "st-new", "st-confirm"].some((id) => document.getElementById(id).value);
    if (!typing) render();
    if (st.companyName === null && state.user.company_id) {
      const result = await api(`/api/v1/companies/${state.user.company_id}`, { auth: true });
      if (result.status === 200 && result.data.data && result.data.data.name) {
        st.companyName = result.data.data.name;
        const rows = document.getElementById("st-profile");
        if (rows) rows.innerHTML = profileRows(state.user);
      }
    }
  }

  window.NexusSections = window.NexusSections || {};
  window.NexusSections["section-settings"] = () => show();
})();
