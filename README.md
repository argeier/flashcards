# Flashcards PDF

Simple tool to create printable 2x2 flashcards from CSV/Excel files.

<img src="examples/example_front.png" width="500" alt="Example flashcards">
<img src="examples/example_back.png" width="500" alt="Example flashcards">


## Usage

```bash
uv sync
uv run flashcards my_course
```

Expected folder structure:
```
my_course/
├── my_course.csv (or .xlsx/.xls)
└── Images/ (optional, for image flashcards)
```

CSV format: `Question` and `Answer` columns, semicolon-separated by default.

## Options

- `--output path.pdf` - Custom output path
- `--delimiter ","` - CSV delimiter (or "auto")
- `--sheet "Sheet1"` - Excel sheet name/index
- `--no-pad` - Don't pad to multiple of 4 cards

Cards are automatically padded to multiples of 4 for easy printing and cutting.