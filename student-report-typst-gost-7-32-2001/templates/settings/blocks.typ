// Data blocks: PDF and DOCX render the same Typst content.
#let para(body) = (kind: "paragraph", body: body)
#let section(body, level: 1, id: none, numbered: true, new-page: none) = (
  kind: "heading", body: body, level: level, id: id,
  numbered: numbered, new-page: new-page, structural: false,
)
#let structural(body, new-page: none) = (
  kind: "heading", body: body, level: 1, id: none,
  numbered: false, new-page: new-page, structural: true,
)
// Pixel rectangle (x, y, width, height), measured from the top-left corner.
// Store relative trim amounts so PDF and Word use the same viewport.
#let crop-px(region, source: none) = {
  assert(source != none and source.len() == 2 and region.len() == 4,
    message: "crop-px requires region (x, y, width, height) and source (width, height)")
  let (sw, sh) = source
  let (x, y, w, h) = region
  assert(sw > 0 and sh > 0 and x >= 0 and y >= 0 and w > 0 and h > 0
    and x + w <= sw and y + h <= sh, message: "Crop rectangle is outside the source image")
  (left: x / sw, top: y / sh, right: (sw - x - w) / sw, bottom: (sh - y - h) / sh)
}
#let screenshot(path, caption, id: none, width: 0.92, crop: none, max-height: none) = (
  kind: "figure", path: path, caption: caption, id: id, width: width,
  crop: crop, max-height: max-height,
)
#let result-table(caption, headers, rows, id: none, widths: none) = (
  kind: "table", caption: caption, headers: headers, rows: rows,
  id: id, widths: widths,
)
#let formula(body, id: none) = (kind: "equation", body: body, id: id)
#let bullet-list(items) = (kind: "list", ordered: false, items: items)
#let numbered-list(items) = (kind: "list", ordered: true, items: items)
#let source(id, body) = (kind: "source", id: id, body: body)
#let new-page() = (kind: "pagebreak")

// Number once, so references and captions agree across PDF and Word.
#let prepare(blocks, config) = {
  let counts = (figure: 0, table: 0, equation: 0, source: 0)
  let headings = (0, 0, 0)
  let in-structural-section = false
  let ids = ()
  let result = ()
  for item in blocks {
    let b = item
    let id = b.at("id", default: none)
    if id != none {
      assert(type(id) == str and id != "", message: "Block id must be a nonempty string")
      assert(not (id in ids), message: "Duplicate block id: " + id)
      ids.push(id)
    }
    // Resolve page policy once for both renderers. Explicit values are exceptions.
    if b.kind == "heading" {
      assert(b.level >= 1 and b.level <= 3, message: "Heading levels: 1–3")
      let break-before = b.new-page
      assert(break-before == none or type(break-before) == bool,
        message: "new-page must be none (profile), true or false")
      if break-before == none {
        break-before = b.structural or (b.level == 1 and
          (in-structural-section or config.profile == "student-course"))
      }
      b.insert("new-page", break-before)
      if b.level == 1 { in-structural-section = b.structural }
    }
    let num = ""
    if b.kind == "heading" and b.numbered {
      assert(b.level >= 1 and b.level <= 3, message: "Heading levels: 1–3")
      let i = b.level - 1
      if i > 0 { assert(headings.at(i - 1) > 0, message: "Missing parent heading") }
      headings.at(i) += 1
      for j in range(i + 1, 3) { headings.at(j) = 0 }
      num = headings.slice(0, b.level).map(str).join(".") + config.at("heading-number-suffix", default: ".")
      if b.level == 1 and config.equation-numbering == "section" { counts.equation = 0 }
    } else if b.kind in counts {
      counts.at(b.kind) += 1
      num = str(counts.at(b.kind))
      if b.kind == "equation" and config.equation-numbering == "section" {
        assert(headings.first() > 0, message: "Section equation requires a numbered chapter")
        num = str(headings.first()) + "." + num
      }
    }
    b.insert("number", num)
    result.push(b)
  }
  result
}

#let reference-text(b, short: true) = {
  if b.kind == "figure" { (if short { "рис. " } else { "рисунок " }) + b.number }
  else if b.kind == "table" { (if short { "табл. " } else { "таблица " }) + b.number }
  else if b.kind == "equation" { "(" + b.number + ")" }
  else if b.kind == "source" { "[" + b.number + "]" }
  else { b.number }
}
