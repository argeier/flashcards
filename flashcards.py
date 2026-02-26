#!/usr/bin/env python3
import argparse
import pathlib
import re
from typing import List, Optional
from xml.sax.saxutils import escape

import genanki
import markdown
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepInFrame, Paragraph, Table, TableStyle, XPreformatted

# --- Constants & Configuration ---
ANKI_MODEL_ID = 1607392319


def create_anki_deck(deck_data, root_deck_name, output_path, media_files):
    model_css = (
        ".card { text-align: center; color: black; background-color: white; font-family: Arial; font-size: 16px; } "
        ".question { margin-bottom: 20px; font-weight: bold; } "
        ".answer { text-align: left; display: inline-block; width: 100%; } "
        "img { max-width: 100%; height: auto; } "
        "table { border-collapse: collapse; margin: 10px auto; width: 100%; } "
        "th, td { border: 1px solid #ccc; padding: 6px; text-align: left; } "
        "th { background-color: #f4f4f4; } "
        "pre { text-align: left; background: #f0f0f0; padding: 10px; border-radius: 5px; "
        "      overflow-x: auto; max-width: 100%; box-sizing: border-box; } "
        "code { font-family: monospace; background: #f0f0f0; padding: 2px; font-size: 13px; } "
        "ul, ol { text-align: left; display: inline-block; margin-left: 20px; margin-top: 5px; margin-bottom: 5px; } "
        "li { margin-bottom: 4px; } "
        "b, strong { color: #2e5cb8; } "
    )
    model = genanki.Model(
        ANKI_MODEL_ID,
        "Obsidian Markdown Hierarchical Model",
        fields=[{"name": "Question"}, {"name": "Answer"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": '<div class="question">{{Question}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="answer">{{Answer}}</div>',
            }
        ],
        css=model_css,
    )

    decks = []
    global_idx = 1

    for subdeck_name, qa_pairs in deck_data.items():
        full_name = f"{root_deck_name}::{subdeck_name}" if subdeck_name else root_deck_name
        deck_id = abs(hash(full_name)) % (10**10)
        deck = genanki.Deck(deck_id, full_name)

        for q_html, a_html in qa_pairs:
            q_final = f"<div style='display:none;'>{global_idx:04d}</div>{q_html}<br><span style='font-size: 10px; color: grey;'>ID: {global_idx}</span>"
            note = genanki.Note(model=model, fields=[q_final, a_html])
            deck.add_note(note)
            global_idx += 1

        decks.append(deck)

    package = genanki.Package(decks)
    package.media_files = media_files
    package.write_to_file(output_path)


# --- Helper Functions ---
def _extract_image_names(text: str) -> List[str]:
    return [m.split("|")[0] for m in re.findall(r"!\[\[(.*?)(?:\|.*?)?\]\]", text)]


def _resolve_image_path(
    filename: str, images_dir: Optional[pathlib.Path]
) -> Optional[pathlib.Path]:
    if images_dir and (images_dir / filename).exists():
        return images_dir / filename
    return None


