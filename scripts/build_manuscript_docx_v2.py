#!/usr/bin/env python3
"""Build the anonymous journal manuscript as a publication-ready DOCX (v2).

Differences from build_manuscript_docx.py:
- Self-contained footnote insertion (no external insert_note.py dependency):
  [[FNxxx]] markers become real Word footnotes via direct OOXML surgery.
- Renders the new inference tables: TABLE3 (within-party contrasts with exact
  odds ratios and CIs, from results/extended/ext_C_contrasts_enriched.csv) and
  TABLE4 (negative binomial + OLS view models, from
  results/extended/ext_E_view_models.csv).
- Renders FIGURE4 (odds-ratio forest plot) as 图3.

Usage: build_manuscript_docx_v2.py OUTPUT.docx
"""

from __future__ import annotations

import csv
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "manuscript.md"
RESULTS = ROOT / "results"
EXT = RESULTS / "extended"
FIGURES = RESULTS / "figures"
WORK = ROOT / "work"

ACCOUNT_ORDER = ["dnc", "harris", "rnc", "trump"]
ACCOUNT_LABEL = {"dnc": "DNC", "harris": "Harris", "rnc": "RNC", "trump": "Trump"}

SIGNAL_ORDER = [
    "opponent_reference",
    "attack_signal",
    "mobilization_signal",
    "policy_signal",
    "personal_signal",
    "endorsement_signal",
    "first_person_signal",
]
SIGNAL_LABEL = {
    "opponent_reference": "对手指涉",
    "attack_signal": "攻击",
    "mobilization_signal": "动员",
    "policy_signal": "政策",
    "personal_signal": "私人／日常",
    "endorsement_signal": "背书",
    "first_person_signal": "第一人称",
}
TERM_LABEL = {
    "Intercept": "截距",
    "C(party)[T.Republican]": "共和党",
    "C(actor_type)[T.party]": "党组织账号",
    "C(party)[T.Republican]:C(actor_type)[T.party]": "共和党×党组织账号",
    "opponent_reference": "对手指涉",
    "mobilization_signal": "动员",
    "policy_signal": "政策",
    "personal_signal": "私人／日常",
    "endorsement_signal": "背书",
    "duration_seconds": "时长（秒）",
    "day_index": "发布日序",
}


def set_run_font(run, east_asia="宋体", latin="Times New Roman", size=10.5, bold=None, italic=None):
    run.font.name = latin
    run.font.size = Pt(size)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        # schema order: shd precedes noWrap/tcMar/textDirection/tcFitText/vAlign
        successor = None
        for tag in ("w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark"):
            successor = tc_pr.find(qn(tag))
            if successor is not None:
                break
        if successor is not None:
            successor.addprevious(shd)
        else:
            tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=60, start=80, bottom=60, end=80):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        # schema order: tcMar must precede textDirection/tcFitText/vAlign/hideMark
        successor = None
        for tag in ("w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark"):
            successor = tc_pr.find(qn(tag))
            if successor is not None:
                break
        if successor is not None:
            successor.addprevious(tc_mar)
        else:
            tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_table_borders(table, color="666666", size="6"):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        # schema order: tblBorders precedes shd/tblLayout/tblCellMar/tblLook
        successor = None
        for tag in ("w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription"):
            successor = tbl_pr.find(qn(tag))
            if successor is not None:
                break
        if successor is not None:
            successor.addprevious(borders)
        else:
            tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_begin, instr, fld_sep, fld_end])
    set_run_font(run, size=9)


def setup_styles(doc):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    pf = normal.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(18)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.first_line_indent = Pt(21)

    title = styles["Title"]
    title.font.name = "Times New Roman"
    title.font.size = Pt(18)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0, 0, 0)
    title._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
    title_ppr = title._element.get_or_add_pPr()
    title_border = title_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_ppr.remove(title_border)
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    title.paragraph_format.keep_with_next = True

    for name, size in (("Heading 1", 14), ("Heading 2", 12)):
        style = styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        style.paragraph_format.space_before = Pt(10 if name == "Heading 1" else 6)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.first_line_indent = Pt(0)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        style.paragraph_format.line_spacing = Pt(18)


