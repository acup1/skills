#import "settings/config.typ": config
#import "settings/metadata.typ": info
#import "settings/render.typ": render-report
#import "settings/blocks.typ": structural
#import "titles/selected.typ": title-variant
#import "chapters/01-introduction.typ": introduction
#import "chapters/02-main.typ": main-part
#import "chapters/03-conclusion.typ": conclusion
#import "bibliography/sources.typ": sources

// This file only assembles modules. Content lives in subdirectories.
#let blocks = introduction + main-part + conclusion
#if sources.len() > 0 {
  blocks += (structural([СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ], new-page: true),)
  blocks += sources
}
#render-report(config, info, title-variant, blocks)
