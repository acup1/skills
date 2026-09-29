# Студенческие отчёты в Typst и Word

Инструкции навыка: [SKILL.md](SKILL.md).

- [Шаблоны](templates/) — модульный проект с тремя вариантами титула.
- [Создание проекта](scripts/init_project.py) — шесть поддиректорий и корневой сборщик.
- [Экспорт DOCX](scripts/export_docx.py) — редактируемый Word из той же модели Typst.
- [Проверка](scripts/preflight.py) — данные, ссылки, PDF и структура DOCX.

Сначала создаётся структура, затем выбирается титул: `lab`, `mai-course` или `generic`. Профили оформления: `student-lab`, `student-course`, `gost-2001-strict`. Сборка не выбирает неизвестный титул молча.

```bash
python3 scripts/init_project.py /tmp/my-report --title lab
# Заполнить реквизиты и главы, добавить реальные изображения/таблицы.
typst compile /tmp/my-report/report.typ /tmp/my-report/report.pdf
python3 scripts/export_docx.py /tmp/my-report/report.typ /tmp/my-report/report.docx
python3 scripts/preflight.py /tmp/my-report/report.typ /tmp/my-report/report.pdf --docx /tmp/my-report/report.docx
```

[Формат проекта](references/project-format.md) · [Титулы](references/title-pages.md) · [DOCX и ограничения](references/docx.md) · [ГОСТ 2001](references/gost-7.32-2001.md)

Проверки разработчика: `python3 -m unittest discover -s tests -v` (Typst и python-docx нужны для полного прогона).
