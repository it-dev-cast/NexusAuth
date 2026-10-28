"""Page-level contracts for the sidebar brand, the removed top bars, and the
Settings page. These read the shipped front-end files, so a change that brings
a removed element back, or breaks Settings' wiring, fails here."""
import re
from pathlib import Path

from app.tests.conftest import client

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def _sidebar(html):
    start = html.index('<aside class="sidebar">')
    return html[start: html.index("</aside>", start)]


def test_sidebar_brand_has_no_foundation_core_line():
    sidebar = _sidebar(_read("index.html"))
    brand = sidebar[: sidebar.index("<nav")]
    assert "Foundation Core" not in brand
    assert "sidebar-brand-tag" not in brand
    assert "Casterly" in brand and "Nexus Auth" in brand
    # the footer is the signed-in profile only: no "Part of Nexus One Foundation" card
    footer = sidebar[sidebar.index('class="sidebar-footer"'):]
    assert "Nexus One Foundation" not in sidebar and "sidebar-product" not in sidebar
    assert 'id="who-name"' in footer and 'id="btn-logout"' in footer


def test_the_floating_top_bar_and_page_title_bars_are_gone():
    html = _read("index.html")
    app = html[html.index('<section id="app"'):]  # the signed-in app (the sign-in page has its own bar)
    assert "<header" not in app.replace('<header class="page-header">', "")  # no app-wide top bar, only page headers
    assert 'class="topbar' not in html and "topbar-" not in html
    assert 'class="page-head"' not in html
    assert "topbar.js" not in html
    assert not (FRONTEND / "topbar.js").exists()
    # ...but each page has exactly ONE proper heading: breadcrumb + PageHeader (icon, title, description)
    for title in ("Users", "Companies", "Employees", "Suppliers", "Assets", "Audit log", "Events", "Sessions", "Reports", "Help Center", "Master Management", "Settings"):
        section = re.search(r'<section id="section-[a-z-]+" class="page-section hidden">\s*<header class="page-header">.*?<h2 class="text-headline">%s</h2>' % re.escape(title), html, re.S)
        assert section, title
    assert html.count('class="page-header"') == 12 and 'class="page-bar"' not in html
    app_html = html[html.index('<section id="app"'):]
    for page in re.findall(r'<section id="(section-[a-z-]+)"', app_html):
        block = app_html[app_html.index(f'<section id="{page}"'):]
        block = block[: block.index("</section>")]
        assert block.count('class="page-header"') == (0 if page == "section-overview" else 1), page
        assert block.count('class="breadcrumb"') == 1, page
    # the old theme dropdown (it lived in those bars) is gone from page and script
    assert "theme-swatch" not in html and "theme-picker-mount" not in html
    js = _read("app.js")
    assert "theme-swatch" not in js and "relocateThemePicker" not in js and "NexusTopbar" not in js
    css = _read("styles.css")
    assert not re.search(r"^\.topbar[\s{.,-]", css, re.M)


def test_design_system_is_applied_across_the_screen():
    html, css = _read("index.html"), _read("styles.css")
    assert '<a class="skip-link" href="#main-content">' in html and 'id="main-content"' in html
    assert '<script src="/static/design.js"></script>' in html and (FRONTEND / "design.js").exists()
    assert "Poppins" in html
    block = css[css.index("Casterly design system"):]
    for token in ("--radius-xl: 1rem", "--shadow-card", "--font-mono", "--sidebar-bg", ".page-header", ".breadcrumb", ".text-mono-id", ":focus-visible", "prefers-reduced-motion"):
        assert token in block, token
    for theme in ("ocean-blue", "graphite-dark", "casterly-erp-green", "emerald"):
        assert f'data-theme="{theme}"' in block, theme
    assert "page-bar" not in css and "sidebar-product" not in css


