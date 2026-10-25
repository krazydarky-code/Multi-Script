# Multi-Script 6.19.2 — Notion Fit

## Exact Notion composer width

The Multi-Script bar now anchors to the visible Notion “Ask anything” composer card itself. Previously it was inserted as a 100%-wide sibling inside Notion’s wider action rail, which includes controls beside the composer; that made the bar continue past the chat box and off-screen.

Anchored mode reads the composer rectangle continuously and copies its exact left edge and width, so the bar follows Notion through window resizes, sidebar changes, and responsive layout shifts without modifying Notion’s React tree.

## Width-aware controls

Bar responsiveness is now based on the measured composer width rather than viewport width. On narrower centered composers, secondary support icons collapse into the existing menu, labels truncate safely, and very compact bars hide the redundant engine-free start action when a normal engine start is already available.

No provider or tool behavior changed. The fix applies safely to every anchored provider while Notion uses it directly for exact-width fitting.
