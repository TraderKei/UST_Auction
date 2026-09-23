"""Render the QRA document/data ERD as a high-resolution PNG."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "qra-document-data-erd.png"

WIDTH = 1800
HEIGHT = 2480

BACKGROUND = "#f7f9fc"
INK = "#142033"
MUTED = "#607089"
LINE = "#6b7f99"
UPSTREAM_FILL = "#edf4ff"
UPSTREAM_BORDER = "#5275a3"
ROOT_FILL = "#0f766e"
ROOT_BORDER = "#0b5f59"
CHILD_FILL = "#ffffff"
CHILD_BORDER = "#70839b"
SURVEY_FILL = "#fff7ed"
SURVEY_BORDER = "#c45d22"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


FONT_KR_BOLD = font(r"C:\Windows\Fonts\malgunbd.ttf", 68)
FONT_KR = font(r"C:\Windows\Fonts\malgun.ttf", 31)
FONT_NODE = font(r"C:\Windows\Fonts\segoeuib.ttf", 43)
FONT_ROOT = font(r"C:\Windows\Fonts\segoeuib.ttf", 46)
FONT_EDGE = font(r"C:\Windows\Fonts\segoeuib.ttf", 29)
FONT_SECTION = font(r"C:\Windows\Fonts\malgunbd.ttf", 35)
FONT_FOOTER = font(r"C:\Windows\Fonts\malgun.ttf", 25)


image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
draw = ImageDraw.Draw(image)


def centered_text(box: tuple[int, int, int, int], text: str, text_font, fill: str) -> None:
    x1, y1, x2, y2 = box
    bounds = draw.textbbox((0, 0), text, font=text_font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = x1 + (x2 - x1 - text_width) / 2
    y = y1 + (y2 - y1 - text_height) / 2 - bounds[1]
    draw.text((x, y), text, font=text_font, fill=fill)


def node(
    box: tuple[int, int, int, int],
    text: str,
    *,
    fill: str = CHILD_FILL,
    border: str = CHILD_BORDER,
    text_fill: str = INK,
    text_font=FONT_NODE,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(
        (x1 + 7, y1 + 10, x2 + 7, y2 + 10),
        radius=23,
        fill="#dfe5ed",
    )
    draw.rounded_rectangle(
        box,
        radius=23,
        fill=fill,
        outline=border,
        width=4,
    )
    centered_text(box, text, text_font, text_fill)


def edge_label(x: int, y: int, text: str) -> None:
    bounds = draw.textbbox((0, 0), text, font=FONT_EDGE)
    padding_x = 17
    padding_y = 9
    width = bounds[2] - bounds[0] + padding_x * 2
    height = bounds[3] - bounds[1] + padding_y * 2
    box = (x - width // 2, y - height // 2, x + width // 2, y + height // 2)
    draw.rounded_rectangle(box, radius=height // 2, fill="#e8eef6")
    centered_text(box, text, FONT_EDGE, MUTED)


def line(points: list[tuple[int, int]], *, color: str = LINE, width: int = 5) -> None:
    draw.line(points, fill=color, width=width, joint="curve")


title_bounds = draw.textbbox((0, 0), "QRA 문서–데이터 ERD", font=FONT_KR_BOLD)
draw.text(
    ((WIDTH - (title_bounds[2] - title_bounds[0])) / 2, 57),
    "QRA 문서–데이터 ERD",
    font=FONT_KR_BOLD,
    fill=INK,
)

subtitle = "문서 계보와 문서 버전이 지원하는 데이터셋"
subtitle_bounds = draw.textbbox((0, 0), subtitle, font=FONT_KR)
draw.text(
    ((WIDTH - (subtitle_bounds[2] - subtitle_bounds[0])) / 2, 150),
    subtitle,
    font=FONT_KR,
    fill=MUTED,
)

# Upstream document lineage.
refunding = (90, 280, 570, 410)
document = (690, 280, 1170, 410)
snapshot = (90, 565, 570, 695)
version = (690, 555, 1280, 705)

line([(570, 345), (690, 345)])
line([(930, 410), (930, 555)])
line([(570, 630), (690, 630)])

edge_label(630, 250, "publishes · 1:N")
edge_label(1050, 482, "versions · 1:N")
edge_label(630, 535, "preserves · 1:N")

node(refunding, "qra_refunding", fill=UPSTREAM_FILL, border=UPSTREAM_BORDER)
node(document, "qra_document", fill=UPSTREAM_FILL, border=UPSTREAM_BORDER)
node(snapshot, "source_snapshot", fill=UPSTREAM_FILL, border=UPSTREAM_BORDER)
node(
    version,
    "qra_document_version",
    fill=ROOT_FILL,
    border=ROOT_BORDER,
    text_fill="#ffffff",
    text_font=FONT_ROOT,
)

# Downstream supported datasets. A single labelled bus keeps the repeated
# qra_document_version ||--o{ child : supports relationships readable.
draw.text((130, 775), "지원 데이터셋", font=FONT_SECTION, fill=INK)
draw.text((410, 784), "qra_document_version supports · 1:N", font=FONT_EDGE, fill=MUTED)

left_x1, left_x2 = 130, 825
right_x1, right_x2 = 975, 1670
node_height = 125
row_y = [920, 1175, 1430, 1685, 1940]

left_nodes = [
    "qra_supply",
    "qra_auction_size",
    "qra_financing_mix",
    "qra_tentative_auction",
    "qra_buyback_policy",
]
right_nodes = [
    "qra_borrowing_estimate",
    "qra_tga_path",
    "qra_guidance",
    "qra_buyback_operation",
    "qra_dealer_survey",
]

root_x = (version[0] + version[2]) // 2
left_rail = 70
right_rail = 1730
bus_y = 855
last_center_y = row_y[-1] + node_height // 2

line([(root_x, version[3]), (root_x, bus_y)])
line([(left_rail, bus_y), (right_rail, bus_y)])
line([(left_rail, bus_y), (left_rail, last_center_y)])
line([(right_rail, bus_y), (right_rail, last_center_y)])

for y, left_name, right_name in zip(row_y, left_nodes, right_nodes):
    center_y = y + node_height // 2
    line([(left_rail, center_y), (left_x1, center_y)])
    line([(right_x2, center_y), (right_rail, center_y)])
    node((left_x1, y, left_x2, y + node_height), left_name)
    right_fill = SURVEY_FILL if right_name == "qra_dealer_survey" else CHILD_FILL
    right_border = SURVEY_BORDER if right_name == "qra_dealer_survey" else CHILD_BORDER
    node(
        (right_x1, y, right_x2, y + node_height),
        right_name,
        fill=right_fill,
        border=right_border,
    )

# Dealer survey cells are a child of qra_dealer_survey, not of the document version.
survey_value = (975, 2220, 1670, 2345)
line([(1322, 2065), (1322, 2220)], color=SURVEY_BORDER)
edge_label(1460, 2143, "cells · 1:N")
node(
    survey_value,
    "qra_dealer_survey_value",
    fill=SURVEY_FILL,
    border=SURVEY_BORDER,
)

footer = "관계 표기  1:N = 한 상위 레코드에 여러 하위 레코드"
draw.text((130, 2400), footer, font=FONT_FOOTER, fill=MUTED)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUTPUT, format="PNG", optimize=True, dpi=(144, 144))
print(f"saved: {OUTPUT}")
print(f"size: {image.width}x{image.height}")