def test_settings_is_a_sidebar_page_for_every_role():
    html = _read("index.html")
    sidebar = _sidebar(html)
    button = re.search(r'<button class="nav-item([^"]*)" data-section="section-settings"', sidebar)
    assert button and "admin-only" not in button.group(1)
    support = sidebar[sidebar.index('id="nav-h-support"'):]
    assert support.index('data-section="section-settings"') < support.index('data-section="section-help"')
    assert '<section id="section-settings"' in html and 'id="settings-root"' in html
    assert '<script src="/static/settings.js"></script>' in html
    js = _read("app.js")
    routes = js[js.index("const HASH_TO_SECTION"): js.index("const SECTION_TO_HASH")]
    assert 'settings: "section-settings"' in routes


def test_settings_uses_only_existing_endpoints_and_they_exist():
    settings = _read("settings.js")
    paths = client.get("/openapi.json").json()["paths"]
    for endpoint in ("/api/v1/auth/change-password", "/api/v1/auth/logout-all"):
        assert endpoint in settings, endpoint
        assert endpoint in paths and "post" in paths[endpoint], endpoint
    # profile data comes from the existing session + companies API, nothing invented
    assert "/api/v1/companies/" in settings and "/api/v1/auth" in settings
    # password handling: sends both fields, never stores or logs the password
    assert "current_password" in settings and "new_password" in settings
    assert "localStorage.setItem(\"password" not in settings and "console." not in settings
    # the sections the page promises
    for heading in ("Profile", "Appearance", "Password", "Sessions"):
        assert f">{heading}</h3>" in settings, heading


def test_sidebar_preferences_reuse_the_apps_own_storage_keys():
    settings, js = _read("settings.js"), _read("app.js")
    for name in ("SIDEBAR_COLLAPSE_KEY", "applySidebarCollapsed", "setNavGroupCollapsed"):
        assert name in settings, name
        assert re.search(rf"(const|function) {name}\b", js), name  # defined once, in app.js


def test_theme_is_picked_from_the_top_right_menu_not_settings():
    html, settings, js = _read("index.html"), _read("settings.js"), _read("app.js")
    # one picker, in the content area itself (before any page section), so it
    # shows on every page
    main = html[html.index('<main class="content"'):]
    assert main.index('id="theme-menu-wrap"') < main.index("<section")
    assert html.count('id="btn-theme-menu"') == 1 and 'id="theme-menu"' in html
    # Settings no longer has a theme section
    assert "data-st-theme" not in settings and "THEME_STORAGE_KEY" not in settings
    assert "NexusSettings" not in js
    # the menu is built from the one THEMES list and stores the same key
    for name in ("THEME_STORAGE_KEY", "THEMES", "applyTheme", "systemDefaultTheme", "renderThemeMenu"):
        assert re.search(rf"(const|function) {name}\b", js), name
    assert 'item("device"' in js


def test_brand_card_and_status_pills_keep_the_reference_look():
    css = _read("styles.css")
    assert ".sidebar-collapse-btn" in css and "border-radius: 50%" in css
    assert "Status is shown in words, not colour" in css


def test_no_foundation_core_text_is_left_in_the_app():
    html = _read("index.html")
    assert "Foundation Core" not in html
    for name in ("help-content.js", "settings.js", "masters.js", "reports.js", "help.js"):
        assert "Foundation Core" not in _read(name), name


def test_indicators_are_neutral_not_red_or_green():
    css = _read("styles.css")
    block = css[css.index("Neutral indicators"):]
    # statuses, health pill, KPI accents, toasts, error boxes and danger buttons are all neutral
    for selector in (".status-pill.good", ".toast.ok, .toast.bad", ".kpi-card.kpi-e", ".overview-status-pill", "button.danger", ".rp-error, .st-error", ".required-mark"):
        assert selector in css, selector
    for token in ("--kpi-accent: var(--muted)", "animation: none", "color: var(--ink)"):
        assert token in block, token
    for forbidden in ("var(--danger)", "var(--color-success)", "var(--color-danger", "#16a34a", "#dc2626"):
        assert forbidden not in block, forbidden
    # the markup never asks for a coloured status any more: pills carry no green/red variant in new code
    assert 'class="kpi-dot"' in _read("index.html")  # the dot stays, only its colour is neutral