# --- Advanced PDF Generator (Markdown -> ReportLab Platypus) ---
def create_pdf(questions, answers, output_pdf, images_dir=None):
    c = canvas.Canvas(str(output_pdf), pagesize=landscape(A4))
    page_width, page_height = landscape(A4)

    outer_margin = 0.25 * inch
    card_width = (page_width - (2 * outer_margin)) / 2
    card_height = (page_height - (2 * outer_margin)) / 2

    # --- Platypus PDF Styles ---
    styles = getSampleStyleSheet()
    ans_style = ParagraphStyle(
        "AnsText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=10,
        spaceBefore=0,
        spaceAfter=2,
    )
    q_style = ParagraphStyle(
        "QText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=15,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=0,
    )
    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=9,
        backColor=colors.whitesmoke,
        borderPadding=2,
        spaceAfter=2,
    )
    table_text_style = ParagraphStyle(
        "TableText", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=9
    )

    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]
    )

    def parse_to_flowables(text, is_question=False):
        flowables = []
        lines = text.split("\n")

        in_code = False
        code_lines = []
        in_table = False
        table_data = []

        base_style = q_style if is_question else ans_style
        max_w = card_width - (outer_margin * 2.5)

        card_num = None
        if is_question and lines:
            card_num = lines.pop().strip()

        for line in lines:
            line_stripped = line.strip()

            # --- 1. Fenced Code Blocks ---
            if line_stripped.startswith("```"):
                if in_code:
                    in_code = False

                    longest_line = max(code_lines, key=len) if code_lines else ""
                    # Calculate pixel width of the longest line (accounting for tabs and padding)
                    req_width = c.stringWidth(
                        longest_line.replace("\t", "    "), code_style.fontName, code_style.fontSize
                    ) + (code_style.borderPadding * 2)

                    custom_code_style = code_style
                    if req_width > max_w:
                        # Calculate exact scale needed, adding a 2% safety buffer so it doesn't touch the very edge
                        scale = (max_w * 0.98) / req_width
                        custom_code_style = ParagraphStyle(
                            "ScaledCode",
                            parent=code_style,
                            fontSize=code_style.fontSize * scale,
                            leading=code_style.leading * scale,
                        )

                    code_text = escape("\n".join(code_lines))
                    pre = XPreformatted(code_text, custom_code_style)
                    flowables.append(pre)
                    code_lines = []
                else:
                    in_code = True
                continue
            if in_code:
                code_lines.append(line)
                continue

            # --- 2. Markdown Tables ---
            if line_stripped.startswith("|") and line_stripped.endswith("|"):
                in_table = True
                row = [cell.strip() for cell in line_stripped.split("|")[1:-1]]
                if all(re.match(r"^[-:]+$", c.replace(" ", "")) for c in row):
                    continue

                formatted_row = []
                for c_raw in row:
                    c_esc = escape(c_raw)
                    c_esc = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", c_esc)
                    c_esc = re.sub(r"\*(.*?)\*", r"<i>\1</i>", c_esc)
                    c_esc = re.sub(r"`(.*?)`", r'<font name="Courier">\1</font>', c_esc)
                    ts = ParagraphStyle(
                        "Tbl",
                        parent=table_text_style,
                        alignment=TA_CENTER if not table_data else TA_LEFT,
                    )
                    formatted_row.append(Paragraph(c_esc, ts))
                table_data.append(formatted_row)
                continue
            else:
                if in_table:
                    t = Table(table_data)
                    t.setStyle(table_style)
                    t.hAlign = "CENTER" if is_question else "LEFT"
                    t.spaceAfter = 4
                    flowables.append(t)
                    in_table = False
                    table_data = []

            if not line_stripped:
                continue

            # --- 3. Image Handling ---
            img_names = _extract_image_names(line)
            if img_names:
                img_path = _resolve_image_path(img_names[0], images_dir)
                if img_path:
                    try:
                        img = RLImage(str(img_path))
                        img.drawWidth = max_w * 0.8
                        img.drawHeight = (img.drawWidth / img.imageWidth) * img.imageHeight
                        if img.drawHeight > card_height * 0.5:
                            img.drawHeight = card_height * 0.5
                            img.drawWidth = (img.drawHeight / img.imageHeight) * img.imageWidth
                        img.hAlign = "CENTER" if is_question else "LEFT"
                        img.spaceAfter = 4
                        flowables.append(img)
                    except Exception:
                        pass
                continue

            # --- 4. Standard Text and Lists ---
            if line_stripped.startswith("![") or line_stripped.startswith("]("):
                continue

            indent = len(line) - len(line.lstrip())
            clean_txt = line.strip()
            bullet = None

            if clean_txt.startswith("- ") or clean_txt.startswith("* "):
                bullet = "&bull;"
                clean_txt = clean_txt[2:]
            elif re.match(r"^\d+\.\s", clean_txt):
                bullet = clean_txt.split(".")[0] + "."
                clean_txt = clean_txt.split(".", 1)[1].lstrip()

            clean_txt = escape(clean_txt)
            clean_txt = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_txt)
            clean_txt = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_txt)
            clean_txt = re.sub(r"`(.*?)`", r'<font name="Courier">\1</font>', clean_txt)

            if is_question:
                p_style = ParagraphStyle("DynQ", parent=base_style, alignment=TA_CENTER)
                flowables.append(Paragraph(clean_txt, p_style))
            else:
                indent_pts = indent * 4
                p_style = ParagraphStyle(
                    "DynA",
                    parent=base_style,
                    leftIndent=indent_pts + (12 if bullet else 0),
                    firstLineIndent=-12 if bullet else 0,
                    bulletIndent=indent_pts,
                )
                if bullet:
                    flowables.append(Paragraph(f"<bullet>{bullet}</bullet>{clean_txt}", p_style))
                else:
                    flowables.append(Paragraph(clean_txt, p_style))

        if in_table:
            t = Table(table_data)
            t.setStyle(table_style)
            t.hAlign = "CENTER" if is_question else "LEFT"
            t.spaceAfter = 4
            flowables.append(t)

        return flowables, card_num

    def draw_page(c, items, is_question_side=True):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.lightgrey)

        for i, item in enumerate(items):
            if not item and not is_question_side:
                continue
            row, col = i // 2, i % 2

            x = outer_margin + (col * card_width)
            y = page_height - outer_margin - ((row + 1) * card_height)
            c.rect(x, y, card_width, card_height)

            flowables, card_num = parse_to_flowables(item, is_question_side)

            pad = 0.25 * inch
            id_space = 15 if is_question_side else 0

            frame_w = card_width - (pad * 2)
            frame_h = card_height - (pad * 2) - id_space

            kif = KeepInFrame(
                frame_w, frame_h, flowables, mode="shrink", hAlign="CENTER", vAlign="MIDDLE"
            )
            actual_w, actual_h = kif.wrapOn(c, frame_w, frame_h)

            draw_x = x + pad + (frame_w - actual_w) / 2
            draw_y = y + pad + id_space + (frame_h - actual_h) / 2

            kif.drawOn(c, draw_x, draw_y)

            if is_question_side and card_num:
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.grey)
                c.drawCentredString(x + card_width / 2, y + 10, f"ID: {card_num}")
                c.setFillColor(colors.black)

    for i in range(0, len(questions), 4):
        draw_page(c, questions[i : i + 4], True)
        c.showPage()
        ans_batch = [answers[j] if j < len(answers) else "" for j in range(i, i + 4)]
        if len(ans_batch) >= 2:
            ans_batch[0], ans_batch[1] = ans_batch[1], ans_batch[0]
            if len(ans_batch) == 4:
                ans_batch[2], ans_batch[3] = ans_batch[3], ans_batch[2]
        draw_page(c, ans_batch, False)
        c.showPage()

    c.save()