def configure_section(section):
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.3)
    section.left_margin = Cm(2.55)
    section.right_margin = Cm(2.55)
    section.header_distance = Cm(1.0)
    section.footer_distance = Cm(1.1)


INLINE_RE = re.compile(r"(\*\*.*?\*\*|\*.*?\*|\[\[FN\d{3}\]\])")


def add_inline(paragraph, text, default_size=10.5):
    for part in INLINE_RE.split(text):
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        italic = not bold and part.startswith("*") and part.endswith("*")
        content = part[2:-2] if bold else part[1:-1] if italic else part
        run = paragraph.add_run(content)
        set_run_font(run, size=default_size, bold=bold if bold else None, italic=italic if italic else None)


def add_table_title(doc, number, title):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(f"表{number}  {title}")
    set_run_font(run, east_asia="黑体", size=10.5, bold=True)


def add_table_note(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run("注：" + text)
    set_run_font(r, size=8.5)


def format_table(table, widths=None):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    set_repeat_table_header(table.rows[0])
    for ri, row in enumerate(table.rows):
        for ci, cell in enumerate(row.cells):
            if widths:
                cell.width = Cm(widths[ci])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            if ri == 0:
                set_cell_shading(cell, "E7E7E7")
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.first_line_indent = Pt(0)
                p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                for run in p.runs:
                    set_run_font(run, size=8.5, bold=(ri == 0))


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt_p(p: float) -> str:
    if p < 0.001:
        return "＜0.001"
    return f"{p:.3f}"


def fmt_or(v: float) -> str:
    if v == 0:
        return "0"
    if v >= 100:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    if v < 0.01:
        return f"{v:.3f}"
    return f"{v:.2f}"


def fmt_ci(lo: float, hi: float) -> str:
    return f"[{fmt_or(lo)}, {fmt_or(hi)}]"


DICT_TABLE_ROWS = [
    ("对手指涉", "标题出现对方阵营候选人或政党指涉词",
     "民主党账号：Trump, (JD) Vance, MAGA, Republicans, GOP, Project 2025；共和党账号：Kamala (Harris), (Tim) Walz, (Joe) Biden, Democrats, DNC"),
    ("攻击", "对手指涉词与否定词同现（两者相乘）",
     "否定词如lie/lying, fraud, fail(ed), radical, dangerous, crisis, disaster, worst, corrupt, weak, refuse, unfit"),
    ("自方指涉", "标题出现本方候选人或政党指涉词",
     "民主党账号：Kamala Harris, (Tim) Walz, Democrats, President Biden；共和党账号：(Donald) Trump, (JD) Vance, Republicans, GOP, MAGA"),
    ("动员", "出现投票、捐款或参与号召词",
     "vote/voting, register, make your plan, plan to vote, join us, donate, chip in"),
    ("政策", "出现政策议题词",
     "economy, prices, tax(es), jobs, Medicare, Social Security, health care, abortion, border, immigration, crime, energy, democracy, Ukraine, Israel"),
    ("私人／日常", "出现家庭、饮食等私人生活词",
     "family, mom(ala), dad, husband, Doug, baby, recipe, food, sweet treat"),
    ("背书", "出现背书动词或背书者姓名",
     "endorse(ment), back(s), support, listen to；Barack/Michelle Obama, Jennifer Lopez, Bruce Springsteen, Anuel AA, Tulsi, RFK"),
    ("幽默", "出现幽默、玩梗词", "lol, meme, joke, word salad"),
    ("第一人称", "出现第一人称代词", "I, I'm, me, my, we, we're, our, us"),
]


def add_table_dictionary(doc):
    add_table_title(doc, 1, "九个标题信号的判定规则与核心词典（节选）")
    headers = ["标题信号", "判定规则", "核心词例"]
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for label, rule, terms in DICT_TABLE_ROWS:
        cells = table.add_row().cells
        for cell, value in zip(cells, [label, rule, terms]):
            cell.text = value
    format_table(table, [2.0, 4.2, 9.6])
    for row in table.rows[1:]:
        for cell in (row.cells[1], row.cells[2]):
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_table_note(
        doc,
        "词例为词典节选；实际匹配使用完整词典与正则表达式（含词形变化与词界约束），逐条匹配结果与全部规则随复现材料公开。"
        "攻击信号要求标题同时命中对手指涉词与否定词；同一标题可命中多个信号。",
    )


def add_table1(doc):
    rows = {}
    for row in read_csv(RESULTS / "table1_descriptive.csv"):
        rows[row["account_slug"]] = row
    add_table_title(doc, 2, "四个官方账号的样本与累计平台指标")
    headers = ["账号", "角色", "样本量", "日均发布", "时长中位数（秒）", "观看中位数", "点赞率中位数", "评论率中位数"]
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for slug in ACCOUNT_ORDER:
        x = rows[slug]
        vals = [
            ACCOUNT_LABEL[slug],
            "党组织" if x["actor_type"] == "party" else "候选人",
            x["n"],
            f'{float(x["posts_per_day"]):.2f}',
            f'{float(x["duration_median"]):.0f}',
            f'{float(x["views_median"]):,.0f}',
            f'{float(x["like_rate_median"])*100:.2f}%',
            f'{float(x["comment_rate_median"])*100:.2f}%',
        ]
        cells = table.add_row().cells
        for cell, value in zip(cells, vals):
            cell.text = value
    format_table(table, [1.4, 1.5, 1.2, 1.5, 2.0, 2.1, 2.1, 2.1])
    add_table_note(doc, "观看、点赞和评论为2026年8月24日抓取时点累计值；点赞率和评论率分别以观看数为分母。")


def add_table2(doc):
    wanted = [
        ("opponent_reference", "对手指涉"),
        ("attack_signal", "攻击"),
        ("mobilization_signal", "动员"),
        ("policy_signal", "政策"),
        ("personal_signal", "私人／日常"),
        ("endorsement_signal", "背书"),
        ("first_person_signal", "第一人称"),
    ]
    values = {}
    for row in read_csv(RESULTS / "table2_text_signals.csv"):
        values[(row["account_slug"], row["signal"])] = float(row["proportion"]) * 100
    add_table_title(doc, 3, "四个官方账号标题信号比例（%）")
    headers = ["标题信号", "DNC", "Harris", "RNC", "Trump"]
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for key, label in wanted:
        cells = table.add_row().cells
        vals = [label] + [f"{values[(slug, key)]:.1f}" for slug in ACCOUNT_ORDER]
        for cell, value in zip(cells, vals):
            cell.text = value
    format_table(table, [3.1, 2.8, 2.8, 2.8, 2.8])
    add_table_note(doc, "同一标题可同时命中多个信号。词典规则见随稿数据说明；比例不代表完整视频语义编码。")


def add_table3(doc):
    data = read_csv(EXT / "ext_C_contrasts_enriched.csv")
    idx = {(r["party"], r["variable"]): r for r in data}
    add_table_title(doc, 4, "阵营内“党组织—候选人”标题信号对比：效应量与确切检验")
    headers = ["标题信号", "阵营", "党组织（%）", "候选人（%）", "风险差（百分点）", "确切OR", "OR的95%CI", "校正p"]
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for party, party_label in [("Democratic", "民主党"), ("Republican", "共和党")]:
        for sig in SIGNAL_ORDER:
            r = idx[(party, sig)]
            cells = table.add_row().cells
            vals = [
                SIGNAL_LABEL[sig],
                party_label,
                f'{float(r["party_prop"])*100:.1f}',
                f'{float(r["candidate_prop"])*100:.1f}',
                f'{float(r["risk_diff"])*100:.1f}',
                fmt_or(float(r["odds_ratio_cmle"])),
                fmt_ci(float(r["or_ci_low"]), float(r["or_ci_high"])),
                fmt_p(float(r["p_adjust_bh"])),
            ]
            for cell, value in zip(cells, vals):
                cell.text = value
    format_table(table, [2.2, 1.5, 1.8, 1.8, 2.2, 1.5, 2.7, 1.6])
    add_table_note(
        doc,
        "OR为党组织账号相对候选人账号的条件最大似然比值比，区间为95%确切置信区间；OR＝0表示党组织账号无命中。"
        "校正p为Benjamini—Hochberg方法在20项比较族（含观看数、点赞率与评论率检验）内的校正值。风险差＝党组织比例−候选人比例。",
    )


def add_table4(doc):
    data = read_csv(EXT / "ext_E_view_models.csv")
    add_table_title(doc, 5, "累计观看数的负二项回归与对数观看OLS")
    headers = ["变量", "NB发生率比", "NB的95%CI", "NB p", "OLS系数", "OLS的95%CI", "OLS p"]
    table = doc.add_table(rows=1, cols=len(headers))
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for r in data:
        term = r["term"]
        label = TERM_LABEL.get(term, term)
        irr = float(r["nb_irr"])
        irr_str = f"{irr:,.0f}" if irr >= 1000 else f"{irr:.3f}" if irr < 0.1 else fmt_or(irr)
        lo, hi = float(r["nb_irr_ci_low"]), float(r["nb_irr_ci_high"])
        ci_str = (
            f"[{lo:,.0f}, {hi:,.0f}]" if hi >= 1000 else f"[{lo:.3f}, {hi:.3f}]" if hi < 0.1 else fmt_ci(lo, hi)
        )
        cells = table.add_row().cells
        vals = [
            label,
            irr_str,
            ci_str,
            fmt_p(float(r["nb_p"])),
            f'{float(r["ols_coef"]):.3f}',
            f'[{float(r["ols_ci_low"]):.3f}, {float(r["ols_ci_high"]):.3f}]',
            fmt_p(float(r["ols_p"])),
        ]
        for cell, value in zip(cells, vals):
            cell.text = value
    format_table(table, [2.9, 1.9, 2.6, 1.5, 1.6, 2.9, 1.5])
    add_table_note(
        doc,
        "n＝363。NB为NB2负二项回归（HC1稳健标准误），离散参数α＝1.13（95%CI：0.97—1.30）；OLS因变量为log(1＋观看数)"
        "（HC3稳健标准误），R²＝0.844。“党派×角色”组合饱和四个账号，等价于账号固定效应；因同日抓取，控制发布日序即控制曝光时长。"
        "中位数回归与泊松QMLE的方向和显著性形态一致，见复现材料。截距为基线组（民主党候选人账号、各信号为0、时长与日序为0）的条件期望。",
    )


def add_figure(doc, number, filename, caption, note):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(FIGURES / filename), width=Cm(15.6))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.first_line_indent = Pt(0)
    cap.paragraph_format.space_before = Pt(2)
    cap.paragraph_format.space_after = Pt(1)
    cap.paragraph_format.keep_with_next = True
    r = cap.add_run(f"图{number}  {caption}")
    set_run_font(r, east_asia="黑体", size=9.5, bold=True)
    add_table_note(doc, note)


