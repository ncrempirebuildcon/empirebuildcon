/** CMS addresses used in more than one place, so a rename happens once. */
export const SIGN_IN_PATH = "/admin/login";
export const PROJECTS_PATH = "/admin/projects";
export const CATALOGUE_PATH = "/admin/catalogue";
export const MEDIA_PATH = "/admin/media";
export const LEADS_PATH = "/admin/leads";
export const SITE_VISITS_PATH = "/admin/site-visits";
export const UTM_REPORT_PATH = "/admin/reports/utm";

/** The editor for one project. */
export const projectPath = (id: string) => `${PROJECTS_PATH}/${id}`;

/** The detail page of one lead. */
export const leadPath = (id: string) => `${LEADS_PATH}/${id}`;

/**
 * True for an address inside the CMS ("/admin…"), the only kind of link the dashboard follows
 * from API data (counts and tasks carry their own `link`).
 * SECURITY: a link from the API is never used as-is unless it stays on this site's CMS, so a bad
 * value can't turn a dashboard tile into an open redirect or a `javascript:` URL.
 */
export function isCmsPath(link: string): boolean {
  return /^\/admin(?:[/?#]|$)/.test(link) && !link.startsWith("//");
}

// CMS screens that exist today. WHY: the API's dashboard tasks may point at screens that arrive
// in later parts (e.g. /admin/settings in part 5); those tasks are shown without a link rather
// than leading to a "page not found".
// TODO(phase-4): add /admin/settings, /admin/pages, /admin/users and /admin/audit with parts 4–5.
const BUILT_SCREENS = [
  "/admin/leads",
  "/admin/site-visits",
  "/admin/reports/utm",
  PROJECTS_PATH,
  CATALOGUE_PATH,
  MEDIA_PATH,
];

/** True for a CMS link to a screen that exists in this version of the CMS (see BUILT_SCREENS). */
export function isBuiltCmsPath(link: string): boolean {
  if (!isCmsPath(link)) return false;
  const path = link.split(/[?#]/)[0] ?? "";
  return (
    path === "/admin" ||
    BUILT_SCREENS.some((screen) => path === screen || path.startsWith(`${screen}/`))
  );
}
