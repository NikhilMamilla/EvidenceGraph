/**
 * Shared, localStorage-backed store for the evaluator checklist's progress.
 *
 * This is intentionally NOT React state lifted into a context. The checklist
 * lives in one tab (EvaluatorGuide) but the actions that actually satisfy a
 * step happen in completely different tabs (AI Verify, Defense Eval,
 * Payments, Operations) that mount and unmount independently. A plain module
 * with synchronous reads/writes is the simplest thing that lets any of those
 * components report "this specific, real thing happened" without prop
 * drilling a callback through the whole app.
 *
 * Every call site here should correspond to something that actually
 * happened — a fetch that resolved with real data, a specific case that was
 * actually run — never "the user clicked a button that merely navigates."
 * Marking a step done for navigating alone would mean the checklist can lie
 * about what the evaluator has actually seen, which is exactly the kind of
 * fabrication this project's own evidence engine refuses to do.
 */

const STORAGE_KEY = 'eg:evaluator-checklist:v1'

export function readGuideProgress(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function setGuideStep(id: string, value: boolean): void {
  try {
    const current = readGuideProgress()
    if (current[id] === value) return
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...current, [id]: value }))
  } catch {
    /* private mode — fine, just don't persist */
  }
}

export function markGuideStepDone(id: string): void {
  setGuideStep(id, true)
}

export function resetGuideProgress(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({}))
  } catch {
    /* private mode — fine, just don't persist */
  }
}

/**
 * Which step's "Go to tab" button was last clicked. Read on landing back on
 * the checklist tab, to scroll straight to that specific step instead of
 * just the top of the list — so "open Operations, check it, come back"
 * returns you to step 1 exactly, and "open AI Verify, come back" (from step
 * 2 or step 3) returns you to whichever of those you left from. Not cleared
 * after reading — revisiting the checklist keeps landing on the same step
 * until a different step's button is clicked, which is the expected
 * "resume where I left off" behaviour. sessionStorage because this is
 * navigation state for the current visit, not progress worth remembering
 * across a new session.
 */
const LAST_STEP_KEY = 'eg:evaluator-checklist:last-step'

export function setLastVisitedStep(id: string): void {
  try {
    sessionStorage.setItem(LAST_STEP_KEY, id)
  } catch {
    /* private mode — fine, this is a nice-to-have */
  }
}

export function getLastVisitedStep(): string | null {
  try {
    return sessionStorage.getItem(LAST_STEP_KEY)
  } catch {
    return null
  }
}
