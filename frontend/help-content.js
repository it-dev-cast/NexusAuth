/* Help Center content — structured, static, and checked against the app.
 *
 * Every statement here describes behaviour that exists in this codebase today
 * (the pages in index.html/app.js and the rules in app/services, app/core).
 * When behaviour changes, update the matching article and bump its `updated`
 * date; if a feature is removed, delete its text rather than leaving it
 * documented. Nothing is invented: there is no support-ticket system or
 * contact address in this project, so none is described.
 *
 * Shape
 *   categories[]  { id, title, description }
 *   articles[]    { id, category, title, summary, updated,
 *                   steps?: [string],                 // numbered "Steps"
 *                   sections?: [{ heading, blocks: [ block ] }],
 *                   related?: [articleId] }
 *   block         { p: string } | { ul: [string] } | { ol: [string] }
 *               | { note: { kind: "tip" | "info" | "warning", text: string } }
 *               | { table: { head: [string], rows: [[string]] } }
 *   faqs[]        { id, topic, question, answer: [string], article?: articleId }
 *   topics[]      FAQ groupings (id, title)
 *   popular[]     article ids shown as quick links on the landing page
 *
 * Inline text supports `code` and **bold** only (rendered safely by help.js).
 * `updated` is the date the article was last written/verified against the app.
 */