# --- Markdown Preprocessor (For Anki HTML) ---
def preprocess_markdown(text):
    text = re.sub(r"!\[\[(.*?)(?:\|.*?)?\]\]", r"![](\1)", text)
    text = re.sub(r"<([A-Z][^>]*)>", r"&lt;\1&gt;", text)

    lines = text.split("\n")
    cleaned_lines = []
    in_table = False
    header_sep_seen = False
    in_code = False

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Protect code blocks
        if line_stripped.startswith("```"):
            in_code = not in_code
            cleaned_lines.append(line)
            continue

        if in_code:
            cleaned_lines.append(line)
            continue

        # Clean Table Separators
        if line_stripped.startswith("|") and line_stripped.endswith("|"):
            is_sep = re.match(r"^\|[\s\-:]+\|([\s\-:]+\|)*$", line_stripped)
            if not in_table:
                in_table = True
                header_sep_seen = False

            if is_sep:
                if not header_sep_seen:
                    header_sep_seen = True
                    cleaned_lines.append(line)
                else:
                    continue  # DROP mid-table separators!
            else:
                cleaned_lines.append(line)
        else:
            in_table = False

            # Ensure lists have a preceding blank line
            is_list_item = re.match(r"^[ \t]*([-*+]|\d+\.)\s+", line)
            if is_list_item and i > 0:
                prev_line_orig = lines[i - 1]
                prev_line_stripped = prev_line_orig.strip()
                is_prev_list_item = re.match(r"^[ \t]*([-*+]|\d+\.)\s+", prev_line_orig)

                if (
                    prev_line_stripped
                    and not is_prev_list_item
                    and not prev_line_stripped.startswith("|")
                    and not prev_line_stripped.startswith("#")
                ):
                    cleaned_lines.append("")

            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Dedent ASCII architecture blocks
    def dedent_code(match):
        block = match.group(0)
        m = re.match(r"^([ \t]+)```", block)
        if not m:
            return block
        indent_str = m.group(1)

        lines = block.split("\n")
        dedented = []
        for line in lines:
            if line.startswith(indent_str):
                dedented.append(line[len(indent_str) :])
            else:
                dedented.append(line)
        return "\n".join(dedented)

    text = re.sub(r"^[ \t]*```[\s\S]*?^[ \t]*```", dedent_code, text, flags=re.M)
    return text


