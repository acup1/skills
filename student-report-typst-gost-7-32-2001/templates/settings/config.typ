// Numbers: pt for font size, mm for geometry, fractions for image/column widths.
#let config = (
  profile: "student-lab",
  font: "Times New Roman",
  font-size: 14,
  math-font: "Cambria Math",
  line-spacing: 1.5,
  paragraph-spacing: 0, // pt, extra gap beyond the normal line pitch
  hyphenate: false,
  first-indent: 12.5,
  margins: (left: 30, right: 10, top: 20, bottom: 20),
  heading-bold: true,
  heading-number-suffix: ".", // 1. / 2.3. / 3.1.2.
  heading-space-before: (12, 9, 6), // pt, levels 1–3
  heading-space-after: (6, 6, 3),
  heading-uppercase: false,
  short-refs: true,
  equation-numbering: "continuous", // or "section": (1.1), (1.2), (2.1)
  figure-max-height: 80, // mm, image only; allow extra room for caption
  contents: false,
  contents-depth: 2,
)
