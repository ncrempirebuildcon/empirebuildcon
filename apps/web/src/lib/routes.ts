/** CMS addresses used in more than one place, so a rename happens once. */
export const SIGN_IN_PATH = "/admin/login";
export const PROJECTS_PATH = "/admin/projects";
export const CATALOGUE_PATH = "/admin/catalogue";
export const MEDIA_PATH = "/admin/media";
export const LEADS_PATH = "/admin/leads";
export const SITE_VISITS_PATH = "/admin/site-visits";
export const UTM_REPORT_PATH = "/admin/reports/utm";
export const PAGES_PATH = "/admin/pages";
export const POSTS_PATH = "/admin/posts";
export const OFFERS_PATH = "/admin/offers";
export const FAQS_PATH = "/admin/faqs";
export const TESTIMONIALS_PATH = "/admin/testimonials";
export const REDIRECTS_PATH = "/admin/redirects";

/** The editor for one project. */
export const projectPath = (id: string) => `${PROJECTS_PATH}/${id}`;

/** The detail page of one lead. */
export const leadPath = (id: string) => `${LEADS_PATH}/${id}`;

/** The editor for one page. */
export const pagePath = (id: string) => `${PAGES_PATH}/${id}`;

/** The editor for one blog post. */
export const postPath = (id: string) => `${POSTS_PATH}/${id}`;

/**
 * The "Offers & blog" sections (board NoirCmsContent's tabs, plus Redirects), in menu order, with
 * the permission each one needs (ARCHITECTURE.md §11). The menu item opens the first section the
 * role can use, and every section shows the same sub-navigation.
 * SECURITY: hiding a section is a convenience; the API checks the permission on every call.
 */
export const CONTENT_SECTIONS = [
  { id: "offers", label: "Offers", href: OFFERS_PATH, permission: "offers.manage" },
  { id: "posts", label: "Blog posts", href: POSTS_PATH, permission: "content.read" },
  { id: "faqs", label: "FAQs", href: FAQS_PATH, permission: "content.read" },
  {
    id: "testimonials",
    label: "Testimonials",
    href: TESTIMONIALS_PATH,
    permission: "content.read",
  },
  { id: "redirects", label: "Redirects", href: REDIRECTS_PATH, permission: "seo.manage" },
] as const;

export type ContentSectionId = (typeof CONTENT_SECTIONS)[number]["id"];

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
// TODO(phase-4): add /admin/settings, /admin/users and /admin/audit with part 5.
const BUILT_SCREENS = [
  "/admin/leads",
  "/admin/site-visits",
  "/admin/reports/utm",
  PROJECTS_PATH,
  CATALOGUE_PATH,
  MEDIA_PATH,
  PAGES_PATH,
  POSTS_PATH,
  OFFERS_PATH,
  FAQS_PATH,
  TESTIMONIALS_PATH,
  REDIRECTS_PATH,
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
