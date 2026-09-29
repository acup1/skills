// Clip at layout time: the image file is never cropped or rewritten.
#let report-image(path, width: 160mm, max-height: 80mm, crop: none) = context {
  assert(width > 0pt and max-height > 0pt, message: "Image size limits must be positive")
  let c = if crop == none { (left: 0, top: 0, right: 0, bottom: 0) } else { crop }
  assert((c.left, c.top, c.right, c.bottom).all(v => v >= 0 and v < 1)
    and c.left + c.right < 1 and c.top + c.bottom < 1,
    message: "Crop margins must leave a nonempty image")
  let natural = measure(image(path))
  let visible-x = 1 - c.left - c.right
  let visible-y = 1 - c.top - c.bottom
  let ratio = (natural.width / natural.height) * visible-x / visible-y
  let w = calc.min(width, max-height * ratio)
  let h = w / ratio
  if crop == none {
    image(path, width: w, height: h)
  } else {
    box(width: w, height: h, clip: true,
      place(top + left, dx: -w * c.left / visible-x, dy: -h * c.top / visible-y,
        image(path, width: w / visible-x, height: h / visible-y)))
  }
}
