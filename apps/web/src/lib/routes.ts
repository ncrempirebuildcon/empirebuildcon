/** CMS addresses used in more than one place, so a rename happens once. */
export const SIGN_IN_PATH = "/admin/login";
export const PROJECTS_PATH = "/admin/projects";
export const CATALOGUE_PATH = "/admin/catalogue";

/** The editor for one project. */
export const projectPath = (id: string) => `${PROJECTS_PATH}/${id}`;
