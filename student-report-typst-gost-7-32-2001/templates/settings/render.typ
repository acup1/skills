#import "blocks.typ": prepare, reference-text
#import "image-layout.typ": report-image
#import "../titles/lab.typ" as lab
#import "../titles/mai-course.typ" as mai
#import "../titles/generic.typ" as generic

#let render-report(config, info, title-variant, content-blocks) = {
  assert(title-variant in ("lab", "mai-course", "generic"),
    message: "Choose a title with the user, then edit titles/selected.typ")
  assert(config.equation-numbering in ("continuous", "section"))
  let blocks = prepare(content-blocks, config)
  if config.profile == "gost-2001-strict" {
    assert(not config.heading-bold and not config.short-refs,
      message: "Strict GOST requires regular headings and full references")
  }
  set document(title: info.topic, author: info.students)
  let line-gap = (config.line-spacing - 1) * 1em
  let paragraph-gap = line-gap + config.at("paragraph-spacing", default: 0) * 1pt
  set text(font: config.font, size: config.font-size * 1pt, lang: "ru", fill: black,
    top-edge: 0.8em, bottom-edge: -0.2em, hyphenate: config.at("hyphenate", default: false))
  // The bottom edge must be BELOW the baseline: 0.8em + 0.2em + 0.5em = 1.5em.
  // Typst spacing includes the gap between text frames; Word before/after do not.
  set par(justify: true, first-line-indent: (amount: config.first-indent * 1mm, all: true),
    leading: line-gap, spacing: paragraph-gap)
  set page(paper: "a4", margin: (left: config.margins.left * 1mm, right: config.margins.right * 1mm, top: config.margins.top * 1mm, bottom: config.margins.bottom * 1mm),
    footer: context {
      if counter(page).get().first() > 1 { align(center, counter(page).display("1")) }
    })
  show math.equation: set text(font: config.math-font)
  set heading(numbering: none)
  set figure.caption(separator: [ – ])
  // Show-set rules preserve native heading semantics and spacing.
  let heading-before = config.at("heading-space-before", default: (12, 9, 6))
  let heading-after = config.at("heading-space-after", default: (6, 6, 3))
  show heading: set text(size: config.font-size * 1pt,
    weight: if config.heading-bold { "bold" } else { "regular" }, hyphenate: false)
  show heading: set par(first-line-indent: 0pt, justify: false)
  show heading.where(level: 1): set block(above: heading-before.at(0) * 1pt,
    below: heading-after.at(0) * 1pt, sticky: true, breakable: false)
  show heading.where(level: 2): set block(above: heading-before.at(1) * 1pt,
    below: heading-after.at(1) * 1pt, sticky: true, breakable: false)
  show heading.where(level: 3): set block(above: heading-before.at(2) * 1pt,
    below: heading-after.at(2) * 1pt, sticky: true, breakable: false)
  show figure.caption: it => {
    set par(first-line-indent: 0pt, justify: false)
    if it.kind == table { align(left, it) } else { align(center, it) }
  }
  show ref: it => {
    let found = blocks.filter(b => b.at("id", default: none) == str(it.target))
    assert(found.len() == 1, message: "Unknown reference: " + str(it.target))
    link(it.target, reference-text(found.first(), short: config.short-refs))
  }
  set list(indent: config.first-indent * 1mm, body-indent: 0.5em, marker: "–")
  set enum(indent: config.first-indent * 1mm, body-indent: 0.5em, numbering: "1.")
  set table(stroke: 0.5pt + black, fill: none, inset: 4pt, align: left)

  [#metadata((schema: 1, config: config, info: info, title: title-variant, blocks: blocks)) <report-data>]
  if title-variant == "mai-course" { mai.title(info, config) }
  else if title-variant == "generic" { generic.title(info, config) }
  else { lab.title(info, config) }
  if config.contents {
    {
      set align(center)
      heading(level: 1, outlined: false, [СОДЕРЖАНИЕ])
    }
    outline(title: none, indent: config.first-indent * 1mm, depth: config.contents-depth)
    pagebreak()
  }
  for b in blocks {
    let rendered = if b.kind == "paragraph" { par(b.body) }
    else if b.kind == "heading" {
      if b.new-page { pagebreak(weak: true) }
      let title = if b.structural or (b.level == 1 and config.heading-uppercase) { upper(b.body) } else { b.body }
      if b.number != "" { title = [#b.number #title] }
      set align(if b.structural or (b.level == 1 and config.heading-uppercase) { center } else { left })
      heading(level: b.level, title)
    } else if b.kind == "figure" {
      assert(b.width > 0 and b.width <= 1, message: "Figure width must be in (0, 1]")
      let height-limit = b.at("max-height", default: none)
      if height-limit == none { height-limit = config.at("figure-max-height", default: 80) }
      let available-width = (210 - config.margins.left - config.margins.right) * 1mm
      figure(report-image("/" + b.path, width: b.width * available-width,
        max-height: height-limit * 1mm, crop: b.at("crop", default: none)), kind: image,
        caption: b.caption, supplement: [Рисунок], numbering: "1", gap: 4pt)
    } else if b.kind == "table" {
      let n = b.headers.len()
      assert(n > 0 and b.rows.all(r => r.len() == n), message: "Unequal table row lengths")
      let widths = if b.widths == none { (1,) * n } else { b.widths }
      assert(widths.len() == n and widths.all(w => w > 0), message: "Invalid table widths")
      set par(first-line-indent: 0pt, justify: false)
      set figure.caption(position: top)
      show figure: set block(breakable: true)
      figure(table(columns: widths.map(w => w * 1fr), table.header(..b.headers), ..b.rows.flatten()),
        kind: table, caption: b.caption, supplement: [Таблица], numbering: "1", gap: 4pt)
    } else if b.kind == "equation" {
      block(above: 6pt, below: 6pt, math.equation(b.body, block: true, numbering: n => "(" + b.number + ")"))
    } else if b.kind == "list" {
      if b.ordered { enum(..b.items) } else { list(..b.items) }
    } else if b.kind == "source" {
      set par(first-line-indent: 0pt, hanging-indent: config.first-indent * 1mm)
      par([#b.number. #b.body])
    } else if b.kind == "pagebreak" { pagebreak() }
    else { panic("Unsupported report block: " + b.kind) }
    if b.at("id", default: none) != none { [#rendered #label(b.id)] }
    else { rendered }
    parbreak()
  }
}
