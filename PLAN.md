# Media Viewer — Improvement Plan

## Bug Fixes (High Priority)

### 1. Rating doesn't save/work consistently
- **Root cause**: The viewer fetches `/api/all-media` which returns indices into `MEDIA_FILES` (the *filtered* list). But after a word-cloud filter, `MEDIA_FILES` is a subset of `CORPUS`. If you navigate then rate, the index sent to `/api/set-rating` may point at the wrong `MediaFile` — or be out of bounds — depending on filter state. Additionally, rating and then immediately calling `navigate(1)` races against the POST response.
- **Fix**: Use a stable file identifier (e.g. the md5 hash) instead of a positional index for `set-rating`. Validate the id server-side against `CORPUS`, not `MEDIA_FILES`.

### 2. Word cloud only lets you select one word
- **Root cause**: `filterByWord(word)` does a single substring match (`word_lower in mf.path.lower()`) then immediately redirects to the gallery. There's no way to build up an AND/OR of multiple words.
- **Fix**: Keep a set of selected words client-side. Toggle words on/off (highlight selected tags). Send all selected words to a new `/api/filter` endpoint that supports a list. Apply AND logic (file path must contain *all* selected words). Add a visible "Apply Filter" button instead of auto-redirecting on click.

### 3. Filter state is lost on navigation
- Filtering is server-side global state (`MEDIA_FILES` global). If two browsers are open, they share (and clobber) the same filter. Going back to gallery after viewing loses awareness of what filter is active.
- **Fix**: Move filter state into URL query parameters (e.g. `/?words=foo,bar&ratings=0,1`) so it's bookmarkable and per-client. Apply filtering at render time rather than mutating a global list.

## Architectural Improvements

### 4. Replace `http.server` with Flask (or similar)
- The hand-rolled `BaseHTTPRequestHandler` with manual URL dispatch, manual template substitution, and manual JSON serialization is fragile and hard to extend.
- Flask (already a one-line pip install) gives you proper routing, Jinja2 templating, JSON helpers, static file serving, and request parsing for free. The entire handler could shrink by half.

### 5. Use a proper templating engine
- Currently doing `template.replace('{{PAGE}}', ...)` — no escaping, no conditionals, no loops.
- With Jinja2 (comes with Flask) or even a minimal template library, the templates become much more maintainable and XSS-safe.

### 6. Persistent state — use SQLite instead of flat files
- `ratings.txt` is a flat file re-written in full on every rating change. Under concurrent access this can corrupt.
- A small SQLite DB (`mediaviewer.db`) in `.mediaviewer/` would give atomic writes, easy querying (e.g. "all files rated >= 2"), and extensibility (tags, notes, view history).

### 7. Thread safety
- The server uses `HTTPServer` (single-threaded by default) but also uses global mutable state (`MEDIA_FILES`, `RATINGS`, `WORD_COUNTS`). If switched to `ThreadingHTTPServer` (or Flask), every mutable global needs a lock.
- **Fix**: Either use `ThreadingHTTPServer` with proper locking, or move to Flask with a DB backend.

## Feature Polish

### 8. Show current rating in the viewer
- The rating buttons (0–3) are displayed but there's no visual indication of the *current* rating for the file being viewed. Highlight the active rating button.

### 9. Gallery thumbnails should show rating
- A small badge/star on each thumbnail so you can see at a glance what's rated.

### 10. Keyboard shortcut help overlay
- The viewer supports arrow keys, Escape, and 0–3 for rating, but there's no on-screen hint. Add a small `?` button or press-`h` overlay listing shortcuts.

### 11. Lazy-load thumbnails in gallery
- All 50 thumbnails per page are loaded at once. Use `loading="lazy"` on `<img>` tags or Intersection Observer for smoother scrolling on large pages.

### 12. Preload adjacent images in viewer
- When viewing image N, preload N-1 and N+1 in hidden `<img>` tags so navigation feels instant.

### 13. Better word cloud
- Size words proportionally to their count (actual word-cloud styling).
- Allow excluding common/boring words (stop list — e.g. "the", "jpg", "png", path segments like "home").
- Support multi-word selection with AND/OR toggle.
- Show which words are currently active as filters.

### 14. Sort options
- Gallery is always sorted by file path. Add options: by name, by size, by rating, by file type, random/shuffle.

### 15. Search / jump-to
- A search box in the gallery header that filters by filename substring without needing the word cloud.

### 16. Slideshow mode
- Auto-advance through images on a timer (configurable interval). Useful for hands-free viewing.

### 17. Support more formats
- Currently: png, jpg, jpeg, gif, mp4, m4v.
- Add: webp, avif, bmp, tiff (images); webm, mkv, avi (videos — browser-playable subset).
- `check_is_video` hardcodes extensions — make this data-driven.

### 18. Delete / hide files from the UI
- A "hide" action (move to a `.mediaviewer/trash/` folder or just flag in DB) so you can remove unwanted files during triage without leaving the browser.

## Code Quality

### 19. Error handling on preview generation
- If `generate_preview` or `generate_video_preview` throws, the exception is caught and printed but the placeholder SVG is only served for "no preview found", not distinguished from "preview generation failed". Show a distinct error thumbnail.

### 20. Static file serving security
- `serve_static_file` joins a user-supplied path to `script_dir` with only an `os.path.exists` check — a `../` in the URL path could escape the static directory. Add a check that the resolved path is still under the allowed directory.

### 21. Content-Length on HTML responses
- Gallery, viewer, and words page responses don't send `Content-Length`. Add it for correctness and so progress indicators work.

### 22. Cache headers
- Previews are static once generated — serve them with `Cache-Control` / `ETag` headers so the browser doesn't re-fetch on every page load.

### 23. WEBP previews instead of PNG
- Previews are 320×200 PNGs. WebP would cut size roughly in half with no visible quality loss.

## UX / Visual

### 24. Dark mode
- The gallery is light-themed but the viewer is dark. Add a consistent dark mode toggle, or follow `prefers-color-scheme`.

### 25. Filename in gallery thumbnails
- Currently shows "Media 42" — show the actual filename (truncated) so you can identify files.

### 26. Responsive thumbnail grid
- The grid uses `minmax(320px, 1fr)` which works but doesn't adapt well to very wide screens. Consider a handful of breakpoints or letting the user pick grid density.

### 27. Progress indicator for cache building
- `--build-cache` only shows console output. If triggered from the UI (or web-initiated), a progress bar / percentage in the browser would be helpful.

### 28. Indicate video vs. image in gallery
- Currently no visual distinction between video and image thumbnails (animated GIF previews help, but a small "▶" badge would be clearer).
