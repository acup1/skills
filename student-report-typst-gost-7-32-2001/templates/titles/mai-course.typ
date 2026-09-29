// User's MAI course title: 5 cm / 3 cm gaps, variant, inline group,
// reviewer position, city/year below. Personal details stay in metadata.typ.
#import "common.typ": *
#let title(info, config) = {
  set par(first-line-indent: 0pt, justify: false)
  organization(info, bold-university: config.profile != "gost-2001-strict")
  v(50mm)
  work(info)
  v(30mm)
  signatures(info, inline-group: true)
  v(1fr)
  city-year(info)
  pagebreak()
}
