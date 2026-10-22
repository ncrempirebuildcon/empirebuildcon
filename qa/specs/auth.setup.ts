// Signs the throwaway super-admin in once and saves the session for the CMS specs
// (playwright.config.ts "setup" project; lib/auth.ts explains why only once).
import { test as setup } from "@playwright/test";
import { CMS_STATE, signIn } from "../lib/auth";

setup("sign in once for the CMS journeys", async ({ page }) => {
  await signIn(page);
  await page.context().storageState({ path: CMS_STATE });
});
