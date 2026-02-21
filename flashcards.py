#!/usr/bin/env python3
import argparse
import html
import pathlib
import re
from typing import List, Optional

import genanki
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")
ANKI_MODEL_ID = 1607392319
ANKI_DECK_ID = 2059400110


def create_anki_deck(questions, answers, deck_name, output_path, media_files):
    model = genanki.Model(
        ANKI_MODEL_ID,
        "Obsidian Unique Model",
        fields=[{"name": "Question"}, {"name": "Answer"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": '<div style="font-family: Arial; font-size: 20px; text-align: center;">{{Question}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div style="font-family: Arial; font-size: 16px; text-align: left; display: inline-block;">{{Answer}}</div>',
            }
        ],
        css=".card { text-align: center; color: black; background-color: white; } img { max-width: 100%; height: auto; }",
    )

    deck = genanki.Deck(ANKI_DECK_ID, deck_name)

    for i, (q, a) in enumerate(zip(questions, answers)):
        if not q.strip():
            continue

        q_safe = html.escape(q)
        a_safe = html.escape(a)

        def replace_with_img(match):
            img_name = match.group(1).split("|")[0]
            return f'<img src="{img_name}">'

        q_html = re.sub(r"!\[\[(.*?)(?:\|.*?)?\]\]", replace_with_img, q_safe)
        a_html = re.sub(r"!\[\[(.*?)(?:\|.*?)?\]\]", replace_with_img, a_safe)

        # ADDED HIDDEN PREFIX {i+1:04d} for strict Anki sorting
        q_final = f"<div style='display:none;'>{i + 1:04d}</div>{q_html.replace('\n', '<br>')}<br><br><span style='font-size: 10px; color: grey;'>ID: {i + 1}</span>"
        a_final = a_html.replace("\n", "<br>").replace("    ", "&nbsp;&nbsp;&nbsp;&nbsp;")

        note = genanki.Note(model=model, fields=[q_final, a_final])
        deck.add_note(note)

    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(output_path)


def _extract_image_names(text: str) -> List[str]:
    return [m.split("|")[0] for m in re.findall(r"!\[\[(.*?)(?:\|.*?)?\]\]", text)]


def _resolve_image_path(
    filename: str, images_dir: Optional[pathlib.Path]
) -> Optional[pathlib.Path]:
    if images_dir and (images_dir / filename).exists():
        return images_dir / filename
    return None


def wrap_line_with_indent(c, text, max_width, bullet_width):
    lines = []
    words = text.split()
    if not words:
        return [""]
    curr_line = []
    for i, word in enumerate(words):
        test_line = " ".join(curr_line + [word])
        eff_max = max_width if i == 0 else max_width - bullet_width
        if c.stringWidth(test_line) < eff_max:
            curr_line.append(word)
        else:
            lines.append(" ".join(curr_line))
            curr_line = [word]
    lines.append(" ".join(curr_line))
    return lines


def create_pdf(questions, answers, output_pdf, images_dir=None):
    c = canvas.Canvas(str(output_pdf), pagesize=landscape(A4))
    page_width, page_height = landscape(A4)
    margin = 0.25 * inch
    card_width, card_height = (page_width - 0.5 * inch) / 2, (page_height - 0.5 * inch) / 2

    def draw_page(c, items, is_question_side=True):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.lightgrey)
        for i, item in enumerate(items):
            if not item and not is_question_side:
                continue
            row, col = i // 2, i % 2
            x, y = (
                col * card_width + margin / 2,
                page_height - ((row + 1) * card_height) - margin / 2,
            )
            c.rect(x, y, card_width, card_height)

            img_names = _extract_image_names(item)
            if img_names:
                img_path = _resolve_image_path(img_names[0], images_dir)
                if img_path:
                    try:
                        c.drawImage(
                            str(img_path),
                            x + card_width * 0.075,
                            y + card_height * 0.075,
                            width=card_width * 0.85,
                            height=card_height * 0.85,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                        if is_question_side:
                            card_num = item.split("\n")[-1]
                            c.setFont("Helvetica", 9)
                            c.setFillColor(colors.grey)
                            c.drawCentredString(x + card_width / 2, y + 10, f"ID: {card_num}")
                            c.setFillColor(colors.black)
                        continue
                    except:
                        pass

            max_w = card_width - (margin * 2.5)
            if is_question_side:
                parts = item.split("\n")
                title_text, card_num = "\n".join(parts[:-1]), parts[-1]
                c.setFont("Helvetica-Bold", 14)
                wrapped_title = []
                for line in title_text.split("\n"):
                    words = line.split()
                    curr = []
                    for w in words:
                        if c.stringWidth(" ".join(curr + [w])) < max_w:
                            curr.append(w)
                        else:
                            wrapped_title.append(" ".join(curr))
                            curr = [w]
                    wrapped_title.append(" ".join(curr))
                line_h = 16
                curr_y = y + (card_height / 2) + ((len(wrapped_title) * line_h) / 2) - line_h
                c.setFillColor(colors.black)
                for line in wrapped_title:
                    c.drawCentredString(x + card_width / 2, curr_y, line)
                    curr_y -= line_h
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.grey)
                c.drawCentredString(x + card_width / 2, y + 10, f"ID: {card_num}")
            else:
                c.setFont("Helvetica", 9)
                lines = [l for l in item.split("\n") if l.strip()]
                if not lines:
                    continue
                indents = sorted(list(set(len(l) - len(l.lstrip()) for l in lines)))
                indent_map = {val: i for i, val in enumerate(indents)}
                processed = []
                for rl in lines:
                    depth = indent_map.get(len(rl) - len(rl.lstrip()), 0)
                    bullet = ["• ", "◦ ", "▪ ", "▫ "][min(depth, 3)]
                    clean_txt = rl.strip().lstrip("-* ")
                    wrapped = wrap_line_with_indent(c, clean_txt, max_w - (depth * 12), 8)
                    for idx, wl in enumerate(wrapped):
                        processed.append(
                            (depth * 12 + (8 if idx > 0 else 0), (bullet if idx == 0 else "") + wl)
                        )
                line_h = 10
                total_h = len(processed) * line_h
                curr_y = y + (card_height / 2) + (total_h / 2) - line_h
                max_list_w = 0
                for ind, txt in processed:
                    max_list_w = max(max_list_w, c.stringWidth(txt) + ind)
                start_x_base = x + (card_width - max_list_w) / 2
                c.setFillColor(colors.black)
                for indent, text in processed:
                    c.drawString(start_x_base + indent, curr_y, text)
                    curr_y -= line_h

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--anki", action="store_true")
    args = parser.parse_args()
    input_file = pathlib.Path(args.file).resolve()
    img_dir = input_file.parent / "attachments"
    with open(input_file, "r", encoding="utf-8") as f:
        matches = re.findall(r"^##\s*(.*?)\n(.*?)(?=\n##\s*|\Z)", f.read(), re.M | re.S)
    qs, ans = [m[0].strip() for m in matches], [m[1].strip() for m in matches]
    if args.anki:
        all_text = " ".join(qs + ans)
        media = [str(img_dir / n) for n in _extract_image_names(all_text) if (img_dir / n).exists()]
        create_anki_deck(qs, ans, input_file.stem, input_file.with_suffix(".apkg"), media)
    pdf_q = [f"{q}\n{i + 1}" for i, q in enumerate(qs)]
    create_pdf(pdf_q, ans, input_file.with_suffix(".pdf"), img_dir)
    print(f"Erfolg! PDF erstellt: {input_file.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()
