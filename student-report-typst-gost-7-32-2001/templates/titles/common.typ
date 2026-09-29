#let organization(info, bold-university: false) = align(center)[
  #info.ministry #linebreak()
  #info.organization #linebreak()
  #text(weight: if bold-university { "bold" } else { "regular" })[
    #info.university #linebreak()
    #info.university-detail
  ]
  #if info.department != "" { linebreak(); info.department }
]

#let work(info) = align(center)[
  #info.work-kind #linebreak()
  по дисциплине #linebreak()
  «#info.discipline»
  #if info.topic != "" { linebreak(); [на тему: «#info.topic»] }
  #if info.variant != "" { linebreak(); [#info.variant вариант] }
]

#let signatures(info, inline-group: false) = align(right)[
  #info.student-label #linebreak()
  #for person in info.students {
    if inline-group and info.group != "" { [Студент группы #info.group ] }
    [#person #linebreak()]
  }
  #if not inline-group and info.group != "" { [Группа #info.group #linebreak()] }
  #v(4mm)
  #info.teacher-label #linebreak()
  #if info.teacher-position != "" { [#info.teacher-position ] }
  #info.teacher
]

#let city-year(info) = align(center)[#info.city #linebreak() #info.year]
