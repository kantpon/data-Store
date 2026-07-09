import streamlit as st
import cloudinary
import cloudinary.uploader
import io
import datetime
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageOps

st.set_page_config(page_title="อัพโหลดใบเสร็จ", page_icon="🧾", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Sarabun', sans-serif; }
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
    .block-container { background: white; border-radius: 20px; padding: 2.5rem 2rem !important; margin-top: 2rem; box-shadow: 0 20px 60px rgba(0,0,0,0.15); max-width: 680px; }
    h1 { color: #1a1a2e !important; font-weight: 700 !important; text-align: center; }
    .subtitle { text-align: center; color: #6b7280; margin-top: -0.5rem; margin-bottom: 1.5rem; font-size: 1rem; }
    .stButton > button { background: linear-gradient(135deg, #667eea, #764ba2) !important; color: white !important; border: none !important; border-radius: 12px !important; padding: 0.75rem 2rem !important; font-size: 1.1rem !important; font-weight: 600 !important; width: 100%; }
    .success-box { background: #f0fdf4; border: 2px solid #86efac; border-radius: 14px; padding: 1.2rem 1.5rem; color: #166534; margin-top: 1rem; }
    .error-box { background: #fef2f2; border: 2px solid #fca5a5; border-radius: 14px; padding: 1.2rem 1.5rem; color: #991b1b; margin-top: 1rem; }
    .branch-box { background: #eef2ff; border: 2px solid #c7d2fe; border-radius: 14px; padding: 1rem 1.2rem; color: #3730a3; margin-top: 0.6rem; }
    .guide-box { background: #fffbeb; border: 2px solid #fcd34d; border-radius: 14px; padding: 1.2rem 1.4rem; color: #92400e; margin: 1rem 0; line-height: 1.7; }
    .divider { border: none; border-top: 1.5px solid #f3f4f6; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def setup_cloudinary():
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True
    )

@st.cache_resource
def get_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)

def setup_gsheet():
    """
    เชื่อมต่อ Google Sheet (ชีทบันทึกผลลัพธ์) ผ่าน Service Account
    ต้องมี st.secrets["gcp_service_account"] และ st.secrets["gsheet"]["sheet_url"]
    """
    client = get_gsheet_client()
    sheet = client.open_by_url(st.secrets["gsheet"]["sheet_url"])
    worksheet = sheet.worksheet(st.secrets["gsheet"].get("worksheet_name", "receipts"))
    return worksheet

@st.cache_data(ttl=300)
def load_branch_list():
    """
    โหลดรายชื่อสาขาจากชีท "รายชื่อสาขา"
    คอลัมน์ในชีท: A=รหัส, B=รายชื่อสาขา, C=zone
    ตั้งชื่อ worksheet ผ่าน st.secrets["gsheet"]["branch_worksheet_name"] (ค่าเริ่มต้น "รายชื่อสาขา")
    ตั้ง URL ชีทแยกได้ผ่าน st.secrets["gsheet"]["branch_sheet_url"] (ถ้าไม่ตั้ง จะใช้ sheet_url เดิม)
    คืนค่า list ของ dict: [{"code":..., "name":..., "zone":...}, ...]
    """
    try:
        client = get_gsheet_client()
        sheet_url = st.secrets["gsheet"].get("branch_sheet_url", st.secrets["gsheet"]["sheet_url"])
        sheet = client.open_by_url(sheet_url)
        ws_name = st.secrets["gsheet"].get("branch_worksheet_name", "รายชื่อสาขา")
        worksheet = sheet.worksheet(ws_name)
        records = worksheet.get_all_records()  # ใช้แถวแรกเป็น header อัตโนมัติ

        branches = []
        for r in records:
            code = str(r.get("รหัส", "")).strip()
            name = str(r.get("รายชื่อสาขา", "")).strip()
            zone = str(r.get("zone", "")).strip()
            if name:
                branches.append({"code": code, "name": name, "zone": zone})
        return branches, ""
    except Exception as e:
        return [], str(e)

def log_to_sheet(reporter, branch, zone, status, reason="", filename="", url=""):
    """
    บันทึกแถวข้อมูลลง Google Sheet
    ลำดับคอลัมน์: วันที่เวลา, ผู้กรอก, สาขา, Zone, สถานะ, เหตุผล, ชื่อไฟล์, ลิงก์รูป
    คืน True ถ้าสำเร็จ, False ถ้าไม่สำเร็จ (พร้อม error message)
    """
    try:
        worksheet = setup_gsheet()
        ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        worksheet.append_row([ts, reporter, branch, zone, status, reason, filename, url])
        return True, ""
    except Exception as e:
        return False, str(e)

def fix_orientation(file, thumb_side: int = 500, extra_rotation: int = 0):
    """เปิดรูป หมุนตาม EXIF ให้ถูกทาง + หมุนเพิ่มตามที่ผู้ใช้กดปุ่ม แล้วย่อเป็นรูปเล็กสำหรับพรีวิว (โหลดเร็ว)"""
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    if extra_rotation:
        img = img.rotate(-extra_rotation, expand=True)
    img.thumbnail((thumb_side, thumb_side), Image.LANCZOS)
    return img

def compress_image(file, max_side: int = 1280, quality: int = 78, extra_rotation: int = 0) -> tuple[bytes, int, int]:
    """
    ลดขนาดรูปให้ด้านยาวไม่เกิน max_side px แล้ว compress เป็น JPEG
    คืน (bytes, new_width, new_height)
    """
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)  # หมุนรูปให้ตรงทิศทางจริงตาม EXIF ก่อน compress
    if extra_rotation:
        img = img.rotate(-extra_rotation, expand=True)  # หมุนเพิ่มตามที่ผู้ใช้กดปุ่ม
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), img.width, img.height

def upload_to_cloudinary(image_bytes, filename):
    """
    อัพโหลดขึ้น Cloudinary โดยเก็บรวมไว้ในโฟลเดอร์ branch โฟลเดอร์เดียวทั้งหมด
    """
    result = cloudinary.uploader.upload(
        image_bytes,
        folder="branch",
        public_id=filename,
        resource_type="image",
        overwrite=False,
    )
    return result.get("secure_url", "")

setup_cloudinary()

if "show_sent_dialog" not in st.session_state:
    st.session_state.show_sent_dialog = False
if "sent_count" not in st.session_state:
    st.session_state.sent_count = 0

@st.dialog("✅ ส่งข้อมูลสำเร็จ")
def show_success_dialog():
    st.markdown("### คุณส่งแล้ว")
    st.write(f"อัพโหลดใบเสร็จ {st.session_state.sent_count} รูป และบันทึกข้อมูลเรียบร้อยแล้ว")
    if st.button("ตกลง", use_container_width=True):
        st.session_state.show_sent_dialog = False
        st.rerun()

st.markdown("# 🧾 อัพโหลดใบเสร็จ")
st.markdown('<p class="subtitle">รูปจะถูกส่งเข้า Cloudinary โดยตรง · ปลอดภัย</p>', unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

st.markdown("#### 📋 จำนวนใบเสร็จในรูป")
mode = st.radio("โหมด", [ "2 ใบเสร็จ"], label_visibility="collapsed")
num_receipts = int(mode[0])

# ── ชื่อผู้กรอก (พิมพ์เอง) ──
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 🙋 ชื่อผู้กรอก")
reporter_name = st.text_input(
    "ชื่อผู้กรอก",
    placeholder="พิมพ์ชื่อผู้กรอกข้อมูล",
    label_visibility="collapsed",
)

# ── เลือกสาขา (พิมพ์ค้นหาชื่อได้) แทนการพิมพ์เอง ──
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 🏢 เลือกสาขา")

branches, branch_err = load_branch_list()

if branch_err:
    st.markdown(
        f'<div class="error-box">❌ โหลดรายชื่อสาขาไม่สำเร็จ: {branch_err}<br>'
        f'ตรวจสอบว่ามี worksheet ชื่อ "รายชื่อสาขา" (หรือชื่อที่ตั้งใน secrets) '
        f'และมีคอลัมน์หัวตาราง รหัส, รายชื่อสาขา, zone</div>',
        unsafe_allow_html=True,
    )
    sender_name, zone = "", ""
elif not branches:
    st.markdown('<div class="error-box">⚠️ ยังไม่มีรายชื่อสาขาในชีท กรุณาเพิ่มข้อมูลก่อนใช้งาน</div>', unsafe_allow_html=True)
    sender_name, zone = "", ""
else:
    # ── ขั้น 1: เลือก Zone ก่อน เพื่อตัดตัวเลือกให้แคบลง ──
    st.caption("📍 ขั้นที่ 1: เลือก Zone")
    zone_list = sorted({b["zone"] for b in branches if b["zone"]})
    zone_options = ["ทั้งหมด (ทุก Zone)"] + zone_list
    picked_zone = st.selectbox(
        "เลือก Zone",
        zone_options,
        label_visibility="collapsed",
    )

    if picked_zone == "ทั้งหมด (ทุก Zone)":
        filtered_branches = branches
    else:
        filtered_branches = [b for b in branches if b["zone"] == picked_zone]

    # ── ขั้น 2: พิมพ์ค้นหา/เลือกสาขา จากรายการที่กรองแล้ว (ค้นหาได้ทั้งรหัสและชื่อ) ──
    def display_label(b):
        if b["code"]:
            return f'{b["code"]} | {b["name"]}'
        return b["name"]

    st.caption(f"🔎 ขั้นที่ 2: พิมพ์รหัสหรือชื่อเพื่อค้นหา/เลือกสาขา ({len(filtered_branches)} สาขา)")
    branch_options = ["-- กรุณาเลือกสาขา --"] + [display_label(b) for b in filtered_branches]
    picked = st.selectbox(
        "เลือกสาขา",
        branch_options,
        label_visibility="collapsed",
        key=f"branch_select_{picked_zone}",
    )

    if picked != "-- กรุณาเลือกสาขา --":
        matched = next((b for b in filtered_branches if display_label(b) == picked), None)
    else:
        matched = None

    if matched:
        sender_name = matched["name"]
        zone = matched["zone"]
        code_note = f' &nbsp;·&nbsp; รหัส: {matched["code"]}' if matched["code"] else ""
        st.markdown(
            f'<div class="branch-box">🏪 <strong>{matched["name"]}</strong> '
            f'&nbsp;·&nbsp; Zone {matched["zone"] or "-"}{code_note}</div>',
            unsafe_allow_html=True,
        )
    else:
        sender_name, zone = "", ""

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 📦 เครื่องที่ขาด")
st.caption("เลือก \"ครบ\" หรือเลือกเครื่องที่ขาดได้หลายเครื่อง (เลือก \"ครบ\" แล้วจะเลือกเครื่องอื่นไม่ได้)")

def _enforce_completeness_exclusive():
    prev = st.session_state.get("_prev_completeness_sel", [])
    cur = st.session_state.completeness_sel
    added = [x for x in cur if x not in prev]
    if added:
        new_item = added[0]
        if new_item == "ครบ":
            st.session_state.completeness_sel = ["ครบ"]
        elif "ครบ" in cur:
            st.session_state.completeness_sel = [x for x in cur if x != "ครบ"]
    st.session_state["_prev_completeness_sel"] = st.session_state.completeness_sel

completeness_sel = st.multiselect(
    "เครื่องที่ขาด",
    ["ครบ", "ขาดเครื่องที่ 1", "ขาดเครื่องที่ 2", "ขาดเครื่องที่ 3", "ขาดเครื่องที่ 4"],
    label_visibility="collapsed",
    key="completeness_sel",
    on_change=_enforce_completeness_exclusive,
)

if "ครบ" in completeness_sel:
    completeness = "ครบ"
elif completeness_sel:
    completeness = "ไม่ครบ"
else:
    completeness = "-- กรุณาเลือก --"

incomplete_reason = ", ".join([x for x in completeness_sel if x != "ครบ"])

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 📷 เลือกรูปภาพ (เลือกได้หลายรูปพร้อมกัน)")
st.caption("💡 กด Ctrl ค้างไว้แล้วคลิกเลือกหลายรูปพร้อมกัน")

uploaded_files = st.file_uploader(
    "เลือกไฟล์",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f"#### 🔍 ตรวจสอบรูปก่อนส่ง ({len(uploaded_files)} รูป)")

    st.markdown(
        '<div class="guide-box">'
        '📸 <strong>โปรดถ่ายบิลให้ถูกต้อง</strong><br>'
        '<br><br>'
        '1. ภาพชัดให้อ่านค่าได้<br>'
        '2. มีระยะห่างจากกันระหว่างบิล<br>'
        '3. ภาพเป็นแนวตั้ง (หากเป็นแนวนอนสามารถปรับหมุนได้)<br><br>'

        '</div>',
        unsafe_allow_html=True,
    )

    if "rotations" not in st.session_state:
        st.session_state.rotations = {}

    for i, f in enumerate(uploaded_files):
        rot_key = f"{f.name}_{f.size}_{i}"
        current_rot = st.session_state.rotations.get(rot_key, 0)
        preview_img = fix_orientation(f, thumb_side=1000, extra_rotation=current_rot)
        st.image(preview_img, caption=f.name, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("↺ หมุนซ้าย", key=f"rotate_left_{rot_key}", use_container_width=True):
                st.session_state.rotations[rot_key] = (current_rot - 90) % 360
                st.rerun()
        with c2:
            if st.button("↻ หมุนขวา", key=f"rotate_right_{rot_key}", use_container_width=True):
                st.session_state.rotations[rot_key] = (current_rot + 90) % 360
                st.rerun()
        with c3:
            if st.button("🔃 กลับหัว", key=f"rotate_flip_{rot_key}", use_container_width=True):
                st.session_state.rotations[rot_key] = (current_rot + 180) % 360
                st.rerun()

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

    st.info(f"จะบันทึกในโฟลเดอร์ branch ทั้ง {len(uploaded_files)} รูป")
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    if st.button(f"☁️ อัพโหลดทั้งหมด ({len(uploaded_files)} รูป)"):
        missing = []
        if not reporter_name.strip():
            missing.append("ชื่อผู้กรอก")
        if not sender_name.strip():
            missing.append("สาขา (กรุณาเลือกจากรายการ)")
        if completeness == "-- กรุณาเลือก --":
            missing.append("เครื่องที่ขาด")
        if completeness == "ไม่ครบ" and not incomplete_reason.strip():
            missing.append("เครื่องที่ขาด (เลือกอย่างน้อย 1 เครื่อง)")

        if missing:
            items = "".join([f"<br>• {m}" for m in missing])
            st.markdown(f'<div class="error-box">⚠️ กรุณากรอกข้อมูลให้ครบก่อนอัพโหลด:{items}</div>', unsafe_allow_html=True)
        else:
            safe_sender = sender_name.strip().replace("/", "-").replace("\\", "-")
            results = []
            prog = st.progress(0, text="กำลังอัพโหลด...")

            for idx, f in enumerate(uploaded_files):
                try:
                    # ── compress: max 1280px ด้านยาว, quality 78 + หมุนตามที่ผู้ใช้เลือก ──
                    f.seek(0)  # รีเซ็ตตำแหน่งไฟล์ เพราะพรีวิวด้านบนอ่านไปแล้ว
                    rot_key = f"{f.name}_{f.size}_{idx}"
                    extra_rot = st.session_state.get("rotations", {}).get(rot_key, 0)
                    img_bytes, new_w, new_h = compress_image(f, max_side=1280, quality=78, extra_rotation=extra_rot)

                    ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    fname = f"{safe_sender}_{ts_file}_{idx+1}"
                    secure_url = upload_to_cloudinary(img_bytes, fname)

                    status_label = "ครบ" if completeness == "ครบ" else "ไม่ครบ"
                    log_ok, log_err = log_to_sheet(
                        reporter=reporter_name.strip(),
                        branch=sender_name.strip(),
                        zone=zone.strip(),
                        status=status_label,
                        reason=incomplete_reason.strip(),
                        filename=f"{fname}.jpg",
                        url=secure_url,
                    )

                    results.append({
                        "filename": fname,
                        "ok": True,
                        "size_kb": round(len(img_bytes) / 1024),
                        "dim": f"{new_w}×{new_h}",
                        "log_ok": log_ok,
                        "log_err": log_err,
                    })
                except Exception as e:
                    results.append({"filename": f.name, "ok": False, "err": str(e)})

                prog.progress((idx+1)/len(uploaded_files), text=f"อัพโหลด {idx+1}/{len(uploaded_files)}...")

            prog.empty()
            ok   = [r for r in results if r["ok"]]
            fail = [r for r in results if not r["ok"]]

            if ok:
                lines = [f"<strong>✅ อัพโหลดสำเร็จ {len(ok)} รูป!</strong>"]
                for r in ok:
                    lines.append(f"📄 {r['filename']}.jpg &nbsp;·&nbsp; {r['dim']} px &nbsp;·&nbsp; {r['size_kb']} KB")
                st.markdown(f'<div class="success-box">{"<br>".join(lines)}</div>', unsafe_allow_html=True)

                sheet_fail = [r for r in ok if not r.get("log_ok", True)]
                if sheet_fail:
                    lines2 = ["<strong>⚠️ อัพโหลดรูปสำเร็จ แต่บันทึกลง Google Sheet ไม่สำเร็จ:</strong>"]
                    lines2 += [f"• {r['filename']}: {r.get('log_err','')}" for r in sheet_fail]
                    st.markdown(f'<div class="error-box">{"<br>".join(lines2)}</div>', unsafe_allow_html=True)
                else:
                    st.session_state.show_sent_dialog = True
                    st.session_state.sent_count = len(ok)
                    st.rerun()
            if fail:
                lines = [f"<strong>❌ ไม่สำเร็จ {len(fail)} รูป</strong>"]
                lines += [f"• {r['filename']}: {r.get('err','')}" for r in fail]
                st.markdown(f'<div class="error-box">{"<br>".join(lines)}</div>', unsafe_allow_html=True)

if st.session_state.show_sent_dialog:
    show_success_dialog()

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;color:#d1d5db;font-size:0.8rem;">รูปทั้งหมดจะถูกส่งเข้าบัญชี Cloudinary ของเจ้าของระบบเท่านั้น</p>', unsafe_allow_html=True)