window.NEXUS_HELP = {
  categories: [
    {
      id: "getting-started",
      title: "Getting Started",
      description: "Signing in, finding your way around, and running reports.",
    },
    {
      id: "people",
      title: "User and Employee Management",
      description: "Users and roles, employee records, departments, job roles and application access.",
    },
    {
      id: "companies",
      title: "Company Management",
      description: "Adding companies, what a company record holds, and the data tied to a company.",
    },
    {
      id: "assets-suppliers",
      title: "Assets and Suppliers",
      description: "Registering assets, manufacturers and models, suppliers, and finding assets.",
    },
    {
      id: "security",
      title: "Security and Administration",
      description: "Roles and permissions, the audit log, sessions and events, and fixing access problems.",
    },
  ],

  topics: [
    { id: "login-access", title: "Login and access" },
    { id: "people", title: "Users and employees" },
    { id: "companies", title: "Company records" },
    { id: "assets-suppliers", title: "Assets and suppliers" },
    { id: "reports-exports", title: "Reports and exports" },
    { id: "master-data", title: "Master management" },
    { id: "errors", title: "Common errors" },
  ],

  popular: ["logging-in", "reports-guide", "roles-permissions", "employee-records", "managing-companies", "troubleshooting-access"],

  articles: [
    /* ===================== Getting Started ===================== */
    {
      id: "logging-in",
      category: "getting-started",
      title: "Logging in and out",
      summary: "Sign in with your email and password, create an account if you don't have one, and how sessions and lockouts work.",
      updated: "2026-10-26",
      steps: [
        "Open the Nexus One address that ends in `/ui`. The sign-in screen has two tabs: **Login** and **Register**.",
        "On the **Login** tab enter your **Email** and **Password**, then press **Login**.",
        "When sign-in succeeds you land on the Overview page. The sidebar shows the pages your role can open.",
      ],
      sections: [
        {
          heading: "If you don't have an account yet",
          blocks: [
            { p: "Open the **Register** tab, enter a **Full name** (optional), your **Email** and a **Password**, and submit. You'll see “Registration received. If this email isn't already registered, you can now sign in.” — then sign in on the Login tab. The message is the same whether or not the address already had an account, so it never reveals who is registered; if you can't sign in, the address may already belong to an account (ask an administrator)." },
            { p: "A new account always starts with **Read only** access. An administrator can change your role afterwards (see *Understanding roles and permissions*). A password can be at most 72 bytes long." },
          ],
        },
        {
          heading: "If sign-in fails",
          blocks: [
            { p: "The message is always “Invalid email or password.” — whether the email is unknown, the password is wrong, the account is inactive or the account is locked. That is deliberate: the message must not reveal which accounts exist." },
            {
              ul: [
                "After **5** failed attempts an account is locked for **15 minutes**.",
                "An administrator can unlock it sooner from the Users page (**Unlock**).",
                "The sign-in and register forms also limit how fast you can try: more than 10 sign-in attempts (or 5 registrations) in a minute from one address shows “Too many requests. Please try again shortly.” Wait a minute and try again.",
              ],
            },
          ],
        },
        {
          heading: "How long you stay signed in",
          blocks: [
            { p: "Your access token lasts **15 minutes**. Reloading the page keeps you signed in while the token is still valid, and closing the browser tab ends the session." },
            { p: "To get a new access token without signing in again, press **Refresh access token** on the Overview page (under *Your session*). If you see “Access token has expired.” and can't refresh, log in again." },
          ],
        },
        {
          heading: "Logging out",
          blocks: [
            { p: "Press **Logout** at the bottom of the sidebar and confirm “Log out?”. This ends the current session." },
            { p: "**Logout all sessions** (Overview → *Your session*) revokes every session on your account, including ones open in other browsers." },
            { note: { kind: "info", text: "To change your password, open **Settings → Password** (you need your current password). The web app has no “forgot password” screen." } },
          ],
        },
      ],
      related: ["troubleshooting-access", "sessions-events", "roles-permissions", "dashboard-overview"],
    },

    {
      id: "dashboard-overview",
      category: "getting-started",
      title: "Understanding the Overview dashboard",
      summary: "What the Overview page shows to everyone and what only administrators see.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "For everyone: Your session",
          blocks: [
            { p: "**Current user** shows your email, full name, role, company ID, whether your account is active, and how many times you've logged in." },
            { p: "**JWT claims** lists the details carried by your current access token: your user ID, role, company ID, token ID, when it was issued, when it expires and its type." },
            { p: "Two buttons sit here: **Refresh access token** and **Logout all sessions**." },
          ],
        },
        {
          heading: "For administrators: System overview",
          blocks: [
            { p: "Administrators also see five counters:" },
            { ul: ["**Registered users**", "**Successful logins**", "**Active sessions**", "**Failed attempts (current)**", "**Locked accounts**"] },
            { p: "Below them, **Recent activity** lists the most recent logins across every account. The Sessions page has the full, searchable list." },
            { note: { kind: "info", text: "The counters and the recent-activity list are administrator-only. Other roles see only *Your session*." } },
          ],
        },
        {
          heading: "Looking for business numbers?",
          blocks: [{ p: "The **Reports** page has its own summary cards (employees, companies, assets, suppliers) that link to the reports behind each number." }],
        },
      ],
      related: ["reports-guide", "your-account", "navigating-the-app"],
    },

    {
      id: "navigating-the-app",
      category: "getting-started",
      title: "Navigating the application",
      summary: "The sidebar, which pages you can see, page links, exports and themes.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "The sidebar",
          blocks: [
            { p: "The sidebar lists every page you can open, in groups (Workspace, People, Assets & Data, Security, Support). Press a group's heading to fold it up or open it again — your choice is remembered in this browser (**Settings → Appearance** has an *Open all sidebar groups* button). Press the round **‹** button on the sidebar's edge to collapse it to icons only; hover an icon to see the page name. At the bottom you can see who you're signed in as (email, role and company) and log out." },
            {
              table: {
                head: ["Your role", "Pages in the sidebar"],
                rows: [
                  ["Administrator", "Overview, Reports, Users, Companies, Employees, Suppliers, Assets, Master Management, Audit log, Events, Sessions, Settings, Help Center"],
                  ["Operator / Read only", "Overview, Reports, Sessions, Settings, Help Center"],
                ],
              },
            },
            { p: "Departments, Job Roles, Manufacturers and Models aren't separate sidebar items: they are masters, chosen from the dropdown on **Master Management**. **Applications** has its own sidebar item and page (Application Master). Old addresses, such as `/ui#job-roles`, still open the right master." },
            { note: { kind: "info", text: "Hiding a page is only a convenience. The server checks your role on every request, so a page that isn't in your sidebar can't be used by opening its address either." } },
          ],
        },
        {
          heading: "Every page has its own address",
          blocks: [{ p: "Each page has its own web address (for example `/ui#employees`), so refreshing the browser, Back and Forward all keep you on the right page. You can bookmark a page or share its link — the person opening it still has to sign in and be allowed to see it." }],
        },
        {
          heading: "Searching and exporting",
          blocks: [
            { p: "Search boxes on list pages narrow the rows already loaded on that page as you type. The **Export** button on those pages downloads the rows currently shown as a CSV file." },
            { p: "For exports of everything that matches a set of filters, use the **Reports** page instead (see *Running and exporting reports*)." },
          ],
        },
        {
          heading: "Themes",
          blocks: [{ p: "The **palette button** at the top right of every page changes the theme. There are nine: seven light and two dark. Until you choose one, the app uses Casterly Light or Graphite Dark to match your device's light/dark setting, and it remembers your choice in this browser. *Use my device's setting* goes back to following your device." }],
        },
        {
          heading: "Confirmations",
          blocks: [{ p: "Actions that are hard to undo — logging out, changing a role, deactivating a company — ask you to confirm first." }],
        },
      ],
      related: ["roles-permissions", "reports-guide", "logging-in"],
    },

    {
      id: "your-account",
      category: "getting-started",
      title: "Using Settings and your account details",
      summary: "Settings shows your profile and lets you change the sidebar, password and sessions. What can and can't be changed.",
      updated: "2026-10-27",
      steps: [
        "Open **Settings** in the sidebar (every role has it, under *Support*).",
        "**Profile** shows who you're signed in as: name, email, role, company, account status and how many times you've signed in.",
        "**Appearance** lets you keep the sidebar collapsed or open all sidebar groups. (The theme is chosen from the palette button at the top right of every page.)",
        "**Password** changes your password; **Sessions** signs you out of every session.",
      ],
      sections: [
        {
          heading: "Appearance",
          blocks: [
            { p: "*Keep the sidebar collapsed* shows only icons; *Open all sidebar groups* unfolds any group you folded. To change the theme, click the palette button at the top right of any page: pick one of the nine themes (saved in this browser), or *Use my device's setting* to go back to Casterly Light or Graphite Dark depending on your device." },
          ],
        },
        {
          heading: "Changing your password",
          blocks: [
            { ol: ["Enter your **Current password**.", "Enter the **New password** twice. It must differ from the current one and be at most 72 bytes long.", "Press **Change password** and confirm."] },
            { p: "If the current password is wrong you'll see “Current password is incorrect.” and nothing changes. When it succeeds, every session on your account is ended — including this one — so you sign in again with the new password." },
          ],
        },
        {
          heading: "Logging out of all sessions",
          blocks: [
            { p: "**Log out of all sessions** ends every session on your account on every browser and device, then returns you to the sign-in screen. The **Sessions** page lists your sign-ins (when each was created, last used, the address it came from and whether it is Active or Revoked)." },
          ],
        },
        {
          heading: "What you can't change in the web app",
          blocks: [
            { p: "There is no profile-editing screen: your name and email can't be changed from the web app." },
            { p: "Your **role** is set by an administrator on the Users page. Ask an administrator if you need different access." },
          ],
        },
      ],
      related: ["roles-permissions", "sessions-events", "logging-in"],
    },

    {
      id: "reports-guide",
      category: "getting-started",
      title: "Running and exporting reports",
      summary: "Open a report, filter, sort and page through it, then export it to CSV or print it.",
      updated: "2026-10-26",
      steps: [
        "Open **Reports** in the sidebar. The page opens with summary cards and the list of reports you're allowed to run.",
        "Pick a category tab, or type in **Search reports…** to find one by name or description.",
        "Open a report. Set any filters you need and press **Apply filters**. **Reset** clears them.",
        "Click a column heading to sort by it; click again to reverse the order.",
        "Move through the results with **Previous** / **Next**, and choose how many **Rows per page** to show.",
        "Press **Export CSV** to download the results, or **Print** to print the page.",
      ],
      sections: [
        {
          heading: "Which reports you can run",
          blocks: [
            { p: "Reports follow the same permissions as the data underneath them, so you only ever see reports you are allowed to run." },
            {
              table: {
                head: ["Category", "Administrator", "Operator", "Read only"],
                rows: [
                  ["Employee reports", "Yes", "Yes (own company)", "No"],
                  ["Company reports", "Yes", "Yes (own company)", "Yes (own company)"],
                  ["Asset reports", "Yes", "Yes", "Yes"],
                  ["Supplier reports", "Yes", "Yes", "Yes"],
                  ["Master Management reports (Summary, Values, Unused Values)", "Yes", "Yes", "Yes"],
                  ["Master Changes (who changed which master)", "Yes", "No", "No"],
                  ["Security & Audit reports", "Yes", "No", "No"],
                ],
              },
            },
            { p: "Operators and read-only users only see their own company's employees and company record. Assets and suppliers are shared across companies, so those reports are not limited by company." },
          ],
        },
        {
          heading: "Master Management reports",
          blocks: [
            {
              ul: [
                "**Master Summary** — every master (Departments, Job Roles, Applications, Application Categories, Manufacturers, Models, Supplier Categories, Payment Terms) with how many values are active, inactive and in total, and how many values records use.",
                "**Master Values** — every value of every master with its status, how many records use it, and when it was added and last updated. Filter by master, status, name and date added.",
                "**Unused Master Values** — active values that no record uses: candidates to deactivate or tidy up.",
                "**Master Changes** (administrators) — who added, edited, deactivated or reactivated a master value, and when. Before/after values aren't included; the Audit log has those.",
              ],
            },
            { p: "“In use” counts current records: exited employees and disposed assets aren't counted, and a Job Role counts an employee once whether it is saved as their job role or their title. The Master Management page links straight to these reports." },
          ],
        },
        {
          heading: "The summary cards",
          blocks: [
            { p: "The cards are calculated live from the database. Click one to open the report behind it with the filters already applied, so the number on the card and the report's total always match." },
            {
              ul: [
                "**Total employees** — everyone except exited employees.",
                "**Active employees** — employees whose status is Active.",
                "**Total companies**, **Total assets**, **Total suppliers**.",
                "**Recent administrative activity** (administrators only) — changes to records and access over the last 7 days, counted in UTC.",
              ],
            },
          ],
        },
        {
          heading: "Filters",
          blocks: [
            { p: "Each report offers only the filters that make sense for it, such as company, department, status, category or a date range. A filter always changes the results; one that doesn't apply to a report simply isn't shown." },
            {
              ul: [
                "**Employee status** defaults to *Current*, which hides exited employees (the same as the Employees page). Choose *All statuses* to include them.",
                "**Dates** are matched in UTC, and the “to” date includes that whole day.",
                "Filters, sort order, page and page size are stored in the page address, so you can bookmark or share a report view and refreshing keeps it.",
              ],
            },
          ],
        },
        {
          heading: "Exporting to CSV",
          blocks: [
            {
              ul: [
                "The file contains **every record that matches your applied filters** — not just the page on screen — sorted the way you sorted the table.",
                "It opens in Excel, Google Sheets and similar tools. Text that begins with `=`, `+`, `-` or `@` is given a leading apostrophe so a spreadsheet can't run it as a formula.",
                "An export is limited to 50,000 rows. If a report has more, narrow the filters and export again.",
                "Every export is recorded in the Audit log (action `export`, resource type `report`) with the report name, the filters used and the number of rows — never the data itself.",
              ],
            },
            { note: { kind: "info", text: "The Export buttons on the management pages (Users, Companies, …) are different: they save only the rows that page has loaded in your browser." } },
          ],
        },
        {
          heading: "What reports never contain",
          blocks: [{ p: "Phone numbers, addresses, bank details, government ID numbers, photos, passwords, access tokens and IP addresses are never included in any report or export. Audit reports show who did what and when, but not the before/after values." }],
        },
        {
          heading: "Good to know",
          blocks: [
            {
              ul: [
                "**Employees by Job Role** counts each employee's job-role field. The Employee form saves its **Job role** there, so employees saved from the form are counted under the role they were given; employees saved earlier may still show the default “Employee”.",
                "There is no “assets by assignee” report because assets don't record who holds them.",
                "Printing prints the report as shown — title, filters, time and the current page of results.",
              ],
            },
          ],
        },
      ],
      related: ["audit-log", "roles-permissions", "asset-filters", "troubleshooting-access"],
    },

    /* ===================== User and Employee Management ===================== */
    {
      id: "managing-users",
      category: "people",
      title: "Managing users and roles",
      summary: "For administrators: find users, change their role, unlock locked accounts and avoid removing the last admin.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "The Users page",
          blocks: [
            { p: "Users (administrators only) lists every account with its **Full name**, **Email**, **Role**, **Status** (Active or Locked), number of **Logins** and **Last login**. Use the search box to narrow the list and **Export** to download the rows shown." },
          ],
        },
        {
          heading: "Changing someone's role",
          blocks: [
            {
              ol: [
                "In the user's row, choose **admin**, **operator** or **read_only** in the role list.",
                "Press **Apply**.",
                "Confirm “Change this user's role to …?”.",
              ],
            },
            { p: "The change applies on that person's next request — they don't have to sign in again." },
            { note: { kind: "warning", text: "The last remaining administrator can't be demoted: you'll get “Cannot remove the last admin.”" } },
          ],
        },
        {
          heading: "Unlocking an account",
          blocks: [{ p: "After 5 failed sign-ins an account is locked for 15 minutes. A locked account shows **Locked** in the Status column with an **Unlock** button; confirm “Unlock this account?” to let the person try again straight away." }],
        },
        {
          heading: "How accounts are created",
          blocks: [{ p: "There is no “New user” button on the Users page. People create their own account on the **Register** tab of the sign-in screen, and it starts as **Read only**. An administrator then sets the right role here." }],
        },
      ],
      related: ["roles-permissions", "logging-in", "employee-records", "audit-log"],
    },

    {
      id: "employee-records",
      category: "people",
      title: "Creating and managing employee records",
      summary: "Add an employee, understand the status lifecycle, and use the View, Access, Edit and More actions.",
      updated: "2026-10-26",
      steps: [
        "Open **Employees** (administrators). Choose a **Company** in the filter, or leave **All companies**.",
        "Press **New employee**.",
        "Fill in the required fields (marked with an asterisk): **Company**, **First name**, **Last name** and **Email**.",
        "Add anything optional — Employee ID, Job role, Phone number, Photo, LinkedIn URL, Department, Address, Manager and Application access.",
        "Press **Create employee**.",
      ],
      sections: [
        {
          heading: "Rules to know",
          blocks: [
            {
              ul: [
                "An email can only be used once per company.",
                "An Employee ID, if you use one, is unique within a company.",
                "A phone number must be exactly 10 digits.",
                "**Job role** is picked from the Job Roles master (choose it on **Master Management**). Only active roles are offered, and an employee keeps their job role if it is deactivated later.",
                "You can't add an employee to an inactive company (“Cannot add an employee to an inactive company.”).",
                "The **Manager** must belong to the same company, and an assignment that would create a reporting loop is rejected.",
                "A photo can be a JPG, PNG, GIF or WEBP image. Files over the upload limit (5 MB by default) are rejected.",
              ],
            },
          ],
        },
        {
          heading: "Status lifecycle",
          blocks: [
            { p: "New employees start as **Onboarded**. The allowed moves are: Onboarded → Active, Active ⇄ On leave, and any of those → Exited. **Exited is final** — an exited employee can't change status again." },
            { p: "The **Include exited** checkbox shows or hides exited employees in the list." },
          ],
        },
        {
          heading: "The row actions",
          blocks: [
            {
              ul: [
                "**View** opens a read-only profile: contact details, work information (Employee ID, company, department, job role, manager) and account & access.",
                "**Access to** shows which applications the employee has been granted.",
                "**Edit** changes the record (not available once an employee has exited).",
                "**More** lets you **Change status**, link or manage the employee's **User account**, or **Delete employee**.",
              ],
            },
            { note: { kind: "warning", text: "**Delete employee** doesn't erase the record. It marks the employee Exited and, if they are linked to a user account, turns that login off. Use it when someone leaves." } },
          ],
        },
        {
          heading: "Linking an employee to a user account",
          blocks: [{ p: "Use **More → User account** to connect an employee to their login. The user must belong to the same company, and one user can be linked to only one employee." }],
        },
      ],
      related: ["departments-job-roles", "application-access", "managing-companies", "reports-guide"],
    },

    {
      id: "departments-job-roles",
      category: "people",
      title: "Understanding departments and job roles",
      summary: "The shared Department and Job Role lists, where to manage them, and how a job role differs from an access role.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "Departments",
          blocks: [
            { p: "**Departments** (administrators; choose it on **Master Management**) is a shared, company-wide master list — the same list for every company. Each department has a **Name**, an optional **Parent department** (so you can build a hierarchy), an optional **Manager** and a **Description**." },
            { p: "Use the **Level** filter to show only top-level departments, and **Include inactive** to see deactivated ones. Deactivating a department removes it from the Employee form's Department list without changing employees already assigned to it." },
          ],
        },
        {
          heading: "Job roles",
          blocks: [
            { p: "**Job Roles** (choose it on **Master Management**) is a shared list of job titles (for example “Software Engineer” or “CFO”). It fills the **Job role** dropdown on the Employee form: only active roles are offered, and a role you add, rename, deactivate or reactivate shows up there straight away. Deactivating one removes it from the dropdown without affecting employees already using it — their job role is kept. The master also shows how many current employees hold each role." },
          ],
        },
        {
          heading: "Two different things called “role”",
          blocks: [
            {
              table: {
                head: ["Term", "What it is", "Where you set it"],
                rows: [
                  ["Access role", "Admin, Operator or Read only — what you're allowed to do in Nexus One", "Users page"],
                  ["Job role", "An employee's job title — picked from the Job Roles list, or typed in under *Other*", "Employee form (the list itself is under Master Management → Job Roles)"],
                ],
              },
            },
            { note: { kind: "info", text: "The Employee form's **Job role** and **Department** dropdowns are filled from the Job Roles and Departments masters. Neither has anything to do with your access role." } },
          ],
        },
      ],
      related: ["employee-records", "roles-permissions", "reports-guide"],
    },

    {
      id: "application-access",
      category: "people",
      title: "Assigning application access to employees",
      summary: "Register applications in the Application Master and choose which employees have access to each.",
      updated: "2026-10-27",
      steps: [
        "Open **Applications** in the sidebar (administrators). Press **Add Application**, enter the **Application name** and a unique **Application code** (letters, digits, - and _; it is saved in capitals), optionally a **Category**, **Application URL** and **Description**, and create it.",
        "Find applications with the search box (name or code) and the **Status** and **Category** filters. Each row has **View**, **Edit**, **Access** and **Deactivate** / **Activate**.",
        "Press **Access** on a row to see who has the application, search them by name, email or employee ID, **Revoke** access (after a confirmation), or tick several employees and press **Give access**.",
        "You can also open an employee's details (the eye icon on **Employees**): the **Applications** section lists what they have, with dates, and administrators can give or revoke access there.",
        "The Employee form's **Application access** checkboxes still work for creating or editing an employee.",
      ],
      sections: [
        {
          heading: "Good to know",
          blocks: [
            {
              ul: [
                "The Application Master records who is meant to use an application. It does not sign anyone in to, or create accounts in, the application itself.",
                "Only administrators can add or edit applications and give or revoke access. Every grant, revoke and status change is written to the audit log.",
                "An inactive application can't be given to anyone new, and exited employees can't be given access.",
                "Deactivating an application never removes access that employees already have: it stays listed, marked inactive, until you revoke it, and reactivating the application restores it as it was.",
                "Access given before dates were recorded shows “Before tracking” instead of a date.",
                "The **Access to** button on an employee's row shows which applications they have.",
              ],
            },
          ],
        },
      ],
      related: ["employee-records", "departments-job-roles"],
    },

    /* ===================== Company Management ===================== */
    {
      id: "managing-companies",
      category: "companies",
      title: "Adding and editing companies",
      summary: "Create a company, edit it, and deactivate or reactivate it.",
      updated: "2026-10-26",
      steps: [
        "Open **Companies** (administrators) and press **New company**.",
        "Enter the required fields: **Name**, **Address** and **Contact email**. **Type** is *external* by default — choose *internal* for your own organisation. **Contact phone** is optional and must be exactly 10 digits.",
        "Press **Create company**.",
        "To change a company later, press **Edit** on its row, change the fields and press **Save changes**.",
      ],
      sections: [
        {
          heading: "Rules to know",
          blocks: [
            {
              ul: [
                "A company name must be unique.",
                "A company's **Type** is fixed once it exists — the Type field is locked while editing.",
                "Use the **Sort by** and **Type** controls to order or narrow the list, and **Export** to download the rows shown.",
              ],
            },
          ],
        },
        {
          heading: "Deactivating and reactivating",
          blocks: [
            { p: "Companies aren't deleted. **Deactivate** (confirm “Deactivate this company?”) marks the company Inactive; it stays in the list, still searchable, and **Reactivate** brings it back. An inactive company can't be edited, and no employee can be added to it until it is reactivated." },
          ],
        },
      ],
      related: ["company-records", "company-data", "employee-records"],
    },

    {
      id: "company-records",
      category: "companies",
      title: "Understanding company records",
      summary: "What a company record holds and how companies, users and employees relate.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "What's in a company record",
          blocks: [
            { ul: ["**Name** (unique)", "**Type** — internal or external", "**Address**, **Contact email** and **Contact phone**", "**Status** — Active or Inactive", "When it was added and last updated"] },
            { p: "Open **Reports → Company Directory** to see these together, with each company's current headcount." },
          ],
        },
        {
          heading: "How companies connect to everything else",
          blocks: [
            {
              ul: [
                "Every **employee** belongs to exactly one company.",
                "Every **user account** belongs to a company (it appears as *company ID* on your Overview page).",
                "Administrators can work across all companies. Operators and read-only users can only see their **own** company's company record and employees.",
                "Assets and suppliers are **not** tied to a company: they're one shared catalog.",
              ],
            },
          ],
        },
      ],
      related: ["managing-companies", "company-data", "roles-permissions"],
    },

    {
      id: "company-data",
      category: "companies",
      title: "Managing company-related data",
      summary: "Employees per company, what deactivation affects, and the company reports.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "Employees by company",
          blocks: [{ p: "On the Employees page, the **Company** filter lists one company's employees, or all of them. The Company Directory report shows each company's current headcount, and the Company-wise Employee Summary report breaks every company's employees down by status." }],
        },
        {
          heading: "What deactivating a company does",
          blocks: [
            { ul: ["The company is marked Inactive but its record and its employees remain.", "No new employee can be added to it, and an employee can't be moved into it.", "Reactivating it removes those limits."] },
          ],
        },
        {
          heading: "Company reports",
          blocks: [
            { ul: ["**Company Directory** — type, status, contacts and headcount.", "**Company-wise Employee Summary** — employees per company by status.", "**Company Status Summary** — active versus inactive, split by internal and external."] },
          ],
        },
      ],
      related: ["reports-guide", "managing-companies", "company-records"],
    },

    /* ===================== Assets and Suppliers ===================== */
    {
      id: "registering-assets",
      category: "assets-suppliers",
      title: "Registering and tracking assets",
      summary: "Create an asset record, understand its status flow, and use tags and attachments.",
      updated: "2026-10-26",
      steps: [
        "Open **Assets** (administrators) and press **New asset**.",
        "Enter an **Asset tag** and choose the **Supplier**. Only suppliers whose status is **approved** appear as valid choices.",
        "Choose the **Manufacturer** and **Model** from the lists, or pick *Other (type below)…* and type your own.",
        "Optionally add a **Serial number**, **Barcode**, **Purchase cost**, **Current value** and **Currency**.",
        "Press **Register asset**.",
      ],
      sections: [
        {
          heading: "Rules to know",
          blocks: [
            {
              ul: [
                "The **asset tag can't be changed** after the asset is created.",
                "A supplier that isn't approved is rejected: “This supplier is not approved and cannot be referenced by an asset.”",
                "Purchase cost and current value can't be negative.",
              ],
            },
          ],
        },
        {
          heading: "Status flow",
          blocks: [
            { p: "A new asset is **Registered**. It can move to **In repair**, then **Certified**, and between those two as needed (In repair ⇄ Certified). From any status it can be marked **Disposed**, which is final." },
          ],
        },
        {
          heading: "Tags, attachments and the timeline",
          blocks: [
            { p: "Open an asset's details to add **Tags** (up to 50 characters each), add **Attachments**, and read its **Timeline**." },
            { note: { kind: "info", text: "An attachment is a reference only — a URL or path plus an optional description. Nothing is uploaded or stored for assets in this version." } },
          ],
        },
      ],
      related: ["manufacturers-models", "managing-suppliers", "asset-filters", "reports-guide"],
    },

    {
      id: "manufacturers-models",
      category: "assets-suppliers",
      title: "Understanding manufacturers and models",
      summary: "The shared Manufacturer and Model lists that feed the Asset form.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "Two separate shared lists",
          blocks: [
            { p: "**Manufacturers** and **Models** (administrators; choose them on **Master Management**) are shared lists that fill the Manufacturer and Model dropdowns on the Asset form. Each entry has just a **Name**." },
            { note: { kind: "info", text: "The two lists are independent: choosing a manufacturer does not filter the models offered, and a model isn't linked to a manufacturer." } },
          ],
        },
        {
          heading: "Adding, searching and deactivating",
          blocks: [
            { ul: ["Press **New manufacturer** / **New model**, enter the name and create it.", "Use the search box, and **Include inactive** to see deactivated entries.", "Deactivating an entry removes it from the Asset form's dropdown but doesn't affect assets already registered under it."] },
          ],
        },
        {
          heading: "Reporting on them",
          blocks: [{ p: "The **Assets by Manufacturer** and **Assets by Model** reports count your assets by the manufacturer and model recorded on each asset." }],
        },
      ],
      related: ["registering-assets", "asset-filters", "reports-guide"],
    },

    {
      id: "managing-suppliers",
      category: "assets-suppliers",
      title: "Managing suppliers",
      summary: "Add suppliers, move them through onboarded, approved and suspended, and why approval matters for assets.",
      updated: "2026-10-26",
      steps: [
        "Open **Suppliers** (administrators) and press **New supplier**.",
        "Enter the **Name** (required). Optionally add a **Contact email**, a **Contact phone** (10 digits), a **Category**, **Terms** and a **Rating** from 0 to 5.",
        "Press **Create supplier**. New suppliers start as **onboarded**.",
        "When the supplier is cleared for use, change its status to **approved**.",
      ],
      sections: [
        {
          heading: "Status rules",
          blocks: [
            { p: "A supplier moves onboarded → approved, and then between **approved** and **suspended** as needed." },
            { note: { kind: "warning", text: "A supplier must be **approved** before an asset can reference it. Suspending a supplier takes it out of use for new assets." } },
          ],
        },
        {
          heading: "The dropdown lists",
          blocks: [
            { p: "**Category** and **Terms** are picked from the Supplier Categories and Payment Terms masters (on **Master Management**). *Other (type below)…* still lets you type a value that isn't on the list." },
          ],
        },
        {
          heading: "Finding suppliers",
          blocks: [{ p: "Use the search box and the **Status** filter (All, onboarded, approved, suspended), and **Export** to download the rows shown. The **Supplier Directory**, **Suppliers by Category** and **Supplier Status Report** reports cover suppliers across the whole catalog." }],
        },
      ],
      related: ["registering-assets", "reports-guide", "roles-permissions"],
    },

    {
      id: "asset-filters",
      category: "assets-suppliers",
      title: "Using asset filters and search",
      summary: "Find assets on the Assets page, and use the Asset reports for more filters.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "On the Assets page",
          blocks: [
            {
              ul: [
                "**Status** filter — All, registered, in_repair, certified or disposed.",
                "**Search** — matches an asset's tag, manufacturer, model, serial number and its tags.",
                "**Export** — downloads the rows currently shown as CSV.",
              ],
            },
          ],
        },
        {
          heading: "In Reports",
          blocks: [
            { p: "**Asset Inventory** adds Manufacturer and Model filters and a registration date range, sorts by any column, pages through large results and exports everything that matches. **Assets by Manufacturer**, **Assets by Model** and **Assets by Status** give counts." },
            { note: { kind: "tip", text: "Amounts are shown in each asset's own currency and are not added together." } },
          ],
        },
      ],
      related: ["registering-assets", "manufacturers-models", "reports-guide"],
    },

    /* ===================== Security and Administration ===================== */
    {
      id: "roles-permissions",
      category: "security",
      title: "Understanding roles and permissions",
      summary: "What Admin, Operator and Read only can do, and how company limits apply.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "The three roles",
          blocks: [
            { ul: ["**Admin** — can do everything, across every company.", "**Operator** — can view and edit most business data, but only within their own company for companies and employees.", "**Read only** — can view company, supplier, asset and shared-list data, and nothing else."] },
            { p: "New accounts start as Read only; administrators change roles on the Users page." },
          ],
        },
        {
          heading: "What each role can do",
          blocks: [
            {
              table: {
                head: ["Data", "Admin", "Operator", "Read only"],
                rows: [
                  ["Companies", "View, add, edit, deactivate", "View, add, edit (own company)", "View (own company)"],
                  ["Employees", "Everything, including delete and linking users", "View, add, edit (own company)", "No access"],
                  ["Suppliers", "View, add, edit", "View, add, edit", "View"],
                  ["Assets", "View, add, edit, delete", "View, add, edit", "View"],
                  ["Departments, Job roles, Applications, Manufacturers, Models", "View and edit", "View", "View"],
                  ["Audit log and Events", "View", "No access", "No access"],
                  ["Reports", "All reports", "Employee, Company, Asset, Supplier", "Company, Asset, Supplier"],
                ],
              },
            },
          ],
        },
        {
          heading: "Company limits",
          blocks: [
            { p: "Administrators work across all companies. Operators and read-only users are limited to their own company for **company** and **employee** data: asking for another company's record gets the same “not found” as a record that doesn't exist. Suppliers and assets are one shared catalog, so they aren't limited by company." },
          ],
        },
        {
          heading: "The web app versus the API",
          blocks: [
            { p: "In the web app only administrators see the management pages. The permissions above are enforced by the server on every request, so they also apply to operators and read-only users who call the API directly (for example from another module). Refused requests are recorded in the audit log." },
          ],
        },
      ],
      related: ["managing-users", "audit-log", "troubleshooting-access", "reports-guide"],
    },

    {
      id: "master-management",
      category: "security",
      title: "Using Master Management",
      summary: "For administrators: manage every master list from one page — choose a master from the dropdown, then add, edit, deactivate or reactivate its values.",
      updated: "2026-10-26",
      steps: [
        "Open **Master Management** (administrators) in the sidebar.",
        "Use the **Master** dropdown to choose the master you want. Only that master's content is shown below it.",
        "To add a value, press the **New …** button, enter the **Name** (and an optional description) and create it.",
        "To change one, press **Edit** on its row. To stop it being offered, press **Deactivate**; **Reactivate** brings it back.",
      ],
      sections: [
        {
          heading: "The masters in the dropdown",
          blocks: [
            {
              table: {
                head: ["Group", "Masters", "Where the values appear"],
                rows: [
                  ["People", "Departments, Job Roles, Applications, Application Categories", "Employee form → Department, Job role, Application access; Application form → Category"],
                  ["Assets", "Manufacturers, Models", "Asset form → Manufacturer, Model"],
                  ["Suppliers", "Supplier Categories, Payment Terms", "Supplier form → Category, Terms"],
                ],
              },
            },
            { p: "Under the dropdown a line tells you what the chosen master is for, where it is used, and how many of its values are active." },
          ],
        },
        {
          heading: "Two kinds of master, one page",
          blocks: [
            { p: "**Departments, Job Roles, Applications, Manufacturers and Models** have their own fields (for example a department's parent and manager), so they keep their own tables and controls — Master Management shows them as they are, including their *Include inactive* switch and Export button." },
            { p: "**Application Categories, Supplier Categories and Payment Terms** are simple lists of names. They have a search box, a **Status** filter (Active, Inactive or All), sorting by name, and paging; the page address keeps your choices, so a refresh or shared link shows the same view." },
          ],
        },
        {
          heading: "Rules for the simple lists",
          blocks: [
            {
              ul: [
                "A name must be unique within its list, ignoring capital letters.",
                "A value's **name can't be changed once records use it** — the table shows how many do. Deactivate it and add a new value instead.",
                "**Deactivate** stops a value being offered in the dropdowns. Records that already have it keep it, and nothing is deleted.",
                "Changes appear in the form dropdowns straight away.",
                "Every add, edit, deactivation and reactivation is recorded in the Audit log with resource type `master_item`.",
              ],
            },
          ],
        },
        {
          heading: "Who can use it",
          blocks: [
            { p: "Only administrators see the page and can change masters. Operators and read-only users never edit them; they simply pick from the dropdowns on the forms they can use. The **Master Management reports** (linked from the page, and listed on the Reports page) can be run by every role, except the change history, which is for administrators." },
          ],
        },
      ],
      related: ["departments-job-roles", "application-access", "manufacturers-models", "managing-suppliers", "reports-guide", "audit-log"],
    },

    {
      id: "audit-log",
      category: "security",
      title: "Using the audit log",
      summary: "For administrators: what the audit log records and how to filter it.",
      updated: "2026-10-26",
      steps: [
        "Open **Audit log** (administrators). Press **Filters** to show the filter panel.",
        "Narrow by **Resource type**, **Action**, **Resource id** and/or **User id**.",
        "Press **Search**. **Clear filters** resets the panel.",
        "Press **Export** to download the rows shown.",
      ],
      sections: [
        {
          heading: "What it records",
          blocks: [
            { p: "Every important event is recorded automatically: records created, updated or deleted, status changes, role changes, account links, sign-ins (successes and failures), refused requests (**access_denied**), and report exports (**export**)." },
            { p: "Each entry shows who did what to which resource, when, and — where relevant — the old and new values." },
          ],
        },
        {
          heading: "Good to know",
          blocks: [
            {
              ul: [
                "The audit log is **read-only**. Nothing in the app lets anyone edit or remove an entry.",
                "Sensitive values (emails, phone numbers, bank, PAN and Aadhaar numbers) are masked in the old/new snapshots, even for administrators; passwords are redacted entirely.",
                "For totals instead of individual entries, use the **Security & Audit** reports: Audit Activity, User Activity, Authentication & Sessions and Administrative Changes.",
              ],
            },
          ],
        },
      ],
      related: ["sessions-events", "reports-guide", "roles-permissions"],
    },

    {
      id: "sessions-events",
      category: "security",
      title: "Understanding sessions and events",
      summary: "What the Sessions page lists and what the Events page is for.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "Sessions",
          blocks: [
            { p: "Every sign-in creates a session. The **Sessions** page lists yours, with each one's ID, when it was created and expires, when it was last used, the IP address it came from and whether it is **Active** or **Revoked**." },
            {
              ul: [
                "Refreshing your access token **rotates** the session: the old one is revoked and a new one takes its place.",
                "Logging out revokes the session and puts its access token on a block list, so the token stops working immediately.",
                "**Logout all sessions** (Overview) revokes every session on your account.",
              ],
            },
          ],
        },
        {
          heading: "Events",
          blocks: [
            { p: "The **Events** page (administrators) is a stream of everything that happens, one event for every audit-log entry. You can filter by **Resource type**, **Event type**, **Resource id** and **Company id**." },
            { note: { kind: "info", text: "Nothing consumes this stream yet — no workflow engine is connected. It is a durable record that other tools can read later." } },
          ],
        },
      ],
      related: ["audit-log", "logging-in", "troubleshooting-access"],
    },

    {
      id: "troubleshooting-access",
      category: "security",
      title: "Troubleshooting access problems",
      summary: "What common messages mean and what to do about them.",
      updated: "2026-10-26",
      sections: [
        {
          heading: "Messages and what to do",
          blocks: [
            {
              table: {
                head: ["You see", "What it means", "What to do"],
                rows: [
                  ["Invalid email or password.", "The email or password doesn't match, or the account is inactive or locked.", "Check both carefully. After 5 failed attempts the account locks for 15 minutes; an administrator can unlock it."],
                  ["Too many requests. Please try again shortly.", "Too many sign-in or register attempts from one address in a minute.", "Wait a minute, then try again."],
                  ["Access token has expired.", "Your 15-minute access token has run out.", "Press Refresh access token on the Overview page, or log in again."],
                  ["Access token has been revoked.", "You logged out, or someone used Logout all sessions.", "Log in again."],
                  ["Missing or invalid Authorization header. / Invalid access token.", "Your session is no longer valid.", "Log in again."],
                  ["You do not have permission to access this resource.", "Your role isn't allowed to do that.", "See Understanding roles and permissions; ask an administrator if you need access."],
                  ["Cannot add an employee to an inactive company.", "The company has been deactivated.", "Ask an administrator to reactivate the company."],
                  ["This supplier is not approved and cannot be referenced by an asset.", "The chosen supplier is onboarded or suspended.", "Approve the supplier first, or choose another."],
                ],
              },
            },
          ],
        },
        {
          heading: "A page is missing from my sidebar",
          blocks: [{ p: "Operators and read-only users see only Overview, Reports, Sessions and Help Center; the management pages are for administrators." }],
        },
        {
          heading: "A report I expected isn't listed",
          blocks: [{ p: "Reports follow your role. Employee reports aren't available to read-only users, and Security & Audit reports are for administrators only." }],
        },
        {
          heading: "Still stuck?",
          blocks: [
            { p: "Nexus One has no built-in support-ticket or contact form. Contact your Nexus Auth administrator — the person who manages accounts and roles for your organisation — and tell them what you were doing, the exact message you saw, and roughly when. Administrators can look for matching sign-ins, refused requests and changes in the Audit log." },
          ],
        },
      ],
      related: ["logging-in", "roles-permissions", "audit-log"],
    },
  ],

  faqs: [
    /* Login and access */
    {
      id: "faq-cant-login",
      topic: "login-access",
      question: "I can't log in. What should I check?",
      answer: [
        "The message “Invalid email or password.” is used for every sign-in failure — wrong email, wrong password, inactive account or locked account — so it can't tell you which one.",
        "After 5 failed attempts an account is locked for 15 minutes. Wait, or ask an administrator to unlock it on the Users page.",
      ],
      article: "logging-in",
    },
    {
      id: "faq-signed-out",
      topic: "login-access",
      question: "Why was I signed out?",
      answer: [
        "Access tokens last 15 minutes, closing the browser tab ends the session, and **Logout all sessions** signs out every browser. Press **Refresh access token** on the Overview page before your token runs out to stay signed in; otherwise log in again.",
      ],
      article: "logging-in",
    },
    {
      id: "faq-missing-pages",
      topic: "login-access",
      question: "Why don't I see Users, Companies or Employees in the sidebar?",
      answer: ["Those management pages are shown to administrators only. Operators and read-only users see Overview, Reports, Sessions and the Help Center."],
      article: "navigating-the-app",
    },
    {
      id: "faq-password",
      topic: "login-access",
      question: "Can I reset or change my password?",
      answer: [
        "Yes, you can change it: open **Settings → Password** and enter your current password and the new one twice. You are then signed out everywhere and sign in again with the new password. There is no “forgot password” screen.",
      ],
      article: "logging-in",
    },
    {
      id: "faq-new-role",
      topic: "login-access",
      question: "What access does a new account get?",
      answer: ["**Read only**. An administrator can change the role on the Users page."],
      article: "managing-users",
    },

    /* Users and employees */
    {
      id: "faq-job-vs-access",
      topic: "people",
      question: "What's the difference between a job role and a user role?",
      answer: [
        "A **user (access) role** — Admin, Operator or Read only — controls what you can do in Nexus One. A **job role** is an employee's job title, picked on the Employee form from the shared Job Roles list. It has nothing to do with your access role.",
      ],
      article: "departments-job-roles",
    },
    {
      id: "faq-delete-employee",
      topic: "people",
      question: "What does “Delete employee” do?",
      answer: ["It doesn't erase the record. It marks the employee **Exited** and, if they're linked to a user account, turns that login off."],
      article: "employee-records",
    },
    {
      id: "faq-status",
      topic: "people",
      question: "Why can't I move an employee to a particular status?",
      answer: ["Only some moves are allowed: Onboarded → Active, Active ⇄ On leave, and any of those → Exited. Exited is final."],
      article: "employee-records",
    },
    {
      id: "faq-photo",
      topic: "people",
      question: "Can I upload an employee photo?",
      answer: ["Yes, on the Employee form. JPG, PNG, GIF and WEBP images are accepted; files over the upload limit (5 MB by default) are rejected."],
      article: "employee-records",
    },

    /* Company records */
    {
      id: "faq-delete-company",
      topic: "companies",
      question: "Can I delete a company?",
      answer: ["No — companies are deactivated, not deleted. An inactive company stays in the list and can be reactivated."],
      article: "managing-companies",
    },
    {
      id: "faq-company-type",
      topic: "companies",
      question: "Why can't I change a company's type?",
      answer: ["A company's Type (internal or external) is fixed when it's created; the field is locked while editing."],
      article: "managing-companies",
    },
    {
      id: "faq-inactive-company",
      topic: "companies",
      question: "Why can't I add an employee to a company?",
      answer: ["If you see “Cannot add an employee to an inactive company.”, the company has been deactivated. Reactivate it first."],
      article: "company-data",
    },

    /* Assets and suppliers */
    {
      id: "faq-supplier-approved",
      topic: "assets-suppliers",
      question: "Why can't I register an asset for a supplier?",
      answer: ["Assets can only reference **approved** suppliers. Approve the supplier first (onboarded → approved)."],
      article: "managing-suppliers",
    },
    {
      id: "faq-asset-tag",
      topic: "assets-suppliers",
      question: "Can I change an asset tag?",
      answer: ["No. The asset tag is fixed once the asset is created."],
      article: "registering-assets",
    },
    {
      id: "faq-asset-file",
      topic: "assets-suppliers",
      question: "Can I attach a file to an asset?",
      answer: ["Not yet. An attachment is a reference (a URL or path and an optional description) — files aren't uploaded or stored for assets in this version."],
      article: "registering-assets",
    },
    {
      id: "faq-missing-manufacturer",
      topic: "assets-suppliers",
      question: "My manufacturer or model isn't in the dropdown.",
      answer: ["The dropdowns come from the shared Manufacturers and Models lists, which administrators maintain. On the Asset form you can also choose “Other (type below)…” and type it."],
      article: "manufacturers-models",
    },

    /* Reports and exports */
    {
      id: "faq-missing-reports",
      topic: "reports-exports",
      question: "Why don't I see some reports?",
      answer: ["Reports follow your role. Employee reports aren't available to read-only users, and Security & Audit reports are for administrators only."],
      article: "reports-guide",
    },
    {
      id: "faq-export-scope",
      topic: "reports-exports",
      question: "Does Export CSV include every row or just the page I'm on?",
      answer: ["Every record that matches your applied filters, sorted as shown — up to 50,000 rows. The Export buttons on management pages are different: they save only the rows that page has loaded."],
      article: "reports-guide",
    },
    {
      id: "faq-export-sensitive",
      topic: "reports-exports",
      question: "Do reports include sensitive personal details?",
      answer: ["No. Phone numbers, addresses, bank details, government IDs, photos, passwords and IP addresses are never included. Exports are recorded in the Audit log, without the data."],
      article: "reports-guide",
    },
    {
      id: "faq-card-numbers",
      topic: "reports-exports",
      question: "Where do the numbers on the Reports cards come from?",
      answer: ["They're calculated live from the database, and each card links to the report behind it with the same filters, so the totals match."],
      article: "reports-guide",
    },

    /* Master management */
    {
      id: "faq-master-missing-value",
      topic: "master-data",
      question: "A job role, category or payment term I need isn't in the dropdown.",
      answer: ["Those dropdowns list the active values of the matching master. Ask an administrator to add it (or reactivate it) on **Master Management**; it appears in the dropdown straight away."],
      article: "master-management",
    },
    {
      id: "faq-master-rename",
      topic: "master-data",
      question: "Why can't I rename a Supplier Category, Payment Term or Application Category?",
      answer: ["Records store the value by name, so once any record uses it the name is locked — the table shows how many do. Deactivate the old value and add a new one instead."],
      article: "master-management",
    },
    {
      id: "faq-master-delete",
      topic: "master-data",
      question: "Can I delete a master value?",
      answer: ["Values are deactivated, not deleted. A deactivated value disappears from dropdowns but stays on the records that already use it, and you can reactivate it later."],
      article: "master-management",
    },

    /* Common errors */
    {
      id: "faq-no-permission",
      topic: "errors",
      question: "“You do not have permission to access this resource.”",
      answer: ["Your role isn't allowed to do that. Ask an administrator if you need access. The refusal is recorded in the audit log."],
      article: "roles-permissions",
    },
    {
      id: "faq-too-many",
      topic: "errors",
      question: "“Too many requests. Please try again shortly.”",
      answer: ["You made too many sign-in (or register) attempts from one address in a minute. Wait a minute and try again."],
      article: "troubleshooting-access",
    },
    {
      id: "faq-expired",
      topic: "errors",
      question: "“Access token has expired.”",
      answer: ["Your 15-minute access token ran out. Press **Refresh access token** on the Overview page, or log in again."],
      article: "troubleshooting-access",
    },
  ],
};
