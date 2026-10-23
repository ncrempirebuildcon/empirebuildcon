// Signs the throwaway super-admin and the throwaway sales user in once each and saves their
// sessions for the CMS specs (playwright.config.ts "setup" project; lib/auth.ts explains why only
// once). Together with login.spec.ts a run uses 4 of the API's 10 sign-ins per 15 minutes.
import { test as setup } from "@playwright/test";
import { CMS_STATE, SALES_STATE, salesUser, signIn } from "../lib/auth";

setup("sign in once for the CMS journeys", async ({ page }) => {
  await signIn(page);
  await page.context().storageState({ path: CMS_STATE });
});

setup("sign the sales user in once for the own-leads journey", async ({ page }) => {
  await signIn(page, salesUser());
  await page.context().storageState({ path: SALES_STATE });
});
