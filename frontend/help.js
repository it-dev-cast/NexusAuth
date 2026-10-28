/* Help Center page.
 *
 * Renders the static, structured content in help-content.js (window.NEXUS_HELP)
 * — there is no help database and no backend call. Search, the topic pages,
 * the article view and the FAQ accordion all run in the browser over that
 * data.
 *
 * URL = state, same idea as the Reports page:
 *   #help                  landing (search, topics, popular guides, FAQs)
 *   #help?q=<text>         landing with search results
 *   #help/topic/<id>       every article in one category
 *   #help/<articleId>      one article
 * Typing in the search box updates the address with replaceState (no history
 * entry per keystroke); opening an article or topic is a real navigation, so
 * Back returns to the results you came from. Refresh and shared links work
 * because the view is rebuilt from the hash alone.
 *
 * Loaded BEFORE app.js (see index.html), so it touches app.js's bindings
 * (`state`, `escapeHtml`, `SECTION_TO_HASH`) only inside functions that run
 * once the section is opened.
 */
(function () {
  "use strict";

  const SEARCH_DEBOUNCE_MS = 120;
  const MAX_TERMS = 8;

  const hc = {
    data: null,
    index: null, // search index, built once from the static data
    q: "",
    lastSearch: "",
    faqTopic: "all",
    faqQ: "",
    lastHash: null,
    wired: false,
    rendered: false,
    timer: null,
  };

  const esc = (value) => escapeHtml(value == null ? "" : String(value));
  const root = () => document.getElementById("help-root");
  const byId = (list, id) => list.find((item) => item.id === id);

  /* ------------------------------------------------------------------ */
  /* Text helpers                                                        */
  /* ------------------------------------------------------------------ */

  // The content supports `code`, **bold** and *italic* only. Everything is
  // HTML-escaped first, then those three markers become tags, so content can
  // never inject markup.
  function inline(text) {
    return String(text)
      .split(/(`[^`]+`)/)
      .map((part) => {
        if (part.length > 1 && part[0] === "`" && part[part.length - 1] === "`") {
          return `<code>${esc(part.slice(1, -1))}</code>`;
        }
        return esc(part)
          .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
          .replace(/\*([^*\s][^*]*?)\*/g, "<em>$1</em>");
      })
      .join("");
  }

  const plain = (text) => String(text).replace(/[`*]/g, "");

  function formatDate(iso) {
    const d = new Date(`${iso}T00:00:00Z`);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  const regexEscape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Wrap matches of the search terms in <mark>. Works on the raw string and
  // escapes each piece, so entities are never split.
  function highlight(text, terms) {
    const raw = plain(text);
    if (!terms.length) return esc(raw);
    const re = new RegExp(`(${terms.map(regexEscape).join("|")})`, "gi");
    return raw
      .split(re)
      .map((piece, i) => (i % 2 ? `<mark>${esc(piece)}</mark>` : esc(piece)))
      .join("");
  }

  /* ------------------------------------------------------------------ */
  /* Search                                                              */
  /* ------------------------------------------------------------------ */
  function blockText(block) {
    if (block.p) return [block.p];
    if (block.ul) return block.ul;
    if (block.ol) return block.ol;
    if (block.note) return [block.note.text];
    if (block.table) return [block.table.head.join(" "), ...block.table.rows.map((r) => r.join(" "))];
    return [];
  }

  function articleBody(article) {
    const parts = [...(article.steps || [])];
    for (const section of article.sections || []) {
      parts.push(section.heading);
      for (const block of section.blocks || []) parts.push(...blockText(block));
    }
    return parts.map(plain);
  }

  function buildIndex() {
    const { articles, categories, faqs } = hc.data;
    hc.index = {
      articles: articles.map((article) => {
        const category = byId(categories, article.category);
        const body = articleBody(article);
        return {
          article,
          title: plain(article.title).toLowerCase(),
          category: plain(category ? category.title : "").toLowerCase(),
          summary: plain(article.summary).toLowerCase(),
          body,
          bodyLower: body.map((s) => s.toLowerCase()),
        };
      }),
      faqs: faqs.map((faq) => ({
        faq,
        question: plain(faq.question).toLowerCase(),
        answer: faq.answer.map((a) => plain(a).toLowerCase()).join(" "),
      })),
    };
  }

  function termsOf(query) {
    const seen = new Set();
    const out = [];
    for (const word of String(query).toLowerCase().split(/\s+/)) {
      const t = word.replace(/[^\p{L}\p{N}'’_-]/gu, "");
      if (t && !seen.has(t)) {
        seen.add(t);
        out.push(t);
        if (out.length >= MAX_TERMS) break;
      }
    }
    return out;
  }

  // Every term must appear somewhere in the article (title, category, summary
  // or body); title hits count most, then category/summary, then the body.
  function searchArticles(terms) {
    const results = [];
    for (const entry of hc.index.articles) {
      let score = 0;
      let ok = true;
      for (const t of terms) {
        const inTitle = entry.title.includes(t);
        const inCat = entry.category.includes(t);
        const inSummary = entry.summary.includes(t);
        const inBody = entry.bodyLower.some((s) => s.includes(t));
        if (!inTitle && !inCat && !inSummary && !inBody) {
          ok = false;
          break;
        }
        score += (inTitle ? 6 : 0) + (inCat ? 3 : 0) + (inSummary ? 3 : 0) + (inBody ? 1 : 0);
      }
      if (ok) results.push({ entry, score });
    }
    results.sort((a, b) => b.score - a.score || a.entry.article.title.localeCompare(b.entry.article.title));
    return results;
  }

  function searchFaqs(terms, topic) {
    return hc.index.faqs.filter((entry) => {
      if (topic !== "all" && entry.faq.topic !== topic) return false;
      return terms.every((t) => entry.question.includes(t) || entry.answer.includes(t));
    });
  }

  // A short body excerpt for results whose match isn't visible in the title or
  // summary, so the reader can see why it matched.
  function snippet(entry, terms) {
    const visible = `${entry.title} ${entry.summary}`;
    if (terms.every((t) => visible.includes(t))) return "";
    for (let i = 0; i < entry.bodyLower.length; i++) {
      const lower = entry.bodyLower[i];
      const at = terms.map((t) => lower.indexOf(t)).filter((n) => n >= 0);
      if (!at.length) continue;
      const start = Math.max(0, Math.min(...at) - 50);
      const text = entry.body[i];
      const piece = text.slice(start, start + 140);
      return `${start > 0 ? "…" : ""}${piece}${start + 140 < text.length ? "…" : ""}`;
    }
    return "";
  }

  /* ------------------------------------------------------------------ */
  /* Routing                                                             */
  /* ------------------------------------------------------------------ */
  function parseRoute() {
    const raw = location.hash.replace(/^#/, "");
    const cut = raw.indexOf("?");
    const path = cut === -1 ? raw : raw.slice(0, cut);
    const params = new URLSearchParams(cut === -1 ? "" : raw.slice(cut + 1));
    const seg = path.split("/").map((s) => {
      try {
        return decodeURIComponent(s);
      } catch (error) {
        return s;
      }
    });
    if (seg[1] === "topic") return { view: "topic", id: seg[2] || "", q: params.get("q") || "" };
    if (seg[1]) return { view: "article", id: seg[1], q: params.get("q") || "" };
    return { view: "home", q: (params.get("q") || "").slice(0, 120) };
  }

  const articleHref = (id) => `#help/${encodeURIComponent(id)}`;
  const topicHref = (id) => `#help/topic/${encodeURIComponent(id)}`;
  const searchHref = (q) => (q ? `#help?q=${encodeURIComponent(q)}` : "#help");

  /* ------------------------------------------------------------------ */
  /* Building blocks                                                     */
  /* ------------------------------------------------------------------ */
  const SEARCH_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
  const ARROW =
    '<svg class="hc-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="13 6 19 12 13 18"/></svg>';

  function searchBox(q) {
    return `
      <form class="hc-search" role="search" data-hc-form>
        ${SEARCH_ICON}
        <label class="rp-sr" for="hc-search">Search the Help Center</label>
        <input id="hc-search" type="search" autocomplete="off" maxlength="120"
          placeholder="Search guides and FAQs"
          value="${esc(q)}" />
        <button type="button" class="hc-clear${q ? "" : " hidden"}" data-hc-action="clear-search" aria-label="Clear search">Clear</button>
      </form>`;
  }

  function categoryTitle(id) {
    const c = byId(hc.data.categories, id);
    return c ? c.title : "";
  }

  function articleCard(article, { terms = [], excerpt = "" } = {}) {
    return `
      <li>
        <a class="hc-result" href="${articleHref(article.id)}">
          <span class="hc-result-cat">${esc(categoryTitle(article.category))}</span>
          <strong>${terms.length ? highlight(article.title, terms) : esc(article.title)}</strong>
          <span class="hc-result-sum">${terms.length ? highlight(article.summary, terms) : esc(article.summary)}</span>
          ${excerpt ? `<span class="hc-result-snip">${highlight(excerpt, terms)}</span>` : ""}
        </a>
      </li>`;
  }

  function faqItem(entry, terms = []) {
    const faq = entry.faq || entry;
    const article = faq.article ? byId(hc.data.articles, faq.article) : null;
    return `
      <details class="hc-faq">
        <summary>${terms.length ? highlight(faq.question, terms) : inline(faq.question)}</summary>
        <div class="hc-faq-body">
          ${faq.answer.map((a) => `<p>${inline(a)}</p>`).join("")}
          ${article ? `<p class="hc-faq-more"><a href="${articleHref(article.id)}">Read the guide: ${esc(article.title)} ${ARROW}</a></p>` : ""}
        </div>
      </details>`;
  }

  function emptyState(text, extra = "") {
    return `<div class="hc-empty" role="status"><strong>${text}</strong>${extra}</div>`;
  }

  /* ------------------------------------------------------------------ */
  /* Blocks inside an article                                            */
  /* ------------------------------------------------------------------ */
  function renderBlock(block) {
    if (block.p) return `<p>${inline(block.p)}</p>`;
    if (block.ul) return `<ul>${block.ul.map((i) => `<li>${inline(i)}</li>`).join("")}</ul>`;
    if (block.ol) return `<ol>${block.ol.map((i) => `<li>${inline(i)}</li>`).join("")}</ol>`;
    if (block.note) {
      const kind = ["tip", "info", "warning"].includes(block.note.kind) ? block.note.kind : "info";
      const label = { tip: "Tip", info: "Note", warning: "Important" }[kind];
      return `<div class="hc-note hc-note-${kind}" role="note"><strong>${label}</strong><span>${inline(block.note.text)}</span></div>`;
    }
    if (block.table) {
      const { head, rows } = block.table;
      return `
        <div class="hc-table-wrap">
          <table class="hc-table">
            <thead><tr>${head.map((h) => `<th scope="col">${inline(h)}</th>`).join("")}</tr></thead>
            <tbody>${rows.map((r) => `<tr>${r.map((c, i) => (i === 0 ? `<th scope="row">${inline(c)}</th>` : `<td>${inline(c)}</td>`)).join("")}</tr>`).join("")}</tbody>
          </table>
        </div>`;
    }
    return "";
  }

  /* ------------------------------------------------------------------ */
  /* Views                                                               */
  /* ------------------------------------------------------------------ */
  function quickLinks() {
    const wanted = [
      ["section-reports", "Reports"],
      ["section-employees", "Employees"],
      ["section-companies", "Companies"],
      ["section-assets", "Assets"],
      ["section-suppliers", "Suppliers"],
      ["section-audit", "Audit log"],
      ["section-sessions", "Sessions"],
    ];
    const hashes = typeof SECTION_TO_HASH !== "undefined" ? SECTION_TO_HASH : {};
    const links = [];
    for (const [sectionId, label] of wanted) {
      // Only offer pages this person's sidebar actually shows.
      const nav = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
      if (!nav || nav.classList.contains("hidden") || !hashes[sectionId]) continue;
      links.push(`<a class="hc-chip" href="#${hashes[sectionId]}">${esc(label)}</a>`);
    }
    return links.join("");
  }

  function quickSection() {
    const links = quickLinks();
    if (!links) return "";
    return `<section class="hc-block" aria-labelledby="hc-quick-h">
        <h3 id="hc-quick-h">Quick links</h3>
        <p class="hc-sub">Jump to a page in Nexus One.</p>
        <div class="hc-chips">${links}</div>
      </section>`;
  }

  // After a page reload the sidebar's role-based items are revealed a moment
  // after this page first renders (app.js reveals them once /auth/me returns),
  // so fill the quick links in again once the user is known.
  function refreshQuickLinksWhenReady() {
    let tries = 0;
    const tick = () => {
      const slot = document.getElementById("hc-quick-slot");
      if (!slot) return; // navigated away from the landing view
      if (typeof state !== "undefined" && state.user) {
        setTimeout(() => {
          const again = document.getElementById("hc-quick-slot");
          if (again) again.innerHTML = quickSection();
        }, 0);
        return;
      }
      if (typeof state === "undefined" || !state.accessToken || ++tries > 200) return;
      setTimeout(tick, 100);
    };
    tick();
  }

  function homeBody() {
    const { categories, articles, popular, topics } = hc.data;
    const popularItems = popular.map((id) => byId(articles, id)).filter(Boolean);
    return `
      <section class="hc-block" aria-labelledby="hc-topics-h">
        <h3 id="hc-topics-h">Browse by topic</h3>
        <ul class="hc-topics">
          ${categories
            .map((c) => {
              const count = articles.filter((a) => a.category === c.id).length;
              return `
                <li>
                  <a class="hc-topic" href="${topicHref(c.id)}">
                    <strong>${esc(c.title)}</strong>
                    <span>${esc(c.description)}</span>
                    <em>${count} ${count === 1 ? "guide" : "guides"} ${ARROW}</em>
                  </a>
                </li>`;
            })
            .join("")}
        </ul>
      </section>

      <div class="hc-two">
        <section class="hc-block" aria-labelledby="hc-pop-h">
          <h3 id="hc-pop-h">Popular guides</h3>
          <ul class="hc-linklist">
            ${popularItems.map((a) => `<li><a href="${articleHref(a.id)}"><span>${esc(a.title)}</span>${ARROW}</a></li>`).join("")}
          </ul>
        </section>
        <div id="hc-quick-slot">${quickSection()}</div>
      </div>

      <section class="hc-block" aria-labelledby="hc-faq-h">
        <h3 id="hc-faq-h">Frequently asked questions</h3>
        <div class="hc-faq-tools">
          <div class="hc-chips" role="group" aria-label="Filter questions by topic">
            ${[{ id: "all", title: "All" }, ...topics]
              .map(
                (t) =>
                  `<button type="button" class="hc-chip${hc.faqTopic === t.id ? " on" : ""}" data-hc-action="faq-topic" data-topic="${esc(t.id)}" aria-pressed="${hc.faqTopic === t.id}">${esc(t.title)}</button>`
              )
              .join("")}
          </div>
          <div class="hc-faq-search">
            ${SEARCH_ICON}
            <label class="rp-sr" for="hc-faq-q">Search questions</label>
            <input id="hc-faq-q" type="search" autocomplete="off" maxlength="120" placeholder="Search questions…" value="${esc(hc.faqQ)}" />
          </div>
        </div>
        <div id="hc-faq-list" aria-live="polite">${faqListHtml()}</div>
      </section>

      <section class="hc-block hc-more" aria-labelledby="hc-more-h">
        <h3 id="hc-more-h">Need more help?</h3>
        <p>Nexus One doesn't have a built-in support-ticket system or contact form. If these guides don't answer your question, ask your Nexus Auth administrator — the person who manages accounts and roles for your organisation — and tell them what you were doing, the exact message you saw, and roughly when.</p>
        <p><a href="${articleHref("troubleshooting-access")}">Troubleshooting access problems ${ARROW}</a></p>
      </section>`;
  }

  function faqListHtml() {
    const terms = termsOf(hc.faqQ);
    const list = searchFaqs(terms, hc.faqTopic);
    if (!list.length) {
      return emptyState(
        "No questions match.",
        `<span>Try fewer words, or <button type="button" class="hc-linkbtn" data-hc-action="faq-reset">show all questions</button>.</span>`
      );
    }
    return list.map((entry) => faqItem(entry, terms)).join("");
  }

  function resultsBody(q) {
    const terms = termsOf(q);
    if (!terms.length) return homeBody();
    const found = searchArticles(terms);
    const faqs = searchFaqs(terms, "all");
    const total = found.length + faqs.length;
    if (!total) {
      return `
        <p class="hc-count" role="status">No results for “<strong>${esc(q)}</strong>”.</p>
        ${emptyState(
          "Nothing matched your search.",
          `<span>Check the spelling, try fewer or more general words (for example “export” or “role”), or
            <button type="button" class="hc-linkbtn" data-hc-action="clear-search">clear the search</button>
            to browse by topic.</span>`
        )}`;
    }
    return `
      <p class="hc-count" role="status">
        <strong>${found.length}</strong> ${found.length === 1 ? "guide" : "guides"} and
        <strong>${faqs.length}</strong> ${faqs.length === 1 ? "question" : "questions"} match “<strong>${esc(q)}</strong>”.
      </p>
      ${
        found.length
          ? `<section class="hc-block"><h3>Guides</h3>
              <ul class="hc-results">${found.map((r) => articleCard(r.entry.article, { terms, excerpt: snippet(r.entry, terms) })).join("")}</ul>
            </section>`
          : ""
      }
      ${
        faqs.length
          ? `<section class="hc-block"><h3>Questions</h3>${faqs.map((entry) => faqItem(entry, terms)).join("")}</section>`
          : ""
      }`;
  }

  function topicBody(id) {
    const category = byId(hc.data.categories, id);
    if (!category) {
      return `<nav class="rp-crumbs"><a href="#help">&larr; Help Center</a></nav>${emptyState("That help topic doesn't exist.")}`;
    }
    const list = hc.data.articles.filter((a) => a.category === id);
    const faqs = hc.data.faqs.filter((f) => f.article && list.some((a) => a.id === f.article));
    return `
      <nav class="rp-crumbs" aria-label="Breadcrumb"><a href="#help">&larr; Help Center</a><span aria-hidden="true">/</span><span>${esc(category.title)}</span></nav>
      <header class="hc-head">
        <h3>${esc(category.title)}</h3>
        <p>${esc(category.description)}</p>
      </header>
      <ul class="hc-results">${list.map((a) => articleCard(a)).join("")}</ul>
      ${
        faqs.length
          ? `<section class="hc-block"><h3>Related questions</h3>${faqs.map((f) => faqItem(f)).join("")}</section>`
          : ""
      }`;
  }

  function articleBodyHtml(id, fromQuery) {
    const article = byId(hc.data.articles, id);
    if (!article) {
      return `<nav class="rp-crumbs"><a href="#help">&larr; Help Center</a></nav>${emptyState(
        "That help article doesn't exist.",
        `<span><a href="#help">Browse all topics</a> or search above.</span>`
      )}`;
    }
    const category = byId(hc.data.categories, article.category);
    const back = fromQuery
      ? `<a href="${searchHref(fromQuery)}">&larr; Back to search results</a>`
      : `<a href="#help">&larr; Help Center</a>`;
    const related = (article.related || []).map((rid) => byId(hc.data.articles, rid)).filter(Boolean);
    const faqs = hc.data.faqs.filter((f) => f.article === article.id);
    const steps = article.steps && article.steps.length
      ? `<section class="hc-section"><h4>Steps</h4><ol class="hc-steps">${article.steps.map((s) => `<li>${inline(s)}</li>`).join("")}</ol></section>`
      : "";
    const sections = (article.sections || [])
      .map((s) => `<section class="hc-section"><h4>${esc(plain(s.heading))}</h4>${(s.blocks || []).map(renderBlock).join("")}</section>`)
      .join("");
    return `
      <nav class="rp-crumbs" aria-label="Breadcrumb">
        ${back}
        ${category ? `<span aria-hidden="true">/</span><a href="${topicHref(category.id)}">${esc(category.title)}</a>` : ""}
      </nav>
      <article class="hc-article">
        <header class="hc-head">
          ${category ? `<span class="hc-result-cat">${esc(category.title)}</span>` : ""}
          <h3>${esc(article.title)}</h3>
          <p>${esc(article.summary)}</p>
          <p class="hc-updated">Last updated ${esc(formatDate(article.updated))}</p>
        </header>
        ${steps}
        ${sections}
        ${
          faqs.length
            ? `<section class="hc-section"><h4>Related questions</h4>${faqs.map((f) => faqItem(f)).join("")}</section>`
            : ""
        }
        ${
          related.length
            ? `<section class="hc-section hc-related"><h4>Related articles</h4>
                <ul class="hc-linklist">${related.map((a) => `<li><a href="${articleHref(a.id)}"><span>${esc(a.title)}</span>${ARROW}</a></li>`).join("")}</ul>
              </section>`
            : ""
        }
      </article>`;
  }

  /* ------------------------------------------------------------------ */
  /* Render                                                              */
  /* ------------------------------------------------------------------ */
  function hero(q) {
    return `
      <div class="hc-hero">
        <h3>Welcome to the Help Center</h3>
        <p>Step-by-step guides for everything in Nexus One — signing in, managing people, companies, assets and suppliers, running reports, and keeping access secure. Search below, or browse by topic.</p>
        ${searchBox(q)}
        <p class="hc-hint">Try “unlock account”, “export” or “supplier”.</p>
      </div>`;
  }

  function render() {
    if (!hc.data) {
      root().innerHTML = `<div class="rp-error" role="alert"><div>The Help Center content could not be loaded.</div><button type="button" data-hc-action="reload">Reload page</button></div>`;
      return;
    }
    if (!hc.index) buildIndex();
    const route = parseRoute();
    hc.q = route.view === "home" ? route.q : "";
    // Remember the last search so an article opened from its results can offer
    // "Back to search results" (the article's own address has no query).
    // Landing without a search, or on a topic page, forgets it.
    if (route.view === "home") hc.lastSearch = termsOf(hc.q).length ? hc.q.trim() : "";
    else if (route.view === "topic") hc.lastSearch = "";
    let body;
    let header = "";
    if (route.view === "home") {
      header = hero(hc.q);
      body = resultsBody(hc.q);
    } else if (route.view === "topic") {
      header = `<div class="hc-hero hc-hero-compact">${searchBox("")}</div>`;
      body = topicBody(route.id);
    } else {
      header = `<div class="hc-hero hc-hero-compact">${searchBox("")}</div>`;
      body = articleBodyHtml(route.id, route.q || hc.lastSearch);
    }
    root().innerHTML = `${header}<div id="hc-body">${body}</div>`;
    hc.lastHash = location.hash;
    hc.rendered = true;
    if (document.getElementById("hc-quick-slot")) refreshQuickLinksWhenReady();
  }

  // Re-render only the results area while typing, so the search box keeps
  // focus and the caret.
  function renderBody() {
    const body = document.getElementById("hc-body");
    if (!body) return render();
    body.innerHTML = resultsBody(hc.q);
    hc.lastSearch = termsOf(hc.q).length ? hc.q.trim() : "";
    const clear = root().querySelector(".hc-clear");
    if (clear) clear.classList.toggle("hidden", !hc.q);
    const hash = searchHref(termsOf(hc.q).length ? hc.q.trim() : "");
    if (location.hash !== hash) history.replaceState(null, "", hash);
    hc.lastHash = location.hash;
  }

  function runSearchNow(value) {
    const route = parseRoute();
    if (route.view !== "home") {
      // Searching from an article/topic page: go to the results (a real
      // navigation, so Back returns here).
      location.hash = searchHref(value.trim());
      return;
    }
    hc.q = value;
    renderBody();
  }

  /* ------------------------------------------------------------------ */
  /* Events (delegated on the root, wired once)                          */
  /* ------------------------------------------------------------------ */
  function ensureWired() {
    if (hc.wired) return;
    hc.wired = true;
    const el = root();

    el.addEventListener("input", (event) => {
      const target = event.target;
      if (target.id === "hc-search") {
        clearTimeout(hc.timer);
        const value = target.value;
        const clear = el.querySelector(".hc-clear");
        if (clear) clear.classList.toggle("hidden", !value);
        // Typing on an article/topic page jumps to the results once there is
        // something to search for.
        hc.timer = setTimeout(() => {
          if (parseRoute().view !== "home" && !termsOf(value).length) return;
          runSearchNow(value);
        }, SEARCH_DEBOUNCE_MS);
      } else if (target.id === "hc-faq-q") {
        hc.faqQ = target.value;
        const list = document.getElementById("hc-faq-list");
        if (list) list.innerHTML = faqListHtml();
      }
    });

    el.addEventListener("submit", (event) => {
      if (!event.target.matches("[data-hc-form]")) return;
      event.preventDefault();
      clearTimeout(hc.timer);
      runSearchNow(el.querySelector("#hc-search").value);
    });

    el.addEventListener("click", (event) => {
      const button = event.target.closest("[data-hc-action]");
      if (!button) return;
      const action = button.getAttribute("data-hc-action");
      if (action === "clear-search") {
        clearTimeout(hc.timer);
        const input = el.querySelector("#hc-search");
        if (input) input.value = "";
        hc.q = "";
        if (parseRoute().view === "home") {
          renderBody();
          if (input) input.focus();
        } else {
          location.hash = "#help";
        }
      } else if (action === "faq-topic") {
        hc.faqTopic = button.getAttribute("data-topic") || "all";
        el.querySelectorAll('[data-hc-action="faq-topic"]').forEach((b) => {
          const on = b.getAttribute("data-topic") === hc.faqTopic;
          b.classList.toggle("on", on);
          b.setAttribute("aria-pressed", String(on));
        });
        const list = document.getElementById("hc-faq-list");
        if (list) list.innerHTML = faqListHtml();
      } else if (action === "faq-reset") {
        hc.faqTopic = "all";
        hc.faqQ = "";
        render();
      } else if (action === "reload") {
        location.reload();
      }
    });
  }

  function scrollToTop() {
    const content = document.querySelector(".content");
    if (content && typeof content.scrollTo === "function") content.scrollTo(0, 0);
    window.scrollTo(0, 0);
  }

  function show() {
    hc.data = window.NEXUS_HELP || null;
    ensureWired();
    // The nav click lands here twice (directly, then via hashchange), and the
    // address changes via replaceState while typing: skip a re-render when the
    // view already matches the URL.
    if (hc.rendered && hc.lastHash === location.hash && root().childElementCount) return;
    const before = hc.lastHash;
    render();
    // New page of help (article/topic/landing reached by link): start at the top.
    if (before !== null) scrollToTop();
  }

  window.NexusSections = window.NexusSections || {};
  window.NexusSections["section-help"] = show;
})();
