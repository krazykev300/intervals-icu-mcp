# Brand

A loose guide to the foothill2skyline and intervals coach marks. The colours and
fonts match kevinkauffman.com/foothill2skyline.

## Colours

| Name | Hex | Use |
|---|---|---|
| Paper | `#E8E4DC` | Page background; foothill2skyline icon background |
| Cream | `#F3EDE3` | Coach bars; lighter icon background |
| Ink | `#1A1A18` | Text; the "you" marker outline |
| Forest | `#1A5C3A` | The hill; coach icon background |
| Race red | `#C8232C` | The race tree, the peak bar, the "2" in the wordmark |
| Stone | `#6B6358` | Taglines and secondary text |
| Back hill | `#CFC6B6` | The far ridge |
| Mint | `#CFE0D4` | Coach baseline |

Red means race day. Use it once per mark, for the goal, never as decoration.

## Fonts

- **Fraunces** for names and headlines.
- **IBM Plex Mono** for taglines, labels and data: uppercase, wide letter spacing.

The lockup SVGs use live text, so they need these fonts loaded; elsewhere they
fall back to Georgia and a system monospace.

## Logos

| File | Use |
|---|---|
| `foothill2skyline-mark.svg` | Favicon, avatar, app icon |
| `foothill2skyline-lockup.svg` | Site header, social cards |
| `coach-mark.svg` | Connector icon, avatar |
| `coach-lockup.svg` | README header, docs |

PNG copies with transparent corners live in `png/`, for places that won't
take SVG:

- `*-mark-32.png` for favicons, `*-mark-180.png` for the Apple touch icon,
  `*-mark-512.png` for avatars and app icons.
- `*-lockup.png` at 760×160 (2× the SVG), with the fonts baked in.

Re-export them from the SVGs after any change.

- Marks read down to 16px.
- On the paper page background, give the foothill2skyline mark a cream
  (`#F3EDE3`) background so it doesn't blend in.
- Don't recolour, stretch or add effects.
