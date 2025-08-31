#!/usr/bin/env python3
import argparse
import pathlib
import sys
from typing import Optional

import pandas as pd
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")


def create_flashcards_from_excel(
    input_excel: pathlib.Path,
    output_pdf: pathlib.Path,
    pad_to_multiple_of_4: bool = True,
    sheet=None,
    images_dir: Optional[pathlib.Path] = None,
):
    df = pd.read_excel(pathlib.Path(input_excel), sheet_name=sheet)
    _create_from_df(df, output_pdf, pad_to_multiple_of_4, images_dir=images_dir)


def create_flashcards_from_csv(
    input_csv: pathlib.Path,
    output_pdf: pathlib.Path,
    delimiter: str = ";",
    pad_to_multiple_of_4: bool = True,
    images_dir: Optional[pathlib.Path] = None,
):
    if delimiter in (None, "", "auto"):
        import csv

        with open(input_csv, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";"

    df = pd.read_csv(
        pathlib.Path(input_csv),
        delimiter=delimiter,
        dtype=str,
        keep_default_na=False,
    )
    _create_from_df(df, output_pdf, pad_to_multiple_of_4, images_dir=images_dir)


def _create_from_df(
    df: pd.DataFrame,
    output_pdf: pathlib.Path,
    pad_to_multiple_of_4: bool,
    images_dir: Optional[pathlib.Path] = None,
):
    required = {"Question", "Answer"}
    if not required.issubset(df.columns):
        raise ValueError("Input must contain 'Question' and 'Answer' columns.")

    questions = df["Question"].astype(str).tolist()
    answers = df["Answer"].astype(str).tolist()

    if pad_to_multiple_of_4:
        total_cards = ((len(questions) + 3) // 4) * 4
        questions += [f"Question {i+1}" for i in range(len(questions), total_cards)]
        answers += ["Answer"] * (total_cards - len(answers))

    create_pdf(questions, answers, output_pdf, images_dir=images_dir)


def _resolve_image_path(item: str, images_dir: Optional[pathlib.Path]) -> Optional[pathlib.Path]:
    low = item.strip().lower()
    if not low.endswith(IMAGE_EXTS):
        return None

    raw = pathlib.Path(item.replace("\\", "/"))

    if raw.is_absolute() and raw.exists():
        return raw
    if raw.exists():
        return raw
    if images_dir:
        base_try = images_dir / raw.name
        if base_try.exists():
            return base_try
        nested_try = images_dir / raw
        if nested_try.exists():
            return nested_try
    return None


def create_pdf(
    questions,
    answers,
    output_pdf: pathlib.Path,
    images_dir: Optional[pathlib.Path] = None,
):
    page_width, page_height = landscape(A4)
    margin = 0.25 * inch
    card_width = (page_width - (0.5 * inch)) / 2
    card_height = (page_height - (0.5 * inch)) / 2
    cards_per_row = 2
    cards_per_column = 2

    def draw_page(c, items, is_question_side=True, start_index=0):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.black)

        for i, item in enumerate(items):
            row = i // cards_per_row
            col = i % cards_per_row
            x = col * card_width + margin / 2
            y = page_height - ((row + 1) * card_height) - margin / 2

            if col > 0:
                c.line(x, y, x, y + card_height)
            if row > 0:
                c.line(x, y + card_height, x + card_width, y + card_height)

            max_text_width = card_width - 2 * margin

            text = f"{item}\n(Card {start_index + i + 1})" if is_question_side else item

            img_path = _resolve_image_path(item, images_dir=images_dir)
            if img_path is not None:
                try:
                    img_width = card_width * 0.8
                    img_height = card_height * 0.8
                    img_x = x + (card_width - img_width) / 2
                    img_y = y + (card_height - img_height) / 2
                    c.drawImage(
                        str(img_path),
                        img_x,
                        img_y,
                        width=img_width,
                        height=img_height,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    continue
                except Exception:
                    pass

            c.setFont("Helvetica-Bold", 6)
            text_lines = []
            text = text.replace("\\n", "\n")
            for line in text.split("\n"):
                words = line.split()
                temp_line = ""
                for word in words:
                    candidate = (temp_line + " " + word).strip()
                    if c.stringWidth(candidate, "Helvetica-Bold", 6) < max_text_width:
                        temp_line = candidate
                    else:
                        if temp_line:
                            text_lines.append(temp_line)
                        temp_line = word
                if temp_line:
                    text_lines.append(temp_line)
                text_lines.append("")

            line_height = 7
            total_text_height = len(text_lines) * line_height
            start_y = y + (card_height + total_text_height) / 2 - (line_height / 2)
            for j, line in enumerate(text_lines):
                c.drawCentredString(x + card_width / 2, start_y - j * line_height, line)

    c = canvas.Canvas(str(pathlib.Path(output_pdf)), pagesize=landscape(A4))

    batch_size = cards_per_row * cards_per_column
    for i in range(0, len(questions), batch_size):
        question_batch = questions[i : i + batch_size]
        draw_page(c, question_batch, is_question_side=True, start_index=i)
        c.showPage()

        answer_batch = answers[i : i + batch_size]
        answer_batch = [answer_batch[j ^ 1] for j in range(len(answer_batch))]
        draw_page(c, answer_batch, is_question_side=False)
        c.showPage()

    c.save()
    print(f"Flashcard PDF saved as {output_pdf}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Create printable 2x2 flashcards PDF from a folder containing CSV/XLSX and an Images/ dir.",
    )
    p.add_argument(
        "folder",
        help="Folder name (expects <folder>/<folder>.csv or .xlsx/.xls and <folder>/Images/).",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output PDF path (default: <folder>/<arg>_flashcards.pdf).",
    )
    p.add_argument(
        "--delimiter",
        default=";",
        help='CSV delimiter (use "auto" to sniff). Default: ";"',
    )
    p.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name or index (if using Excel; default: first sheet).",
    )
    p.add_argument(
        "--no-pad",
        action="store_true",
        help="Do not pad to a multiple of 4 cards.",
    )
    return p.parse_args(argv)


def _pick_input_file(base_dir: pathlib.Path, base_name: str) -> pathlib.Path:
    csv = base_dir / f"{base_name}.csv"
    xlsx = base_dir / f"{base_name}.xlsx"
    xls = base_dir / f"{base_name}.xls"
    if csv.exists():
        return csv
    if xlsx.exists():
        return xlsx
    if xls.exists():
        return xls
    raise SystemExit(f"Could not find {csv.name}, {xlsx.name}, or {xls.name} in {base_dir}")


def main(argv=None):
    args = parse_args(argv)

    folder = pathlib.Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    base_name = folder.name
    input_path = _pick_input_file(folder, base_name)

    output_path = pathlib.Path(args.output) if args.output else (folder / f"{base_name}_flashcards.pdf")

    images_dir = folder / "Images"
    if not images_dir.exists():
        print(f"Warning: images directory not found: {images_dir}", file=sys.stderr)

    sheet = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)

    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        create_flashcards_from_csv(
            input_path,
            output_path,
            delimiter=args.delimiter,
            pad_to_multiple_of_4=not args.no_pad,
            images_dir=images_dir,
        )
    elif suffix in (".xlsx", ".xls"):
        create_flashcards_from_excel(
            input_path,
            output_path,
            pad_to_multiple_of_4=not args.no_pad,
            sheet=sheet,
            images_dir=images_dir,
        )
    else:
        raise SystemExit("Input must be .csv, .xlsx, or .xls")


if __name__ == "__main__":
    main()