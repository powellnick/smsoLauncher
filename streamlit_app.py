import re
import pandas as pd
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
import io
import streamlit as st

st.set_page_config(page_title="Schedule Builder", layout="wide")

def find_header_row(df):
    hits = df.apply(lambda r: r.astype(str).str.contains("Associate Name", na=False)).any(axis=1)
    idxs = list(df.index[hits])
    return idxs[0] if idxs else None

def load_rostered_sheet(xlsx_bytes):
    xls = pd.ExcelFile(io.BytesIO(xlsx_bytes))
    target = None
    for name in xls.sheet_names:
        if "Rostered" in name or "Work Blocks" in name:
            target = name
            break
    if target is None:
        target = xls.sheet_names[0]
    df_raw = pd.read_excel(xls, sheet_name=target, header=None)
    hdr_i = find_header_row(df_raw)
    if hdr_i is None:
        raise ValueError("Couldn't find 'Associate Name' header row.")
    headers = df_raw.iloc[hdr_i].tolist()
    df = df_raw.iloc[hdr_i+1:].copy()
    df.columns = headers
    df = df.dropna(how="all")
    weekday_cols = [c for c in df.columns if isinstance(c,str) and re.search(r'(Sun|Mon|Tue|Wed|Thu|Fri|Sat)', c)]
    use = df[["Associate Name"] + weekday_cols].copy()
    return use, weekday_cols

def parse_day(df_use, day_key):
    cols = [c for c in df_use.columns if isinstance(c,str) and c.startswith(day_key)]
    if not cols:
        cols = [c for c in df_use.columns if isinstance(c,str) and day_key in c]
    if not cols:
        return []
    col = cols[0]
    records = []
    for _, row in df_use.iterrows():
        name = str(row["Associate Name"]).strip()
        cell = row[col]
        if not isinstance(cell, str):
            continue
        m = re.search(r'(\d{1,2}:\d{2})\s*([ap]m)?', cell, flags=re.I)
        if not m:
            continue
        t = m.group(1)
        ampm = (m.group(2) or '').lower()
        hh, mm = map(int, t.split(':'))
        if ampm:
            if ampm == 'pm' and hh != 12:
                hh += 12
            if ampm == 'am' and hh == 12:
                hh = 0
        minutes = hh*60 + mm
        records.append((minutes, t + (ampm if ampm else ''), name))
    groups = defaultdict(list)
    for minutes, label, name in records:
        groups[(minutes, label)].append(name)
    sorted_groups = sorted(groups.items(), key=lambda kv: kv[0][0])
    return [(minu, label, names) for (minu,label), names in sorted_groups]

def render_schedule(groups, launcher_name="Launcher", pad_colors=None):
    if pad_colors is None:
        pad_colors = {1:(74,120,206), 2:(226,40,216), 3:(73,230,54)}
    left_pad_w = 220
    idx_col_w = 50
    name_col_w = 700
    header_h = 120
    row_h = 48
    gap = 2

    total_rows = sum(len(names) for _,_,names in groups)
    height = header_h + total_rows*(row_h+gap) + 40
    width = left_pad_w + idx_col_w + name_col_w + 80

    img = Image.new("RGB", (width, int(height)), (245,245,245))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_pad = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font_title = font = font_bold = font_pad = None

    draw.rectangle([0,0,width,header_h], fill=(255,255,255), outline=(0,0,0))
    draw.text((20,20), "Launcher:", fill=(0,0,0), font=font_title)
    draw.text((20,62), launcher_name, fill=(0,0,0), font=font_title)
    draw.rectangle([left_pad_w,0,width, header_h], outline=(0,0,0))
    draw.text((left_pad_w+80,20), "DRIVER NAME", fill=(0,0,0), font=font_title)

    y = header_h
    idx=1
    for gi,(minutes,label,names) in enumerate(groups):
        pad_num = gi%3 + 1
        pad_color = pad_colors[pad_num]
        block_h = len(names)*(row_h+gap)
        draw.rectangle([0,y,left_pad_w,y+block_h], fill=pad_color, outline=(0,0,0))
        pad_text = f"Pad {pad_num}\n{label}"
        lines = pad_text.split("\n")
        yy = y + block_h/2 - (len(lines)*28)/2
        for line in lines:
            w,h = draw.textbbox((0,0), line, font=font_pad)[2:]
            draw.text((left_pad_w/2 - w/2, yy), line, fill=(0,0,0), font=font_pad)
            yy += 32
        for n in names:
            draw.rectangle([left_pad_w, y, left_pad_w+idx_col_w, y+row_h], fill=(235,240,250), outline=(0,0,0))
            draw.text((left_pad_w+12, y+10), str(idx), fill=(0,0,0), font=font_bold)
            draw.rectangle([left_pad_w+idx_col_w, y, width-20, y+row_h], fill=(220,230,250) if (gi%2==0) else (230,220,240), outline=(0,0,0))
            draw.text((left_pad_w+idx_col_w+12, y+10), n, fill=(0,0,0), font=font)
            y += row_h+gap
            idx += 1
    return img

st.title("SMSO Schedule Builder")
launcher = st.text_input("Launcher name", value="")
file = st.file_uploader("Upload the schedule Excel (.xlsx)", type=["xlsx"])

if file:
    df_use, days = load_rostered_sheet(file.read())
    day_keys = [d.split(",")[0] for d in days]
    day = st.selectbox("Select day of week", options=day_keys, index=0)
    groups = parse_day(df_use, day)
    if not groups:
        st.error(f"No routes found for {day}.")
    else:
        img = render_schedule(groups, launcher)
        st.image(img, caption=f"Schedule for {day}")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.download_button("Download PNG", buf.getvalue(), file_name=f"schedule_{day}.png", mime="image/png")
else:
    st.info("Upload Excel file to get schedule!")
