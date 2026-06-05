---
name: Terminal Obsidian
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353943'
  surface-container-lowest: '#0a0e17'
  surface-container-low: '#181b25'
  surface-container: '#1c1f29'
  surface-container-high: '#262a34'
  surface-container-highest: '#31353f'
  on-surface: '#dfe2ef'
  on-surface-variant: '#c7c4d7'
  inverse-surface: '#dfe2ef'
  inverse-on-surface: '#2c303a'
  outline: '#908fa0'
  outline-variant: '#464554'
  surface-tint: '#c1c1ff'
  primary: '#c1c1ff'
  on-primary: '#1600a8'
  primary-container: '#8283ff'
  on-primary-container: '#120094'
  inverse-primary: '#4b49d8'
  secondary: '#d0bcff'
  on-secondary: '#3c0091'
  secondary-container: '#571bc1'
  on-secondary-container: '#c4abff'
  tertiary: '#dfb7ff'
  on-tertiary: '#4b007e'
  tertiary-container: '#ba6bff'
  on-tertiary-container: '#41006f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c1c1ff'
  on-primary-fixed: '#0a006b'
  on-primary-fixed-variant: '#312cc0'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#f1daff'
  tertiary-fixed-dim: '#dfb7ff'
  on-tertiary-fixed: '#2d004f'
  on-tertiary-fixed-variant: '#6b00b0'
  background: '#0f131c'
  on-background: '#dfe2ef'
  surface-variant: '#31353f'
typography:
  display-xl:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  data-mono:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-margin: 24px
  gutter: 16px
  section-gap: 32px
  input-padding: 12px 16px
---

## Brand & Style

The design system establishes a high-performance, premium environment for financial data analysis. It targets professional traders and analysts who require a high-density information display without sacrificing the aesthetic polish associated with flagship SaaS products like Linear or Apple.

The visual style is **Glassmorphic Modernism**. It balances technical precision with atmospheric depth, utilizing deep obsidian voids, semi-transparent layers, and vibrant aurora-inspired background glows. The interface should feel like a high-end physical hardware terminal—weighty, responsive, and meticulously crafted. The emotional response is one of calm control, institutional reliability, and technological edge.

All interface labels and messaging are localized in **Russian**, using professional financial terminology.

## Colors

The palette is anchored in a deep obsidian `#0a0e17` to maximize contrast and reduce eye strain during long trading sessions. 

- **Primary Accent:** A three-stop linear gradient is used for flagship actions, progress indicators, and "active" states.
- **Surface Tiers:** 
  - Base Card: `#131a28`
  - Elevated/Hover: `#1a2335`
- **Functional Colors:** 
  - **Success (Рост):** Emerald green for positive price action and completed orders.
  - **Danger (Падение):** Soft rose for negative price action and alerts.
  - **Warning (Ожидание):** Amber for pending states or liquidity gaps.
- **Typography:** Primary text uses a high-visibility off-white `#f1f5fb`, while secondary/meta-info uses a muted slate-blue `#8c99b0` to maintain hierarchy.

## Typography

This design system exclusively utilizes **Inter**. For a trading terminal, the key requirement is legible data. 

- **Tabular Numerals:** All numeric data (prices, volumes, percentages) must use `font-variant-numeric: tabular-nums`. This ensures columns of numbers align vertically, preventing layout jitter during real-time updates.
- **Hierarchy:** Headlines are bold and tightly tracked to feel architectural. 
- **Language Support:** Cyrillic characters must maintain the same weight-to-x-height ratio as Latin counterparts.
- **Labels:** Use "Label Caps" for section headers like "ОРДЕРА" (Orders) or "БАЛАНС" (Balance) to differentiate from active content.

## Layout & Spacing

The system uses a **Fluid Grid** model with a 12-column structure for the main dashboard. 

- **Density:** Despite being "generous," the layout remains functional. Components use an 8px base grid, but the internal padding of cards is 24px to provide the "premium" breathability found in high-end SaaS.
- **Breakpoints:**
  - **Desktop (1440px+):** 12 columns, 24px margins. Sidebar is fixed at 280px.
  - **Tablet (768px - 1439px):** 8 columns, 16px margins. Sidebar collapses to icons.
  - **Mobile (<767px):** 4 columns, 12px margins. Horizontal scrolling for data tables is permitted.
- **Scroll Areas:** Main content uses hidden scrollbars with custom indicators to maintain the "Glassmorphism" look.

## Elevation & Depth

Hierarchy is established through transparency and blurred backdrops rather than traditional heavy shadows.

- **Surface Levels:**
  - **Level 0 (Background):** `#0a0e17`. Deepest layer. Contains subtle `aurora` blurs—large, low-opacity blobs of primary/secondary colors (blur: 120px) that move slowly in the background.
  - **Level 1 (Cards):** `#131a28` with 80% opacity. Backdrop-blur: 20px. Border: 1px solid `rgba(255,255,255,0.07)`.
  - **Level 2 (Modals/Popovers):** `#1a2335` with 90% opacity. Backdrop-blur: 40px. Shadow: 0px 20px 40px rgba(0,0,0,0.4).
- **Interactive States:** Hovering over a card should slightly increase the border opacity to `0.15` and increase the background saturation.

## Shapes

The design system follows a **Rounded** philosophy to soften the technical nature of the data.

- **Base Radius:** 16px (`1rem`) for all primary containers, cards, and large modals.
- **Small Elements:** 8px (`0.5rem`) for buttons, input fields, and tags.
- **Interactive Clips:** All hover states must respect the parent container's corner radius. Focus rings are offset by 2px and use the primary gradient color.

## Components

### Buttons (Кнопки)
- **Primary:** Filled with the accent gradient. Text is white. Box-shadow includes a soft glow of the primary color.
- **Secondary:** Transparent background with the 1px white/0.07 border. Hover state fills with `#1a2335`.
- **Destructive:** Border and text use the `Danger` status color.

### Data Tables (Таблицы данных)
- **Header:** Labels in `label-caps` with `#8c99b0`.
- **Row:** 1px border-bottom. Hover state applies a subtle highlight.
- **Cell:** Monospaced numbers for all financial values. Use "Рост" (Green) and "Падение" (Red) text colors for price changes.

### Inputs (Поля ввода)
- **Style:** Background `#0a0e17`, border `rgba(255,255,255,0.07)`.
- **Focus:** Border changes to primary color; 2px outer glow.
- **Labels:** Always Russian (e.g., "Сумма сделки", "Стоп-лосс").

### Chips & Status (Индикаторы)
- Small, 4px rounded tags. 
- Usage: "В исполнении" (In progress), "Завершено" (Completed), "Отменено" (Cancelled).

### Charts (Графики)
- Line charts use the primary gradient for the stroke.
- Area charts use a vertical gradient from primary (20% opacity) to transparent.
- Candlesticks: Solid fills, no borders, using the status success/danger colors.