# --- Main Logic ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to your Markdown file")
    parser.add_argument("--anki", action="store_true", help="Enable Anki .apkg generation")
    parser.add_argument("-n", "--name", help="Custom output filename")
    args = parser.parse_args()

    input_file = pathlib.Path(args.file).resolve()
    img_dir = input_file.parent / "attachments"
    output_stem = args.name if args.name else input_file.stem

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")

    md_exts = ["tables", "fenced_code", "sane_lists", "nl2br"]
    sections = re.split(r"^#\s+", content, flags=re.M)
    deck_data = {}
    pdf_qs, pdf_ans = [], []

    for section in sections:
        if not section.strip():
            continue
        lines = section.split("\n", 1)
        subdeck_name = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""

        matches = re.findall(r"^##\s*(.*?)\n(.*?)(?=\n##\s*|\Z)", body, re.M | re.S)
        if matches:
            rendered_pairs = []
            for q_raw, a_raw in matches:
                q_prep = preprocess_markdown(q_raw.strip())
                a_prep = preprocess_markdown(a_raw.strip())

                q_html = markdown.markdown(q_prep, extensions=md_exts)
                a_html = markdown.markdown(a_prep, extensions=md_exts)

                # Post-Process HTML: Scrub <br> tags injected by nl2br
                block_tags = r"ul|ol|li|table|thead|tbody|tr|td|th|pre|div|h[1-6]|p"
                for _ in range(2):
                    q_html = re.sub(rf"(</?(?:{block_tags})[^>]*>)\s*<br\s*/?>", r"\1", q_html)
                    a_html = re.sub(rf"(</?(?:{block_tags})[^>]*>)\s*<br\s*/?>", r"\1", a_html)
                    q_html = re.sub(rf"<br\s*/?>\s*(</?(?:{block_tags})[^>]*>)", r"\1", q_html)
                    a_html = re.sub(rf"<br\s*/?>\s*(</?(?:{block_tags})[^>]*>)", r"\1", a_html)

                rendered_pairs.append((q_html, a_html))

                pdf_qs.append(f"{q_raw.strip()}\n{len(pdf_qs) + 1}")
                pdf_ans.append(a_raw.strip())

            deck_data[subdeck_name] = rendered_pairs

    if args.anki:
        media = []
        if img_dir.exists():
            media = [
                str(img_dir / n) for n in _extract_image_names(content) if (img_dir / n).exists()
            ]

        apkg_path = input_file.with_name(f"{output_stem}.apkg")
        create_anki_deck(deck_data, output_stem, apkg_path, media)
        print(f"Erfolg! Anki-Deck erstellt: {apkg_path.name}")

    pdf_path = input_file.with_name(f"{output_stem}.pdf")
    create_pdf(pdf_qs, pdf_ans, pdf_path, img_dir)
    print(f"Erfolg! PDF erstellt: {pdf_path.name}")


if __name__ == "__main__":
    main()