def add_body_paragraph(doc, text, kind="body"):
    p = doc.add_paragraph()
    if kind == "abstract":
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.left_indent = Pt(10.5)
        p.paragraph_format.right_indent = Pt(10.5)
        p.paragraph_format.space_after = Pt(3)
    elif kind == "keywords":
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.left_indent = Pt(10.5)
        p.paragraph_format.right_indent = Pt(10.5)
        p.paragraph_format.space_after = Pt(6)
    elif kind == "rq":
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.left_indent = Pt(21)
        p.paragraph_format.space_after = Pt(2)
    elif kind == "reference":
        p.paragraph_format.first_line_indent = Pt(-18)
        p.paragraph_format.left_indent = Pt(18)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(15)
        p.paragraph_format.space_after = Pt(2)
    elif kind == "english":
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(16)
        p.paragraph_format.space_after = Pt(4)
    add_inline(p, text, default_size=9.5 if kind in {"abstract", "keywords", "reference", "english"} else 10.5)
    return p


def parse_source():
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    notes = {}
    body = []
    for line in lines:
        m = re.match(r"^\[\[FN(\d{3})\]\]\s+(.*)$", line)
        if m:
            notes[f"[[FN{m.group(1)}]]"] = m.group(2)
        else:
            body.append(line)
    return body, notes


