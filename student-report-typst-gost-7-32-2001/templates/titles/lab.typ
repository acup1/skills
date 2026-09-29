#import "common.typ": *
#let title(info, config) = {
  set par(first-line-indent: 0pt, justify: false)
  organization(info)
  v(24mm)
  work(info)
  v(1fr)
  signatures(info)
  v(1fr)
  city-year(info)
  pagebreak()
}
