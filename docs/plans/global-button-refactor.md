# Refactor: Scope global button styles to `.btn` class

## Problem

The global `button` reset in `global.css` applies opinionated styles to every `<button>` element:

```css
button {
  background: var(--muted);
  border-radius: var(--radius);
  padding: 0.5rem 1rem;
  box-shadow: var(--shadow);
  /* ... */
}
```

This breaks any small utility button (icon buttons, tabs, toggle buttons, toolbar actions) because they inherit background, padding, box-shadow, and border-radius that they then have to individually override. Every new component with buttons needs `padding: 0; box-shadow: none; background: transparent;` to undo the global style.

## Affected components

Buttons that currently override the global style with `box-shadow: none`, `padding: 0`, etc:
- `PreviewPanel.module.css` — `.tab`, `.actionBtn`
- `FilePreviewInline.module.css` — `.toolbarBtn`, `.toggleBtn`
- `FullscreenPreview.module.css` — `.toggleBtn`, `.headerBtn`
- `DesktopPreview.module.css` — `.controlBtn`, `.expandBtn`
- `TerminalOutput.module.css` — `.closeBtn`, `.collapseBtn`
- `PreviewShell.module.css` — close/expand buttons
- `Message.module.css` — `.fileOutputBtn`

## Proposed change

1. Strip the global `button` rule down to a minimal reset:

```css
button {
  background: none;
  border: none;
  padding: 0;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
```

2. Move the opinionated styles into a `.btn` class:

```css
.btn {
  background: var(--muted);
  border-radius: var(--radius);
  color: var(--text);
  border: 1px solid transparent;
  padding: 0.5rem 1rem;
  box-shadow: var(--shadow);
  transition: background-color 160ms ease, box-shadow 160ms ease, transform 60ms ease;
}
```

3. Add `className="btn"` to every button that currently relies on the global style (buttons without a CSS Module class).

4. Remove the now-unnecessary `box-shadow: none; padding: 0;` overrides from all the CSS Modules listed above.

## Risk

Buttons without any `className` that rely on the global style will lose their styling. Need to audit all `<button>` elements without `className` and add `.btn` to them.