def build_base(out_path):
    doc = Document()
    configure_section(doc.sections[0])
    setup_styles(doc)
    add_page_number(doc.sections[0].footer.paragraphs[0])
    body, notes = parse_source()
    in_references = False
    in_english = False

    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line == "[[TABLE1]]":
            add_table_dictionary(doc)
            continue
        if line == "[[TABLE2]]":
            add_table1(doc)
            continue
        if line == "[[TABLE3]]":
            add_table2(doc)
            continue
        if line == "[[TABLE4]]":
            add_table3(doc)
            continue
        if line == "[[TABLE5]]":
            add_table4(doc)
            continue
        if line == "[[FIGURE1]]":
            add_figure(doc, 1, "figure1_output_and_attention.png", "样本期发布量与单条累计观看中位数", "右图使用对数坐标；累计观看为2026年8月24日抓取值。")
            continue
        if line == "[[FIGURE2]]":
            add_figure(doc, 2, "figure2_lexical_signal_heatmap.png", "四账号标题中的可复核传播信号", "数值为各账号标题命中固定词典的比例；同一标题可同时命中多个信号。")
            continue
        if line == "[[FIGURE4]]":
            add_figure(
                doc,
                3,
                "figure4_or_forest.png",
                "党组织账号相对候选人账号的标题信号比值比",
                "横轴为对数坐标，区间为95%确切置信区间；深色加粗线表示Benjamini—Hochberg校正后p＜0.05；OR＝0（党组织账号无命中）绘于坐标下限。数值见表4。",
            )
            continue
        if line.startswith("# "):
            p = doc.add_paragraph(style="Title")
            p.paragraph_format.first_line_indent = Pt(0)
            add_inline(p, line[2:], default_size=18)
            continue
        if line.startswith("## ——"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_after = Pt(10)
            p.paragraph_format.keep_with_next = True
            r = p.add_run(line[3:])
            set_run_font(r, east_asia="黑体", size=13, bold=True)
            continue
        if line.startswith("## "):
            heading = line[3:]
            in_references = heading == "参考文献"
            in_english = heading == "English Title and Abstract"
            doc.add_paragraph(heading, style="Heading 1")
            continue
        if line.startswith("### "):
            doc.add_paragraph(line[4:], style="Heading 2")
            continue
        if line.startswith("**内容提要：**"):
            add_body_paragraph(doc, line, "abstract")
            continue
        if line.startswith("**关键词：**"):
            add_body_paragraph(doc, line, "keywords")
            continue
        if re.match(r"^RQ\d：", line):
            add_body_paragraph(doc, line, "rq")
            continue
        if in_references and re.match(r"^\d+\.\s", line):
            add_body_paragraph(doc, line, "reference")
            continue
        if in_english:
            p = add_body_paragraph(doc, line, "english")
            if line.startswith("**Has the Party"):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.bold = True
                    run.font.size = Pt(11)
            continue
        add_body_paragraph(doc, line)

    props = doc.core_properties
    props.title = "党组织退场了吗？平台化竞选中的“政党—候选人”传播分工"
    props.subject = "匿名投稿稿件"
    props.author = ""
    props.last_modified_by = ""
    props.comments = ""
    doc.save(out_path)
    return notes


# ------------------------------------------------------------ footnotes ----

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
FOOTNOTES_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
FOOTNOTES_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"


def _w(tag):
    return f"{{{W_NS}}}{tag}"


def build_footnotes_xml(notes: dict[str, str], marker_order: list[str]) -> bytes:
    """Write footnotes in document-order ids (1..N following marker_order)."""
    from lxml import etree

    root = etree.Element(_w("footnotes"), nsmap={"w": W_NS})
    for special_id, special_tag in ((-1, "separator"), (0, "continuationSeparator")):
        fn = etree.SubElement(root, _w("footnote"))
        fn.set(_w("type"), "separator" if special_id == -1 else "continuationSeparator")
        fn.set(_w("id"), str(special_id))
        p = etree.SubElement(fn, _w("p"))
        ppr = etree.SubElement(p, _w("pPr"))
        spacing = etree.SubElement(ppr, _w("spacing"))
        spacing.set(_w("after"), "0")
        spacing.set(_w("line"), "240")
        spacing.set(_w("lineRule"), "auto")
        run = etree.SubElement(p, _w("r"))
        etree.SubElement(run, _w(special_tag))
    ordered = [(marker, notes[marker]) for marker in marker_order]
    for i, (_, text) in enumerate(ordered, start=1):
        fn = etree.SubElement(root, _w("footnote"))
        fn.set(_w("id"), str(i))
        p = etree.SubElement(fn, _w("p"))
        ppr = etree.SubElement(p, _w("pPr"))
        spacing = etree.SubElement(ppr, _w("spacing"))
        spacing.set(_w("after"), "0")
        spacing.set(_w("line"), "220")
        spacing.set(_w("lineRule"), "exact")
        ind = etree.SubElement(ppr, _w("ind"))
        ind.set(_w("firstLine"), "200")
        ref_run = etree.SubElement(p, _w("r"))
        etree.SubElement(ref_run, _w("footnoteRef"))
        sp_run = etree.SubElement(p, _w("r"))
        sp_t = etree.SubElement(sp_run, _w("t"))
        sp_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        sp_t.text = " "
        txt_run = etree.SubElement(p, _w("r"))
        txt = etree.SubElement(txt_run, _w("t"))
        txt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        txt.text = text
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def inject_footnotes(docx_path: Path, notes: dict[str, str]) -> None:
    from lxml import etree

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with zipfile.ZipFile(docx_path, "r") as zin:
            zin.extractall(tmp)

        # Assign footnote ids by order of appearance in the document, so that
        # renderers that pair references and notes positionally stay correct.
        doc_path = tmp / "word" / "document.xml"
        dtree = etree.parse(str(doc_path))
        droot = dtree.getroot()
        marker_order: list[str] = []
        for t in droot.iter(_w("t")):
            text = t.text or ""
            if text in notes and text not in marker_order:
                marker_order.append(text)
        missing_markers = set(notes) - set(marker_order)
        if missing_markers:
            raise RuntimeError(f"Footnote markers not found in document: {sorted(missing_markers)}")
        marker_ids = {marker: i for i, marker in enumerate(marker_order, start=1)}

        (tmp / "word" / "footnotes.xml").write_bytes(build_footnotes_xml(notes, marker_order))

        ct_path = tmp / "[Content_Types].xml"
        ct_tree = etree.parse(str(ct_path))
        ct_root = ct_tree.getroot()
        if not any(
            el.get("PartName") == "/word/footnotes.xml"
            for el in ct_root.findall(f"{{{CT_NS}}}Override")
        ):
            override = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
            override.set("PartName", "/word/footnotes.xml")
            override.set("ContentType", FOOTNOTES_CT)
        ct_tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        rels_path = tmp / "word" / "_rels" / "document.xml.rels"
        rels_tree = etree.parse(str(rels_path))
        rels_root = rels_tree.getroot()
        pkg_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        existing_ids = {el.get("Id") for el in rels_root.findall(f"{{{pkg_ns}}}Relationship")}
        n = 1
        while f"rId{n}" in existing_ids:
            n += 1
        rel = etree.SubElement(rels_root, f"{{{pkg_ns}}}Relationship")
        rel.set("Id", f"rId{n}")
        rel.set("Type", FOOTNOTES_REL)
        rel.set("Target", "footnotes.xml")
        rels_tree.write(str(rels_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        doc_path = tmp / "word" / "document.xml"
        dtree = etree.parse(str(doc_path))
        droot = dtree.getroot()
        replaced = set()
        for t in droot.iter(_w("t")):
            text = t.text or ""
            if text in marker_ids:
                run = t.getparent()
                rpr = etree.Element(_w("rPr"))
                vert = etree.SubElement(rpr, _w("vertAlign"))
                vert.set(_w("val"), "superscript")
                new_run = etree.Element(_w("r"))
                new_run.append(rpr)
                ref = etree.SubElement(new_run, _w("footnoteReference"))
                ref.set(_w("id"), str(marker_ids[text]))
                run.getparent().replace(run, new_run)
                replaced.add(text)
        missing = set(marker_ids) - replaced
        if missing:
            raise RuntimeError(f"Footnote markers not found in document: {sorted(missing)}")
        dtree.write(str(doc_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        rebuilt = docx_path.with_suffix(".fn.docx")
        with zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as zout:
            for path in tmp.rglob("*"):
                if path.is_file():
                    zout.write(path, path.relative_to(tmp).as_posix())
        rebuilt.replace(docx_path)


def patch_footnotes(docx_path: Path) -> None:
    """Per-page footnote numbering + superscript refs + fonts (as v1)."""
    from lxml import etree

    ns = {"w": W_NS}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with zipfile.ZipFile(docx_path, "r") as zin:
            zin.extractall(tmp)

        settings_path = tmp / "word" / "settings.xml"
        tree = etree.parse(str(settings_path))
        root = tree.getroot()
        zoom = root.find("w:zoom", ns)
        if zoom is not None and zoom.get(f"{{{W_NS}}}percent") is None:
            zoom.set(f"{{{W_NS}}}percent", "100")
        footnote_pr = root.find("w:footnotePr", ns)
        if footnote_pr is None:
            footnote_pr = etree.Element(f"{{{W_NS}}}footnotePr")
            # schema order: footnotePr precedes endnotePr/compat/rsids
            successor = None
            for tag in ("w:endnotePr", "w:compat", "w:rsids"):
                successor = root.find(tag, ns)
                if successor is not None:
                    break
            if successor is not None:
                successor.addprevious(footnote_pr)
            else:
                root.append(footnote_pr)
        restart = footnote_pr.find("w:numRestart", ns)
        if restart is None:
            restart = etree.SubElement(footnote_pr, f"{{{W_NS}}}numRestart")
        restart.set(f"{{{W_NS}}}val", "eachPage")
        tree.write(str(settings_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        footnotes_path = tmp / "word" / "footnotes.xml"
        if footnotes_path.exists():
            ftree = etree.parse(str(footnotes_path))
            froot = ftree.getroot()
            for run in froot.xpath(".//w:r", namespaces=ns):
                rpr = run.find("w:rPr", ns)
                if rpr is None:
                    rpr = etree.Element(f"{{{W_NS}}}rPr")
                    run.insert(0, rpr)
                rfonts = rpr.find("w:rFonts", ns)
                if rfonts is None:
                    rfonts = etree.SubElement(rpr, f"{{{W_NS}}}rFonts")
                rfonts.set(f"{{{W_NS}}}ascii", "Times New Roman")
                rfonts.set(f"{{{W_NS}}}hAnsi", "Times New Roman")
                rfonts.set(f"{{{W_NS}}}eastAsia", "宋体")
                sz = rpr.find("w:sz", ns)
                if sz is None:
                    sz = etree.SubElement(rpr, f"{{{W_NS}}}sz")
                sz.set(f"{{{W_NS}}}val", "18")
                szcs = rpr.find("w:szCs", ns)
                if szcs is None:
                    szcs = etree.SubElement(rpr, f"{{{W_NS}}}szCs")
                szcs.set(f"{{{W_NS}}}val", "18")
                if run.find("w:footnoteRef", ns) is not None:
                    vert = rpr.find("w:vertAlign", ns)
                    if vert is None:
                        vert = etree.SubElement(rpr, f"{{{W_NS}}}vertAlign")
                    vert.set(f"{{{W_NS}}}val", "superscript")
            ftree.write(str(footnotes_path), xml_declaration=True, encoding="UTF-8", standalone=True)

        rebuilt = docx_path.with_suffix(".patched.docx")
        with zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as zout:
            for path in tmp.rglob("*"):
                if path.is_file():
                    zout.write(path, path.relative_to(tmp).as_posix())
        rebuilt.replace(docx_path)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: build_manuscript_docx_v2.py OUTPUT.docx")
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(exist_ok=True)
    base = WORK / "manuscript_v2_base.docx"
    notes = build_base(base)
    shutil.copy2(base, output)
    inject_footnotes(output, notes)
    patch_footnotes(output)
    print(f"Created {output}")
    print(f"Footnotes inserted: {len(notes)}")


if __name__ == "__main__":
    main()
