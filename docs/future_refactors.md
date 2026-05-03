# Future Refactors

A running list of refactors that are scoped, low-risk, and worth picking up
between feature work. Each entry should describe **what**, **why**, and the
**call sites** so a future contributor can pick one off and ship it without
re-deriving the context.

---

## Migrate ad-hoc inline error blocks onto the `Callout` primitive

The SIGNAL design language now defines a `Callout` primitive
(`server/ui/src/components/primitives/Callout.jsx`) for inline, panel-level
status messages. Three pre-existing call sites still hand-roll an inline
"error block" with their own CSS. Each was the right shape at the time but
none share visual treatment, padding, or tone-handling.

Migrate them one at a time. Each migration is independent and small.

### Call sites

1. **`ProfileBuilder.errorPanel`** —
   `server/ui/src/components/ProfileBuilder.jsx` (`saveError` rendering near
   the Identity section, plus the `.errorPanel` / `.errorTitle` classes in
   `ProfileBuilder.module.css`). Currently surfaces the
   `default_agent_cannot_be_disabled` save error. Should become a `tone="danger"`
   Callout sitting in the same slot.

2. **`AddIntegrationModal.errorBox`** —
   `server/ui/src/components/integrations/AddIntegrationModal.module.css`
   defines `.errorBox` (left rail + danger-muted background) used by the form
   to surface auth/credential validation failures. Replace with a `tone="danger"`
   Callout. Drop the bespoke CSS.

3. **`GoalsView.errorBanner`** —
   `server/ui/src/components/goals/GoalsView.module.css` defines
   `.errorBanner` (a sticky-top danger band) used when `setError(err.message)`
   trips. Replace with a `tone="danger"` Callout placed in the same flow
   position. Sticky positioning is no longer needed if the Callout is rendered
   above the scroll container.

### Why

- Three near-identical patterns, three different CSS modules. A change to
  the agreed-upon error visual today touches three files and risks visual
  drift.
- The `Callout` primitive already handles tones, dismissal, structured
  bodies (`Callout.List` / `Callout.Footnote`), and animation. Hand-rolled
  versions don't.
- Consolidating gives the codebase one canonical "show an inline error"
  primitive — newcomers stop inventing variant #4.

### Out of scope

Don't fold Toast usage into Callout — they're separate primitives by design
(transient floating vs. anchored persistent). See `docs/design/design_language.html`
§11 Feedback for the split.

---
