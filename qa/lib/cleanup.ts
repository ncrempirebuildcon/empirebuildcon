/**
 * Cleanup in a `finally` that never hides the test's own failure (task 5.8). If the test body
 * failed and the cleanup fails too, the cleanup error is logged and the body's error stands; if
 * the body passed, a failing cleanup fails the test.
 *
 *   let failed = true;
 *   try { …; failed = false; } finally { await cleanup(failed, async () => { … }); }
 */
export async function cleanup(failed: boolean, step: () => Promise<void>): Promise<void> {
  try {
    await step();
  } catch (error) {
    if (!failed) throw error;
    console.warn(`Cleanup failed after the test had already failed: ${String(error)}`);
  }
}
